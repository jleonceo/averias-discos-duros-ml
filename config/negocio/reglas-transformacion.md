---
titulo: Reglas de transformación del caso 68 · dos dimensiones y siete tablas para el análisis, de una fila por disco y foto a una por centro y mes
estado: aprobado por el responsable del caso el 17/11/2026 («Sí, las apruebo»). Escrito con el diseño del modelo de datos aprobado y medido sobre las tablas corregidas
fecha_documento: 2026-11-17
dueno: El responsable del caso (decide)
fuentes: `reglas-negocio.md` §3 a §7; `01_ficha_del_caso.md`; `cuestiones-pendientes.md` (cuestión 001 a cuestión 011); `../modelo/modelo-datos.md` (aprobado el 17/11/2026) e `informes/modelado-datos.json`; `../modelo/registro-transformaciones.md` (R-001 a R-009); `../sector/precios_de_coste_discos.md`; `../metodo/plan_de_la_analitica.md`
---

# Reglas de transformación del proyecto

> Este fichero lo lee el método `transformacion-datos`. Dice qué tablas se construyen para el análisis y de dónde sale
> cada columna. Los criterios no se definen aquí: vienen de `reglas-negocio.md`, que se cita por apartado, y del diseño
> aprobado en `../modelo/modelo-datos.md`. El responsable del caso no ha decidido ningún criterio en este fichero. Hay siete convenciones
> técnicas que las reglas no fijan, decididas por el analista porque ninguna cambia la respuesta a una pregunta del caso. Van
> junto a la columna que aclaran, marcadas «(criterio técnico)», y con su medida:
>
> 1. el año de edad son 8.766 horas (§1);
> 2. las «capacidades vecinas» del precio son las dos más cercanas con curva ese día (§1);
> 3. el cambio de un contador se mide contra la foto anterior del mismo disco (§3);
> 4. un fallo que cae en el horizonte de dos fotos es objetivo en las dos (§3);
> 5. el disco con dos modelos toma el de su primera foto (§5);
> 6. un disco que desaparece avisando se cuenta en el mes y con la edad de su última foto (§5 y §6);
> 7. los días de una celda del recuento sin foto quedan sin repartir (§6).

## Proyecto de averías de discos duros en los centros de datos de Backblaze

### De qué se parte

De las cuatro tablas corregidas de `data/processed/`, que no se modifican, y del Calendario, siguiendo el diseño
aprobado. No hubo integración antes: todos los cruces del plan piden una dimensión o el Calendario, o filtrar o agregar
antes con una regla, y los hace esta transformación con los controles de `integracion-datos` (`modelo-datos.md` §7).
Solo se cruza lo que está en el plan de cruces aprobado (cruces 1 a 15 de `informes/modelado-datos.json`).

- `fotos_mensuales_corregido.parquet`: un disco el día 1 de cada mes, 14.851.669 filas de enero de 2020 a junio de
  2025, con huella `998d1edec335…`.
- `ventanas_fallo_corregido.parquet`: un disco cada uno de los 30 días anteriores a un fallo y el del fallo, 536.597
  filas, con huella `63d4379a89b9…`.
- `recuento_diario_corregido.parquet`: un día, un modelo, una capacidad y un centro, 197.871 filas, con huella
  `320f487a6a82…`.
- `fallos_corregido.parquet`: un disco el día que Backblaze lo da por fallado, 17.960 filas, con huella
  `59e45676a6a7…`.
- `calendario.parquet`: un día por fila, 2.008 días del 01/01/2020 al 30/06/2025, con `periodo` (construcción hasta el
  30/06/2024 y validación hasta el 30/06/2025), el año, el trimestre y el mes.

Cada tabla nueva se guarda aparte en `data/processed/`. La reserva, del 01/07/2025 al 30/06/2026, no está en el caso y
no se lee (reglas, apartado 5).

La fecha de referencia es el 30/06/2025 (reglas, apartado 5). No hay una sola fecha de corte por fila: cada foto se mira en su
propio día, y su objetivo se conoce 30 días después (reglas, apartado 7).

**Antes de cruzar**, la transformación iguala dos cosas, sin guardarlas en las tablas corregidas (`modelo-datos.md`
§4): `dia_fallo` pasa de nanosegundos a milisegundos, como `fecha`, y el centro vacío de las fotos y las ventanas pasa a
«sin dato», como en el recuento.

**La población.** Todo cálculo usa solo los discos de datos (reglas, apartado 3 y §7). Los de arranque se quedan en dos tablas,
marcados, para poder contarlos aparte: en `dim_modelo` y en `fallos_detalle`.

