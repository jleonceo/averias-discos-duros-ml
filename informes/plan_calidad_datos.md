---
titulo: Plan de calidad de los datos del caso 68 · qué va a comprobar el script de calidad sobre los cuatro datasets, antes de escribirlo
estado: opción del 17/11/2026; aprobada por el responsable del caso ese día («Sí, apruebo»), con las cuatro lecturas cerradas como dice «Lo aprobado» y las ocho reglas candidatas como comprobaciones. El script de calidad va en la petición siguiente
fecha_documento: 2026-11-17
dueno: El responsable del caso (decide)
fuente: config/fuentes/diccionario-datos-origen.json (ejecución del 17/11/2026); negocio/reglas-negocio.md; informes/reconocimiento/reconocimiento_de_los_datos.ipynb, secciones 2, 9, 11, 12, 14 y 15; método calidad-datos (METODO.md, comprobaciones.md y parametros.md)
---

# Plan de calidad de los datos

## Lo que se pide

Este plan dice qué va a comprobar el script de calidad en los cuatro datasets del caso: **fotos mensuales, ventanas de
fallo, recuento diario y lista de fallos**. También dice con qué parámetros y sobre qué columnas trabaja. El esquema de
Backblaze no es un dataset: se usa como diccionario de la organización y solo entra en la revisión de nombres.

Hacen falta dos cosas del responsable del caso antes de escribir el script:

- el visto bueno al plan, o los cambios que quiera en los bloques, los parámetros o las comprobaciones;
- cuatro decisiones de lectura, marcadas abajo como **[DECISIÓN]** y reunidas al final. Ninguna la fijan las reglas.

El script diagnostica y no corrige nada. Lo que las reglas de negocio ya deciden se comprueba en los datos y no se
pregunta.

## Lo que ya se sabe de los cuatro datasets

El diccionario del origen leyó los cuatro datasets enteros, sin muestra, y el script de calidad parte de él sin volver a
contar lo que ya trae: filas, tipos, roles, vacíos y valores distintos de cada columna.

- Fotos mensuales: 14.851.669 filas en 66 ficheros, de 101 a 130 columnas; 408.208 discos. Una fila es un disco el día 1
  de un mes, y la clave disco y fecha no se repite.
- Ventanas de fallo: 536.825 filas en 22 ficheros, de 102 a 131 columnas; 17.960 ventanas. Una fila es un disco en uno
  de los 30 días anteriores a su fallo o en el del fallo. Hay 3.542 ventanas de menos de 31 filas y ninguna fila fuera de
  su ventana.
- Recuento diario: 201.502 filas y 6 columnas; 2.008 días seguidos, del 01/01/2020 al 30/06/2025. Suma 453.609.422 días de
  disco y 17.960 fallos.
- Lista de fallos: 17.960 fallos de 17.948 discos; 12 discos fallan dos veces.

Cada dataset se reparte así entre construcción (hasta el 30/06/2024) y validación (desde el 01/07/2024), por la fecha de
la fila o, en ventanas y fallos, por el día del fallo:

- fotos: 11.223.741 y 3.627.928 filas;
- ventanas: 398.970 y 137.855;
- recuento: 140.361 y 61.141;
- fallos: 13.376 y 4.584.

Los discos de arranque se separan por la capacidad de su modelo (reglas, apartado 3). En las fotos son 246.280 filas; en las
ventanas, 28.558; en el recuento, 61.775; y en la lista, 964 fallos. Los fallos de discos de datos son 12.478 en
construcción y 4.518 en validación.

## Los bloques del método

Se aplican los once bloques. El del esquema se limita a los nombres, porque el esquema es una lista de nombres de columna
y no trae tipos ni valores.

- 3.1 Inspección general. Sí, con lo que ya da el diccionario; el script solo añade la cobertura temporal de cada fichero.
- 3.2 Estructura. Sí. Columnas vacías, casi vacías y constantes en cada fichero, no solo en el total: 49 columnas de las
  fotos están vacías en más del 99 % de las filas. Nombres de columna (comprobaciones §9), con las dos erratas del esquema
  (`smart_211_normailized` y `smart_212_normailized`) y las columnas que entran a mitad del periodo. La forma de la tabla
  (comprobaciones §1) no aplica: no hay periodos en columnas ni dos datos en una celda.
