---
titulo: Reglas de negocio del caso 68 · qué es un disco, un fallo y un día de disco en los centros de datos de Backblaze, cómo se cuenta la tasa de fallo y con qué se valora
estado: aprobadas por el responsable del caso el 17/11/2026 («Sí, se aprueban»), tras la prueba de comprensión. Primera versión del 16/11/2026. Lo abierto está en `cuestiones-pendientes.md`
fecha_documento: 2026-11-16
dueno: El responsable del caso (decide)
fuentes: `00_briefing.md`; `01_ficha_del_caso.md`; `matriz_de_impacto.md`; `../sector/como_trabaja_backblaze.md`; `../sector/mapa_del_sector.md`; `../sector/precios_de_coste_discos.md`; `../fuentes/ficha_de_los_datos.md`; `../metodo/plan_de_la_analitica.md`; los documentos de `../sector/documentos/`, citados por su número; el registro del caso
---

# Reglas de negocio de Backblaze

La empresa y los datos son reales: Backblaze publica cada día el estado de sus discos. La petición y las personas son
inventados. Lo que no sale de los datos ni de un documento de Backblaze o del sector va marcado como **(supuesto)**.

## 1. La petición

La petición de la dirección de operaciones de los centros de datos está en `00_briefing.md`: el problema, los
objetivos, las preguntas de partida, el alcance y lo que se entrega. Este documento no lo repite. Las preguntas que se
contestan son las que se aprueben en el paso 1, en «El problema» de `01_ficha_del_caso.md`.

## 2. Contexto del negocio

Backblaze vende almacenamiento en la nube (B2), desde 6,95 dólares por terabyte al mes (doc. 15) y copias de seguridad
de ordenadores (doc. 14). En 2025 ingresó 145,8 millones de dólares: 77,2 por contratos de consumo, 68,2 por suscripciones y 0,4 por ventas
puntuales (doc. 16, que da también 2023 y 2024). Tiene más de 500.000 clientes en más de 175 países.

Guarda los datos en discos duros suyos o en arrendamiento financiero, montados en seis centros de datos alquilados de
cuatro regiones, en Estados Unidos, Canadá y Países Bajos (docs. 12b y 14). Su coste de los ingresos es sobre todo el
alquiler de esos centros, la red y la amortización de los equipos (doc. 14). Si los fallos cambian con la época del año
no consta: se mide en el reconocimiento de los datos.

### Personas

| Papel | Quién | Qué hace en el proyecto |
|---|---|---|
| Patrocinador | Dirección de operaciones de los centros de datos (supuesto) | aprueba el problema y decide compras y renovaciones |
| Responsable | Compras de discos y técnicos de los centros de datos (supuesto) | usan el ranking de modelos y la lista de discos que avisan |
| Dueño de los datos | Backblaze Drive Stats, publicación trimestral | publica el registro diario de cada disco |
| Quien valida | Control de gestión (supuesto) | comprueba las cifras y el valor en dólares |

La persona responsable del proyecto es quien resuelve las cuestiones pendientes.

Este documento recoge el contexto funcional, las definiciones y los criterios acordados para el proyecto. No define
la estructura técnica de los datos, las relaciones entre tablas ni las decisiones de implementación.

## 3. Los discos

### El disco

Un **disco** es una unidad física identificada por su número de serie. Es la unidad del análisis.

- Incluye: los discos de datos de los vaults y los discos temporales que se ponen unos días mientras se rehace uno que
  falló (doc. 12a).
- Excluye: los **discos de arranque** de los servidores (ver abajo).
- No implica un hueco fijo: un hueco de un servidor recibe muchos discos a lo largo del tiempo, temporales incluidos.
- Si la petición no lo concreta: se cuenta en discos de datos, no en huecos ni en servidores.

### Los discos de arranque

Un **disco de arranque** es el disco pequeño con el que arranca cada servidor. No guarda datos de clientes.

- Son los discos de 0,2 a 2 TB: SSD y discos de portátil, todos sin ranura en el servidor. El 01/01/2025 eran 4.056
  (medido en los datos el 16/11/2026).
- Backblaze los quita de todas sus tasas de fallo: unos 4.000 en cada informe (4.013 en el 4.º trimestre de 2025 y 3.881
  en el 2.º de 2026; docs. 8a y 8b).
- Quedan fuera de las tasas de fallo, del coste por terabyte y del modelo. Se pueden contar aparte si una petición lo
  pide.
- No implica que no fallen: sus fallos existen en los datos, pero no son los discos que guardan los datos.

### El modelo y el fabricante

Un **modelo** es el número de modelo del disco. Es la unidad de compra: Backblaze compra en bloque, por modelo (doc. 9).

- El **fabricante** sale del nombre del modelo: Toshiba, WDC y HGST lo llevan delante; en Seagate el modelo empieza por
  «ST». Dos modelos no siguen el patrón: el Hitachi HDS5C4040ALE630 cuenta como HGST, la marca que sucedió a Hitachi;
  el WUH721816ALE6L4 como WDC, porque los demás discos WUH llevan «WDC» delante. Suman 51.526 días de disco y 7 fallos
  (medido el 17/11/2026).
- No implica fiabilidad pareja: dos modelos del mismo fabricante y capacidad pueden fallar muy distinto, un HGST de
  12 TB al 7,63 % y otro al 1,08 % en el mismo trimestre (doc. 8b).
- Si la petición dice «marca» o «fabricante» sin más: se da por fabricante y se avisa de que mezcla modelos de edades
  distintas.

### La capacidad

La **capacidad** es lo que cabe en el disco, en terabytes. Incluye la parte que se usa para paridad y la que está libre.

