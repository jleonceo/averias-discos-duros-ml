---
titulo: Modelo de datos del caso 68 · cuatro tablas de hechos, tres dimensiones y un tablón por pregunta
estado: opción del 17/11/2026, aprobada por el responsable del caso el mismo día («Sí, lo apruebo»). Comprobada con scripts/04_modelado_datos.py; sus cifras están en informes/modelado-datos.json
fecha_documento: 2026-11-17
dueno: El responsable del caso (decide)
---

# Modelo de datos del caso 68

Las cuatro tablas corregidas son cuatro tablas de hechos con grano distinto. Se quedan separadas, comparten tres
dimensiones que todavía no existen como fichero (`dim_modelo`, `dim_precio_gb` y `Calendario`) y de ellas se saca un
tablón por pregunta. El disco y el sitio no son tablas: van como atributos de cada fila de hechos. Las cuatro claves
de grano son únicas en los datos. Ningún cruce del plan une dos tablas de hechos fila a fila sin llevarlas antes al
mismo grano. Cuestión 011 la cerró el responsable del caso el mismo día.

## 1. Fuentes consultadas

- las instrucciones del caso.
- Negocio: `01_ficha_del_caso.md` (las cuatro preguntas, los KPI y las seis comprobaciones del modelo),
  `reglas-negocio.md` (§3 a §7) y `cuestiones-pendientes.md` (cuestión 001 a cuestión 010 cerradas).
- Método: `como_estan_organizados_los_datos.md` (la opción de hechos, dimensiones y tablones que este diseño fija) y
  `plan_de_la_analitica.md` (los nueve bloques).
- Modelo: `registro-transformaciones.md` (R-001 a R-009) y `decisiones-correccion.json`.
- Sector: `precios_de_coste_discos.md`.
- Informes: `correccion-datos.json` (estado AVISO, sin pendientes; las huellas de las cuatro tablas) y
  `calidad-datos.json` (sus seis cruces ya contados).
- Las cuatro tablas de `data/processed/`, solo las columnas que pide cada comprobación.
- No existen `negocio/reglas-transformacion.md`, que se escribe después de este diseño, ni
  `fuentes/proteccion-datos.json`: no hay datos personales (reglas, apartado 9).

## 2. Preguntas y lo que necesitan

| Pregunta | Qué se mide | Ejes | Fecha y periodo |
|---|---|---|---|
| 1. Qué modelo de cada capacidad sale más barato por TB y año | coste por TB y año, con la tasa anual de fallo al lado | modelo dentro de cada capacidad; año y trimestre | `fecha` del recuento y `dia_fallo`; del 01/01/2020 al 30/06/2025 |
| 2. A partir de qué año de vida sube la tasa de cada modelo | tasa anual por año de edad y supervivencia | año de edad; todos los discos y cada modelo | `fecha` del recuento repartida con la foto del mes; edad de cada día de disco |
| 3. Si hay centros o tomos con más fallos de los que les tocan | tasa por centro, bruta y ajustada por modelo y edad; fallos que coinciden en un tomo frente a lo esperado | centro, tomo (centro, vault y ranura), trimestre | del 01/07/2023 al 30/06/2025 |
| 4. Qué discos tienen más riesgo y qué tomos están en peligro | fallos señalados por el modelo frente a la regla de los cinco contadores | disco y foto mensual; tomo | fecha de la foto; construcción hasta el 30/06/2024 y validación hasta el 30/06/2025 |
| Fallos previstos frente a reales (bloque 9) | fallos de la cuenta entre fallos reales | trimestre y capacidad | primer día de cada trimestre, de 2021 a junio de 2025 |
| Fallos sin aviso | fallos sin ningún contador por encima de cero el día anterior | todos los discos; dentro de cada fabricante | `dia_fallo` y el día anterior |

Las cuatro preguntas se pueden contestar con las tablas que hay; los límites de cada una son los de la ficha
(«Veredicto de cada pregunta»).

### Cada pregunta de punta a punta