**La edad**, que usan cuatro tablas, se calcula siempre igual (reglas, apartado 3): las horas encendido de la fila, pasadas a
años. Si la fila no las trae, son los días desde la primera aparición del disco, que es su primera foto o, si sale
antes en una ventana, el primer día de esa ventana. La primera aparición nunca es posterior a la fila, así que la edad
no usa nada del futuro. Si las horas de un disco bajan entre dos fotos, cada foto usa las suyas: pasa 3.468 veces, la
regla, apartado 3 dice «sus horas encendido» y la corrección lo dejó como está (R-009, C-18).

### 1. Las dos dimensiones van primero porque las demás tablas las usan

#### `dim_modelo`: una fila por modelo

Nueva tabla, `dim_modelo.parquet`, con los 94 modelos del recuento, que son los mismos que los de las fotos y las
ventanas.

- `model`: la clave, el nombre corregido (R-004).
- `capacity_bytes`: la única capacidad del modelo tras la corrección (R-005).
- `capacidad_tb`: `capacity_bytes` entre 10^12, redondeada a un decimal; un TB son 1.000 GB (reglas, apartado 6).
- `tipo_disco`: «arranque» hasta 2.048.408.248.320 bytes y «datos» desde ahí (reglas, apartado 3 y §7). Son 33 y 61. Ninguno
  está entre 2 y 4 TB.
- `fabricante`: Seagate si el modelo empieza por «ST»; Toshiba, WDC o HGST si lleva delante ese nombre; el Hitachi
  HDS5C4040ALE630 es HGST y el WUH721816ALE6L4 es WDC (reglas, apartado 3). Queda vacío en los 23 modelos de arranque que no
  siguen ningún patrón; ningún modelo de datos queda vacío.
- `garantia_anos`: 5 en los Seagate con «NM», los HGST HUH y HUS, los WDC WUH y los Toshiba MG; 3 en los HMS5C; 2 en
  los Seagate con «DM» (reglas, apartado 6). Queda vacío en ocho modelos de datos sin garantía comprobada, que suman 35 fallos y
  cuentan como fuera de garantía.
- `fecha_compra`: la entrada media de los discos del modelo: para cada disco, el día de su primera foto menos sus horas
  encendido de esa foto, y de ahí la media (reglas, apartado 6). Los discos sin horas en su primera foto no entran en la media.
  Vacía en los de arranque.
- `coste_gb_compra`, en dólares por GB: el de su capacidad en su `fecha_compra`, de `precios_de_coste_discos.md`:
  - si su capacidad tiene curva ese día, la recta entre el valor de principio y el de final de cada año de la tabla;
  - desde el 15/11/2022, lo inferido: la recta entre 0,0145 ese día y 0,0132, 0,0115 y 0,0100 el 1 de julio de 2023,
    2024 y 2025;
  - si su capacidad no tiene curva ese día, la media de las dos capacidades más cercanas que la tengan, o la única si
    solo hay una (reglas, apartado 6, «capacidades vecinas»).
- `precio_usd`: `coste_gb_compra` × `capacidad_tb` × 1.000. Vacío en los de arranque y en los cuatro modelos de 6 TB que
  la tabla de precios deja sin precio (reglas, apartado 6). El ST6000DX000 sí lo tiene.
- `origen_precio`: «curva», «inferido» o «vecinas», para que cada gráfico diga de dónde sale su precio (precios,
  «Límites»).

La fecha de compra y el precio son una ficha de hoy: se calculan con todo el periodo, no con lo que se sabía en cada
fecha (`modelo-datos.md` §3). Por eso no entran en la tabla de la pregunta 4.

**La recta y las vecinas (criterio técnico).** La tabla de precios da el valor al empezar y al acabar cada año. No
dice cómo se lee un día intermedio. La recta entre los dos es la del reconocimiento, donde se midieron las cifras que
citan las reglas. «Las capacidades vecinas» se lee como las dos más cercanas con curva ese día, que es lo que hace la
tabla con 10 TB (8 y 12) y con 18 TB (14 y 16). La otra lectura posible, la más cercana por arriba y por abajo, cambia el
precio de 17 modelos. Ninguno cambia de puesto en el ranking de todo el periodo, y en el de cada año cambian 2 de las
152 celdas de modelo y año. La diferencia mayor es de 0,06 dólares por TB y año, en el ST12000NM001G. Medido por el analista
el 17/11/2026.