- No implica datos guardados: lo que guardan los clientes no se publica.
- **La capacidad de un disco es la de su modelo**, la que trae casi siempre. En los datos de trabajo, 2.096 filas del
  recuento diario traen -1 y siete días de disco traen 0,1 TB, que son lecturas malas de un modelo de 4 TB y otro de
  6 TB; afectan a 20 fallos. Los 59 modelos con alguna capacidad -1 tienen una capacidad conocida: la misma siempre en
  57 de ellos; en los otros dos, la que no es 0,1 TB. Medido el 17/11/2026.

### La edad

La **edad** de un disco son sus horas encendido, pasadas a años. Si un disco no las trae, cuenta desde el primer día
que aparece.

- Cambiado el 17/11/2026. La regla anterior era la de la consulta de Backblaze (doc. 9): horas encendido para los
  discos que ya estaban el 01/01/2020 y primera aparición para los demás. Medido en los datos de trabajo, de los
  279.754 discos que entran después, 2.699 llegan con más de un año de horas y 1.314 con más de tres: son discos
  usados. La primera aparición los contaría como nuevos. Además, los datos podados solo dan la primera aparición con
  un mes de margen. Las horas faltan en el 0,1 % de los discos. Avanzan como el calendario: en un año suman las horas
  del año, con un margen del 3 %, en el 98,9 % al 99,96 % de los discos (medido en tres pares de fotos).

- La edad va con cada día de disco: un disco que cumple 5 años a mitad de un trimestre cuenta en el tramo de 4 a 5 años
  hasta ese día y en el de 5 a 6 después. La previsión es la excepción: usa la edad del primer día del trimestre (§7).
- No implica la fecha de compra ni la de fabricación, que no están en los datos.
- La **vida útil contable** son 6 años desde el 01/04/2025; antes, de 3 a 5 (doc. 14). No es lo mismo que lo que dura un
  disco. El coste por terabyte usa 6 años en todo el periodo, también antes de 2025 (cuestión 001).

### Los estados de un disco

Un disco pasa por estos estados:

- **En servicio:** desde el primer día que aparece en los datos hasta el último.
- **Avisa:** algún día tiene por encima de cero alguno de los cinco contadores de avería que vigila Backblaze: sectores
  sustituidos, errores sin corregir, órdenes abortadas por tiempo, sectores pendientes y sectores ilegibles («What SMART
  Stats Indicate Hard Drive Failures», sin guardar en la base; los cinco, también en el doc. 10). Empieza el primer día que alguno pasa de cero.
  Esos contadores se acumulan y casi nunca vuelven a cero, así que avisar no tiene final dentro de la vida del disco
  (supuesto). Dos de los cinco, errores sin corregir y órdenes abortadas, solo los traen los Seagate: en los demás
  fabricantes avisar depende de tres contadores. El porcentaje de discos que avisan no se compara entre fabricantes.
  De un disco que no falla solo hay una foto al mes, así que el primer día de aviso se sabe con un mes de margen.
- **Falla:** el día que Backblaze lo marca como fallado. Ver «El fallo».
- **Desaparece sin fallo:** deja de aparecer en los datos sin haber fallado. Ver «Los discos que desaparecen».

Avisar no implica que Backblaze lo cambie: de los 21.604 discos que avisaban el 01/01/2025, el 96 % seguía funcionando
al acabar el trimestre (estudio previo).

### El fallo

Un **fallo** es el día en que Backblaze da un disco por fallado: el disco «has failed and been removed from service»
(doc. 10).

- Incluye: los discos que dejan de funcionar y los que Backblaze retira porque han mostrado que van a fallar pronto
  («Hard Drive SMART Stats», sin guardar en la base).
- Excluye: los discos que se migran a otro vault, que «are not marked as failed» (doc. 13) y los que se retiran sanos
  por gestión de riesgo, que salen de servicio «without ever having failed» (doc. 9). Ni unos ni otros llevan la marca
  de fallo: en los datos son discos que desaparecen. No hay que quitarlos a mano.
- No implica una avería del disco: la marca la pone Backblaze a mano. Una parte son retiradas que decide la empresa.
  Qué parte no se puede saber con los datos.
- No implica la fecha de la avería: si el día marcado es el de la avería o el de la retirada no consta. En 2020, 2023
  y 2024 el fin de semana tiene el 22 al 23 % de los fallos frente al 28 al 29 % esperado, lo que apunta a que a veces
  es el de la retirada. Con la lista a 30 días y la previsión por trimestre, un desfase de uno o dos días no cambia
  ninguna respuesta (cuestión 006, cerrada el 17/11/2026).
- Un mismo disco puede fallar más de una vez: 43 discos fallan dos veces entre 2020 y junio de 2026, con 7 a 30 meses
  entre uno y otro (medido el 16/11/2026); 12 de ellos, con los dos fallos en los datos de trabajo.
- Un disco puede seguir en servicio después de un fallo: 161 discos vuelven a salir en los datos tras su fallo, casi
  todos sin fallar otra vez (medido el 17/11/2026). Sus días siguen contando como días de disco. En la supervivencia, la
  vida de un disco acaba en su primer fallo. Cada fallo cuenta como uno, que es como lo cuenta la consulta de Backblaze
  (doc. 9).

### Los discos que desaparecen

Un disco **desaparece sin fallo** cuando deja de salir en los datos sin haber fallado. Pasa con entre el 1,5 % y el
2,6 % de los discos cada trimestre (estudio previo).

- Puede ser un disco migrado a otro vault, uno retirado sano o uno temporal (docs. 13, 9 y 12a). Los datos no dicen cuál
  es cada uno.
