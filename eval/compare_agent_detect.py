"""Experimento D1: detección contra detección.

Se le pide a Claude Code (`claude -p`, solo herramientas de lectura) que revise
un caso de prueba y liste las inconsistencias, sin cambiar nada. Su respuesta
se puntúa con las mismas etiquetas y la misma regla de emparejamiento que
SkillDoc Check, y se compara con las corridas finales de SkillDoc Check (API y
local) sobre los mismos casos.

Para poder puntuarla, al agente se le pide responder en JSON con tipo, archivo,
líneas y cita de cada problema. Su respuesta se toma tal cual (sin la
validación de citas de SkillDoc Check); la fidelidad de sus citas se mide
aparte con el mismo validador.

    python -m eval.compare_agent_detect --cases nt01 nt02 nt03 nt04 nt05 tk01 tk02 tk03 tk04 tk05
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from eval.build_cases import _matches
from eval.compare_agent import load_case
from src.ingest import load_dir
from src.model_provider import parse_json
from src.schemas import Finding
from src.validate_output import validate_findings

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"

AGENT_MODEL = "sonnet"
AGENT_TOOLS = "Read,Glob,Grep"

PROMPT = """Este proyecto es una API pequeña en FastAPI con un README.md y skills para asistentes de programación en .claude/skills/. No modifiques ningún archivo.

Revisa si hay alguno de estos problemas:
- readme_code: el README o la documentación dicen algo que contradice el código o la configuración.
- skill_project: una skill da instrucciones que ya no corresponden al proyecto.
- skill_overlap: dos skills describen el mismo ámbito de uso, de modo que un asistente no sabría cuál usar.
- redundancy: la misma instrucción, con palabras iguales o distintas, aparece en varias skills.

Responde solo con un JSON con esta forma, sin texto adicional:
{"findings": [{"type": "readme_code", "summary": "...", "evidence": [{"path": "README.md", "start_line": 12, "end_line": 12, "quote": "texto literal de la línea"}]}]}

Cada hallazgo debe citar el archivo y las líneas donde está el problema. Si no hay problemas, responde {"findings": []}."""


def run_agent(workdir: Path, budget: float) -> dict:
    cmd = [
        "claude", "-p", PROMPT,
        "--output-format", "json",
        "--model", AGENT_MODEL,
        "--tools", AGENT_TOOLS,
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--max-budget-usd", str(budget),
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=900)
    wall = time.perf_counter() - t0
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": (proc.stderr or proc.stdout)[:300], "wall_s": round(wall, 1), "text": ""}
    tin = tout = 0
    for u in (data.get("modelUsage") or {}).values():
        tin += u.get("inputTokens", 0) + u.get("cacheReadInputTokens", 0) + u.get("cacheCreationInputTokens", 0)
        tout += u.get("outputTokens", 0)
    return {
        "error": "" if not data.get("is_error") else str(data.get("result", ""))[:300],
        "tokens_in": tin,
        "tokens_out": tout,
        "cost_usd": round(data.get("total_cost_usd", 0.0), 5),
        "turns": data.get("num_turns", 0),
        "wall_s": round(wall, 1),
        "text": str(data.get("result", "")),
    }


def extract_json(text: str) -> dict | None:
    parsed, _ = parse_json(text)
    if parsed is not None:
        return parsed
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        parsed, _ = parse_json(text[start : end + 1])
    return parsed


def score_case(case: dict, findings: list[Finding]) -> tuple[int, int, int]:
    unmatched = list(findings)
    tp = fn = 0
    for exp in case["expected"]:
        hit = next((f for f in unmatched if _matches(f, exp)), None)
        if hit:
            unmatched.remove(hit)
            tp += 0 if exp.get("optional") else 1
        elif not exp.get("optional"):
            fn += 1
    return tp, len(unmatched), fn


def main() -> int:
    ap = argparse.ArgumentParser(description="Claude Code revisando, contra SkillDoc Check")
    ap.add_argument("--cases", nargs="+", required=True)
    ap.add_argument("--budget", type=float, default=1.0)
    args = ap.parse_args()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS / "runs" / f"{run_id}_agent_detect"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for cid in args.cases:
        case = load_case(cid)
        base = ROOT / case["repo"]
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / cid
            shutil.copytree(base, workdir)
            res = run_agent(workdir, args.budget)
        parsed = extract_json(res.get("text", "")) or {"findings": []}
        findings = [Finding.from_dict({**d, "status": "confirmed", "severity": "medium", "reason": ""}) for d in parsed.get("findings", []) if isinstance(d, dict)]
        tp, fp, fn = score_case(case, findings)
        _, vstats = validate_findings([Finding.from_dict(f.to_dict()) for f in findings], load_dir(base))
        row = {
            "case_id": cid,
            "category": case["category"],
            "agent": f"Claude Code + {AGENT_MODEL}",
            "tokens_in": res.get("tokens_in", 0),
            "tokens_out": res.get("tokens_out", 0),
            "cost_usd": res.get("cost_usd", 0.0),
            "turns": res.get("turns", 0),
            "wall_s": res.get("wall_s", 0.0),
            "n_findings": len(findings),
            "tp": tp, "fp": fp, "fn": fn,
            "citations": vstats.evidence_total,
            "citations_verified": vstats.evidence_verified,
            "valid_json": int(extract_json(res.get("text", "")) is not None),
            "error": res.get("error", ""),
        }
        rows.append(row)
        (out_dir / f"{cid}.json").write_text(json.dumps({"row": row, "agent_text": res.get("text", "")}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{cid}: {len(findings)} hallazgos | TP {tp} FP {fp} FN {fn} | {row['tokens_in']}+{row['tokens_out']} tok, "
              f"{row['cost_usd']:.4f} USD, {row['turns']} vueltas, {row['wall_s']} s" + (f" | ERROR {row['error']}" if row["error"] else ""), flush=True)

    with (RESULTS / "agent_detect.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nGuardado en eval/results/agent_detect.csv y {out_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