- 3.3 Tipos y formatos. Sí, con la escala de cada magnitud (§3) y la tabla de tipos (§6). Se miran la ranura leída como
  decimal, el centro sin tipo en las fotos anteriores a julio de 2023 y la fecha que viene dos veces, como texto (`date`) y
  como fecha (`fecha`).
- 3.4 Valores ausentes. Sí, con el reparto por segmento, los códigos de ausencia (§4) y los vacíos por fila (§8).
- 3.5 Duplicados. Sí: exactos, sin el número de serie (§5), por clave, y lógicos (un mismo modelo escrito de dos formas).
- 3.6 Claves y granularidad. Sí, en las cuatro tablas, con la clave que fija el diccionario.
- 3.7 Categóricas y texto. Sí, en modelo y centro, con las categorías raras (§10). No hay texto libre.
- 3.8 Numéricas y atípicos. Solo en las magnitudes: los valores en bruto de los contadores, la capacidad y, en el
  recuento, discos y fallos. No se aplica a las notas normalizadas, al número de serie ni a los códigos de sitio.
- 3.9 Fechas. Sí, en `fecha`, `date` y `dia_fallo`. Las fechas vienen en formato ISO, así que no hay duda entre día y
  mes que demostrar.
- 3.10 Reglas lógicas e integridad. Sí, con las comprobaciones de las reglas, las reglas candidatas y los riesgos para
  un modelo, porque la pregunta 4 entrena uno. Las reglas no traen tabla «Lo esperable», así que este bloque no tiene
  rangos de negocio que mirar.
- 3.11 Cruces entre tablas. Sí. Los cuatro datasets comparten el número de serie, el día, el modelo y el centro.

## El rol de cada columna

El rol sale del diccionario. Decide qué comprobaciones se aplican a cada columna.

- Fechas: `fecha` y `date` en fotos y ventanas; `dia_fallo` en ventanas y en la lista de fallos; `fecha` en el recuento.
- Identificador: `serial_number`, en fotos, ventanas y lista de fallos. Identifica un disco, no a una persona.
- Categóricas: `model` en fotos, ventanas y recuento; `datacenter` en las tres.
- Binaria: `failure`, en fotos y ventanas.
- Códigos: `cluster_id`, `vault_id`, `pod_id` y `pod_slot_num`, y las 48 notas normalizadas de los contadores
  que traen las fotos (`smart_N_normalized`). Son notas ordinales que pone cada fabricante. No se suman ni se comparan como cantidades.
- Magnitudes: `capacity_bytes`; los 71 valores en bruto de los contadores que traen las fotos (`smart_N_raw`); y, en el recuento, `discos`
  y `fallos`.

Las ventanas tienen las mismas columnas que las fotos y, además, `dia_fallo`.

## Los parámetros

| Parámetro | Valor | De dónde sale |
|---|---|---|
| límite del rango intercuartílico | 1,5 × IQR | por defecto; las reglas no fijan otro |
| límite del z robusto | 3,5 | por defecto; las reglas no fijan otro |
| segmento mínimo para el reparto de vacíos | 30 filas | por defecto |
| concentración de vacíos en un segmento | el doble del porcentaje global | por defecto |
| categoría rara | menos del 2,5 % de las filas o menos de cinco apariciones | diccionario-datos, el mismo que usó el diccionario |
| código de ausencia numérico candidato | un valor en un extremo del rango con el 5 % de las filas o más | por defecto; se fijó sin fuente y este caso es de los primeros que lo usan |
| colas de cada magnitud | diez valores por cada lado | por defecto |
| fecha de Excel candidata | no aplica | ninguna fecha llega como número: vienen como fecha o como texto ISO |
| horizonte de fechas futuras | 30/06/2025 | reglas, apartado 5, fecha de referencia; no la fecha de ejecución |

**Las dimensiones del reparto de vacíos** son cinco:

- el periodo, construcción o validación (reglas, apartado 7);
- el fabricante, sacado del nombre del modelo con sus dos excepciones (reglas, apartado 3);
- el año de la fecha de la fila;
- disco de datos o de arranque, por la capacidad del modelo (reglas, apartado 3);
- en las columnas de sitio, antes y después del 01/07/2023 (reglas, apartado 4).

Además, el modelo entra como dimensión en los contadores, porque es la que comprueba que un contador vacío quiere decir
que ese modelo no lo apunta.

## Los códigos de ausencia que ya se ven

El diccionario deja ver cinco. Cuatro tienen el significado fijado por las reglas, y el script los cuenta sin preguntar:

- Capacidad -1 o 0,1 TB. Son 2.729 filas de fotos, 165 de ventanas y 2.102 del recuento. En las fotos, la capacidad de su
  modelo las pone casi todas en discos de datos (2.725) y 4 en discos de arranque. Las reglas, apartado 3 las resuelven con la
  capacidad del modelo, y ningún modelo trae dos capacidades válidas.
- Centro «sin dato» en el recuento. Son 84.647 filas, con 249.886.684 días de disco; 4.551 de ellas son desde el
  01/07/2023. En fotos y ventanas el centro viene vacío, no con texto. Las reglas, apartado 4 y §5 dicen que no consta y que se
  cuenta.
- Centro vacío en fotos y ventanas. Falta en todas las filas anteriores al 01/07/2023, como dicen las reglas, apartado 4. Desde
  esa fecha falta en 76.954 filas de fotos de construcción y en 158.818 de validación; el script dirá cuántas son de
  discos de arranque.
- Ranura vacía. Falta en todas las filas de discos de arranque (101.607 en fotos), que las reglas, apartado 3 describen sin
  ranura, y en 1.608 filas de fotos de discos de datos.

El quinto no lo fija ninguna regla:

- [DECISIÓN] `cluster_id` vale 0 en 4.781.548 de las 6.885.677 filas de fotos que traen la columna, y en 213.090 filas de
  ventanas. El 0 está en el extremo del rango y pasa del 5 %, así que es un código de ausencia candidato. Puede leerse como
  un grupo de servidores más o como «sin grupo». Ninguna pregunta del caso usa esta columna, y el diccionario la deja como
  «no se puede saber».

Hay además una ausencia que es de la fila entera. Las 2.729 filas de fotos con capacidad no válida no traen horas
encendido ni ningún contador. El script mirará si caen en las mismas filas en todas las columnas (comprobaciones §4) y lo
dirá como ausencia de la fila. Así se explican casi todas las 2.738 filas de discos de datos sin horas del reconocimiento:
2.725 son de esas filas y 13 de las demás.

## Las comprobaciones de las reglas

Cada regla se mira en los datos con una medida concreta. Ninguna se aplica a los datos en esta fase.

- La capacidad de un disco es la de su modelo (reglas, apartado 3). Capacidades válidas por modelo en cada tabla, y filas con -1
  o 0,1 TB por modelo y por fallo afectado.
- El fabricante sale del nombre del modelo, con las dos excepciones (§3). Lista de los modelos que no siguen el patrón
  de su fabricante. Se espera que salgan los dos de la regla y los de los discos de arranque; cualquier otro se dice.
- La edad son las horas encendido y, sin ellas, cuenta desde la primera aparición (§3). Discos sin horas en ninguna
  foto, discos con horas en unas fotos y no en otras, y fallos con edad negativa por la primera aparición.
- Un disco puede fallar dos veces y seguir en servicio tras un fallo (§3). Discos con más de un fallo, discos que
  vuelven a salir en las fotos después de su fallo y si vuelven a fallar.
- Un disco que falta en una foto y vuelve no ha desaparecido (§3). Discos con huecos entre su primera y su última foto,
  con el tamaño del hueco en meses.
- El sitio solo consta desde el 01/07/2023 y no se rellena hacia atrás (§4). Porcentaje de centro, vault, servidor y
  ranura vacíos antes y después de esa fecha, en cada tabla.
- Un disco con dos registros el mismo día cuenta una vez (§5). Repeticiones de disco y día en fotos y ventanas. El
  diccionario ya dio cero en las dos; el script lo repite como comprobación.
- Un contador vacío quiere decir que ese modelo no lo apunta (§5). Para cada modelo y contador, si está vacío en todas
  sus filas, en ninguna o solo en parte. Los modelos con vacíos parciales son los que contradicen la regla.
- Un sitio vacío quiere decir que no consta (§5). Recuento de filas con sitio vacío desde el 01/07/2023, por centro y
  tabla, sin apartarlas.
- El sitio de un fallo es el del último día anterior que lo trae, dentro de su ventana (§5). Fallos con ranura el día
  del fallo, fallos que la recuperan un día anterior de su ventana y fallos que no la tienen ningún día.
- Los valores en bruto de algunos contadores tienen formato de cada fabricante (§5). Rango y cifras de los valores en
  bruto de los contadores 1, 7, 188 y 195 por fabricante, para ver dónde cambia el formato.

