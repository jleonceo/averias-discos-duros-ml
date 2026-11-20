# Informe de transformación de datos

**Estado: OK.** Nueve tablas en data/processed/: 14.604.861 fotos de riesgo, 17.960 fallos y 402.643 discos, con todas las validaciones en verde. Ninguna celda queda pendiente.

## Fuente

- **Entrada:** `data/processed/fotos_mensuales_corregido.parquet`, 14.851.669 filas y 130 columnas, huella `998d1edec335…`.
- **Entrada:** `data/processed/ventanas_fallo_corregido.parquet`, 536.597 filas y 131 columnas, huella `63d4379a89b9…`.
- **Entrada:** `data/processed/recuento_diario_corregido.parquet`, 197.871 filas y 6 columnas, huella `320f487a6a82…`.
- **Entrada:** `data/processed/fallos_corregido.parquet`, 17.960 filas y 2 columnas, huella `59e45676a6a7…`.
- **Entrada:** `data/processed/calendario.parquet`, 2.008 filas y 7 columnas, huella `e76a8d082426…`.
- **Salida:** las nueve tablas de `data/processed/` que lista «Dataset generado».
- **Contexto:** `contexto-proyecto/negocio/reglas-transformacion.md` (aprobado el 17/11/2026), `reglas-negocio.md`, `modelo/modelo-datos.md`, el plan de cruces de `informes/modelado-datos.json` y `sector/precios_de_coste_discos.md`.
- **Ejecución:** 2026-11-17T20:06:35, con Python 3.13.15, pandas 3.0.6 y pyarrow 24.0.0. Fecha de los datos: 2025-06-30.

## Objetivo

Preparar las tablas con las que el análisis contesta las cuatro preguntas del caso: dos dimensiones de modelo y precio, la tabla de fotos con el objetivo a 30 días para el modelo de la pregunta 4, el detalle de cada fallo, la vida de cada disco y cuatro agregados de días de disco y fallos. No se calcula ninguna tasa, ranking ni modelo.

## Transformaciones aplicadas

- **T-01 · Igualar las claves antes de cruzar, sin guardarlo en las tablas corregidas** (reglas de transformación, «De qué se parte»): 17.960 fallos cruzados con dia_fallo en milisegundos; el centro vacío como «sin dato» al cruzar fotos y ventanas con el recuento. Ficha R-010.
- **T-02 · Construir dim_modelo** (reglas de transformación §1): 94 modelos, 57 con precio. Ficha R-011.
- **T-03 · Construir dim_precio_gb** (reglas de transformación §1): 66 filas. Ficha R-012.
- **T-04 · Construir fotos_riesgo bloque a bloque** (reglas de transformación §3): 14.604.861 filas, 16.266 con objetivo 1. Ficha R-013.
- **T-05 · Construir fallos_detalle** (reglas de transformación §4): 17.960 fallos. Ficha R-014.
- **T-06 · Construir vida_discos** (reglas de transformación §5): 402.643 discos. Ficha R-015.
- **T-07 · Construir dias_por_tramo** (reglas de transformación §6): 13.275 filas. Ficha R-016.
- **T-08 · Construir inicio_trimestre** (reglas de transformación §7): 3.117 filas. Ficha R-017.
- **T-09 · Construir modelo_trimestre** (reglas de transformación §8): 1.028 filas. Ficha R-018.
- **T-10 · Construir centro_mes** (reglas de transformación §9): 186 filas. Ficha R-019.

## Variables generadas

Marcas: (P) usa información posterior a la fila; (O) sale del objetivo; (S) es suma o resta de otras.

