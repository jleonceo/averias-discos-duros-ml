# Calidad de los datos del caso 68

Diagnóstico de los cuatro datasets del caso, generado por `scripts/02_calidad_datos.py` el 2026-11-17 a partir de `informes/calidad-datos.json`. No se ha corregido ningún dato. Lo leen la persona responsable del caso y la fase de corrección.

## 1. Fuente analizada

Se leyeron enteros los cuatro datasets de `data/raw/podado/`, sin muestra, y el esquema de Backblaze, que solo entra en la revisión de nombres. La huella de los 91 ficheros de `data/raw/` es la misma al empezar y al acabar.

- **fotos mensuales** (`data/raw/podado/fotos_mensuales`): 66 ficheros que pesan 731.506.906 bytes.
- **ventanas de fallo** (`data/raw/podado/ventanas_fallo`): 22 ficheros que pesan 39.116.051 bytes.
- **recuento diario** (`data/raw/podado/recuento_diario.parquet`): 1 fichero que pesa 341.786 bytes.
- **lista de fallos** (`data/raw/podado/fallos.parquet`): 1 fichero que pesa 205.699 bytes.
- **esquema de Backblaze** (`data/raw/Drive_Stats_Schema_Current.csv`): 3.531 bytes.
- Huella SHA-256 de la lista de fallos: `901e8e07fc0d89f5969af23787c46abfaa502b98139c169cef12f234ada5b2e5`. La del esquema: `365cf50ad5ebfc3e20d0959337d9877ce9539e0432955bda836b7482cd0f5358`. Las de los demás ficheros están en `entradas` del JSON.
- Ejecución: 2026-11-17T16:01:35, con Python 3.13.15 y pandas 3.0.6; tardó 230 segundos.
- Se partió del diccionario del origen, cuyas huellas coinciden con las de los ficheros analizados: filas, tipos, roles, vacíos y categorías raras se toman de él sin recalcular.

## 2. Resumen

Estado: AVISO. Riesgo: medio. Los cuatro datasets diagnosticados enteros, sin corregir nada: 30 problemas para la corrección y 1 pendientes. Las cuatro lecturas del plan (D1 a D4) están cerradas; de las ocho reglas candidatas, 4 tienen filas que las incumplen.

Los problemas principales, con su identificador para la corrección:

- C-05, fotos mensuales, `capacity_bytes`: 2.729 filas con capacidad -1 o 0,1 TB; 2.729 de ellas sin ningún contador.
- C-07, recuento diario, `capacity_bytes`: 2.102 filas con capacidad -1 o 0,1 TB, con 20 fallos.
- C-08, recuento diario, `datacenter`: 84.647 filas con centro «sin dato», 4.551 desde el 01/07/2023.
- C-13, fotos mensuales, ventanas de fallo y recuento diario, `model`: 4 modelos escritos con dos espacios tras «WDC»; 3.285 discos salen con los dos nombres.
- C-14, fotos mensuales, `smart_188_raw`: 192.593 filas de discos de datos por encima de mil millones.
- C-16, ventanas de fallo, `smart_194_raw`: 9 filas por encima de 70 grados, con máximo de 117.
- C-17, ventanas de fallo, `fecha, date`: 228 filas en que la fecha y su texto no coinciden: fecha 2022-12-10, texto 2022-12-11.
- C-18, fotos mensuales, `smart_9_raw`: RC-01 incumplida: 3.468 veces bajan las horas entre dos fotos seguidas; 3.468 más de un día.
- C-19, fotos mensuales, `model, capacity_bytes`: RC-02 incumplida: el modelo cambia 7.372 veces (1 sin contar las variantes de espacios) y la capacidad 3.854 (0 entre capacidades válidas).
- C-20, fotos mensuales, `smart_5_raw, smart_187_raw, smart_188_raw, smart_197_raw, smart_198_raw`: RC-03 incumplida: smart_5_raw baja 575 veces en 413 discos; smart_187_raw baja 12 veces en 12 discos; smart_188_raw baja 1.650 veces en 1.650 discos; smart_197_raw baja 24.477 veces en 11.547 discos; smart_198_raw baja 10.055 veces en 5.517 discos.
- C-23, lista de fallos, `serial_number`: 210 fallos de 210 discos que no salen en ninguna foto.

Hay 30 problemas en total y una cuestión pendiente:
- P-01 (C-17): ¿Las filas cuya fecha no coincide con su texto son una copia del día que dice el texto, o son de su fecha con el texto mal? Opciones: son una copia del día que dice el texto: su fecha no tiene datos propios y sus filas sobran; son de su fecha y solo el texto está mal: se quedan como están. Cifra: 228 filas de ventanas; 228 traen las mismas horas que la fila del día del texto. No estaba en el plan; la corrección mide si quitarlas cambia alguna respuesta, y solo si cambia se lleva a la persona responsable.

## 3. Inspección general

Los cuatro datasets cubren del 2020-01-01 al 2025-06-30. Ninguna fila cae en la reserva.

- **fotos mensuales**: 14.851.669 filas y de 101 a 130 columnas. Construcción, 11.223.741 filas; validación, 3.627.928.
- **ventanas de fallo**: 536.825 filas y de 102 a 131 columnas. Construcción, 398.970 filas; validación, 137.855.
- **recuento diario**: 201.502 filas y 6 columnas. Construcción, 140.361 filas; validación, 61.141.
- **lista de fallos**: 17.960 filas y 2 columnas. Construcción, 13.376 filas; validación, 4.584.
- Las fotos van del 2020-01-01 al 2025-06-01. Ficheros con más de una fecha: 0.
- Las ventanas van del 2020-01-01 al 2025-06-30; sus fallos, del 2020-01-01 al 2025-06-30.
- El recuento trae 2.008 días; entre el primero y el último faltan 0.

## 4. Estructura

En las fotos mensuales, 49 columnas están vacías en más del 99 % de las filas que las traen, y 0 lo están del todo.

- Columnas constantes en todas sus filas: ninguna.
- Columnas que no traen todos los ficheros: 29. Entran a mitad del periodo, entre 2020-10 y 2024-04, y en los ficheros anteriores no existen.
- Ficheros con alguna columna vacía entera: 47 de 66; con alguna columna constante: 66.

En las ventanas de fallo, 48 columnas están vacías en más del 99 % de las filas que las traen, y 0 lo están del todo.

