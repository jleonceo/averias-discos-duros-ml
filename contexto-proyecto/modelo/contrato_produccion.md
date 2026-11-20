---
titulo: Contrato de producción del caso 68 · qué pasos llevan cada foto de disco desde el dato en bruto hasta la probabilidad de fallo
estado: aprobado por Juan, 19/11/2026: «Sí, con el arreglo»
fecha_documento: 2026-11-19
dueno: Juan (aprueba) · Claude (redacta)
fuente: informes/modelado.json; contexto-proyecto/modelo/registro-transformaciones.md; contexto-proyecto/negocio/reglas-transformacion.md; contexto-proyecto/modelo/matriz_transformaciones.md; generado por scripts/18_contrato_produccion.py
---

# Contrato de producción

Este contrato fija qué hace producción con cada foto mensual de un disco para darle su probabilidad de fallo a 30 días con el modelo aprobado, un HistGradientBoostingClassifier. Cada columna que entra al modelo tiene su cadena de pasos desde el dato en bruto, y cada paso, su clase. Con él aprobado se escribe el código de producción; sin aprobar, no.

## Lo que se aprueba

- **El modelo:** el ganador de la validación, con su receta fija; usa 63 columnas y su preprocesador lee 64, porque lee también datacenter y lo vacía.
- **Las finalistas:** 68 variables: las 64 que lee el preprocesador, el identificador (serial_number y fecha), el objetivo (falla_30d) y su horizonte (horizonte_hasta).
- **Los pasos:** 25, de ellos 3 quitan filas, 13 no aprenden, 5 necesitan otras filas y 4 aprenden.
- **El corte:** las listas de 20, 100, 500 y 1.000 discos de más riesgo de cada foto mensual, con la de 100 como principal.

## El identificador y el objetivo

Cada fila es una foto: un disco (serial_number) el día de su foto mensual (fecha). Al ejecutar sale una fila por cada fila de entrada, en el mismo orden y con su identificador.

El objetivo es falla_30d: 1 si el disco tiene un fallo en los 30 días siguientes a la foto (reglas §7, CP-003 y CP-004). Solo lo usa el reentreno, que lo recibe hecho en la tabla de entrenamiento; al ejecutar no se calcula ni se usa.

## Las finalistas y su cadena

Salen de contexto-proyecto/modelo/matriz_transformaciones.md, columnas que entran en el HistGradientBoosting, porque el HistGradientBoostingClassifier no se preseleccionó. La cadena se lee con los pasos del apartado siguiente, en su orden.

