"""Análisis por consola, útil para probar sin la interfaz.

Ejemplos:
    python -m src.cli examples/stale_project --provider api
    python -m src.cli proyecto.zip --provider local --iteration V1
    python -m src.cli examples/stale_project --no-llm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.analyze import FINAL_ITERATION, ITERATIONS, analyze_iteration
from src.handoff import task_for_finding, to_json, to_markdown
from src.ingest import IngestError, load_dir, load_zip


def main() -> int:
    ap = argparse.ArgumentParser(description="SkillDoc Check por consola")
    ap.add_argument("path", help="Carpeta del proyecto o archivo .zip")
    ap.add_argument("--provider", default="api", choices=["api", "local"])
    ap.add_argument("--iteration", default=FINAL_ITERATION, choices=list(ITERATIONS))
    ap.add_argument("--context", default="selected", choices=["selected", "raw"])
    ap.add_argument("--no-llm", action="store_true", help="Solo reglas deterministas, sin llamar al modelo")
    ap.add_argument("--json", action="store_true", help="Imprimir el resultado en JSON")
    ap.add_argument("--tasks", action="store_true", help="Imprimir la tarea copiable de cada hallazgo")
    args = ap.parse_args()

    p = Path(args.path)
    try:
        repo = load_zip(p.read_bytes()) if p.suffix == ".zip" else load_dir(p)
    except IngestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    result = analyze_iteration(repo, args.iteration, provider=args.provider, context_mode=args.context, use_llm=not args.no_llm)
    print(to_json(result) if args.json else to_markdown(result))
    if args.tasks:
        for f in result.findings:
            print(f"\n{'=' * 20} Tarea {f.id} {'=' * 20}\n{task_for_finding(f)}")
    return 0 if not result.error else 2


if __name__ == "__main__":
    raise SystemExit(main())
