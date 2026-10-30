# Registro de experimentos

Cada corrida formal queda en `eval/results/runs.csv` y su salida completa en `eval/results/runs/<run_id>/`. Aquí se anotan los cambios, las fallas observadas y las decisiones.

## 29 de octubre de 2026, pruebas de humo con el caso w01 (dev)

Configuración: Claude Haiku 5.5 (`claude-haiku-5-5`), razonamiento apagado, esfuerzo `low`, `max_tokens` 4000, salida estructurada con el esquema común, iteración V2 (prompt v1 + reglas + validación), contexto seleccionado (todo el proyecto cabe, unos 1.2K tokens estimados de archivos).

| Corrida | Tokens entrada | Tokens salida | Costo USD | Latencia | Hallazgos del LLM que sobreviven |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 5007 | 1241 | 0.00112 | 7.0 s | campo `prediction` vs `forecast`, versión de Python, comando de pytest (falso positivo) |
| 2 | 5007 | 1362 | 0.00118 | 6.3 s | campo `prediction` vs `forecast`, comando de pytest (falso positivo), un "sin contradicción clara" |

Las reglas encontraron en las dos corridas los mismos 6 problemas (ruta `/predict` en README y skill, dos archivos inexistentes, instrucción duplicada y traslape de descripciones).

### Fallas observadas

1. Variación entre corridas. La versión de Python (3.11 en el README contra `>=3.12` en `pyproject.toml`) apareció en la corrida 1 y no en la 2. Haiku 5.5 no acepta `temperature`, así que no se puede fijar en 0. Decisión pendiente: correr cada configuración dos veces en la evaluación final o reportar la variación con una muestra.
2. Cita real pero equivocada. En la corrida 1 el hallazgo de la versión de Python citó las líneas 12-14 del README (el bloque de `pip install`) en vez de la línea 7. La cita existe, por eso la validación automática la marca como verificada, pero no sustenta el problema. Esto lo tiene que medir la revisión humana de fidelidad.
3. Falso positivo repetido. El modelo marca como conflicto que el README ejecute `pytest tests/test_api.py` y las skills `pytest tests/`. No es una contradicción.
4. El modelo a veces reporta un "hallazgo" para decir que no encontró problema (estado `insufficient_evidence`, resumen "Sin contradicción clara"). Es ruido en la interfaz.

### Corrección aplicada

- La unión de hallazgos copiaba la propuesta del modelo a un hallazgo de regla aunque fuera para otro archivo (en la corrida 1 el README terminó con una propuesta escrita para una skill). Ahora solo se copia si el archivo a editar es el mismo.

### Ideas para la siguiente iteración del prompt (solo con casos dev)

- Pedir que la cita contenga el texto exacto que demuestra el problema.
- Prohibir hallazgos cuyo contenido sea que no hay problema.
- Aclarar que diferencias de alcance (un archivo de pruebas vs toda la carpeta) no son contradicciones.

## 29 de octubre de 2026, iteraciones V0 a V4 sobre desarrollo

Casos de desarrollo de Joel: w01, inv01 a inv06 y bk01 a bk05 (12 casos, 17 problemas etiquetados, 2 casos limpios). Mismo modelo en todas (Claude Haiku 5.5), mismo contexto seleccionado y mismo esquema JSON. La puntuación de esta tabla es preliminar, con la regla de emparejamiento del README aplicada con un script rápido mientras Kevin termina `eval/score.py`.

| Iteración | Cambio respecto a la anterior | Precisión | Recall | F1 | USD por caso | Latencia media | Tokens salida |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V0 | Prompt simple (baseline) | 0.17 | 0.53 | 0.26 | 0.00172 | 11.3 s | 2758 |
| V1 | Prompt estructurado con tipos, reglas de evidencia y ejemplos | 0.58 | 0.82 | 0.68 | 0.00115 | 5.5 s | 1331 |
| V2 | + reglas deterministas y validación de citas | 0.48 | 0.88 | 0.62 | 0.00115 | 5.5 s | 1260 |
| V3 (corrida 1) | Prompt v2 con criterios para traslape, redundancia y no contradicciones | 0.80 | 0.94 | 0.86 | 0.00093 | 3.6 s | 755 |
| V3 (corrida 2) | igual | 0.94 | 0.88 | 0.91 | 0.00087 | 3.5 s | 622 |
| V4 (corrida 1) | V3 con razonamiento adaptativo del modelo | 1.00 | 1.00 | 1.00 | 0.00104 | 4.8 s | 960 |
| V4 (corrida 2) | igual | 0.94 | 1.00 | 0.97 | 0.00108 | 5.2 s | 1055 |

### Qué falló en cada paso y cómo se abordó

