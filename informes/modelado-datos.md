# Modelado de datos · caso 68

## Fuente

- Diseño: `config/modelo/modelo-datos.md`. Ejecución: 2026-11-18T07:39:20. Fecha de los datos: 2025-06-30.
- `data/processed/fotos_mensuales_corregido.parquet`: 14.851.669 filas, 130 columnas, huella `998d1edec335d5cf…`
- `data/processed/ventanas_fallo_corregido.parquet`: 536.597 filas, 131 columnas, huella `63d4379a89b96f54…`
- `data/processed/recuento_diario_corregido.parquet`: 197.871 filas, 6 columnas, huella `320f487a6a82bbd1…`
- `data/processed/fallos_corregido.parquet`: 17.960 filas, 2 columnas, huella `59e45676a6a7a2da…`

## Resumen

**Estado OK.** Diseño comprobado sobre las cuatro tablas: 15 cruces en el plan y 10 clases en el registro de exclusiones. Las cuatro claves de grano son únicas.

Siguiente: transformacion-datos, con el plan de cruces aprobado y los controles de integracion-datos

## Tablas y grano

| Tabla | Tipo | Grano | Clave | Filas | Clave única | Filas repetidas |
|---|---|---|---|---:|---|---:|
| hechos_fotos | hechos | un disco el día 1 de un mes: la foto mensual de cada disco en servicio | serial_number, fecha | 14.851.669 | sí | 0 |
| hechos_ventanas | hechos | un disco un día, dentro de los 30 días anteriores a uno de sus fallos o el del fallo | serial_number, fecha | 536.597 | sí | 0 |
| hechos_recuento | hechos | un día, un modelo, una capacidad y un centro: cuántos discos había y cuántos fallaron | fecha, model, capacity_bytes, datacenter | 197.871 | sí | 0 |
| hechos_fallos | hechos | un disco el día que Backblaze lo da por fallado | serial_number, dia_fallo | 17.960 | sí | 0 |
| dim_modelo | dimension | un modelo de disco | model |  | sin datos |  |
| dim_precio_gb | dimension | una capacidad un año: lo que costaba el GB | capacidad_tb, ano |  | sin datos |  |
| Calendario | dimension | un día, del primer al último día del recuento | fecha |  | sin datos |  |

- date distinta de fecha: 0 filas en las fotos y 0 en las ventanas.
- Discos con dos fallos: 12. Fallos sin ventana: 0; sin la fila del día del fallo: 0.
- Fallos de discos que no salen en ninguna foto: 210.
- Modelos: 94 en las fotos y 94 en el recuento (los mismos); 71 en las ventanas, 0 fuera del recuento. Con más de una capacidad: 0. De arranque 33 y de datos 61; entre 2 y 4 TB, 0.

## Relaciones