- Columnas constantes en todas sus filas: `smart_171_raw`, `smart_179_raw`, `smart_181_raw`, `smart_206_raw`, `smart_211_raw`, `smart_212_raw`, `smart_235_normalized`.
- Columnas que no traen todos los ficheros: 29. Entran a mitad del periodo, entre data_Q1_2021 y data_Q1_2025, y en los ficheros anteriores no existen.

Nombres de columna de los cuatro datasets con algún aviso: 0. Colisiones al normalizarlos: 0. Nombres del esquema con aviso: 3.

- `Last Updated Q2 2024` (esquema de Backblaze): espacios, mayúsculas, no es un nombre de columna.
- `smart_211_normailized` (esquema de Backblaze): errata: no sigue la forma smart_N_raw o smart_N_normalized.
- `smart_212_normailized` (esquema de Backblaze): errata: no sigue la forma smart_N_raw o smart_N_normalized.

## 5. Tipos y formatos

Columnas con algún valor que no se convierte al tipo que les toca por su rol: 0.

- La ranura (`pod_slot_num`) se lee como decimal en las fotos y en las ventanas, y el 0 % de sus valores no es entero.
- El centro viene sin tipo en 42 ficheros de fotos, del 2020-01 al 2023-06, porque está vacío entero.
- La fecha llega dos veces, como texto (`date`) y como fecha (`fecha`). Filas en que no dicen lo mismo: 228. Textos que no siguen el formato ISO: 0.
- Magnitudes con un salto de orden de magnitud sin valores en medio: 35. Lo que mide un contador en bruto explica casi siempre que vaya de 0 a miles de millones, así que el salto solo señala dónde mirar.
  - `capacity_bytes` (fotos mensuales): cifras enteras 1: 2.729, 12: 245.976, 13: 3.519.380, 14: 11.083.584.
  - `smart_10_raw` (fotos mensuales): cifras enteras 1: 14.688.176, 5: 3.068, 6: 298, 7: 43, 11: 11.
  - `smart_13_raw` (fotos mensuales): cifras enteras 1: 4.756, 2: 31, 3: 62, 11: 27, 12: 6, 13: 1, 14: 2, 15: 6.
  - `smart_22_raw` (fotos mensuales): cifras enteras 1: 13, 2: 3.699, 3: 2.866.040, 5: 1, 7: 356.871.
  - `smart_90_raw` (fotos mensuales): cifras enteras 11: 14, 12: 344.442, 15: 518.
  - `smart_170_raw` (fotos mensuales): cifras enteras 1: 7.357, 2: 35.270, 3: 60.814, 4: 207, 10: 5.007, 11: 694, 12: 763, 13: 5.
  - `smart_173_raw` (fotos mensuales): cifras enteras 1: 636, 2: 3.879, 3: 16.683, 4: 9.092, 5: 27, 6: 331, 7: 946, 8: 40, 10: 3.695, 11: 2.351, 12: 18.517, 13: 74.488, 14: 1.881.
  - `smart_188_raw` (fotos mensuales): cifras enteras 1: 6.725.018, 2: 6.487, 3: 5.531, 4: 4.145, 5: 6.571, 6: 5.372, 7: 591, 8: 37, 10: 146.552, 11: 51.426, 12: 5.871, 13: 130.
  - `smart_200_raw` (fotos mensuales): cifras enteras 1: 4.398.789, 3: 80, 4: 574, 5: 3.548, 6: 15.737, 7: 2.984.
  - `smart_201_raw` (fotos mensuales): cifras enteras 1: 4.849, 4: 3, 10: 1, 11: 37, 12: 1.
  - `smart_220_raw` (fotos mensuales): cifras enteras 1: 56.438, 2: 8, 6: 170.887, 7: 393.100, 8: 1.246.773, 9: 1.472.630.
  - `smart_230_raw` (fotos mensuales): cifras enteras 1: 1.712, 10: 1, 11: 68, 12: 245, 13: 1.888, 14: 3.857, 15: 8.
  - `smart_231_raw` (fotos mensuales): cifras enteras 1: 17.725, 2: 42.427, 3: 2, 15: 42.103.
  - `smart_232_raw` (fotos mensuales): cifras enteras 1: 60.110, 2: 2.888, 3: 5.048, 10: 44, 12: 42.103.
  - `smart_233_raw` (fotos mensuales): cifras enteras 1: 56, 2: 13, 3: 3.241, 4: 5.670, 5: 46.940, 6: 54.128, 7: 30, 9: 40, 10: 101, 11: 1.985, 12: 2.686, 13: 37.
  - `smart_235_raw` (fotos mensuales): cifras enteras 1: 16, 2: 11, 4: 5, 5: 9, 6: 28, 8: 1, 9: 120, 10: 2.737, 11: 22.585, 12: 76.457, 13: 369.
  - `capacity_bytes` (ventanas de fallo): cifras enteras 1: 158, 12: 28.525, 13: 154.079, 14: 354.063.
  - `smart_10_raw` (ventanas de fallo): cifras enteras 1: 529.912, 5: 45, 6: 5, 7: 92.
  - `smart_13_raw` (ventanas de fallo): cifras enteras 1: 370, 10: 1, 11: 3, 12: 7, 13: 8.
  - `smart_22_raw` (ventanas de fallo): cifras enteras 1: 142, 2: 1.188, 3: 84.050, 5: 14, 6: 5, 7: 8.112.
  - `smart_90_raw` (ventanas de fallo): cifras enteras 12: 6.939, 15: 3.
  - `smart_165_raw` (ventanas de fallo): cifras enteras 2: 335, 3: 1.698, 4: 953, 5: 40, 7: 14, 8: 1, 11: 7, 12: 93, 13: 129, 14: 241, 15: 29.
  - `smart_170_raw` (ventanas de fallo): cifras enteras 1: 503, 2: 481, 3: 921, 4: 31, 10: 71, 11: 9, 12: 301, 13: 96.
  - `smart_173_raw` (ventanas de fallo): cifras enteras 1: 50, 2: 333, 3: 366, 4: 245, 5: 1, 6: 19, 7: 31, 10: 64, 11: 44, 12: 359, 13: 1.361.
  - `smart_188_raw` (ventanas de fallo): cifras enteras 1: 265.778, 2: 848, 3: 120, 4: 116, 5: 4.948, 6: 6.765, 7: 829, 10: 20.410, 11: 10.758, 12: 1.448, 13: 3.
  - `smart_195_raw` (ventanas de fallo): cifras enteras 1: 7.628, 4: 15, 5: 72, 6: 729, 7: 7.083, 8: 70.188, 9: 112.232.
  - `smart_200_raw` (ventanas de fallo): cifras enteras 1: 167.140, 3: 31, 4: 216, 5: 595, 6: 2.643, 7: 367.
  - `smart_201_raw` (ventanas de fallo): cifras enteras 1: 370, 12: 19.
  - `smart_220_raw` (ventanas de fallo): cifras enteras 1: 15.953, 2: 2, 6: 4.069, 7: 10.796, 8: 33.833, 9: 39.878.
  - `smart_231_raw` (ventanas de fallo): cifras enteras 1: 93, 2: 611, 15: 1.175.
  - `smart_232_raw` (ventanas de fallo): cifras enteras 1: 703, 2: 2.666, 3: 874, 10: 1, 12: 1.175.
  - `smart_233_raw` (ventanas de fallo): cifras enteras 3: 340, 4: 215, 5: 867, 6: 990, 11: 339, 12: 31.
  - `smart_234_raw` (ventanas de fallo): cifras enteras 1: 19, 2: 4, 3: 17, 4: 48, 5: 348, 6: 68, 7: 29, 9: 9, 10: 80, 11: 31, 12: 93.
  - `smart_235_raw` (ventanas de fallo): cifras enteras 5: 11, 6: 8, 9: 8, 10: 74, 11: 476, 12: 1.383.
  - `capacity_bytes` (recuento diario): cifras enteras 1: 2.096, 12: 56.833, 13: 55.372, 14: 87.201.

