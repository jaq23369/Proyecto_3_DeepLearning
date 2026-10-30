| Métrica | api | local |
| --- | ---: | ---: |
| Modelo | claude-haiku-5-5 | qwen3:8b |
| Razonamiento previo | adaptive | adaptive |
| Casos | 26 | 26 |
| Macro-F1 | 0.92 | 0.50 |
| Precisión | 0.86 | 0.67 |
| Recall | 0.97 | 0.52 |
| F1 (micro) | 0.91 | 0.58 |
| F1 README vs código | 0.88 | 0.57 |
| F1 skill desactualizada | 0.94 | 0.71 |
| F1 traslape | 0.86 | 0.33 |
| F1 redundancia | 1.00 | 0.40 |
| Casos limpios con alerta (%) | 50 | 25 |
| Fidelidad de citas | 1.00 | 0.95 |
| Respuestas válidas (%) | 100 | 100 |
| Evidencia insuficiente (total) | 0 | 0 |
| Latencia media (s) | 6.2 | 64.2 |
| Latencia mediana (s) | 5.9 | 24.9 |
| Latencia p95 (s) | 9.8 | 277.1 |
| Tokens de entrada por caso | 7651 | 4908 |
| Tokens de salida por caso | 1233 | 943 |
| Costo total (USD) | 0.0359 | 0.0000 |
| Costo por caso (USD) | 0.00138 | 0.00000 |
| Memoria cargada (GB) / % en GPU | n/a | 6.6 / 95 % |

Corridas: api = `20261030-121703_api_V4_selected_m1api`, local = `20261030-111927_local_V4_selected_m1`

Casos donde no coinciden:
- w01: api TP 8 FP 0 FN 0; local TP 6 FP 0 FN 2
- inv03: api TP 1 FP 0 FN 0; local TP 0 FP 0 FN 1
- inv05: api TP 1 FP 0 FN 0; local TP 0 FP 0 FN 1
- inv06: api TP 1 FP 0 FN 0; local TP 0 FP 0 FN 1
- sd02: api TP 2 FP 1 FN 0; local TP 0 FP 1 FN 2
- sd03: api TP 0 FP 1 FN 1; local TP 0 FP 2 FN 1
- sd04: api TP 1 FP 1 FN 0; local TP 0 FP 1 FN 1
- lib01: api TP 0 FP 1 FN 0; local TP 0 FP 0 FN 0
- lib03: api TP 1 FP 0 FN 0; local TP 0 FP 0 FN 1
- lib04: api TP 1 FP 0 FN 0; local TP 0 FP 0 FN 1
- lib06: api TP 1 FP 0 FN 0; local TP 0 FP 2 FN 1
- lib07: api TP 1 FP 0 FN 0; local TP 0 FP 1 FN 1
- lib08: api TP 1 FP 0 FN 0; local TP 0 FP 0 FN 1
- lib10: api TP 2 FP 0 FN 0; local TP 1 FP 0 FN 1