**Comprobación.** Los 61 modelos de datos tienen fecha de compra. 57 tienen precio, y los cuatro sin precio suman 18.840
días de disco, como dice la tabla de precios. El ST6000DX000 sale comprado en abril de 2015, a 198,35 dólares, y la tabla
da abril de 2015 y 200 dólares. El ST4000DM000 sale en noviembre de 2015, la fecha que citan las reglas, apartado 6. Medido por
el analista con el intérprete del caso el 17/11/2026.

#### `dim_precio_gb`: una fila por capacidad y año

Nueva tabla, `dim_precio_gb.parquet`: las 11 capacidades de datos (4, 6, 8, 10, 12, 14, 16, 18, 20, 22 y 24 TB) por
los seis años de 2020 a 2025, 66 filas. Da el precio del disco nuevo que sustituye a uno que falla, que se compra el año
del fallo (reglas, apartado 6).

- `capacidad_tb` y `ano`: la clave.
- `coste_gb`: el de esa capacidad el 1 de julio de ese año, con la misma regla que `coste_gb_compra`. Desde 2023 es el
  inferido de cada año para todas las capacidades: 0,0132, 0,0115 y 0,0100.
- `origen`: «curva», «inferido» o «vecinas».

Para la prueba final hará falta añadir 2026, con el 0,0151 de la tabla de precios.

**Comprobación.** Con estos precios, los 4.538 fallos de discos de datos de 2024 cuestan 832.698 dólares, y 305.124 si
la garantía pagara los que estaban dentro, el 72 % de ellos. Las reglas, apartado 6 dan unos 833.000 y unos 310.000. Medido el
17/11/2026.

### 2. Calendario

Ya existe (`calendario.parquet`, del diseño aprobado). Esta transformación no lo cambia: lo une a las demás tablas por
`fecha`, y a los fallos por `dia_fallo` (cruces 6, 8 y 10).

### 3. `fotos_riesgo`: una fila por disco de datos y foto mensual

Nueva tabla, `fotos_riesgo.parquet`, para la pregunta 4. Entran las fotos de discos de datos, salvo las del día en que
el disco falla (`failure` = 1), porque ese día ya está marcado como fallado (`modelo-datos.md` §9). Cada fila lleva solo
lo que se sabía el día de la foto, salvo el objetivo (ficha, «El modelo se entrena como se usará»).

**Lo que se conoce el día de la foto**, que el modelo puede usar:

- `serial_number`, `fecha`, `model`, `capacity_bytes`: los de la fila. El modelo de cada fila es el que trae esa fila
  (`modelo-datos.md` §3).
- `capacidad_tb`, `fabricante`, `garantia_anos`: de `dim_modelo` (cruce 9).
- `edad_anos`: con la regla de la edad de «De qué se parte», sin redondear.
- `edad_de_horas`: verdadero si la edad sale de las horas encendido y falso si sale de la primera aparición.
- `avisa`: verdadero si alguno de los cinco contadores de avería (5, 187, 188, 197 y 198) pasa de cero; un vacío no
  cuenta (reglas, apartado 3 y §5).
- `contadores_que_avisan`: cuántos de los cinco pasan de cero.
- `suma_contadores_sin_188`: la suma de los contadores 5, 187, 197 y 198, sin los vacíos. Con la columna anterior,
  ordena la regla de los cinco contadores (reglas, apartado 7, cuestión 010).
- `smart_188_no_cero`: 1 si el contador 188 pasa de cero, 0 si vale cero, vacío si no consta. El 188 no es un recuento
  creíble y se usa así (plan, «Lo que hay que comprobar»).
- `cambio_smart_5`, `cambio_smart_187`, `cambio_smart_197` y `cambio_smart_198`: el valor de la fila menos el de la foto
  anterior del mismo disco. Queda vacío si no hay foto anterior o si uno de los dos valores es vacío. El 188 no lleva
  cambio, por lo dicho arriba. Un contador que baja da un cambio negativo y se deja así: pasa en los cinco contadores
  (R-009, C-20).
- `meses_desde_foto_anterior`: los meses entre la foto y la anterior del mismo disco. Vacío en la primera.

**El cambio, contra la foto anterior (criterio técnico).** El diseño dice «la diferencia con las fotos anteriores» sin
fijar cuántas. Aquí se mide contra la anterior. Otros plazos, como tres o seis meses, son variables del paso 5, que se
crean y se preseleccionan allí. Hoy 14.194.397 filas tienen la foto anterior un mes antes, 8.026 más de un mes antes y
402.438 son la primera foto de su disco.

