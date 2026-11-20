# Informe de corrección de datos

**Estado: AVISO.** Los cuatro datasets corregidos, uno por tabla en data/processed/: 16 correcciones con cambio y 23 problemas que se dejan como están, con su motivo, para que los lea el método siguiente. Ningún vacío rellenado y ninguna fila perdida sin explicar.

## Fuente

- **Datasets de entrada:** los cuatro de `data/raw/podado/`: 66 fotos mensuales, 22 ventanas de fallo por trimestre, el recuento diario y la lista de fallos (91 ficheros en `data/raw/` con el esquema).
- **Diagnóstico usado:** `informes/calidad-datos.json`, en estado AVISO, ejecutado el 2026-11-17T16:01:35, con la misma huella de entrada que estos datos.
- **Decisiones leídas:** `config/modelo/decisiones-correccion.json`.
- **Datasets de salida:** `data/processed/fotos_mensuales_corregido.parquet`; `data/processed/ventanas_fallo_corregido.parquet`; `data/processed/recuento_diario_corregido.parquet`; `data/processed/fallos_corregido.parquet`.
- **Ejecución:** 2026-11-17T17:01:20, con Python 3.13.15, pandas 3.0.6, pyarrow 24.0.0 y numpy 2.5.3.
- **Huellas:** las de los 91 ficheros de entrada y las de las cuatro salidas están en el JSON (`entradas` y `salidas`). data/raw/ tiene la misma huella al empezar y al terminar.
- **Teoría aplicada:** Manual 8.1 antes de corregir (cada corrección responde a un problema diagnosticado, con su regla y su recuento); 8.3 para los tipos (la fecha del texto con el patrón explícito %Y-%m-%d, contando los vacíos que crea); 8.7 para el nombre del modelo (mapeo cerrado con replace, que deja como está lo que no encuentra); 8.6 para el recuento (se suman las filas con la misma clave porque la granularidad documentada da una fila por clave); 8.4 y 33.4 para las filas quitadas de las ventanas (se cuentan; la regla se puede aplicar siempre); 8.10 para el cierre (filas, vacíos y sumas antes y después). Los apartados 4.5 y 4.6 no se aplican: las filas quitadas repiten el día siguiente y no tienen datos propios, así que no cambian ninguna comparación entre grupos.

## Correcciones aplicadas

