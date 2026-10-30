"""Interfaz web de SkillDoc Check (Streamlit).

    streamlit run app.py

Todo el análisis lo hace el pipeline de src/; aquí solo se carga el proyecto,
se elige el modelo y se muestran los hallazgos con su evidencia.
"""

from __future__ import annotations

import json
import os
import time

import streamlit as st

from src.analyze import FINAL_ITERATION, analyze_iteration
from src.demo_cache import example_path, has_cached, list_examples, load_cached, zip_bytes
from src.handoff import can_handoff, task_for_finding, to_json, to_markdown
from src.ingest import MAX_FILES, MAX_ZIP_BYTES, IngestError, load_dir, load_files, load_zip
from src.schemas import SEVERITY_LABELS, STATUS_LABELS, TYPE_LABELS

st.set_page_config(page_title="SkillDoc Check", page_icon=":mag:", layout="wide")

API_MODEL = os.getenv("SKILLDOC_API_MODEL", "claude-haiku-5-5")
LOCAL_MODEL = os.getenv("SKILLDOC_LOCAL_MODEL", "qwen3:8b")

PROVIDERS = {
    "api": {
        "label": f"API ({API_MODEL})",
        "privacy": "El contenido de los archivos se envía a Anthropic. Necesita internet y una clave de API.",
    },
    "local": {
        "label": f"Local ({LOCAL_MODEL} con Ollama)",
        "privacy": "Todo se queda en esta computadora y no necesita internet. La primera respuesta es la más lenta.",
    },
}
STATUS_COLORS = {"confirmed": "green", "possible_conflict": "orange", "insufficient_evidence": "gray"}
SEVERITY_COLORS = {"high": "red", "medium": "orange", "low": "blue"}
LANGUAGES = {".py": "python", ".md": "markdown", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml", ".json": "json"}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def copy_button(text: str, label: str) -> None:
    """Botón que copia el texto al portapapeles (Streamlit no trae uno propio).

    st.iframe comparte origen con la app y el texto sale de archivos subidos,
    así que el payload se escapa por completo: no puede contener <, > ni &.
    """
    payload = json.dumps(text).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    st.iframe(
        f"""
        <button id="b" style="font:600 14px sans-serif;padding:8px 14px;border:1px solid #888;border-radius:8px;
                 background:transparent;color:inherit;cursor:pointer">{label}</button>
        <script>
        const text = {payload};
        const b = document.getElementById('b');
        b.onclick = async () => {{
          try {{ await navigator.clipboard.writeText(text); }}
          catch (e) {{
            const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t);
            t.select(); document.execCommand('copy'); t.remove();
          }}
          b.textContent = 'Copiada';
          setTimeout(() => b.textContent = {json.dumps(label)}, 1500);
        }};
        </script>
        """,
        height=46,
    )


def load_uploaded(files) -> object:
    """Convierte lo que subió la persona en un Repo. Lanza IngestError con un mensaje legible."""
    zips = [f for f in files if f.name.lower().endswith(".zip")]
    if zips and len(files) > 1:
        raise IngestError("Sube un solo ZIP o varios archivos sueltos, no las dos cosas a la vez.")
    if zips:
        return load_zip(zips[0].getvalue())
    return load_files([(f.name, f.getvalue()) for f in files])


def run_analysis(repo, provider: str, reasoning: bool, example: str | None):
    """Corre el pipeline y devuelve (resultado, segundos). Nunca lanza: los errores quedan en result.error."""
    iteration = FINAL_ITERATION if reasoning else "V3"
    start = time.perf_counter()
    try:
        result = analyze_iteration(repo, iteration, provider=provider)
    except Exception as exc:  # p. ej. falta la clave de API: se muestran al menos las reglas
        result = analyze_iteration(repo, iteration, provider=provider, use_llm=False)
        result.error = f"No se pudo usar el modelo ({exc.__class__.__name__}). Revisa la configuración del modo elegido."
        result.provider = provider
    elapsed = time.perf_counter() - start
    if result.error and example and has_cached(example):
        live_error = result.error
        result = load_cached(example)
        result.warnings.insert(0, f"El análisis en vivo falló: {live_error}")
    return result, elapsed


def model_label(result) -> str:
    if result.settings.get("cached"):
        return f"{result.model} (resultado precalculado, no es un análisis en vivo)"
    if not result.usage.calls:
        return "solo reglas automáticas (sin modelo)"
    where = {"api": "API, el contenido salió de esta máquina", "local": "local, el contenido no salió de esta máquina"}
    return f"{result.model} ({where.get(result.provider, result.provider)})"


# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------

st.title("SkillDoc Check")
st.markdown(
    "Revisa si las **skills** (`SKILL.md`), el **README** y el **código** de un proyecto siguen diciendo lo mismo. "
    "Para cada problema muestra la evidencia con archivo y línea, propone una corrección que puedes editar y arma "
    "una tarea lista para copiarle a tu asistente de programación (Claude Code, Codex u otro)."
)
with st.expander("Qué detecta y qué formatos acepta"):
    st.markdown(
        "- **README vs código**: el README documenta algo que el código ya no hace (rutas, campos, límites, comandos).\n"
        "- **Skill desactualizada**: una skill menciona archivos, rutas o comportamientos que cambiaron.\n"
        "- **Traslape entre skills**: dos skills dicen servir para lo mismo. Es un riesgo de conflicto, no una falla comprobada.\n"
        "- **Instrucción redundante**: la misma instrucción repetida en varias skills.\n"
        "- **Formato de `SKILL.md`**: frontmatter sin `name` o `description`.\n\n"
        f"Acepta un **ZIP** (hasta {MAX_ZIP_BYTES // (1024 * 1024)} MB) o **archivos sueltos** (`README.md`, `SKILL.md`, `.py`, "
        f"`pyproject.toml`, `requirements.txt`), hasta {MAX_FILES} archivos de texto. Está hecho para proyectos "
        "**Python/FastAPI**. No ejecuta nada de tu proyecto, no instala skills y no cambia tus archivos."
    )

# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("1. Tu proyecto")
    uploaded = st.file_uploader(
        "ZIP del proyecto o archivos sueltos",
        accept_multiple_files=True,
        help="Con archivos sueltos solo se puede decir que algo no está entre los archivos subidos, no que no existe.",
    )
    examples = list_examples()
    ex_col, btn_col = st.columns([3, 2])
    example = ex_col.selectbox("O prueba con un ejemplo", examples, label_visibility="collapsed") if examples else None
    use_example = btn_col.button("Probar con un ejemplo", use_container_width=True, disabled=not examples)
    if example:
        st.download_button(
            "Descargar el ZIP del ejemplo",
            zip_bytes(example),
            file_name=f"{example}.zip",
            mime="application/zip",
            help="Para probar la subida de un ZIP igual que lo haría un visitante.",
        )

with right:
    st.subheader("2. Modelo")
    provider = st.radio(
        "Quién hace el análisis",
        list(PROVIDERS),
        format_func=lambda k: PROVIDERS[k]["label"],
        label_visibility="collapsed",
    )
    if provider == "api":
        st.warning(PROVIDERS[provider]["privacy"], icon=":material/cloud_upload:")
    else:
        st.success(PROVIDERS[provider]["privacy"], icon=":material/lock:")
    reasoning = st.checkbox(
        "Razonamiento previo del modelo",
        value=True,
        help="Es la configuración final del proyecto (iteración V4). Desactivarlo es más rápido pero reporta más ruido.",
    )
    analyze_clicked = st.button("Analizar", type="primary", use_container_width=True, disabled=not uploaded)

# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------

source = None
if use_example and example:
    source = ("example", example)
elif analyze_clicked and uploaded:
    source = ("upload", None)

if source:
    try:
        if source[0] == "example":
            repo = load_dir(example_path(source[1]))
        else:
            repo = load_uploaded(uploaded)
    except IngestError as exc:
        st.session_state.pop("result", None)
        st.error(str(exc))
    else:
        wait = "la API tarda entre 3 y 13 segundos" if provider == "api" else "el modelo local puede tardar un par de minutos la primera vez"
        with st.spinner(f"Analizando con {PROVIDERS[provider]['label']}: {wait}…"):
            result, elapsed = run_analysis(repo, provider, reasoning, source[1])
        st.session_state.update(
            result=result,
            elapsed=elapsed,
            run_n=st.session_state.get("run_n", 0) + 1,
            source_name=source[1] or "tu proyecto",
        )

# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------

result = st.session_state.get("result")
if result is None:
    st.info("Sube un proyecto o elige un ejemplo para empezar.")
    st.stop()

run_n = st.session_state["run_n"]
u = result.usage
st.divider()
st.subheader(f"Resultado de {st.session_state['source_name']}")
st.caption(f"Diagnóstico producido por: {model_label(result)}")

if result.error:
    st.error(result.error)
for w in result.warnings:
    st.warning(w)

metrics = st.columns(4)
metrics[0].metric("Hallazgos", len(result.findings))
metrics[1].metric("Tiempo total", f"{st.session_state['elapsed']:.1f} s")
if u.calls and not result.settings.get("cached"):
    metrics[2].metric("Tiempo del modelo", f"{u.latency_s:.1f} s")
    metrics[3].metric("Tokens", f"{u.input_tokens} + {u.output_tokens}", help="Entrada + salida")
    if result.provider == "api":
        st.caption(f"Costo estimado de este análisis: {u.cost_usd:.5f} USD.")
    else:
        st.caption("Modelo local: sin factura por solicitud (usa memoria, energía y tiempo de esta máquina).")

edits = {
    f.id: st.session_state.get(f"edit_{run_n}_{f.id}", f.suggested_edit) for f in result.findings
}
dl1, dl2, _ = st.columns([2, 2, 3])
dl1.download_button("Descargar reporte (Markdown)", to_markdown(result, edits), "skilldoc_reporte.md", "text/markdown", use_container_width=True)
dl2.download_button("Descargar reporte (JSON)", to_json(result), "skilldoc_reporte.json", "application/json", use_container_width=True)

if not result.findings:
    if not result.error:
        st.success("No se detectaron problemas en los archivos examinados.")
        st.caption("Esto no garantiza que todo el repositorio esté bien: solo se revisó lo que aparece en la lista de archivos examinados.")
else:
    for f in result.findings:
        with st.container(border=True):
            st.markdown(f"**{f.id}. {f.summary}**")
            st.badge(TYPE_LABELS.get(f.type, f.type), color="violet")
            badges = st.columns([1, 1, 1, 3])
            with badges[0]:
                st.badge(STATUS_LABELS.get(f.status, f.status), color=STATUS_COLORS.get(f.status, "gray"))
            with badges[1]:
                st.badge(f"Severidad {SEVERITY_LABELS.get(f.severity, f.severity).lower()}", color=SEVERITY_COLORS.get(f.severity, "gray"))
            with badges[2]:
                st.badge("Regla automática" if f.origin == "rule" else "Modelo", color="gray")
            st.write(f.reason)

            for e in f.evidence:
                lines = f"{e.start_line}" if e.start_line == e.end_line else f"{e.start_line}-{e.end_line}"
                note = " (cita no verificada)" if e.verified is False else ""
                st.caption(f"`{e.path}:{lines}`{note}")
                ext = "." + e.path.rsplit(".", 1)[-1] if "." in e.path else ""
                st.code(e.quote, language=LANGUAGES.get(ext))
            if f.limitations:
                st.caption(f"Limitaciones: {f.limitations}")
            for note in f.validation_notes:
                st.caption(f"Validación: {note}")

            if f.suggested_edit or f.type == "skill_overlap":
                where = f" para `{f.edit_path}`" if f.edit_path else ""
                st.text_area(f"Propuesta{where} (puedes editarla)", value=f.suggested_edit, key=f"edit_{run_n}_{f.id}", height=100)

            ok, why = can_handoff(f)
            if ok:
                task = task_for_finding(f, edited_suggestion=st.session_state.get(f"edit_{run_n}_{f.id}", f.suggested_edit))
                copy_button(task, "Copiar tarea de corrección")
                with st.expander("Ver la tarea"):
                    st.code(task, language=None)
            else:
                st.info(why)

with st.expander(f"Archivos examinados ({len(result.files_examined)}) y omitidos ({len(result.files_skipped)})"):
    st.markdown("**Examinados**")
    st.markdown("\n".join(f"- `{p}`" for p in result.files_examined) or "Ninguno.")
    if result.files_skipped:
        st.markdown("**Omitidos**")
        st.markdown("\n".join(f"- `{s['path']}`: {s['reason']}" for s in result.files_skipped))