**El sitio**, que solo consta desde el 01/07/2023 y que el paso 5 decide si entra (`modelo-datos.md` §3):

- `datacenter`, `vault_id`, `pod_id`, `pod_slot_num`: los de la fila, vacíos donde no constan.

**La partición, que no se usa para predecir:**

- `periodo`: el del Calendario en la `fecha` de la foto (reglas, apartado 7, «La partición por fecha»).

**El objetivo y lo que sale de él**, que se conocen después de la foto y no se usan para predecir:

- `horizonte_hasta`: 30 días después de la foto, recortado al 30/06/2024 en construcción y al 30/06/2025 en validación
  (`modelo-datos.md` §9; reglas, apartado 7).
- `falla_30d`: 1 si el disco tiene algún fallo en la lista con `dia_fallo` del día siguiente a la foto a
  `horizonte_hasta`, los dos incluidos; 0 si no (reglas, apartado 7, cuestión 003 y cuestión 004; cruce 12). Cuenta cualquier fallo, también
  el segundo de un disco que volvió.

**Un fallo en dos fotos (criterio técnico).** Febrero es más corto que 30 días, así que el horizonte de la foto de
febrero llega a los primeros días de marzo, que también están en el de la foto de marzo. Un fallo de esos días es
objetivo de las dos fotos, porque las dos lo tenían por delante. Hoy son 78 fallos. **`falla_30d` no se suma entre
filas para contar fallos:** los fallos se cuentan en `fallos_detalle`.

**Lo que pasa de las fotos sin cambios.** Las demás columnas de la tabla corregida, todas `smart_*`, pasan sin
cambios. En el grupo de lo que se conoce el día de la foto van los contadores de avería y las candidatas del plan
(temperatura, 194; errores de cable, 199; encendidos, 12; apagados de emergencia, 192; errores de lectura, 1, y de
colocación del cabezal, 7). Las demás quedan como «no previstas». Cuáles entran al modelo lo decide la preselección del
paso 5.

**Lo que sale de la tabla.** Salen tres columnas de la tabla corregida, y ninguna cambia una respuesta:

- `failure`, que vale 0 en todas las filas que quedan;
- `date`, que repite `fecha` (0 valores distintos, `modelo-datos.md` §3);
- `cluster_id`, que no usa ninguna pregunta (R-009, C-11).

La fecha de compra y el precio de `dim_modelo` no entran, porque son una ficha de hoy.

**Comprobación.** 14.604.861 filas: 11.026.052 de construcción y 3.578.809 de validación. Las 528 fotos del día del
fallo quedan fuera. `falla_30d` vale 1 en 11.962 filas de construcción y 4.304 de validación. Son 16.266 filas con
objetivo 1 para 16.188 fallos distintos, porque 78 fallos están en dos fotos. Medido por el analista el 17/11/2026, sobre las
tablas corregidas. El script para si alguna columna de la tabla no está en ninguno de los grupos de arriba.

### 4. `fallos_detalle`: una fila por fallo

Nueva tabla, `fallos_detalle.parquet`, con los 17.960 fallos de la lista, también los de discos de arranque, marcados,
para contarlos aparte. Cada fallo toma una sola fila de su ventana, elegida por una regla de fecha (cruces 1 a 3).

**Del día del fallo** (cruce 1):

- `serial_number`, `dia_fallo`: la clave, `dia_fallo` ya en milisegundos.
- `model`: el de la fila de la ventana con `fecha` igual a `dia_fallo`. La lista no trae modelo (`modelo-datos.md` §9).
- `capacidad_tb`, `fabricante`, `tipo_disco`, `garantia_anos`: de `dim_modelo` (cruce 4).
- `horas_al_fallar`: las horas encendido del día del fallo o, si no las trae, las del día anterior.
- `edad_al_fallar_anos`: `horas_al_fallar` pasadas a años; sin horas, con la regla de la edad.
- `edad_de_horas`: como en `fotos_riesgo`.
- `en_garantia`: verdadero si `edad_al_fallar_anos` es menor que `garantia_anos`. Falso si el modelo no tiene garantía
  comprobada (reglas, apartado 6).

**Del día anterior** (cruce 2):

- `hay_dia_anterior`: verdadero si la ventana trae el día anterior al fallo.
- `avisa_dia_anterior`: si alguno de los cinco contadores pasa de cero ese día. Vacío si no hay día anterior.
- `sin_aviso`: verdadero si hay día anterior y no avisa (reglas, apartado 6, «Fallo sin aviso»). Vacío si no hay día anterior:
  esos fallos salen del indicador y se cuentan aparte.

