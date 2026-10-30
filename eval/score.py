"""Puntúa una corrida de eval/run_eval.py contra las etiquetas de los casos.

Usa la regla para emparejar fijada antes de correr los modelos (ver README):

1. Solo cuentan como predicción los hallazgos confirmed y possible_conflict.
   Los insufficient_evidence se reportan aparte.
2. Un hallazgo empareja con una etiqueta si tiene el mismo tipo y una evidencia
   en un archivo de la etiqueta con líneas que se cruzan (tolerancia de 2).
   La comparación es eval.build_cases._matches.
3. Emparejamiento uno a uno. Se calcula el máximo emparejamiento posible, así
   el resultado no depende del orden en que el modelo escribió los hallazgos.
4. Predicho sin pareja es falso positivo; etiqueta sin pareja, falso negativo.
5. skill_format no se puntúa salvo que el caso lo espere. Una etiqueta opcional
   no cuenta como falso negativo si falta ni como falso positivo si aparece.
6. Métricas: precisión, recall y F1 por tipo, macro-F1, porcentaje de casos
   limpios con alguna alerta y fidelidad de citas.

Macro-F1: promedio del F1 de los tipos que aparecen en las etiquetas o en las
predicciones de la corrida (un tipo que ni se espera ni se predice no tiene F1).

Fidelidad de citas: evidencias con la cita presente en el archivo, entre todas
las que escribió el modelo. En las iteraciones con validación se toma de la
propia validación; en V0 y V1 (sin validación) se comprueba aquí contra los
archivos del caso.

    python -m eval.score eval/results/runs/<corrida>
    python -m eval.score <run_id>
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import statistics
import sys
from pathlib import Path

from eval.build_cases import _matches
from src.ingest import load_dir
from src.schemas import AnalysisResult
from src.validate_output import validate_findings

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "eval" / "results"
RUNS_DIR = RESULTS_DIR / "runs"
SCORES_CSV = RESULTS_DIR / "scores.csv"

TYPES = ["readme_code", "skill_project", "skill_overlap", "redundancy", "skill_format"]
COUNTED_STATUSES = ("confirmed", "possible_conflict")


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn}


def _max_matching(preds: list, labels: list) -> dict[int, int]:
    """Emparejamiento uno a uno de tamaño máximo (caminos aumentantes). {índice de etiqueta: índice de predicción}."""
    edges = {j: [i for i, f in enumerate(preds) if _matches(f, lab)] for j, lab in enumerate(labels)}
    owner: dict[int, int] = {}  # predicción → etiqueta

    def try_label(j: int, seen: set[int]) -> bool:
        for i in edges[j]:
            if i in seen:
                continue
            seen.add(i)
            if i not in owner or try_label(owner[i], seen):
                owner[i] = j
                return True
        return False

    for j in edges:
        try_label(j, set())
    return {j: i for i, j in owner.items()}


def match_case(findings: list, expected: list[dict]) -> dict:
    """Empareja los hallazgos de un caso con sus etiquetas."""
    expects_format = any(e["type"] == "skill_format" for e in expected)
    preds = [f for f in findings if f.status in COUNTED_STATUSES and (f.type != "skill_format" or expects_format)]
    required = [e for e in expected if not e.get("optional")]
    optional = [e for e in expected if e.get("optional")]

    pairs = _max_matching(preds, required)  # etiqueta → predicción
    used = set(pairs.values())
    left = [f for i, f in enumerate(preds) if i not in used]
    opt_pairs = _max_matching(left, optional)
    ignored = {id(left[i]) for i in opt_pairs.values()}

    tp = [(required[j], preds[i]) for j, i in pairs.items()]
    fn = [e for j, e in enumerate(required) if j not in pairs]
    fp = [f for i, f in enumerate(preds) if i not in used and id(f) not in ignored]
    return {"tp": tp, "fp": fp, "fn": fn, "ignored_optional": len(ignored), "n_pred": len(preds)}


def _citation_stats(result: AnalysisResult, case: dict) -> tuple[int, int]:
    """(citas verificadas, citas escritas por el modelo) de un caso."""
    v = result.settings.get("validation")
    if v:
        return int(v.get("evidence_verified", 0)), int(v.get("evidence_total", 0))
    llm = [copy.deepcopy(f) for f in result.findings if f.origin == "llm"]
    if not llm:
        return 0, 0
    _, stats = validate_findings(llm, load_dir(ROOT / case["repo"]))
    return stats.evidence_verified, stats.evidence_total


def _pctl(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)


def resolve_run(name: str) -> Path:
    p = Path(name)
    if p.is_dir():
        return p
    if (RUNS_DIR / name).is_dir():
        return RUNS_DIR / name
    raise SystemExit(f"No encuentro la corrida {name} (ni como carpeta ni en eval/results/runs/).")


def load_run(run_dir: Path) -> tuple[dict, list[tuple[dict, AnalysisResult]]]:
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    items = []
    for cid in meta["cases"]:
        f = run_dir / f"{cid}.json"
        if not f.exists():
            continue  # caso que no se alcanzó a correr (tope de gasto)
        data = json.loads(f.read_text(encoding="utf-8"))
        items.append((data["case"], AnalysisResult.from_dict(data["result"])))
    return meta, items


def score_run(run_dir: str | Path, only_cases: set[str] | None = None) -> dict:
    run_dir = resolve_run(str(run_dir))
    meta, items = load_run(run_dir)
    if only_cases is not None:
        items = [(c, r) for c, r in items if c["id"] in only_cases]

    totals = {t: {"tp": 0, "fp": 0, "fn": 0} for t in TYPES}
    by_cat: dict[str, dict[str, int]] = {}
    per_case = []
    clean_total = clean_alert = 0
    insufficient = 0
    cite_ok = cite_all = 0
    lat, tok_in, tok_out, cost = [], [], [], []
    errors = 0
    ignored = 0

    for case, result in items:
        m = match_case(result.findings, case["expected"])
        for exp, _ in m["tp"]:
            totals[exp["type"]]["tp"] += 1
        for f in m["fp"]:
            totals[f.type]["fp"] += 1
        for exp in m["fn"]:
            totals[exp["type"]]["fn"] += 1
        cat = by_cat.setdefault(case.get("category", ""), {"tp": 0, "fp": 0, "fn": 0, "cases": 0})
        cat["tp"] += len(m["tp"]); cat["fp"] += len(m["fp"]); cat["fn"] += len(m["fn"]); cat["cases"] += 1

        if not case["expected"]:
            clean_total += 1
            clean_alert += bool(m["fp"])
        insufficient += sum(f.status == "insufficient_evidence" for f in result.findings)
        ignored += m["ignored_optional"]
        ok, tot = _citation_stats(result, case)
        cite_ok += ok
        cite_all += tot

        u = result.usage
        lat.append(u.latency_s); tok_in.append(u.input_tokens); tok_out.append(u.output_tokens); cost.append(u.cost_usd)
        errors += bool(result.error)
        per_case.append({
            "case_id": case["id"], "category": case.get("category", ""), "split": case.get("split", ""),
            "tp": len(m["tp"]), "fp": len(m["fp"]), "fn": len(m["fn"]),
            "fp_detail": [f"[{f.type}] {f.summary[:90]} ({f.origin})" for f in m["fp"]],
            "fn_detail": [f"[{e['type']}] {e['note'][:90]}" for e in m["fn"]],
            "error": result.error,
            "latency_s": u.latency_s,
        })

    by_type = {t: prf(**totals[t]) for t in TYPES if sum(totals[t].values())}
    macro_types = [t for t in by_type if t != "skill_format" or totals["skill_format"]["fn"]]
    macro_f1 = round(statistics.fmean(by_type[t]["f1"] for t in macro_types), 4) if macro_types else 0.0
    tp = sum(v["tp"] for v in totals.values()); fp = sum(v["fp"] for v in totals.values()); fn = sum(v["fn"] for v in totals.values())
    n = len(items)
    # meta.json se escribe antes de que la iteración fije el razonamiento del
    # proveedor; lo que valió en cada análisis está en result.settings.
    prov = {**meta.get("provider", {}), **(items[0][1].settings if items else {})}
    resources = {}
    for _, r in items:
        for k in ("loaded_gb", "gpu_gb", "gpu_share", "load_duration_s", "eval_duration_s"):
            if k in r.settings:
                resources.setdefault(k, []).append(r.settings[k])

    return {
        "run_id": meta["run_id"],
        "provider": prov.get("provider", ""),
        "model": prov.get("model", ""),
        "iteration": meta.get("iteration", ""),
        "thinking": prov.get("thinking", ""),
        "split": meta.get("split", ""),
        "digest": prov.get("digest", ""),
        "quantization": prov.get("quantization", ""),
        "num_ctx": prov.get("num_ctx", ""),
        "n_cases": n,
        "micro": prf(tp, fp, fn),
        "macro_f1": macro_f1,
        "by_type": by_type,
        "by_category": {c: {**prf(v["tp"], v["fp"], v["fn"]), "cases": v["cases"]} for c, v in by_cat.items()},
        "clean_cases": clean_total,
        "clean_with_alert": clean_alert,
        "clean_alert_pct": round(100 * clean_alert / clean_total, 1) if clean_total else None,
        "insufficient_evidence": insufficient,
        "optional_ignored": ignored,
        "citation_fidelity": round(cite_ok / cite_all, 4) if cite_all else None,
        "citations_total": cite_all,
        "valid_response_pct": round(100 * (n - errors) / n, 1) if n else None,
        "errors": errors,
        "latency_mean_s": round(statistics.fmean(lat), 3) if lat else 0,
        "latency_median_s": round(statistics.median(lat), 3) if lat else 0,
        "latency_p95_s": _pctl(lat, 0.95),
        "input_tokens_mean": round(statistics.fmean(tok_in)) if tok_in else 0,
        "output_tokens_mean": round(statistics.fmean(tok_out)) if tok_out else 0,
        "cost_total_usd": round(sum(cost), 5),
        "cost_per_case_usd": round(sum(cost) / n, 5) if n else 0,
        "resources": {k: round(statistics.fmean(v), 2) for k, v in resources.items()},
        "per_case": per_case,
    }


CSV_FIELDS = [
    "run_id", "provider", "model", "iteration", "thinking", "split", "n_cases", "precision", "recall", "f1", "macro_f1",
    "f1_readme_code", "f1_skill_project", "f1_skill_overlap", "f1_redundancy", "clean_alert_pct", "citation_fidelity",
    "valid_response_pct", "insufficient_evidence", "latency_mean_s", "latency_median_s", "latency_p95_s",
    "input_tokens_mean", "output_tokens_mean", "cost_total_usd",
]


def save_score(score: dict, run_dir: Path) -> None:
    """Guarda score.json junto a la corrida y una fila por corrida en eval/results/scores.csv."""
    (run_dir / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")
    row = {
        "run_id": score["run_id"], "provider": score["provider"], "model": score["model"], "iteration": score["iteration"],
        "thinking": score["thinking"], "split": score["split"], "n_cases": score["n_cases"],
        "precision": score["micro"]["precision"], "recall": score["micro"]["recall"], "f1": score["micro"]["f1"],
        "macro_f1": score["macro_f1"], "clean_alert_pct": score["clean_alert_pct"], "citation_fidelity": score["citation_fidelity"],
        "valid_response_pct": score["valid_response_pct"], "insufficient_evidence": score["insufficient_evidence"],
        "latency_mean_s": score["latency_mean_s"], "latency_median_s": score["latency_median_s"],
        "latency_p95_s": score["latency_p95_s"], "input_tokens_mean": score["input_tokens_mean"],
        "output_tokens_mean": score["output_tokens_mean"], "cost_total_usd": score["cost_total_usd"],
    }
    for t in ("readme_code", "skill_project", "skill_overlap", "redundancy"):
        row[f"f1_{t}"] = score["by_type"].get(t, {}).get("f1", "")
    rows = []
    if SCORES_CSV.exists():
        with SCORES_CSV.open(newline="", encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["run_id"] != score["run_id"]]
    rows.append(row)
    with SCORES_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _fmt(v, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    return f"{100 * v:.0f} %" if pct else f"{v:.2f}"


def print_score(s: dict, detail: bool = True) -> None:
    print(f"Corrida {s['run_id']}")
    print(f"  {s['provider']} · {s['model']} · {s['iteration']} · razonamiento {s['thinking'] or 'n/a'} · {s['split']} · {s['n_cases']} casos")
    print(f"\n  {'tipo':15} {'precisión':>9} {'recall':>7} {'F1':>6}   TP  FP  FN")
    for t, v in s["by_type"].items():
        print(f"  {t:15} {v['precision']:9.2f} {v['recall']:7.2f} {v['f1']:6.2f}  {v['tp']:3} {v['fp']:3} {v['fn']:3}")
    m = s["micro"]
    print(f"  {'total (micro)':15} {m['precision']:9.2f} {m['recall']:7.2f} {m['f1']:6.2f}  {m['tp']:3} {m['fp']:3} {m['fn']:3}")
    print(f"  macro-F1: {s['macro_f1']:.2f}")
    clean = f"{s['clean_with_alert']} de {s['clean_cases']} ({s['clean_alert_pct']:.0f} %)" if s["clean_cases"] else "no hay casos limpios"
    print(f"  Casos limpios con alguna alerta: {clean}")
    print(f"  Fidelidad de citas: {_fmt(s['citation_fidelity'], True)} de {s['citations_total']} citas del modelo")
    print(f"  Respuestas válidas: {s['valid_response_pct']:.0f} % ({s['errors']} con error) · evidencia insuficiente (aparte): {s['insufficient_evidence']}")
    print(f"  Latencia: media {s['latency_mean_s']:.1f} s, mediana {s['latency_median_s']:.1f} s, p95 {s['latency_p95_s']:.1f} s")
    print(f"  Tokens por caso: {s['input_tokens_mean']} entrada, {s['output_tokens_mean']} salida · costo {s['cost_total_usd']:.5f} USD")
    if s["resources"]:
        print(f"  Recursos (Ollama): {s['resources']}")
    if detail:
        print("\n  Por categoría de caso:")
        for c, v in s["by_category"].items():
            print(f"    {c:14} {v['cases']:2} casos · P {v['precision']:.2f} R {v['recall']:.2f} F1 {v['f1']:.2f} (TP {v['tp']} FP {v['fp']} FN {v['fn']})")
        print("\n  Errores por caso:")
        for c in s["per_case"]:
            if c["fp"] or c["fn"] or c["error"]:
                print(f"    {c['case_id']:6} FP {c['fp']} FN {c['fn']}" + (f" · ERROR: {c['error']}" if c["error"] else ""))
                for d in c["fp_detail"]:
                    print(f"        + falso positivo {d}")
                for d in c["fn_detail"]:
                    print(f"        - falso negativo {d}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Puntúa una corrida contra las etiquetas")
    ap.add_argument("run", help="Carpeta de la corrida o su run_id")
    ap.add_argument("--brief", action="store_true", help="Sin el detalle por categoría y por caso")
    ap.add_argument("--no-save", action="store_true", help="No escribir score.json ni scores.csv")
    args = ap.parse_args()
    run_dir = resolve_run(args.run)
    score = score_run(run_dir)
    print_score(score, detail=not args.brief)
    if not args.no_save:
        save_score(score, run_dir)
        print(f"\nGuardado en {run_dir.name}/score.json y eval/results/scores.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