- No implica un fallo. No se cuenta como tal.
- **Un disco que vuelve no ha desaparecido.** 7.798 discos de datos, el 1,9 %, faltan en alguna foto mensual y vuelven
  después, casi siempre al mes siguiente (medido el 17/11/2026; la primera medida dio 8.871 y no se reproduce). Desaparecer es dejar de salir hasta el final de los
  datos. Los días que el disco falta no son días de disco.
- Sus días en servicio cuentan en los días de disco; en la supervivencia, el disco cuenta como **censurado**: se sabe
  que llegó vivo hasta ese día, no cuándo habría fallado.
- Los que desaparecen avisaban más que el conjunto de discos (el 10,4 % en su última foto, frente al 5,8 %) y son mayores (4,0 años
  de media frente a 2,8; medido en la construcción el 17/11/2026). Por eso, al lado de la supervivencia y de la tasa por
  edad, va la misma cifra contando como fallo a los que avisaban al desaparecer: en los años 2 y 3 de edad la tasa pasa
  del 1,22 y 1,58 % al 2,45 y 3,24 %. Si las dos cifras dan respuestas distintas, se dice.

## 4. La instalación

De lo general a lo particular:

- **Región:** cuatro (doc. 12b). Los datos no dicen qué centro va en cada región. Si una petición dice «región», se da por
  centro de datos y se avisa.
- **Centro de datos:** seis, con un código cada uno: phx1, sac0, sac2, iad1, ams5 e yyz1. Su ciudad sale de los códigos
  de aeropuerto: Phoenix, Sacramento (dos centros), Virginia, Ámsterdam y Toronto. Ninguna fuente da la tabla de códigos
  (deducido, `como_trabaja_backblaze.md`).
- **Vault:** 20 servidores iguales, con 26, 45 o 60 discos cada uno; uno de 60 discos por servidor tiene 1.200 discos
  (doc. 13).
- **Servidor:** uno de los 20 de un vault.
- **Ranura:** el sitio del disco dentro del servidor.
- **Tomo:** los 20 discos de la misma ranura en los 20 servidores de un vault. Cada fichero vive en un tomo, partido en
  20 trozos de datos y de paridad (doc. 13). Se identifica por su centro, su vault y su ranura (deducido; casi todos los
  tomos tienen 20 discos, 14.701 de 15.061 el 01/01/2025).

- **El sitio solo consta desde el 01/07/2023.** Antes vienen vacíos el centro y la ranura; el vault y el servidor
  empiezan en el 2.º trimestre de 2023, todavía sin centro. Lo que va por sitio, centros y tomos, se mide del
  01/07/2023 al 30/06/2025: dos años y 8.634 fallos de discos de datos. No se rellena hacia atrás: de los 8.362 fallos
  anteriores, solo 53 son de discos que seguían en julio de 2023. Medido el 17/11/2026.

La **paridad** de un tomo es cuántos discos suyos pueden caer a la vez sin perder datos: 3, 4 o 5, más cuanto más grande
es el disco (doc. 13). En su ejemplo de costes, Backblaze usa 3 con discos de 4 TB y 5 con los de 16 TB; la de cada
vault no está en los datos. Para el riesgo de perder datos se supone 3 hasta 8 TB, 4 de 10 a 14 TB y 5 desde 16 TB
**(supuesto)**.

## 5. Operaciones y tiempo

### El registro diario

Cada **registro** es el estado de un disco un día: su modelo, dónde está, sus contadores y si ese día falló. Un disco
tiene un registro por cada día que está en servicio.

- Un disco con dos registros el mismo día cuenta una vez (criterio, aplicado en la poda de los datos).
- Un **día de disco** es un disco en servicio un día. Es el denominador de la tasa de fallo. El día del fallo también
  cuenta como día de disco, como en la consulta de Backblaze (doc. 9).
- **Con qué se cuentan.** El total de días de disco de cada modelo, cada día, está completo en los datos de trabajo.
  De cada disco, en cambio, solo se guarda una foto al mes, salvo los 30 días antes de un fallo, que van día a día. Lo
  que depende del disco (edad, temperatura, si avisa) se toma de la foto de su mes. Los días de ese mes se reparten
  con ella (`../metodo/plan_de_la_analitica.md`, «Antes de la primera consulta»).

### Los cambios de disco

Cuando un disco falla, el técnico lo saca y pone uno temporal, que rehace los datos pidiéndolos a los otros 19 discos
del tomo. Mientras, se intenta clonar el que falló; sale bien más o menos la mitad de las veces y, si sale, el clon
sustituye al temporal (doc. 12a). Rehacer un disco tarda un día por TB, más un día de espera antes de empezar (doc. 11).
Cada cambio lleva 0,74 horas de técnico (doc. 12b).

### La renovación

Backblaze renueva por vaults enteros: migra un vault a discos más grandes cuando su tasa de fallo amenaza la
durabilidad o cuando conviene ganar capacidad. Lo desmonta a los tres meses (doc. 13). Un disco que se va en una
migración no ha fallado.

### Fechas

- La única fecha de los datos es el día de cada registro. No hay fecha de compra, de fabricación ni de salida al
  mercado de un modelo.
- **Fecha de referencia:** el 30/06/2025, último día que se mira hasta la prueba final. «El último año» son los doce
  meses del 01/07/2024 al 30/06/2025, nunca contados desde hoy. Un año con nombre, como 2024, es el natural; 2025 es
  parcial.
- **Reserva:** del 01/07/2025 al 30/06/2026 no se mira nada hasta la prueba final del modelo y de la previsión. Vale
  para todo el caso (el responsable del caso, 16/11/2026).
