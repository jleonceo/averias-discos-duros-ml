# Preproducción del caso 68

**Estado: OK.** Contrato aprobado (el responsable del caso, 19/11/2026: «Sí, con el arreglo»). Las 11 validaciones, en verde.

## Las finalistas y su cadena

El modelo usa 63 columnas y lee 64 variables, porque también lee datacenter y lo vacía. Con el identificador, el objetivo y su horizonte son 68 finalistas, todas con su cadena de pasos en el contrato.

## El contrato

Aprobación: El responsable del caso, 19/11/2026: «Sí, con el arreglo». Está en `config/modelo/contrato_produccion.md`: 25 pasos, cada uno con su clase, la receta del HistGradientBoostingClassifier y el corte, las listas de 20, 100, 500, 1000 discos de cada foto mensual, con la de 100 como principal.

## Qué hace cada script

- `scripts/pipeline_riesgo.py`: pasa la foto en bruto a las columnas del modelo y construye el Pipeline nuevo cada vez.
- `produccion/reentrenar.py`: rehace el modelo con la receta fija y lo deja aparte, con su ficha; no sustituye el modelo en uso.
- `produccion/ejecutar.py`: puntúa una foto mensual sin quitar ninguna fila; lo que no puntúa sale con su motivo.
- `tests/comprobar_produccion_por_otro_camino.py`: rehace la puntuación por otro camino, sin cargar el modelo, y la compara fila a fila.

## El reentreno

Tabla `data\processed\fotos_riesgo.parquet`, 14.604.861 fotos. Quitadas: disco de arranque, 0; fotos posteriores a la fecha del entrenamiento, 0; objetivo sin conocer, 0; sanas que no entran en la muestra, 14.296.824.
Modelo en uso: sí (modelos/en_uso/modelo_riesgo.joblib). Igual a lo que guardó el modelado o al modelo en uso: None. Guardado en `modelos\reentrenos\2026-11-19`.

## El lote

Entrada `data\raw\reserva\fotos_mensuales\2026-06.parquet`: 353.401 filas y 353.401 de salida. Sin puntuar: disco de arranque: fuera del modelo (reglas, apartado 3 y §7), 3.893; foto del día del fallo: el disco ya está marcado como fallado (reglas de transformación §3), 13.

## La prueba por otro camino

Coincide: True, con tolerancia 1e-12; con la salida estropeada da rojo: True.

## Validaciones

- cadenas_completas: sí
- pasos_con_clase: sí
- aprende_tras_la_particion: sí
- contrato_sin_vacios: sí
- columnas_del_contrato: sí
- filas_ejecucion: sí
- bit_a_bit: sí
- otro_camino: sí
- sin_quitar_filas_al_ejecutar: sí
- ficha_cuadra: sí
- cambia_con_datos_nuevos: sí

## Parámetros usados

- tolerancia de la prueba por otro camino: 1e-12 (preproduccion/parametros.md, por defecto)
- semilla: 42 (informes/modelado.json, ganador.semilla)
- corte: listas de 20, 100, 500, 1000 por foto mensual; principal 100 (informes/modelado.json (validacion.por_mes y aprobado_antes); reglas, apartado 7, cuestión 010)
- carpeta de reentrenos: modelos/reentrenos/AAAA-MM-DD/ (preproduccion/parametros.md)
- carpeta de predicciones: data/predicciones/AAAA-MM-DD/ (preproduccion/parametros.md)
- formato de guardado: joblib con el módulo .py (preproduccion/parametros.md)

## Datos personales

Los datos son de discos: serial_number identifica un disco, no a una persona (reglas, apartado 9). El contrato no usa ni deja ninguna columna de datos personales. No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección.

## Límites

- El contrato describe la parte 2, que todavía no existe: nada de él se ha ejecutado sobre los datos.
- La capacidad del modelo se toma al ejecutar de la historia de fotos y ventanas hasta el día de la foto. En el desarrollo salió de todo el periodo, también del recuento diario. Si algún modelo tiene su única capacidad válida solo en el recuento, NO SE PUEDE SABER sin medirlo; lo mide la parte 2 con las fotos de control.
- La primera aparición de un disco sin horas encendido solo usa las ventanas de fallos ocurridos antes del día de la foto. El desarrollo usó también las de fallos posteriores: en una de las 2.735 fotos sin horas de fotos_riesgo la edad puede salir distinta, y la prueba del módulo la cuenta aparte.
- En la validación, dos discos con la misma probabilidad cerca del borde de una lista se contaron con su valor esperado (por eso hay cifras con decimales); producción desempata por serial_number. Las listas pueden diferir en esos empates.