| Desde | Hacia | Clave | Maestro | Cardinalidad | Mismo tipo | Procedencia |
|---|---|---|---|---|---|---|
| hechos_fotos | dim_modelo | model → model | dim_modelo | N:1 | sí | reglas, apartado 3 (el modelo es la unidad de compra y la capacidad de un disco es la de su modelo); como_estan_organizados_los_datos.md (dimensión modelo) |
| hechos_ventanas | dim_modelo | model → model | dim_modelo | N:1 | sí | reglas, apartado 3 (el modelo es la unidad de compra y la capacidad de un disco es la de su modelo); como_estan_organizados_los_datos.md (dimensión modelo) |
| hechos_recuento | dim_modelo | model → model | dim_modelo | N:1 | sí | reglas, apartado 3 (el modelo es la unidad de compra y la capacidad de un disco es la de su modelo); como_estan_organizados_los_datos.md (dimensión modelo) |
| hechos_fotos | Calendario | fecha → fecha | Calendario | N:1 | sí | reglas, apartado 5 (cada registro es el estado de un disco un día; un día de disco es un disco un día) |
| hechos_ventanas | Calendario | fecha → fecha | Calendario | N:1 | sí | reglas, apartado 5 (cada registro es el estado de un disco un día; un día de disco es un disco un día) |
| hechos_recuento | Calendario | fecha → fecha | Calendario | N:1 | sí | reglas, apartado 5 (cada registro es el estado de un disco un día; un día de disco es un disco un día) |
| hechos_fallos | Calendario | dia_fallo → fecha | Calendario | N:1 | **no** (dia_fallo timestamp[ns] / fecha timestamp[ms]) | reglas, apartado 3 (un fallo es el día en que Backblaze da un disco por fallado) |
| hechos_ventanas | hechos_fallos | serial_number, dia_fallo → serial_number, dia_fallo | hechos_fallos | N:1 | sí | como_estan_organizados_los_datos.md (una ventana son los 30 días antes de un fallo y el del fallo); reglas, apartado 5 («salvo los 30 días antes de un fallo, que van día a día») |
| hechos_fallos | hechos_ventanas | serial_number, dia_fallo → serial_number, fecha | hechos_ventanas (su fila del día del fallo) | 1:1 | **no** (dia_fallo timestamp[ns] / fecha timestamp[ms]) | reglas, apartado 5 (un registro por disco y día, el del fallo incluido); como_estan_organizados_los_datos.md |
| hechos_fallos | dim_modelo | model → model | dim_modelo | N:1 | sí | reglas, apartado 3 (el modelo es la unidad de compra y la capacidad de un disco es la de su modelo); como_estan_organizados_los_datos.md (dimensión modelo); el modelo es el de la fila del día del fallo |
| hechos_fallos | dim_precio_gb | capacidad_tb, ano_fallo → capacidad_tb, ano | dim_precio_gb | N:1 | sin tipo aún | reglas, apartado 6 (el disco nuevo que sustituye a uno que falla, al coste por GB del año del fallo) |

## Fechas y calendario

- Recuento: del 2020-01-01 al 2025-06-30, 2008 días; faltan 0.
- Fotos: 66 meses, del 2020-01-01 al 2025-06-01; 0 fechas que no son día 1 y 0 meses que faltan.
- Ventanas: 2007 días; faltan 1 dentro de su rango (2022-12-10).
- Calendario: por día, del 2020-01-01 al 2025-06-30. Construido en `data/processed/calendario.parquet`.

## Registro de exclusiones