## 6. Valores ausentes

Las filas con capacidad no válida de las fotos llegan sin ningún contador en 2.729 de 2.729 casos: es una ausencia de la fila. Los demás vacíos se reparten así por variable.

### Códigos de ausencia

- `capacity_bytes` = -1 o 0,1 TB en fotos mensuales: 2.729 filas (0,02 %), documentado. 2.729 de ellas no traen ningún contador: es una ausencia de la fila. Reglas §3: la capacidad es la de su modelo.
- `capacity_bytes` = -1 o 0,1 TB en ventanas de fallo: 165 filas (0,03 %), documentado. Reglas §3: la capacidad es la de su modelo.
- `capacity_bytes` = -1 o 0,1 TB en recuento diario: 2.102 filas (1,04 %), documentado. Llevan 128.722 días de disco y 20 fallos.
- `datacenter` = sin dato en recuento diario: 84.647 filas (42,01 %), documentado. 4.551 son desde el 01/07/2023. Reglas §4 y §5: el centro no consta y se cuenta.
- `cluster_id` = 0 en fotos mensuales: 4.781.548 filas (69,44 %), sin documentar. Valor del mínimo con el 69,44 % de las filas que traen la columna. Por centro: sin centro 84.695, sac0 1.976.669, phx1 1.465.162, sac2 1.255.022.
- `pod_id` = 0 en fotos mensuales: 380.858 filas (5,00 %), sin documentar. Valor del mínimo con el 5,00 % de las filas que traen la columna.
- `smart_22_raw` = 6.553.700 en fotos mensuales: 356.870 filas (11,06 %), sin documentar. Valor del máximo con el 11,06 % de las filas que traen la columna.
- `smart_212_raw` = 16 en fotos mensuales: 3 filas (7,69 %), sin documentar. Valor del máximo con el 7,69 % de las filas que traen la columna.
- `cluster_id` = 0 en ventanas de fallo: 213.090 filas (81,62 %), sin documentar. Valor del mínimo con el 81,62 % de las filas que traen la columna.
- `smart_22_raw` = 6.553.700 en ventanas de fallo: 8.099 filas (8,66 %), sin documentar. Valor del máximo con el 8,66 % de las filas que traen la columna.
- `smart_166_raw` = 1 en ventanas de fallo: 2.240 filas (63,28 %), sin documentar. Valor del mínimo con el 63,28 % de las filas que traen la columna.
- `smart_168_raw` = 5.050 en ventanas de fallo: 3.026 filas (55,84 %), sin documentar. Valor del máximo con el 55,84 % de las filas que traen la columna.
- `smart_177_raw` = 10 en ventanas de fallo: 1.113 filas (22,69 %), sin documentar. Valor del máximo con el 22,69 % de las filas que traen la columna.
- `smart_180_raw` = 4.652 en ventanas de fallo: 308 filas (39,09 %), sin documentar. Valor del máximo con el 39,09 % de las filas que traen la columna.
- `smart_211_raw` = 50 en ventanas de fallo: 1 filas (100 %), sin documentar. Valor del mínimo con el 100 % de las filas que traen la columna.

### Reparto de los vacíos

- fotos mensuales: repartidos, 80; concentrados, 41; sin nulos, 9.
- ventanas de fallo: repartidos, 80; concentrados, 41; sin nulos, 10.

Las variables que más pesan en las preguntas, con su porcentaje global y el segmento que más lo concentra:

- `datacenter`: 55,22 % vacío, repartidos.
- `pod_slot_num`: 1,50 % vacío, concentrados. El segmento que más concentra es sin patrón (fabricante), con el 100 %.
- `smart_5_raw`: 0,84 % vacío, concentrados. El segmento que más concentra es DELLBOSS VD (modelo), con el 100 %.
- `smart_9_raw`: 0,15 % vacío, concentrados. El segmento que más concentra es DELLBOSS VD (modelo), con el 100 %.
- `smart_187_raw`: 53,01 % vacío, repartidos.
- `smart_188_raw`: 53,15 % vacío, repartidos.
- `smart_194_raw`: 0,15 % vacío, concentrados. El segmento que más concentra es DELLBOSS VD (modelo), con el 100 %.
- `smart_197_raw`: 2,61 % vacío, concentrados. El segmento que más concentra es DELLBOSS VD (modelo), con el 100 %.
- `smart_198_raw`: 0,89 % vacío, concentrados. El segmento que más concentra es DELLBOSS VD (modelo), con el 100 %.

### Vacíos por fila

- fotos mensuales: la mediana de vacíos por fila es 73 contando todas las columnas, y 26 sin las 49 casi vacías. Filas sin ningún vacío: 0 y 0.
- ventanas de fallo: la mediana de vacíos por fila es 72 contando todas las columnas, y 27 sin las 48 casi vacías. Filas sin ningún vacío: 0 y 0.
- recuento diario: ninguna fila tiene vacíos.
- lista de fallos: ninguna fila tiene vacíos.

