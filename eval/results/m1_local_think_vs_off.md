| Métrica | local_V4 | local_V3 |
| --- | ---: | ---: |
| Modelo | qwen3:8b | qwen3:8b |
| Razonamiento previo | adaptive | off |
| Casos | 26 | 26 |
| Macro-F1 | 0.50 | 0.45 |
| Precisión | 0.67 | 0.48 |
| Recall | 0.52 | 0.52 |
| F1 (micro) | 0.58 | 0.50 |
| F1 README vs código | 0.57 | 0.47 |
| F1 skill desactualizada | 0.71 | 0.71 |
| F1 traslape | 0.33 | 0.22 |
| F1 redundancia | 0.40 | 0.40 |
| Casos limpios con alerta (%) | 25 | 50 |
| Fidelidad de citas | 0.95 | 0.98 |
| Respuestas válidas (%) | 100 | 100 |
| Evidencia insuficiente (total) | 0 | 0 |
| Latencia media (s) | 64.2 | 12.0 |
| Latencia mediana (s) | 24.9 | 9.1 |
| Latencia p95 (s) | 277.1 | 33.3 |
| Tokens de entrada por caso | 4908 | 4914 |
| Tokens de salida por caso | 943 | 271 |
| Costo total (USD) | 0.0000 | 0.0000 |
| Costo por caso (USD) | 0.00000 | 0.00000 |
| Memoria cargada (GB) / % en GPU | 6.6 / 95 % | 6.6 / 95 % |

Corridas: local_V4 = `20261030-111927_local_V4_selected_m1`, local_V3 = `20261030-114900_local_V3_selected_m1off`

Casos donde no coinciden:
- inv02: local_V4 TP 1 FP 0 FN 0; local_V3 TP 1 FP 1 FN 0
- bk01: local_V4 TP 0 FP 0 FN 0; local_V3 TP 0 FP 4 FN 0
- bk03: local_V4 TP 1 FP 0 FN 0; local_V3 TP 1 FP 3 FN 0
- bk04: local_V4 TP 1 FP 0 FN 0; local_V3 TP 1 FP 4 FN 0
- sd03: local_V4 TP 0 FP 2 FN 1; local_V3 TP 0 FP 1 FN 1
- lib06: local_V4 TP 0 FP 2 FN 1; local_V3 TP 0 FP 0 FN 1
- lib07: local_V4 TP 0 FP 1 FN 1; local_V3 TP 0 FP 0 FN 1
- lib09: local_V4 TP 1 FP 0 FN 0; local_V3 TP 1 FP 1 FN 0
