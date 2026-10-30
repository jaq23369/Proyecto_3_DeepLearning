"""Salidas para la persona usuaria: reporte Markdown/JSON y tarea copiable.

La tarea de corrección se arma solo con datos ya validados (sin otra llamada
al LLM) para entregársela a Codex, Claude Code u otro asistente. No afirma que
el cambio ya se aplicó y le pide al asistente comprobarlo antes de terminar.
"""

from __future__ import annotations

import json
from datetime import datetime

from src.schemas import SEVERITY_LABELS, STATUS_LABELS, TYPE_LABELS, AnalysisResult, Finding

MAX_QUOTE_CHARS = 400


def _quote(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_QUOTE_CHARS else text[:MAX_QUOTE_CHARS] + " …"


def can_handoff(f: Finding) -> tuple[bool, str]:
    """Una tarea solo se genera si hay evidencia verificada."""
    if f.status == "insufficient_evidence":
        return False, "La evidencia no alcanza para pedir un cambio concreto. Revisa los archivos indicados a mano."
    if not any(e.verified is not False for e in f.evidence):
        return False, "Ninguna cita se pudo verificar en los archivos."
    return True, ""


def task_for_finding(f: Finding, edited_suggestion: str | None = None) -> str:
    """Texto breve y copiable para un asistente de programación."""
    ok, why = can_handoff(f)
    if not ok:
        return why

    lines = [
        f"Tarea: corregir una inconsistencia detectada por SkillDoc Check ({TYPE_LABELS.get(f.type, f.type)}).",
        "",
        f"Problema: {f.summary}",
        f"Por qué importa: {f.reason}",
        f"Certeza del diagnóstico: {STATUS_LABELS.get(f.status, f.status)}.",
        "",
        "Evidencia (ruta y líneas):",
    ]
    for e in f.evidence:
        if e.verified is False:
            continue
        rango = f"{e.start_line}" if e.start_line == e.end_line else f"{e.start_line}-{e.end_line}"
        lines.append(f"- {e.path}:{rango}")
        lines.append("  ```")
        lines += [f"  {q}" for q in _quote(e.quote).split("\n")]
        lines.append("  ```")

    suggestion = edited_suggestion if edited_suggestion is not None else f.suggested_edit
    if suggestion.strip():
        origen = "editada por la persona usuaria" if edited_suggestion is not None and edited_suggestion != f.suggested_edit else "sugerida por SkillDoc Check"
        lines += ["", f"Cambio propuesto en {f.edit_path} ({origen}, revísala antes de aplicarla):", suggestion.strip()]
    if f.limitations:
        lines += ["", f"Limitaciones: {f.limitations}"]
    lines += [
        "",
        "Antes de cambiar nada, abre los archivos citados y confirma que el problema sigue ahí.",
        "Haz el cambio mínimo, sin tocar otras partes del proyecto.",
        "Si el cambio afecta código o pruebas, ejecuta las pruebas existentes y reporta el resultado.",
        "Si ves que el diagnóstico no es correcto, no apliques el cambio y explica por qué.",
    ]
    return "\n".join(lines)


def _model_label(result: AnalysisResult) -> str:
    if not result.usage.calls:
        return "solo reglas automáticas (sin LLM)"
    where = {"api": "API, el contenido salió de la máquina", "local": "local, el contenido no salió de la máquina"}
    return f"{result.model} ({where.get(result.provider, result.provider)})"


def to_json(result: AnalysisResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


def to_markdown(result: AnalysisResult, edits: dict[str, str] | None = None) -> str:
    edits = edits or {}
    u = result.usage
    out = [
        "# Reporte de SkillDoc Check",
        "",
        f"- Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Modelo: {_model_label(result)}",
        f"- Archivos examinados: {len(result.files_examined)}",
    ]
    if u.calls:
        out += [
            f"- Tokens: {u.input_tokens} de entrada y {u.output_tokens} de salida",
            f"- Tiempo del modelo: {u.latency_s:.1f} s",
        ]
    if result.provider == "api" and u.calls:
        out.append(f"- Costo estimado: {u.cost_usd:.5f} USD")
    if result.error:
        out += ["", f"> Aviso: {result.error}"]
    for w in result.warnings:
        out += ["", f"> {w}"]

    out += ["", f"## Hallazgos ({len(result.findings)})", ""]
    if not result.findings:
        out.append("No se detectaron problemas en los archivos examinados. Esto no garantiza que todo el repositorio sea correcto.")
    for f in result.findings:
        out += [
            f"### {f.id}. {f.summary}",
            "",
            f"- Tipo: {TYPE_LABELS.get(f.type, f.type)}",
            f"- Estado: {STATUS_LABELS.get(f.status, f.status)}",
            f"- Severidad: {SEVERITY_LABELS.get(f.severity, f.severity)}",
            f"- Origen: {'regla automática' if f.origin == 'rule' else 'modelo'}",
            "",
            f.reason,
            "",
        ]
        for e in f.evidence:
            mark = "" if e.verified is not False else " (cita no verificada)"
            out.append(f"`{e.path}:{e.start_line}-{e.end_line}`{mark}")
            out += ["```", _quote(e.quote), "```"]
        suggestion = edits.get(f.id, f.suggested_edit)
        if suggestion:
            out += ["", f"Propuesta para `{f.edit_path}`:", "", suggestion]
        if f.limitations:
            out += ["", f"Limitaciones: {f.limitations}"]
        out.append("")

    out += ["## Archivos examinados", ""] + [f"- {p}" for p in result.files_examined]
    if result.files_skipped:
        out += ["", "## Archivos omitidos", ""] + [f"- {s['path']}: {s['reason']}" for s in result.files_skipped]
    return "\n".join(out) + "\n"
