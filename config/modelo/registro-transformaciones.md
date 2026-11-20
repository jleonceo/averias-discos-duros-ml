---
titulo: Registro de transformaciones del caso 68 · cada regla que cambia los datos de trabajo, con su ficha
estado: vivo; solo acumula. Lo escribe scripts/03_correccion_datos.py la primera vez que aplica cada regla
fecha_documento: 2026-11-17
dueno: El responsable del caso (decide)
---

# Registro de transformaciones

Cada ficha lleva nueve campos: tabla y columna; cómo estaba; problema; decisión; qué se hizo; quién y con qué permiso;
comprobación; cómo quedó; cómo deshacer. Una ficha no se borra ni se reescribe: si una regla se retira o se corrige, se
añade otra que lo dice. Las cifras de cada ficha son las de la ejecución que la escribió.

## R-001 · fotos mensuales y ventanas de fallo · datacenter

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: fotos mensuales y ventanas de fallo · datacenter.
2. Cómo estaba: en las piezas anteriores a julio de 2023 el centro llega sin tipo (columna nula entera) y en las demás como texto.
3. Problema: C-03: al juntar las piezas, el centro tiene que tener un solo tipo.
4. Decisión: el centro es una categórica (diccionario del origen); técnicamente inequívoca.
5. Qué se hizo:

```python
columnas["datacenter"] = t["datacenter"].cast(pa.string(), safe=True)
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: fotos mensuales, de 42 a 0 ficheros sin tipo; ventanas de fallo, de 14 a 0 ficheros sin tipo; los vacíos de la columna son los mismos antes y después.
8. Cómo quedó: datacenter es texto en las dos tablas; donde no consta, sigue vacío.
9. Cómo deshacer: volver a leer la columna con el tipo de cada pieza. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-002 · fotos mensuales y ventanas de fallo · pod_slot_num

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: fotos mensuales y ventanas de fallo · pod_slot_num.
2. Cómo estaba: la ranura llega como decimal (38.0) porque trae vacíos.
3. Problema: C-04: un código de ranura no es un decimal.
4. Decisión: entero que admite vacío (petición 07): sus valores con dato son todos enteros.
5. Qué se hizo:

```python
columnas["pod_slot_num"] = t["pod_slot_num"].cast(pa.int64(), safe=True)  # falla si un valor no es entero
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: fotos mensuales, de 6.885.677 a 0 filas leídas como decimal; ventanas de fallo, de 261.083 a 0 filas leídas como decimal; los vacíos son los mismos antes y después.
8. Cómo quedó: pod_slot_num es int64 con vacíos.
9. Cómo deshacer: volver a leerla como decimal. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-003 · fotos mensuales y ventanas de fallo · date

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: fotos mensuales y ventanas de fallo · date.
2. Cómo estaba: date llega como texto AAAA-MM-DD; la columna fecha ya es fecha.
3. Problema: el rol de date en el diccionario es fecha.
4. Decisión: las fechas como fecha (petición 07).
5. Qué se hizo:

```python
fecha = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")  # para si algún texto no convierte
columnas["date"] = pa.array(fecha, type=pa.timestamp("ms"))
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: fotos mensuales, de 14.851.669 a 0 filas con la fecha como texto; ventanas de fallo, de 536.597 a 0 filas con la fecha como texto; ningún texto quedó sin convertir.
8. Cómo quedó: date es fecha, con la precisión de fecha.
9. Cómo deshacer: volver a escribir la fecha como texto ISO. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-004 · fotos mensuales con ventanas de fallo y recuento diario · model

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: fotos mensuales, ventanas de fallo y recuento diario · model.
2. Cómo estaba: cuatro modelos llegan también con dos espacios tras «WDC»: «WDC  WDS250G2B0A» → «WDC WDS250G2B0A»; «WDC  WUH721414ALE6L4» → «WDC WUH721414ALE6L4»; «WDC  WUH721816ALE6L0» → «WDC WUH721816ALE6L0»; «WDC  WUH721816ALE6L4» → «WDC WUH721816ALE6L4».
3. Problema: C-13: el mismo modelo escrito de dos formas parte en dos sus discos, sus días de disco y sus fallos.
4. Decisión: los modelos que solo se distinguen por los dos espacios tras «WDC» son el mismo modelo, porque son los mismos discos, con el mismo número de serie, escritos de dos formas; la corrección los junta (el responsable del caso, 17/11/2026, plan de calidad, «Lo aprobado»).
5. Qué se hizo:

```python
df["model"] = df["model"].replace(mapeo)  # mapeo cerrado de decisiones-correccion.json
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: fotos mensuales, de 4 a 0 nombres con dos espacios; ventanas de fallo, de 2 a 0 nombres con dos espacios; recuento diario, de 4 a 0 nombres con dos espacios. Filas cambiadas: fotos 3.896, ventanas 25, recuento 1.536.
8. Cómo quedó: ningún modelo del mapeo queda con dos espacios.
9. Cómo deshacer: aplicar el mapeo al revés en las filas que cambiaron, que se ven en data/raw/. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-005 · fotos mensuales con ventanas de fallo y recuento diario · capacity_bytes

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: fotos mensuales, ventanas de fallo y recuento diario · capacity_bytes.
2. Cómo estaba: algunas filas traen -1 o 0,1 TB.
3. Problema: C-05, C-06 y C-07: son lecturas malas, y en el recuento parten una clave en dos.
4. Decisión: reglas de negocio §3: la capacidad de un disco es la de su modelo; -1 y 0,1 TB son lecturas malas.
5. Qué se hizo:

