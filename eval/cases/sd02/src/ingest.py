"""Carga del proyecto del usuario: ZIP, archivos sueltos o una carpeta local.

Nunca se ejecuta nada del repositorio. Solo se lee texto, se filtra lo que no
sirve (dependencias, binarios, secretos) y se guarda cada archivo con su ruta,
sus líneas y un hash para poder citarlo después.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

# Límites de diseño del MVP (se ajustan con las pruebas de costo y latencia).
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_FILES = 60
MAX_FILE_BYTES = 200 * 1024

TEXT_EXTENSIONS = {".py", ".md", ".toml", ".txt", ".yaml", ".yml", ".json", ".cfg", ".ini"}

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".idea", ".vscode", ".tox", "site-packages",
}
IGNORED_NAMES = {".DS_Store", "poetry.lock", "package-lock.json", "uv.lock"}


@dataclass
class SourceFile:
    path: str
    text: str
    kind: str
    sha: str

    @property
    def lines(self) -> list[str]:
        return self.text.split("\n")


@dataclass
class Repo:
    files: dict[str, SourceFile]
    skipped: list[dict[str, str]] = field(default_factory=list)
    # "zip" o "dir" si es el proyecto completo, "files" si son archivos sueltos.
    # Con archivos sueltos no se puede afirmar que una ruta "no existe".
    source_mode: str = "zip"

    def by_kind(self, kind: str) -> list[SourceFile]:
        return [f for f in self.files.values() if f.kind == kind]

    @property
    def is_complete(self) -> bool:
        return self.source_mode in ("zip", "dir")


class IngestError(Exception):
    """Error legible para mostrarle al usuario."""


def _skip_reason(path: str) -> str | None:
    p = PurePosixPath(path)
    if any(part in IGNORED_DIRS for part in p.parts[:-1]):
        return "carpeta de dependencias o generada"
    name = p.name
    if name in IGNORED_NAMES:
        return "archivo generado"
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return "posible archivo de secretos"
    if p.suffix.lower() not in TEXT_EXTENSIONS and name not in ("SKILL.md",):
        return "extensión no admitida"
    return None


def _safe_path(raw: str) -> str | None:
    """Normaliza una ruta del ZIP y rechaza las que intentan salirse."""
    raw = raw.replace("\\", "/")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        return None
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _decode(data: bytes) -> str | None:
    if b"\x00" in data[:4096]:
        return None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None
    # Saltos de línea uniformes; el contenido citado no cambia.
    return text.replace("\r\n", "\n").replace("\r", "\n")


def classify(path: str, skill_dirs: set[str]) -> str:
    p = PurePosixPath(path)
    if p.name == "SKILL.md":
        return "skill"
    if any(path.startswith(d + "/") for d in skill_dirs):
        return "skill_ref"
    if p.name.lower().startswith("readme"):
        return "readme"
    if p.suffix == ".py":
        return "python"
    if p.name in ("pyproject.toml", "requirements.txt", "setup.cfg") or p.suffix in (".toml", ".cfg", ".ini"):
        return "config"
    if p.suffix == ".md":
        return "doc"
    return "other"


def _strip_common_root(paths: list[str]) -> dict[str, str]:
    """Si todo el ZIP está dentro de una sola carpeta, la quita de las rutas."""
    firsts = {p.split("/")[0] for p in paths}
    if len(firsts) == 1 and all("/" in p for p in paths):
        root = firsts.pop() + "/"
        return {p: p[len(root):] for p in paths}
    return {p: p for p in paths}


def _build(raw_files: list[tuple[str, bytes]], source_mode: str, skipped: list[dict[str, str]] | None = None) -> Repo:
    skipped = list(skipped or [])
    accepted: list[tuple[str, bytes]] = []

    for raw_path, data in raw_files:
        path = _safe_path(raw_path)
        if path is None:
            skipped.append({"path": raw_path, "reason": "ruta insegura"})
            continue
        reason = _skip_reason(path)
        if reason:
            skipped.append({"path": path, "reason": reason})
            continue
        if len(data) > MAX_FILE_BYTES:
            skipped.append({"path": path, "reason": "archivo demasiado grande"})
            continue
        accepted.append((path, data))

    if source_mode == "zip":
        renamed = _strip_common_root([p for p, _ in accepted])
        accepted = [(renamed[p], d) for p, d in accepted]

    # Prioridad si hay más archivos que el límite: skills, README, config y código.
    order = {"SKILL.md": 0}
    accepted.sort(key=lambda x: (order.get(PurePosixPath(x[0]).name, 1), x[0].count("/"), x[0]))

    skill_dirs = {str(PurePosixPath(p).parent) for p, _ in accepted if PurePosixPath(p).name == "SKILL.md"}
    files: dict[str, SourceFile] = {}
    for path, data in accepted:
        if len(files) >= MAX_FILES:
            skipped.append({"path": path, "reason": f"se superó el máximo de {MAX_FILES} archivos"})
            continue
        text = _decode(data)
        if text is None:
            skipped.append({"path": path, "reason": "binario o codificación ilegible"})
            continue
        files[path] = SourceFile(
            path=path,
            text=text,
            kind=classify(path, skill_dirs),
            sha=hashlib.sha256(data).hexdigest()[:12],
        )

    if not files:
        raise IngestError("No se encontró ningún archivo de texto admitido (.py, .md, .toml, .txt, .yaml, .json).")
    return Repo(files=files, skipped=skipped, source_mode=source_mode)


def load_zip(data: bytes) -> Repo:
    if len(data) > MAX_ZIP_BYTES:
        raise IngestError(f"El ZIP pesa más de {MAX_ZIP_BYTES // (1024 * 1024)} MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise IngestError("El archivo no es un ZIP válido.") from exc
    raw: list[tuple[str, bytes]] = []
    pre_skipped: list[dict[str, str]] = []
    total = 0
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Protección contra ZIPs que se inflan muchísimo al descomprimir.
            total += info.file_size
            if total > MAX_ZIP_BYTES * 5:
                raise IngestError("El contenido descomprimido es demasiado grande.")
            if _skip_reason(info.filename.replace("\\", "/")):
                # Se pasa vacío solo para que quede registrado el motivo.
                raw.append((info.filename, b""))
            elif info.file_size > MAX_FILE_BYTES:
                pre_skipped.append({"path": info.filename, "reason": "archivo demasiado grande"})
            else:
                raw.append((info.filename, zf.read(info)))
    return _build(raw, "zip", pre_skipped)


def load_files(items: list[tuple[str, bytes]]) -> Repo:
    """Archivos sueltos (por ejemplo desde st.file_uploader)."""
    return _build(items, "files")


def load_dir(root: str | Path) -> Repo:
    root = Path(root)
    if not root.is_dir():
        raise IngestError(f"No existe la carpeta {root}.")
    raw: list[tuple[str, bytes]] = []
    pre_skipped: list[dict[str, str]] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if _skip_reason(rel):
            raw.append((rel, b""))
        elif p.stat().st_size > MAX_FILE_BYTES:
            pre_skipped.append({"path": rel, "reason": "archivo demasiado grande"})
        else:
            raw.append((rel, p.read_bytes()))
    return _build(raw, "dir", pre_skipped)
