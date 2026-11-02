"""Experimento A2: el agente corrige con y sin el diagnóstico de SkillDoc Check.

Se le pide a Claude Code (modo no interactivo, `claude -p`) que deje coherentes
la documentación y las skills de un caso de prueba, en dos condiciones:

- A, sin diagnóstico: el agente revisa todo el proyecto por su cuenta.
- B, con diagnóstico por API: el agente recibe las tareas de corrección que
  genera SkillDoc Check (iteración final, Claude Haiku 5.5) y solo las
  verifica y aplica.
- C, con diagnóstico local: igual que B, pero el diagnóstico lo hace SkillDoc
  Check en modo local (Qwen3-8B con Ollama), sin enviar el código a una API.

Las dos condiciones usan el mismo modelo, las mismas herramientas (leer y
editar archivos, sin terminal) y el mismo encuadre ("el código es la fuente de
verdad, no modifiques archivos .py"). Cada sesión trabaja sobre una copia del
caso en una carpeta temporal; el proyecto real no se toca.

Claude Code protege la carpeta .claude/ y no deja editarla en modo no
interactivo, así que en cada copia las skills se mueven de .claude/skills/ a
skills/. SkillDoc Check analiza esa misma copia, de modo que sus tareas citan
las rutas que ve el agente.

Se mide por sesión: tokens procesados por el agente (entrada, caché y salida),
costo que reporta Claude Code, vueltas y tiempo. En la condición B se suma el
análisis de SkillDoc Check. La calidad se mide con las etiquetas del caso: un
problema cuenta como corregido si la línea desactualizada que citan las
etiquetas ya no está en ese archivo. También se revisa si el agente cambió
código Python.

    python -m eval.compare_agent --cases nt02 nt03 nt05 tk02 tk04 tk05
    python -m eval.compare_agent --cases nt02 nt03 --conditions C

Las filas se guardan en eval/results/agent_handoff.csv; una corrida nueva
reemplaza solo las filas de los mismos casos y condiciones.
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

from src.analyze import FINAL_ITERATION, analyze_iteration
from src.handoff import can_handoff, task_for_finding
from src.ingest import load_dir

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
CASES_FILE = ROOT / "eval" / "cases.jsonl"

AGENT_MODEL = "sonnet"
SKILLS_SRC = ".claude/skills"
SKILLS_DST = "skills"
AGENT_TOOLS = "Read,Glob,Grep,Edit,Write"

FRAME = (
    "Este proyecto es una API pequeña en FastAPI con un README.md y skills para asistentes de programación "
    "en skills/. El código Python es la fuente de verdad. No modifiques archivos .py."
)
PROMPT_A = (
    FRAME
    + "\n\nRevisa si el README, la documentación o las skills dicen algo que ya no coincide con el código, "
    "o si las skills se contradicen o se repiten entre sí, y corrige solo la documentación y las skills para "
    "que queden coherentes. Al terminar, resume en una lista corta qué cambiaste."
)
PROMPT_B_HEAD = (
    FRAME
    + "\n\nUna revisión previa encontró los problemas de abajo. Aplica cada tarea. "
    "Al terminar, resume en una lista corta qué cambiaste.\n"
)


def load_case(case_id: str) -> dict:
    for line in CASES_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            if case["id"] == case_id:
                return case
    raise SystemExit(f"No existe el caso {case_id}")


def agent_path(path: str) -> str:
    return path.replace(SKILLS_SRC + "/", SKILLS_DST + "/", 1)


def prepare(base: Path, dest: Path) -> None:
    shutil.copytree(base, dest)
    if (dest / SKILLS_SRC).exists():
        (dest / SKILLS_SRC).rename(dest / SKILLS_DST)
        if not any((dest / ".claude").iterdir()):
            (dest / ".claude").rmdir()


def stale_lines(case: dict) -> list[dict]:
    """Por etiqueta, las líneas de documentación o skills que marca como desactualizadas."""
    base = ROOT / case["repo"]
    out = []
    for exp in case["expected"]:
        if exp.get("optional"):
            continue
        spots = []
        for path, (start, end) in exp["evidence"].items():
            if path.endswith(".py"):
                continue
            lines = (base / path).read_text(encoding="utf-8").split("\n")
            spots.append({"path": agent_path(path), "text": "\n".join(lines[start - 1 : end]).strip()})
        out.append({"type": exp["type"], "note": exp["note"], "spots": spots})
    return out


def quality(case: dict, workdir: Path) -> dict:
    """Un problema cuenta como corregido si cambió al menos una de sus líneas de documentación.

    En un traslape o una redundancia basta con corregir una de las dos skills.
    """
    base = ROOT / case["repo"]
    items = stale_lines(case)
    fixed = 0
    detail = []
    for it in items:
        changed = [
            not ((workdir / sp["path"]).exists() and sp["text"] in (workdir / sp["path"]).read_text(encoding="utf-8"))
            for sp in it["spots"]
        ]
        ok = any(changed)
        fixed += ok
        detail.append({**it, "fixed": ok})
    py_changed = sorted(
        p.relative_to(base).as_posix()
        for p in base.rglob("*.py")
        if "__pycache__" not in p.parts
        and (not (workdir / p.relative_to(base)).exists() or (workdir / p.relative_to(base)).read_bytes() != p.read_bytes())
    )
    return {"labels": len(items), "fixed": fixed, "py_changed": py_changed, "detail": detail}


def run_agent(prompt: str, workdir: Path, budget: float) -> dict:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", AGENT_MODEL,
        "--tools", AGENT_TOOLS,
        "--permission-mode", "acceptEdits",
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
        return {"error": (proc.stderr or proc.stdout)[:300], "wall_s": round(wall, 1)}
    tokens_in = tokens_out = 0
    for usage in (data.get("modelUsage") or {}).values():
        tokens_in += usage.get("inputTokens", 0) + usage.get("cacheReadInputTokens", 0) + usage.get("cacheCreationInputTokens", 0)
        tokens_out += usage.get("outputTokens", 0)
    return {
        "error": "" if not data.get("is_error") else str(data.get("result", ""))[:300],
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(data.get("total_cost_usd", 0.0), 5),
        "turns": data.get("num_turns", 0),
        "wall_s": round(wall, 1),
        "summary": str(data.get("result", ""))[:1500],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Agente con y sin el diagnóstico de SkillDoc Check")
    ap.add_argument("--cases", nargs="+", required=True)
    ap.add_argument("--budget", type=float, default=1.0, help="Tope en USD por sesión del agente")
    ap.add_argument("--conditions", nargs="+", default=["A", "B", "C"], choices=["A", "B", "C"])
    args = ap.parse_args()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS / "runs" / f"{run_id}_agent"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    for cid in args.cases:
        case = load_case(cid)
        base = ROOT / case["repo"]

        def diagnose(provider: str):
            """Diagnóstico de SkillDoc Check (iteración final) sobre la misma copia que ve el agente."""
            with tempfile.TemporaryDirectory() as tmp:
                prepared = Path(tmp) / cid
                prepare(base, prepared)
                d = analyze_iteration(load_dir(prepared), FINAL_ITERATION, provider=provider)
            t = [task_for_finding(f) for f in d.findings if can_handoff(f)[0]]
            return d, t, PROMPT_B_HEAD + "\n\n".join(f"--- Tarea {i} ---\n{x}" for i, x in enumerate(t, start=1))

        plan = []
        if "A" in args.conditions:
            plan.append(("A_sin_diagnostico", PROMPT_A, None, []))
        if "B" in args.conditions:
            d, t, pr = diagnose("api")
            plan.append(("B_con_skilldoc", pr, d, t))
        if "C" in args.conditions:
            d, t, pr = diagnose("local")
            plan.append(("C_con_skilldoc_local", pr, d, t))

        for cond, prompt, diag, tasks in plan:
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp) / cid
                prepare(base, workdir)
                res = run_agent(prompt, workdir, args.budget)
                q = quality(case, workdir)
            row = {
                "case_id": cid,
                "condition": cond,
                "agent_model": AGENT_MODEL,
                "agent_tokens_in": res.get("tokens_in", 0),
                "agent_tokens_out": res.get("tokens_out", 0),
                "agent_cost_usd": res.get("cost_usd", 0.0),
                "agent_turns": res.get("turns", 0),
                "agent_wall_s": res.get("wall_s", 0.0),
                "skilldoc_model": diag.model if diag else "",
                "skilldoc_tokens": diag.usage.input_tokens + diag.usage.output_tokens if diag else 0,
                "skilldoc_cost_usd": diag.usage.cost_usd if diag else 0.0,
                "skilldoc_s": diag.usage.latency_s if diag else 0.0,
                "skilldoc_findings": len(diag.findings) if diag else 0,
                "tasks_given": len(tasks),
                "labels": q["labels"],
                "fixed": q["fixed"],
                "py_changed": ";".join(q["py_changed"]),
                "error": res.get("error", ""),
            }
            rows.append(row)
            (out_dir / f"{cid}_{cond}.json").write_text(
                json.dumps({"row": row, "quality": q, "agent_summary": res.get("summary", ""), "prompt": prompt}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"{cid} {cond:18} | agente {row['agent_tokens_in']}+{row['agent_tokens_out']} tok, {row['agent_cost_usd']:.4f} USD, "
                  f"{row['agent_turns']} vueltas, {row['agent_wall_s']} s | corregidos {row['fixed']}/{row['labels']}"
                  + (f" | tocó .py: {row['py_changed']}" if row["py_changed"] else "") + (f" | ERROR {row['error']}" if row["error"] else ""),
                  flush=True)

    csv_path = RESULTS / "agent_handoff.csv"
    done = {(r["case_id"], r["condition"]) for r in rows}
    old_rows = []
    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as fh:
            old_rows = [r for r in csv.DictReader(fh) if (r["case_id"], r["condition"]) not in done]
    fields = list(rows[0])
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in fields} for r in old_rows + rows])
    print(f"\nGuardado en {csv_path.relative_to(ROOT)} y {out_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