| Pregunta | Cifra final | Fórmula | Estadístico | Población | Exclusiones | Mínimo |
|---|---|---|---|---|---|---|
| 1. Modelo más barato por TB y año | Coste por TB y año, contando las averías, de cada modelo, ordenado dentro de cada capacidad y año de compra (reglas, apartado 7, 18/11/2026; el orden de todos juntos va al lado), con su tasa anual de fallo al lado; con 6 años de vida y la vida real al lado; con y sin garantía (ficha, KPI) | Por disco y año: precio / capacidad / 6 años, más tasa anual de fallo × (precio de un disco nuevo + 37 dólares) / capacidad, con la tasa en tanto por uno; tasa anual = 100 × 365 × fallos / días de disco (reglas, apartado 6) | Ratio de sumas (fallos entre días de disco del recuento, nunca fotos sueltas). Dos modelos se distinguen si el intervalo al 95 % de la diferencia de sus tasas no cruza el cero (`poblacion_del_analisis.md`, regla 5); el precio es el mismo dentro de una capacidad y un año de compra, así que el intervalo del coste es el de su tasa (reglas, apartado 6 y §7) | Discos de datos, todos de 4 TB o más, del 01/01/2020 al 30/06/2025 (reglas, apartado 7, «Coste por terabyte») | Discos de arranque, que no tienen precio; la reserva | 50.000 días de disco en el año (reglas, apartado 7). El ranking de todo el periodo toma los modelos que pasan el mínimo algún año, que son los 32 de la ficha; por trimestre, los que lo pasan en el año de ese trimestre. Los demás se enseñan aparte con su recuento |
| 2. Año de vida en que sube la tasa | Tasa anual por año de edad, del conjunto de discos y de los modelos con más discos y el año en que sube; supervivencia por modelo a los 1, 3 y 5 años (plan, bloque 3); al lado, la misma cifra contando como fallo a los que avisaban al desaparecer (reglas, apartado 3) | Tasa anual = 100 × 365 × fallos / días de disco, con la edad de cada día de disco; edad = horas encendido pasadas a años, o desde el primer día que aparece si no las trae (reglas, apartado 3) | Ratio de sumas por año de edad. La tasa sube cuando el intervalo al 95 % de un año de edad no se solapa con el del año anterior (reglas, apartado 7, cuestión 009). Supervivencia con Kaplan-Meier: los que desaparecen, censurados; cada disco entra a la edad del primer día que se le ve; la vida acaba en el primer fallo (plan, bloque 3; `poblacion_del_analisis.md`, regla 6) | Discos de datos, del 01/01/2020 al 30/06/2025 (reglas, apartado 7, «Tasas de fallo y previsión») | Discos de arranque; la reserva | Un año de edad con menos de 20 fallos se enseña sin conclusión (reglas, apartado 7, cuestión 009); en el conjunto de discos, cada año de 0 a 8 pasa de 20 fallos y por modelo no llegan 99 de 207 celdas de modelo y edad |
| 3. Centros o tomos con más fallos de los que les tocan | Por centro, la tasa bruta y la ajustada por modelo y edad, una al lado de otra; por tomo, los fallos que coinciden en un tomo frente a lo esperado al azar (plan, bloques 5 y 7) | Tasa anual por centro y trimestre; tasa ajustada: la que saldría si todos los centros tuvieran la misma mezcla de discos (plan, bloque 5). Dos fallos del mismo tomo coinciden si el segundo llega antes de que acabe de rehacerse el primero: un día por TB más uno, con la capacidad del primero; el último día ya no coincide (reglas, apartado 7) | Ratio de sumas por centro. Un centro falla más «por sí mismo» solo si su tasa sigue más alta con la misma mezcla de modelos, edades y trimestres (reglas, apartado 7, 18/11/2026), mirado con el intervalo al 95 % ensanchado con φ (reglas, apartado 7). Tomos: fallos que coinciden entre los esperados con la tasa diaria del conjunto de discos en los 19 discos restantes del tomo, como se midió el 4,02 de cuestión 004 | Fallos y días de disco de discos de datos del 01/07/2023 al 30/06/2025 con su centro; para el tomo, con centro, vault y ranura (reglas, apartado 7, «Población del análisis») | Lo anterior al 01/07/2023, sin sitio; los días y fallos sin centro desde esa fecha; los fallos sin tomo. Contados y dichos | Cada centro, 50.000 días de disco en el año (reglas, apartado 7); la tasa ajustada, con los 21 modelos que llegan al mínimo en dos centros o más (plan, bloque 5) |
| 4. Discos de más riesgo y tomos en peligro | Una lista mensual de los discos de más riesgo para los técnicos y el aviso de tomos en peligro; medidos en fallos señalados frente a la regla de los cinco contadores (ficha; reglas, apartado 6) | Acierto entre los de más riesgo: de los N discos que el modelo pone primero, cuántos fallan en el horizonte, frente a la regla. Fallos señalados en tomos en peligro: de los fallos que llegan en un tomo donde acaba de fallar un disco, cuántos estaban entre los que el modelo puso primero, frente a la regla (ficha, KPI). Objetivo: que el disco falle en los 30 días siguientes a la foto, con todos los fallos (reglas, apartado 7, cuestión 003 y cuestión 004) | Proporciones por foto mensual, en listas de 20, 100, 500 y 1.000 discos al mes, con la regla ordenada por cuántos contadores avisan y, a igualdad, por su suma sin el 188 (reglas, apartado 7, cuestión 010); la correlación de Matthews al lado; sin exactitud (plan, notas para el modelo). Modelo y regla se distinguen si el intervalo al 95 % de su diferencia no cruza el cero (reglas, apartado 7; `poblacion_del_analisis.md`, regla 5) | Una fila por disco de datos y foto mensual; construcción hasta el 30/06/2024 y validación del 01/07/2024 al 30/06/2025, que se mira una sola vez (reglas, apartado 7) | Discos de arranque; las fotos del día en que el disco falla; el horizonte que pasa del borde de su periodo se recorta (decisiones de modelado) | El que dan las listas de cuestión 010 en las 12 fotos de validación, con 4.518 fallos para validar (ficha); el tamaño de la lista lo elige Backblaze (reglas, apartado 7) |
| Fallos previstos frente a reales (bloque 9) | Fallos reales y previstos por trimestre, por capacidad, con la referencia de repetir los fallos del trimestre anterior (plan, bloque 9) | Fallos esperados de un trimestre = días de disco que habrá de cada modelo y año de edad × su tasa anual a esa edad / 365, sumados por capacidad; los días, con los discos del primer día del trimestre y su edad ese día; las tasas, medidas hasta el día anterior (plan, bloque 9; reglas, apartado 3 y §7) | Fallos de la cuenta / fallos reales, por trimestre y capacidad; mejor cerca de 1 (ficha, KPI). La cuenta solo vale si gana a la referencia (reglas, apartado 7). Gana si su error absoluto ponderado de todos los trimestres y capacidades es menor que el de la referencia, con el sesgo al lado (reglas, apartado 7, cuestión 011) | Discos de datos, todos los modelos (reglas, apartado 7, «Tasas de fallo y previsión») | Discos de arranque; la reserva, hasta la prueba final | Los trimestres de 2021 a junio de 2025 (plan, bloque 9); todos juntos, en una sola cifra (cuestión 011) |
| Fallos sin aviso | Parte de los fallos que llegan sin aviso (ficha, KPI) | Fallos sin ningún contador de avería por encima de cero el día anterior / fallos; un contador vacío no cuenta como aviso (reglas, apartado 6) | Proporción sobre todos los discos; el porcentaje no se compara entre fabricantes, porque fuera de Seagate el aviso depende de tres contadores (reglas, apartado 3) | Fallos de discos de datos, del 01/01/2020 al 30/06/2025 | Discos de arranque; los fallos cuya ventana no trae el día anterior | No se compara entre grupos: no aplica |