## 7. Duplicados

Filas repetidas enteras en las cuatro tablas: 0. Sin el número de serie, dos discos pueden coincidir en todo: esas filas se cuentan como evidencia, no como error.

- fotos mensuales: exactos, 0; sin identificadores, 35.697; por clave, 0; casi duplicados, 0; lógicos, 3.896.
- ventanas de fallo: exactos, 0; sin identificadores, 8; por clave, 0; casi duplicados, 0; lógicos, 25.
- recuento diario: exactos, 0; sin identificadores, 0; por clave, 0; casi duplicados, 2.095; lógicos, 1.536.
- lista de fallos: exactos, 0; sin identificadores, 15.996; por clave, 0; casi duplicados, 0; lógicos, 0.

Los casi duplicados del recuento son filas cuya clave se repite si se quita la capacidad, la misma combinación partida por una capacidad no válida. Los lógicos son filas con un modelo escrito con dos espacios tras «WDC» (D1). En la lista de fallos, sin el número de serie se repiten los días con más de un fallo.

## 8. Claves y granularidad

Claves repetidas en las cuatro tablas: 0. La granularidad observada es la documentada.

- fotos mensuales: una fila es un disco el día 1 de un mes; clave `serial_number`, `fecha`, con 0 repetidas.
- ventanas de fallo: una fila es un disco en un día de los 30 anteriores a un fallo o el del fallo, con el fallo al que pertenece; clave `serial_number`, `fecha`, con 0 repetidas.
- recuento diario: una fila es un día, un modelo, una capacidad y un centro, con sus discos y sus fallos; clave `fecha`, `model`, `capacity_bytes`, `datacenter`, con 0 repetidas.
- lista de fallos: una fila es un disco y el día de su fallo; clave `serial_number`, `dia_fallo`, con 0 repetidas.
- Ningún disco sale dos veces en la misma foto (0 repeticiones).

## 9. Categóricas y texto

El modelo tiene 98 valores en las fotos y el centro, 6. Columnas de texto libre: 0. Valores con forma de instrucción: 0. Textos de ausencia sin documentar: 0.

- Variantes de escritura del modelo (D1, cerrada el 17/11/2026: son el mismo modelo y los junta la corrección):
  - «WDC  WDS250G2B0A» frente a «WDC WDS250G2B0A»: en las fotos, 7 filas de 6 discos; en las ventanas, 0 filas; en el recuento, 147 filas. Discos con los dos nombres: 6.
  - «WDC  WUH721414ALE6L4» frente a «WDC WUH721414ALE6L4»: en las fotos, 2.763 filas de 2.336 discos; en las ventanas, 23 filas; en el recuento, 686 filas. Discos con los dos nombres: 2.336.
  - «WDC  WUH721816ALE6L0» frente a «WDC WUH721816ALE6L0»: en las fotos, 1.009 filas de 831 discos; en las ventanas, 2 filas; en el recuento, 518 filas. Discos con los dos nombres: 831.
  - «WDC  WUH721816ALE6L4» frente a «WDC WUH721816ALE6L4»: en las fotos, 117 filas de 112 discos; en las ventanas, 0 filas; en el recuento, 185 filas. Discos con los dos nombres: 112.
- Modelos que no siguen el patrón de su fabricante: 25. De ellos, 25 son discos de arranque o una de las dos excepciones de las reglas.
- Categorías raras del diccionario: 83 modelos de las fotos y 1 centro. Las que son un código de ausencia: 0.
- El centro «sin dato» del recuento es un código documentado (reglas §4 y §5), no una categoría.

## 10. Numéricas y outliers

Los atípicos se buscan solo en las magnitudes y solo con la construcción, por rango intercuartílico (1,5 veces) y por z robusto (3,5). Solo detectan: ningún valor se ha tocado. Manual 7.1 y 7.2 para el orden del diagnóstico; 7.3 para los vacíos por fila y los códigos de ausencia; 7.4 para los duplicados con clave; 7.5 y 33.10 para las categorías raras; 7.6, 3.6 y 33.9 para la escala, las colas y los atípicos, que se miden en la construcción porque lo que se aprende de los datos se ajusta solo con ella (33.2); 14.13 para comprobar que las fechas son fechas; 7.8 a 7.10 antes de dar el diagnóstico por terminado.

- Magnitudes revisadas: 147. Con dispersión cero por los dos métodos, sin atípicos que marcar: 45.
- Magnitudes con algún valor marcado por los dos métodos: 71.

Las colas que piden las decisiones del plan, con la construcción:

- `smart_194_raw`, fotos mensuales: los más bajos, 12 (55), 13 (349), 14 (902); los cinco más altos, 65 (1), 66 (2), 67 (1), 69 (1), 70 (1).
- `smart_194_raw`, ventanas de fallo: los más bajos, 13 (67), 14 (38), 15 (262); los cinco más altos, 74 (1), 88 (1), 95 (1), 98 (1), 117 (1).
- `smart_5_raw`, fotos mensuales: los más bajos, 0 (10.804.254), 1 (21.967), 2 (5.510); los cinco más altos, 65.488 (1), 65.504 (1), 65.512 (1), 65.520 (1), 65.528 (6).
- `smart_5_raw`, ventanas de fallo: los más bajos, 0 (225.503), 1 (6.008), 2 (2.974); los cinco más altos, 65.504 (24), 65.512 (1), 65.520 (52), 65.528 (61), 65.534 (1).
- `smart_187_raw`, fotos mensuales: los más bajos, 0 (5.506.765), 1 (23.499), 2 (11.207); los cinco más altos, 34.101 (1), 34.105 (7), 35.975 (1), 35.977 (1), 65.535 (25).
- `smart_187_raw`, ventanas de fallo: los más bajos, 0 (111.182), 1 (8.787), 2 (5.412); los cinco más altos, 50.692 (1), 50.720 (1), 55.724 (1), 65.429 (1), 65.535 (70).
- `smart_188_raw`, fotos mensuales: los más bajos, 0 (5.451.525), 1 (28.344), 2 (4.229); los cinco más altos, 1.571.982.016.920 (1), 1.735.193.264.579 (1), 1.941.355.113.084 (4), 2.022.960.541.105 (4), 2.207.647.150.149 (4).
- `smart_188_raw`, ventanas de fallo: los más bajos, 0 (217.928), 1 (3.618), 2 (884); los cinco más altos, 627.085.090.727 (1), 674.324.283.612 (1), 876.190.040.438 (4), 1.168.275.800.746 (1), 1.357.262.619.432 (2).
- `smart_9_raw`, fotos mensuales: los más bajos, 0 (284), 1 (79), 2 (67); los cinco más altos, 95.021 (1), 95.426 (1), 95.762 (1), 96.479 (1), 97.234 (1).
- `smart_9_raw`, ventanas de fallo: los más bajos, 0 (106), 1 (14), 2 (7); los cinco más altos, 82.879 (1), 82.911 (1), 82.926 (1), 82.958 (1), 82.990 (1).
- `capacity_bytes`, fotos mensuales: los más bajos, -1 (2.533), 240.057.409.536 (3.790), 250.059.350.016 (97.354); los cinco más altos, 14.000.519.643.136 (2.517.271), 16.000.900.661.248 (1.927.595), 18.000.207.937.536 (2.700), 20.000.588.955.648 (18), 22.000.969.973.760 (38.450).
- `capacity_bytes`, ventanas de fallo: los más bajos, -1 (121), 137.438.952.960 (5), 240.057.409.536 (370); los cinco más altos, 12.000.138.625.024 (121.932), 14.000.519.643.136 (70.076), 16.000.900.661.248 (37.422), 18.000.207.937.536 (308), 22.000.969.973.760 (1.102).