- `capacidad_tb`: capacity_bytes / 10^12, a un decimal. De `capacity_bytes`.
- `tipo_disco`: arranque hasta 2.048.408.248.320 bytes; datos por encima. De `capacity_bytes`.
- `fabricante`: prefijo del modelo y dos excepciones (reglas §3). De `model`.
- `garantia_anos`: familia del modelo (reglas §6). De `model`.
- `fecha_compra` (P): media de (primera foto - horas encendido) de los discos del modelo; ficha de hoy. De `fecha`, `smart_9_raw`.
- `coste_gb_compra` (P): coste por GB de su capacidad en su fecha de compra (curva, inferido o vecinas). De `capacidad_tb`, `fecha_compra`.
- `precio_usd` (P): coste_gb_compra × capacidad_tb × 1.000; ficha de hoy. De `coste_gb_compra`, `capacidad_tb`.
- `origen_precio` (P): curva, inferido o vecinas. De `fecha_compra`.
- `coste_gb`: coste por GB de la capacidad el 1 de julio del año. De `capacidad_tb`, `ano`.
- `edad_anos`: smart_9_raw / 8.766; sin horas, días desde la primera aparición / 365,25. De `smart_9_raw`, `fecha`.
- `edad_de_horas`: smart_9_raw no vacío. De `smart_9_raw`.
- `avisa`: algún contador de avería > 0; un vacío no cuenta. De `smart_5_raw`, `smart_187_raw`, `smart_188_raw`, `smart_197_raw`, `smart_198_raw`.
- `contadores_que_avisan` (S): cuántos de los cinco contadores > 0. De `smart_5_raw`, `smart_187_raw`, `smart_188_raw`, `smart_197_raw`, `smart_198_raw`.
- `suma_contadores_sin_188` (S): smart_5 + smart_187 + smart_197 + smart_198 sin los vacíos; vacía si los cuatro lo están. De `smart_5_raw`, `smart_187_raw`, `smart_197_raw`, `smart_198_raw`.
- `smart_188_no_cero`: 1 si smart_188 > 0, 0 si vale 0, vacío si no consta. De `smart_188_raw`.
- `cambio_smart_5` (S): smart_5_raw - smart_5_raw de la foto anterior del mismo disco. De `smart_5_raw`.
- `cambio_smart_187` (S): smart_187_raw - smart_187_raw de la foto anterior del mismo disco. De `smart_187_raw`.
- `cambio_smart_197` (S): smart_197_raw - smart_197_raw de la foto anterior del mismo disco. De `smart_197_raw`.
- `cambio_smart_198` (S): smart_198_raw - smart_198_raw de la foto anterior del mismo disco. De `smart_198_raw`.
- `meses_desde_foto_anterior`: meses entre la foto y la anterior del mismo disco. De `fecha`.
- `capacidad_tb, fabricante, garantia_anos`: de dim_modelo (cruce 9). De `model`.
- `periodo`: el del Calendario en la fecha de la foto (cruce 10). De `fecha`.
- `horizonte_hasta` (P): fecha + 30 días, recortado al último día de su periodo. De `fecha`, `periodo`.
- `falla_30d` (PO): 1 si el disco tiene un fallo con fecha < dia_fallo <= horizonte_hasta (cruce 12). De `serial_number`, `fecha`, `dia_fallo`.
- `horas_al_fallar`: horas del día del fallo o, si no las trae, del anterior. De `smart_9_raw`.
- `edad_al_fallar_anos`: horas_al_fallar / 8.766; sin horas, días desde la primera aparición / 365,25. De `horas_al_fallar`, `dia_fallo`.
- `en_garantia`: edad_al_fallar_anos < garantia_anos; falso sin garantía comprobada. De `edad_al_fallar_anos`, `garantia_anos`.
- `hay_dia_anterior, avisa_dia_anterior, sin_aviso`: la fila del día anterior de la ventana y sus cinco contadores. De `smart_5_raw`, `smart_187_raw`, `smart_188_raw`, `smart_197_raw`, `smart_198_raw`.
- `tomo`: centro|vault|ranura de la última fila con los cuatro datos de sitio. De `datacenter`, `vault_id`, `pod_id`, `pod_slot_num`.
- `plazo_reconstruccion_dias` (S): capacidad_tb + 1. De `capacidad_tb`.
- `dias_desde_anterior_del_tomo, coincide_con_anterior` (S): días desde el fallo anterior del tomo; coincide si son menos que su plazo. De `tomo`, `dia_fallo`.
- `precio_nuevo_usd`: coste_gb del año del fallo × capacidad_tb × 1.000 (cruce 5). De `capacidad_tb`, `dia_fallo`.
- `coste_fallo_usd` (S): precio_nuevo_usd + 37. De `precio_nuevo_usd`.
- `coste_fallo_garantia_usd`: 37 si en_garantia; si no, coste_fallo_usd. De `coste_fallo_usd`, `en_garantia`.
- `ultima_foto_anterior`: última foto del disco anterior al fallo (cruce 13). De `fecha`.
- `objetivo_de_alguna_foto` (PO): el fallo está en el horizonte de alguna fila de fotos_riesgo. De `falla_30d`.
- `periodo, ano, trimestre, mes, primer_fallo_del_disco`: del Calendario en dia_fallo (cruce 6); el primer fallo de cada disco. De `dia_fallo`.
- `primera_aparicion, edad_entrada_anos`: primera foto o primer día de ventana; su edad ese día. De `fecha`, `smart_9_raw`.
- `ultima_foto, primer_fallo, evento, fecha_fin, edad_fin_anos` (P): última foto; primer fallo; fallo, desaparece o sigue. De `fecha`, `dia_fallo`.
- `avisa_ultima_foto, desaparece_avisando` (P): aviso en la última foto; desaparece y avisaba. De `smart_5_raw`, `smart_187_raw`, `smart_188_raw`, `smart_197_raw`, `smart_198_raw`.
- `fotos, dias_disco, fallos, desaparecen_avisando`: fotos por celda; días del recuento repartidos por sus fotos (cruce 11); fallos (cruce 15). De `discos`, `fallos`.
- `discos, dias_trimestre`: discos de la foto del primer día del trimestre; días del trimestre. De `fecha`.
- `dias_disco, fallos, fallos_en_garantia, coste_fallos_usd, coste_fallos_garantia_usd, dias_disco_ano, pasa_minimo_ano`: sumas del recuento y de fallos_detalle; mínimo de 50.000 días en el año. De `discos`, `dia_fallo`.
- `dias_disco, fallos, periodo, con_sitio`: sumas del recuento; con_sitio desde julio de 2023. De `discos`, `fallos`.