La cifra final se define igual en la ficha, las reglas y el plan en las seis filas. La ficha da 4.518 fallos para
validar y el plan cuenta la tasa por centro con 8.634 fallos; el script da las mismas cifras de fallos de discos de
datos en esos periodos.

## 3. Tablas

### Hechos

| Tabla | Fichero | Grano: una fila es… | Clave del grano | Medidas y atributos principales |
|---|---|---|---|---|
| `hechos_fotos` | `fotos_mensuales_corregido.parquet` | un disco el día 1 de un mes | `serial_number`, `fecha` | horas encendido y contadores de avería (niveles: no se suman entre fotos); modelo, capacidad, sitio; `failure`, el fallo de ese día |
| `hechos_ventanas` | `ventanas_fallo_corregido.parquet` | un disco un día, dentro de la ventana de uno de sus fallos: los 30 días anteriores y el del fallo | `serial_number`, `fecha`; cada fila pertenece al fallo (`serial_number`, `dia_fallo`) | lo mismo que las fotos, día a día, solo de los discos que fallan |
| `hechos_recuento` | `recuento_diario_corregido.parquet` | un día, un modelo, una capacidad y un centro | `fecha`, `model`, `capacity_bytes`, `datacenter`; «sin dato» es el centro que no consta | `discos` (cuántos había ese día; sumados por días son días de disco) y `fallos` |
| `hechos_fallos` | `fallos_corregido.parquet` | un disco el día que Backblaze lo da por fallado | `serial_number`, `dia_fallo` | el fallo; no trae modelo |

En las fotos y las ventanas, `date` repite `fecha` en todas las filas (0 distintas). El modelo usa `fecha`; `date` no
entra en ningún cruce.

El modelo de cada fila es el que trae esa fila. Un disco no se une a su modelo por el número de serie: el 5QJB76AB sale
con dos modelos. La lista de fallos no trae modelo y lo toma de la fila del día del fallo de su ventana (cruce 1).

### Dimensiones

Ninguna existe hoy como fichero. Las construye la transformación con este diseño aprobado. El Calendario lo
construye `scripts/04_modelado_datos.py` cuando lee la aprobación.

**`dim_modelo`**, una fila por modelo, clave `model` (texto). Sale de los 94 modelos del recuento, que son los mismos
que los de las fotos; los 71 de las ventanas están todos en el recuento.