## Lo que el reconocimiento dejó para este paso

Son cuestiones a revisar, contadas sin corregir. El script vuelve a medir cada una con su cifra; si quitarlas cambia
alguna respuesta lo medirá la corrección, no este diagnóstico.

- Modelos con dos espacios tras «WDC». Cuatro modelos, que hacen que 3.286 discos tengan dos nombres. El script
  contará discos y filas de cada variante en cada tabla. Va con la decisión de lectura del modelo.
- Capacidad -1 o 0,1 TB. Las 2.102 filas del recuento, con las de fotos y ventanas, por modelo y por periodo.
- Centro «sin dato». Las 84.647 filas del recuento, 4.551 de ellas desde el 01/07/2023, con sus días de disco.
- Horas encendido. Las 2.738 filas de fotos de discos de datos sin horas, y el fallo que con la primera aparición
  sale con edad negativa.
- El 188 por encima de mil millones. 192.593 filas de fotos de discos de datos, por fabricante y modelo. Va con su
  decisión de lectura.
- El 5 y el 187 en su tope. 14 filas con el 5 en 65.528 y 52 con el 187 en 65.535. El diccionario ve además el 5 en
  65.529 en las fotos y en 65.534 en las ventanas. El script dará las colas de los dos contadores. Va con su decisión de
  lectura.
- Fallos sin ranura. 2.010 fallos de datos sin ranura el día del fallo desde julio de 2023, 174 de ellos sin ranura
  ningún día de su ventana.
- Fallos sin foto o sin día anterior. 210 fallos de discos que no salen en ninguna foto; 896 fallos de discos de datos
  sin el día anterior en su ventana, 902 contando los de arranque; 3.542 ventanas de menos de 31 filas.
- Horas que bajan. 3.468 veces en que las horas de un disco de datos bajan más de un día entre dos fotos, en 3.443
  discos; 3.414 de ellas bajan más de un año.
- Días hundidos en el recuento. El 06/06/2022, el 19/03/2023, el 13 y el 16/04/2023, el 05/07/2023, el 18/12/2023 y el
  12/05/2025, con los discos que faltan frente a los días de al lado.
- Tipos y nombres. La ranura leída como decimal, el centro sin tipo en las fotos anteriores a julio de 2023 y las dos
  erratas del esquema.

El diccionario añade una que el reconocimiento no vio, porque miró la temperatura solo en las fotos:

- Temperatura por encima de 70 grados en las ventanas. El contador 194 llega a 117 grados en las ventanas, frente a un
  máximo de 70 en las fotos. El script contará las filas por encima de 70 y de qué discos y días son.

## Reglas candidatas

Son reglas que se ven en los datos y que ningún documento fija. El script cuenta las filas que incumpliría cada una y no
la aplica. Si el responsable del caso aprueba alguna, pasa a las reglas de negocio y se comprueba en la ejecución siguiente.

- RC-01 · Las horas encendido de un disco no bajan entre dos fotos. Columna `smart_9_raw`; el reconocimiento contó 3.468
  bajadas de más de un día.
- RC-02 · El modelo y la capacidad de un disco no cambian entre fotos. Columnas `model` y `capacity_bytes`.
- RC-03 · Los cinco contadores de avería no bajan con el tiempo en un mismo disco. Las reglas, apartado 3 lo dan como supuesto
  («casi nunca vuelven a cero»); el script cuenta las bajadas.
- RC-04 · La temperatura está entre 10 y 70 grados. Columna `smart_194_raw`; en las ventanas hay valores de hasta 117.
- RC-05 · Toda foto con `failure = 1` está en la lista de fallos, el mismo disco y el mismo día. El reconocimiento casó
  las 563.
- RC-06 · En cada ventana, `failure = 1` solo el día del fallo. Columnas `failure`, `fecha` y `dia_fallo`.
- RC-07 · En el recuento, los fallos no pasan de los discos de su fila. Columnas `fallos` y `discos`.
- RC-08 · Los fallos de cada día del recuento suman los de la lista de fallos de ese día. El reconocimiento los vio
  cuadrar los 2.008 días.

## Riesgos para un modelo

La pregunta 4 entrena un modelo, así que el script señala estos riesgos como cuestiones a revisar y no decide nada sobre
ellos:

- El sitio falta al construir y está al validar. Centro, vault y ranura faltan en el 75 %, 68 % y 75 % de las fotos de
  construcción y casi nunca en validación (reconocimiento, sección 14).
- Los contadores 187 y 188 solo los traen los Seagate. Su vacío pasa del 48 % de la construcción al 64 % de la
  validación, porque cambia la mezcla de fabricantes.
- La variable objetivo está muy desequilibrada. Con el fallo a 90 días, la construcción tiene 34.001 casos frente a
  10.428.469 no casos (reconocimiento, sección 14). El objetivo aprobado es a 30 días (cuestión 004), y el script dará también
  esa cuenta.
- Las ventanas solo existen para discos que fallan. Usar sus columnas día a día para el modelo mezclaría con el objetivo
  información que solo tienen los que fallan.
- El modelo tiene 98 valores en las fotos, 83 de ellos por debajo del umbral de categoría rara.
- Columnas calculadas a partir de otras. Cada nota normalizada sale del valor en bruto de su contador, y la capacidad
  sale del modelo.

## Las decisiones del responsable del caso

Las cuatro son lecturas con más de una opción legítima que las reglas no fijan. El script diagnostica igual las columnas
afectadas y deja su posible acción como pregunta.

| Decisión | Columnas | Lecturas posibles |
|---|---|---|
| **D1 · Modelos que solo se distinguen por los espacios** | `model` en fotos, ventanas y recuento (P-01, P-05 y P-09 del diccionario) | son el mismo modelo escrito de dos formas y se cuentan juntos; o son modelos distintos, como los publica Backblaze, y se cuentan aparte |
| **D2 · Cómo se lee el 188** | `smart_188_raw` en fotos y ventanas (P-04 y P-08) | recuento de órdenes abortadas que se usa por su valor; formato propio del fabricante que solo vale como cero o no cero; no se usa ni como recuento ni como aviso |
| **D3 · Los valores del 5 y del 187 pegados a 65.535** | `smart_5_raw` y `smart_187_raw` en fotos y ventanas (P-02, P-03, P-06 y P-07) | son el tope del contador y el valor real es ese o mayor; o son un recuento real del disco |
| **D4 · El 0 de `cluster_id`** | `cluster_id` en fotos y ventanas | es un grupo de servidores más; o quiere decir «sin grupo» y es una ausencia |

## Límites de este plan

- El plan describe lo que hará el script. Las cifras que trae salen del diccionario y del reconocimiento; las del script
  de calidad saldrán de su propia ejecución.
- Los cuatro datasets traen de cada disco una foto al mes, y día a día solo los 30 días anteriores a cada fallo. Las
  comprobaciones que siguen a un disco en el tiempo (horas que bajan, contadores que bajan, huecos) tienen un mes de
  margen.
- El esquema se compara con las columnas de las fotos y las ventanas. Las 66 columnas que nombra y que esos datasets no
  traen se quitaron al preparar los cuatro datasets; desde aquí no se puede comprobar si estaban vacías o eran constantes.
- No existe `config/fuentes/proteccion-datos.json`: los datos no pasaron por la protección. El paso 2a se
  saltó el 17/11/2026 con el sí del responsable del caso porque no hay datos de personas (reglas, apartado 9), y ninguna columna es un dato personal.
- No se miran los datos de validación contra el fallo: en validación el script solo cuenta filas, vacíos y formatos.

## Lo aprobado

El responsable del caso aprobó el plan el 17/11/2026 («Sí, apruebo»). Las cuatro lecturas no eran decisiones de negocio, y quedaron
cerradas así, como criterio técnico:

- D1: los modelos que solo se distinguen por los espacios tras «WDC» son el mismo modelo, porque son los mismos
  discos, con el mismo número de serie, escritos de dos formas. La corrección los junta.
- D2: el 188 ya lo deciden las reglas: cuenta como aviso cuando pasa de cero (§3) y no entra en la suma de la regla
  de los contadores (§7, cuestión 010). Su valor como variable del modelo se mira en la preselección del paso 5.
- D3: el 5 y el 187 pegados a 65.535 se tratan como el tope del contador. No cambian nada: el disco avisa igual.
- D4: el 0 de `cluster_id` no se decide, porque ninguna pregunta usa esa columna. Se cuenta y se dice.

Las ocho reglas candidatas, de RC-01 a RC-08, entran como comprobaciones: el script cuenta las filas que las
incumplen y no cambia ni quita ninguna.
