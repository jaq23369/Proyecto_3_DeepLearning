"""Genera los casos de evaluación a partir de repos base y modificaciones controladas.

Cada persona define sus casos en eval/case_defs_<autor>.py (lista CASES). Este
script copia el repo base de cada caso, aplica las modificaciones, calcula los
números de línea de las etiquetas buscando el texto citado y escribe:

- eval/cases/<id>/            archivos del caso
- eval/cases.jsonl            una línea por caso (se reescriben solo los casos
                              definidos en case_defs_*.py; las líneas escritas
                              a mano se conservan)

Con --check corre solo las reglas deterministas (sin LLM y sin costo) y
muestra qué etiquetas detectan y si las reglas dan alertas que no están en las
etiquetas. Sirve para revisar las etiquetas antes de correr los modelos.

    python -m eval.build_cases
    python -m eval.build_cases --check
"""

from __future__ import annotations

import argparse
import filecmp
import importlib
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
CASES_DIR = EVAL / "cases"
CASES_FILE = EVAL / "cases.jsonl"
LINE_TOLERANCE = 2


class CaseError(Exception):
    pass


def _apply(case_dir: Path, op: tuple) -> None:
    kind = op[0]
    if kind in ("replace", "replace_all"):
        _, rel, old, new = op
        p = case_dir / rel
        text = p.read_text(encoding="utf-8")
        if old not in text:
            raise CaseError(f"'{old[:50]}' no está en {rel}")
        if kind == "replace" and text.count(old) > 1:
            raise CaseError(f"'{old[:50]}' aparece varias veces en {rel}; usar replace_all o un texto más largo")
        p.write_text(text.replace(old, new), encoding="utf-8")
    elif kind == "rename":
        _, old, new = op
        (case_dir / new).parent.mkdir(parents=True, exist_ok=True)
        (case_dir / old).rename(case_dir / new)
    elif kind == "delete":
        (case_dir / op[1]).unlink()
    elif kind == "write":
        _, rel, content = op
        (case_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (case_dir / rel).write_text(content, encoding="utf-8")
    else:
        raise CaseError(f"Operación desconocida: {kind}")


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store")


def _sync(src: Path, dst: Path) -> None:
    """Deja dst igual a src tocando solo los archivos que cambian."""
    dst.mkdir(parents=True, exist_ok=True)
    wanted = set(_files(src))
    for rel in _files(dst):
        if rel not in wanted:
            (dst / rel).unlink()
    for rel in wanted:
        target = dst / rel
        if not target.exists() or not filecmp.cmp(src / rel, target, shallow=False):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, target)
    for d in sorted((p for p in dst.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()


def _locate(case_dir: Path, rel: str, needle: str) -> list[int]:
    """Línea (o líneas, si el texto ocupa varias) donde aparece needle."""
    p = case_dir / rel
    if not p.exists():
        raise CaseError(f"La etiqueta cita {rel}, que no existe en el caso")
    lines = p.read_text(encoding="utf-8").split("\n")
    first = needle.split("\n")[0]
    hits = [i for i, line in enumerate(lines, start=1) if first in line]
    if not hits:
        raise CaseError(f"No se encontró '{first[:60]}' en {rel}")
    if len(hits) > 1:
        raise CaseError(f"'{first[:60]}' aparece en varias líneas de {rel} ({hits}); usar un texto único")
    start = hits[0]
    return [start, start + needle.count("\n")]


def build_case(defn: dict, author: str) -> dict:
    cid = defn["id"]
    if "repo" in defn:  # caso que usa una carpeta existente tal cual
        case_dir = ROOT / defn["repo"]
        repo_rel = defn["repo"]
    else:
        case_dir = CASES_DIR / cid
        # Se arma fuera del proyecto y luego se sincroniza archivo por archivo.
        # Borrar y recrear carpetas enteras hace que iCloud cree copias de
        # conflicto ("models 2.py") que contaminan los casos.
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp) / cid
            shutil.copytree(EVAL / "repos" / defn["base"], staging)
            for op in defn.get("mutations", []):
                _apply(staging, op)
            _sync(staging, case_dir)
        repo_rel = case_dir.relative_to(ROOT).as_posix()

    expected = []
    for exp in defn.get("expected", []):
        evidence = {rel: _locate(case_dir, rel, needle) for rel, needle in exp["evidence"]}
        item = {"type": exp["type"], "evidence": evidence, "note": exp.get("note", "")}
        if exp.get("optional"):
            item["optional"] = True
        expected.append(item)

    return {
        "id": cid,
        "split": defn["split"],
        "family": defn["family"],
        "repo": repo_rel,
        "category": defn["category"],
        "author": author,
        "reviewed_by": defn.get("reviewed_by", ""),
        "description": defn["description"],
        "expected": expected,
        # Lista exacta de archivos; run_eval se niega a correr si aparecen otros.
        "files": _files(case_dir),
    }


def load_definitions() -> list[tuple[str, dict]]:
    defs = []
    for path in sorted(EVAL.glob("case_defs_*.py")):
        author = path.stem.removeprefix("case_defs_")
        module = importlib.import_module(f"eval.{path.stem}")
        defs += [(author, d) for d in module.CASES]
    return defs


def write_cases(built: list[dict]) -> None:
    generated = {c["id"] for c in built}
    manual = []
    if CASES_FILE.exists():
        for line in CASES_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("//"):
                case = json.loads(line)
                if case["id"] not in generated:
                    manual.append(case)
    ordered = manual + built
    CASES_FILE.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in ordered) + "\n", encoding="utf-8")


def _matches(finding, exp: dict) -> bool:
    if finding.type != exp["type"]:
        return False
    for e in finding.evidence:
        span = exp["evidence"].get(e.path)
        if span and e.start_line <= span[1] + LINE_TOLERANCE and span[0] - LINE_TOLERANCE <= e.end_line:
            return True
    return False


def check(cases: list[dict]) -> None:
    """Revisión de etiquetas solo con reglas (sin LLM)."""
    from src.analyze import analyze_iteration
    from src.ingest import load_dir

    for case in cases:
        result = analyze_iteration(load_dir(ROOT / case["repo"]), "V2", use_llm=False)
        found = [f for f in result.findings if f.status != "insufficient_evidence"]
        caught, unmatched = [], list(found)
        for exp in case["expected"]:
            hit = next((f for f in unmatched if _matches(f, exp)), None)
            if hit:
                unmatched.remove(hit)
                caught.append(exp["type"])
        n_req = sum(1 for e in case["expected"] if not e.get("optional"))
        print(f"{case['id']:6} {case['split']:4} {case['category']:14} etiquetas {n_req} | reglas detectan {len(caught)}"
              + (f" | ALERTAS DE REGLAS SIN ETIQUETA: {[(f.type, f.summary[:60]) for f in unmatched]}" if unmatched else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera los casos de evaluación")
    ap.add_argument("--check", action="store_true", help="Revisar etiquetas con las reglas (sin LLM)")
    args = ap.parse_args()

    built = []
    for author, defn in load_definitions():
        try:
            built.append(build_case(defn, author))
        except CaseError as exc:
            raise SystemExit(f"Caso {defn['id']}: {exc}")
    write_cases(built)
    by_split = {s: sum(1 for c in built if c["split"] == s) for s in ("dev", "test")}
    print(f"{len(built)} casos generados ({by_split['dev']} dev, {by_split['test']} test) en {CASES_FILE.relative_to(ROOT)}")
    if args.check:
        check(built)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