| Atributo | De dónde sale |
|---|---|
| capacidad en TB | `capacity_bytes` del modelo, una sola por modelo tras R-005; un TB son 1.000 GB (reglas, apartado 6) |
| fabricante | el nombre del modelo, con los dos que no siguen el patrón (reglas, apartado 3) |
| tipo de disco | de arranque, de 0,2 a 2 TB, hasta 2.048.408.248.320 bytes; de datos, desde 4 TB (reglas, apartado 3 y §7). Son 33 y 61; ninguno entre 2 y 4 TB |
| garantía en años | la familia del modelo: 5, 3 o 2 años; sin garantía comprobada en los demás (reglas, apartado 6) |
| fecha de compra | la entrada media de todos sus discos vistos de 2020 a junio de 2025: para cada disco, la fecha de su primera foto menos sus horas encendido (reglas, apartado 6) |
| precio en dólares | coste por GB de su capacidad en su fecha de compra × capacidad en GB, de `precios_de_coste_discos.md`, con las capacidades vecinas si falta la suya (reglas, apartado 6); vacío en los de arranque y en los cuatro modelos de 6 TB sin precio que dice esa tabla |

La fecha de compra y el precio se calculan con todo el periodo: son una ficha de hoy, no lo que se sabía en cada fecha.

**`dim_precio_gb`**, una fila por capacidad y año, clave `capacidad_tb` y `ano`, con el coste por GB y su origen
(artículo, gráfico o inferido), de `precios_de_coste_discos.md`. Da el precio del disco nuevo que sustituye a uno que
falla, al coste por GB del año del fallo (reglas, apartado 6).

**`Calendario`**, una fila por día. Su detalle está en el apartado 6.

### Por qué el disco y el sitio no son tablas

- **El disco** se queda como atributo de cada fila (`serial_number`). Lo que lo describe cambia con el tiempo: el modelo
  puede cambiar entre dos fotos (queda 1 cambio real tras la corrección, R-009), la edad cambia cada día y el sitio
  también. Una tabla de discos con un solo modelo por disco pondría mal el del 5QJB76AB. Lo que la pregunta 2 necesita
  por disco (primer día, último día, primer fallo, si desaparece) es el tablón de esa pregunta, que hace la transformación.
- **El sitio** (`datacenter`, `vault_id`, `pod_id`, `pod_slot_num`) se queda como atributo de las fotos, las ventanas y,
  el centro, del recuento. Solo consta desde el 01/07/2023 y cambia con el tiempo (reglas, apartado 4): un disco se migra y un
  hueco recibe muchos discos. El tomo (centro, vault y ranura) no tiene ningún atributo fijo que poner en una tabla, así
  que es una clave que calcula la transformación en el tablón de la pregunta 3.

### La tabla «Cada dato a la fecha» del tablón de la pregunta 4

Una fila por disco de datos y foto mensual: 14.604.861 filas, 11.026.052 de construcción y 3.578.809 de validación,
sin las 528 fotos del día del fallo. Ningún dato se conoce después de la fecha de la foto salvo el objetivo.

| Dato | Tabla de origen | Fecha con que se corta | Valor que toma | Regla que lo define | Desde cuándo se conoce |
|---|---|---|---|---|---|
| disco y fecha de la foto | `hechos_fotos` | la foto | `serial_number` y `fecha` de la fila | grano del tablón (ficha, «el modelo se entrena como se usará») | el día de la foto |
| modelo | `hechos_fotos` | la foto | el `model` de esa fila | el modelo de cada fila es el que trae esa fila | el día de la foto |
| capacidad, fabricante, tipo de disco | `dim_modelo` | ninguna: no cambian | los del modelo de la fila | reglas, apartado 3 | el día de la foto |
| garantía en años | `dim_modelo` | ninguna: es la ficha del fabricante | los años de su familia | reglas, apartado 6 | el día de la foto |
| edad | `hechos_fotos` | la foto | horas encendido de la fila pasadas a años; sin ellas, días desde la primera aparición del disco, que nunca es posterior a la foto | reglas, apartado 3 | el día de la foto |
| contadores de avería (5, 187, 188, 197 y 198) y si avisa | `hechos_fotos` | la foto | el valor de la fila; el 188, como cero o no cero; vacío si el modelo no lo apunta | reglas, apartado 3 y §5; plan, «Lo que hay que comprobar» | el día de la foto |
| cambio de un contador | `hechos_fotos` | la foto | la diferencia con las fotos anteriores del mismo disco | plan, notas para el modelo | el día de la foto |
| sitio (centro, vault, ranura) | `hechos_fotos` | la foto | el de la fila; vacío antes del 01/07/2023. Si entra lo decide el paso 5 | reglas, apartado 4; plan, notas para el modelo | el día de la foto |
| periodo | `Calendario` | la foto | construcción hasta el 30/06/2024; validación desde el 01/07/2024 | reglas, apartado 7 | el día de la foto |
| fecha de compra y precio del modelo | `dim_modelo` | ninguna: se calculan con todo el periodo | los del modelo | reglas, apartado 6 | **ficha de hoy**: se calculan con datos hasta junio de 2025. Si entran en la pregunta 4, el modelo ve algo que no se sabía el día de la foto |
| `failure` | `hechos_fotos` | la foto | el fallo de ese día | reglas, apartado 3 | no es una variable: las filas con `failure = 1` salen del tablón |
| objetivo | `hechos_fallos` | el horizonte: del día siguiente a la foto hasta 30 días después, recortado al 30/06/2024 en construcción y al 30/06/2025 en validación | 1 si el disco tiene un fallo en el horizonte | reglas, apartado 7, cuestión 003 y cuestión 004 | hasta 30 días después de la foto; es el único dato posterior |

