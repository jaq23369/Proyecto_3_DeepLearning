"""Pipeline completo de un análisis.

ingest → reglas deterministas → selección de contexto → prompt → LLM (API o
local) → validación de citas → unión con los hallazgos de las reglas.

Las iteraciones del experimento son combinaciones de opciones de este mismo
pipeline (ver ITERATIONS), así cada una cambia una sola cosa respecto a la
anterior.
"""

from __future__ import annotations

from pathlib import Path

from src import deterministic_checks
from src.ingest import Repo
from src.model_provider import ModelProvider, ModelRequest, get_provider
from src.schemas import LLM_OUTPUT_SCHEMA, AnalysisResult, Finding, Usage
from src.select_context import DEFAULT_BUDGET_TOKENS, build_context
from src.validate_output import validate_findings

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

PROMPT_FILES = {
    "v0": "v0_baseline.txt",
    "v1": "v1_structured.txt",
    "v2": "v2_structured.txt",
}

# Cada iteración cambia una sola cosa respecto a la anterior.
ITERATIONS = {
    # Baseline: prompt simple, mismo modelo, mismo contexto. Solo se fuerza el
    # esquema JSON para poder puntuarlo igual que el resto.
    "V0": {"prompt_version": "v0", "use_rules": False, "validate": False},
    # Prompt estructurado: tipos definidos, obligación de citar, ejemplos breves.
    "V1": {"prompt_version": "v1", "use_rules": False, "validate": False},
    # Reglas deterministas + validación de rutas, líneas y citas.
    "V2": {"prompt_version": "v1", "use_rules": True, "validate": True},
    # Prompt v2: criterios explícitos para traslape, redundancia y lo que no es
    # contradicción; la cita debe ser el texto que demuestra el problema.
    "V3": {"prompt_version": "v2", "use_rules": True, "validate": True},
    # Mismo pipeline que V3 con razonamiento previo del modelo (thinking).
    "V4": {"prompt_version": "v2", "use_rules": True, "validate": True, "thinking": "adaptive"},
}
FINAL_ITERATION = "V4"

STATUS_ORDER = {"confirmed": 0, "possible_conflict": 1, "insufficient_evidence": 2}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def load_prompt(version: str) -> tuple[str, str]:
    text = (PROMPTS_DIR / PROMPT_FILES[version]).read_text(encoding="utf-8")
    system = text.split("### SYSTEM", 1)[1].split("### USER", 1)[0].strip()
    user = text.split("### USER", 1)[1].strip()
    return system, user


def _facts_block(facts: dict, rule_findings: list[Finding]) -> str:
    lines = ["Datos que el sistema ya verificó con reglas (úsalos como hechos):"]
    routes = facts.get("routes") or []
    lines.append("- Rutas definidas en el código: " + (", ".join(routes) if routes else "no se detectaron rutas FastAPI."))
    skills = facts.get("skills") or []
    lines.append("- Skills encontradas: " + (", ".join(skills) if skills else "ninguna."))
    if rule_findings:
        lines.append("- Problemas ya detectados por las reglas (no los repitas):")
        for f in rule_findings:
            where = ", ".join(f"{e.path}:{e.start_line}" for e in f.evidence[:2])
            lines.append(f"  * [{f.type}] {f.summary} ({where})")
    lines.append(
        "Concéntrate en lo que necesita interpretar el texto: nombres de campos, comportamientos, versiones, "
        "traslapes entre skills e instrucciones repetidas con palabras distintas."
    )
    return "\n".join(lines)


def _overlaps(a: Finding, b: Finding) -> bool:
    """Dos hallazgos hablan de lo mismo si comparten una cita del mismo archivo."""
    same_family = a.type == b.type or {a.type, b.type} <= {"readme_code", "skill_project"}
    if not same_family:
        return False
    for ea in a.evidence:
        for eb in b.evidence:
            if ea.path == eb.path and ea.start_line <= eb.end_line and eb.start_line <= ea.end_line:
                if ea.path.endswith(".py"):
                    continue  # la misma ruta de código puede sustentar problemas distintos
                return True
    return False


