# Experimento A2: el agente corrige con y sin el diagnóstico de SkillDoc Check

Fecha: 2 de noviembre de 2026. Script `eval/compare_agent.py`, datos en `eval/results/agent_handoff.csv`.

## Qué se comparó

| | A. Agente solo | B. Agente + SkillDoc Check por API | C. Agente + SkillDoc Check local |
| --- | --- | --- | --- |
| Quién diagnostica | Nadie: el agente revisa todo el proyecto por su cuenta | SkillDoc Check V4 con **Claude Haiku 5.5** (`claude-haiku-5-5`, API de Anthropic) | SkillDoc Check V4 con **Qwen3-8B** (`qwen3:8b`, Q4_K_M) en Ollama, en la Mac M3 Max, sin internet |
| Quién corrige | **Claude Code 2.1.296** con **Claude Sonnet 5.5** (`claude-sonnet-5-5`) | El mismo | El mismo |
| Qué recibe el agente | "Revisa si el README, la documentación o las skills ya no coinciden con el código y corrígelos" | Las tareas de corrección de SkillDoc Check (problema, evidencia, propuesta, verificar antes de cambiar) | Igual que B, generadas por el modelo local |
| ¿El código sale de la máquina en el diagnóstico? | — | Sí (a Anthropic) | No |

En las tres: herramientas del agente limitadas a leer y editar archivos (sin terminal), el código Python es la fuente de verdad y no se tocan archivos `.py`, una sesión por caso sobre una copia temporal. Casos: 6 de la prueba final (`nt02`, `nt03`, `nt05`, `tk02`, `tk04`, `tk05`) con 14 problemas de los 4 tipos.

## Resultado

| Medida | A. Agente solo | B. + SkillDoc por API | C. + SkillDoc local |
| --- | ---: | ---: | ---: |
| Problemas corregidos | **14 de 14** | **14 de 14** | **8 de 14** |
| Tareas entregadas al agente | — | 14 | 8 |
| Tokens del agente (Sonnet 5.5) | 260,316 | 191,048 (27 % menos) | 142,828 (45 % menos) |
| Costo del agente | 0.338 USD | 0.246 USD | 0.173 USD |
| Costo del diagnóstico | — | 0.0075 USD | 0 (corre en la máquina) |
| **Costo total** | **0.338 USD** | **0.253 USD (25 % menos)** | **0.173 USD (49 % menos)** |
| Vueltas del agente | 83 | 42 (49 % menos) | 28 (66 % menos) |
| Tiempo del agente | 138 s | 97 s | 85 s |
| Tiempo del diagnóstico | — | 47 s | 181 s |
| Tiempo total | 138 s | 144 s | 266 s |
| Archivos `.py` modificados | 0 | 0 | 0 |

## Por caso

| Caso | Problemas | A: corregidos / costo / vueltas | B: tareas / corregidos / costo total / vueltas | C: tareas / corregidos / costo / vueltas |
| --- | ---: | --- | --- | --- |
| nt02 | 2 | 2 / 0.053 / 14 | 2 / 2 / 0.041 / 6 | 2 / 2 / 0.039 / 6 |
| nt03 | 2 | 2 / 0.053 / 13 | 2 / 2 / 0.051 / 9 | 0 / 0 / 0.013 / 1 |
| nt05 | 3 | 3 / 0.053 / 11 | 3 / 3 / 0.043 / 8 | 2 / 2 / 0.034 / 6 |
| tk02 | 2 | 2 / 0.050 / 12 | 2 / 2 / 0.038 / 6 | 2 / 2 / 0.035 / 6 |
| tk04 | 2 | 2 / 0.067 / 16 | 2 / 2 / 0.038 / 5 | 0 / 0 / 0.019 / 3 |
| tk05 | 3 | 3 / 0.062 / 17 | 3 / 3 / 0.044 / 8 | 2 / 2 / 0.032 / 6 |

## Cómo se interpreta

- **B es el escenario recomendado.** El agente corrige lo mismo que solo (14 de 14) pero cuesta un 25 % menos en total, da la mitad de vueltas y no hace cambios que nadie pidió. El análisis de SkillDoc Check cuesta menos de una décima de centavo por caso.
- **C es la opción privada.** El diagnóstico corre gratis en la máquina y el código no sale a ninguna API, pero el agente solo corrige lo que el modelo local detecta: 8 de 14. Se le escapan los problemas que exigen entender el texto (el orden de la lista en `nt03`, el traslape y la redundancia parafraseados en `tk04`, la respuesta de DELETE en `nt05`, el parámetro de filtro en `tk05`). Es el mismo límite que mostró la prueba final (recall 0.59).
- **A corrige todo, pero es lo más caro** y además agrega a la documentación cosas que nadie pidió.
- **El tiempo total no mejora.** Lo que el agente ahorra, el diagnóstico lo consume (unos 8 s por caso con la API y unos 30 s en local). La ganancia es en costo, vueltas y enfoque.
- En `nt03` y `tk04` el modelo local no encontró nada, así que el agente recibió una lista vacía y no hizo cambios. En uso real, con cero hallazgos nadie llamaría al agente; esas dos sesiones costaron poco por eso.

## Límites

- 6 casos pequeños y una sola sesión por caso y condición. Evidencia preliminar.
- Claude Code protege `.claude/` en modo no interactivo, así que en las copias las skills se movieron a `skills/` (igual en las tres condiciones). La primera corrida, sin ese cambio, se invalidó.
- En repositorios grandes el agente solo tendría que explorar más; la diferencia probablemente crece, pero no se midió.
- Mide corregir los problemas de documentación y skills de estos casos, no una sesión de desarrollo completa.