## 4. Relaciones

| Desde | Hacia | Clave a cada lado | Maestro | Cardinalidad | De dónde sale | Sin pareja |
|---|---|---|---|---|---|---|
| `hechos_fotos`, `hechos_ventanas`, `hechos_recuento` | `dim_modelo` | `model` → `model` | `dim_modelo` | N:1 | reglas, apartado 3: el modelo es la unidad de compra y la capacidad de un disco es la de su modelo; `como_estan_organizados_los_datos.md`, dimensión modelo | no se esperan: cuenta integración |
| `hechos_fallos` (con el modelo de su fila del día del fallo) | `dim_modelo` | `model` → `model` | `dim_modelo` | N:1 | lo mismo | lo mismo |
| `hechos_fotos`, `hechos_ventanas`, `hechos_recuento` | `Calendario` | `fecha` → `fecha` | `Calendario` | N:1 | reglas, apartado 5: cada registro es el estado de un disco un día | el Calendario cubre todos los días del recuento |
| `hechos_fallos` | `Calendario` | `dia_fallo` → `fecha` | `Calendario` | N:1 | reglas, apartado 3: el fallo es un día | lo mismo |
| `hechos_ventanas` | `hechos_fallos` | `serial_number`, `dia_fallo` → `serial_number`, `dia_fallo` | `hechos_fallos` | N:1 | `como_estan_organizados_los_datos.md` (una ventana son los 30 días antes de un fallo y el del fallo); reglas, apartado 5 | ninguna en los datos: 0 fallos sin ventana |
| `hechos_fallos` | `hechos_ventanas`, fila del día del fallo | `serial_number`, `dia_fallo` → `serial_number`, `fecha` | `hechos_ventanas` | 1:1 | reglas, apartado 5: un registro por disco y día, el del fallo incluido | 0 fallos sin esa fila |
| `hechos_fallos` | `dim_precio_gb` | capacidad del modelo y año del fallo → `capacidad_tb`, `ano` | `dim_precio_gb` | N:1 | reglas, apartado 6: el disco nuevo, al coste por GB del año del fallo | la capacidad sin precio ese año toma las vecinas (reglas, apartado 6); resuelto en `../negocio/reglas-transformacion.md` §1, aprobado el 17/11/2026: las dos capacidades más cercanas con curva ese día |

Ninguna cardinalidad sale de los datos: todas salen de las reglas y de la organización de los datos.

**Tipos de las claves.** `dia_fallo` viene en nanosegundos y `fecha` en milisegundos, en la lista de fallos, en las
ventanas y en el Calendario. El script lo enseña como diferencia de tipo en las dos relaciones que la tienen y no lo
corrige: lo iguala la transformación antes de cruzar. Las demás claves tienen el mismo tipo a los dos lados.

**El centro vacío.** En las fotos y las ventanas el centro que no consta está vacío; en el recuento es «sin dato» (R-009).
Antes de cruzar fotos con recuento se iguala el vacío a «sin dato», sin guardarlo en las tablas corregidas.

## 5. Hechos con grano distinto

Ninguna tabla de hechos se une fila a fila con otra de grano distinto. Cada par que una pregunta necesita junto se
relaciona así:

- **Recuento y fotos (preguntas 2 y 3, bloque 9).** Los días de disco salen siempre del recuento. Lo que depende del
  disco (edad, si avisa, sitio) se toma de la foto de su mes. Los días de ese mes se reparten con ella (reglas, apartado 5,
  «Con qué se cuentan»). Se lleva cada tabla al grano común antes de unirlas: las fotos, contadas por modelo, centro,
  mes y tramo, dan la parte de cada tramo; el recuento, sumado por modelo, centro y mes, da los días que se reparten
  (cruce 11).
