# Modelado · competición y ganador

La validación, abierta una vez, da por bueno el modelo: en la lista de 100 encuentra de media 16,33 fallos más que la regla por mes (intervalo 14,00 a 18,92) y su AUC es 0,898.

## Lo aprobado antes de entrenar

La medida principal son los fallos encontrados entre los 100 discos de más riesgo de cada mes. Es lo que mide el negocio: de los N discos de más riesgo, cuántos fallan (reglas, apartado 7). Se da por bueno si en la validación el modelo encuentra en esa lista más fallos que la regla, con el intervalo de la diferencia por encima de cero, y su AUC es 0,70 o más.

Las referencias son la regla de los cinco contadores (cuestión 010), el trivial, DummyClassifier(strategy="prior"). La preselección llegó así: en AVISO, con cada pendiente decidido por el responsable del caso: P-01, seguir con la lista de la semilla 42 (El responsable del caso, 18/11/2026, R-023).

## Qué se probó y cuánto costó

Una búsqueda por algoritmo con los mismos cinco pliegues por fecha. Cada búsqueda usa ParameterGrid o ParameterSampler de scikit-learn y los cinco pliegues por fecha, y puntúa cada bloque por trozos; no usa RandomizedSearchCV porque la muestra se toma solo en la parte que entrena de cada pliegue y el bloque medido no cabe en memoria transformado.

- regresión logística: 12 candidatos de 12 combinaciones posibles.
- bosque aleatorio: 17 candidatos de 54 combinaciones posibles.
- HistGradientBoosting: 17 candidatos de 81 combinaciones posibles.

La rejilla se amplió por el borde en: bosque aleatorio, max_features hasta 0,7000; bosque aleatorio, max_depth hasta 20; HistGradientBoosting, max_iter hasta 1000; HistGradientBoosting, learning_rate hasta 0,0125.

La búsqueda tardó 3.443 segundos.

## El desequilibrio

La regla del caso (reglas, apartado 7) entrena con todas las fotos con fallo y el 2 % de las sanas de cada mes, solo al ajustar cada pliegue; lo medido conserva la proporción real. La probabilidad del ganador se recalibra con la corrección del prior sobre el logit.
En el reajuste final, la muestra tiene una tasa de fallo de 5,15 % y la construcción, de 0,1085 %; la recalibración devuelve la probabilidad a la escala real.

## Ranking

Fallos encontrados en la lista de 100 de cada mes, media de los meses medidos, fuera de pliegue. El AUC de entrenamiento va al lado para ver el sobreajuste frente al AUC fuera de pliegue.

| Algoritmo | Lista de 100, media | Desviación entre pliegues | AUC fuera de pliegue | AUC en entrenamiento |
|---|---|---|---|---|
| HistGradientBoosting | 36,13 | 5,97 | 0,873 | 0,905 |
| bosque aleatorio | 29,37 | 5,20 | 0,863 | 0,864 |
| regresión logística | 28,20 | 6,39 | 0,856 | 0,846 |
| regla de los cinco contadores | 20,47 | 5,50 | 0,823 | — |
| trivial | 0,13 | 0,03 | 0,500 | — |

## El ganador y por qué

Gana HistGradientBoosting. Tiene la mejor media en la lista de 100 fuera de pliegue (36,13 fallos por mes); la comparación pliegue a pliegue con los otros va en «ganador_detalle».

Hiperparámetros: {"min_samples_leaf": "hoja", "max_iter": 500, "max_depth": null, "learning_rate": 0.025, "l2_regularization": 0.5}. El centro de datos se vacía (sin sitio): con él no encuentra más fallos en los 12 meses con sitio, así que se vacía.

Frente a la regla de los cinco contadores, pliegue a pliegue, supera: encuentra de media 15,67 fallos más por mes en la lista de 100, con una desviación entre pliegues de 1,13.

Falta que el responsable del caso apruebe el ganador: aprobado_por está escrito: El responsable del caso, 19/11/2026: «Sí, abre la validación», con el desvío de la probabilidad media en los bloques 1 y 2 (validación 12) aceptado como límite.