**Del sitio del fallo** (cruce 3):

- `datacenter`: el de la última fila hasta el día del fallo que trae centro (reglas, apartado 5, «El sitio de un fallo»).
- `vault_id`, `pod_id`, `pod_slot_num`: los de la última fila hasta el día del fallo que trae centro, vault, servidor y
  ranura. Vacíos si ninguna los trae.
- `tomo`: centro, vault y ranura juntos, vacío si falta alguno (reglas, apartado 4).
- `plazo_reconstruccion_dias`: `capacidad_tb` más uno, un día por TB más uno de espera (reglas, apartado 5 y §7).
- `dias_desde_anterior_del_tomo`: los días desde el fallo anterior del mismo tomo, con la tabla ordenada por tomo y
  día. Vacío si es el primero de su tomo o no tiene tomo.
- `coincide_con_anterior`: verdadero si esos días son menos que el plazo del fallo anterior de su tomo. El plazo cuenta
  con la capacidad del primero, y su último día ya no coincide (reglas, apartado 7, «Fallos que coinciden en un tomo»). No es un
  cruce: se calcula dentro de la tabla (`modelo-datos.md` §5).

**Del valor** (cruce 5):

- `precio_nuevo_usd`: `coste_gb` de `dim_precio_gb` para su capacidad y el año del fallo, por la capacidad en GB
  (reglas, apartado 6).
- `coste_fallo_usd`: `precio_nuevo_usd` más los 37 dólares del cambio (reglas, apartado 6).
- `coste_fallo_garantia_usd`: 37 si `en_garantia`; si no, `coste_fallo_usd` (reglas, apartado 6, la cifra con garantía).

**De la pregunta 4** (cruce 13):

- `ultima_foto_anterior`: la fecha de la última foto del disco anterior al fallo, para saber qué puesto tenía en la
  lista de ese mes. Vacía si el disco no tiene ninguna foto antes del fallo.
- `objetivo_de_alguna_foto`: verdadero si el fallo está en el horizonte de alguna fila de `fotos_riesgo`.

**Del calendario** (cruce 6):

- `periodo`, `ano`, `trimestre`, `mes`: los del Calendario en `dia_fallo`.
- `primer_fallo_del_disco`: verdadero en el primer fallo de cada disco. La vida de un disco acaba en su primer fallo
  (reglas, apartado 3).

**Comprobación.** Medido por el analista el 17/11/2026:

- Los fallos: 17.960 en total. 16.996 son de discos de datos, 12.478 en construcción y 4.518 en validación, y 964 de
  discos de arranque. Todos tienen la fila del día del fallo.
- La edad: 82 fallos no traen horas ni el día del fallo ni el anterior, y su edad sale de la primera aparición.
- El aviso: de los 16.996 fallos de discos de datos, 903 no tienen el día anterior. De los 16.093 que lo tienen, 4.046
  llegan sin aviso, el 25,1 %. La corrección dio 16.101 y 4.049 (R-009, C-26). La diferencia, 8 fallos, no la explica
  ninguna medida de hoy: la transformación da las dos cifras y dice cuál vale.
- El sitio: desde el 01/07/2023 hay 8.634 fallos de discos de datos. 128 no tienen centro y 141 no tienen tomo. Los 8.493
  con tomo están en 5.404 tomos, y 262 coinciden con el anterior de su tomo.
- El cuadre por centro: los fallos de cada centro desde el 01/07/2023 son los mismos en esta tabla y en el recuento.
  Son 476 en ams5, 512 en iad1, 2.160 en phx1, 2.806 en sac0, 2.546 en sac2, 6 en yyz1 y 128 sin dato.
- La garantía: el 66,6 % de los fallos de discos de datos cae dentro.

### 5. `vida_discos`: una fila por disco de datos

Nueva tabla, `vida_discos.parquet`, para la supervivencia de la pregunta 2 y las altas y bajas del bloque 1. Entran
los discos de datos que salen en alguna foto o en alguna ventana.

- `serial_number`: la clave.
- `model`: el de su primera foto o, si no tiene ninguna, el de su ventana.
- `primera_aparicion`: su primera foto o, si sale antes en una ventana, el primer día de esa ventana.
- `edad_entrada_anos`: su edad en su primera aparición. Un disco que ya era viejo el 01/01/2020 entra en la curva a esa
  edad, no desde cero (plan, bloque 3).
