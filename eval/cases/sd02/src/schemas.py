"""Contrato común de datos de SkillDoc Check.

Todo el pipeline (reglas, proveedores de LLM, validación, interfaz y evaluación)
intercambia hallazgos con esta forma. Si cambia algo aquí, cambia para los dos
proveedores al mismo tiempo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Tipos de hallazgo que puede reportar el LLM.
LLM_FINDING_TYPES = ["readme_code", "skill_project", "skill_overlap", "redundancy"]
# skill_format solo lo producen las reglas (frontmatter inválido de SKILL.md).
FINDING_TYPES = LLM_FINDING_TYPES + ["skill_format"]

# Qué tan seguro está el sistema del hallazgo.
STATUSES = ["confirmed", "possible_conflict", "insufficient_evidence"]

SEVERITIES = ["high", "medium", "low"]

TYPE_LABELS = {
    "readme_code": "README vs código",
    "skill_project": "Skill desactualizada",
    "skill_overlap": "Traslape entre skills",
    "redundancy": "Instrucción redundante",
    "skill_format": "Formato de SKILL.md",
}

STATUS_LABELS = {
    "confirmed": "Comprobado",
    "possible_conflict": "Posible conflicto",
    "insufficient_evidence": "Evidencia insuficiente",
}

SEVERITY_LABELS = {"high": "Alta", "medium": "Media", "low": "Baja"}


@dataclass
class Evidence:
    """Un fragmento citado de un archivo examinado."""

    path: str
    start_line: int
    end_line: int
    quote: str
    # Lo llena validate_output: True si la cita existe en esas líneas.
    verified: bool | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Evidence":
        return cls(
            path=str(d.get("path", "")),
            start_line=int(d.get("start_line", 0) or 0),
            end_line=int(d.get("end_line", 0) or 0),
            quote=str(d.get("quote", "")),
            verified=d.get("verified"),
        )


@dataclass
class Finding:
    """Un problema detectado, venga de una regla o del LLM."""

    type: str
    status: str
    severity: str
    summary: str
    evidence: list[Evidence]
    reason: str
    edit_path: str = ""
    suggested_edit: str = ""
    limitations: str = ""
    # "rule" si lo produjo una regla determinista, "llm" si lo produjo el modelo.
    origin: str = "llm"
    # Notas que agrega la validación (citas corregidas, degradaciones, etc.).
    validation_notes: list[str] = field(default_factory=list)
    id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any], origin: str = "llm") -> "Finding":
        return cls(
            type=str(d.get("type", "")),
            status=str(d.get("status", "")),
            severity=str(d.get("severity", "medium")),
            summary=str(d.get("summary", "")),
            evidence=[Evidence.from_dict(e) for e in d.get("evidence", []) or []],
            reason=str(d.get("reason", "")),
            edit_path=str(d.get("edit_path", "") or ""),
            suggested_edit=str(d.get("suggested_edit", "") or ""),
            limitations=str(d.get("limitations", "") or ""),
            origin=str(d.get("origin", origin)),
            validation_notes=list(d.get("validation_notes", []) or []),
            id=str(d.get("id", "") or ""),
        )


@dataclass
class Usage:
    """Consumo de una corrida de análisis (suma de todas las llamadas)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    calls: int = 0
    retries: int = 0


@dataclass
class AnalysisResult:
    """Resultado completo de analizar un repositorio."""

    findings: list[Finding]
    files_examined: list[str]
    files_skipped: list[dict[str, str]]
    provider: str
    model: str
    prompt_version: str
    context_mode: str
    context_hash: str
    context_tokens_est: int
    usage: Usage
    settings: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AnalysisResult":
        return cls(
            findings=[Finding.from_dict(f, f.get("origin", "llm")) for f in d.get("findings", [])],
            files_examined=list(d.get("files_examined", [])),
            files_skipped=list(d.get("files_skipped", [])),
            provider=d.get("provider", ""),
            model=d.get("model", ""),
            prompt_version=d.get("prompt_version", ""),
            context_mode=d.get("context_mode", ""),
            context_hash=d.get("context_hash", ""),
            context_tokens_est=int(d.get("context_tokens_est", 0)),
            usage=Usage(**d.get("usage", {})),
            settings=dict(d.get("settings", {})),
            warnings=list(d.get("warnings", [])),
            error=d.get("error", ""),
        )


# Esquema JSON que deben devolver los dos proveedores (API y local).
# El orden de los campos importa: el modelo escribe primero la evidencia y la
# razón, y solo después decide el estado y la severidad.
_EVIDENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
        "quote": {"type": "string"},
    },
    "required": ["path", "start_line", "end_line", "quote"],
    "additionalProperties": False,
}

LLM_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": LLM_FINDING_TYPES},
                    "evidence": {"type": "array", "items": _EVIDENCE_SCHEMA},
                    "reason": {"type": "string"},
                    "status": {"type": "string", "enum": STATUSES},
                    "severity": {"type": "string", "enum": SEVERITIES},
                    "summary": {"type": "string"},
                    "edit_path": {"type": "string"},
                    "suggested_edit": {"type": "string"},
                    "limitations": {"type": "string"},
                },
                "required": [
                    "type",
                    "evidence",
                    "reason",
                    "status",
                    "severity",
                    "summary",
                    "edit_path",
                    "suggested_edit",
                    "limitations",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}