- **La reserva no es del todo desconocida.** Los informes de Backblaze de 2025 y del 2.º trimestre de 2026 (docs. 8a y
  8b) dan tasas de fallo de ese periodo. El caso los cita como contexto. Ninguna cifra suya de julio de 2025 en
  adelante se usa para ajustar el modelo, la previsión ni un umbral.
- Un trimestre o un año sin todos sus días es **parcial** y no se compara con uno completo.
- Una tasa de un trimestre se compara con la del mismo trimestre de otro año mientras no se sepa si hay época del año.

### Datos vacíos y valores especiales

- Un contador vacío quiere decir que ese modelo no lo apunta. No es un cero y no se rellena.
- Un dato de sitio vacío (centro, vault o ranura) quiere decir que no consta. El registro no se aparta en silencio: se
  cuenta y se dice.
- **El sitio de un fallo** (centro, vault, servidor y ranura) es el del último día anterior que lo trae, dentro de sus
  30 días de ventana. Desde 2025 el
  día del fallo suele venir sin ranura (861 de 1.067 fallos en el 1.er trimestre). El día antes la trae en 841 de esos
  861. Quedan sin ranura de 20 a 36 fallos en cada trimestre medido, del 4.º de 2024 al 2.º de 2025; se cuentan y se
  dicen. Medido el 17/11/2026.
- Los valores en bruto de algunos contadores tienen un formato propio de cada fabricante y no se comparan entre
  fabricantes (ficha de los datos).

## 6. Información económica

Todos los importes van en dólares estadounidenses. Si los precios de los discos llevan impuestos no consta.

### El precio de un disco

El **precio de un disco** es lo que pagó Backblaze por él, su precio de coste.

- Sale del coste por gigabyte de su capacidad en el año de compra (`../sector/precios_de_coste_discos.md`). Hasta 2022
  lo publica Backblaze; de 2023 a 2026 es inferido.
- La fecha de compra de un modelo es la entrada media de todos sus discos vistos de 2020 a junio de 2025: para cada
  disco, la fecha de su primera foto menos sus horas encendido. Si el modelo entró después, la de su edad media en el
  informe de Backblaze del 2.º trimestre de 2026 (doc. 8b). Cambiado el 17/11/2026: con la edad media de los discos que
  quedaban el 01/01/2025, un modelo comprado en varias tandas parecía más nuevo, porque los viejos ya se habían
  retirado. El ST4000DM000 salía comprado en enero de 2018 y su entrada media es noviembre de 2015.
- Un terabyte son 1.000 gigabytes, como cuentan los fabricantes y la tabla de precios.
- No implica el precio de un modelo concreto: dos modelos de la misma capacidad comprados el mismo año tienen el mismo
  precio.
- Una capacidad comprada hasta 2022 que no esté en la tabla toma el coste por GB de las capacidades vecinas en su fecha
  de compra, como 6, 10 y 18 TB. Un modelo comprado después toma el precio inferido de su año.
- **El disco nuevo que sustituye a uno que falla** es uno de la misma capacidad, al coste por GB del año del fallo,
  que es cuando se compra. Así se calcularon los 833.000 dólares de los fallos de 2024.

### Los costes de un cambio

| Coste | Dólares | Origen |
|---|---:|---|
| Mano de obra de un cambio | 37 | 0,74 horas por disco cambiado (doc. 12b) a 50 dólares la hora con cargas (supuesto) |
| Disco sano retirado antes de tiempo | precio × años de vida contable que le quedan / 6; cero si ya pasó de 6 años | vida útil contable de 6 años (doc. 14) |

- **Un fallo cuesta un disco y un cambio**, llegue o no por sorpresa. Las 0,74 horas son 3.112 horas entre unos 4.200
  discos cambiados en 2025, los fallos de un año: cubren el disco temporal y el clonado. Hasta el 17/11/2026 se sumaba
  un segundo cambio de 37 dólares a cada fallo no previsto, sin base.
- **El riesgo de perder datos se da aparte**, no dentro del coste de un fallo: unas 0,013 pérdidas esperadas al año, el
  95 % en tomos de 8 TB (`matriz_de_impacto.md`).
- **El disco que falla lo paga Backblaze** en la cifra principal (supuesto; el responsable del caso, 17/11/2026, cuestión 005), porque no consta
  si Backblaze reclama la garantía. Al lado va la cifra con garantía: la garantía de cada modelo sale de la ficha de su fabricante (5 años en los discos de centro de datos: Seagate con «NM» en el modelo, HGST HUH y HUS, WDC WUH y Toshiba MG;
  3 en los HGST MegaScale de 4 TB, los HMS5C; 2 en los Seagate de sobremesa, con «DM»; unos 35 fallos son de modelos sin
  garantía comprobada y cuentan como fuera de ella; 34 con el modelo de las fotos y 35 en el reconocimiento, que también
  asigna modelo a los discos que no salen en ninguna foto) y la edad del disco al fallar,
  de sus horas encendido. Con eso, el 66 % de los fallos de los datos de trabajo cae dentro de garantía (72 % en 2024).
  Si la garantía pagara esos discos, los fallos de 2024 costarían 305.124 dólares en lugar de 832.698 (medido con las
  tablas transformadas el 17/11/2026, `reglas-transformacion.md` §6; el reconocimiento daba 71 % y unos 310.000).
  La edad por horas encendido es aproximada: la garantía cuenta desde la venta. El disco pasa unas semanas guardado.

### Las métricas

- **Tasa anual de fallo = 100 × 365 × fallos / días de disco** (doc. 9). Se calcula sobre los días de disco reales de
  cada día, nunca sobre fotos de un día suelto.