- V0. El prompt simple produce muchas observaciones de estilo y mejoras generales que no son contradicciones (44 falsos positivos en 12 casos) y responde lento porque escribe mucho.
- V1. Definir los cuatro tipos y exigir citas baja los falsos positivos a 10. Persisten traslapes y redundancias exagerados.
- V2. Las reglas suben el recall, pero la precisión baja. Causa encontrada, el bloque de datos verificados mostraba las rutas con barra final (`GET /products/`) y el modelo empezó a reportar que el README "omite la barra final" en 7 casos. Además el modelo marcó como redundancia instrucciones que mencionan el mismo archivo para tareas distintas, y como traslape skills de código y de documentación.
- V3. Se normalizaron las rutas del bloque de datos (sin barra final) y el prompt v2 explica cuándo hay traslape, cuándo hay redundancia y qué no es contradicción. Se quitó del prompt un ejemplo que mencionaba releases porque se parecía a una skill de la familia de prueba. Quedaron hallazgos de ruido del tipo "comportamiento documentado correctamente".
- V4. Con razonamiento adaptativo desaparecen los hallazgos de ruido y los falsos positivos de traslape. Cuesta unos 0.0002 USD más por caso y 1.5 s más.
- Variación. Haiku 5.5 no acepta temperature. Entre dos corridas iguales el F1 varió unos 5 puntos en V3 y 3 en V4. Por eso las iteraciones finales se corrieron dos veces.

### Corrección de datos

- El README base de reservas decía que las reservas canceladas "se quedan en la lista", pero no hay endpoint que liste reservas. V4 lo reportó en bk05. El modelo tenía razón, era un defecto del repo base. Se cambió la frase a "are kept with status cancelled". Es un repo de desarrollo, no de prueba.

## 29 de octubre de 2026, experimento T1 de tokens

Mismo modelo, iteración V4 y casos. Solo cambia el contexto, archivos completos (raw) o selección por relevancia con presupuesto de 10K tokens. Submuestra de 10 casos definida antes de correr, los 4 de la familia skilldoc (copia congelada de este proyecto, unos 26K tokens de archivos) y 6 casos pequeños.

| Grupo | Tokens de entrada raw | Seleccionado | Ahorro | Costo raw | Costo seleccionado |
| --- | ---: | ---: | ---: | ---: | ---: |
| 6 casos pequeños | 33,245 | 33,245 | 0 % | | |
| 4 casos skilldoc | 166,479 | 73,346 | 55.9 % | | |
| Total | 199,724 | 106,591 | 46.6 % | 0.02664 USD | 0.01771 USD |

- En repos pequeños todo cabe y la selección no recorta nada.
- En el repo grande la selección deja fuera el código menos relacionado con README y skills. Se perdió 1 de 17 problemas (sd03, el modelo por defecto en `src/api_provider.py` quedó fuera del presupuesto). Recall 1.00 con raw y 0.94 con selección.
- Falso positivo de las reglas en los 4 casos skilldoc. El README menciona `tests/test_predict.py` como ejemplo dentro de una tabla y la regla de archivos inexistentes no distingue un ejemplo de una instrucción. Se deja medido como limitación.
- La cifra describe el análisis de SkillDoc Check. No dice nada del consumo posterior de Codex o Claude Code.

### Incidente con iCloud

La carpeta del proyecto está en el Escritorio, que se sincroniza con iCloud. Al regenerar los casos borrando y recreando carpetas, iCloud creó copias de conflicto (`models 2.py`, `SKILL 3.md`, 110 archivos idénticos a los originales). La primera corrida seleccionada de T1 las incluyó y mostró redundancias falsas entre `SKILL.md` y `SKILL 3.md`. Se invalidó (movida a `eval/results/runs/_invalid/` y retirada de los CSV), se borraron las copias, el generador ahora sincroniza archivo por archivo y cada caso guarda su lista exacta de archivos. `run_eval` se niega a correr si la carpeta no coincide. Ninguna otra corrida tenía copias.

### Otros ajustes del mismo día

- Una mención sin carpeta (por ejemplo `SKILL.md`) ahora cuenta como existente si hay un archivo con ese nombre en cualquier lugar.
- El presupuesto de contexto se calcula con el texto tal como va al modelo (con números de línea y encabezados). Antes se pasaba un 15 %.
- Ninguno de los dos cambia los resultados de V0 a V4 porque esos casos caben completos y no tienen menciones sin carpeta.

### Pendiente

- La prueba final (familia notes) no se ha corrido con ningún modelo. Se corre una sola vez al final con API y local.
- Posible mejora de la selección, dar prioridad a los fragmentos con términos exactos citados por las skills (por ejemplo `claude-haiku-5-5`). No se aplica ahora para no ajustar sobre los mismos casos de T1.

## 30 de octubre de 2026, M1: Qwen3-8B local sobre los 26 casos de desarrollo

