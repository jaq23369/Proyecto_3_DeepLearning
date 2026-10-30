---
name: skilldoc-providers
description: Add or change an LLM provider. Use when touching src/api_provider.py, src/model_provider.py or the local provider.
---

# Providers

1. Providers implement `ModelProvider.analyze(request)` from `src/model_provider.py` and return a `ModelResult`.
2. Never change the prompt inside a provider; both providers must receive the same `ModelRequest`.
3. Record tokens, latency and cost in the `ModelResult`; the API price table is `PRICES` in `src/api_provider.py`.
4. The default API model is `claude-haiku-5-5`.