## Qué variables pesan

Importancia por permutación en el último bloque, con el modelo del pliegue 5, que no lo vio; métrica PR-AUC, 10 repeticiones sobre el 25 % de las fotos del bloque, sorteado una vez (210.874 fotos, 276 con fallo).

- suma_contadores_sin_188: 0,07548 (desviación 0,00270).
- cambio_smart_187: 0,01023 (desviación 0,00267).
- cambio_smart_197: 0,00979 (desviación 0,00045).
- smart_197_raw: 0,00936 (desviación 0,00158).
- contadores_que_avisan: 0,00411 (desviación 0,00158).
- smart_241_raw: 0,00396 (desviación 0,00052).
- smart_184_raw: 0,00391 (desviación 0,00070).
- model: 0,00309 (desviación 0,00172).
- smart_5_raw: 0,00293 (desviación 0,00011).
- smart_7_raw: 0,00231 (desviación 0,00043).

El peso de una variable dice que el modelo la usa para acertar, no que cause el fallo.

## La validación

La validación se abrió una vez, con el ganador aprobado por el responsable del caso, 19/11/2026: «Sí, abre la validación», con el desvío de la probabilidad media en los bloques 1 y 2 (validación 12) aceptado como límite. En sus 12 meses el modelo encuentra de media 16,33 fallos más que la regla en la lista de 100, con un intervalo del 95 % de 14,00 a 18,92. Su AUC es 0,898.

## El corte

El modelo no lleva un corte fijo: da una lista de los discos de más riesgo de cada mes, y su tamaño lo elige Backblaze según lo que puedan atender sus técnicos, que no consta (reglas, apartado 7, cuestión 010). Por eso se dan las listas de 20, 100, 500 y 1.000. El tamaño se puede cambiar sin reentrenar.

## ¿Se da por bueno?

Sí: frente a la regla, el intervalo va de 14,00 a 18,92, y el AUC es 0,898 frente al mínimo de 0,70. Frente al trivial, supera.

## Las tres vías de mejora

1. Mejor modelo: se probaron tres algoritmos con su búsqueda (regresión logística, 12 candidatos; bosque aleatorio, 17 candidatos; HistGradientBoosting, 17 candidatos); quedan sin probar XGBoost y los castigos L1 y mezcla de la logística, que el responsable del caso dejó fuera (reglas, apartado 7).
2. Crear variables con los datos que ya hay: las cuatro variables nuevas candidatas de la matriz (P-04), no se crean en esta petición; se crean si el modelo no supera a la regla, con la decisión de el responsable del caso y antes de abrir la validación (reglas, apartado 7).
3. Pedir más información: las lecturas SMART diarias, no solo la foto mensual, ver los fallos que avisan entre una foto y la siguiente (lo tiene Backblaze).

## Validaciones

- Ninguna cifra de comparación sale de las filas del ajuste: en verde.
- Cada modelo y cada muestra llevan la semilla 42: en verde.
- La validación no se abrió o se abrió una sola vez, con el ganador aprobado: en verde.
- Las medidas se calcularon con la probabilidad: en verde.
- Las columnas del ganador son las de la preselección: en verde.
- La probabilidad se recalibró, porque se entrenó con una muestra: en verde.
- Lo que cita el JSON existe: en verde.
- El mismo ajuste, repetido, da las mismas cifras: en verde.
- Ningún identificador ni variable posterior a la decisión entra: en verde.
- El script no lleva ninguna validación escrita con un sí: en verde.
- El canario: con el objetivo barajado cae al trivial y con la fuga sube a casi todo: en verde.
- La probabilidad media recalibrada de cada bloque queda cerca de su tasa: EN ROJO.
- Ningún entrenamiento usa una foto con el horizonte abierto el día que empieza lo que mide: en verde.

## Parámetros usados