`falla_30d` no se suma entre filas para contar fallos: un fallo puede ser objetivo de dos fotos. Los fallos se cuentan en `fallos_detalle`.

## Transformaciones pendientes

- Ninguna: cada columna de las reglas de transformación se llenó con su regla.

## Cambios estructurales

- De «un disco el día 1 de un mes (fotos)» a «un disco de datos en una foto mensual, sin la foto del día en que falla»:
  - filas: fotos de datos menos las del día del fallo: 14.604.861 antes y 14.604.861 después; coinciden.
- De «un disco un día de la ventana de un fallo, y la lista de fallos» a «un fallo de la lista: un disco el día que Backblaze lo da por fallado»:
  - fallos de la lista: 17.960 antes y 17.960 después; coinciden.
- De «fotos y ventanas» a «un disco de datos que sale en alguna foto o en alguna ventana»:
  - discos de datos distintos: 402.643 antes y 402.643 después; coinciden.
- De «un día, un modelo, una capacidad y un centro (recuento)» a «un modelo de datos, un centro, un mes y un año de edad cumplido»:
  - días de disco de las celdas con foto: 445.189.491 antes y 445.189.491 después; coinciden.
  - fallos de discos de datos de la lista: 16.996 antes y 16.996 después; coinciden.
- De «fotos del primer día de cada trimestre» a «un trimestre, un modelo de datos y un año de edad cumplido, el primer día del trimestre»:
  - discos de datos de esas fotos: 4.805.590 antes y 4.805.590 después; coinciden.
- De «un día, un modelo, una capacidad y un centro (recuento)» a «un modelo de datos en un trimestre»:
  - días de disco de datos: 446.108.683 antes y 446.108.683 después; coinciden.
  - fallos de discos de datos de la lista: 16.996 antes y 16.996 después; coinciden.
- De «un día, un modelo, una capacidad y un centro (recuento)» a «un centro de datos en un mes, solo discos de datos»:
  - días de disco de datos: 446.108.683 antes y 446.108.683 después; coinciden.
  - fallos del recuento de discos de datos: 16.996 antes y 16.996 después; coinciden.