## 11. Fechas

Textos de fecha que no siguen el formato ISO: 0; con formato ISO no hay duda entre día y mes. Fechas después del horizonte, el 2025-06-30: 0.

- `fecha` (fotos mensuales): del 2020-01-01 al 2025-06-01; fuera del horizonte, 0.
- `date` (fotos mensuales): del 2020-01-01 al 2025-06-01; fuera del horizonte, 0.
- `fecha` (ventanas de fallo): del 2020-01-01 al 2025-06-30; fuera del horizonte, 0.
- `dia_fallo` (ventanas de fallo): del 2020-01-01 al 2025-06-30; fuera del horizonte, 0.
- `fecha` (recuento diario): del 2020-01-01 al 2025-06-30; fuera del horizonte, 0.
- `dia_fallo` (lista de fallos): del 2020-01-01 al 2025-06-30; fuera del horizonte, 0.
- Fotos que no son de un día 1: 0. Filas de ventana fuera de los 30 días anteriores a su fallo: 0.

## 12. Reglas lógicas e integridad

Cada regla del caso se ha mirado con su medida, sin aplicarla a los datos. Las reglas no traen tabla de valores esperables, así que no hay rangos de negocio que mirar.

### Comprobaciones de las reglas

- R-01, la capacidad de un disco es la de su modelo (reglas §3): ningún modelo trae dos capacidades válidas (0 con más de una). Filas con -1 o 0,1 TB: 2.729 en fotos, 165 en ventanas y 2.102 en el recuento; 20 fallos la traen el día del fallo.
- R-02, el fabricante sale del nombre del modelo, con dos excepciones (reglas §3): 25 modelos no siguen el patrón; 0 no son ni de arranque ni una de las dos excepciones.
- R-03, la edad son las horas encendido y, sin ellas, cuenta desde la primera aparición (reglas §3): discos de datos sin horas en ninguna foto, 1; con horas en unas fotos y no en otras, 2.736. Fallos con edad negativa por la primera aparición en las fotos: 67.
- R-04, un disco puede fallar dos veces y seguir en servicio tras un fallo (reglas §3): 12 discos fallan dos veces. 161 discos salen en alguna foto después de su fallo, y 10 de ellos tienen dos fallos en la lista.
- R-05, un disco que falta en una foto y vuelve no ha desaparecido (reglas §3): 7.798 discos de datos (1,94 %) faltan en alguna foto y vuelven; huecos de un mes: 6.113 de 8.298.
- R-06, el sitio solo consta desde el 01/07/2023 y no se rellena hacia atrás (reglas §4): en las fotos, sin dato antes y desde el 01/07/2023: datacenter 100 % y 3,42 %; cluster_id 100 % y 0 %; vault_id 90,83 % y 0 %; pod_id 90,83 % y 0 %; pod_slot_num 100 % y 1,50 %.
- R-07, un disco con dos registros el mismo día cuenta una vez (reglas §5): repeticiones de disco y día: 0 en las fotos y 0 en las ventanas.
- R-08, un contador vacío quiere decir que ese modelo no lo apunta (reglas §5): sin las filas de capacidad no válida, 163 pares de modelo y contador tienen vacíos solo en parte de sus filas, en 33 contadores; suman 2.789.298 filas vacías. Son los que contradicen la regla.
- R-09, un sitio vacío quiere decir que no consta (reglas §5): filas de fotos sin dato de sitio desde el 01/07/2023: datacenter 235.772; cluster_id 0; vault_id 0; pod_id 0; pod_slot_num 103.221. El reparto por centro y por grupo está en el JSON.
- R-10, el sitio de un fallo es el del último día anterior que lo trae, dentro de su ventana (reglas §5): de 8.634 fallos de discos de datos desde el 01/07/2023, 2.010 no traen ranura el día del fallo; 1.997 la recuperan un día anterior y 13 no la tienen ningún día.
- R-11, los valores en bruto de algunos contadores tienen formato de cada fabricante (reglas §5): rango y cifras por fabricante, con la construcción: smart_1_raw de 0 a 4.294.967.295; smart_7_raw de 0 a 281.471.670.783.244; smart_188_raw de 0 a 2.207.647.150.149; smart_195_raw de 0 a 244.140.504. El detalle por fabricante, en el JSON.

### Cuestiones del reconocimiento