| Variable | Columna del modelo | Cadena | Nota |
|---|---|---|---|
| `capacidad_tb` | `capacidad_tb` | P01 → P03 → P04 → P07 → P08 → P11 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `garantia_anos` | `garantia_anos` | P01 → P03 → P04 → P08 → P09 → P10 → P11 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_5_raw` | `smart_5_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_187_raw` | `smart_187_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_197_raw` | `smart_197_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_198_raw` | `smart_198_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_194_raw` | `smart_194_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_199_raw` | `smart_199_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_12_raw` | `smart_12_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_192_raw` | `smart_192_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_1_raw` | `smart_1_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_7_raw` | `smart_7_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `edad_anos` | `edad_anos` | P01 → P03 → P04 → P05 → P06 → P08 → P11 → P12 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `avisa` | `avisa` | P01 → P03 → P04 → P05 → P08 → P11 → P13 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `contadores_que_avisan` | `contadores_que_avisan` | P01 → P03 → P04 → P05 → P08 → P11 → P13 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `suma_contadores_sin_188` | `suma_contadores_sin_188` | P01 → P03 → P04 → P05 → P08 → P11 → P13 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_188_no_cero` | `smart_188_no_cero` | P01 → P03 → P04 → P05 → P08 → P11 → P13 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `cambio_smart_5` | `cambio_smart_5` | P01 → P03 → P04 → P05 → P08 → P11 → P14 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `cambio_smart_187` | `cambio_smart_187` | P01 → P03 → P04 → P05 → P08 → P11 → P14 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `cambio_smart_197` | `cambio_smart_197` | P01 → P03 → P04 → P05 → P08 → P11 → P14 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `cambio_smart_198` | `cambio_smart_198` | P01 → P03 → P04 → P05 → P08 → P11 → P14 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `meses_desde_foto_anterior` | `meses_desde_foto_anterior` | P01 → P03 → P04 → P05 → P08 → P11 → P14 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_1_normalized` | `smart_1_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_2_normalized` | `smart_2_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_2_raw` | `smart_2_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_3_normalized` | `smart_3_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_3_raw` | `smart_3_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_4_raw` | `smart_4_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_5_normalized` | `smart_5_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_7_normalized` | `smart_7_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_8_normalized` | `smart_8_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_8_raw` | `smart_8_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_9_normalized` | `smart_9_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_22_normalized` | `smart_22_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_22_raw` | `smart_22_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_24_normalized` | `smart_24_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_90_raw` | `smart_90_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_183_raw` | `smart_183_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_184_raw` | `smart_184_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_189_raw` | `smart_189_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_191_normalized` | `smart_191_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_191_raw` | `smart_191_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_192_normalized` | `smart_192_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_193_normalized` | `smart_193_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_193_raw` | `smart_193_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_194_normalized` | `smart_194_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_195_normalized` | `smart_195_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_195_raw` | `smart_195_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_196_normalized` | `smart_196_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_196_raw` | `smart_196_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_198_normalized` | `smart_198_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_199_normalized` | `smart_199_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_200_normalized` | `smart_200_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_220_raw` | `smart_220_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_222_raw` | `smart_222_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_223_raw` | `smart_223_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_226_raw` | `smart_226_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_240_raw` | `smart_240_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_241_raw` | `smart_241_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_242_raw` | `smart_242_raw` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `smart_197_normalized` | `smart_197_normalized` | P01 → P03 → P04 → P05 → P08 → P11 → P15 → P18 → P19 → P20 → P24 → P25 | entra al modelo con su nombre |
| `model` | `model` | P01 → P03 → P04 → P08 → P11 → P15 → P18 → P19 → P22 → P23 → P24 → P25 | entra al modelo con su nombre |
| `fabricante` | `fabricante` | P01 → P03 → P04 → P08 → P09 → P11 → P18 → P19 → P22 → P23 → P24 → P25 | entra al modelo con su nombre |
| `datacenter` | ninguna | P01 → P02 → P03 → P04 → P08 → P11 → P15 → P18 → P19 → P21 → P22 → P23 → P24 → P25 | el preprocesador la lee y no saca columna: se vacía (sin sitio) |
| `serial_number` | ninguna | P01 → P15 | no entra al modelo: es el identificador |
| `fecha` | ninguna | P01 → P15 | no entra al modelo: es el identificador |
| `falla_30d` | ninguna | P01 → P03 → P04 → P08 → P11 → P17 → P18 | no entra al modelo: es el objetivo |
| `horizonte_hasta` | ninguna | P01 → P03 → P04 → P08 → P11 → P16 → P18 | no entra al modelo: fija qué fotos entrenan |

## Los pasos

Cada paso cita la ficha del registro de transformaciones que lo hizo y, cuando la ficha remite a las reglas de transformación, el apartado que lo define. La clase decide dónde va: lo que quita filas, solo al reentrenar y contado; lo que no aprende, como función, igual en los dos scripts; lo que necesita otras filas, con la historia hasta el día de la foto; lo que aprende, dentro del Pipeline, con fit en el entrenamiento.