| Cruce | Etiqueta | Cardinalidad esperada | Observada | Filas antes | Filas después | Sin pareja en la partida | Hecho |
|---:|---|---|---|---:|---:|---:|---|
| 7 | recuento | N:1 | N:1 | 197.871 | 197.871 | 0 | sí |
| 8 | recuento | N:1 | N:1 | 197.871 | 197.871 | 0 | sí |
| 1 | fallos_detalle, día del fallo | 1:1 | 1:1 | 17.960 | 17.960 | 0 | sí |
| 2 | fallos_detalle, día anterior | 1:1 | 1:1 | 17.960 | 17.960 | 910 | sí |
| 3 | fallos_detalle, último día con centro | 1:1 | 1:1 | 17.960 | 17.960 | 9.259 | sí |
| 3 | fallos_detalle, último día con ranura | 1:1 | 1:1 | 17.960 | 17.960 | 9.467 | sí |
| 4 | fallos_detalle | N:1 | N:1 | 17.960 | 17.960 | 0 | sí |
| 5 | fallos_detalle | N:1 | N:1 | 17.960 | 17.960 | 964 | sí |
| 6 | fallos_detalle | N:1 | N:1 | 17.960 | 17.960 | 0 | sí |
| 9 | fotos | N:1 | N:1 | 14.851.669 | 14.851.669 | 0 | sí |
| 10 | fotos | N:1 | N:1 | 14.851.669 | 14.851.669 | 0 | sí |
| 13 | fallos y fotos | N:1 | N:1 | 1.185.360 | 1.185.360 | 624.405 | sí |
| 12 | fotos_riesgo | N:1 | 1:1 | 14.604.861 | 14.604.861 | 14.588.595 | sí |
| 9 | vida_discos | N:1 | N:1 | 408.418 | 408.418 | 0 | sí |
| 13 | vida_discos | N:1 | 1:1 | 402.643 | 402.643 | 385.659 | sí |
| 11 | dias_por_tramo | N:1 | N:1 | 13.211 | 13.211 | 0 | sí |
| 15 | dias_por_tramo | 1:1 | 1:1 | 13.211 | 13.275 | 9.932 | sí |
| 10 | inicio_trimestre | N:1 | N:1 | 3.117 | 3.117 | 0 | sí |
| 14 | inicio_trimestre | N:1 | 1:1 | 995 | 995 | 0 | sí |
| 15 | modelo_trimestre | 1:1 | 1:1 | 1.028 | 1.028 | 477 | sí |
| 7 | modelo_trimestre | N:1 | N:1 | 1.028 | 1.028 | 0 | sí |
| 8 | centro_mes | N:1 | N:1 | 186 | 186 | 0 | sí |

## Validación

- cada bloque de las fotos es un mes y van en orden de fecha: pasa.
- ninguna edad negativa ni vacía en las fotos: pasa.
- cada columna de fotos_riesgo está en un solo grupo: pasa.
- ningún modelo de las fotos sin fila en dim_modelo: pasa.
- ningún tipo de disco ni evento sin regla: pasa.
- ningún cruce gana filas: pasa.
- todas las sumas de control de los cruces coinciden: pasa.
- todas las sumas de control de los cambios de granularidad coinciden: pasa.
- dim_modelo: clave model única: pasa.
- dim_precio_gb: clave capacidad_tb, ano única: pasa.
- fallos_detalle: clave serial_number, dia_fallo única: pasa.
- vida_discos: clave serial_number única: pasa.
- dias_por_tramo: clave model, centro, mes, edad_anos_cumplidos única: pasa.
- inicio_trimestre: clave ano, trimestre, model, edad_anos_cumplidos única: pasa.
- modelo_trimestre: clave model, ano, trimestre única: pasa.
- centro_mes: clave datacenter, mes única: pasa.
- fotos_riesgo: clave serial_number, fecha única (cada bloque es una fecha distinta): pasa.
- las huellas de las tablas corregidas son las mismas al terminar: pasa.

**Comprobaciones de las reglas** (no paran el guardado; si una no pasa, el estado es AVISO):

