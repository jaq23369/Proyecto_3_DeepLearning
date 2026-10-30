"""Reglas deterministas: lo que se puede comprobar sin un LLM.

Cada regla devuelve hallazgos con el mismo formato que el modelo (schemas.Finding)
y origin="rule". Si una regla no puede demostrar algo, no lo marca como
"confirmed".

Formato de SKILL.md según https://agentskills.io/specification (consultada el
29 de octubre de 2026).
"""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

import yaml

from src.ingest import Repo, SourceFile
from src.schemas import Evidence, Finding

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
DOC_KINDS = {"readme", "doc", "skill", "skill_ref"}
SKILL_KINDS = {"skill", "skill_ref"}

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# "POST /predict", "`GET /items`" y filas de tabla como "| GET | `/items` |".
ENDPOINT_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\b[\s|]*`?(/[A-Za-z0-9_\-/{}.:]*)")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
PATH_EXTENSIONS = (".py", ".md", ".toml", ".txt", ".yaml", ".yml", ".json", ".cfg", ".ini", ".sh")
# Módulos que se invocan con python -m pero no son del proyecto.
EXTERNAL_MODULES = {"pytest", "pip", "venv", "uvicorn", "http", "unittest", "black", "ruff", "mypy", "build"}


@dataclass
class Route:
    method: str
    path: str
    file: str
    line: int
    source: str


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _ev(f: SourceFile, start: int, end: int | None = None) -> Evidence:
    end = end or start
    quote = "\n".join(f.lines[start - 1 : end]).strip()
    return Evidence(path=f.path, start_line=start, end_line=end, quote=quote, verified=True)


def _finding_type(f: SourceFile) -> str:
    return "skill_project" if f.kind in SKILL_KINDS else "readme_code"


def _norm_route(path: str) -> str:
    path = re.sub(r"\{[^}]*\}", "{}", path.rstrip("/") or "/")
    return path


def _frontmatter(f: SourceFile) -> tuple[dict | None, int, str]:
    """Devuelve (datos, línea donde cierra el frontmatter, error)."""
    lines = f.lines
    if not lines or lines[0].strip() != "---":
        return None, 0, "SKILL.md no empieza con un bloque de frontmatter YAML (---)."
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            raw = "\n".join(lines[1:i])
            try:
                data = yaml.safe_load(raw) or {}
            except yaml.YAMLError as exc:
                return None, i + 1, f"El frontmatter no es YAML válido ({exc.__class__.__name__})."
            if not isinstance(data, dict):
                return None, i + 1, "El frontmatter debe ser un mapa de claves y valores."
            return data, i + 1, ""
    return None, 0, "El frontmatter de SKILL.md no se cierra con ---."


def _in_fences(f: SourceFile) -> list[bool]:
    """Marca qué líneas están dentro de un bloque de código ```."""
    inside, out = False, []
    for line in f.lines:
        if line.strip().startswith("```"):
            out.append(True)
            inside = not inside
            continue
        out.append(inside)
    return out


def _exists(repo: Repo, path: str) -> bool:
    path = path.strip().rstrip("/")
    if not path:
        return True
    if path in repo.files:
        return True
    prefix = path + "/"
    if any(p.startswith(prefix) for p in repo.files):
        return True
    # Un nombre sin carpeta (por ejemplo `SKILL.md`) puede referirse a cualquier archivo con ese nombre.
    if "/" not in path and any(p.rsplit("/", 1)[-1] == path for p in repo.files):
        return True
    return any(s["path"] == path or s["path"].startswith(prefix) for s in repo.skipped)


def _closest(name: str, options: list[str]) -> str:
    match = difflib.get_close_matches(name, options, n=1, cutoff=0.4)
    return match[0] if match else ""


# ---------------------------------------------------------------------------
# 1. Formato de SKILL.md
# ---------------------------------------------------------------------------

def check_skill_format(repo: Repo) -> list[Finding]:
    findings: list[Finding] = []
    for f in repo.by_kind("skill"):
        data, end, error = _frontmatter(f)
        problems: list[str] = []
        if error:
            problems.append(error)
        else:
            name = data.get("name")
            desc = data.get("description")
            folder = PurePosixPath(f.path).parent.name
            if not name:
                problems.append("Falta el campo obligatorio name.")
            elif not isinstance(name, str) or len(name) > 64 or not NAME_RE.match(name):
                problems.append(
                    "name debe tener de 1 a 64 caracteres, solo minúsculas, números y guiones, "
                    "sin guion al inicio o al final ni guiones dobles."
                )
            elif folder and name != folder:
                problems.append(f"name ({name}) no coincide con el nombre de la carpeta ({folder}).")
            if not desc or not isinstance(desc, str):
                problems.append("Falta el campo obligatorio description o está vacío.")
            elif len(desc) > 1024:
                problems.append("description supera los 1024 caracteres.")
            comp = data.get("compatibility")
            if comp is not None and (not isinstance(comp, str) or not 1 <= len(comp) <= 500):
                problems.append("compatibility debe tener de 1 a 500 caracteres.")
            meta = data.get("metadata")
            if meta is not None and not isinstance(meta, dict):
                problems.append("metadata debe ser un mapa de claves y valores.")
        if len(f.lines) > 500:
            problems.append(
                f"SKILL.md tiene {len(f.lines)} líneas y la especificación recomienda menos de 500; "
                "conviene mover detalle a archivos de referencia."
            )
        if problems:
            findings.append(
                Finding(
                    type="skill_format",
                    status="confirmed",
                    severity="high" if error or any("Falta" in p for p in problems) else "medium",
                    summary=f"{f.path} no cumple el formato de Agent Skills.",
                    evidence=[_ev(f, 1, max(1, min(end or 1, len(f.lines))))],
                    reason=" ".join(problems),
                    edit_path=f.path,
                    suggested_edit="Corregir el frontmatter para que tenga name y description válidos según la especificación de Agent Skills.",
                    origin="rule",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 2. Rutas de FastAPI (subconjunto soportado)
# ---------------------------------------------------------------------------

def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _kw(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == name:
            return _const_str(kw.value)
    return None


def extract_fastapi_routes(repo: Repo) -> list[Route]:
    """Rutas declaradas con @app.get("/x"), @router.post("/y"), etc.

    Soporta APIRouter(prefix=...) dentro del mismo archivo e
    include_router(modulo.router, prefix=...) con el nombre del módulo. Lo que no
    reconoce simplemente no aparece, por eso solo se compara si hay rutas.
    """
    raw: list[tuple[Route, str]] = []  # (ruta, nombre de la variable del router)
    router_prefix: dict[tuple[str, str], str] = {}  # (archivo, variable) -> prefijo
    include_prefix: dict[str, str] = {}  # stem del módulo -> prefijo

    for f in repo.by_kind("python"):
        try:
            tree = ast.parse(f.text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = node.value.func
                fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if fname == "APIRouter":
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            router_prefix[(f.path, t.id)] = _kw(node.value, "prefix") or ""
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router":
                prefix = _kw(node, "prefix") or ""
                if node.args:
                    target = node.args[0]
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        include_prefix[target.value.id] = prefix
                    elif isinstance(target, ast.Name):
                        include_prefix[target.id] = prefix
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                        continue
                    method = dec.func.attr.lower()
                    if method not in HTTP_METHODS:
                        continue
                    path = _const_str(dec.args[0]) if dec.args else _kw(dec, "path")
                    if path is None:
                        continue
                    var = dec.func.value.id if isinstance(dec.func.value, ast.Name) else ""
                    line = dec.lineno
                    raw.append((Route(method.upper(), path, f.path, line, f.lines[line - 1].strip()), var))

    routes: list[Route] = []
    for r, var in raw:
        prefix = router_prefix.get((r.file, var), "")
        stem = PurePosixPath(r.file).stem
        prefix = include_prefix.get(stem, include_prefix.get(var, "")) + prefix if var != "app" else ""
        routes.append(Route(r.method, (prefix + r.path) or "/", r.file, r.line, r.source))
    return routes


def check_endpoints(repo: Repo, routes: list[Route]) -> list[Finding]:
    if not routes:
        return []
    known = {(r.method, _norm_route(r.path)) for r in routes}
    findings: list[Finding] = []
    for f in repo.files.values():
        if f.kind not in DOC_KINDS:
            continue
        mentions: dict[tuple[str, str], list[int]] = {}
        for i, line in enumerate(f.lines, start=1):
            for m in ENDPOINT_RE.finditer(line):
                method, path = m.group(1), m.group(2).rstrip(".:`")
                if (method, _norm_route(path)) not in known:
                    mentions.setdefault((method, path), []).append(i)
        for (method, path), lines in mentions.items():
            same_method = [r for r in routes if r.method == method] or routes
            best = max(same_method, key=lambda r: difflib.SequenceMatcher(None, r.path, path).ratio())
            code_file = repo.files[best.file]
            evidence = [_ev(f, ln) for ln in lines] + [_ev(code_file, best.line, best.line + 1)]
            findings.append(
                Finding(
                    type=_finding_type(f),
                    status="confirmed" if repo.is_complete else "possible_conflict",
                    severity="high",
                    summary=f"{f.path} menciona {method} {path}, pero esa ruta no está definida en el código.",
                    evidence=evidence,
                    reason=(
                        f"Las rutas declaradas en el código son: "
                        + ", ".join(sorted(f"{r.method} {r.path}" for r in routes))
                        + f". La más parecida es {best.method} {best.path} en {best.file}:{best.line}."
                    ),
                    edit_path=f.path,
                    suggested_edit=f"Reemplazar `{method} {path}` por `{best.method} {best.path}` si es la misma operación, o eliminar la referencia si la ruta ya no existe.",
                    limitations="" if repo.is_complete else "Se analizaron archivos sueltos; la ruta podría estar definida en un archivo que no se subió.",
                    origin="rule",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 3. Archivos y comandos mencionados que no existen
# ---------------------------------------------------------------------------

def _looks_like_path(token: str) -> bool:
    token = token.strip()
    if not token or " " in token or token.startswith(("http", "/", "-", "$", "<")):
        return False
    if any(c in token for c in "*?()[]{}=,;'\"|"):
        return False
    return "/" in token or token.endswith(PATH_EXTENSIONS)


def _path_candidates(f: SourceFile, token: str) -> list[str]:
    token = token.strip().removeprefix("./")
    cands = [token]
    if f.kind in SKILL_KINDS:
        # En una skill las rutas pueden ser relativas a la carpeta de la skill.
        skill_root = f.path.split("/SKILL.md")[0] if f.kind == "skill" else str(PurePosixPath(f.path).parent)
        cands.append(f"{skill_root}/{token}")
    return cands


def _command_targets(command: str) -> list[str]:
    """Rutas locales que un comando necesita para funcionar."""
    targets: list[str] = []
    parts = command.split()
    if not parts:
        return targets
    if parts[0] == "uvicorn" and len(parts) > 1 and ":" in parts[1]:
        module = parts[1].split(":")[0]
        targets.append(module.replace(".", "/") + ".py")
    elif parts[0] in ("python", "python3") and len(parts) > 1:
        if parts[1] == "-m" and len(parts) > 2:
            module = parts[2]
            if module.split(".")[0] not in EXTERNAL_MODULES:
                targets.append(module.replace(".", "/") + ".py")
        elif parts[1].endswith(".py"):
            targets.append(parts[1])
    elif parts[0] == "pytest":
        targets += [p.split("::")[0] for p in parts[1:] if not p.startswith("-")]
    elif parts[:2] in (["pip", "install"], ["pip3", "install"]) and "-r" in parts:
        idx = parts.index("-r")
        if idx + 1 < len(parts):
            targets.append(parts[idx + 1])
    return targets


def _module_exists(repo: Repo, target: str) -> bool:
    if target.endswith(".py") and _exists(repo, target[:-3] + "/__init__.py"):
        return True
    if target.endswith(".py") and _exists(repo, target[:-3]):
        return True
    return _exists(repo, target)


def check_references(repo: Repo) -> list[Finding]:
    """Archivos o comandos citados en README y skills que no existen.

    Solo aplica cuando se subió el proyecto completo (ZIP o carpeta); con
    archivos sueltos no se puede afirmar que algo falta.
    """
    if not repo.is_complete:
        return []
    all_paths = list(repo.files)
    findings: list[Finding] = []
    for f in repo.files.values():
        if f.kind not in DOC_KINDS:
            continue
        fences = _in_fences(f)
        missing: dict[str, list[int]] = {}
        commands: dict[str, list[int]] = {}
        for i, line in enumerate(f.lines, start=1):
            if f.kind == "skill" and i == 1:
                continue
            inline = INLINE_CODE_RE.findall(line)
            for token in inline:
                if _looks_like_path(token):
                    if not any(_exists(repo, c) for c in _path_candidates(f, token)):
                        missing.setdefault(token.strip(), []).append(i)
                else:
                    for target in _command_targets(token):
                        if not _module_exists(repo, target):
                            commands.setdefault(f"{token.strip()}|{target}", []).append(i)
            if fences[i - 1] and not line.strip().startswith("```"):
                for target in _command_targets(line.strip()):
                    if not _module_exists(repo, target):
                        commands.setdefault(f"{line.strip()}|{target}", []).append(i)

        for token, lines in missing.items():
            near = _closest(token, all_paths)
            findings.append(
                Finding(
                    type=_finding_type(f),
                    status="confirmed",
                    severity="medium",
                    summary=f"{f.path} menciona el archivo `{token}`, que no existe en el proyecto.",
                    evidence=[_ev(f, ln) for ln in lines],
                    reason=f"No hay ningún archivo ni carpeta `{token}` entre los archivos del proyecto."
                    + (f" El archivo existente más parecido es `{near}`." if near else ""),
                    edit_path=f.path,
                    suggested_edit=(
                        f"Cambiar la referencia por `{near}` si es el archivo correcto, o eliminar la mención si el archivo ya no forma parte del proyecto."
                        if near
                        else "Eliminar la mención o corregir la ruta si el archivo se movió."
                    ),
                    origin="rule",
                )
            )
        missing_lines = {ln for lines in missing.values() for ln in lines}
        for key, lines in commands.items():
            command, target = key.split("|", 1)
            # Si la misma línea ya tiene un archivo inexistente, es el mismo problema.
            if set(lines) & missing_lines:
                continue
            findings.append(
                Finding(
                    type=_finding_type(f),
                    status="confirmed",
                    severity="medium",
                    summary=f"El comando `{command}` en {f.path} apunta a `{target}`, que no existe.",
                    evidence=[_ev(f, ln) for ln in lines],
                    reason=f"El comando necesita `{target}` y ese archivo no está en el proyecto.",
                    edit_path=f.path,
                    suggested_edit="Actualizar el comando para que use un archivo o módulo existente.",
                    origin="rule",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 4. Instrucciones duplicadas y descripciones repetidas entre skills
# ---------------------------------------------------------------------------

def _norm_instruction(line: str) -> str:
    line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
    return re.sub(r"\s+", " ", line).strip().lower()


def check_duplicates(repo: Repo) -> list[Finding]:
    skills = [f for f in repo.files.values() if f.kind in SKILL_KINDS]
    seen: dict[str, list[tuple[SourceFile, int]]] = {}
    for f in skills:
        _, body_start, _ = _frontmatter(f) if f.kind == "skill" else (None, 0, "")
        fences = _in_fences(f)
        for i, line in enumerate(f.lines, start=1):
            if i <= body_start or fences[i - 1] or line.lstrip().startswith("#"):
                continue
            norm = _norm_instruction(line)
            if len(norm) >= 25:
                seen.setdefault(norm, []).append((f, i))
    findings: list[Finding] = []
    for norm, places in seen.items():
        files = {f.path for f, _ in places}
        if len(files) < 2:
            continue
        findings.append(
            Finding(
                type="redundancy",
                status="confirmed",
                severity="low",
                summary=f"La misma instrucción aparece en {len(files)} skills.",
                evidence=[_ev(f, ln) for f, ln in places],
                reason="Repetir la instrucción en varias skills carga el mismo texto varias veces y obliga a mantener copias sincronizadas.",
                edit_path=places[0][0].path,
                suggested_edit="Dejar la instrucción en una sola skill (o en un archivo de referencia compartido) y quitarla de las demás.",
                origin="rule",
            )
        )
    return findings


def check_description_overlap(repo: Repo) -> list[Finding]:
    """Frases idénticas en las descripciones de dos skills.

    Es un riesgo de conflicto, no un fallo comprobado: no sabemos qué skill
    cargaría un agente sin observar una ejecución real.
    """
    descs: list[tuple[SourceFile, int, list[str]]] = []
    for f in repo.by_kind("skill"):
        data, _, error = _frontmatter(f)
        if error or not isinstance(data.get("description"), str):
            continue
        line = next((i for i, l in enumerate(f.lines, start=1) if l.strip().startswith("description:")), 1)
        sentences = [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+", data["description"]) if len(s.strip()) >= 15]
        descs.append((f, line, sentences))
    findings: list[Finding] = []
    for a in range(len(descs)):
        for b in range(a + 1, len(descs)):
            fa, la, sa = descs[a]
            fb, lb, sb = descs[b]
            shared = sorted(set(sa) & set(sb))
            if not shared:
                continue
            findings.append(
                Finding(
                    type="skill_overlap",
                    status="possible_conflict",
                    severity="medium",
                    summary=f"Las skills {PurePosixPath(fa.path).parent.name} y {PurePosixPath(fb.path).parent.name} usan la misma frase para decir cuándo activarse.",
                    evidence=[_ev(fa, la), _ev(fb, lb)],
                    reason=f"Ambas descripciones dicen: \"{shared[0]}\". Con la misma condición de uso, el asistente no tiene cómo elegir entre ellas.",
                    edit_path=fb.path,
                    suggested_edit="Delimitar cada descripción a su propio caso de uso (por ejemplo, una para escribir pruebas y otra para modificar rutas).",
                    limitations="Es un riesgo según el texto; no se observó una ejecución real del asistente.",
                    origin="rule",
                )
            )
    return findings


# ---------------------------------------------------------------------------

def run_all(repo: Repo) -> tuple[list[Finding], dict]:
    """Corre todas las reglas y devuelve (hallazgos, datos extraídos)."""
    routes = extract_fastapi_routes(repo)
    findings = (
        check_skill_format(repo)
        + check_endpoints(repo, routes)
        + check_references(repo)
        + check_duplicates(repo)
        + check_description_overlap(repo)
    )
    facts = {
        # Sin barra final: para FastAPI /items y /items/ son la misma ruta.
        "routes": [f"{r.method} {_norm_route(r.path)} ({r.file}:{r.line})" for r in routes],
        "skills": [f.path for f in repo.by_kind("skill")],
    }
    return findings, facts
