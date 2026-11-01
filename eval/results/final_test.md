| Métrica | api | local | baseline |
| --- | ---: | ---: | ---: |
| Modelo | claude-haiku-5-5 | qwen3:8b | claude-haiku-5-5 |
| Razonamiento previo | adaptive | adaptive | off |
| Casos | 10 | 10 | 10 |
| Macro-F1 | 1.00 | 0.69 | 0.39 |
| Precisión | 1.00 | 0.83 | 0.29 |
| Recall | 1.00 | 0.59 | 0.71 |
| F1 (micro) | 1.00 | 0.69 | 0.41 |
| F1 README vs código | 1.00 | 0.67 | 0.58 |
| F1 skill desactualizada | 1.00 | 0.75 | 0.25 |
| F1 traslape | 1.00 | 0.67 | 0.57 |
| F1 redundancia | 1.00 | 0.67 | 0.17 |
| Casos limpios con alerta (%) | 0 | 0 | 100 |
| Fidelidad de citas | 1.00 | 1.00 | 0.99 |
| Respuestas válidas (%) | 100 | 100 | 100 |
| Evidencia insuficiente (total) | 0 | 0 | 24 |
| Latencia media (s) | 5.3 | 31.5 | 10.1 |
| Latencia mediana (s) | 5.0 | 31.4 | 8.8 |
| Latencia p95 (s) | 8.1 | 46.1 | 14.5 |
| Tokens de entrada por caso | 5676 | 3357 | 3502 |
| Tokens de salida por caso | 1143 | 1050 | 2532 |
| Costo total (USD) | 0.0114 | 0.0000 | 0.0162 |
| Costo por caso (USD) | 0.00114 | 0.00000 | 0.00162 |
| Memoria cargada (GB) / % en GPU | n/a | 5.4 / 100 % | n/a |

Corridas: api = `20261031-221455_api_V4_selected_final`, local = `20261031-221753_local_V4_selected_final`, baseline = `20261031-221549_api_V0_selected_final`

Casos donde no coinciden:
- nt01: api TP 0 FP 0 FN 0; local TP 0 FP 0 FN 0; baseline TP 0 FP 4 FN 0
- nt02: api TP 2 FP 0 FN 0; local TP 2 FP 0 FN 0; baseline TP 2 FP 1 FN 0
- nt03: api TP 2 FP 0 FN 0; local TP 0 FP 0 FN 2; baseline TP 1 FP 4 FN 1
- nt04: api TP 2 FP 0 FN 0; local TP 2 FP 0 FN 0; baseline TP 1 FP 1 FN 1
- nt05: api TP 3 FP 0 FN 0; local TP 2 FP 0 FN 1; baseline TP 1 FP 2 FN 2
- tk01: api TP 0 FP 0 FN 0; local TP 0 FP 0 FN 0; baseline TP 0 FP 6 FN 0
- tk02: api TP 2 FP 0 FN 0; local TP 2 FP 0 FN 0; baseline TP 2 FP 2 FN 0
- tk03: api TP 1 FP 0 FN 0; local TP 0 FP 2 FN 1; baseline TP 1 FP 3 FN 0
- tk04: api TP 2 FP 0 FN 0; local TP 0 FP 0 FN 2; baseline TP 2 FP 4 FN 0
- tk05: api TP 3 FP 0 FN 0; local TP 2 FP 0 FN 1; baseline TP 2 FP 3 FN 1
