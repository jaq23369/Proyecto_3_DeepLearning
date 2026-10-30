"""Selección del contexto que se le envía al modelo.

No hay RAG ni embeddings: se trabaja solo con los archivos que el usuario acaba
de subir. Las skills, el README y la configuración entran completos; el código
entra por relevancia léxica (rutas, nombres de archivo y términos que mencionan
la documentación y las skills). Si un archivo no cabe, se parte en fragmentos
por líneas.

Cada línea va numerada ("12| texto") para que el modelo pueda citar ruta y
líneas exactas, y la validación pueda comprobarlas.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from src.ingest import Repo, SourceFile

DEFAULT_BUDGET_TOKENS = 10_000
CHUNK_TOKENS = 1_000
OVERLAP_TOKENS = 120
# Aproximación de caracteres por token para código y Markdown. Los tokens reales
# se registran con lo que devuelve cada proveedor.
CHARS_PER_TOKEN = 3.5

ALWAYS_KINDS = ("skill", "skill_ref", "readme", "doc", "config")
KIND_ORDER = {"skill": 0, "skill_ref": 1, "readme": 2, "doc": 3, "config": 4, "python": 5, "other": 6}

TERM_RE = re.compile(r"`([^`\n]+)`|(/[a-z0-9_\-/{}]+)|\b([A-Za-z_][A-Za-z0-9_]{3,})\b")
STOPWORDS = {
    "with", "that", "this", "from", "when", "your", "will", "must", "should", "into", "each", "every",
    "para", "como", "cuando", "debe", "esta", "este", "todos", "test", "tests", "file", "files", "true",
    "false", "none", "return", "import", "def", "class", "self", "the", "and", "use", "using", "always",
}


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


@dataclass
class Chunk:
    path: str
    kind: str
    start_line: int
    end_line: int
    text: str
    score: float = 0.0

    @property
    def tokens(self) -> int:
        # Se cuenta el texto tal como va al modelo (con números de línea y encabezado).
        return estimate_tokens(_render(self))


@dataclass
class Context:
    text: str
    mode: str
    chunks: list[Chunk]
    dropped: list[str] = field(default_factory=list)
    budget_tokens: int = DEFAULT_BUDGET_TOKENS

    @property
    def tokens_est(self) -> int:
        return estimate_tokens(self.text)

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:16]

    @property
    def files_included(self) -> list[str]:
        return sorted({c.path for c in self.chunks})


def _render(chunk: Chunk) -> str:
    lines = chunk.text.split("\n")
    width = len(str(chunk.end_line))
    body = "\n".join(f"{n:>{width}}| {line}" for n, line in zip(range(chunk.start_line, chunk.end_line + 1), lines))
    total = f"líneas {chunk.start_line}-{chunk.end_line}"
    return f"=== ARCHIVO: {chunk.path} (tipo: {chunk.kind}, {total}) ===\n{body}\n=== FIN: {chunk.path} ==="


def _whole(f: SourceFile) -> Chunk:
    return Chunk(f.path, f.kind, 1, len(f.lines), f.text)


def _split(f: SourceFile) -> list[Chunk]:
    """Fragmentos de ~CHUNK_TOKENS con solapamiento, cortando por líneas."""
    max_chars = int(CHUNK_TOKENS * CHARS_PER_TOKEN)
    overlap_chars = int(OVERLAP_TOKENS * CHARS_PER_TOKEN)
    lines = f.lines
    chunks: list[Chunk] = []
    start = 0
    while start < len(lines):
        size, end = 0, start
        while end < len(lines) and (size + len(lines[end]) + 1 <= max_chars or end == start):
            size += len(lines[end]) + 1
            end += 1
        chunks.append(Chunk(f.path, f.kind, start + 1, end, "\n".join(lines[start:end])))
        if end >= len(lines):
            break
        # Retroceder para dejar solapamiento entre fragmentos.
        back, new_start = 0, end
        while new_start > start + 1 and back < overlap_chars:
            new_start -= 1
            back += len(lines[new_start]) + 1
        start = new_start
    return chunks


def _terms(repo: Repo) -> set[str]:
    """Términos que mencionan la documentación y las skills."""
    terms: set[str] = set()
    for f in repo.files.values():
        if f.kind not in ("skill", "skill_ref", "readme", "doc"):
            continue
        for m in TERM_RE.finditer(f.text):
            token = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            if not token or token.lower() in STOPWORDS:
                continue
            terms.add(token.lower())
            for part in re.split(r"[/.:\s]+", token):
                if len(part) >= 4 and part.lower() not in STOPWORDS:
                    terms.add(part.lower())
    return terms


def _score(chunk: Chunk, terms: set[str], mentioned_paths: set[str]) -> float:
    text = chunk.text.lower()
    score = sum(1.0 for t in terms if t in text)
    if chunk.path in mentioned_paths or PurePosixPath(chunk.path).name in mentioned_paths:
        score += 10
    if re.search(r"@\w+\.(get|post|put|patch|delete)\(", chunk.text):
        score += 8
    return score


def build_context(repo: Repo, mode: str = "selected", budget_tokens: int = DEFAULT_BUDGET_TOKENS) -> Context:
    """mode="selected": selección por relevancia dentro del presupuesto.
    mode="raw": todos los archivos completos, sin seleccionar (para el experimento T1).
    """
    files = sorted(
        (f for f in repo.files.values() if f.text.strip()),
        key=lambda f: (KIND_ORDER.get(f.kind, 9), f.path),
    )

    if mode == "raw":
        chunks = [_whole(f) for f in files]
        return Context(text="\n\n".join(_render(c) for c in chunks), mode=mode, chunks=chunks, budget_tokens=budget_tokens)

    chosen: list[Chunk] = []
    dropped: list[str] = []
    used = 0

    # 1. Skills, README, documentación y configuración entran completos.
    for f in files:
        if f.kind in ALWAYS_KINDS:
            c = _whole(f)
            if used + c.tokens <= budget_tokens:
                chosen.append(c)
                used += c.tokens
            else:
                dropped.append(f"{f.path} (no cabe en el presupuesto)")

    # 2. Código: por relevancia, completo si es pequeño y en fragmentos si no.
    terms = _terms(repo)
    mentioned = {t for t in terms if "/" in t or t.endswith(".py")}
    candidates: list[Chunk] = []
    for f in files:
        if f.kind in ALWAYS_KINDS:
            continue
        whole = _whole(f)
        candidates += [whole] if whole.tokens <= CHUNK_TOKENS else _split(f)
    for c in candidates:
        c.score = _score(c, terms, mentioned)
    for c in sorted(candidates, key=lambda c: (-c.score, c.path, c.start_line)):
        if used + c.tokens <= budget_tokens:
            chosen.append(c)
            used += c.tokens
        else:
            dropped.append(f"{c.path}:{c.start_line}-{c.end_line}")

    chosen.sort(key=lambda c: (KIND_ORDER.get(c.kind, 9), c.path, c.start_line))
    text = "\n\n".join(_render(c) for c in chosen)
    return Context(text=text, mode=mode, chunks=chosen, dropped=dropped, budget_tokens=budget_tokens)