| Orden | Paso | Fuente | Clase | Qué hace | Al reentrenar | Al ejecutar |
|---|---|---|---|---|---|---|
| 1 | P01 · leer la foto en un fichero | R-008 | no aprende | La foto mensual se lee como un solo fichero, con sus columnas por nombre; una columna que su pieza no trae queda vacía y no se rellena. | Ya está aplicado en la tabla de entrenamiento. | La entrada es la foto de un mes; sus columnas se comprueban por nombre. |
| 2 | P02 · el centro como texto | R-001 | no aprende | datacenter pasa a texto; donde no consta sigue vacío. | Ya está aplicado en la tabla de entrenamiento. | Se aplica a la foto. |
| 3 | P03 · el nombre del modelo | R-004 | no aprende | Los modelos escritos con dos espacios tras «WDC» pasan a su nombre con el mapeo cerrado de decisiones-correccion.json; lo que no está en el mapeo se queda como está. | Ya está aplicado en la tabla de entrenamiento. | Se aplica a la foto y a su historia. |
| 4 | P04 · la capacidad del modelo | R-005 | necesita otras filas | Una capacidad no válida (-1 o 0,1 TB, por debajo del mínimo de decisiones-correccion.json) pasa a la única capacidad válida de su modelo. | Ya está aplicado en la tabla de entrenamiento. | Se calcula con la foto y su historia, modelo a modelo. |
| 5 | P05 · los contadores vacíos se quedan vacíos | R-009 | no aprende | Un contador vacío quiere decir que el modelo no lo apunta: no se rellena (C-12). | Ya está así en la tabla de entrenamiento. | No se rellena ningún vacío. |
| 6 | P06 · la historia de las ventanas sin los días copiados | R-007 | necesita otras filas | De la historia de ventanas salen las filas cuya fecha no es la de su texto (date), que son copia del día siguiente, y las ventanas de fallos que no han ocurrido antes del día de la foto (dia_fallo igual o posterior a su fecha). | Ya está aplicado en la tabla de entrenamiento. | Se aplica a la historia de ventanas antes de usarla. |
| 7 | P07 · capacidad en TB | R-011; reglas de transformación, «`dim_modelo`» | no aprende | capacidad_tb es la capacidad del modelo entre 10^12, redondeada a un decimal, con el medio hacia arriba. | Llega hecha en la tabla de entrenamiento. | Se calcula en la foto. |
| 8 | P08 · disco de arranque o de datos | R-011; reglas de transformación, «`dim_modelo`» | no aprende | tipo_disco es «arranque» si la capacidad del modelo no pasa del límite de las reglas §3 y §7 y «datos» si lo pasa. | Decide la población, ya aplicada en la tabla. | Se calcula en la foto para el motivo de P11. |
| 9 | P09 · el fabricante | R-011; reglas de transformación, «`dim_modelo`» | no aprende | fabricante sale del nombre del modelo: «ST» es Seagate; TOSHIBA, WDC y HGST delante dan su nombre; dos excepciones escritas en las reglas §3. | Llega hecho en la tabla de entrenamiento. | Se calcula en la foto. |
| 10 | P10 · la garantía | R-011; reglas de transformación, «`dim_modelo`» | no aprende | garantia_anos sale del nombre del modelo, solo en los discos de datos (reglas §6); un modelo sin garantía comprobada queda vacío. | Llega hecha en la tabla de entrenamiento. | Se calcula en la foto. |
| 11 | P11 · la población | R-013; reglas de transformación, «3. `fotos_riesgo`» | quita filas | Entran los discos de datos y sale la foto del día en que el disco falla (failure = 1). | La tabla ya llega sin esas filas: se comprueba que no queda ninguna y se cuenta. | No se quita ninguna: el disco de arranque y la foto del día del fallo salen con la puntuación vacía y su motivo. |
| 12 | P12 · la edad | R-013; reglas de transformación, «3. `fotos_riesgo`»; «De qué se parte» | necesita otras filas | edad_anos son las horas encendido entre 8.766; sin horas, los días desde la primera aparición del disco entre 365,25. Al ejecutar, la primera aparición solo usa las ventanas de fallos con dia_fallo anterior a la fecha de la foto. | Llega hecha en la tabla de entrenamiento. | Se calcula con la foto y su historia. |
| 13 | P13 · los avisos | R-013; reglas de transformación, «3. `fotos_riesgo`» | no aprende | avisa, contadores_que_avisan, suma_contadores_sin_188 y smart_188_no_cero salen de los cinco contadores de avería de la fila; un vacío no cuenta como aviso. | Llegan hechos en la tabla de entrenamiento. | Se calculan en la foto. |
| 14 | P14 · los cambios contra la foto anterior | R-013; reglas de transformación, «3. `fotos_riesgo`» | necesita otras filas | cambio_smart_5, 187, 197 y 198 restan al contador de la fila el de la foto anterior del mismo disco; meses_desde_foto_anterior cuenta los meses entre las dos. Sin foto anterior, o con uno de los dos valores vacío, quedan vacíos. | Llegan hechos en la tabla de entrenamiento. | Se calculan con la foto y su historia. |
| 15 | P15 · lo que pasa sin cambios | R-013; reglas de transformación, «3. `fotos_riesgo`» | no aprende | serial_number, fecha, model, datacenter y los contadores smart_* pasan tal como están en la fila. | Llegan así en la tabla de entrenamiento. | Se toman de la foto. |
| 16 | P16 · el horizonte del objetivo | R-013; reglas de transformación, «3. `fotos_riesgo`» | no aprende | horizonte_hasta son 30 días después de la foto, recortado al final de su periodo. | Llega hecho en la tabla de entrenamiento y lo usa P18. | No se usa. |
| 17 | P17 · el objetivo | R-010, R-013; reglas de transformación, «3. `fotos_riesgo`» | necesita otras filas | falla_30d vale 1 si el disco tiene un fallo de la lista del día siguiente a la foto a horizonte_hasta, con dia_fallo igualado a milisegundos antes de cruzar. | Llega hecho en la tabla de entrenamiento. | No se calcula ni se usa: si llega, se ignora. |
| 18 | P18 · el objetivo conocido al entrenar | R-020; informes/modelado.json, validacion_cruzada.objetivo_sin_conocer | quita filas | Entrenan las fotos anteriores a la fecha del entrenamiento cuyo horizonte_hasta también es anterior a esa fecha; las demás se quitan y se cuentan, con los fallos que llevan. | Antes del Pipeline, contado. | No aplica: no se quita ninguna fila. |
| 19 | P19 · la muestra | informes/modelado.json, ganador.muestra; reglas de negocio §7 | quita filas | Entrenan todas las fotos con fallo y una parte de las sanas de cada mes, sorteada con la semilla, como en el modelado. | Antes del Pipeline, contado. | No aplica: se puntúan todas las filas. |
| 20 | P20 · las numéricas tal cual | R-021, R-022 | no aprende | Las numéricas entran al modelo tal cual, con el vacío como vacío (rama «numericas», passthrough). | Dentro del Pipeline. | Dentro del Pipeline. |
| 21 | P21 · el centro se vacía | R-021; informes/modelado.json, ganador.datacenter y sitio | no aprende | datacenter se lee y se vacía antes de codificarlo, porque el sitio no entró en el modelo. | Dentro del Pipeline, como función. | Dentro del Pipeline, como función. |
| 22 | P22 · las categorías raras | R-021, R-022 | aprende | En model, fabricante y datacenter el vacío pasa a «sin dato» y las categorías con menos fotos, fallos o sanas que el mínimo de la matriz van a «otras»; una categoría que no estaba en el entrenamiento va a «otras» si existe y, si no, a la referencia (P-03 de la matriz). | Dentro del Pipeline, con fit. | Dentro del Pipeline, ya ajustado. |
| 23 | P23 · el código de categoría | R-021 | aprende | Cada categoría pasa a un código ordinal, que el HistGradientBoosting trata como categórica nativa; lo que no conoce sale vacío. | Dentro del Pipeline, con fit. | Dentro del Pipeline, ya ajustado. |
| 24 | P24 · el modelo | informes/modelado.json, ganador | aprende | El HistGradientBoosting con la receta fija del ganador. | Dentro del Pipeline, con fit. | Dentro del Pipeline, con predict_proba. |
| 25 | P25 · la recalibración | informes/modelado.json, ganador.recalibracion | aprende | La probabilidad del modelo pasa a la escala real con la corrección del prior sobre el logit, con la tasa de fallo de la muestra y la real del entrenamiento. | Se miden las dos tasas al entrenar y viajan con el modelo. | Se aplica a la probabilidad. |