def merge_findings(rule_findings: list[Finding], llm_findings: list[Finding]) -> list[Finding]:
    merged = list(rule_findings)
    for f in llm_findings:
        dup = next((r for r in merged if _overlaps(r, f)), None)
        if dup is None:
            merged.append(f)
        elif dup.origin == "rule" and f.origin == "llm" and f.suggested_edit and f.edit_path == dup.edit_path:
            # La regla aporta la certeza; el modelo suele proponer un texto mejor.
            dup.suggested_edit = f.suggested_edit
            dup.validation_notes.append("Propuesta de corrección redactada por el modelo.")
    merged.sort(key=lambda f: (STATUS_ORDER.get(f.status, 9), SEVERITY_ORDER.get(f.severity, 9), f.type))
    for i, f in enumerate(merged, start=1):
        f.id = f"F{i:02d}"
    return merged


def analyze_repo(
    repo: Repo,
    provider: str | ModelProvider = "api",
    prompt_version: str = "v1",
    use_rules: bool = True,
    validate: bool = True,
    context_mode: str = "selected",
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    max_tokens: int = 4000,
    use_llm: bool = True,
) -> AnalysisResult:
    """Corre el análisis completo y devuelve un AnalysisResult.

    Si el modelo falla, igual se devuelven los hallazgos de las reglas y el
    error queda en result.error para mostrarlo al usuario.
    """
    model_provider = get_provider(provider) if isinstance(provider, str) else provider
    warnings: list[str] = []
    if not repo.is_complete:
        warnings.append(
            "Se analizaron archivos sueltos. No se puede afirmar que un archivo o ruta no existe, "
            "solo que no está entre los archivos subidos."
        )

    rule_findings: list[Finding] = []
    facts: dict = {}
    if use_rules:
        rule_findings, facts = deterministic_checks.run_all(repo)

    context = build_context(repo, mode=context_mode, budget_tokens=budget_tokens)
    if context.dropped:
        warnings.append(
            f"{len(context.dropped)} archivo(s) o fragmento(s) no entraron en el límite de contexto: "
            + ", ".join(context.dropped[:5])
            + ("…" if len(context.dropped) > 5 else "")
        )

    system, user_tpl = load_prompt(prompt_version)
    facts_text = _facts_block(facts, rule_findings) if use_rules else ""
    user = user_tpl.replace("{facts}", facts_text).replace("{context}", context.text)
    request = ModelRequest(system=system, user=user, json_schema=LLM_OUTPUT_SCHEMA, max_tokens=max_tokens)

    usage = Usage()
    error = ""
    llm_findings: list[Finding] = []
    settings = {**model_provider.describe(), "max_tokens": max_tokens, "budget_tokens": budget_tokens}
    model_name = settings.get("model", "")

    if use_llm:
        res = model_provider.analyze(request)
        usage = Usage(
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            cost_usd=res.cost_usd,
            latency_s=res.latency_s,
            calls=1,
            retries=res.retries,
        )
        settings.update(res.settings)
        model_name = res.model
        if res.ok:
            llm_findings = [Finding.from_dict(d, origin="llm") for d in res.parsed.get("findings", []) if isinstance(d, dict)]
        else:
            error = res.error
            if rule_findings:
                warnings.append("El modelo no respondió bien; se muestran solo las comprobaciones automáticas.")

    if validate:
        llm_findings, vstats = validate_findings(llm_findings, repo)
        settings["validation"] = vstats.__dict__

    findings = merge_findings(rule_findings, llm_findings)
    if not use_llm:
        model_name = "solo reglas"

    return AnalysisResult(
        findings=findings,
        files_examined=sorted(repo.files),
        files_skipped=repo.skipped,
        provider=model_provider.name,
        model=model_name,
        prompt_version=prompt_version,
        context_mode=context_mode,
        context_hash=context.hash,
        context_tokens_est=context.tokens_est,
        usage=usage,
        settings=settings,
        warnings=warnings,
        error=error,
    )


def analyze_iteration(repo: Repo, iteration: str, provider: str | ModelProvider = "api", **kwargs) -> AnalysisResult:
    """Atajo para correr una iteración con nombre (V0, V1, V2)."""
    opts = {**ITERATIONS[iteration], **kwargs}
    thinking = opts.pop("thinking", "off")
    model_provider = get_provider(provider) if isinstance(provider, str) else provider
    # El razonamiento previo es un ajuste del proveedor; se fija por iteración
    # y se restaura al terminar para no afectar otras corridas.
    previous = getattr(model_provider, "thinking", None)
    if previous is not None:
        model_provider.thinking = thinking
    try:
        result = analyze_repo(repo, provider=model_provider, **opts)
    finally:
        if previous is not None:
            model_provider.thinking = previous
    result.settings["iteration"] = iteration
    return result