- `ultima_foto`: su última foto.
- `primer_fallo`: el día de su primer fallo, vacío si no falla.
- `evento`: «fallo» si tiene un fallo; «desaparece» si su última foto es anterior a la última de los datos, el
  01/06/2025, sin ningún fallo desde esa foto; «sigue» en los demás (reglas, apartado 3, «Los discos que desaparecen»).
  Un disco que falta unos meses y vuelve no desaparece.
- `fecha_fin`: el día del primer fallo, o la última foto si desaparece o sigue. Desde la última foto, un disco que
  desaparece se va en algún día del mes siguiente, que no se sabe.
- `edad_fin_anos`: su edad en `fecha_fin`.
- `avisa_ultima_foto`: si en su última foto avisaba.
- `desaparece_avisando`: verdadero si desaparece y avisaba en su última foto (reglas, apartado 3, la cifra que va al lado).

**El disco con dos modelos (criterio técnico).** El 5QJB76AB sale con dos modelos (R-009, C-19). En esta tabla toma el
de su primera foto. Es un disco entre 402.643.

**Comprobación.** 402.643 discos: 402.450 con foto y 193 que solo salen en la ventana de su fallo. 16.984 acaban en
fallo, 71.328 desaparecen y 314.331 siguen. Desaparecen avisando 6.557. 16.517 entran con 4 años o más, 9 de ellos entre
los 193 que solo salen en su ventana, y 66 fallan antes de su primera foto. Medido por el analista el 17/11/2026 y corregido
ese día con la transformación (historial). El reconocimiento contó 71.373 discos que dejan de salir sin un
fallo después de su última foto. Aquí acaban en «desaparece» 71.328: los otros 45 fallaron antes de irse, su vida acaba
en ese primer fallo y su `evento` es «fallo».

### 6. `dias_por_tramo` por modelo × centro × mes × año de edad

Nueva tabla, `dias_por_tramo.parquet`, para la tasa por edad de la pregunta 2, la tasa ajustada por centro de la 3 y
las tasas de la previsión del bloque 9. Junta los cruces 11 y 15.

- `model`, `centro`, `mes` y `edad_anos_cumplidos` (los años enteros de `edad_anos`): la clave. El centro es el
  `datacenter` de la foto o «sin dato».
- `fotos`: cuántas fotos de discos de datos del mes caen en ese modelo, centro y año de edad.
- `dias_disco`: los días de disco del recuento de ese modelo, centro y mes, repartidos entre sus años de edad en
  proporción a sus fotos (reglas, apartado 5, «Con qué se cuentan»; cruce 11). Es un flujo y se suma.
- `fallos`: los fallos de discos de datos de `fallos_detalle` con ese modelo, el centro del fallo, el mes de
  `dia_fallo` y su año de edad al fallar (cruce 15). Se suma.
- `desaparecen_avisando`: los discos de `vida_discos` que desaparecen avisando, en el modelo, el centro y el mes de su
  última foto y con la edad de esa foto. Sirve solo para la cifra que va al lado de la tasa por edad, contándolos como
  fallo (reglas, apartado 3).

**Desaparecer en la última foto (criterio técnico).** Un disco que desaparece se va en algún día entre su última foto y
la siguiente, que no se sabe. Se cuenta en el mes y con la edad de su última foto, como en la medida del comité del
paso 1 que citan las reglas (en los años 2 y 3 de edad, la tasa pasa del 1,22 y 1,58 % al 2,45 y 3,24 %).

**Los días sin foto (criterio técnico).** Si un modelo tiene días en un centro y un mes del recuento y ninguna foto
ahí, esos días no tienen con qué repartirse. Quedan fuera de esta tabla y se cuentan en el registro de exclusiones. Son
919.192 días de disco en 110 celdas, el 0,21 % de los días de discos de datos, con 26 fallos del recuento. Repartirlos
con las fotos del mismo modelo en otro centro mezclaría centros, y la tabla sirve para comparar centros. Al revés, 140
fallos caen en una fila sin días, porque el disco falló en un modelo, centro, mes y edad sin ninguna foto. Están en
`fallos` y el script los cuenta.

**Comprobación.** 13.275 filas, 64 de ellas solo con fallos. Se reparten 445.189.491 días de disco de los 446.108.683
del recuento, y están los 16.996 fallos. La tasa anual del conjunto de discos por año de edad sale del 0,79 % el primer año al
2,58 % a los 5. La ficha da 0,78 % y 2,58 %, con los días repartidos por modelo y mes, sin
separar centros. Los años de edad van de 0 a 10; los años 9 y 10 no tienen ningún fallo. Medido por el analista
el 17/11/2026.