Configuración: `qwen3:8b` (Q4_K_M, digest `500a1f067a9f`) con Ollama, salida estructurada con el mismo esquema, mismo prompt v2, reglas y contexto que la API. RTX 4060 Ti de 8 GB. Contexto automático (8192 para casi todos los casos, 24576 para los 4 de `skilldoc`). Con razonamiento apagado `temperature` 0; con razonamiento, 0.6 / `top_p` 0.95 / `top_k` 20 (recomendación de Qwen). Semilla 7. Una sola corrida de cada una, sin repetir (el modelo local con `temperature` 0 es determinista, pero con razonamiento no).

| Corrida | Precisión | Recall | F1 | Macro-F1 | Casos limpios con alerta | Fidelidad de citas | Latencia media / mediana / p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Local V4 (razonamiento) | 0.67 | 0.52 | 0.58 | 0.50 | 1 de 4 | 95 % | 64.2 / 24.9 / 277 s |
| Local V3 (sin razonamiento) | 0.48 | 0.52 | 0.50 | 0.45 | 2 de 4 | 98 % | 12.0 / 9.1 / 33 s |

Tabla completa y gráfica en `eval/results/m1_local_think_vs_off.*`. El detalle de cada caso queda en `eval/results/runs/<corrida>/score.json` (no se sube).

- Todas las respuestas fueron JSON válido y ninguna se cortó. Ninguna llamada perdió contexto (se comprueba `prompt_eval_count` contra `num_ctx`).
- El razonamiento sube la precisión (de 0.48 a 0.67) sin cambiar el recall, y baja a la mitad los casos limpios con alerta. Cuesta unas 5 veces más de tiempo.
- Lo que más se pierde es lo que exige leer el significado: límites numéricos (`lib03`, `lib10`), campos renombrados (`inv03`, `lib04`), traslapes y redundancias parafraseadas (`inv05`, `inv06`, `lib07`, `lib08`). Las reglas deterministas cubren buena parte del recall; el modelo local aporta poco encima de ellas.
- Un hallazgo bien visto pero con el tipo equivocado cuenta como falso positivo y como falso negativo (`lib06`: lo reportó como `readme_code` en vez de `skill_project`).
- Los 4 casos `skilldoc` (unos 12K tokens de Qwen) tardan entre 2 y 5 minutos con contexto de 24576: la GPU de 8 GB ya no aloja todo el modelo y parte corre en CPU. Con el contexto de 8192 los casos pequeños corren 100 % en GPU (14 a 45 tokens/s según el modo).
- Los falsos positivos de `sd01` a `sd04` son la alerta de regla de `tests/test_predict.py` ya documentada en T1.
- Hallazgo de rendimiento: con `num_ctx` fijo en 16384 el modelo quedaba 80 % en GPU y el análisis de `stale_project` tardaba 137 s (67 s solo de carga); con 8192, 21 s sin razonamiento y 36 s con razonamiento. Por eso el proveedor elige el contexto por solicitud.
- Prueba con la interfaz en modo local (pruebas automatizadas de Streamlit, con red): `clean_project` en 21 s sin hallazgos y `stale_project` en 50 s con 6 hallazgos. Falta repetirla con el wifi apagado.

## 30 de octubre de 2026, API vs local sobre los 26 casos de desarrollo (V4)

Mismos casos, mismo prompt v2, reglas y esquema. API: Claude Haiku 5.5 con razonamiento adaptativo, una sola corrida. Local: la corrida M1 de arriba. Tabla y gráfica en `eval/results/m1_api_vs_local_dev.*`.

| | Precisión | Recall | F1 | Macro-F1 | Casos limpios con alerta | Fidelidad de citas | Latencia mediana | Costo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| API (Haiku 5.5) | 0.86 | 0.97 | 0.91 | 0.92 | 2 de 4 | 100 % | 5.9 s | 0.036 USD (0.0014 por caso) |
| Local (Qwen3-8B) | 0.67 | 0.52 | 0.58 | 0.50 | 1 de 4 | 95 % | 24.9 s | sin factura por solicitud |

- Los 5 falsos positivos de la API son 4 alertas de regla de `tests/test_predict.py` en `skilldoc` (limitación ya documentada) y un traslape reportado en `lib01` (caso limpio de Kevin) entre `loans-api` y `loans-tests`, que el modelo marcó como posible conflicto y las etiquetas no. Revisar con Joel si ese caso limpio es ambiguo antes de la prueba final.
- El único falso negativo de la API es `sd03` (modelo por defecto en `src/api_provider.py`, fuera del presupuesto de contexto), el mismo que ya se había perdido en T1.
- La API cuesta unos 0.0014 USD por caso y tarda unos 6 s; el modelo local no cobra por solicitud pero necesita 4 a 10 veces más tiempo y aporta mucho menos recall sobre lo que ya detectan las reglas.
- Los tokens de entrada no son comparables entre modelos (distinto tokenizador): 7651 de Claude contra 4908 de Qwen para los mismos prompts.