```python
mala = df["capacity_bytes"] < minimo  # 2e11 bytes, de decisiones-correccion.json
df.loc[mala, "capacity_bytes"] = df.loc[mala, "model"].map(capacidad_modelo)  # la única válida del modelo
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: fotos mensuales, de 2.729 a 0 filas con capacidad -1 o 0,1 TB; ventanas de fallo, de 165 a 0 filas con capacidad -1 o 0,1 TB; recuento diario, de 2.102 a 0 filas con capacidad -1 o 0,1 TB; 94 modelos con capacidad y 0 con dos capacidades válidas. No es un relleno: es la regla, apartado 3 para un valor que no es válido.
8. Cómo quedó: ninguna fila con -1 o 0,1 TB.
9. Cómo deshacer: poner -1 o 0,1 TB en las filas que cambiaron, que se ven en data/raw/. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-006 · recuento diario · fila

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: recuento diario · fila.
2. Cómo estaba: tras corregir el nombre y la capacidad, varias filas comparten fecha, modelo, capacidad y centro.
3. Problema: C-07: la granularidad del recuento es una fila por clave.
4. Decisión: después de corregir el nombre y la capacidad, las filas del recuento con la misma clave se suman en una (discos y fallos).
5. Qué se hizo:

```python
df = df.groupby(["fecha", "model", "capacity_bytes", "datacenter"], sort=False, dropna=False, as_index=False)[["discos", "fallos"]].sum()
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: recuento diario, de 201.502 a 197.871 filas. Discos 453.609.422 y 453.609.422; fallos 17.960 y 17.960, por dos vías y día a día.
8. Cómo quedó: la clave es única y las sumas no cambian.
9. Cómo deshacer: volver a leer el recuento de data/raw/ y aplicar solo R-004 y R-005. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-007 · ventanas de fallo · fila

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: ventanas de fallo · fila.
2. Cómo estaba: 228 filas con fecha 2022-12-10 dicen 2022-12-11 en su texto y traen las horas encendido de ese día.
3. Problema: C-17 y P-01: no son datos de su fecha.
4. Decisión: son una copia del día que dice el texto: su fecha no tiene datos propios y sus filas sobran. Quitarlas no cambia ninguna respuesta (las instrucciones del caso, «Datos que no sirven o están mal»; criterios.md §2); el recuento de ese día se queda como está.
5. Qué se hizo:

```python
distinta = pd.to_datetime(df["date"], format="%Y-%m-%d") != df["fecha"]
salida = salida.filter(pa.array(~distinta))  # para si alguna trae un fallo
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: ventanas de fallo, de 536.825 a 536.597 filas, el 0,0 % de las filas, ninguna con un fallo. Los fallos de discos de datos sin el día anterior en su ventana pasan de 896 a 903. No cambian ninguna respuesta: el recuento de ese día se queda como está y no hay comparación entre grupos que dependa de ellas.
8. Cómo quedó: ninguna fila de las ventanas tiene la fecha distinta de su texto.
9. Cómo deshacer: volver a ejecutar sin la regla; las filas siguen en data/raw/. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-008 · fotos mensuales y ventanas de fallo · fichero

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: fotos mensuales y ventanas de fallo · fichero.
2. Cómo estaba: cada tabla llega partida en piezas por tamaño. Las piezas no traen todas las columnas.
3. Problema: la petición 07 pide un fichero corregido por dataset.
4. Decisión: juntar las piezas sin cambiar las filas (metodo/como_estan_organizados_los_datos.md).
5. Qué se hizo:

```python
with pq.ParquetWriter(destino, esquema_comun) as escritor:
    for f in piezas:
        escritor.write_table(corregir_pieza(pq.read_table(f), ...))
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: fotos mensuales, de 66 a 1 ficheros; ventanas de fallo, de 22 a 1 ficheros. Las columnas que una pieza no trae quedan vacías en sus filas; no se rellena ninguna.
8. Cómo quedó: un Parquet por tabla en data/processed/.
9. Cómo deshacer: leer las piezas de data/raw/podado/. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-009 · las cuatro tablas · lo que se deja sin cambios

Escrita el 2026-11-17 por scripts/03_correccion_datos.py.

1. Tabla y columna: las cuatro tablas · lo que se deja sin cambios.
2. Cómo estaba: el diagnóstico de calidad dejó 30 problemas.
3. Problema: 23 de ellos no se corrigen.
4. Decisión: C-01: ninguna de las 49 columnas casi vacías es de los cinco contadores de avería; si entran al modelo lo decide la preselección; C-02: las erratas están en el esquema, no en los datos; C-08: el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7); en el recuento, «sin dato» se queda como etiqueta del centro que no consta, la de correccion-datos/parametros.md; C-09: el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7); C-10: el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7); C-11: D4: ninguna pregunta usa cluster_id; C-12: un contador vacío quiere decir que el modelo no lo apunta y no se rellena (reglas, apartado 5); C-14: D2, cerrada en el plan de calidad («Lo aprobado»); C-15: D3, cerrada en el plan de calidad («Lo aprobado»); C-16: ninguna pregunta usa la temperatura de las ventanas; C-18: la edad la calcula la transformación con la regla de las reglas, apartado 3 (horas encendido y, sin ellas, primera aparición, también en las ventanas); las horas que bajan afectan a 3.443 discos y 52 fallos de 17.960 (cifras de la petición 07); C-19: tras corregir el nombre del modelo (C-13) y la capacidad (C-05) queda 1 cambio(s) de modelo real(es) entre dos fotos seguidas de un disco y 0 de capacidad, medidos en las fotos corregidas; C-20: el aviso mira si un contador pasa de cero el día anterior (reglas, apartado 6), no si sube; C-21: la edad la calcula la transformación con la regla de las reglas, apartado 3 (horas encendido y, sin ellas, primera aparición, también en las ventanas); C-22: la edad la calcula la transformación con la regla de las reglas, apartado 3 (horas encendido y, sin ellas, primera aparición, también en las ventanas); C-23: la edad la calcula la transformación con la regla de las reglas, apartado 3 (horas encendido y, sin ellas, primera aparición, también en las ventanas); C-24: reglas, apartado 3: un disco puede seguir en servicio tras un fallo y sus días siguen contando; C-25: reglas, apartado 3: un disco que falta en una foto y vuelve no ha desaparecido; C-26: de 16.101 fallos de discos de datos con día anterior, 4.049 llegan sin aviso y solo 69 tienen un contador vacío que su modelo sí apunta; aunque contaran como aviso, la parte sin aviso pasa del 25,1 % al 24,7 % (cifras de la petición 07); C-27: el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7); C-28: el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7); C-29: el sitio que falta se cuenta y se dice (reglas, apartado 5 y §7); al quitar las filas de C-17 pasan de 896 a 903 fallos de discos de datos sin el día anterior en su ventana; C-30: ninguna pregunta usa la tasa de un día.
5. Qué se hizo:

```python
# ninguna regla: estos datos no se tocan
```

6. Quién y con qué permiso: el analista, con la petición peticiones/07_correccion.md, lanzado por el responsable del caso el 17/11/2026 («Sí, lánzalo»).
7. Comprobación: las comprobaciones de vacíos y sumas de esta ejecución confirman que no cambian.
8. Cómo quedó: como llegaron.
9. Cómo deshacer: no hay nada que deshacer. data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.