**Por qué va cada paso en su clase**, cuando no es evidente:

- **P04, la capacidad del modelo (necesita otras filas).** No aprende nada de la tabla de entrenamiento: aplica la regla §3, la capacidad de un disco es la de su modelo, y para saberla mira otras filas del mismo modelo con capacidad válida. En el desarrollo se miró todo el periodo y cada modelo tenía una sola; al ejecutar se mira solo lo que hay hasta el día de la foto, la propia foto incluida. Si un modelo no tiene ninguna capacidad válida hasta ese día, su fila sale sin puntuar y con su motivo.
- **P06, la historia de las ventanas sin los días copiados (necesita otras filas).** Quita filas de la tabla de historia, nunca de la foto que se puntúa; por eso no es de la clase que quita filas. Sirve para la primera aparición de la edad y para la capacidad del modelo. Una ventana son los 30 días anteriores a un fallo: que exista una fila de ventana el día de la foto anuncia un fallo que ese día no se conoce (arreglo aprobado por Juan el 19/11/2026).
- **P09, el fabricante (no aprende).** Es una regla fija sobre el nombre. En el desarrollo se guardó en dim_modelo, una tabla por modelo, pero esa tabla solo repite la regla: un modelo nuevo la cumple igual. Un modelo que no sigue ningún patrón queda vacío.
- **P10, la garantía (no aprende).** Igual que el fabricante: una regla fija sobre el nombre, que la tabla dim_modelo solo guarda.
- **P11, la población (quita filas).** Son los discos del modelo (reglas §3 y §7); la foto del día del fallo ya está marcada como fallada.
- **P12, la edad (necesita otras filas).** Con horas es la propia fila. Sin horas cuenta desde la primera aparición, que es su primera foto o, si sale antes, el primer día de una ventana suya: eso pide la historia del disco hasta el día de la foto, nunca después. La ventana de un fallo que aún no ha ocurrido no cuenta, porque anuncia ese fallo (arreglo de Juan, 19/11/2026). En el desarrollo sí contó: de las 2.735 fotos de fotos_riesgo sin horas, en una sola la primera aparición sale de una ventana, y esa foto puede salir distinta.
- **P14, los cambios contra la foto anterior (necesita otras filas).** Necesitan la foto anterior del mismo disco, de cualquier mes anterior: una fila que no es la que se puntúa.
- **P17, el objetivo (necesita otras filas).** Es el objetivo: mira los fallos posteriores a la foto, que al ejecutar no se conocen. Llega hecho en la tabla de entrenamiento; ejecutar no lo calcula ni lo usa.
- **P22, las categorías raras (aprende).** Qué categorías son raras se aprende de la tabla de entrenamiento, con el objetivo: va con fit.
- **P23, el código de categoría (aprende).** La lista de categorías se aprende en el entrenamiento: va con fit.
- **P24, el modelo (aprende).** Es lo que se entrena.
- **P25, la recalibración (aprende).** Las dos tasas se miden en cada reentreno, con su tabla: no se copian del modelado.

