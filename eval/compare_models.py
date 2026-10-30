"""Compara corridas lado a lado (por ejemplo API y local) sobre los mismos casos.

    python -m eval.compare_models --runs api=<corrida> local=<corrida>
    python -m eval.compare_models --runs api=<a> local_v4=<b> local_v3=<c> --out eval/results/test_final
    python -m eval.compare_models --auto --split dev --iteration V4

Cada corrida se puntúa con eval.score. La comparación es pareada: solo cuentan
los casos que están en todas las corridas, y se avisa si alguna tiene menos.
Escribe una tabla (.md y .csv) y una gráfica (.png) para la presentación.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from eval.score import RUNS_DIR, load_run, resolve_run, score_run

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "eval" / "results" / "model_comparison"

# Ranuras categóricas 1 y 2 de la paleta de referencia (azul y naranja).
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"

ROWS = [
    ("Macro-F1", lambda s: s["macro_f1"], "{:.2f}"),
    ("Precisión", lambda s: s["micro"]["precision"], "{:.2f}"),
    ("Recall", lambda s: s["micro"]["recall"], "{:.2f}"),
    ("F1 (micro)", lambda s: s["micro"]["f1"], "{:.2f}"),
    ("F1 README vs código", lambda s: s["by_type"].get("readme_code", {}).get("f1"), "{:.2f}"),
    ("F1 skill desactualizada", lambda s: s["by_type"].get("skill_project", {}).get("f1"), "{:.2f}"),
    ("F1 traslape", lambda s: s["by_type"].get("skill_overlap", {}).get("f1"), "{:.2f}"),
    ("F1 redundancia", lambda s: s["by_type"].get("redundancy", {}).get("f1"), "{:.2f}"),
    ("Casos limpios con alerta (%)", lambda s: s["clean_alert_pct"], "{:.0f}"),
    ("Fidelidad de citas", lambda s: s["citation_fidelity"], "{:.2f}"),
    ("Respuestas válidas (%)", lambda s: s["valid_response_pct"], "{:.0f}"),
    ("Evidencia insuficiente (total)", lambda s: s["insufficient_evidence"], "{}"),
    ("Latencia media (s)", lambda s: s["latency_mean_s"], "{:.1f}"),
    ("Latencia mediana (s)", lambda s: s["latency_median_s"], "{:.1f}"),
    ("Latencia p95 (s)", lambda s: s["latency_p95_s"], "{:.1f}"),
    ("Tokens de entrada por caso", lambda s: s["input_tokens_mean"], "{}"),
    ("Tokens de salida por caso", lambda s: s["output_tokens_mean"], "{}"),
    ("Costo total (USD)", lambda s: s["cost_total_usd"], "{:.4f}"),
    ("Costo por caso (USD)", lambda s: s["cost_per_case_usd"], "{:.5f}"),
]


def auto_runs(split: str, iteration: str) -> dict[str, str]:
    """La corrida más reciente de api y de local con esa partición e iteración."""
    found: dict[str, str] = {}
    for d in sorted(RUNS_DIR.iterdir() if RUNS_DIR.exists() else []):
        if not (d / "meta.json").exists() or d.name.startswith("_"):
            continue
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if meta.get("split") == split and meta.get("iteration") == iteration:
            found[meta["provider"]["provider"]] = d.name  # sorted: gana la más reciente
    return found


def fmt(value, f: str) -> str:
    return "n/a" if value is None else f.format(value)


def table_rows(labels: list[str], scores: list[dict]) -> list[list[str]]:
    rows = [[name] + [fmt(get(s), f) for s in scores] for name, get, f in ROWS]
    rows.insert(0, ["Modelo"] + [f"{s['model']}" for s in scores])
    rows.insert(1, ["Razonamiento previo"] + [str(s["thinking"] or "n/a") for s in scores])
    rows.insert(2, ["Casos"] + [str(s["n_cases"]) for s in scores])
    res = [s["resources"] for s in scores]
    if any(res):
        rows.append(["Memoria cargada (GB) / % en GPU"] + [
            f"{r['loaded_gb']:.1f} / {100 * r['gpu_share']:.0f} %" if r.get("loaded_gb") else "n/a" for r in res
        ])
    return rows


def markdown(labels: list[str], rows: list[list[str]], extra: list[str]) -> str:
    out = ["| Métrica | " + " | ".join(labels) + " |", "| --- | " + " | ".join(["---:"] * len(labels)) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out + [""] + extra) + "\n"


def per_case_differences(labels: list[str], scores: list[dict]) -> list[str]:
    """Casos donde las corridas no aciertan igual (FP + FN distintos)."""
    by_case = [{c["case_id"]: c for c in s["per_case"]} for s in scores]
    lines = []
    for cid in by_case[0]:
        vals = [(b[cid]["tp"], b[cid]["fp"], b[cid]["fn"]) for b in by_case]
        if len(set(vals)) > 1:
            lines.append(f"- {cid}: " + "; ".join(f"{l} TP {v[0]} FP {v[1]} FN {v[2]}" for l, v in zip(labels, vals)))
    return lines


def chart(labels: list[str], scores: list[dict], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(scores)
    metrics = [
        ("Macro-F1", lambda s: s["macro_f1"]),
        ("README vs\ncódigo", lambda s: s["by_type"].get("readme_code", {}).get("f1", 0)),
        ("Skill desact.", lambda s: s["by_type"].get("skill_project", {}).get("f1", 0)),
        ("Traslape", lambda s: s["by_type"].get("skill_overlap", {}).get("f1", 0)),
        ("Redundancia", lambda s: s["by_type"].get("redundancy", {}).get("f1", 0)),
    ]
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": GRID, "text.color": INK})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [3, 1]}, facecolor=SURFACE)
    width = 0.8 / n
    for i, (label, s) in enumerate(zip(labels, scores)):
        xs = [j + (i - (n - 1) / 2) * width for j in range(len(metrics))]
        vals = [get(s) for _, get in metrics]
        bars = ax1.bar(xs, vals, width * 0.9, color=COLORS[i], label=label, edgecolor=SURFACE, linewidth=1.5)
        for b, v in zip(bars, vals):
            ax1.text(b.get_x() + b.get_width() / 2, v + 0.015, f"{v:.2f}", ha="center", va="bottom", fontsize=8, color=MUTED)
    ax1.set_xticks(range(len(metrics)), [m for m, _ in metrics], fontsize=9, color=MUTED)
    ax1.set_ylim(0, 1.12)
    ax1.set_title("Calidad (F1) sobre los mismos casos", loc="left", fontsize=11, color=INK)
    ax1.legend(frameon=False, fontsize=9, loc="lower right", bbox_to_anchor=(1, 1.0), ncol=n)

    lat = [s["latency_mean_s"] for s in scores]
    bars = ax2.bar(range(n), lat, 0.6, color=COLORS[:n], edgecolor=SURFACE)
    for b, v, s in zip(bars, lat, scores):
        cost = f"{s['cost_per_case_usd']:.4f} USD" if s["cost_total_usd"] else "sin factura"
        ax2.text(b.get_x() + b.get_width() / 2, v * 1.02, f"{v:.1f} s\n{cost}", ha="center", va="bottom", fontsize=8, color=MUTED)
    ax2.set_xticks(range(n), labels, fontsize=8, color=MUTED)
    ax2.set_ylim(0, max(lat) * 1.3 if lat else 1)
    ax2.set_title("Latencia media por caso", loc="left", fontsize=11, color=INK)
    for ax in (ax1, ax2):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.tick_params(axis="y", colors=MUTED, labelsize=8, length=0)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Compara corridas lado a lado")
    ap.add_argument("--runs", nargs="*", default=[], help="etiqueta=corrida (carpeta o run_id)")
    ap.add_argument("--auto", action="store_true", help="Usar la última corrida api y local de --split/--iteration")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--iteration", default="V4")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Prefijo de los archivos de salida")
    args = ap.parse_args()

    runs = dict(r.split("=", 1) for r in args.runs)
    if args.auto:
        runs = {k: v for k, v in auto_runs(args.split, args.iteration).items()}
    if len(runs) < 2:
        raise SystemExit("Hacen falta al menos dos corridas (--runs api=<corrida> local=<corrida>).")

    labels = list(runs)
    dirs = [resolve_run(v) for v in runs.values()]
    sets = [{c["id"] for c, _ in load_run(d)[1]} for d in dirs]
    common = set.intersection(*sets)
    notes = []
    for label, ids in zip(labels, sets):
        if ids != common:
            notes.append(f"Aviso: {label} tiene {len(ids)} casos y solo {len(common)} están en todas; se comparan esos.")
    scores = [score_run(d, only_cases=common) for d in dirs]

    rows = table_rows(labels, scores)
    diffs = per_case_differences(labels, scores)
    extra = notes + [f"Corridas: " + ", ".join(f"{l} = `{s['run_id']}`" for l, s in zip(labels, scores))]
    if diffs:
        extra += ["", "Casos donde no coinciden:"] + diffs
    md = markdown(labels, rows, extra)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text(md, encoding="utf-8")
    with out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metrica"] + labels)
        w.writerows(rows)
    chart(labels, scores, out.with_suffix(".png"))
    print(md)
    print(f"Guardado en {out.with_suffix('.md').name}, .csv y .png (carpeta {out.parent})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
