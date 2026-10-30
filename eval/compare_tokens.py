"""Experimento T1: archivos completos (raw) contra fragmentos seleccionados.

Mismo modelo, mismo prompt, misma iteración y mismos casos; solo cambia cómo
se arma el contexto. Mide cuántos tokens de entrada se ahorran y si se pierden
hallazgos. La cifra describe el análisis de SkillDoc Check, no el consumo
posterior de Codex o Claude Code.

    python -m eval.compare_tokens --cases t01 t02 t03 --iteration V2
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from eval.run_eval import RESULTS_DIR, run

OUT_CSV = RESULTS_DIR / "tokens_comparison.csv"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compara contexto completo contra seleccionado")
    ap.add_argument("--cases", nargs="+", required=True, help="Submuestra predefinida de casos")
    ap.add_argument("--iteration", default="V2")
    ap.add_argument("--provider", default="api", choices=["api", "local"])
    ap.add_argument("--max-cost", type=float, default=1.0)
    args = ap.parse_args()

    raw_id, raw_rows = run(args.provider, args.iteration, "all", "raw", case_ids=args.cases, max_cost=args.max_cost, tag="T1")
    sel_id, sel_rows = run(args.provider, args.iteration, "all", "selected", case_ids=args.cases, max_cost=args.max_cost, tag="T1")
    sel = {r["case_id"]: r for r in sel_rows}

    rows = []
    for r in raw_rows:
        s = sel.get(r["case_id"])
        if not s:
            continue
        saved = r["input_tokens"] - s["input_tokens"]
        rows.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "case_id": r["case_id"],
            "model": r["model"],
            "raw_input_tokens": r["input_tokens"],
            "selected_input_tokens": s["input_tokens"],
            "input_saving_pct": round(100 * saved / r["input_tokens"], 1) if r["input_tokens"] else 0,
            "raw_output_tokens": r["output_tokens"],
            "selected_output_tokens": s["output_tokens"],
            "raw_cost_usd": r["cost_usd"],
            "selected_cost_usd": s["cost_usd"],
            "raw_findings": r["n_findings"],
            "selected_findings": s["n_findings"],
            "raw_run": raw_id,
            "selected_run": sel_id,
        })

    if not rows:
        print("No hubo casos comparables.")
        return 1
    new = not OUT_CSV.exists()
    with OUT_CSV.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        if new:
            w.writeheader()
        w.writerows(rows)

    tr = sum(r["raw_input_tokens"] for r in rows)
    ts = sum(r["selected_input_tokens"] for r in rows)
    cr = sum(r["raw_cost_usd"] for r in rows)
    cs = sum(r["selected_cost_usd"] for r in rows)
    print(f"\nT1 sobre {len(rows)} casos")
    print(f"Tokens de entrada: {tr} completos vs {ts} seleccionados → ahorro {100 * (tr - ts) / tr:.1f} %")
    print(f"Costo total (entrada + salida): {cr:.5f} vs {cs:.5f} USD")
    print("Para ver si se perdieron hallazgos, puntuar las dos corridas con eval/score.py:")
    print(f"  {raw_id}\n  {sel_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
