"""Validación de lo que responde el modelo, igual para API y local.

Un LLM puede devolver JSON con el formato correcto y aun así inventar archivos,
líneas o citas. Aquí se comprueba cada evidencia contra los archivos reales:

- La ruta existe entre los archivos examinados.
- La cita aparece en las líneas indicadas (si aparece en otra parte del mismo
  archivo, se corrigen las líneas y se deja nota).
- El tipo de hallazgo tiene la evidencia que necesita (por ejemplo, un traslape
  necesita citas de dos skills distintas).

Lo que no se puede sostener se degrada a "insufficient_evidence" o se descarta.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from src.ingest import Repo
from src.schemas import FINDING_TYPES, SEVERITIES, STATUSES, Evidence, Finding

DOC_KINDS = {"readme", "doc"}
SKILL_KINDS = {"skill", "skill_ref"}
LINE_PREFIX_RE = re.compile(r"^\s*\d+\|\s?", re.MULTILINE)


@dataclass
class ValidationStats:
    findings_in: int = 0
    findings_out: int = 0
    dropped: int = 0
    downgraded: int = 0
    evidence_total: int = 0
    evidence_verified: int = 0
    evidence_corrected: int = 0
    dropped_reasons: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    text = LINE_PREFIX_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip().strip("`").strip()


def _resolve_path(path: str, repo: Repo) -> str | None:
    path = path.strip().removeprefix("./").lstrip("/")
    if path in repo.files:
        return path
    matches = [p for p in repo.files if p.endswith("/" + path) or path.endswith("/" + p)]
    return matches[0] if len(matches) == 1 else None


def _locate(quote: str, lines: list[str], start: int, end: int) -> tuple[int, int, str] | None:
    """Busca la cita en el archivo. Devuelve (inicio, fin, modo) o None."""
    q = _norm(quote)
    if not q:
        return None
    n = len(lines)
    start = max(1, min(start, n))
    end = max(start, min(end, n))

    window = _norm("\n".join(lines[start - 1 : end]))
    if q in window:
        return start, end, "exact"

    # Buscar en todo el archivo con ventanas de hasta 8 líneas.
    span = max(1, min(8, q.count(" ") // 4 + 1))
    for size in range(1, span + 4):
        for i in range(0, n - size + 1):
            if q in _norm("\n".join(lines[i : i + size])):
                return i + 1, i + size, "moved"

    # Cita casi igual (el modelo cambió comillas o espacios).
    ratio = difflib.SequenceMatcher(None, q, window).ratio() if window else 0
    if ratio >= 0.85:
        return start, end, "approx"
    return None


def _check_evidence(ev: Evidence, repo: Repo, notes: list[str], stats: ValidationStats) -> Evidence | None:
    stats.evidence_total += 1
    path = _resolve_path(ev.path, repo)
    if path is None:
        notes.append(f"Se descartó una cita de {ev.path}: ese archivo no está entre los examinados.")
        return None
    if path != ev.path:
        notes.append(f"Ruta corregida de {ev.path} a {path}.")
    lines = repo.files[path].lines
    found = _locate(ev.quote, lines, ev.start_line, ev.end_line or ev.start_line)
    if found is None:
        notes.append(f"La cita de {path}:{ev.start_line} no se encontró en el archivo.")
        return Evidence(path, ev.start_line, ev.end_line, ev.quote, verified=False)
    start, end, mode = found
    if mode == "moved":
        stats.evidence_corrected += 1
        notes.append(f"Líneas corregidas en {path}: {ev.start_line}-{ev.end_line} → {start}-{end}.")
    elif mode == "approx":
        notes.append(f"La cita de {path}:{start} coincide de forma aproximada.")
    stats.evidence_verified += 1
    return Evidence(path, start, end, ev.quote, verified=True)


def _requirements_met(f: Finding, repo: Repo) -> tuple[bool, str]:
    ok = [e for e in f.evidence if e.verified]
    kinds = [repo.files[e.path].kind for e in ok]
    if f.type == "readme_code":
        if not any(k in DOC_KINDS for k in kinds):
            return False, "Falta una cita verificada del README o documentación."
        if not any(k not in DOC_KINDS | SKILL_KINDS for k in kinds):
            return False, "Falta una cita verificada del código o configuración que lo contradiga."
    elif f.type == "skill_project":
        if not any(k in SKILL_KINDS for k in kinds):
            return False, "Falta una cita verificada de la skill."
    elif f.type == "skill_overlap":
        skills = {e.path for e in ok if repo.files[e.path].kind == "skill"}
        if len(skills) < 2:
            return False, "Un traslape necesita citas de dos skills distintas."
    elif f.type == "redundancy":
        if len({(e.path, e.start_line) for e in ok}) < 2:
            return False, "Una redundancia necesita al menos dos lugares citados."
    return True, ""


def validate_findings(findings: list[Finding], repo: Repo) -> tuple[list[Finding], ValidationStats]:
    stats = ValidationStats(findings_in=len(findings))
    kept: list[Finding] = []
    for f in findings:
        notes = list(f.validation_notes)
        if f.type not in FINDING_TYPES:
            stats.dropped += 1
            stats.dropped_reasons.append(f"tipo desconocido: {f.type}")
            continue
        if f.status not in STATUSES:
            notes.append(f"Estado desconocido ({f.status}); se trató como posible conflicto.")
            f.status = "possible_conflict"
        if f.severity not in SEVERITIES:
            f.severity = "medium"

        checked = [_check_evidence(e, repo, notes, stats) for e in f.evidence]
        f.evidence = [e for e in checked if e is not None]
        if not f.evidence:
            stats.dropped += 1
            stats.dropped_reasons.append(f"sin evidencia en archivos examinados: {f.summary[:80]}")
            continue

        original = f.status
        if not any(e.verified for e in f.evidence):
            f.status = "insufficient_evidence"
            notes.append("Ninguna cita se pudo verificar en los archivos.")
        else:
            met, why = _requirements_met(f, repo)
            if not met and f.status == "confirmed":
                f.status = "possible_conflict"
                notes.append(why)
            elif not met:
                notes.append(why)
        # Un traslape entre descripciones nunca está comprobado sin observar al agente.
        if f.type == "skill_overlap" and f.status == "confirmed":
            f.status = "possible_conflict"
        if f.status != original:
            stats.downgraded += 1

        if f.edit_path:
            resolved = _resolve_path(f.edit_path, repo)
            if resolved is None:
                notes.append(f"El archivo a editar ({f.edit_path}) no existe; se usará el de la primera cita.")
                f.edit_path = f.evidence[0].path
            else:
                f.edit_path = resolved
        else:
            f.edit_path = f.evidence[0].path

        f.validation_notes = notes
        kept.append(f)
    stats.findings_out = len(kept)
    return kept, stats