- Q-01, modelos con dos espacios tras «WDC» (D1): 4 variantes; 3.896 filas de fotos, 25 de ventanas y 1.536 del recuento. 3.285 discos salen con los dos nombres. Cerrada el 17/11/2026 (D1).
- Q-02, capacidad -1 o 0,1 TB: 2.729 filas de fotos, 165 de ventanas y 2.102 del recuento; en construcción, 2.533 de las fotos.
- Q-03, centro «sin dato» en el recuento: 84.647 filas con 249.886.684 días de disco; 4.551 son desde el 01/07/2023.
- Q-04, horas encendido que faltan: 2.738 filas de fotos de discos de datos sin horas: 2.725 son de capacidad no válida y 13 del resto. Fallos con edad negativa: 67.
- Q-05, el 188 por encima de mil millones (D2): 192.593 filas de fotos de discos de datos; por fabricante: Seagate 192.593. Cerrada el 17/11/2026 (D2).
- Q-06, el 5 y el 187 en su tope (D3): el 187 vale 65.535 en 52 filas de fotos y 169 de ventanas; el máximo del 5 es 65.529 en fotos y 65.534 en ventanas. Las colas, en «colas». Cerrada el 17/11/2026 (D3).
- Q-07, fallos sin ranura: 2.010 fallos de discos de datos sin ranura el día del fallo desde el 01/07/2023, 13 sin ranura ningún día de su ventana. Sin tomo completo (centro, vault y ranura) ningún día de su ventana: 141.
- Q-08, fallos sin foto o sin día anterior: 210 fallos de discos que no salen en ninguna foto; 896 fallos de discos de datos sin el día anterior en su ventana (902 con los de arranque).
- Q-09, horas que bajan: 3.468 veces bajan más de un día en discos de datos, en 3.443 discos; 3.414 bajan más de un año.
- Q-10, días hundidos en el recuento: discos que faltan frente a la media del día de antes y el de después: 2022-06-06, 146.944; 2023-03-19, 89.084; 2023-04-13, 169.071; 2023-04-16, 169.574; 2023-07-05, 92.393; 2023-12-18, 55.364; 2025-05-12, 70.413.
- Q-11, tipos y nombres: la ranura llega como decimal; el centro, sin tipo en 42 ficheros de fotos; erratas del esquema: smart_211_normailized, smart_212_normailized.
- Q-12, temperatura por encima de 70 grados en las ventanas: 9 filas de ventanas de 7 discos, con máximo de 117 grados; en las fotos el máximo es 70.

### Riesgos para un modelo

- El sitio falta al construir y está al validar. Sin dato en construcción: datacenter 71,66 %, vault_id 64,46 %, pod_slot_num 71,45 %. En validación: datacenter 4,38 %, vault_id 0 %, pod_slot_num 1,38 %.
- Los contadores 187 y 188 solo los traen los Seagate y su vacío cambia entre periodos: smart_187_raw, 49,35 % en construcción y 64,32 % en validación; smart_188_raw, 49,48 % en construcción y 64,53 % en validación.
- La variable objetivo está muy desequilibrada. Con el fallo a 30 días, la construcción tiene 11.577 casos frente a 10.732.277 no casos (0,1078 %). A 90 días, como el reconocimiento, 34.001 frente a 10.428.469.
- Las ventanas solo existen para los 17.948 discos que fallan: usar sus columnas día a día mezclaría con el objetivo información que solo tienen los que fallan.
- El modelo tiene 98 valores en las fotos, 83 de ellos por debajo del umbral de categoría rara.
- Columnas calculadas a partir de otras: las 48 notas normalizadas salen del valor en bruto de su contador, y la capacidad sale del modelo.

## 13. Cruces entre tablas

Se revisaron las seis relaciones entre los cuatro datasets, sin guardar ninguna tabla cruzada.

- lista de fallos con ventanas de fallo, por `serial_number`, `dia_fallo`, 1:N: sin pareja a la izquierda, 0; a la derecha, 0.
- lista de fallos con fotos mensuales, por `serial_number`, N:M, por el disco: sin pareja a la izquierda, 210; a la derecha, 390.470. Un disco de las fotos sin fallo es lo normal: casi ningún disco falla.
- ventanas de fallo con fotos mensuales (relación supuesta), por `serial_number`, `fecha`, 1:1: sin pareja a la izquierda, 0; a la derecha, 0.
  - Filas que casan con otro modelo: 0.
  - Filas que casan con otra capacidad: 0.
- recuento diario con fotos mensuales, por `fecha`, `model`, `capacity_bytes`, `datacenter`, 1:N: sin pareja a la izquierda, 0; a la derecha, 0.
  - Claves con otro número de discos: 0.
  - Antes de igualar el centro vacío con «sin dato»: sin pareja izquierda, 2.803; sin pareja derecha, 2.803.
- recuento diario con ventanas de fallo (relación supuesta), por `fecha`, `model`, `capacity_bytes`, `datacenter`, 1:N: sin pareja a la izquierda, 131.231; a la derecha, 0. Una fila del recuento sin ventana es lo normal: ese día ningún disco de su clave estaba a 30 días de fallar.
  - Claves con más filas que discos: 0.
  - Antes de igualar el centro vacío con «sin dato»: sin pareja derecha, 30.462.
- recuento diario con lista de fallos (relación supuesta), por `fecha`, `model`, `capacity_bytes`, `datacenter`, 1:N: sin pareja a la izquierda, 0; a la derecha, 0.
  - Claves con otro número de fallos: 0.

## 14. Reglas candidatas para aprobar

Juan aprobó las ocho como comprobaciones el 17/11/2026. Aquí se cuentan las filas que las incumplen y no se cambia ni se quita ninguna. Pasarlas a las reglas de negocio va por la cascada.

- RC-01. Las horas encendido de un disco no bajan entre dos fotos. Columnas: `smart_9_raw`. Incumplen: 3.468 pares de fotos seguidas de un disco.
- RC-02. El modelo y la capacidad de un disco no cambian entre fotos. Columnas: `model`, `capacity_bytes`. Incumplen: 11.226 pares de fotos seguidas de un disco.
- RC-03. Los cinco contadores de avería no bajan con el tiempo en un mismo disco. Columnas: `smart_5_raw`, `smart_187_raw`, `smart_188_raw`, `smart_197_raw`, `smart_198_raw`. Incumplen: 26.852 pares de fotos seguidas de un disco.
- RC-04. La temperatura está entre 10 y 70 grados. Columnas: `smart_194_raw`. Incumplen: 9 filas.
- RC-05. Toda foto con failure = 1 está en la lista de fallos, el mismo disco y el mismo día. Columnas: `failure`, `serial_number`, `fecha`, `dia_fallo`. Incumplen: 0 filas.
- RC-06. En cada ventana, failure = 1 solo el día del fallo. Columnas: `failure`, `fecha`, `dia_fallo`. Incumplen: 0 filas.
- RC-07. En el recuento, los fallos no pasan de los discos de su fila. Columnas: `fallos`, `discos`. Incumplen: 0 filas.
- RC-08. Los fallos de cada día del recuento suman los de la lista de fallos de ese día. Columnas: `fallos`, `fecha`, `dia_fallo`. Incumplen: 0 días.

