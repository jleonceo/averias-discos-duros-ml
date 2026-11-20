# Preparación para el modelo · el preprocesador

Los tres preprocesadores de la matriz aprobada están construidos y pasan las diez validaciones. Se ajustaron una sola vez, solo para comprobarlos, con la muestra de partida de entrenamiento, y la validación se transformó sin leer su objetivo.

La muestra de ajuste tiene 232.243 filas: los 11.962 fallos y 220.281 sanas, el 2 % de cada mes.

Lo que tarda y lo que deja cada familia:

- **Regresión logística:** ajuste en 3,8 s y 496 columnas de salida; transformar la validación, 12,8 s.
- **Bosque aleatorio:** ajuste en 0,5 s y 97 columnas de salida; transformar la validación, 5,5 s.
- **HistGradientBoosting:** ajuste en 0,5 s y 64 columnas de salida; transformar la validación, 4,6 s.

## Partición

Partición por fecha, la de informes/particion.json: Por fecha, como manda reglas-negocio §7 (El responsable del caso, 17/11/2026): el modelo se usará hacia adelante, cada mes con las fotos nuevas, así que la validación es el periodo más reciente, del 01/07/2024 al 30/06/2025, y la construcción va del 01/01/2020 al 30/06/2024. Un disco sigue en servicio de una parte a la otra, como seguirá en producción: no se parte por disco.

- **Entrenamiento:** 11.026.052 fotos, con un 0,1085 % que falla en 30 días.
- **Validacion:** 3.578.809 fotos, con un 0,1203 % que falla en 30 días.

## Desequilibrio de clases

En entrenamiento fallan en 30 días 11.962 de las 11.026.052 fotos. Por cada foto de fallo hay 920,76 sanas.

- **Seagate:** 8.163 fallos en 5.653.315 fotos, el 0,1444 %.
- **Toshiba:** 1.955 fallos en 2.407.073 fotos, el 0,0812 %.
- **HGST:** 1.566 fallos en 2.114.301 fotos, el 0,0741 %.
- **WDC:** 278 fallos en 851.363 fotos, el 0,0327 %.

En las 54 fotos mensuales, el mes con menos fallos fue el 2020-06-01, con 64. El que más, el 2023-04-01, con 559; la mediana es 214,5.

Se trata solo al entrenar, con la muestra de partida, y la probabilidad se recalibra después (reglas, apartado 7).

## Matriz de transformaciones

La matriz la aprobó el responsable del caso el 2026-11-18. Sus decisiones:

- **P-01:** aprueba la matriz tal como la propuso la petición 20 («Sí, siguiente pregunta»).
- **P-04:** las cuatro variables nuevas candidatas no se crean ahora. Se prueban primero si el modelo no supera a la
- **P-05:** seis variables que repetían a otra salen de la matriz (smart_190_raw, copia de smart_194_raw, y cinco normalizados que son función exacta de su bruto: 183, 184, 187, 189 y 222), y smart_197_normalized entra solo en los árboles («arréglalo y haz lo que tengas que hacer», una nota del caso).
- **P-02:** las 2.539 fotos sin lectura SMART van, en la logística, al tramo de referencia de cada variable.
- **P-03:** un modelo de disco que no estaba en entrenamiento va a «otras».

Cómo quedó cada numérica en la logística tras el ajuste:

