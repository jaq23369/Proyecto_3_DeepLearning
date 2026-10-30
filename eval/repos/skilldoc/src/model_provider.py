"""Interfaz común para los proveedores de LLM (API y local).

Los dos proveedores reciben exactamente el mismo ModelRequest (mismo prompt,
mismo contexto y mismo esquema JSON) y devuelven un ModelResult. Así la
comparación API vs local cambia solo el modelo.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelRequest:
    system: str
    user: str
    json_schema: dict[str, Any]
    max_tokens: int = 4000


@dataclass
class ModelResult:
    provider: str
    model: str
    text: str = ""
    parsed: dict[str, Any] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    retries: int = 0
    stop_reason: str = ""
    # Mensaje legible si falló (sin red, sin clave, modelo no instalado, JSON inválido).
    error: str = ""
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error and self.parsed is not None


class ModelProvider(ABC):
    name: str = ""

    @abstractmethod
    def analyze(self, request: ModelRequest) -> ModelResult:
        """Envía la solicitud al modelo y devuelve el resultado con su consumo."""

    def describe(self) -> dict[str, Any]:
        """Configuración exacta que se registra en cada corrida."""
        return {"provider": self.name}


def parse_json(text: str) -> tuple[dict[str, Any] | None, str]:
    """Interpreta la salida del modelo. Tolera bloques ```json alrededor."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    try:
        data = json.loads(t)
    except json.JSONDecodeError as exc:
        return None, f"La respuesta del modelo no es JSON válido ({exc.msg})."
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return None, "La respuesta del modelo no tiene la lista findings."
    return data, ""


def get_provider(name: str, **kwargs: Any) -> ModelProvider:
    """name="api" (Anthropic) o "local" (Ollama)."""
    if name == "api":
        from src.api_provider import ClaudeProvider

        return ClaudeProvider(**kwargs)
    if name == "local":
        try:
            from src.local_provider import OllamaProvider
        except ImportError as exc:
            raise RuntimeError("El proveedor local todavía no está disponible (src/local_provider.py).") from exc
        return OllamaProvider(**kwargs)
    raise ValueError(f"Proveedor desconocido: {name}")