## La receta del modelo

El reentreno rehace el modelo con esta receta, leída de informes/modelado.json, y no vuelve a buscar algoritmo ni hiperparámetros.

- **Algoritmo:** HistGradientBoostingClassifier, con early_stopping=False, random_state=42 y las categóricas nativas `model_oe`, `fabricante_oe`, `datacenter_oe`.
- **Hiperparámetros:** {"min_samples_leaf": "hoja", "max_iter": 500, "max_depth": null, "learning_rate": 0.025, "l2_regularization": 0.5}.
- **La hoja (min_samples_leaf):** max(20, 1 % de las filas que entrenan en el pliegue). Con la muestra del modelado, de 232.243 fotos, da 2.322, la del ajuste final.
- **La muestra:** todas las fotos con fallo y el 2 % de las sanas de cada mes, semilla 42. En el modelado fueron 232.243 fotos, 11.962 con fallo.
- **El objetivo conocido:** entrenan las fotos con fecha y horizonte_hasta anteriores a la fecha del entrenamiento. En el ajuste final la fecha fue el 2024-07-01, con 11.026.052 fotos y 11.962 con fallo.
- **La recalibración:** corrección del prior sobre el logit (desequilibrio.md, «Recalibrar»), con odds = p/(1-p) · [real/(1-real)] / [muestra/(1-muestra)]; probabilidad = odds/(1+odds). Las dos tasas se miden en cada reentreno; en el modelado fueron 0,0515064 en la muestra y 0,0010849 la real.
- **La semilla:** 42, en la muestra y en el modelo.

