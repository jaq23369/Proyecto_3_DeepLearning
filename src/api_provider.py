"""Proveedor por API: Claude (Anthropic).

Usa salidas estructuradas (output_config.format) para que la respuesta cumpla
el esquema JSON común. Registra tokens, costo y latencia de cada llamada.

Sobre los parámetros de generación: en los modelos actuales de Anthropic ya no
se envían temperature, top_p ni top_k (la API los rechaza). Lo que se controla
es el razonamiento previo (thinking), el esfuerzo (effort) y max_tokens, y
eso es lo que se registra en cada corrida.
"""

from __future__ import annotations

import os
import time

import anthropic
from dotenv import load_dotenv

from src.model_provider import ModelProvider, ModelRequest, ModelResult, parse_json

load_dotenv()

# USD por millón de tokens (entrada, salida). Consultado el 29 de octubre de 2026.
# Haiku 5.5 cobra 0.10 / 0.50 hasta 100K tokens de entrada y 0.50 / 2.50 arriba de eso.
PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "long_input": 0.50, "long_output": 2.50, "long_from": 100_000},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
}

RETRYABLE = (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError)


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    p = PRICES.get(model)
    if not p:
        return 0.0
    total_in = input_tokens + cache_write + cache_read
    if "long_from" in p and total_in > p["long_from"]:
        pin, pout = p["long_input"], p["long_output"]
    else:
        pin, pout = p["input"], p["output"]
    cost = input_tokens * pin + cache_write * pin * 1.25 + cache_read * pin * 0.10 + output_tokens * pout
    return cost / 1_000_000


class ClaudeProvider(ModelProvider):
    name = "api"

    def __init__(
        self,
        model: str | None = None,
        thinking: str | None = None,
        effort: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.model = model or os.getenv("SKILLDOC_API_MODEL", "claude-haiku-5-5")
        self.thinking = thinking or os.getenv("SKILLDOC_API_THINKING", "off")
        self.effort = effort or os.getenv("SKILLDOC_API_EFFORT", "low")
        self.max_retries = max_retries
        # Los reintentos se manejan aquí para poder contarlos.
        self.client = anthropic.Anthropic(timeout=timeout_s, max_retries=0)

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "model": self.model,
            "thinking": self.thinking,
            "effort": self.effort,
            "structured_output": "output_config.format json_schema",
        }

    def analyze(self, request: ModelRequest) -> ModelResult:
        result = ModelResult(provider=self.name, model=self.model, settings={**self.describe(), "max_tokens": request.max_tokens})
        params = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": request.json_schema},
            },
            "thinking": {"type": "disabled"} if self.thinking == "off" else {"type": "adaptive"},
        }

        start = time.perf_counter()
        response = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.messages.create(**params)
                break
            except anthropic.AuthenticationError:
                result.error = "La clave de la API no es válida. Revisa ANTHROPIC_API_KEY en el archivo .env."
            except anthropic.PermissionDeniedError:
                result.error = "La clave no tiene permiso para usar este modelo."
            except anthropic.NotFoundError:
                result.error = f"El modelo {self.model} no existe o no está disponible para esta cuenta."
            except anthropic.BadRequestError as exc:
                msg = str(exc.message)
                if "credit" in msg.lower() or "balance" in msg.lower():
                    result.error = "La cuenta de la API no tiene saldo suficiente."
                else:
                    result.error = f"Solicitud rechazada por la API: {msg}"
            except RETRYABLE as exc:
                if attempt < self.max_retries:
                    result.retries += 1
                    time.sleep(2 ** (attempt + 1))
                    continue
                if isinstance(exc, anthropic.APIConnectionError):
                    result.error = "No hay conexión con la API. El modo API necesita internet; usa el modo local si no hay red."
                elif isinstance(exc, anthropic.RateLimitError):
                    result.error = "La API está limitando las solicitudes. Espera un momento y vuelve a intentar."
                else:
                    result.error = "La API tuvo un error temporal. Vuelve a intentar en un momento."
            except anthropic.APIStatusError as exc:
                result.error = f"Error de la API ({exc.status_code})."
            break
        result.latency_s = round(time.perf_counter() - start, 3)

        if response is None:
            return result

        usage = response.usage
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        result.input_tokens = usage.input_tokens + cache_write + cache_read
        result.output_tokens = usage.output_tokens
        result.cost_usd = round(estimate_cost(self.model, usage.input_tokens, usage.output_tokens, cache_write, cache_read), 6)
        result.stop_reason = response.stop_reason or ""

        if response.stop_reason == "refusal":
            result.error = "El modelo se negó a responder esta solicitud."
            return result
        if response.stop_reason == "max_tokens":
            result.error = "La respuesta se cortó por el límite de tokens de salida."
            return result

        result.text = next((b.text for b in response.content if b.type == "text"), "")
        result.parsed, err = parse_json(result.text)
        if err:
            result.error = err
        return result