- **Recuento y fallos (preguntas 1 a 3).** Por separado, a través de las dimensiones que comparten: los fallos, con su
  modelo, edad y sitio, se agregan al mismo grano que los días repartidos y se ponen al lado (cruce 15). La tasa de
  todo un modelo puede usar los fallos del propio recuento, que cuadran con la lista (calidad, cruce recuento y fallos).
- **Fallos y ventanas.** Cada fallo toma una sola fila de su ventana, elegida por una regla de fecha: el día del fallo
  (modelo, horas), el día anterior (aviso) y el último día con sitio (sitio del fallo) (cruces 1 a 3).
- **Fotos y fallos (pregunta 4).** El objetivo es un cruce a una fecha: cada fallo marca las fotos de su disco cuyo
  horizonte lo contiene. Se une a las fotos una fila por disco y foto, así que el tablón no gana filas (cruce 12).
  En sentido contrario, cada fallo toma la última foto de su disco anterior al fallo, para saber su puesto en la lista
  (cruce 13).
- **Fallos del mismo tomo (preguntas 3 y 4).** No es un cruce: dentro de la lista de fallos con tomo, ordenada por tomo
  y día, se mira si cada fallo llega antes de que acabe de rehacerse el anterior (reglas, apartado 7).

## 6. Fechas y calendario

| Columna | Evento | Granularidad |
|---|---|---|
| `fecha` de las fotos | el día de la foto, siempre día 1: 66 meses, de enero de 2020 a junio de 2025, sin huecos | día |
| `fecha` de las ventanas | el día del registro dentro de la ventana: 2.007 días; falta el 10/12/2022, cuyas filas quitó R-007 | día |
| `fecha` del recuento | el día contado: 2.008 días, del 01/01/2020 al 30/06/2025, sin ninguno que falte | día |
| `dia_fallo` de la lista de fallos y de las ventanas | el día del fallo | día (en nanosegundos) |

El **Calendario** tiene una fila por día, del primer al último día del recuento. El script toma los dos extremos de los
datos y no lleva fechas fijas en el código, porque en producción entran datos cada trimestre. Columnas: `fecha`,
`ano`, `trimestre`, `mes`, `periodo` (construcción hasta el 30/06/2024, validación del 01/07/2024 al 30/06/2025,
reserva hasta el 30/06/2026; reglas, apartado 5 y §7), `trimestre_completo` y `ano_completo`. Hoy el primer trimestre y el
último están completos y el único periodo parcial es el año 2025, que no se compara con uno completo (reglas, apartado 5).

Las fotos, las ventanas y el recuento se unen al Calendario por `fecha`; la lista de fallos, por `dia_fallo`. El
Calendario se construye solo cuando el responsable del caso apruebe este diseño (método, §9).

## 7. Forma de entrega al análisis

Tablas separadas y un tablón por pregunta, como proponía `como_estan_organizados_los_datos.md`. Las cuatro tablas de
hechos tienen grano distinto y ninguna pregunta comparte el grano de otra: la 1 va por modelo y año, la 2 por modelo,
mes y año de edad, la 3 por sitio y mes; la 4 por disco y foto.

**Integración antes de la transformación: nada.** Ningún cruce del plan se puede hacer con las tablas tal como están.
Todos piden una dimensión o el Calendario, que construye la transformación, o filtrar o agregar antes con una regla: el
día del fallo, el día anterior, el último día con sitio, el horizonte o el reparto de días. Por eso los hace la
transformación, con los controles de `integracion-datos` (`transformacion-datos`: solo cruza lo que el plan
aprobó, con clave única, claves sin pareja y sumas de control antes y después).

## 8. Plan de cruces

La configuración que se aplica es el `plan_cruces` de `informes/modelado-datos.json`; aquí va en resumen. Todos son
por la izquierda desde la tabla de partida.