| Clase | Sale de | Cómo se trata | Recuperable | Recuentos |
|---|---|---|---|---|
| los discos de 0,2 a 2 TB, con sus fotos, días de disco y fallos | todas las tasas, rankings, coste por terabyte, previsión y la pregunta 4 | fuera de todo cálculo; se pueden contar aparte | sí: siguen en las tablas y se cuentan aparte si una petición lo pide | modelos: 33; filas_fotos: 246280; filas_ventanas: 28546; dias_de_disco: 7500739; fallos_recuento: 964 |
| los días de disco y fallos de discos de datos antes del 01/07/2023, sin centro | tasas por centro y fallos del mismo tomo (pregunta 3) | fuera de las cifras por sitio; siguen en las demás | no: el sitio no está en los datos | dias_de_disco: 238811405; fallos_recuento: 8362; fallos_lista: 8362; filas_fotos_sin_centro: 7821320 |
| los días de disco y fallos de discos de datos desde el 01/07/2023 con el centro «sin dato» | tasas por centro (pregunta 3) | se cuentan y se dicen (reglas, apartado 5) | no, con estos datos | dias_de_disco: 6621213; fallos_recuento: 128; dias_de_disco_desde: 207297278; filas_fotos_sin_centro: 234446 |
| los fallos de discos de datos desde el 01/07/2023 sin ningún día de su ventana, hasta el del fallo, con centro (sin centro) o con centro, vault y ranura (sin tomo) | tasas por centro (sin centro) y fallos del mismo tomo (sin tomo), pregunta 3 y aviso de tomos en peligro de la pregunta 4 | se cuentan y se dicen (reglas, apartado 5) | no, con estos datos | fallos_desde: 8634; fallos_sin_centro: 128; fallos_sin_tomo: 141 |
| los fallos de discos de datos cuya ventana no trae el día anterior al fallo | el indicador de fallos sin aviso | fuera del indicador; se cuentan y se dicen | no: el día no está en los datos | fallos_de_datos: 16996; fallos: 903 |
| los modelos de datos con menos de 50.000 días de disco en el año | los rankings de modelos (preguntas 1 y 2, bloque 2) | se enseñan aparte con su recuento (reglas, apartado 7) | sí: se enseñan aparte; no entran en el ranking | minimo_dias_ano: 50000; modelos_de_datos: 61; modelos_que_pasan_algun_ano: 32 |
| los años de edad, de todos los discos o de un modelo, con menos de 20 fallos | la conclusión de la pregunta 2 (a qué edad sube la tasa) | se enseñan sin conclusión (reglas, apartado 7, cuestión 009) | sí: se enseñan, sin conclusión | todos_anos: 0; todos_fallos: 0; celdas_modelo_edad: 99; celdas_modelo_edad_total: 207; fallos_en_esas_celdas: 462; fallos_con_edad_por_primera_aparicion: 79 |
| las fotos de discos de datos con failure = 1, del mismo día del fallo | el tablón de la pregunta 4 | fuera del tablón; su fallo sigue siendo objetivo de la foto anterior si cae en su horizonte | no: no hay nada que predecir en ellas | filas: 528; construccion: 373; validacion: 155 |
| los fallos que caen después del último día del periodo de la foto | el objetivo de la pregunta 4 | el horizonte se recorta al borde del periodo (reglas, apartado 7: «se recorta o se queda fuera») | el de construcción, no sin mezclar periodos; el de validación, solo con la reserva |  |
| las 228 filas de las ventanas fechadas el 10/12/2022 que eran copia del 11/12/2022 | las ventanas de fallo, ya en la corrección (R-007) | quitadas en la corrección; ninguna traía un fallo | no: eran copias; siguen en data/raw/ | filas: 228; fecha: 2022-12-10; fuente: informes/correccion-datos.json, controles |

Modelos de datos por debajo del mínimo, por año:

- 2020: 23 de 40 modelos, con 179.804 días de disco y 7 fallos; el año tiene 366 días en los datos.
- 2021: 23 de 46 modelos, con 168.365 días de disco y 13 fallos; el año tiene 365 días en los datos.
- 2022: 23 de 49 modelos, con 215.789 días de disco y 18 fallos; el año tiene 365 días en los datos.
- 2023: 29 de 57 modelos, con 256.863 días de disco y 33 fallos; el año tiene 365 días en los datos.
- 2024: 29 de 60 modelos, con 222.848 días de disco y 25 fallos; el año tiene 366 días en los datos.
- 2025: 20 de 47 modelos, con 238.499 días de disco y 5 fallos; el año tiene 181 días en los datos.

## Población de la pregunta 4

- Filas del tablón: 14.604.861 (11.026.052 de construcción y 3.578.809 de validación).
- Foto del 2024-06-01 (construcción): se recorta al 2024-06-30. De 401 fallos de discos de la foto en su horizonte, el recorte pierde 16.
- Foto del 2025-06-01 (validación): se recorta al 2025-06-30; el horizonte entero pasa del último día de los datos: lo que se pierde no se puede saber hasta la prueba final.

## Plan de cruces