- los fallos de cada centro desde el 01/07/2023 son los mismos en fallos_detalle y en el recuento: pasa. ams5: 476; iad1: 512; phx1: 2160; sac0: 2806; sac2: 2546; sin dato: 128; yyz1: 6.
- en cada fila de modelo_trimestre, los fallos de la lista son los del recuento: pasa. 1.028 de 1.028 filas.
- el primer día de cada trimestre, los discos de la foto son los del recuento, modelo a modelo: pasa. 22 de 22 trimestres.
- todos los fallos tienen la fila del día del fallo en su ventana: pasa. 0 sin ella.
- cada disco que desaparece avisando tiene su fila en dias_por_tramo: pasa. 0 sin fila.

## Registro de exclusiones

| Clase | Qué sale | De qué cálculo | Recuentos |
|---|---|---|---|
| discos de arranque | los discos de 0,2 a 2 TB | todo cálculo | dias de disco: 7.500.739; fallos: 964; fotos: 246.280 |
| sitio antes | días y fallos de discos de datos antes del 01/07/2023 | lo que va por centro y por tomo | dias de disco: 238.811.405; fallos: 8.362 |
| centro sin dato desde | días y fallos con el centro «sin dato» desde el 01/07/2023 | las tasas por centro | dias de disco: 6.621.213; fallos: 128 |
| fallos sin tomo desde | fallos de discos de datos sin tomo desde el 01/07/2023 | los tomos y el aviso de tomos en peligro | fallos: 141 |
| fallos sin dia anterior | fallos de discos de datos sin el día anterior en su ventana | el indicador de fallos sin aviso | fallos: 903 |
| fotos del dia del fallo | fotos de discos de datos con failure = 1 | fotos_riesgo | fotos: 528 |
| fallos sin objetivo | fallos de discos de datos que no son objetivo de ninguna foto | el objetivo de fotos_riesgo | fallos: 808; dia 1 tras mes de 31 dias: 291; mas de 31 dias tras la ultima foto: 222; de discos sin foto: 193; antes de la primera foto: 78; recorte del horizonte: 16; otros: 8 |
| dias sin foto | días de disco de celdas del recuento sin ninguna foto en su modelo, centro y mes | dias_por_tramo | dias de disco: 919.192; celdas: 110; fallos recuento: 26 |
| modelos sin precio | modelos de datos sin precio | el coste por TB y año | modelos: 4; dias de disco: 18.840 |

Fallos sin objetivo que no caen en ninguna clase, uno a uno:

- `AAG26PSH`, fallo el 2023-12-02, última foto anterior 2023-11-01.
- `2AGNEDPY`, fallo el 2024-03-03, última foto anterior 2024-02-01.
- `2AGHB9XY`, fallo el 2024-12-02, última foto anterior 2024-11-01.
- `AAG6NW6H`, fallo el 2024-12-02, última foto anterior 2024-11-01.
- `AAGA4XDH`, fallo el 2024-12-02, última foto anterior 2024-11-01.
- `X8H0A03CF97G`, fallo el 2025-05-02, última foto anterior 2025-04-01.
- `ZA171VP0`, fallo el 2025-05-02, última foto anterior 2025-04-01.
- `ZLW0H32E`, fallo el 2025-05-02, última foto anterior 2025-04-01.

Los modelos que no llegan al mínimo y los años de edad con menos de 20 fallos no salen de ninguna tabla: se marcan y el análisis los enseña aparte. Las 228 filas que quitó la corrección están en R-007.

## Dataset generado

- `data/processed/dim_modelo.parquet`: 94 filas y 10 columnas; una fila es un modelo de disco.
- `data/processed/dim_precio_gb.parquet`: 66 filas y 5 columnas; una fila es una capacidad de datos en un año: lo que costaba el GB el 1 de julio.
- `data/processed/fotos_riesgo.parquet`: 14.604.861 filas y 144 columnas; una fila es un disco de datos en una foto mensual, sin la foto del día en que falla.
- `data/processed/fallos_detalle.parquet`: 17.960 filas y 32 columnas; una fila es un fallo de la lista: un disco el día que Backblaze lo da por fallado.
- `data/processed/vida_discos.parquet`: 402.643 filas y 11 columnas; una fila es un disco de datos que sale en alguna foto o en alguna ventana.
- `data/processed/dias_por_tramo.parquet`: 13.275 filas y 8 columnas; una fila es un modelo de datos, un centro, un mes y un año de edad cumplido.
- `data/processed/inicio_trimestre.parquet`: 3.117 filas y 8 columnas; una fila es un trimestre, un modelo de datos y un año de edad cumplido, el primer día del trimestre.
- `data/processed/modelo_trimestre.parquet`: 1.028 filas y 15 columnas; una fila es un modelo de datos en un trimestre.
- `data/processed/centro_mes.parquet`: 186 filas y 6 columnas; una fila es un centro de datos en un mes, solo discos de datos.