### 7. `inicio_trimestre` por trimestre × modelo × año de edad

Nueva tabla, `inicio_trimestre.parquet`, para la previsión del bloque 9. La previsión de cada trimestre se hace con lo
que se sabe su primer día: los discos que hay ese día, con su edad (reglas, apartado 7, «Previsión de fallos»).

- `trimestre`, `model` y `edad_anos_cumplidos`: la clave.
- `fecha`: el primer día del trimestre, que es día de foto.
- `capacidad_tb`: de `dim_modelo`.
- `discos`: los discos de datos de la foto de ese día con ese modelo y año de edad (cruce 14).
- `dias_trimestre`: los días del trimestre, del Calendario.

**Comprobación.** 3.117 filas de los 22 trimestres de 2020 a junio de 2025, con 4.805.590 discos. El primer día de cada
trimestre, los discos de la foto son los mismos que los del recuento, modelo a modelo, en todos los trimestres. Medido
por el analista el 17/11/2026.

### 8. `modelo_trimestre`: una fila por modelo de datos y trimestre

Nueva tabla, `modelo_trimestre.parquet`, para la pregunta 1 (cruces 7 y 8, con los fallos de `fallos_detalle`).

- `model`, `trimestre`: la clave; `ano`, del Calendario.
- `capacidad_tb`, `fabricante`, `fecha_compra`, `precio_usd`, `origen_precio`: de `dim_modelo`.
- `dias_disco`: la suma de `discos` del recuento de ese modelo en el trimestre, todos los centros (reglas, apartado 6).
- `fallos`: los fallos de `fallos_detalle` de ese modelo con `dia_fallo` en el trimestre.
- `fallos_en_garantia`: los de esos fallos con `en_garantia`.
- `coste_fallos_usd` y `coste_fallos_garantia_usd`: la suma de `coste_fallo_usd` y `coste_fallo_garantia_usd` de esos
  fallos.
- `dias_disco_ano`: los días de disco del modelo en todo su año.
- `pasa_minimo_ano`: verdadero si `dias_disco_ano` llega a 50.000 (reglas, apartado 7, «Mínimo para entrar en un ranking»). En
  2025 el año tiene seis meses.

**Comprobación.** 1.028 filas, todas con días de disco. En las 1.028, los fallos de la lista son los del recuento. Suman
16.996 fallos y 446.108.683 días de disco. Pasan el mínimo 152 de las 299 celdas de modelo y año, de 32 modelos.
Medido por el analista el 17/11/2026.

### 9. `centro_mes`: una fila por centro y mes

Nueva tabla, `centro_mes.parquet`, para la tasa bruta por centro de la pregunta 3 y el reparto del conjunto de discos del bloque 1.
Sale solo del recuento, de discos de datos (cruce 8).

- `datacenter`, `mes`: la clave; «sin dato» es el centro que no consta.
- `dias_disco`, `fallos`: las sumas del recuento.
- `periodo`, del Calendario, y `con_sitio`: verdadero desde julio de 2023, cuando el centro empieza a constar (reglas
  §4).

**Comprobación.** 186 filas, 144 desde julio de 2023. En esos dos años, los días de disco y los fallos por centro son:

| Centro | Días de disco | Fallos |
|---|---:|---:|
| ams5 | 12.111.055 | 476 |
| iad1 | 18.007.479 | 512 |
| phx1 | 65.723.705 | 2.160 |
| sac0 | 59.117.752 | 2.806 |
| sac2 | 45.064.768 | 2.546 |
| yyz1 | 651.306 | 6 |
| sin dato | 6.621.213 | 128 |

Medido por el analista el 17/11/2026.

### 10. Registro de exclusiones

No crea ningún dataset. Deja en el informe de la transformación una tabla con una fila por cada clase que sale de algún
cálculo, con sus días de disco, sus fallos y sus fotos, que salen del código y no se escriben a mano (`modelo-datos.md`
§10). Hoy:

- **discos de arranque:** 7.500.739 días de disco, 964 fallos y 246.280 fotos, fuera de todo cálculo. Se pueden contar
  aparte;
- **sitio antes del 01/07/2023:** 238.811.405 días de disco y 8.362 fallos de discos de datos, fuera de lo que va por
  centro y por tomo. No se puede recuperar;
