"""Corre el conjunto de evaluación con un proveedor y una iteración.

Guarda la salida completa de cada caso y agrega una fila por caso a
eval/results/runs.csv (tokens, costo, latencia, hash del contexto, etc.).
La puntuación contra las etiquetas la hace eval/score.py.

Ejemplos:
    python -m eval.run_eval --provider api --iteration V0 --split dev
    python -m eval.run_eval --provider local --iteration V2 --split test
    python -m eval.run_eval --provider api --iteration V2 --split dev --limit 3
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from src.analyze import ITERATIONS, analyze_iteration
from src.ingest import IngestError, load_dir
from src.model_provider import get_provider

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "eval" / "cases.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
RUNS_CSV = RESULTS_DIR / "runs.csv"

CSV_FIELDS = [
    "run_id", "timestamp", "case_id", "split", "category", "provider", "model", "iteration",
    "prompt_version", "context_mode", "context_hash", "context_tokens_est", "n_findings",
    "n_rule", "n_llm", "input_tokens", "output_tokens", "cost_usd", "latency_s", "retries", "error",
]


def load_cases(path: Path = CASES_FILE, split: str = "all") -> list[dict]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            case = json.loads(line)
            if split == "all" or case.get("split") == split:
                cases.append(case)
    return cases


def check_files(case: dict) -> None:
    """Confirma que la carpeta del caso tiene exactamente los archivos esperados."""
    if "files" not in case:
        return
    root = ROOT / case["repo"]
    actual = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store")
    extra = sorted(set(actual) - set(case["files"]))
    missing = sorted(set(case["files"]) - set(actual))
    if extra or missing:
        raise SystemExit(
            f"El caso {case['id']} no coincide con su lista de archivos. Extra: {extra[:5]} Faltan: {missing[:5]}. "
            "Si son copias de iCloud (por ejemplo 'models 2.py'), correr python -m eval.build_cases y repetir."
        )


def append_rows(rows: list[dict], path: Path = RUNS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)


def run(
    provider_name: str,
    iteration: str,
    split: str = "dev",
    context_mode: str = "selected",
    limit: int | None = None,
    case_ids: list[str] | None = None,
    max_cost: float = 1.0,
    tag: str = "",
) -> tuple[str, list[dict]]:
    cases = load_cases(split=split)
    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]
    if limit:
        cases = cases[:limit]
    if not cases:
        raise SystemExit("No hay casos para correr con esos filtros.")

    for case in cases:
        check_files(case)

    provider = get_provider(provider_name)
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}_{provider_name}_{iteration}_{context_mode}" + (f"_{tag}" if tag else "")
    out_dir = RESULTS_DIR / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(
        json.dumps(
            {"run_id": run_id, "provider": provider.describe(), "iteration": iteration, "options": ITERATIONS[iteration],
             "split": split, "context_mode": context_mode, "cases": [c["id"] for c in cases]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    rows: list[dict] = []
    spent = 0.0
    print(f"Corrida {run_id}: {len(cases)} casos")
    for i, case in enumerate(cases, start=1):
        if spent >= max_cost:
            print(f"Se alcanzó el tope de gasto ({max_cost} USD). Se detiene la corrida.")
            break
        try:
            repo = load_dir(ROOT / case["repo"])
        except IngestError as exc:
            print(f"  [{case['id']}] error al cargar: {exc}")
            continue
        t0 = time.perf_counter()
        result = analyze_iteration(repo, iteration, provider=provider, context_mode=context_mode)
        (out_dir / f"{case['id']}.json").write_text(
            json.dumps({"case": case, "result": result.to_dict()}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        u = result.usage
        spent += u.cost_usd
        rows.append({
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "case_id": case["id"],
            "split": case.get("split", ""),
            "category": case.get("category", ""),
            "provider": result.provider,
            "model": result.model,
            "iteration": iteration,
            "prompt_version": result.prompt_version,
            "context_mode": context_mode,
            "context_hash": result.context_hash,
            "context_tokens_est": result.context_tokens_est,
            "n_findings": len(result.findings),
            "n_rule": sum(f.origin == "rule" for f in result.findings),
            "n_llm": sum(f.origin == "llm" for f in result.findings),
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cost_usd": u.cost_usd,
            "latency_s": u.latency_s,
            "retries": u.retries,
            "error": result.error,
        })
        status = f"ERROR: {result.error}" if result.error else f"{len(result.findings)} hallazgos"
        print(f"  [{i}/{len(cases)}] {case['id']}: {status} | {u.input_tokens}+{u.output_tokens} tok | "
              f"{u.latency_s:.1f}s modelo, {time.perf_counter() - t0:.1f}s total | {u.cost_usd:.5f} USD")

    append_rows(rows)
    if rows:
        n = len(rows)
        lat = sorted(r["latency_s"] for r in rows)
        print(
            f"\nResumen: {n} casos | costo total {spent:.5f} USD ({spent / n:.5f} por caso) | "
            f"latencia media {sum(lat) / n:.2f}s, mediana {lat[n // 2]:.2f}s | "
            f"tokens medios {sum(r['input_tokens'] for r in rows) / n:.0f} entrada, "
            f"{sum(r['output_tokens'] for r in rows) / n:.0f} salida | "
            f"errores {sum(1 for r in rows if r['error'])}"
        )
        print(f"Salidas en {out_dir.relative_to(ROOT)}")
    return run_id, rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Corre el conjunto de evaluación")
    ap.add_argument("--provider", default="api", choices=["api", "local"])
    ap.add_argument("--iteration", default="V2", choices=list(ITERATIONS))
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--context", default="selected", choices=["selected", "raw"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--cases", nargs="*", help="IDs de casos específicos")
    ap.add_argument("--max-cost", type=float, default=1.0, help="Tope de gasto en USD para la corrida")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    run(args.provider, args.iteration, args.split, args.context, args.limit, args.cases, args.max_cost, args.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