## Datos personales

- No existe contexto-proyecto/fuentes/proteccion-datos.json: los datos no pasaron por la protección.
- No hay datos de personas (reglas §9): el número de serie identifica un disco, no a una persona.
- Esta transformación no usa ni deja ninguna columna de datos personales.

## Pendiente para el modelo

- **Partición** por `fecha`: desarrollo del 2020-01-01 al 2024-06-30 y validación del 2024-07-01 al 2025-06-30, los dos días incluidos (reglas-negocio §7). Ninguna fila de fotos_riesgo queda fuera de los dos tramos.
- `model` (categorica, grupo del modelo): 61 valores, sin orden real.
- `fabricante` (categorica, grupo del modelo): 4 valores, sin orden real.
- `datacenter` (categorica, grupo sitio): 6 valores, sin orden real.
- `vault_id` (codigo numerico, grupo sitio): 247 valores, sin orden real.
- `pod_id` (codigo numerico, grupo sitio): 20 valores, sin orden real.
- `pod_slot_num` (codigo numerico, grupo sitio): 60 valores, sin orden real.
- `edad_de_horas` (binaria, grupo conocidas el dia de la foto): dos valores, sin orden real.
- `avisa` (binaria, grupo conocidas el dia de la foto): dos valores, sin orden real.
- `smart_188_no_cero` (binaria, grupo conocidas el dia de la foto): dos valores, sin orden real.
- 130 magnitudes, con su unidad y su rango en `pendiente_modelo` del JSON; las de la foto que no están en las reglas van en el grupo «no previstas», y la preselección del paso 5 decide cuáles entran.

## Teoría aplicada

- 11.9, retardos: el cambio de un contador y los meses desde la foto anterior se calculan dentro de cada disco, con las fotos en orden de fecha; la foto anterior se guarda de un bloque al siguiente.
- 13.9, primero y último de cada grupo: la primera aparición, la última foto y el último día de la ventana con sitio se toman de la fila real, ordenada por fecha, no con first(), que salta los vacíos.
- 14.7, tiempo transcurrido: la edad, los días entre fallos del mismo tomo y los meses entre fotos se miden en unidades totales (horas entre 8.766, días entre 365,25), no con las partes de la fecha.
- 12.6 y 11.14, cambiar el nivel: los días de disco y los fallos son flujos y se suman; cada agregación cuadra sus sumas antes y después, y las variables que usan información posterior quedan marcadas.
- Skill, «Agregar por tiempo»: en un flujo, una celda sin registros vale cero solo si se sabe que no hubo nada; las filas de dias_por_tramo que solo tienen fallos dejan sus días de disco vacíos.

## Límites

- La fecha de compra y el precio de dim_modelo son una ficha de hoy, calculada con todo el periodo: no entran en fotos_riesgo.
- En las tablas agregadas, «mes» es el primer día del mes y la clave de trimestre lleva el año al lado («ano» y «trimestre» del Calendario), porque el trimestre del Calendario va de 1 a 4.
- suma_contadores_sin_188 queda vacía cuando los cuatro contadores lo están: un contador vacío no es un cero (reglas §5).
- coincide_con_anterior queda vacía cuando no hay días desde el anterior del tomo (el primero de su tomo o sin tomo), como dias_desde_anterior_del_tomo.
- En dias_por_tramo, las filas que solo tienen fallos dejan sus días de disco vacíos: hubo discos, pero ninguna foto con que repartir sus días.
- Las fotos de dias_por_tramo e inicio_trimestre son todas las de discos de datos, también la del día del fallo, porque ese día el disco está en servicio y cuenta como día de disco.
- No se calcula ninguna tasa, intervalo, ranking ni previsión: es el análisis de las preguntas 1 a 3.
