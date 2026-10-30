"""Proveedor local: Qwen3-8B con Ollama.

Recibe exactamente el mismo ModelRequest que el proveedor de la API (mismo
prompt, contexto y esquema JSON). Lo único propio de este proveedor es cómo se
llama a Ollama: el esquema va en el parámetro format y el razonamiento previo
se controla con think.

Parámetros de generación: con razonamiento apagado se usa temperature 0 (lo
menos aleatorio). Con razonamiento Qwen recomienda no usar decodificación
voraz porque puede entrar en bucles, así que se usan sus valores sugeridos
(temperature 0.6, top_p 0.95, top_k 20). La semilla es fija en los dos casos.
Todo queda en describe() para registrarlo en cada corrida.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from src.model_provider import ModelProvider, ModelRequest, ModelResult, parse_json

load_dotenv()

# Contexto que se le pide a Ollama. El prompt completo ronda 1.5K a 12K tokens
# (de Qwen) y la salida, con razonamiento, hasta 4K más. Si num_ctx no alcanza,
# Ollama recorta el inicio del prompt en silencio, por eso después de cada
# llamada se compara prompt_eval_count con el contexto usado.
#
# Con num_ctx automático se elige el escalón más chico que alcance. Importa por
# la memoria: en una GPU de 8 GB, qwen3:8b con 8192 de contexto cabe completo
# en la GPU, con 12288 queda en 87 % y con 16384 en 80 %, y lo que cae a CPU
# hace la inferencia mucho más lenta. Fijar SKILLDOC_LOCAL_NUM_CTX desactiva
# la selección automática.
CTX_STEPS = (8192, 12288, 16384, 24576)
CHARS_PER_TOKEN = 3.0  # estimación conservadora para texto con código y español
SEED = 7


class OllamaProvider(ModelProvider):
    name = "local"

    def __init__(
        self,
        model: str | None = None,
        thinking: str | None = None,
        num_ctx: int | None = None,
        host: str | None = None,
        timeout_s: float = 600.0,
        keep_alive: str = "30m",
    ) -> None:
        self.model = model or os.getenv("SKILLDOC_LOCAL_MODEL", "qwen3:8b")
        self.thinking = thinking or os.getenv("SKILLDOC_LOCAL_THINKING", "off")
        fixed = num_ctx or os.getenv("SKILLDOC_LOCAL_NUM_CTX")
        self.num_ctx: int | None = int(fixed) if fixed else None  # None = automático
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self.timeout_s = timeout_s
        self.keep_alive = keep_alive
        self._model_info: dict[str, Any] | None = None

    # ------------------------------------------------------------------ config
    def _options(self) -> dict[str, Any]:
        if self.thinking == "off":
            return {"temperature": 0, "seed": SEED}
        return {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "seed": SEED}

    def _ctx_for(self, request: ModelRequest) -> int:
        """Contexto para esta solicitud: el fijado, o el escalón más chico que alcance."""
        if self.num_ctx:
            return self.num_ctx
        need = int((len(request.system) + len(request.user)) / CHARS_PER_TOKEN) + request.max_tokens + 256
        return next((c for c in CTX_STEPS if c >= need), CTX_STEPS[-1])

    def _lookup_model(self) -> dict[str, Any]:
        """Digest, tamaño y cuantización del modelo descargado (vacío si Ollama no responde)."""
        if self._model_info is not None:
            return self._model_info
        info: dict[str, Any] = {}
        try:
            show = requests.post(f"{self.host}/api/show", json={"model": self.model}, timeout=10)
            if show.ok:
                details = show.json().get("details", {})
                info["parameter_size"] = details.get("parameter_size", "")
                info["quantization"] = details.get("quantization_level", "")
                info["family"] = details.get("family", "")
            tags = requests.get(f"{self.host}/api/tags", timeout=10)
            if tags.ok:
                for m in tags.json().get("models", []):
                    if m.get("name") == self.model or m.get("model") == self.model:
                        info["digest"] = m.get("digest", "")[:12]
                        info["size_gb"] = round(m.get("size", 0) / 1e9, 2)
            if info:
                self._model_info = info  # solo se guarda si Ollama respondió
        except requests.RequestException:
            pass
        return info

    def describe(self) -> dict[str, Any]:
        info = self._lookup_model()
        return {
            "provider": self.name,
            "model": self.model,
            "digest": info.get("digest", ""),
            "parameter_size": info.get("parameter_size", ""),
            "quantization": info.get("quantization", ""),
            "num_ctx": self.num_ctx or "auto (" + "/".join(str(c) for c in CTX_STEPS) + ")",
            "think": self.thinking != "off",
            "thinking": self.thinking,
            "options": self._options(),
            "structured_output": "format json_schema",
            "host": self.host,
        }

    # --------------------------------------------------------------- inference
    def _resource_use(self) -> dict[str, Any]:
        """Memoria que ocupa el modelo cargado (para el informe de recursos)."""
        try:
            ps = requests.get(f"{self.host}/api/ps", timeout=5).json()
            for m in ps.get("models", []):
                if m.get("name") == self.model or m.get("model") == self.model:
                    size = m.get("size", 0)
                    vram = m.get("size_vram", 0)
                    return {
                        "loaded_gb": round(size / 1e9, 2),
                        "gpu_gb": round(vram / 1e9, 2),
                        "gpu_share": round(vram / size, 2) if size else 0,
                        "context_length": m.get("context_length", 0),
                    }
        except (requests.RequestException, ValueError):
            pass
        return {}

    def analyze(self, request: ModelRequest) -> ModelResult:
        ctx = self._ctx_for(request)
        settings = {**self.describe(), "max_tokens": request.max_tokens, "num_ctx_used": ctx}
        result = ModelResult(provider=self.name, model=self.model, settings=settings)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "format": request.json_schema,
            "think": self.thinking != "off",
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {**self._options(), "num_ctx": ctx, "num_predict": request.max_tokens},
        }

        start = time.perf_counter()
        try:
            resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout_s)
        except requests.ConnectionError:
            result.error = (
                "Ollama no está corriendo. Ábrelo (o ejecuta `ollama serve` en una terminal) y vuelve a intentar."
            )
        except requests.Timeout:
            result.error = f"El modelo local no respondió en {self.timeout_s:.0f} s."
        except requests.RequestException as exc:
            result.error = f"No se pudo hablar con Ollama: {exc}"
        result.latency_s = round(time.perf_counter() - start, 3)
        if result.error:
            return result

        if resp.status_code == 404:
            result.error = f"El modelo {self.model} no está descargado. Ejecuta `ollama pull {self.model}` con internet."
            return result
        if not resp.ok:
            try:
                detail = resp.json().get("error", resp.text)
            except ValueError:
                detail = resp.text
            result.error = f"Ollama respondió con error ({resp.status_code}): {str(detail)[:200]}"
            return result

        data = resp.json()
        result.input_tokens = int(data.get("prompt_eval_count", 0) or 0)
        result.output_tokens = int(data.get("eval_count", 0) or 0)
        result.cost_usd = 0.0
        result.stop_reason = data.get("done_reason", "") or ""
        message = data.get("message", {})
        result.text = message.get("content", "") or ""
        total_s = (data.get("total_duration", 0) or 0) / 1e9
        load_s = (data.get("load_duration", 0) or 0) / 1e9
        result.settings.update(
            {
                "total_duration_s": round(total_s, 3),
                "load_duration_s": round(load_s, 3),
                "eval_duration_s": round((data.get("eval_duration", 0) or 0) / 1e9, 3),
                "thinking_chars": len(message.get("thinking", "") or ""),
                **self._resource_use(),
            }
        )

        # Si el prompt no cupo, Ollama lo recortó en silencio.
        if result.input_tokens >= ctx - 8:
            result.error = (
                f"El prompt ({result.input_tokens} tokens) no cupo en el contexto de {ctx} tokens "
                "y Ollama lo recortó. Sube SKILLDOC_LOCAL_NUM_CTX o reduce el contexto."
            )
            return result
        if result.stop_reason == "length":
            result.error = "La respuesta se cortó por el límite de tokens de salida."
            return result

        result.parsed, err = parse_json(result.text)
        if err:
            result.error = err
        return result