- **K-01 · fotos mensuales, `datacenter`.** El centro se lee como texto en todas las fotos. Viene del problema C-03; criterio: técnicamente inequívoca: el rol del diccionario es categórica y el tipo nulo es la forma de un centro vacío entero. Pasa de 42 a 0 ficheros sin tipo. Ficha R-001 del registro.
- **K-02 · ventanas de fallo, `datacenter`.** El centro se lee como texto en todas las ventanas. Viene del problema C-03; criterio: técnicamente inequívoca, como en las fotos. Pasa de 14 a 0 ficheros sin tipo. Ficha R-001 del registro.
- **K-03 · fotos mensuales, `pod_slot_num`.** La ranura pasa de decimal a entero. Sus vacíos se quedan vacíos. Viene del problema C-04; criterio: técnicamente inequívoca: todos sus valores con dato son enteros (la conversión segura falla si alguno no lo es). Pasa de 6.885.677 a 0 filas leídas como decimal. Ficha R-002 del registro.
- **K-04 · ventanas de fallo, `pod_slot_num`.** La ranura pasa de decimal a entero. Sus vacíos se quedan vacíos. Viene del problema C-04; criterio: técnicamente inequívoca, como en las fotos. Pasa de 261.083 a 0 filas leídas como decimal. Ficha R-002 del registro.
- **K-05 · fotos mensuales, `date`.** El texto de la fecha pasa a fecha, leído con el patrón %Y-%m-%d. No viene de ningún problema de calidad; criterio: responsable: la petición 07 pide las fechas como fecha, que es el rol de date en el diccionario. Pasa de 14.851.669 a 0 filas con la fecha como texto. Ficha R-003 del registro.
- **K-06 · ventanas de fallo, `date`.** El texto de la fecha pasa a fecha, leído con el patrón %Y-%m-%d. No viene de ningún problema de calidad; criterio: responsable: la petición 07 pide las fechas como fecha. Pasa de 536.597 a 0 filas con la fecha como texto. Ficha R-003 del registro.
- **K-07 · fotos mensuales, `model`.** Los modelos escritos con dos espacios tras «WDC» pasan a su nombre con uno, con el mapeo cerrado de D1 (3.896 filas cambiadas). Viene del problema C-13; criterio: responsable: D1, cerrada por el responsable del caso el 17/11/2026 en el plan de calidad. Pasa de 4 a 0 nombres con dos espacios. Ficha R-004 del registro.
- **K-08 · ventanas de fallo, `model`.** Los modelos escritos con dos espacios tras «WDC» pasan a su nombre con uno, con el mapeo cerrado de D1 (25 filas cambiadas). Viene del problema C-13; criterio: responsable: D1, cerrada por el responsable del caso el 17/11/2026 en el plan de calidad. Pasa de 2 a 0 nombres con dos espacios. Ficha R-004 del registro.
- **K-09 · recuento diario, `model`.** Los modelos escritos con dos espacios tras «WDC» pasan a su nombre con uno, con el mapeo cerrado de D1 (1.536 filas cambiadas). Viene del problema C-13; criterio: responsable: D1, cerrada por el responsable del caso el 17/11/2026 en el plan de calidad. Pasa de 4 a 0 nombres con dos espacios. Ficha R-004 del registro.
- **K-10 · fotos mensuales, `capacity_bytes`.** Las filas con capacidad -1 o 0,1 TB toman la única capacidad válida de su modelo. Viene del problema C-05; criterio: regla documentada: reglas de negocio §3. Pasa de 2.729 a 0 filas con capacidad -1 o 0,1 TB. Ficha R-005 del registro.
- **K-11 · ventanas de fallo, `capacity_bytes`.** Las filas con capacidad -1 o 0,1 TB toman la única capacidad válida de su modelo. Viene del problema C-06; criterio: regla documentada: reglas de negocio §3. Pasa de 165 a 0 filas con capacidad -1 o 0,1 TB. Ficha R-005 del registro.
- **K-12 · recuento diario, `capacity_bytes`.** Las filas con capacidad -1 o 0,1 TB toman la única capacidad válida de su modelo. Viene del problema C-07; criterio: regla documentada: reglas de negocio §3. Pasa de 2.102 a 0 filas con capacidad -1 o 0,1 TB. Ficha R-005 del registro.
- **K-13 · recuento diario, `(fila)`.** Las filas que quedan con la misma clave (fecha, modelo, capacidad y centro) se suman en una: discos y fallos. Viene del problema C-07; criterio: regla documentada: reglas de negocio §3, con el orden de la petición 07 (nombre, capacidad y suma). Pasa de 201.502 a 197.871 filas. Ficha R-006 del registro.
- **K-14 · ventanas de fallo, `(fila)`.** Salen las filas cuya fecha no es la de su texto: traen las horas encendido del día siguiente y no tienen datos propios. Viene del problema C-17; criterio: responsable: la petición 07 resuelve P-01; quitarlas no cambia ninguna respuesta (las instrucciones del caso, «Datos que no sirven o están mal»; criterios.md §2). Pasa de 536.825 a 536.597 filas. Ficha R-007 del registro.
- **K-15 · fotos mensuales, `(fichero)`.** Las 66 fotos mensuales se juntan en un solo Parquet con las 130 columnas que trae alguna; donde una pieza no trae una columna, queda vacía. No viene de ningún problema de calidad; criterio: responsable: la petición 07 y metodo/como_estan_organizados_los_datos.md (las filas son las mismas: solo cambia el fichero). Pasa de 66 a 1 ficheros. Ficha R-008 del registro.
- **K-16 · ventanas de fallo, `(fichero)`.** Las 22 ventanas se juntan en un solo Parquet con las 131 columnas que trae alguna; donde una pieza no trae una columna, queda vacía. No viene de ningún problema de calidad; criterio: responsable: la petición 07 y metodo/como_estan_organizados_los_datos.md. Pasa de 22 a 1 ficheros. Ficha R-008 del registro.

