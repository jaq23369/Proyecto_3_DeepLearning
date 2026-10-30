"""Material de respaldo para la feria.

- Un ZIP por cada proyecto de examples/ (para probar la subida igual que un visitante).
- Un resultado precalculado por ejemplo con la iteración final y la API.

El resultado precalculado es un respaldo por si falla la red o la API. Al
cargarlo siempre lleva un aviso de que no es un análisis en vivo; no se debe
presentar como inferencia sin internet (para eso está el modo local).

    python -m src.demo_cache            # regenera ZIPs y resultados precalculados
    python -m src.demo_cache --zips     # solo los ZIPs, sin llamar a la API
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from src.analyze import FINAL_ITERATION, analyze_iteration
from src.ingest import load_dir
from src.schemas import AnalysisResult

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
CACHE_DIR = EXAMPLES_DIR / "cache"
ZIPS_DIR = EXAMPLES_DIR / "zips"
SKIP = {"cache", "zips"}


def list_examples() -> list[str]:
    return sorted(p.name for p in EXAMPLES_DIR.iterdir() if p.is_dir() and p.name not in SKIP and not p.name.startswith("."))


def example_path(name: str) -> Path:
    return EXAMPLES_DIR / name


def zip_bytes(name: str) -> bytes:
    """ZIP del ejemplo con una carpeta raíz, como los que descarga GitHub."""
    root = example_path(name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts:
                zf.write(p, f"{name}/{p.relative_to(root).as_posix()}")
    return buf.getvalue()


def save_cached(name: str, result: AnalysisResult) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.json"
    payload = {"example": name, "cached_at": datetime.now().isoformat(timespec="minutes"), "result": result.to_dict()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def has_cached(name: str) -> bool:
    return (CACHE_DIR / f"{name}.json").exists()


def load_cached(name: str) -> AnalysisResult:
    """Devuelve el resultado guardado, con un aviso visible de que es precalculado."""
    payload = json.loads((CACHE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    result = AnalysisResult.from_dict(payload["result"])
    when = payload["cached_at"].replace("T", " ")
    result.warnings.insert(
        0,
        f"Resultado precalculado el {when} con {result.model}. Es un respaldo para la demo, no un análisis en vivo.",
    )
    result.settings["cached"] = True
    result.settings["cached_at"] = payload["cached_at"]
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera el material de respaldo de la demo")
    ap.add_argument("--zips", action="store_true", help="Solo generar los ZIP, sin llamar a la API")
    args = ap.parse_args()

    ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    for name in list_examples():
        (ZIPS_DIR / f"{name}.zip").write_bytes(zip_bytes(name))
        line = f"{name}: ZIP listo"
        if not args.zips:
            result = analyze_iteration(load_dir(example_path(name)), FINAL_ITERATION, provider="api")
            if result.error:
                line += f" | ERROR al precalcular: {result.error}"
            else:
                save_cached(name, result)
                line += f" | precalculado con {result.model}: {len(result.findings)} hallazgos, {result.usage.cost_usd:.5f} USD"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