## 15. Resumen de problemas detectados

- **C-01** · bloque 3.2 · fotos mensuales · `(varias)`: 49 columnas vacías en más del 99 % de las filas que las traen.
- **C-02** · bloque 3.2 · esquema de Backblaze · `smart_211_normailized, smart_212_normailized`: 2 nombres con errata en el esquema.
- **C-03** · bloque 3.3 · fotos mensuales · `datacenter`: el centro llega sin tipo en 42 ficheros de fotos.
- **C-04** · bloque 3.3 · fotos mensuales · `pod_slot_num`: la ranura llega como decimal.
- **C-05** · bloque 3.4 · fotos mensuales · `capacity_bytes`: 2.729 filas con capacidad -1 o 0,1 TB; 2.729 de ellas sin ningún contador.
- **C-06** · bloque 3.4 · ventanas de fallo · `capacity_bytes`: 165 filas con capacidad -1 o 0,1 TB.
- **C-07** · bloque 3.4 · recuento diario · `capacity_bytes`: 2.102 filas con capacidad -1 o 0,1 TB, con 20 fallos.
- **C-08** · bloque 3.4 · recuento diario · `datacenter`: 84.647 filas con centro «sin dato», 4.551 desde el 01/07/2023.
- **C-09** · bloque 3.4 · fotos mensuales · `datacenter`: 235.772 filas sin dato desde el 01/07/2023; de discos de datos, 234.446.
- **C-10** · bloque 3.4 · fotos mensuales · `pod_slot_num`: 103.221 filas sin dato desde el 01/07/2023; de discos de datos, 1.613.
- **C-11** · bloque 3.4 · fotos mensuales · `cluster_id`: vale 0 en 4.781.548 de 6.885.677 filas que traen la columna. Cerrado el 2026-11-17 (D4): el 0 de cluster_id no se decide, porque ninguna pregunta usa esa columna: se cuenta y se dice.
- **C-12** · bloque 3.4 · fotos mensuales y ventanas de fallo · `(varias)`: 82 variables con los vacíos concentrados en algún segmento.
- **C-13** · bloque 3.5 · fotos mensuales, ventanas de fallo y recuento diario · `model`: 4 modelos escritos con dos espacios tras «WDC»; 3.285 discos salen con los dos nombres. Cerrado el 2026-11-17 (D1): los modelos que solo se distinguen por los dos espacios tras «WDC» son el mismo modelo; los junta la corrección.
- **C-14** · bloque 3.8 · fotos mensuales · `smart_188_raw`: 192.593 filas de discos de datos por encima de mil millones. Cerrado el 2026-11-17 (D2): el 188 cuenta como aviso cuando pasa de cero (reglas §3) y no entra en la suma de la regla de los contadores (reglas §7, CP-010).
- **C-15** · bloque 3.8 · fotos mensuales y ventanas de fallo · `smart_5_raw, smart_187_raw`: el 187 en 65.535 en 221 filas; el 5 llega a 65.529 en las fotos. Cerrado el 2026-11-17 (D3): el 5 y el 187 pegados a 65.535 son el tope del contador; el disco avisa igual.
- **C-16** · bloque 3.8 · ventanas de fallo · `smart_194_raw`: 9 filas por encima de 70 grados, con máximo de 117.
- **C-17** · bloque 3.9 · ventanas de fallo · `fecha, date`: 228 filas en que la fecha y su texto no coinciden: fecha 2022-12-10, texto 2022-12-11.
- **C-18** · bloque 3.10 · fotos mensuales · `smart_9_raw`: RC-01 incumplida: 3.468 veces bajan las horas entre dos fotos seguidas; 3.468 más de un día.
- **C-19** · bloque 3.10 · fotos mensuales · `model, capacity_bytes`: RC-02 incumplida: el modelo cambia 7.372 veces (1 sin contar las variantes de espacios) y la capacidad 3.854 (0 entre capacidades válidas).
- **C-20** · bloque 3.10 · fotos mensuales · `smart_5_raw, smart_187_raw, smart_188_raw, smart_197_raw, smart_198_raw`: RC-03 incumplida: smart_5_raw baja 575 veces en 413 discos; smart_187_raw baja 12 veces en 12 discos; smart_188_raw baja 1.650 veces en 1.650 discos; smart_197_raw baja 24.477 veces en 11.547 discos; smart_198_raw baja 10.055 veces en 5.517 discos.
- **C-21** · bloque 3.10 · fotos mensuales · `smart_9_raw`: 2.738 filas de discos de datos sin horas encendido.
- **C-22** · bloque 3.10 · lista de fallos · `dia_fallo`: 67 fallos antes de la primera foto de su disco.
- **C-23** · bloque 3.10 · lista de fallos · `serial_number`: 210 fallos de 210 discos que no salen en ninguna foto.
- **C-24** · bloque 3.10 · fotos mensuales · `serial_number`: 161 discos salen en alguna foto después de su fallo.
- **C-25** · bloque 3.10 · fotos mensuales · `serial_number`: 7.798 discos de datos faltan en alguna foto y vuelven.
- **C-26** · bloque 3.10 · fotos mensuales · `contadores en bruto`: 163 pares de modelo y contador con vacíos solo en parte de sus filas; suman 2.789.298 filas vacías.
- **C-27** · bloque 3.10 · ventanas de fallo · `pod_slot_num`: 13 fallos de discos de datos desde el 01/07/2023 sin ranura ningún día de su ventana.
- **C-28** · bloque 3.10 · ventanas de fallo · `datacenter, vault_id, pod_slot_num`: 141 fallos de discos de datos desde el 01/07/2023 sin tomo completo ningún día de su ventana.
- **C-29** · bloque 3.10 · ventanas de fallo · `fecha`: 896 fallos de discos de datos sin el día anterior en su ventana.
- **C-30** · bloque 3.10 · recuento diario · `discos`: 7 días hundidos del reconocimiento con discos de menos frente a sus vecinos.

## 16. Posibles acciones