- Semilla: 42. Origen: parametros.md de las dos métodos.
- Pliegues: cinco bloques de tres meses, de 2023-04 a 2024-06, por fecha y sin barajar. Origen: método §3; petición 21.
- Muestra de cada entrenamiento: todas las fotos con fallo y el 2 % de las sanas de cada mes, solo con el horizonte cerrado. Origen: reglas, apartado 7.
- Medida de la búsqueda: media de los fallos en la lista de 100 de los meses del bloque. Origen: planteamientos 1.C; petición 21.
- Logística: LogisticRegression(solver="lbfgs", l1_ratio=0, max_iter=5000, random_state=42), C en logspace(-3, 2, 12). Origen: reglas, apartado 7, el responsable del caso, 18/11/2026.
- Bosque: RandomForestClassifier(n_jobs=-1, random_state=42), 15 candidatos de ParameterSampler(random_state=42). Origen: algoritmos.md; reglas, apartado 7.
- HistGradientBoosting: early_stopping=False, max_iter en 100, 200 y 500, categóricas nativas, 15 candidatos. Origen: algoritmos.md, con fecha; reglas, apartado 7.
- Hoja: max(20, 1 % de las filas que entrenan en el pliegue). Origen: parametros.md.
- Extensión por el borde: hasta 2 rondas; se queda el valor nuevo si mejora pliegue a pliegue. Origen: método §5.
- Empate: la media de las diferencias en los cinco pliegues no pasa de su desviación típica (con n − 1). Origen: método §6.
- Sitio: datacenter entra solo si con él la lista de 100 encuentra más fallos en cada uno de los 12 meses de 2023-07 a 2024-06. Origen: guion §3; petición 21.
- Permutación: average_precision, 10 repeticiones sobre el 25 % de las fotos del bloque 5, sorteado una vez con la semilla 42. Origen: método §7; parametros.md; la fracción, criterio del script por el tiempo.
- Canario: barajado: como mucho el trivial más tres desviaciones de Poisson y un fallo; fuga: el 90 % de lo que cabe en la lista. Origen: método §9, validación 11; los márgenes, criterio del script.
- Tolerancia de la probabilidad media: 20 % relativo. Origen: petición 21, validación 12.
- Intervalo: 1000 remuestreos de los 12 meses, semilla 42, percentiles 2,5 y 97,5. Origen: método §8; petición 21.

Los apartados del manual aplicados:

- 20.3 y 31.6: validación cruzada temporal, con bloques de meses enteros y sin barajar, porque el modelo se usa hacia adelante y barajar mezclaría meses.
- 32.6 y 32.7: rejilla en la logística, que solo busca C, y búsqueda aleatoria en los árboles, una por algoritmo.
- 37.4 y 37.8: submuestreo de las sanas solo al entrenar y recalibración por la corrección del prior, porque la probabilidad se usa para esperar fallos.
- 21.1 y 21.8: todo con la probabilidad; AUC y PR-AUC del mes al lado de la lista de 100, que es la medida del negocio.
- 19.3: la distancia entre entrenamiento y fuera de pliegue, en AUC, para ver el sobreajuste.
- 5.1: las tres vías de mejora si el modelo no supera a la regla.
- 4.6 y 5.3: el intervalo de la diferencia remuestreando meses, que es la unidad de la medida.

## Datos personales

Los datos son de discos: serial_number identifica un disco, no a una persona (reglas, apartado 9), y el modelo no lo lee. No usa ni deja ninguna columna de datos personales. No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección porque no hacía falta.

## Límites

- El modelo vale para los discos de datos de Backblaze, con una foto al mes, en los periodos de construcción y validación; si cambian los modelos de disco o los centros, su rendimiento puede caer (deriva).
- Detecta asociaciones, no causas: que un contador pese no dice que cause el fallo.
- No ve los fallos que llegan sin aviso en la última foto mensual (reglas, apartado 7).
- La preselección de la logística se hizo una vez y entra fija en cada pliegue: su validación cruzada sale algo optimista; cuánto, NO SE PUEDE SABER sin medirlo.
- Las cuatro variables nuevas candidatas de la matriz (P-04) no se crearon en esta petición.