## Decisiones del responsable

- **P-01:** son una copia del día que dice el texto: su fecha no tiene datos propios y sus filas sobran. Quitarlas no cambia ninguna respuesta (las instrucciones del caso, «Datos que no sirven o están mal»; criterios.md §2); el recuento de ese día se queda como está (el responsable del caso, con la petición 07, 2026-11-17; peticiones/07_correccion.md).
- **D1:** los modelos que solo se distinguen por los dos espacios tras «WDC» son el mismo modelo, porque son los mismos discos, con el mismo número de serie, escritos de dos formas; la corrección los junta (el responsable del caso, 17/11/2026, plan de calidad, «Lo aprobado») (el responsable del caso, 2026-11-17; informes/plan_calidad_datos.md, «Lo aprobado»).
- **tipos de fecha:** las fechas como fecha: el texto date pasa a fecha (el responsable del caso, con la petición 07, 2026-11-17; peticiones/07_correccion.md).
- **juntar las piezas:** las 66 fotos en un Parquet y las 22 ventanas en otro, con todas las columnas (el responsable del caso, con la petición 07, 2026-11-17; peticiones/07_correccion.md; config/metodo/como_estan_organizados_los_datos.md).

## Elementos mantenidos sin cambios

Estos problemas del diagnóstico se dejan como están, cada uno con su motivo. Ninguno rellena un vacío: el caso entrena un modelo.