Ninguna se ha ejecutado. La corrección mide primero si quitar o arreglar cada cosa cambia la respuesta a alguna pregunta del caso.

- C-01: la corrección decide si las deja fuera de las tablas de trabajo; ninguna es uno de los cinco contadores de avería
- C-02: nada en los datos; avisar al documentar las columnas
- C-03: leer el centro como texto al juntar los ficheros
- C-04: leerla como entero con vacíos
- C-05: tomar la capacidad del modelo (reglas §3); la corrección mide si quitarlas cambia la respuesta a alguna pregunta del caso por no traer contadores
- C-06: tomar la capacidad del modelo (reglas §3)
- C-07: tomar la capacidad del modelo y sumar las filas que quedan con la misma clave (reglas §3)
- C-08: contarlas y decirlas en las tasas por centro; no se apartan en silencio
- C-09: contarlas y decirlas en las cifras por centro y por tomo (reglas §7, población del análisis)
- C-10: contarlas y decirlas en las cifras por centro y por tomo (reglas §7, población del análisis)
- C-11: ninguna: ninguna pregunta usa la columna
- C-12: tenerlo en cuenta al comparar fabricantes, modelos o periodos con esas columnas
- C-13: la corrección junta cada variante con su modelo
- C-14: se lee como aviso si pasa de cero y no entra en la suma de la regla de los contadores; su valor como variable se mira en la preselección
- C-15: ninguna: el disco avisa igual
- C-16: la corrección mide si quitarlas cambia la respuesta a alguna pregunta del caso; son de discos a punto de fallar
- C-17: la corrección mide si quitar ese día cambia alguna respuesta; la lectura está en pendientes
- C-18: la corrección mide si quitarlas cambia la respuesta a alguna pregunta del caso
- C-19: la corrección mide si quitarlas cambia la respuesta a alguna pregunta del caso
- C-20: la corrección mide si quitarlas cambia la respuesta a alguna pregunta del caso
- C-21: la edad sale de la primera aparición en esos discos (reglas §3)
- C-22: tomar la primera aparición también de las ventanas
- C-23: la corrección mide si quitarlas cambia la respuesta a alguna pregunta del caso
- C-24: ninguna en los días de disco; en la supervivencia la vida acaba en el primer fallo
- C-25: no contarlos como desaparecidos; los meses que faltan no son días de disco
- C-26: la corrección mide si cambian alguna respuesta; si cambian, preguntar cómo se lee un vacío en un modelo que sí apunta el contador
- C-27: contarlos y decirlos en los fallos del mismo tomo (reglas §7)
- C-28: contarlos y decirlos en los fallos del mismo tomo (reglas §7, población del análisis)
- C-29: decir cuántos fallos no tienen día anterior al contar los fallos sin aviso
- C-30: mirar si cambian alguna tasa diaria; en tasas por trimestre o año pesan poco

## 17. Parámetros usados

- Límite del rango intercuartílico: 1,5 (por defecto; las reglas no fijan otro).
- Límite del z robusto: 3,5 (por defecto; las reglas no fijan otro).
- Segmento mínimo para el reparto de nulos: 30 (por defecto).
- Concentración de nulos en un segmento: 2 veces el porcentaje global (por defecto).
- Categoría rara: menos del 2,5 % de las filas o menos de 5 apariciones (diccionario-datos, el mismo que usó el diccionario del origen).
- Código de ausencia numérico candidato: un valor en un extremo del rango con el 5 % de las filas o más (por defecto; se fijó sin fuente y este caso es de los primeros que lo usan).
- Colas de cada magnitud: 10 (por defecto).
- Fecha de Excel candidata: no aplica (plan aprobado: ninguna fecha llega como número, vienen como fecha o como texto ISO).
- Horizonte de fechas futuras: 2025-06-30 (reglas de negocio §5, fecha de referencia).
- Columna casi vacía: más del 99 % de vacíos en las filas que traen la columna (plan aprobado, bloque 3.2).

El plan lo aprobó Juan el 2026-11-17.

## 18. Datos personales

- No existe contexto-proyecto/fuentes/proteccion-datos.json: los datos no pasaron por la protección.
- No hay datos de personas (reglas §9): el paso de protección se saltó el 17/11/2026 con el sí de Juan.
- El número de serie identifica un disco, no a una persona. Ninguna columna es un dato personal.
- Esta skill no usa ni deja columnas de datos personales.

## 19. Límites de esta revisión

- Relaciones revisadas en el bloque 3.11: lista de fallos con ventanas de fallo; lista de fallos con fotos mensuales; ventanas de fallo con fotos mensuales; recuento diario con fotos mensuales; recuento diario con ventanas de fallo; recuento diario con lista de fallos.
- Dimensiones del reparto de vacíos: el periodo, el fabricante, el año, disco de datos o de arranque y, en las columnas de sitio, antes y después del 01/07/2023; en los contadores, también el modelo. Un segmento que no se ha mirado puede esconder una concentración.
- Forma de la tabla (comprobaciones §1): no hay periodos repartidos en columnas ni dos datos en una celda (plan aprobado).
- Fecha de Excel: ninguna fecha llega como número: vienen como fecha o como texto ISO.
- Atípicos en códigos, notas normalizadas e identificadores: no son magnitudes (SKILL §3.8); la ranura, el centro, el vault, el servidor y el cluster son códigos.
- Códigos de ausencia en las notas normalizadas: son notas ordinales de cada fabricante: un valor alto en el extremo es la nota sana, no una ausencia.
- Cero como código de ausencia en los contadores en bruto: el cero es un valor del contador y el vacío es que el modelo no lo apunta (reglas §5).
- Colas, atípicos y objetivo en validación: en validación solo se cuentan filas, vacíos y formatos; nada se mira contra el fallo (reglas §7 y encargo).
- Rangos de negocio de la tabla «Lo esperable»: las reglas del caso no traen esa tabla.
- Texto libre: no hay columnas de texto libre; el modelo y el centro se miraron por si traían algo con forma de instrucción.
- Correlación entre variables: no es un bloque de la skill; las columnas calculadas a partir de otras se señalan en los riesgos para un modelo.
- Las 66 columnas del esquema que no traen los datasets: se quitaron al preparar los cuatro datasets; desde aquí no se puede saber si estaban vacías o eran constantes.
- Seguimiento de un disco día a día: de los discos que no fallan solo hay una foto al mes: huecos, horas y contadores que bajan tienen un mes de margen.