| Orden | Partida | Se une | Clave | Cardinalidad | Antes de cruzar | Se controla |
|---:|---|---|---|---|---|---|
| 1 | fallos | ventanas, fila del día del fallo | `serial_number`, `dia_fallo` → `serial_number`, `fecha` | 1:1 | filtrar las ventanas a `fecha = dia_fallo` | filas de fallos |
| 2 | fallos | ventanas, fila del día anterior | lo mismo, con `dia_fallo` − 1 | 1:1 | filtrar a ese día | filas de fallos |
| 3 | fallos | ventanas, sitio del fallo | `serial_number`, `dia_fallo` | 1:1 | la última fila hasta el día del fallo con centro; la última con centro, vault, servidor y ranura | filas de fallos |
| 4 | fallos | `dim_modelo` | `model` | N:1 | | filas de fallos |
| 5 | fallos | `dim_precio_gb` | capacidad y año del fallo | N:1 | | filas de fallos |
| 6 | fallos | `Calendario` | `dia_fallo` → `fecha` | N:1 | igualar el tipo | filas de fallos |
| 7 | recuento | `dim_modelo` | `model` | N:1 | | discos y fallos |
| 8 | recuento | `Calendario` | `fecha` | N:1 | | discos y fallos |
| 9 | fotos | `dim_modelo` | `model` | N:1 | | filas de fotos |
| 10 | fotos | `Calendario` | `fecha` | N:1 | | filas de fotos |
| 11 | fotos agregadas | recuento agregado | modelo, centro y mes | N:1 | fotos por modelo, centro, mes y tramo; recuento por modelo, centro y mes | días de disco |
| 12 | fotos de discos de datos | fallos, como horizontes | `serial_number`, fecha de la foto | N:1 | una fila por disco y foto cuyo horizonte contiene un fallo | filas del tablón; suma del objetivo |
| 13 | fallos | fotos, la última anterior al fallo | `serial_number`, fecha de esa foto | N:1 | la fecha de la última foto del disco dentro del horizonte | filas de fallos |
| 14 | fotos del primer día del trimestre | tasas por modelo y edad hasta el día anterior | modelo, año de edad y trimestre | N:1 | discos contados por modelo y edad; tasas de los cruces 1, 4 y 11 | discos del día |
| 15 | días repartidos | fallos agregados | modelo, centro, mes y tramo | 1:1 | los dos al mismo grano | días de disco y fallos |

## 9. Decisiones de modelado

| Decisión | Por qué | Quién y cuándo | Medida |
|---|---|---|---|
| El horizonte del objetivo se recorta en el borde de su periodo: la foto del 01/06/2024 mira hasta el 30/06/2024 y la del 01/06/2025 hasta el 30/06/2025 | Las reglas dicen que una foto cuyo horizonte acaba después «se recorta o se queda fuera» (§7). Recortar conserva la foto entera; dejarla fuera la perdería | el analista, 17/11/2026, por la petición del diseño | En la foto del 01/06/2024 el recorte pierde 16 de los 401 fallos de discos de esa foto en su horizonte. En la del 01/06/2025 lo que se pierde está en la reserva y no se puede saber hasta la prueba final |
| Las fotos del día en que el disco falla (`failure = 1`) quedan fuera del tablón de la pregunta 4 | Ese día el disco ya está marcado como fallado | el analista, 17/11/2026, por la petición del diseño | 528 fotos de discos de datos, 373 de construcción y 155 de validación |
| El disco y el sitio son atributos de los hechos, no tablas | Cambian con el tiempo y no tienen atributos fijos (apartado 3) | el analista, 17/11/2026 | 1 cambio de modelo entre fotos tras la corrección (R-009) |
| La lista de fallos toma el modelo de la fila del día del fallo de su ventana | La lista no trae modelo y el modelo de cada fila es el que trae esa fila | el analista, 17/11/2026, por la petición del diseño | los 17.960 fallos tienen esa fila |
| `dim_precio_gb` como dimensión aparte de `dim_modelo` | El precio del disco nuevo va por el año del fallo, no por el año de compra del modelo (reglas, apartado 6) | el analista, 17/11/2026 | |

El responsable del caso aprobó el diseño el 17/11/2026 («Sí, lo apruebo»); cuestión 011 la cerró después, con la cascada. El diseño no cambia.

Aprobado: sí · el responsable del caso · 2026-11-17

## 10. Observaciones y pendientes

### Registro de exclusiones

Una fila por clase de registro que sale de algún cálculo. Los recuentos los saca el script y están en
`exclusiones` de `informes/modelado-datos.json`; aquí se copian los principales.