- **Coste por terabyte y año, contando las averías:** el precio del disco repartido en su vida y en su capacidad, más
  lo que cuestan sus fallos. Por disco y año: precio / capacidad / 6 años, la vida contable, más tasa anual de fallo ×
  (precio de un disco nuevo + 37 dólares) / capacidad, con la tasa en tanto por uno (un 1,5 % es 0,015). Al lado, la vida real de cada modelo cuando los datos permitan
  medirla; la cifra con garantía, en la que un fallo dentro de garantía cuesta solo los 37 dólares del cambio (el responsable del caso,
  17/11/2026; cuestión 001, cuestión 002 y cuestión 005).
- **Lo que mide el modelo:** los fallos que señala, no dólares. De los fallos que llegan en un tomo donde acaba de
  fallar un disco, cuántos estaban entre los que el modelo puso primero; y de los N discos de más riesgo, cuántos
  fallan. Siempre frente a la regla de los cinco contadores de avería (el responsable del caso, 17/11/2026: «revisa, actualiza todo y lo dejamos así»).
- **Fallo sin aviso:** el que llega sin ningún contador de avería por encima de cero el día anterior, dentro de los 30
  días que se guardan antes de cada fallo. Un contador vacío no cuenta como aviso. En 903 de los 16.996 fallos de
  discos de datos la ventana no trae el día anterior (medido el 17/11/2026, 7 de ellos por las filas quitadas del
  10/12/2022): esos fallos quedan fuera del indicador y se cuentan aparte. Se da también año a año, porque cambia:
  del 40,3 % en 2020 al 17,9 % en 2025; los fallos sin día anterior, del 2,1 % al 10,3 % (medido el 18/11/2026,
  una nota del caso).
- **Ingreso por terabyte de disco** = ingresos del año / capacidad total de los discos de datos, en terabytes, media del
  año. Es un orden de magnitud:
  la capacidad incluye paridad y espacio libre (el responsable del caso, 16/11/2026). Se da para 2023 y 2024; el de 2025 necesita la
  capacidad de julio a diciembre, que es reserva. Se calcula en la prueba final.

### Lo que no se puede calcular

- El coste real de cada disco de 2023 a 2026: Backblaze no lo publica.
- El coste real de la hora de técnico.
- Cuántos terabytes guardan los clientes y por tanto el margen por terabyte guardado.
- Si Backblaze reclama la garantía de los discos que fallan.

## 7. Criterios analíticos acordados

- **La tasa siempre con su base:** cada tasa va con sus fallos y sus días de disco, «2,3 %, 52 fallos en 2,3 millones de
  días de disco» y con su intervalo cuando se comparan grupos (el responsable del caso aprobó el plan de la analítica el 16/11/2026).
- **El intervalo cuenta con que los fallos no son independientes.** Los fallos de un grupo varían de un trimestre a otro
  más de lo que supone el intervalo de Poisson. Esa variación de más, φ, se mide en cada bloque con la misma mezcla con
  que se calcula su cifra (lo que cambia entre trimestres dentro de un mismo modelo y año de edad). El intervalo es el
  exacto de Poisson con los fallos divididos por φ; si φ sale menor que 1, vale 1. Medido el 18/11/2026: 3,37 en los
  modelos, 5,02 en la edad y el minicubo, 1,01 en los centros. El responsable del caso aprobó la tabla del segundo auditor el
  18/11/2026; el método es criterio técnico.
- **Mínimo para entrar en un ranking:** 50.000 días de disco en el año, el umbral anual de Backblaze (doc. 8a; fijado
  por el analista el 16/11/2026, una nota del caso). Lo que no llega se enseña aparte con su recuento. Es fijo. En las cifras por trimestre entran los modelos que pasan
  el mínimo en el año de ese trimestre. **Y 20 fallos:** un modelo con menos de 20 fallos en sus años que pasan el
  mínimo sale con su tasa, sus fallos y sus días, pero sin puesto y «sin conclusión», como un año de edad (el responsable del caso,
  18/11/2026, cuestión 012).
- **Una tasa por modelo se compara a igual edad y en el mismo trimestre:** sus fallos frente a los que tendrían los
  discos de su edad en los mismos trimestres (el responsable del caso, 18/11/2026: «Vale, déjalo así»; antes, solo a igual edad).
  Comparar fabricantes o capacidades mezcla discos de edades distintas. Se avisa siempre.
- **Un centro de datos falla más «por sí mismo»** solo si su tasa sigue más alta con la misma mezcla de modelos,
  edades y trimestres que los demás (el responsable del caso, 18/11/2026; antes, modelos y edades).
- **El coste por TB y año se ordena dentro de cada capacidad y año de compra,** que es donde la tasa de fallo decide:
  entre años de compra, el orden lo pone el precio de cada año (Spearman −0,963 entre el coste y la fecha de compra,
  una nota del caso). El orden de todos juntos va al lado, como contexto.
- **Fallos que coinciden en un tomo:** dos fallos del mismo tomo coinciden si el segundo llega antes de que acabe de
  rehacerse el primero, con la regla de un día por TB más uno (doc. 11), contados con la capacidad del primero. El último día de ese plazo ya
  no coincide.
- **Previsión de fallos:** una cuenta con las tasas por modelo y edad, que solo vale si gana a repetir los fallos del
  trimestre anterior (el responsable del caso, 16/11/2026, bloque 9). Gana si su error absoluto ponderado es menor: la suma de las
  diferencias entre fallos previstos y reales, sin signo, entre la suma de los fallos reales, de todos los trimestres y
  capacidades a la vez. Al lado va el sesgo, la misma cuenta con signo, que dice si prevé de más o de menos (el responsable del caso,
  17/11/2026, cuestión 011). Se hace con lo que se sabe el primer día del trimestre: los discos
  que hay ese día, con su edad y las tasas medidas hasta el día anterior.