- **centro «sin dato» desde el 01/07/2023:** 6.621.213 días de disco y 128 fallos, contados y dichos;
- **fallos sin tomo desde el 01/07/2023:** 141, fuera de los tomos y del aviso de tomos en peligro;
- **fallos sin el día anterior en su ventana:** 903 de discos de datos, fuera del indicador de fallos sin aviso;
- **fotos del día del fallo:** 528, fuera de `fotos_riesgo`;
- **fallos que no son objetivo de ninguna foto:** 808 de discos de datos, en seis clases:
  - 291 caen el día 1 de un mes que sigue a uno de 31 días, a 31 días de la foto anterior;
  - 222 llegan más de 31 días después de la última foto de su disco;
  - 193 son de discos sin ninguna foto;
  - 78 llegan antes de la primera foto de su disco;
  - 16 quedan fuera por el recorte del horizonte el 30/06/2024;
  - 8 no caen en ninguna de esas clases y el informe los enseña uno a uno;
- **días de disco sin foto en su modelo, centro y mes:** 919.192, con 26 fallos del recuento, fuera de `dias_por_tramo`;
- **modelos de 6 TB sin precio:** 4 modelos con 18.840 días de disco, fuera del coste por TB y año. No llegan al
  mínimo del ranking.

Los modelos que no llegan al mínimo y los años de edad con menos de 20 fallos no salen de ninguna tabla. Se marcan, y
el análisis los enseña aparte (reglas, apartado 7). Las 228 filas que quitó la corrección ya están en R-007 y no se repiten aquí.

### Lo que no se hace en esta fase

- No se calcula ninguna tasa, intervalo ni ranking, ni el coste por TB y año, ni la tasa ajustada por centro, ni los
  fallos esperados al azar en un tomo: es el análisis de las preguntas 1 a 3.
- No se hace la previsión del bloque 9 ni su referencia.
- No se calcula la curva de supervivencia.
- No se ajusta ningún modelo ni se eligen variables. No se crean variables para el modelo: ni escalado, ni columnas 0/1
  por categoría, ni otros plazos del cambio de un contador. Es el paso 5.
- No se imputa ningún vacío: un contador vacío quiere decir que el modelo no lo apunta (reglas, apartado 5).
- Los bloques 1, 5, 6 y 8 se consultan en el análisis sobre estas tablas y las corregidas. Los tramos de temperatura,
  de datos escritos y leídos y de arranques del bloque 8 no están en las reglas, y los propone el análisis de ese
  bloque.

### Lo que los pasos siguientes necesitan de estas tablas

- **Exploratorio (paso 4).** El objetivo de `fotos_riesgo` solo se cruza con las columnas en `periodo` «construcción».
  Las tasas del conjunto de discos usan los dos periodos, porque describen el conjunto de discos y no ajustan el modelo (reglas, apartado 7).
- **Modelado (paso 5).** El objetivo de una foto se conoce en su `horizonte_hasta`. Al empezar la validación, el
  01/07/2024, todos los horizontes de construcción ya han acabado, porque el recorte los cierra el 30/06/2024. Dentro de
  la construcción, cada pliegue por tiempo deja fuera las fotos cuyo horizonte acaba después del primer día que mide, y
  las cuenta (`aprendizaje-automatico` §3).
- **El puesto en la lista.** Para medir los fallos señalados en tomos en peligro, cada fallo de `fallos_detalle` busca
  su `ultima_foto_anterior` en la lista de ese mes.
- **Producción (paso 7).** El script separa en dos bloques lo que se calcula con la foto tal como está ese día (la
  edad, los avisos, los cambios y el sitio) y lo que necesita el desenlace (`falla_30d` y su horizonte). El primer
  bloque es el que puntuará los discos cada mes.

## Historial de cambios

| Fecha | Qué cambió | Quién lo decidió |
|---|---|---|
| 17/11/2026 | Primera versión, con el diseño del modelo de datos aprobado y siete convenciones técnicas medidas | el analista la escribe |
| 17/11/2026 | Aprobada entera, con las siete convenciones técnicas. No cambia el texto | el responsable del caso: «Sí, las apruebo» |
| 17/11/2026 | §5, dos cifras de la comprobación que el analista midió mal: desaparecen avisando 6.557 (no 6.569; la medida contaba 11 discos en fallo y otro por saltarse un vacío) y entran con 4 años o más 16.517 (no 16.508; dejaba fuera los discos que solo salen en su ventana). La regla no cambia | el responsable del caso: «Sí, corrígelas» |