## R-010 · igualación antes de cruzar · dia_fallo y centro vacío

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: igualación antes de cruzar · dia_fallo y centro vacío.
2. Cómo estaba: dia_fallo llega en nanosegundos en la lista de fallos y en las ventanas, y fecha en milisegundos; el centro que no consta está vacío en las fotos y las ventanas y es «sin dato» en el recuento.
3. Problema o finalidad: las claves tienen que tener el mismo tipo y el mismo valor para lo que no consta a los dos lados de un cruce (modelo-datos.md §4).
4. Decisión: reglas de transformación, «De qué se parte»: se igualan antes de cruzar y no se guardan en las tablas corregidas.
5. Qué se hizo:

```python
fl["dia_fallo"] = a_milisegundos(fl["dia_fallo"], "fallos")
centro = df["datacenter"].fillna(SIN_DATO)
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: ninguna fecha cambia al pasar a milisegundos (el script para si alguna cambia); 17.960 fallos cruzados con su ventana.
8. Cómo quedó: las claves cruzan con el mismo tipo; las tablas corregidas siguen igual.
9. Cómo deshacer: quitar las dos líneas. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-011 · dim_modelo · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: dim_modelo · tabla nueva.
2. Cómo estaba: no existía: la capacidad está en cada fila y no hay fecha de compra, garantía ni precio.
3. Problema o finalidad: las tablas del análisis necesitan por modelo su capacidad, tipo, fabricante, garantía, compra y precio (§1).
4. Decisión: reglas de transformación §1, con las convenciones técnicas 1 y 2.
5. Qué se hizo:

```python
dm["tipo_disco"] = np.select([cb <= LIMITE_ARRANQUE_BYTES, cb > LIMITE_ARRANQUE_BYTES], ["arranque", "datos"], "SIN_REGLA")
valor, origen, usadas, motivo = coste_gb(capacidad_tb, fecha_compra)
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 94 modelos, 33 de arranque y 61 de datos; 61 con fecha de compra y 57 con precio; los modelos sin precio suman 18.840 días de disco.
8. Cómo quedó: data/processed/dim_modelo.parquet, una fila por modelo.
9. Cómo deshacer: borrar data/processed/dim_modelo.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-012 · dim_precio_gb · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: dim_precio_gb · tabla nueva.
2. Cómo estaba: no existía.
3. Problema o finalidad: el disco nuevo que sustituye a uno que falla se paga al coste por GB del año del fallo (reglas, apartado 6).
4. Decisión: reglas de transformación §1: el coste el 1 de julio de cada año, con la misma regla que dim_modelo.
5. Qué se hizo:

```python
coste_gb(cap, pd.Timestamp(year=ano, month=7, day=1))
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 66 filas; los fallos de discos de datos de 2024 cuestan 832.698 dólares, y 305.124 con garantía.
8. Cómo quedó: data/processed/dim_precio_gb.parquet, una fila por capacidad y año.
9. Cómo deshacer: borrar data/processed/dim_precio_gb.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-013 · fotos_riesgo · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: fotos_riesgo · tabla nueva.
2. Cómo estaba: las fotos mensuales traen todos los discos, la foto del día del fallo y ningún objetivo.
3. Problema o finalidad: la pregunta 4 necesita una fila por disco de datos y foto con lo que se sabía ese día y el objetivo a 30 días.
4. Decisión: reglas de transformación §3, con las convenciones técnicas 3 y 4; salen failure, date y cluster_id.
5. Qué se hizo:

```python
for i in range(pf.num_row_groups):
    t = pf.read_row_group(i, columns=columnas)
    ...
    escritor.write_table(out)
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 14.604.861 filas, 11.026.052 de construcción y 3.578.809 de validación; quedan fuera 528 fotos del día del fallo y 246.280 de arranque; 16.266 filas con objetivo 1 para 16.188 fallos.
8. Cómo quedó: data/processed/fotos_riesgo.parquet, escrito bloque a bloque.
9. Cómo deshacer: borrar data/processed/fotos_riesgo.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-014 · fallos_detalle · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: fallos_detalle · tabla nueva.
2. Cómo estaba: la lista de fallos solo trae el disco y el día.
3. Problema o finalidad: las preguntas 1 a 4 necesitan de cada fallo su modelo, edad, aviso, sitio, tomo y coste.
4. Decisión: reglas de transformación §4 (cruces 1 a 6 y 13).
5. Qué se hizo:

```python
fd = cruzar(ctx, 1, ..., fd, del_dia, ["serial_number", "dia_fallo"], ["serial_number", "fecha"])
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 17.960 fallos, 16.996 de discos de datos; 4.046 sin aviso de 16.093 con día anterior; 262 coinciden con el anterior de su tomo.
8. Cómo quedó: data/processed/fallos_detalle.parquet, una fila por fallo.
9. Cómo deshacer: borrar data/processed/fallos_detalle.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-015 · vida_discos · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: vida_discos · tabla nueva.
2. Cómo estaba: no existía una fila por disco.
3. Problema o finalidad: la supervivencia de la pregunta 2 y las altas y bajas del bloque 1.
4. Decisión: reglas de transformación §5, con la convención técnica 5.
5. Qué se hizo:

```python
np.select([primer_fallo.notna(), desaparece, primer_fallo.isna()], ["fallo", "desaparece", "sigue"], "SIN_REGLA")
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 402.643 discos: 16.984 en fallo, 71.328 desaparecen y 314.331 siguen.
8. Cómo quedó: data/processed/vida_discos.parquet, una fila por disco de datos.
9. Cómo deshacer: borrar data/processed/vida_discos.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-016 · dias_por_tramo · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: dias_por_tramo · tabla nueva.
2. Cómo estaba: los días de disco están por modelo, centro y día, sin edad.
3. Problema o finalidad: la tasa por edad de la pregunta 2, la ajustada por centro de la 3 y la previsión del bloque 9.
4. Decisión: reglas de transformación §6, con las convenciones técnicas 6 y 7 (cruces 11 y 15).
5. Qué se hizo:

```python
m["dias_disco"] = m["parte"] * m["dias_recuento"]
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 13.275 filas; se reparten 445.189.491 días de disco de 446.108.683; quedan sin repartir 919.192 en 110 celdas sin foto.
8. Cómo quedó: data/processed/dias_por_tramo.parquet.
9. Cómo deshacer: borrar data/processed/dias_por_tramo.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-017 · inicio_trimestre · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: inicio_trimestre · tabla nueva.
2. Cómo estaba: no existía.
3. Problema o finalidad: la previsión del bloque 9 usa los discos del primer día de cada trimestre con su edad.
4. Decisión: reglas de transformación §7 (cruce 14).
5. Qué se hizo:

```python
d.groupby(["model", "capacidad_tb", "edad_anos_cumplidos"]).size()
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 3.117 filas de 22 trimestres con 4.805.590 discos; 22 trimestres iguales al recuento, modelo a modelo.
8. Cómo quedó: data/processed/inicio_trimestre.parquet.
9. Cómo deshacer: borrar data/processed/inicio_trimestre.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-018 · modelo_trimestre · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: modelo_trimestre · tabla nueva.
2. Cómo estaba: no existía.
3. Problema o finalidad: la pregunta 1, por modelo y trimestre.
4. Decisión: reglas de transformación §8 (cruces 7, 8 y 15).
5. Qué se hizo:

```python
m["pasa_minimo_ano"] = m["dias_disco_ano"] >= MINIMO_DIAS_ANO
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 1.028 filas; 16.996 fallos y 446.108.683 días de disco; pasan el mínimo 152 de 299 celdas de modelo y año.
8. Cómo quedó: data/processed/modelo_trimestre.parquet.
9. Cómo deshacer: borrar data/processed/modelo_trimestre.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-019 · centro_mes · tabla nueva

Escrita el 2026-11-17 por scripts/05_transformacion_datos.py.

1. Tabla y columna: centro_mes · tabla nueva.
2. Cómo estaba: no existía.
3. Problema o finalidad: la tasa bruta por centro de la pregunta 3 y el reparto de los discos del bloque 1.
4. Decisión: reglas de transformación §9 (cruce 8).
5. Qué se hizo:

```python
rd.groupby(["datacenter", "mes"]).agg(dias_disco=("discos", "sum"), fallos=("fallos", "sum"))
```

6. Quién y con qué permiso: el analista, con la petición peticiones/09_transformacion.md y las reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).
7. Comprobación: 186 filas, 144 desde julio de 2023.
8. Cómo quedó: data/processed/centro_mes.parquet.
9. Cómo deshacer: borrar data/processed/centro_mes.parquet. Las tablas corregidas no se tocan, así que basta con borrar la tabla nueva o volver a ejecutar el script sin la regla.

## R-020 · fotos_riesgo · partición en entrenamiento y validación

Escrita el 2026-11-18 por el analista, con las cifras de la ejecución real de scripts/12_particion.py (el script no escribe
en este registro; petición 20, «Qué es»).

1. Tabla y columna: fotos_riesgo · periodo, partida en dos ficheros.
2. Cómo estaba: una sola tabla con la columna periodo, que la transformación escribió con el Calendario (R-013).
3. Problema o finalidad: el método preparacion-modelo §1 pide la construcción y la validación en ficheros aparte,
   comprobadas sin fuga, antes de describir el desequilibrio y proponer la matriz.
4. Decisión: reglas de negocio §7 (el responsable del caso, 17/11/2026: «Sí, apruebo»): partición por fecha; construcción del
   01/01/2020 al 30/06/2024 y validación del 01/07/2024 al 30/06/2025. No se vuelve a partir: se separa por periodo y se
   comprueba fila a fila contra esas fechas. No hay lote de producción: la prueba final es la reserva, fuera del caso.
5. Qué se hizo:

```python
mascara = pc.fill_null(pc.equal(periodo, p["periodo"]), False)
escritores[p["parte"]].write_table(t.filter(mascara), row_group_size=...)
```

6. Quién y con qué permiso: el analista, agente analista-preparacion-modelo, con la petición
   peticiones/20_particion_y_preparacion.md y el guion del modelo aprobado por el responsable del caso el 18/11/2026 («Sí, apruebo»;
   lanzado con «Vale, venga, adelante»). La ejecución real, la sesión principal.
7. Comprobación: las seis comprobaciones y las tres validaciones de la salida, en verde; ninguna clave en las dos
   partes, ninguna repetida y ninguna fila cuyo periodo no coincida con su fecha. Construcción 11.026.052 fotos y
   11.962 con fallo (0,1085 %), 54 fotos mensuales, horizonte hasta el 2024-06-30; validación 3.578.809 y 4.304
   (0,1203 %), 12 fotos mensuales. Suman las 14.604.861 de la entrada. Diferencia de tasa, 0,0118 puntos. 282.422
   discos están en las dos partes, como se espera al partir por fecha. Todas iguales a las cifras de control.
8. Cómo quedó: data/processed/fotos_riesgo_entrenamiento.parquet (598 MB) y fotos_riesgo_validacion.parquet
   (149 MB), con las 144 columnas y un grupo de filas por fecha; huellas en informes/particion.json.
9. Cómo deshacer: borrar los dos ficheros e informes/particion.json. fotos_riesgo.parquet no se toca.

## R-021 · fotos_riesgo_entrenamiento · matriz de transformaciones aprobada

Escrita el 2026-11-18 por el analista. Todavía no cambia ningún dato: fija cómo entra cada columna en el preprocesador,
que escribirá scripts/13_preparacion.py y se ajustará dentro de cada entrenamiento.

1. Tabla y columna: fotos_riesgo_entrenamiento · las 144 columnas.
2. Cómo estaba: las columnas llegan tal como las dejó la transformación, sin decidir cuáles entran ni cómo.
3. Problema o finalidad: preparacion-modelo §3 pide una matriz aprobada antes del preprocesador: qué entra, en qué
   rama de cada familia de algoritmos, con qué escalado, relleno y columnas de salida.
4. Decisión: la matriz que propuso la petición 20, aprobada por el responsable del caso el 18/11/2026 («Sí, siguiente pregunta», P-01).
   Las cuatro variables nuevas candidatas no se crean ahora (P-04, «Digo, vale, que se hacen luego, en la segunda
   pregunta»). Dos criterios técnicos: las 2.539 fotos sin lectura SMART van al tramo de referencia en la
   logística (P-02) y un modelo nuevo va a «otras» (P-03).
5. Qué se hizo:

```python
# ninguna transformación todavía: la matriz se guarda en config/modelo/matriz_transformaciones.md
```

6. Quién y con qué permiso: el analista, agente analista-preparacion-modelo, con la petición
   peticiones/20_particion_y_preparacion.md; la matriz, aprobada por el responsable del caso el 18/11/2026.
7. Comprobación: 135 columnas en la matriz y 9 fuera suman las 144; entran 70 (69 en las tres familias y 1 solo en
   los árboles) y no entran 65. el analista rehízo sobre el entrenamiento las cifras en que se apoya.
8. Cómo quedó: config/modelo/matriz_transformaciones.md, estado aprobada.
9. Cómo deshacer: una nueva aprobación del responsable del caso con la matriz cambiada; esta ficha no se borra.

## R-022 · fotos_riesgo_entrenamiento · matriz corregida: seis copias fuera

Escrita el 2026-11-18 por el analista. Corrige R-021: la matriz aprobada metía seis variables que repiten a otra.

1. Tabla y columna: fotos_riesgo_entrenamiento · smart_190_raw, smart_183_normalized, smart_184_normalized,
   smart_187_normalized, smart_189_normalized, smart_222_normalized y smart_197_normalized.
2. Cómo estaba: las siete entraban en las tres familias (matriz de R-021).
3. Problema o finalidad: la primera ejecución real de scripts/13_preparacion.py paró con dos validaciones en rojo:
   columnas idénticas en la logística (6) y dos variables sin ninguna columna (7). Medido en todo el entrenamiento:
   smart_190_raw es igual a smart_194_raw en las 5.652.045 fotos en que existe; los cinco normalizados son una función
   exacta de su bruto (ningún bruto con dos normalizados) con el mismo vacío fila a fila. smart_197_normalized solo sale de
   100 en 1.582 fotos y en la logística no deja ningún tramo con la muestra de partida; no es función de su bruto.
4. Decisión: el responsable del caso, 18/11/2026 («arréglalo y haz lo que tengas que hacer»), P-05 de la matriz: las seis copias no entran
   en ninguna familia; smart_197_normalized entra solo en los árboles; el vacío de 183, 184 y 189 lo lleva ahora su bruto.
   El criterio «varía de verdad» añade la función exacta con el mismo vacío. smart_198_normalized se queda: 2.076 fotos
   con un bruto que da dos normalizados.
5. Qué se hizo:

```python
NUM_ARBOLES = NUM_LOGISTICA[:13] + ["avisa"] + NUM_LOGISTICA[13:] + ["smart_197_normalized"]
# NUM_LOGISTICA sin las siete; NO_ENTRAN con las seis; VACIO_COMPARTIDO sin sus siete entradas
```

6. Quién y con qué permiso: el analista, con el método programacion-del-caso y el permiso del responsable del caso del 18/11/2026.
7. Comprobación: la prueba 13 salió en rojo antes del cambio (las listas del script ya no eran las de la matriz) y
   en verde después en sus partes 1 y 2; la matriz suma 64 que entran, 71 que no y 9 fuera, 144.
8. Cómo quedó: config/modelo/matriz_transformaciones.md con P-05; scripts/13_preparacion.py con las listas
   nuevas.
9. Cómo deshacer: la matriz anterior está en el scratchpad de la sesión (`matriz_antes_R68-114.md`); volver a ella
   pide otra aprobación del responsable del caso.

## R-023 · fotos_riesgo_entrenamiento · preselección de variables de la logística

Escrita el 2026-11-18 por el analista, con las cifras de la segunda ejecución real de scripts/14_preseleccion.py. Todavía
no cambia ningún dato: fija qué variables de la matriz entran en la regresión logística.

1. Tabla y columna: fotos_riesgo_entrenamiento · las 62 variables de la logística de la matriz (R-021 y R-022).
2. Cómo estaba: las 62 entraban en la logística, con 496 columnas tras el preprocesador.
3. Problema o finalidad: el método preseleccion-variables pide preseleccionar un modelo lineal: tope de columnas y
   variables que dicen lo mismo, que en una regresión se reparten el efecto.
4. Decisión: reglas de negocio §7 (el responsable del caso, 18/11/2026): modo comparativo, consenso amplio, y smart_5_raw,
   smart_187_raw, smart_197_raw y smart_198_raw siempre dentro; los árboles reciben sus 64 columnas sin votar. El
   parecido entre dos variables se mide solo con las fotos que tienen dato en las dos (el responsable del caso, «adelante», 18/11/2026;
   método §6, último punto), porque en la primera ejecución el vacío de los contadores que solo registra algún modelo
   fabricaba parecidos de 0,99 y 1 (smart_184_raw está vacío en 46 de los 58 modelos). La lista de la semilla 42, aunque
   la de la semilla 43 difiere en dos variables con la muestra entera (P-01; el responsable del caso, «Sí», 18/11/2026).
5. Qué se hizo:

```python
comunes = (df[a].notna() & df[b].notna()).to_numpy()
vc = cramer(cod[a][comunes], cod[b][comunes]) if comunes.any() else None
```

6. Quién y con qué permiso: el script, el agente de la petición peticiones/21_preseleccion_competicion_y_ganador.md
   (primera parte, lanzada por el responsable del caso: «Sí, lánzalo»); el cambio del parecido, el analista con el método programacion-del-caso.
   La ejecución real, la sesión principal.
7. Comprobación: la prueba del parecido por el vacío salió en rojo antes del cambio y las 14 pruebas en verde
   después; las seis validaciones de el método en verde; ninguna alarma de fuga; data/raw/ con la misma huella. Muestra de
   partida 232.243 fotos y 11.962 con fallo; tope 1.196 columnas. Tres intentos (100.000, 200.000 y la muestra entera):
   las dos semillas difieren en 2, 1 y 2 variables; en el último, cambio_smart_197 y meses_desde_foto_anterior. 89
   minutos.
8. Cómo quedó: informes/preseleccion.json y preseleccion.md: 25 variables y 169 columnas en el ajuste con la muestra.
   Salen, entre otras, edad_anos (Spearman 0,797 con smart_240_raw en 167.257 fotos), model (garantia_anos, V de Cramér
   0,999) y contadores_que_avisan (pierde ante smart_5_raw, obligatoria, Spearman 0,748).
9. Cómo deshacer: borrar los dos informes; el modelado leerá entonces las 62 variables. Volver al cálculo con el
   vacío dentro pide otra aprobación del responsable del caso.

## R-024 · producción · contrato de producción aprobado

Escrita el 2026-11-19 por el analista (método preproduccion §4). Todavía no cambia ningún dato: fija qué hace producción con
cada foto mensual, desde el dato en bruto hasta la probabilidad de fallo.

1. Tabla y columna: la foto mensual de producción · las 63 columnas del ganador, más datacenter, el identificador,
   el objetivo y su horizonte (68 finalistas).
2. Cómo estaba: la cadena de cada columna estaba repartida entre este registro y las reglas de transformación, sin
   decir qué paso va al reentrenar y cuál al ejecutar.
3. Problema o finalidad: el método preproduccion pide un contrato sin huecos antes de escribir el código de
   producción.
4. Decisión: el contrato de `config/modelo/contrato_produccion.md`, escrito por
   scripts/18_contrato_produccion.py: 25 pasos, 3 que quitan filas, 13 que no aprenden, 5 que necesitan otras filas y 4
   que aprenden. Aprobado por el responsable del caso el 19/11/2026 («Sí, con el arreglo»), con un cambio: al ejecutar, la edad de un disco
   sin horas encendido solo usa las ventanas de fallos ocurridos antes del día de la foto. Una ventana son los 30 días
   anteriores a un fallo, así que su existencia anuncia un fallo que ese día no se conoce.
5. Qué se hizo:

```python
# ninguna transformación todavía: el contrato se guarda en config/modelo/contrato_produccion.md
```

6. Quién y con qué permiso: el agente de la petición peticiones/22_preproduccion_contrato_y_codigo.md (primera
   parte, lanzada por el responsable del caso: «Sí, lánzalo»); el arreglo, propuesto por el analista y aprobado por el responsable del caso.
7. Comprobación: la prueba del script 18, en rojo antes y con sus 11 casos en verde después, relanzada por el analista.
   Medido por el analista en fotos_riesgo: 2.735 fotos sin horas encendido (2.539 de construcción y 196 de validación); en
   una sola la primera aparición sale de una ventana. Esa foto acaba en fallo. El arreglo no cambia ninguna respuesta
   y la tabla del modelo no se rehace.
8. Cómo quedó: contrato aprobado; el código de producción se escribe con él.
9. Cómo deshacer: una nueva aprobación del responsable del caso con el contrato cambiado; esta ficha no se borra.