| Qué sale | De qué cálculo | Cómo se trata | Recuento | Recuperable |
|---|---|---|---|---|
| Discos de arranque (33 modelos) | todas las tasas, rankings, coste, previsión y pregunta 4 | fuera de todo cálculo (reglas, apartado 3) | 7.500.739 días de disco, 964 fallos, 246.280 fotos | sí: se cuentan aparte si se pide |
| Sitio que no consta antes del 01/07/2023 | tasas por centro y tomos | fuera de las cifras por sitio (reglas, apartado 4) | 238.811.405 días de disco y 8.362 fallos de discos de datos | no: no está en los datos |
| Centro «sin dato» desde el 01/07/2023 | tasas por centro | contado y dicho (reglas, apartado 5) | 6.621.213 días de disco y 128 fallos de discos de datos | no, con estos datos |
| Fallos sin ranura en su ventana, desde el 01/07/2023 | tasas por centro y tomos; aviso de tomos en peligro | contados y dichos (reglas, apartado 5) | de 8.634 fallos, 128 sin centro y 141 sin tomo | no, con estos datos |
| Fallos sin el día anterior en su ventana | fallos sin aviso | fuera del indicador, contados | 903 de 16.996 fallos de discos de datos | no: el día no está |
| Modelos por debajo de 50.000 días de disco en el año | rankings de modelos | se enseñan aparte (reglas, apartado 7) | de 20 a 29 modelos cada año; 32 de los 61 pasan algún año. En 2025, con medio año, no llegan 20 de 47 | sí: aparte, fuera del ranking |
| Años de edad con menos de 20 fallos | conclusión de la pregunta 2 | se enseñan sin conclusión (cuestión 009) | ninguno en el conjunto de discos; 99 de 207 celdas de modelo y edad, con 462 fallos | sí: sin conclusión |
| Modelos con menos de 20 fallos en sus años que pasan el mínimo | rankings de modelos | sin puesto y «sin conclusión» (reglas, apartado 7, cuestión 012, 18/11/2026) | 5 de 32 en el ranking de B2 | sí: con su tasa, sus fallos y sus días |
| Fotos del día del fallo | tablón de la pregunta 4 | fuera del tablón | 528 de discos de datos | no: ya están marcadas como falladas |
| Horizonte que pasa del borde del periodo | objetivo de la pregunta 4 | recortado | 16 fallos en la foto del 01/06/2024; la del 01/06/2025, no se puede saber | el de construcción, no sin mezclar periodos; el de validación, solo con la reserva |
| 228 filas de las ventanas del 10/12/2022 | ventanas de fallo, en la corrección | quitadas (R-007) | 228 filas, ninguna con un fallo | no: eran copias del 11/12/2022 |

### Lo que el script comprueba y lo que no

- El script comprueba el grano y los tipos de las claves. Si las claves casan entre tablas lo mide `integracion-datos`,
  o la transformación con sus controles.
- En pandas, a diferencia de SQL, las claves vacías se emparejan entre sí al cruzar. El plan iguala el centro vacío a
  «sin dato» antes de cruzar fotos con recuento; el sitio vacío de un fallo no se cruza, se cuenta.
- Un maestro que cambia con el tiempo se modela con la versión que hay, no con la vigente en la fecha de cada hecho.
  Aquí lo es `dim_modelo`: su fecha de compra y su precio son una ficha de hoy.

### Interpretaciones sin validar

- **La mezcla de referencia de la tasa ajustada por centro.** El plan dice «la tasa ajustada que saldría si todos los
  centros tuvieran la misma mezcla de discos» y las reglas, «con la misma mezcla de modelos, edades y trimestres que los
  demás» (trimestre añadido el 18/11/2026). El diseño lo lee como la mezcla de todos los centros juntos, del 01/07/2023
  al 30/06/2025.
- **Lo esperado al azar en un tomo.** Se toma como se midió el 4,02 de cuestión 004: la tasa diaria del conjunto de discos en los 19
  discos restantes del tomo.
- **El sitio de un fallo** se busca hasta el propio día del fallo y, si ese día no lo trae, en los anteriores (reglas, apartado 5;
  plan, bloque 7: «la ranura de un fallo que no la trae se toma del día anterior»).
- **La edad al fallar del registro de exclusiones** usa las horas del día del fallo o del anterior y, sin ellas, los
  días desde la primera aparición; 79 fallos van por la primera aparición. La regla exacta la fija la transformación.

### Discrepancias entre fuentes y datos

- Las reglas (§6) decían que el día anterior a un fallo «siempre está en los 30 días que se guardan». En los datos
  falta en 903 fallos de discos de datos, 7 de ellos por las filas quitadas el 10/12/2022 (R-007). Corregido en las
  reglas el 17/11/2026 con la cascada: esos fallos salen del indicador y se cuentan aparte.
- 210 fallos son de discos que no salen en ninguna foto. Cuentan en las tasas, porque el recuento los incluye. No
  pueden ser objetivo de la pregunta 4, porque no tienen foto.
- Del 01/07/2026 en adelante el Calendario no tiene periodo: las reglas no lo definen. Hoy no hay datos de esas fechas.

### Pendiente del responsable del caso

- Nada. Cuestión 011 la cerró el responsable del caso el 17/11/2026 («Sí, ciérrala así»): la previsión del bloque 9 gana a repetir los fallos
  del trimestre anterior si su error absoluto ponderado es menor, con el sesgo al lado (reglas, apartado 7).
- **La aprobación de este diseño.** Hasta que esté, `informes/modelado-datos.json` queda en PARADO, el Calendario no se
  construye y no se escriben las reglas de transformación. (Cumplido: El responsable del caso aprobó el diseño el 17/11/2026, el
  Calendario se construyó y las reglas de transformación se escribieron y se aprobaron ese mismo día.)