- **El modelo da el riesgo de fallo de cada disco** y se usa para la lista de los técnicos y el aviso de tomos en
  peligro; cambiar un disco antes no ahorra dinero (`matriz_de_impacto.md`). Lo decidido en el paso 1 (17/11/2026):
  - aprende con todos los fallos, los que se rompen y los que Backblaze retira (el responsable del caso, cuestión 003). El 39,7 % de los fallos
    a 90 días llega de discos **sin aviso en su última foto mensual** y el modelo no los ve: el informe lo dice. No es
    el 25,1 % «sin aviso el día anterior» de los fallos con día anterior (B6): son dos medidas distintas;
  - la lista avisa a 30 días. El tomo está en peligro mientras se rehace el disco que falló, un día por TB más uno
    (el responsable del caso, cuestión 004);
  - se compara con la regla de los cinco contadores ordenada por cuántos contadores avisan y, a igualdad, por su suma
    sin el 188, en listas de 20, 100, 500 y 1.000 discos al mes. El tamaño de la lista lo elige Backblaze según lo que
    puedan atender sus técnicos, que no consta (cuestión 010, criterio técnico).
- **La tasa sube con la edad** cuando el intervalo al 95 % de la tasa de un año de edad no se solapa con el del año
  anterior. Un año de edad con menos de 20 fallos se enseña sin conclusión (cuestión 009, criterio técnico.

- **La partición por fecha** (el responsable del caso, 17/11/2026: «Sí, apruebo»; paso 2b). Se hace antes del exploratorio:
  - **construcción:** del 01/01/2020 al 30/06/2024; una foto cuyo horizonte acabe después del 30/06/2024 se recorta o
    se queda fuera;
  - **validación:** del 01/07/2024 al 30/06/2025, el último año de trabajo; se mira una sola vez, al medir el modelo;
  - **prueba final:** la reserva, del 01/07/2025 al 30/06/2026, fuera del caso;
  - el exploratorio frente al objetivo usa solo la construcción;
  - la parte analítica (tasas, edad, coste, centros, tomos y previsión) usa todos los datos de trabajo, porque describe
    el conjunto de discos y no ajusta el modelo.

- **El desequilibrio se trata solo al entrenar** (el responsable del caso, 16/11/2026, plan de la analítica, «Notas para el modelo»).
  En construcción, solo el 0,11 % de las fotos acaba en fallo:
  - el modelo aprende con todas las fotos de fallo y una muestra de las sanas;
  - el tamaño de la muestra sale de medir el modelo con muestras crecientes; para empezar, el 2 % de las sanas, medido
    el 18/11/2026;
  - después, la probabilidad se recalibra para que diga cuántos fallos esperar;
  - la validación y la prueba final conservan la proporción real.

- **Cómo se eligen las variables y cuánto se busca** (el responsable del caso, 18/11/2026, antes de ver ningún resultado):
  - en la regresión logística entra una variable si la marcan dos o más de los tres métodos de la preselección
    (consenso amplio); el bosque y el `HistGradientBoosting` no se preseleccionan por votación;
  - en la logística, los contadores de avería 5, 187, 197 y 198 (`smart_5_raw`, `smart_187_raw`, `smart_197_raw` y
    `smart_198_raw`) entran siempre, sin pasar la votación, para poder explicar la lista a los técnicos con lo que ya
    vigilan. El 188 no entra: su valor no es un recuento creíble;
  - la búsqueda del bosque y del `HistGradientBoosting` es de nivel equilibrado, 15 combinaciones por algoritmo y 5
    pliegues. La logística prueba solo el castigo L2, con el resolvedor `lbfgs`, en los 12 valores de `C` de la rejilla
    de el método. Medido el 18/11/2026 con la muestra de partida: con `saga`, un ajuste con castigo flojo tarda de 15 a 55
    minutos. El nivel equilibrado con los tres castigos pasaría de 12 horas; con `lbfgs`, de 4 a 7 segundos. Los
    castigos L1 y mezcla sirven sobre todo para quitar variables. Eso lo hace la preselección (el responsable del caso: «si»). Toda la
    competición, alrededor de hora y media;
  - las cuatro variables nuevas candidatas de la matriz (P-04) solo se crean si el modelo no supera a la regla en la
    competición, con la validación cruzada dentro de construcción y antes de abrir la validación. Crearlas después de ver
    la validación la dejaría contaminada (el responsable del caso, 18/11/2026: «Vale, continuamos»). El modelo superó a la regla y, aun así,
    se probaron el 19/11/2026 por decisión del responsable del caso, solo en el ganador, con sus mismos hiperparámetros y pliegues
    (`scripts/16_variables_nuevas.py`): empatan (+0,60 fallos al mes en la lista de 100, desviación 1,52) y no entran.

### Población del análisis

| Uso | Entra | Sale |
|---|---|---|
| Tasas de fallo y previsión | los discos de datos, todos los modelos, del 01/01/2020 al 30/06/2025 | los discos de arranque y la reserva |
| Rankings de modelos o centros | los que pasan el mínimo de días de disco | los que no llegan, que se enseñan aparte |
| Coste por terabyte | los discos de datos, que son todos de 4 TB o más (no hay ninguno entre 2 y 4 TB; medido el 17/11/2026) | los de arranque, que no tienen precio |
| Tasas por centro | los fallos y días de disco del 01/07/2023 al 30/06/2025 con su centro | los anteriores, sin sitio y los que no traen centro, contados y dichos |
| Fallos del mismo tomo | los fallos del 01/07/2023 al 30/06/2025 con su centro, vault y ranura | los anteriores y los que no traen ranura, contados y dichos |

## 8. Criterios específicos del análisis

Cuando una petición fije una comparación, un umbral o un indicador para un requerimiento concreto, se respeta esa
definición en esa petición.

Esas definiciones no se aplican a otros análisis.

## 9. Datos personales

No aplica: los datos son de los discos de Backblaze y no traen nada de personas. El número de serie identifica un disco,
no a quien guarda datos en él. Ningún campo es un dato personal.

Si en los datos aparece un dato personal en claro, el trabajo para y se avisa.

## 10. Criterios de interpretación

Los términos de negocio se interpretan según las definiciones de este documento y no solo por su significado
habitual.

Debe distinguirse especialmente entre:

- un fallo y una avería: el fallo incluye retiradas que decide la empresa;
- un disco que avisa y un disco que falla: casi todos los que avisan siguen funcionando;
- un disco que falla y uno que desaparece: el que desaparece no ha fallado;
- la tasa anual de fallo y el porcentaje de discos que fallan: la tasa se calcula sobre días de disco;
- la vida útil contable y lo que dura un disco;
- la capacidad de los discos y lo que guardan los clientes;
- el vault y el tomo: el vault son 20 servidores; el tomo, 20 discos de la misma ranura.

No deben inferirse estructuras de datos, relaciones, fórmulas o criterios de exclusión que no estén confirmados por el
contexto disponible.

Cuando una petición requiera una interpretación no recogida en estas reglas, se identifica como una cuestión
pendiente antes de adoptar un criterio.

## 11. Información adicional del proyecto

Estas reglas se complementan con lo que Backblaze publica sobre sus datos y su forma de trabajar, guardado en
`../sector/documentos/` y con la ficha de los datos, en `../fuentes/`.

La documentación técnica que se genere durante el proyecto se mantiene separada de estas reglas.

## 12. Vocabulario

| Palabra | Qué significa en este caso | Con qué se confunde |
|---|---|---|
| fallo | el día en que Backblaze da un disco por fallado y lo saca del servicio | avería; retirada de un disco sano |
| avisar | tener por encima de cero alguno de los cinco contadores de avería | fallar; estar en la lista de cambio |
| día de disco | un disco en servicio un día | disco |
| tasa anual de fallo | 100 × 365 × fallos / días de disco | porcentaje de discos que fallan en el año |
| disco de arranque | el disco pequeño con el que arranca un servidor | disco de datos |
| tomo | los 20 discos de la misma ranura en un vault | vault; volumen de un sistema operativo |
| vault | 20 servidores iguales que guardan los datos repartidos | centro de datos |
| desaparecer | dejar de salir en los datos sin haber fallado | fallar |
| censurado | disco del que se sabe que llegó vivo hasta un día y no cuándo habría fallado | disco que no falla nunca |
| reserva | del 01/07/2025 al 30/06/2026, apartado hasta la prueba final | periodo sin datos |

## 13. Historial de cambios

| Fecha | Qué cambió | Quién lo decidió | Qué se revisó por el cambio |
|---|---|---|---|
| 16/11/2026 | Primera versión, reuniendo lo decidido y lo leído en los documentos del caso y del sector | el analista la escribe; pendiente del responsable del caso | briefing (los discos de arranque salen de las tasas), ficha del caso, plan de la analítica |
| 17/11/2026 | Cotejo de cada cita con su documento: la paridad por tamaño pasa a ejemplo de Backblaze; la tarifa plana de las copias de seguridad, quitada por no tener fuente; la edad, con la regla exacta de la consulta de Backblaze; el día del fallo cuenta como día de disco; el coste de los ingresos, con lo que dice el informe anual | el analista, en el repaso pedido por el responsable del caso («repasa, verifica»); pendiente del responsable del caso | `como_trabaja_backblaze.md`, `matriz_de_impacto.md`, `mapa_del_sector.md` |
| 17/11/2026 | Cotejo con los datos de trabajo, ya podados: la capacidad sale del modelo; el sitio solo consta desde el 01/07/2023; la ranura de un fallo se toma del día anterior | el analista, al comprobar para el responsable del caso que el plan se puede hacer con los datos; pendiente del responsable del caso | ficha de los datos, plan de la analítica, precios, datos necesarios, estudio previo |
| 17/11/2026 | El coste de un fallo, sin el segundo cambio de 37 dólares; el riesgo de perder datos, aparte; lo que mide el modelo, en fallos señalados | el responsable del caso, 17/11/2026: «revisa, actualiza todo y lo dejamos así» | matriz de impacto, briefing, ficha del caso, plan, cuestiones pendientes, datos necesarios, mapa |
| 17/11/2026 | Paso 1: cuestión 003, cuestión 004, cuestión 006, cuestión 009 y cuestión 010 en §3 y §7; la fecha de compra, con la entrada media de los discos; los discos que vuelven, 7.798; los fallos sin garantía comprobada, unos 35; la sensibilidad de los que desaparecen | el responsable del caso (cuestión 003 y cuestión 004); el analista, criterios técnicos (cuestión 006, cuestión 009 y cuestión 010), tras el comité | cuestiones pendientes, tabla de precios, ficha |
| 17/11/2026 | La partición por fecha, en §7 | el responsable del caso: «Sí, apruebo» (paso 2b) | `../metodo/revision_metodos_paso2b.md` |
| 17/11/2026 | Aprobadas, con todo lo de abajo | el responsable del caso: «Sí, se aprueban» | ninguno: no cambia el texto |
| 17/11/2026 | Prueba de comprensión con un revisor sin historial (paso E). Se escriben el último año, la tasa en tanto por uno en el coste, el disco nuevo al precio del año del fallo, la fecha del año de compra, el terabyte de 1.000 GB, la edad por día, los 6 años en todo el periodo, el mínimo en las cifras por trimestre, el sitio del fallo, la coincidencia en un tomo, la paridad supuesta, las familias de la garantía, el fallo sin aviso, el ingreso por terabyte, los dos modelos sin fabricante, los retirados sanos y con qué se cuentan los días de disco; la población separa centro y tomo; los ingresos de 2025, con su total | el analista, con la prueba de `25_`; pendiente del responsable del caso | ficha del caso, briefing, cuestiones pendientes |
| 17/11/2026 | Revisión del diseño contra los datos: la edad pasa a ser las horas encendido; un disco que vuelve no ha desaparecido; un disco puede seguir tras un fallo; avisar depende de tres contadores fuera de Seagate; la reserva y los informes de Backblaze; el ingreso por terabyte de 2025; con qué se hace la previsión | el analista, en la tercera revisión pedida por el responsable del caso («coherencia entre los datos, las reglas y lo que resolverá el caso»); pendiente del responsable del caso | plan de la analítica, ficha del caso, datos necesarios, cuestiones pendientes |
| 17/11/2026 | §7: la previsión gana a repetir el trimestre anterior si su error absoluto ponderado es menor, con el sesgo al lado (antes no decía con qué medida). §6: el día anterior a un fallo no siempre está en su ventana; los 903 fallos sin él salen del indicador de fallos sin aviso y se cuentan aparte (antes decía que siempre estaba) | el responsable del caso: cuestión 011 («Sí, ciérrala así») y la tabla de la cascada («Sí, apruébala») | `../modelo/modelo-datos.md`, `../metodo/plan_de_la_analitica.md`, `informes/modelado-datos.json` y `.md`; la ficha, sin cambios |
| 18/11/2026 | §7: un modelo con menos de 20 fallos sale del ranking sin puesto y «sin conclusión» (cuestión 012); el 39,7 % se llama «sin aviso en su última foto mensual», distinto del 25,1 % «sin aviso el día anterior» | el responsable del caso: «Vale, me parece bien» y «Apruebo la tabla» (auditor del cierre analítico, una nota del caso) | `../metodo/plan_de_la_analitica.md`, `../metodo/04_planteamientos.md`, `../modelo/modelo-datos.md`, `01_ficha_del_caso.md`, `cuestiones-pendientes.md`; los scripts 09 y 10, por la petición 17 |
| 18/11/2026 | §7: los modelos se comparan a igual edad y en el mismo trimestre (antes, a igual edad); los centros con la mezcla de modelos, edades y trimestres (antes, modelos y edades); el intervalo se ensancha con φ, la variación entre trimestres de más; el coste se ordena dentro de cada capacidad y año de compra. §6: la garantía de 2024 con las tablas transformadas (72 % y 305.124, antes 71 % y unos 310.000); el fallo sin aviso, también año a año | el responsable del caso: «Apruebo la tabla» y «Vale, déjalo así» (segundo auditor, una nota del caso a una nota del caso) | `../metodo/plan_de_la_analitica.md`, `../modelo/modelo-datos.md`, `matriz_de_impacto.md`, `01_ficha_del_caso.md`, el borrador de hallazgos; los scripts 09, 10 y 11, por la petición 19 |
| 18/11/2026 | §7: cómo se trata el desequilibrio en el modelo, decidido el 16/11 (antes solo estaba en el plan y en los planteamientos); la muestra de partida, el 2 % de las sanas | el responsable del caso: «Sí, apruebo» (guion del modelo, una nota del caso y una nota del caso) | `../metodo/plan_de_la_analitica.md` y `../metodo/04_planteamientos.md`, sin cambios: ya lo decían |
| 18/11/2026 | §7: cómo se eligen las variables (consenso amplio en la logística, con los contadores 5, 187, 197 y 198 siempre dentro) y la búsqueda de nivel equilibrado (antes no constaba) | el responsable del caso: «Equilibrado», «Vale, si es lo más idóneo, me parece bien», «si es que sí, es que sí» y la tabla de la cascada («Venga, sí, adelante») | `../metodo/04_planteamientos.md`, sin cambios: remite a el método; la matriz y el script 13 no seleccionan variables |
| 18/11/2026 | §7: las variables nuevas de P-04 se deciden con la competición dentro de construcción, antes de abrir la validación (antes la matriz no decía dónde se ve si el modelo supera a la regla) | el responsable del caso: «Vale, continuamos» | `../modelo/matriz_transformaciones.md`, P-04: no cambia lo decidido, se precisa aquí |
| 18/11/2026 | §7: la logística, solo con castigo L2 y `lbfgs` en los 12 valores de `C` (antes, nivel equilibrado con los tres castigos y «unos 30 minutos», una cifra mal medida con los valores por defecto, una nota del caso) | el responsable del caso: «si» | ninguno más: la búsqueda solo vive aquí y en la petición 21, sin escribir todavía |
| 19/11/2026 | §7: las cuatro variables nuevas de P-04 se probaron aunque el modelo superaba a la regla, solo en el ganador; empatan y no entran (antes solo decía cuándo se crearían) | el responsable del caso: «vale, prueba las cuatro variables nuevas», «Sí, solo el ganador», «Sí, primero probar» y la tabla de la cascada («si») | `../modelo/matriz_transformaciones.md` (P-04 y `vault_id`); los informes de la petición 21 y la ficha R-021, sin cambios: dicen lo de su día |