- **C-01** (49 columnas vacías en más del 99 % de las filas que las traen): ninguna de las 49 columnas casi vacías es de los cinco contadores de avería; si entran al modelo lo decide la preselección.
- **C-02** (2 nombres con errata en el esquema): las erratas están en el esquema, no en los datos.
- **C-08** (84.647 filas con centro «sin dato», 4.551 desde el 01/07/2023): el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7); en el recuento, «sin dato» se queda como etiqueta del centro que no consta, la de correccion-datos/parametros.md.
- **C-09** (235.772 filas sin dato desde el 01/07/2023; de discos de datos, 234.446): el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7).
- **C-10** (103.221 filas sin dato desde el 01/07/2023; de discos de datos, 1.613): el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7).
- **C-11** (vale 0 en 4.781.548 de 6.885.677 filas que traen la columna): D4: ninguna pregunta usa cluster_id.
- **C-12** (82 variables con los vacíos concentrados en algún segmento): un contador vacío quiere decir que el modelo no lo apunta y no se rellena (reglas, apartado 5).
- **C-14** (192.593 filas de discos de datos por encima de mil millones): D2, cerrada en el plan de calidad («Lo aprobado»).
- **C-15** (el 187 en 65.535 en 221 filas; el 5 llega a 65.529 en las fotos): D3, cerrada en el plan de calidad («Lo aprobado»).
- **C-16** (9 filas por encima de 70 grados, con máximo de 117): ninguna pregunta usa la temperatura de las ventanas.
- **C-18** (RC-01 incumplida: 3.468 veces bajan las horas entre dos fotos seguidas; 3.468 más de un día): la edad la calcula la transformación con la regla de las reglas, apartado 3 (horas encendido y, sin ellas, primera aparición, también en las ventanas); las horas que bajan afectan a 3.443 discos y 52 fallos de 17.960 (cifras de la petición 07).
- **C-19** (RC-02 incumplida: el modelo cambia 7.372 veces (1 sin contar las variantes de espacios) y la capacidad 3.854 (0 entre capacidades válidas)): tras corregir el nombre del modelo (C-13) y la capacidad (C-05) queda 1 cambio(s) de modelo real(es) entre dos fotos seguidas de un disco y 0 de capacidad, medidos en las fotos corregidas.
- **C-20** (RC-03 incumplida: smart_5_raw baja 575 veces en 413 discos; smart_187_raw baja 12 veces en 12 discos; smart_188_raw baja 1.650 veces en 1.650 discos; smart_197_raw baja 24.477 veces en 11.547 discos; smart_198_raw baja 10.055 veces en 5.517 discos): el aviso mira si un contador pasa de cero el día anterior (reglas, apartado 6), no si sube.
- **C-21** (2.738 filas de discos de datos sin horas encendido): la edad la calcula la transformación con la regla de las reglas, apartado 3 (horas encendido y, sin ellas, primera aparición, también en las ventanas).
- **C-22** (67 fallos antes de la primera foto de su disco): la edad la calcula la transformación con la regla de las reglas, apartado 3 (horas encendido y, sin ellas, primera aparición, también en las ventanas).
- **C-23** (210 fallos de 210 discos que no salen en ninguna foto): la edad la calcula la transformación con la regla de las reglas, apartado 3 (horas encendido y, sin ellas, primera aparición, también en las ventanas).
- **C-24** (161 discos salen en alguna foto después de su fallo): reglas, apartado 3: un disco puede seguir en servicio tras un fallo y sus días siguen contando.
- **C-25** (7.798 discos de datos faltan en alguna foto y vuelven): reglas, apartado 3: un disco que falta en una foto y vuelve no ha desaparecido.
- **C-26** (163 pares de modelo y contador con vacíos solo en parte de sus filas; suman 2.789.298 filas vacías): de 16.101 fallos de discos de datos con día anterior, 4.049 llegan sin aviso y solo 69 tienen un contador vacío que su modelo sí apunta; aunque contaran como aviso, la parte sin aviso pasa del 25,1 % al 24,7 % (cifras de la petición 07).
- **C-27** (13 fallos de discos de datos desde el 01/07/2023 sin ranura ningún día de su ventana): el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7).
- **C-28** (141 fallos de discos de datos desde el 01/07/2023 sin tomo completo ningún día de su ventana): el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7).
- **C-29** (896 fallos de discos de datos sin el día anterior en su ventana): el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7); al quitar las filas de C-17 pasan de 896 a 903 fallos de discos de datos sin el día anterior en su ventana.
- **C-30** (7 días hundidos del reconocimiento con discos de menos frente a sus vecinos): ninguna pregunta usa la tasa de un día.
- Los contadores (smart_N_raw y smart_N_normalized) siguen como decimales: la petición 07 nombra como correcciones de tipo solo el centro, la ranura y las fechas. Un decimal es un tipo válido para una magnitud. La calidad los marcó como «toca entero» sin abrir ningún problema; si se quieren enteros, es una decisión para el paso siguiente.

## Decisiones pendientes

- No queda ninguna. La única cuestión que dejó la calidad, P-01, la resuelve la petición 07 y está en «Decisiones del responsable».

## Validación

| Tabla | Filas antes | Filas después | Capacidad -1 o 0,1 TB antes | Después | Modelos con dos espacios antes | Después |
|---|---:|---:|---:|---:|---:|---:|
| fotos mensuales | 14.851.669 | 14.851.669 | 2.729 | 0 | 4 | 0 |
| ventanas de fallo | 536.825 | 536.597 | 165 | 0 | 2 | 0 |
| recuento diario | 201.502 | 197.871 | 2.102 | 0 | 4 | 0 |
| lista de fallos | 17.960 | 17.960 | sin dato | sin dato | sin dato | sin dato |