| Variable | Tramos | Columnas | Vacío |
|---|---|---|---|
| capacidad_tb | 7 | 6 | en la referencia |
| garantia_anos | 3 | 3 | tramo propio |
| smart_5_raw | 10 | 9 | en la referencia |
| smart_187_raw | 11 | 11 | tramo propio |
| smart_197_raw | 9 | 9 | tramo propio |
| smart_198_raw | 8 | 7 | en la referencia |
| smart_194_raw | 10 | 9 | en la referencia |
| smart_199_raw | 8 | 7 | en la referencia |
| smart_12_raw | 13 | 12 | en la referencia |
| smart_192_raw | 12 | 11 | en la referencia |
| smart_1_raw | 10 | 9 | en la referencia |
| smart_7_raw | 10 | 9 | en la referencia |
| edad_anos | 10 | 9 | en la referencia |
| contadores_que_avisan | 6 | 5 | en la referencia |
| suma_contadores_sin_188 | 10 | 9 | en la referencia |
| smart_188_no_cero | 2 | 2 | tramo propio |
| cambio_smart_5 | 11 | 11 | tramo propio |
| cambio_smart_187 | 9 | 9 | tramo propio |
| cambio_smart_197 | 11 | 11 | tramo propio |
| cambio_smart_198 | 8 | 7 | en la referencia |
| meses_desde_foto_anterior | 2 | 2 | tramo propio |
| smart_1_normalized | 17 | 16 | en la referencia |
| smart_2_normalized | 11 | 11 | tramo propio |
| smart_2_raw | 13 | 12 | en la referencia |
| smart_3_normalized | 20 | 19 | en la referencia |
| smart_3_raw | 11 | 10 | en la referencia |
| smart_4_raw | 10 | 9 | en la referencia |
| smart_5_normalized | 9 | 8 | en la referencia |
| smart_7_normalized | 10 | 9 | en la referencia |
| smart_8_normalized | 8 | 7 | en la referencia |
| smart_8_raw | 7 | 6 | en la referencia |
| smart_9_normalized | 10 | 9 | en la referencia |
| smart_22_normalized | 2 | 2 | tramo propio |
| smart_22_raw | 3 | 2 | en la referencia |
| smart_24_normalized | 1 | 1 | tramo propio |
| smart_90_raw | 1 | 1 | tramo propio |
| smart_183_raw | 12 | 12 | tramo propio |
| smart_184_raw | 1 | 1 | tramo propio |
| smart_189_raw | 8 | 8 | tramo propio |
| smart_191_normalized | 11 | 11 | tramo propio |
| smart_191_raw | 11 | 10 | en la referencia |
| smart_192_normalized | 3 | 2 | en la referencia |
| smart_193_normalized | 11 | 10 | en la referencia |
| smart_193_raw | 10 | 9 | en la referencia |
| smart_194_normalized | 21 | 20 | en la referencia |
| smart_195_normalized | 10 | 10 | tramo propio |
| smart_195_raw | 10 | 9 | en la referencia |
| smart_196_normalized | 2 | 2 | tramo propio |
| smart_196_raw | 9 | 8 | en la referencia |
| smart_198_normalized | 2 | 1 | en la referencia |
| smart_199_normalized | 2 | 1 | en la referencia |
| smart_200_normalized | 1 | 1 | tramo propio |
| smart_220_raw | 10 | 10 | tramo propio |
| smart_222_raw | 10 | 9 | en la referencia |
| smart_223_raw | 1 | 1 | tramo propio |
| smart_226_raw | 10 | 9 | en la referencia |
| smart_240_raw | 11 | 11 | tramo propio |
| smart_241_raw | 10 | 10 | tramo propio |
| smart_242_raw | 10 | 9 | en la referencia |

Las referencias de las nominales en la logística: model, TOSHIBA MG07ACA14TA; fabricante, Seagate; datacenter, sin dato.

## Variables que no entran

De las 144 columnas de la tabla entran 64; no entran 71, cada una con su motivo en la matriz, y 9 quedan fuera desde el principio.

- **No entran:** smart_188_raw, edad_de_horas, smart_4_normalized, smart_9_raw, smart_10_normalized, smart_10_raw, smart_11_normalized, smart_11_raw, smart_12_normalized, smart_13_normalized, smart_13_raw, smart_16_raw, smart_17_raw, smart_27_raw, smart_165_raw, smart_166_raw, smart_167_raw, smart_168_raw, smart_169_raw, smart_170_normalized, smart_170_raw, smart_171_raw, smart_172_normalized, smart_172_raw, smart_173_normalized, smart_173_raw, smart_174_raw, smart_177_normalized, smart_177_raw, smart_179_raw, smart_180_normalized, smart_180_raw, smart_181_raw, smart_188_normalized, smart_190_normalized, smart_200_raw, smart_201_raw, smart_202_normalized, smart_202_raw, smart_206_raw, smart_211_raw, smart_212_raw, smart_218_raw, smart_220_normalized, smart_223_normalized, smart_225_normalized, smart_225_raw, smart_230_normalized, smart_230_raw, smart_231_raw, smart_232_raw, smart_233_raw, smart_234_raw, smart_235_normalized, smart_235_raw, smart_240_normalized, smart_241_normalized, smart_242_normalized, smart_244_normalized, smart_245_normalized, smart_245_raw, smart_246_raw, smart_247_raw, smart_248_raw, smart_254_normalized, smart_190_raw, smart_183_normalized, smart_184_normalized, smart_187_normalized, smart_189_normalized, smart_222_normalized.
- **Fuera:** serial_number, fecha, periodo, horizonte_hasta, falla_30d, capacity_bytes, vault_id, pod_id, pod_slot_num.
- **Solo en los árboles:** avisa, porque en la logística es la suma de los tramos de contadores_que_avisan.