## El corte

El modelo no decide con un umbral. Cada foto mensual se ordena por la probabilidad, de mayor a menor, y a igual probabilidad por serial_number. La salida lleva una marca por cada lista: los 20, 100, 500 y 1.000 primeros de la foto. La lista principal es la de 100.

No se elige un solo tamaño porque el tamaño de la lista lo elige Backblaze según lo que puedan atender sus técnicos, que no consta (reglas §7, CP-010): se dan las listas de 20, 100, 500 y 1.000. Los tamaños se leen de produccion/configuracion.json, que escribe la parte 2.

## La historia que pide ejecutar

La entrada de ejecutar es una foto mensual con las columnas de data/raw/podado/fotos_mensuales/. Antes de puntuar comprueba las columnas por nombre; los números no llegan como texto; la fecha de la foto es la del mes que se pide. Lee de la foto 57 columnas. Además necesita esta historia, que nunca pasa del día de la foto:

- **fotos mensuales anteriores y la propia foto**, hasta la fecha de la foto, incluida: `serial_number`, `fecha`, `model`, `capacity_bytes`, `smart_9_raw`. La usan P04, P12.
- **ventanas de fallo**, hasta las ventanas de fallos ocurridos antes del día de la foto (dia_fallo anterior a su fecha): `serial_number`, `fecha`, `date`, `dia_fallo`, `model`, `capacity_bytes`. La usan P04, P06, P12.
- **fotos mensuales anteriores**, hasta el día anterior a la foto: la última foto del mismo disco, de cualquier mes anterior: `serial_number`, `fecha`, `smart_5_raw`, `smart_187_raw`, `smart_197_raw`, `smart_198_raw`. La usan P14.

## Datos personales

Los datos son de discos: serial_number identifica un disco y no a una persona (reglas §9), y el modelo no lo lee. El contrato no usa ni deja ninguna columna de datos personales. No existe contexto-proyecto/fuentes/proteccion-datos.json: los datos no pasaron por la protección porque no hacía falta.

## Límites

- El contrato describe la parte 2, que todavía no existe: nada de él se ha ejecutado sobre los datos.
- La capacidad del modelo se toma al ejecutar de la historia de fotos y ventanas hasta el día de la foto. En el desarrollo salió de todo el periodo, también del recuento diario. Si algún modelo tiene su única capacidad válida solo en el recuento, NO SE PUEDE SABER sin medirlo; lo mide la parte 2 con las fotos de control.
- La primera aparición de un disco sin horas encendido solo usa las ventanas de fallos ocurridos antes del día de la foto. El desarrollo usó también las de fallos posteriores: en una de las 2.735 fotos sin horas de fotos_riesgo la edad puede salir distinta, y la prueba del módulo la cuenta aparte.
- En la validación, dos discos con la misma probabilidad cerca del borde de una lista se contaron con su valor esperado (por eso hay cifras con decimales); producción desempata por serial_number. Las listas pueden diferir en esos empates.

## La aprobación

Juan, 19/11/2026: «Sí, con el arreglo», el 2026-11-19. El arreglo es el de P06 y P12: al ejecutar, la primera aparición solo usa las ventanas de fallos ocurridos antes del día de la foto. Con el contrato aprobado se escriben el módulo del Pipeline, el reentreno, la ejecución y la prueba por otro camino.