Las ventanas pierden 228 filas, todas del 2022-12-10, ninguna con un fallo. Por eso los fallos de discos de datos sin el día anterior en su ventana pasan de 896 a 903. El recuento pasa de 201.502 a 197.871 filas al sumar las que quedan con la misma clave. En las fotos, tras las dos correcciones, un disco cambia de modelo 1 vez entre dos fotos seguidas, frente a 7.372 antes.

**Sumas de control.** Cada magnitud que no debía cambiar da lo mismo antes y después:

- recuento diario, `discos` (pandas, en memoria): 453.609.422 y 453.609.422; coincide.
- recuento diario, `discos` (pyarrow, sobre los ficheros en disco): 453.609.422 y 453.609.422; coincide.
- recuento diario, `fallos` (pandas, en memoria): 17.960 y 17.960; coincide.
- recuento diario, `fallos` (pyarrow, sobre los ficheros en disco): 17.960 y 17.960; coincide.
- fotos mensuales, `failure` (pyarrow, pieza a pieza, en las filas que se quedan): 563 y 563; coincide.
- fotos mensuales, `smart_9_raw` (pyarrow, pieza a pieza, en las filas que se quedan): 382.275.882.788 y 382.275.882.788; coincide.
- ventanas de fallo, `failure` (pyarrow, pieza a pieza, en las filas que se quedan): 17.960 y 17.960; coincide.
- ventanas de fallo, `smart_9_raw` (pyarrow, pieza a pieza, en las filas que se quedan): 17.754.344.516 y 17.754.344.516; coincide.

**Las cuatro comprobaciones del dataset procesado:**

- completitud: pasa.
- consistencia: pasa.
- utilidad: pasa.
- datos_personales: pasa.

**Comprobaciones de la ejecución:**

- fotos: las mismas filas a la entrada y a la salida: pasa.
- ventanas: salen solo las filas cuya fecha no es la de su texto, ninguna con un fallo: pasa.
- fotos: ninguna fila con la fecha distinta de su texto, que no se quita: pasa.
- recuento: discos y fallos suman lo mismo por las dos vías: pasa.
- recuento: discos y fallos de cada día suman lo mismo: pasa.
- recuento: la clave queda única: pasa.
- lista de fallos: las mismas filas: pasa.
- ninguna capacidad -1 o 0,1 TB después: pasa.
- ningún modelo del mapeo queda con dos espacios: pasa.
- ningún vacío nuevo ni rellenado en fotos y ventanas: pasa.
- los fallos de fotos y ventanas se conservan: pasa.
- los contadores en bruto suman lo mismo en las filas que se quedan: pasa.
- tipos de salida: centro texto, ranura entera y date fecha: pasa.
- ningún modelo con dos capacidades válidas: pasa.
- data/raw intacto: la misma huella al empezar y al terminar: pasa.

Estado final: AVISO. Los datasets corregidos están en `data/processed/`, uno por tabla.

## Datos personales

- No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección.
- No hay datos de personas (reglas, apartado 9): el paso de protección se saltó el 17/11/2026 con el sí del responsable del caso.
- Ninguna columna de los datos tiene el papel de dato personal en el diccionario del origen. El número de serie identifica un disco, no a una persona.
- Antes de corregir se buscaron correos, documentos de identidad, cuentas bancarias y teléfonos en los textos (número de serie, modelo y centro): 0 columnas con alguno.
- Este método no usa ni deja ninguna columna de datos personales.

## Límites

- La corrección mira una tabla cada vez. Una clave huérfana o repetida al otro lado de un cruce no se ve ni se corrige aquí.
- No se repite aquí el diagnóstico completo sobre las tablas corregidas (manual 8.10, paso 1); se comprueban las cifras de cada corrección, los vacíos y las sumas.
- Las cifras de los motivos de C-18 y C-26 son las de la petición 07 y no se vuelven a medir en esta ejecución.
- Los contadores siguen como decimales (ver «Elementos mantenidos sin cambios»).
- Las fechas fecha y dia_fallo ya llegan como fecha y no se cambian; date pasa a fecha con la misma precisión que fecha.