## Validaciones

- **Las filas de entrada y de salida coinciden en cada parte:** en verde (regresión logística, sí; bosque aleatorio, sí; HistGradientBoosting, sí).
- **Ni el objetivo ni su horizonte salen:** en verde (regresión logística, sí; bosque aleatorio, sí; HistGradientBoosting, sí).
- **No queda la original de ninguna variable transformada:** en verde (regresión logística, sí; bosque aleatorio, sí; HistGradientBoosting, sí).
- **Solo tienen vacíos las columnas en que la matriz los deja:** en verde (regresión logística, sí; bosque aleatorio, sí; HistGradientBoosting, sí).
- **Los nombres de salida son únicos:** en verde (regresión logística, sí; bosque aleatorio, sí; HistGradientBoosting, sí).
- **En la logística, ninguna columna de una variable es combinación de las demás y no hay dos iguales:** en verde (regresión logística, sí).
- **Las columnas de salida son las que espera la matriz, en número y en nombre:** en verde (regresión logística, sí; bosque aleatorio, sí; HistGradientBoosting, sí).
- **«sin dato» y «otras» no existen ya en entrenamiento:** en verde.
- **No hay ningún escalador y las columnas 0/1 salen en 0 y 1:** en verde (regresión logística, sí; bosque aleatorio, sí; HistGradientBoosting, sí).
- **Cada columna de la tabla está en la matriz o fuera, y las listas del script son las de la matriz:** en verde.

En validación hay 3 modelos de disco que no salen en entrenamiento, con 19.757 fotos: van a «otras», como fija la matriz.

## Parámetros usados

- **Semilla:** 42. Origen: parametros.md; sortea la muestra de partida.
- **Muestra de partida:** todos los fallos y el 2 % de las sanas de cada mes. Origen: reglas, apartado 7.
- **Mínimo por tramo y por categoría:** 30 fotos, 20 fallos y 20 sanas. Origen: parametros.md; ficha de la logística §4.2 y §4.3.
- **Tramos:** el 0 y cada valor con al menos el 10 % aparte; hasta 3 trozos por debajo de 0 y 10 por encima. Origen: matriz aprobada, criterio «tramos».
- **Relleno categórico:** sin dato. Origen: parametros.md y matriz (datacenter).
- **Etiqueta de las raras:** otras. Origen: ficha de la logística §4.3.
- **Escalado:** ninguno. Origen: matriz aprobada, en las tres familias.
- **Sobrante del ColumnTransformer:** drop. Origen: parametros.md.

Los apartados del manual aplicados:

- 39.3 a 39.5, pipelines: cada preprocesador es un ColumnTransformer dentro de un Pipeline, sin ajustar; lo ajusta aprendizaje-automatico con el modelo, dentro de cada pliegue.
- 35.7, discretización: los tramos se aprenden en el ajuste con el mínimo de casos, y lo que queda fuera del rango del entrenamiento cae en el tramo del borde.
- 35.2 y 35.3: una columna por categoría menos la de referencia en la logística, todas en el bosque y código ordinal para las categóricas nativas de HistGradientBoosting.
- 35.12: ningún escalador, porque la logística solo recibe columnas 0 y 1 y los árboles cortan por orden.
- 20.8, fugas: el ajuste usa solo entrenamiento y la validación se transforma sin leer su objetivo.

## Datos personales

Ninguno: los datos son de discos y serial_number identifica un disco, no a una persona (reglas, apartado 9); el preprocesador no lo usa. No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección porque no hacía falta.

## Límites

- El ajuste de este script es solo para comprobar: no se guarda. Lo ajusta aprendizaje-automatico con el modelo, dentro de cada pliegue, y los tramos y las categorías pueden cambiar con cada muestra.
- Las piezas propias (Tramos, AgruparRaras, ColumnasMenosReferencia) viven en este script: quien guarde el Pipeline con joblib tiene que poder importarlas al cargarlo.
- En la logística, fabricante entra en dos piezas: como nominal y como clave de los tramos de smart_1_raw y smart_7_raw, que solo se aprenden con Seagate. No sale dos veces.
- capacidad_tb, fabricante y garantia_anos salen del modelo de disco: en la logística pueden ser en parte combinación de las columnas de model; la validación 6 mira cada variable por separado y la preselección elige entre ellas (matriz).