| Orden | Partida | Se une | Clave | Cardinalidad | Antes de cruzar | Control |
|---:|---|---|---|---|---|---|
| 1 | hechos_fallos | hechos_ventanas | serial_number, dia_fallo → serial_number, fecha | 1:1 | ventanas filtradas a la fila con fecha = dia_fallo: una por fallo | filas de hechos_fallos |
| 2 | hechos_fallos | hechos_ventanas | serial_number, dia_fallo → serial_number, fecha | 1:1 | ventanas filtradas a la fila con fecha = dia_fallo - 1 día: una por fallo, o ninguna | filas de hechos_fallos |
| 3 | hechos_fallos | hechos_ventanas | serial_number, dia_fallo → serial_number, dia_fallo | 1:1 | por fallo, la última fila de su ventana hasta el día del fallo que trae centro (para las tasas por centro) y la última que trae centro, vault, servidor y ranura (para el tomo): una por fallo | filas de hechos_fallos |
| 4 | hechos_fallos | dim_modelo | model → model | N:1 | — | filas de hechos_fallos |
| 5 | hechos_fallos | dim_precio_gb | capacidad_tb, ano_fallo → capacidad_tb, ano | N:1 | — | filas de hechos_fallos |
| 6 | hechos_fallos | Calendario | dia_fallo → fecha | N:1 | — | filas de hechos_fallos |
| 7 | hechos_recuento | dim_modelo | model → model | N:1 | — | discos, fallos |
| 8 | hechos_recuento | Calendario | fecha → fecha | N:1 | — | discos, fallos |
| 9 | hechos_fotos | dim_modelo | model → model | N:1 | — | filas de hechos_fotos |
| 10 | hechos_fotos | Calendario | fecha → fecha | N:1 | — | filas de hechos_fotos |
| 11 | hechos_fotos | hechos_recuento | model, datacenter, mes → model, datacenter, mes | N:1 | fotos: discos por modelo, centro (el vacío como «sin dato»), mes y tramo (edad, aviso) y su parte dentro de modelo, centro y mes; recuento: días de disco (discos sumados por día) y fallos por modelo, centro y mes. Los días de cada tramo son la parte de la foto por los días del recuento | días de disco del recuento |
| 12 | hechos_fotos | hechos_fallos | serial_number, fecha → serial_number, fecha_foto | N:1 | por fallo, las fechas de las fotos de su disco con fecha < dia_fallo <= fecha + 30 días, con el horizonte recortado al último día del periodo de la foto; una fila por (serial_number, fecha_foto) | filas del tablón de la pregunta 4, objetivo: pares foto-fallo distintos |
| 13 | hechos_fallos | hechos_fotos | serial_number, fecha_foto → serial_number, fecha | N:1 | a cada fallo, la fecha de la última foto de su disco anterior al fallo dentro de su horizonte | filas de hechos_fallos |
| 14 | hechos_fotos | hechos_recuento | model, ano_edad, trimestre → model, ano_edad, trimestre | N:1 | fotos del primer día de cada trimestre (discos de datos), contadas por modelo y año de edad; tasas por modelo y año de edad con los días (cruce 11) y los fallos (cruces 1 y 4) hasta el día anterior al trimestre | discos del primer día del trimestre |
| 15 | hechos_recuento | hechos_fallos | model, datacenter, mes, tramo → model, datacenter, mes, tramo | 1:1 | días de disco repartidos (cruce 11) y fallos (cruces 1, 3 y 4) agregados al mismo grano; los fallos sin días en su celda son huérfanas que cuenta integracion-datos | días de disco, fallos |

## Decisiones pendientes

- Ninguna.

## Datos personales

- No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección.
- No hay datos de personas (reglas, apartado 9): el número de serie identifica un disco, no a una persona.
- Este método no usa ni deja ninguna columna de datos personales.

## Teoría aplicada

- 9.5, granularidad y cardinalidad: el grano de cada tabla y la cardinalidad de cada relación salen de las reglas y de la organización de los datos, no de los datos que se validan.
- 12.5 y 12.6, cambiar el nivel: los días de disco se suman (flujo) y la foto del mes reparte (nivel); los hechos de grano distinto se llevan al grano común antes de unirse.
- 14.9, regularizar una serie: el Calendario es diario y continuo; el recuento no tiene días que falten.

## Límites

- El script comprueba el grano y los tipos de las claves; si las claves casan entre tablas lo mide integracion-datos o la transformación con sus controles.
- En pandas, a diferencia de SQL, las claves vacías se emparejan entre sí al cruzar: el centro vacío de fotos y ventanas se iguala a «sin dato» antes de cruzar con el recuento.
- Un maestro que cambia con el tiempo se modela con la versión que hay: la fecha de compra y el precio de cada modelo se calculan con todo el periodo, como una ficha de hoy.
- La edad al fallar del registro de exclusiones usa las horas del día del fallo o del anterior y, sin ellas, la primera aparición; la regla exacta la fija la transformación.
