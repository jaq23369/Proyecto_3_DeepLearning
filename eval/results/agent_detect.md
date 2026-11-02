# Experimento D1: revisar con Claude Code contra revisar con SkillDoc Check

Fecha: 2 de noviembre de 2026. Script `eval/compare_agent_detect.py`, datos en `eval/results/agent_detect.csv`.

Los 10 casos de la prueba final (17 problemas y 2 proyectos limpios). Ninguno de los dos cambia archivos: solo revisan y listan los problemas. Las respuestas se puntúan con las mismas etiquetas y la misma regla de emparejamiento.

| | Claude Code revisando | SkillDoc Check por API | SkillDoc Check local |
| --- | --- | --- | --- |
| Herramienta | Claude Code 2.1.296, solo lectura (Read, Glob, Grep) | Pipeline completo, iteración V4 | Pipeline completo, iteración V4 |
| Modelo | Claude Sonnet 5.5 | Claude Haiku 5.5 | Qwen3-8B (Q4_K_M) en Ollama |
| Qué recibe | La descripción de los 4 tipos de problema y el formato de respuesta; explora el proyecto con sus herramientas | Reglas + archivos numerados + prompt v2 | Igual que por API |

## Resultado (10 casos)

| Medida | Claude Code revisando | SkillDoc Check por API | SkillDoc Check local |
| --- | ---: | ---: | ---: |
| Problemas encontrados | 16 de 17 | **17 de 17** | 10 de 17 |
| Falsas alarmas | 0 | 0 | 2 |
| F1 | 0.97 | **1.00** | 0.69 |
| Proyectos limpios con alerta | 0 de 2 | 0 de 2 | 0 de 2 |
| Citas que existen de verdad | 29 de 29 | 100 % | 100 % |
| **Costo total** | **0.412 USD** | **0.011 USD** | 0 (sin factura) |
| Costo por revisión | 0.041 USD | 0.0011 USD | 0 |
| Tokens procesados | 242,651 | 68,184 | 44,069 |
| Vueltas del modelo | 111 (11 por revisión) | 10 (1 por revisión) | 10 (1 por revisión) |
| Tiempo medio por revisión | 13.8 s | 5.3 s | 31.5 s |

## Cómo se interpreta

- **Misma calidad, 36 veces más barato.** Claude Code revisando encuentra casi lo mismo (F1 0.97 contra 1.00), pero cada revisión cuesta 0.041 USD contra 0.0011 de SkillDoc Check.
- **2.6 veces más rápido y una sola llamada.** Claude Code da unas 11 vueltas por revisión (abre archivos uno por uno y vuelve a enviar la conversación en cada vuelta); SkillDoc Check resuelve lo comprobable con reglas y hace una sola llamada al modelo con los archivos ya numerados.
- **Los tokens no son del mismo modelo** (Sonnet contra Haiku, tokenizadores distintos), por eso la comparación justa es el costo.
- **Lo que SkillDoc Check agrega aparte del precio:** citas verificadas automáticamente contra los archivos, estados de certeza, formato constante, tareas listas para el agente y la opción local sin internet.
- **SkillDoc local** es gratis y privado, pero encuentra 10 de 17 y tarda más.

## Límites

- Una sola corrida por caso. Claude Code no deja fijar la temperatura, igual que la API.
- Se le dio a Claude Code la misma descripción de los 4 tipos de problema que usa SkillDoc Check y un formato de respuesta, para poder puntuarlo. Un usuario real le daría una instrucción más vaga, así que esto favorece a Claude Code.
- Se probó con Sonnet 5.5. Con un modelo más grande (Opus) costaría más. Codex no se probó.
- Casos pequeños: en repositorios grandes Claude Code tendría que abrir más archivos.
