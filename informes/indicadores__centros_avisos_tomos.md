# Centros de datos y otros factores de riesgo

Caso 68, paso 5, bloques 5 a 8 del plan de la analítica, el minicubo y lo que falta en los datos. Datos hasta el 30/06/2025; ejecutado el 18/11/2026. Estado: **AVISO**, riesgo medio.

Cinco preguntas calculadas con 47 cifras, todas con su segunda vía, y las nueve validaciones en verde. Quedan 8 grupos sin conclusión o aparte, y el centro y el tomo solo constan desde el 01/07/2023.

## Las preguntas y su planteamiento

Las cinco preguntas salen del plan de la analítica, aprobado por el responsable del caso el 16/11/2026, y del planteamiento 1.A. Entran los discos de datos, sin los de arranque. Lo que va por centro y por tomo cubre del 01/07/2023 al 30/06/2025, porque antes el sitio no consta; lo demás, del 01/01/2020 al 30/06/2025. La tasa anual de fallo es 100 × 365 × fallos / días de disco. Cuando el corte no está en el recuento, los días de cada modelo, centro y mes se reparten entre sus fotos.

- **B5.** Si algún centro de datos tiene más fallos que los demás con los mismos discos. Mínimo: 50.000 días de disco al año y 20 fallos (reglas, apartado 7; petición, comprobación 1).
- **B6.** Cuántos discos avisan, qué aviso anticipa más fallos y cuánto siguen funcionando. Mínimo: 30 fotos por grupo (método, parametros.md).
- **B7.** Cuántas veces caen varios discos del mismo tomo cerca en el tiempo, y si pasa más que por azar. Mínimo: no aplica: se cuentan todos los tomos y se comparan con el azar.
- **B8.** Si la temperatura, la carga de trabajo o los arranques acompañan a más fallos. Mínimo: 20 fallos en cada uno de los tres tramos de un grupo (petición, criterio 8).
- **MC.** Qué perfiles de disco tienen más riesgo, por fabricante, capacidad, edad, centro y aviso. Mínimo: 50.000 días de disco y 20 fallos por valor o celda (petición, criterio 9).

## B5 · Si un centro falla más por sí mismo

Con la misma mezcla de modelo, año de edad y trimestre, 1 centros fallan más que los demás (sac2) y 1 fallan menos (sac0). Por azar saldrían distintos 0,25 de los 5 centros con conclusión, y salen 2. La tasa de todos los centros juntos es del 1,5262 % anual.

El intervalo de cada razón lleva φ = 1,0196, lo que varían los fallos de un trimestre a otro más de lo que supone Poisson, medido en 42 celdas de centro y trimestre con 36 grados de libertad (sin «sin dato»). Con φ = 1 no hay variación de más y el intervalo es el exacto de Poisson.

5 fallos caen en un modelo, año de edad y trimestre sin ningún día de disco, así que no tienen tasa con la que calcular sus esperados. Cuentan en los observados de su centro: phx1, 5.

| Centro | Días de disco | Fallos | Tasa bruta | Razón (intervalo) | Tasa ajustada | Lectura |
|---|---:|---:|---:|---|---:|---|
| ams5 | 12.111.055 | 476 | 1,4346 % | 1,0697 (0,9748 a 1,1712) | 1,6325 % | no se distingue |
| iad1 | 18.007.479 | 512 | 1,0378 % | 0,9970 (0,9117 a 1,0882) | 1,5217 % | no se distingue |
| phx1 | 65.723.705 | 2.160 | 1,1996 % | 1,0407 (0,9969 a 1,0860) | 1,5884 % | no se distingue |
| sac0 | 59.117.752 | 2.806 | 1,7325 % | 0,9060 (0,8725 a 0,9405) | 1,3827 % | falla menos |
| sac2 | 45.064.768 | 2.546 | 2,0621 % | 1,0995 (1,0568 a 1,1435) | 1,6780 % | falla más por sí mismo |
| sin dato | 6.621.213 | 128 | 0,7056 % | 0,7506 (0,6250 a 0,8940) | 1,1455 % | aparte |
| yyz1 | 651.306 | 6 | 0,3362 % | 0,5116 (0,1855 a 1,1215) | 0,7808 % | sin conclusión |

La tasa bruta usa los días del recuento por centro; la razón y la tasa ajustada usan los días repartidos por modelo y año de edad, que dejan fuera los días de las celdas sin foto.

- Al quitar uno a uno los modelos de sac0, la lectura cambia en 0 de los 50 modelos probados.
- Al quitar uno a uno los modelos de sac2, la lectura cambia en 0 de los 34 modelos probados.
- 21 modelos pasan el mínimo de días en dos centros o más.
- Temperatura media desde 07/2023: ams5, 34,50 °C; iad1, 33,73 °C; phx1, 33,44 °C; sac0, 30,02 °C; sac2, 35,87 °C; yyz1, 30,88 °C; sin dato, 33,44 °C.

Las comprobaciones de B5:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: sí.
- La referencia: sí.
- El azar en muchos grupos: sí.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: no aplica, porque los bloques 5 a 8 describen y no predicen.
- La cobertura: sí.
- Los periodos: sí.
- Del petición, cada φ usado es el medido y, si sale menor que 1, vale 1: sí.
- Del petición, la lectura de cada centro sale de su intervalo con φ: sí.

## B6 · Qué hace Backblaze con los avisos

De las fotos con algún aviso, el 3,25 % acaba en fallo antes de 90 días, frente al 0,15 % de las fotos sin aviso. El 94,48 % de las que avisan sigue funcionando a los 90 días. La unidad es la foto: un disco que avisa cuenta cada mes, porque el aviso es acumulado.

El intervalo de la parte que falla es el exacto de Clopper-Pearson, ensanchado por el φ de cada grupo: lo que varía de un trimestre a otro la parte de sus fotos que falla, más de lo que supone la binomial.

| Grupo | Fotos | Discos | Sigue | Falla (intervalo) | φ | Desaparece | Frente a sin aviso |
|---|---:|---:|---:|---|---:|---:|---|
| sin aviso | 13.126.654 | 389.282 | 98,34 % | 0,15 % (0,139 % a 0,159 %) | 23,3 | 1,51 % | referencia |
| con algún aviso | 852.080 | 40.925 | 94,48 % | 3,25 % (2,930 % a 3,600 %) | 76,8 | 2,27 % | por encima |
| contador 5 | 440.582 | 23.590 | 93,68 % | 4,34 % (3,906 % a 4,803 %) | 54,1 | 1,98 % | por encima |
| contador 187 | 218.789 | 12.606 | 90,18 % | 6,46 % (5,807 % a 7,153 %) | 41,6 | 3,36 % | por encima |
| contador 188 | 267.618 | 10.192 | 96,24 % | 1,30 % (1,148 % a 1,467 %) | 13,4 | 2,46 % | por encima |
| contador 197 | 149.959 | 16.838 | 88,41 % | 9,58 % (8,385 % a 10,892 %) | 68,2 | 2,00 % | por encima |
| contador 198 | 113.845 | 12.160 | 87,75 % | 9,90 % (8,572 % a 11,358 %) | 62,0 | 2,35 % | por encima |

Solo con las fotos de Seagate, el único fabricante que trae los cinco contadores, 6.714.576 fotos con 90 días por delante. Cada contador se compara con el «sin aviso» de Seagate:

| Grupo | Fotos | Discos | Sigue | Falla (intervalo) | φ | Desaparece | Frente a sin aviso |
|---|---:|---:|---:|---|---:|---:|---|
| sin aviso | 6.015.625 | 166.454 | 97,36 % | 0,17 % (0,149 % a 0,184 %) | 28,2 | 2,47 % | referencia |
| con algún aviso | 698.951 | 28.681 | 94,65 % | 2,73 % (2,440 % a 3,034 %) | 58,8 | 2,62 % | por encima |
| contador 5 | 344.356 | 16.368 | 93,62 % | 4,05 % (3,589 % a 4,560 %) | 52,6 | 2,32 % | por encima |
| contador 187 | 218.789 | 12.606 | 90,18 % | 6,46 % (5,807 % a 7,153 %) | 41,6 | 3,36 % | por encima |
| contador 188 | 267.606 | 10.191 | 96,24 % | 1,30 % (1,147 % a 1,466 %) | 13,4 | 2,46 % | por encima |
| contador 197 | 75.992 | 8.463 | 86,97 % | 9,71 % (8,316 % a 11,246 %) | 46,5 | 3,32 % | por encima |
| contador 198 | 75.992 | 8.463 | 86,97 % | 9,71 % (8,316 % a 11,246 %) | 46,5 | 3,32 % | por encima |

En Seagate, el 197 y el 198 marcan las mismas fotos: 75.992 cada uno, así que sus dos filas son la misma medida y no dos avisos distintos.

De los 16.996 fallos de discos de datos, 16.093 tienen el día anterior en su ventana y 4.046 de ellos llegan sin aviso; 903 no lo tienen y quedan aparte.

Por año del fallo: los que llegan sin aviso el día anterior, entre los que tienen ese día; los que no tienen día anterior, entre todos:

- 2020: 40,3 % sin aviso (516 de 1.279) y 2,1 % sin día anterior (28 de 1.307).
- 2021: 36,8 % sin aviso (656 de 1.785) y 2,1 % sin día anterior (38 de 1.823).
- 2022: 26,6 % sin aviso (762 de 2.865) y 4,5 % sin día anterior (134 de 2.999).
- 2023: 22,5 % sin aviso (890 de 3.958) y 5,8 % sin día anterior (243 de 4.201).
- 2024: 20,5 % sin aviso (880 de 4.298) y 5,3 % sin día anterior (240 de 4.538).
- 2025 (año incompleto): 17,9 % sin aviso (342 de 1.908) y 10,3 % sin día anterior (220 de 2.128).

En la ventana de 30 días, 12.900 de 16.917 fallos avisan algún día y 10.171 ya avisaban el primero.
Los 2.729 que empiezan a avisar dentro lo hacen 10,0 días antes del fallo en la mediana, con cuartiles de 4,0 y 19,0.

En la construcción, el porcentaje de fotos con el contador subiendo respecto a la foto anterior, entre las de discos que fallan en 30 días y las demás:

- Contador 5: 32,46 % frente a 0,553 %.
- Contador 187: 40,21 % frente a 0,412 %.
- Contador 197: 21,58 % frente a 0,230 %.
- Contador 198: 16,63 % frente a 0,151 %.

Las comprobaciones de B6:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: sí.
- La referencia: sí.
- El azar en muchos grupos: sí.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: no aplica, porque los bloques 5 a 8 describen y no predicen.
- La cobertura: sí.
- Los periodos: sí.
- Del petición, ninguna cifra cruzada con el fallo a 30 días usa una foto de validación: sí.
- Del petición, cada φ usado es el medido y, si sale menor que 1, vale 1: sí.

## B7 · Dónde está el riesgo de perder datos

El azar baraja los días de los fallos dentro de cada centro y trimestre del fallo, 200 veces. Hay 489 tomos con dos fallos o más en 30 días, frente a 436,9 de media (percentil 95, 456,0): por encima del percentil 95.
Con tres fallos o más en 7 días hay 8 tomos, frente a 2,91 de media (percentil 95, 6,0): por encima del percentil 95.

Barajando solo dentro de cada centro, como antes de la petición 19: 2 fallos o más en 30 días, media 352,87 y percentil 95 377,0, por encima; 3 fallos o más en 7 días, media 1,11 y percentil 95 3,0, por encima.

Desde el 01/07/2023 hay 8.634 fallos; 8.493 tienen tomo, en 5.404 tomos, y 262 llegan antes de que acabe de rehacerse el anterior de su tomo. La paridad supuesta se alcanza 2 veces.

- 2 fallos o más en 7 días: 151 tomos.
- 2 fallos o más en 30 días: 489 tomos.
- 3 fallos o más en 7 días: 8 tomos.
- 3 fallos o más en 30 días: 28 tomos.
- 4 fallos o más en 7 días: 0 tomos.
- 4 fallos o más en 30 días: 8 tomos.

El riesgo vivo cuenta cada mes los tomos con varios discos que avisan a la vez. Con dos o más hay 4.327,9 al mes de media, frente a 5.720,6 por azar. Con tres o más hay 2.769,5, frente a 2.260,8.

Los cinco tomos con más fallos que coinciden:

- phx1|1063|59 (TOSHIBA MG07ACA14TA, TOSHIBA MG08ACA16TA): 9 fallos y 3 coincidencias.
- sac0|1128|46 (ST12000NM0007, ST12000NM0008): 7 fallos y 3 coincidencias.
- sac2|1118|45 (HGST HUH721212ALE604, HGST HUH721212ALN604): 7 fallos y 3 coincidencias.
- sac2|1123|57 (HGST HUH721212ALN604): 5 fallos y 3 coincidencias.
- phx1|1063|43 (TOSHIBA MG07ACA14TA, TOSHIBA MG08ACA16TE): 9 fallos y 2 coincidencias.

Las comprobaciones de B7:

- La unidad: sí.
- El mínimo de casos: no aplica, porque el bloque no saca conclusiones de grupos: compara recuentos de todos los tomos con el azar.
- Los empates: sí.
- La referencia: sí.
- El azar en muchos grupos: sí.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: no aplica, porque los bloques 5 a 8 describen y no predicen.
- La cobertura: sí.
- Los periodos: sí.
- Del petición, la marca «por encima del percentil 95» de cada medida del azar sale de comparar sus tomos observados con su percentil 95: sí.

## B8 · Otros factores del disco

Cada factor se mide dentro de su grupo, el modelo en la temperatura y el modelo con su año de edad en los demás. La razón compara los fallos de un tramo con los que tendría a la tasa de su grupo. Estas cifras describen una asociación y no dicen por qué ocurre.

- **Temperatura.** Entran 20 de 61 grupos, con 16.200 fallos: 01_frio, razón 0,7737 (0,7470 a 0,8011), 3.170 fallos; 02_medio, razón 0,8983 (0,8757 a 0,9213), 5.995 fallos; 03_caliente, razón 1,2958 (1,2657 a 1,3265), 7.035 fallos. Salen aparte 514 fallos y 11 no tienen tramo.
- **Arranques.** Entran 41 de 332 grupos, con 11.723 fallos: 01_hasta_mediana, razón 0,7779 (0,7565 a 0,7997), 5.025 fallos; 02_hasta_doble, razón 1,1956 (1,1622 a 1,2296), 4.868 fallos; 03_mas_del_doble, razón 1,5359 (1,4663 a 1,6079), 1.830 fallos. Salen aparte 4.991 fallos y 11 no tienen tramo.
- **Datos escritos.** Entran 41 de 155 grupos, con 9.242 fallos: 01_bajo, razón 0,9307 (0,8969 a 0,9655), 2.856 fallos; 02_medio, razón 1,0927 (1,0561 a 1,1303), 3.365 fallos; 03_alto, razón 0,9764 (0,9419 a 1,0119), 3.021 fallos. Salen aparte 913 fallos y 6.570 no tienen tramo.
- **Datos leídos.** Entran 37 de 155 grupos, con 8.860 fallos: 01_bajo, razón 0,8372 (0,8045 a 0,8708), 2.475 fallos; 02_medio, razón 1,0221 (0,9860 a 1,0593), 3.015 fallos; 03_alto, razón 1,1408 (1,1026 a 1,1800), 3.370 fallos. Salen aparte 1.295 fallos y 6.570 no tienen tramo.

Se reparten 445.189.491 días de disco de 446.108.683; 16.725 fallos tienen su foto anterior y 271 no. 4 fallos, de 2 discos que fallan dos veces sin una foto nueva entre los dos fallos, toman la misma foto; cada fallo cuenta una vez.

Las comprobaciones de B8:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: sí.
- La referencia: sí.
- El azar en muchos grupos: sí.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: no aplica, porque los bloques 5 a 8 describen y no predicen.
- La cobertura: sí.
- Los periodos: sí.
- Del petición, en cada factor, los fallos de los tramos, de los grupos aparte y sin tramo suman los fallos con foto: sí.

## MC · Perfiles de riesgo y lo que falta en los datos

La tasa de todas las fotos, con el reparto de los días, es del 1,3712 % anual. Cada intervalo lleva el φ de la edad, 5,0189, medido en 2.543 celdas de modelo, año de edad y trimestre con 2.338 grados de libertad. Por valor de cada dimensión, con su lectura frente a la tasa de todas:

- fabricante: HGST, 1,2758 % (no se distingue); Seagate, 1,7615 % (por encima); Toshiba, 1,0719 % (por debajo); WDC, 0,5179 % (por debajo).
- capacidad_tb: 10, 3,7458 % (por encima); 12, 1,7200 % (por encima); 14, 1,1341 % (por debajo); 16, 0,8154 % (por debajo); 18, 3,8737 % (sin conclusión); 20, 0,6055 % (por debajo); 22, 0,7908 % (por debajo); 24, 1,6616 % (no se distingue); 4, 1,4642 % (no se distingue); 6, 0,3887 % (sin conclusión); 8, 2,0770 % (por encima).
- edad: 00_0, 0,7305 % (por debajo); 01_1, 0,8635 % (por debajo); 02_2, 1,2028 % (por debajo); 03_3, 1,5994 % (por encima); 04_4, 1,8863 % (por encima); 05_5, 2,5409 % (por encima); 06_6, 2,3735 % (por encima); 07_7, 2,4134 % (por encima); 08_8_o_mas, 1,6292 % (no se distingue).
- centro: ams5, 1,4230 % (no se distingue); antes_de_07_2023, 1,2566 % (por debajo); iad1, 0,9993 % (por debajo); phx1, 1,1882 % (por debajo); sac0, 1,7024 % (por encima); sac2, 2,0522 % (por encima); sin dato, 0,7374 % (por debajo); yyz1, 0,3362 % (sin conclusión).
- avisa: no, 0,4891 % (por debajo); sí, 14,9095 % (por encima).

Las celdas de tasa más alta de cada par de dimensiones, con 50.000 días o más y 20 fallos o más:

- fabricante y capacidad_tb: la primera es Seagate con 10, 3,8103 % (243 fallos).
- fabricante y edad: la primera es Toshiba con 06_6, 4,5823 % (37 fallos).
- fabricante y centro: la primera es HGST con sac2, 3,5727 % (1.100 fallos).
- fabricante y avisa: la primera es HGST con sí, 29,8443 % (1.853 fallos).
- capacidad_tb y edad: la primera es 10 con 05_5, 6,6210 % (73 fallos).
- capacidad_tb y centro: la primera es 10 con sac0, 4,8315 % (108 fallos).
- capacidad_tb y avisa: la primera es 14 con sí, 21,1108 % (1.650 fallos).
- edad y centro: la primera es 05_5 con sac2, 5,3930 % (597 fallos).
- edad y avisa: la primera es 00_0 con sí, 18,9368 % (607 fallos).
- centro y avisa: la primera es sac2 con sí, 23,8725 % (1.900 fallos).

Lo que falta en los datos:

- 2024T3: 60 de 1.389 fallos sin ranura el día del fallo, y 59 sin tomo después de tomarla del día anterior.
- 2024T4: 67 de 1.001 fallos sin ranura el día del fallo, y 40 sin tomo después de tomarla del día anterior.
- 2025T1: 861 de 1.067 fallos sin ranura el día del fallo, y 2 sin tomo después de tomarla del día anterior.
- 2025T2: 840 de 1.061 fallos sin ranura el día del fallo, y 2 sin tomo después de tomarla del día anterior.
- Las reglas dicen de 20 a 36 fallos sin ranura por trimestre, medido en el reconocimiento con otros datos; las cifras de los fallos sin tomo no coinciden con ese rango.
- 71.328 discos desaparecen sin fallo; 8.362 fallos son anteriores al 01/07/2023 y no tienen sitio; 344.969 fotos traen el contador 90, cuyo significado no se conoce.

Las comprobaciones de MC:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: sí.
- La referencia: sí.
- El azar en muchos grupos: sí.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: no aplica, porque los bloques 5 a 8 describen y no predicen.
- La cobertura: sí.
- Los periodos: sí.
- Del petición, cada φ usado es el medido y, si sale menor que 1, vale 1: sí.

## Lo que no saca conclusión

- B5, yyz1: 6 casos.
- B8, temperatura: grupos que no llegan a 20 fallos en sus tres tramos: 514 casos.
- B8, arranques: grupos que no llegan a 20 fallos en sus tres tramos: 4.991 casos.
- B8, escritos: grupos que no llegan a 20 fallos en sus tres tramos: 913 casos.
- B8, leidos: grupos que no llegan a 20 fallos en sus tres tramos: 1.295 casos.
- MC, capacidad_tb 18: 11 casos.
- MC, capacidad_tb 6: 15 casos.
- MC, centro yyz1: 6 casos.

## Validaciones

| Validación | Resultado |
|---|---|
| Cada pregunta tiene su planteamiento completo | sí |
| Cada cifra dice su población, sus filas y su periodo | sí |
| Cada cifra tiene su segunda vía, y coinciden | sí |
| Ninguna conclusión sale de un grupo por debajo del mínimo | sí |
| Cada resultado lleva su referencia, con las mismas filas | sí |
| Las comprobaciones tienen su resultado o su motivo | sí |
| Dos cálculos seguidos dan las mismas cifras | sí |
| El script no lleva ningún resultado escrito a mano | sí |
| Los ficheros de data/raw/ no cambian | sí |
| Ni el JSON ni este informe llevan la palabra vetada para el conjunto de discos | sí |

Las segundas vías:

| Cifra | Primera vía | Segunda vía | Comparación | Coinciden |
|---|---|---|---|---|
| días de disco por centro desde 07/2023 | centro_mes | recuento_diario_corregido | exacta, 7 claves, diferencia mayor 0 | sí |
| fallos por centro desde 07/2023 | centro_mes | recuento_diario_corregido | exacta, 7 claves, diferencia mayor 0 | sí |
| días de disco por centro: dias_por_tramo más los días sin foto | dias_por_tramo + días de las celdas del recuento sin foto | recuento_diario_corregido | diferencia menor que 1e-06, 7 claves, diferencia mayor 0 | sí |
| fallos por centro: dias_por_tramo | dias_por_tramo | recuento_diario_corregido | exacta, 7 claves, diferencia mayor 0 | sí |
| suma de los esperados de todos los centros | esperados (tasa de cada modelo, edad y trimestre) | observados de las celdas con días | diferencia menor que 1e-06, 1 claves, diferencia mayor 0 | sí |
| fotos que avisan por mes | columna avisa de fotos_riesgo | los cinco contadores por encima de cero, sin contar los vacíos | exacta, 66 claves, diferencia mayor 0 | sí |
| fotos que fallan en 90 días, por grupo de aviso | unión de fotos y fallos | búsqueda en la lista ordenada de fallos | exacta, 7 claves, diferencia mayor 0 | sí |
| fotos que fallan en 90 días, por grupo de aviso, Seagate | unión de fotos y fallos | búsqueda en la lista ordenada de fallos | exacta, 7 claves, diferencia mayor 0 | sí |
| fotos de Seagate con el 197 y el 198 a la vez | máscaras de los dos contadores | intersección de los índices de las fotos | exacta, 1 claves, diferencia mayor 0 | sí |
| fallos sin aviso por año | agrupación de fallos_detalle por año | recuento en bucle sobre las filas de fallos_detalle | exacta, 18 claves, diferencia mayor 0 | sí |
| fallos con tomo, tomos y coincidencias | columnas tomo y coincide_con_anterior de fallos_detalle | recuento propio en bucle con centro, vault y ranura | exacta, 3 claves, diferencia mayor 0 | sí |
| fallos con su foto | unión con fotos_riesgo por disco y mes | fallos_detalle con ultima_foto_anterior | exacta, 1 claves, diferencia mayor 0 | sí |
| días repartidos por las fotos | suma de los pesos de las fotos | recuento menos los días de las celdas sin foto | diferencia menor que 1e-06, 1 claves, diferencia mayor 0 | sí |
| fallos por dimensión del minicubo | minicubo, con la foto de cada fallo | fallos_detalle con ultima_foto_anterior | exacta, 5 claves, diferencia mayor 0 | sí |
| días por dimensión del minicubo | minicubo, con el reparto de las fotos | recuento menos los días sin foto | diferencia menor que 1e-06, 5 claves, diferencia mayor 0 | sí |

## Parámetros usados

- mínimo de días de disco al año de un centro, un valor o una celda: 50.000 (reglas-negocio §7; en un centro, sobre los dos años del sitio (100.000 días)).
- mínimo de fallos de un centro, un tramo, un valor o una celda: 20 (petición, criterios 8 y 9 y comprobación 1 (yyz1 sin conclusión); reglas, apartado 7, cuestión 009).
- mínimo de fotos de un grupo de aviso: 30 (parametros.md de el método).
- tasa ajustada por centro: estandarización indirecta con la tasa de cada modelo, año de edad y trimestre de todos los centros, «sin dato» incluido (criterio técnico 1, en la petición 15; el trimestre, petición 19).
- φ de B5: chi2 de Pearson / grados de libertad en las celdas centro × trimestre de los centros que constan, con los esperados reescalados para que cada centro sume sus fallos; si sale menor que 1, vale 1 (criterio técnico (reglas, apartado 7), petición 19).
- φ de B6: binomial por grupo de aviso, en las celdas del trimestre de la foto: suma de (fallan − n·p)² / (n·p·(1 − p)) entre celdas − 1; si sale menor que 1, vale 1 (criterio técnico (reglas, apartado 7), petición 19).
- φ del minicubo: el de B3 del 09, calculado igual: celdas modelo × año de edad × trimestre de dias_por_tramo con la tasa de su modelo y año de edad (criterio técnico (reglas, apartado 7), petición 19).
- intervalo con φ: exacto de Poisson con observados y esperados (o fallos y días) entre φ; Clopper-Pearson con fallan/φ y fotos/φ en el desenlace (petición 19).
- desenlace a 90 días: falla, desaparece o sigue, por foto (criterio técnico 2).
- tomos con k fallos en d días: k = 2, 3 y 4; d = 7 y 30 (criterio técnico 3).
- azar de los tomos: 200 repeticiones, semilla 68, días barajados dentro de cada centro y trimestre del fallo, y al lado dentro de cada centro; media y percentil 95 (interpolación lineal de numpy) (criterio técnico 4; el trimestre, petición 19).
- discos a la vez: fallos anteriores del tomo con día + plazo posterior al día del fallo, más uno; paridad supuesta 3, 4 y 5 (criterio técnico 5; reglas, apartado 4).
- riesgo vivo: binomial de 2 o más y de 3 o más con los discos del tomo y la proporción del mes (criterio técnico 6).
- reparto de los días: días de la celda de modelo, mes y centro entre sus fotos (criterio técnico 7).
- tramos del bloque 8: temperatura ±3 °C de la mediana del modelo; arranques 1 y 2 veces la mediana de modelo y edad; escritos y leídos por tercios (criterio técnico 8, aprobado por el responsable del caso el 18/11/2026).
- minicubo: cinco dimensiones, tasa por el reparto, diez celdas por par en el nivel 2 (criterio técnico 9; assets/23_metodo_minicubo.md).
- confianza de los intervalos: 0,95 (parametros.md de el método y 42.6 del manual).
- tolerancia de las segundas vías en días repartidos: 1e-06 (petición, «SEGUNDA VÍA»).
- semilla: 68 (petición, criterio 4).

Apartados del manual aplicados:

- 42.1: elegir la función por la pregunta: grupos frente a una referencia en B5, B6 y B8, el minicubo en MC y una comparación con el azar en B7.
- 38.1: el objetivo de negocio, reducir costes y alargar la vida útil, da la decisión de cada bloque.
- 42.6: cada grupo con su intervalo y cuántos saldrían distintos solo por azar.
- 13.13 y assets/23_metodo_minicubo.md: el minicubo de cinco dimensiones, con el recuento de cada valor y el nivel 2.
- 13.6 y 13.7: consultas agrupadas por centro y trimestre, por mes, por modelo y por tramo.
- 5.5: cada tasa es suma de fallos entre suma de días, con su base, nunca la media de las tasas.
- 5.6: la tasa bruta de un centro mezcla modelos y edades; la ajustada compara con la misma mezcla.
- 4.5 y 4.7: intervalo al 95 %; el mínimo de casos lo fijan las reglas del caso.
- 4.11 y 4.12: las tasas no se contrastan como dos proporciones: van con el intervalo exacto de Poisson; el desenlace por aviso, con el exacto de Clopper-Pearson; los dos, ensanchados por φ (petición 19).

## Datos personales

- No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección, porque no traen datos de personas.
- No hay datos de personas (reglas-negocio §9): el número de serie identifica un disco, no a una persona.
- Este cálculo usa el número de serie solo para unir fotos, fallos y ventanas. No deja ninguno en el JSON ni en el informe.

## Límites

- Las cifras describen el periodo de trabajo. Ninguna dice por qué un centro, un aviso o un tramo falla más: solo valen verbos de asociación.
- El centro y el tomo solo constan desde el 01/07/2023; lo anterior no se rellena. El centro «sin dato» y los fallos sin tomo van aparte, con su recuento.
- Un centro que falla más con la misma mezcla de modelo y edad puede deberse a lo que no está en los datos, como su operación o sus retiradas: no se puede saber.
- El aviso es acumulado y casi nunca vuelve a cero, así que el desenlace a 90 días cuenta fotos, no discos, y el riesgo vivo se compara con el azar.
- La ventana da 16.093 fallos con día anterior y 4.046 sin aviso; fallos_detalle da 16.093 y 4.046. Se dan las de fallos_detalle, que son las de las reglas.
- Los contadores 187 y 188 solo los traen los Seagate, y los datos escritos y leídos solo se miden en Seagate: el porcentaje que avisa no se compara entre fabricantes.
- La paridad de cada vault no está en los datos: se usa la supuesta de las reglas, apartado 4. El tiempo de reconstrucción es la regla de Backblaze, un día por TB más uno.
- La tasa del minicubo usa los días repartidos por las fotos, que dejan fuera los días de las celdas sin foto: la del recuento por fabricante y capacidad va al lado, con su diferencia.
- Las reglas, apartado 5 dicen de 20 a 36 fallos sin ranura por trimestre, medido en el reconocimiento con otros datos; las cifras de fallos_detalle no coinciden con ese rango.
- Según lo medido al preparar la petición 15, la temperatura de un disco casi no cambia de un mes a otro: el tramo dice cómo de caliente trabaja ese disco respecto a su modelo, no un mes caluroso.
- La tasa ajustada compara modelos presentes en varios centros: 21 modelos pasan el mínimo de días en dos centros o más.
- Los intervalos de B5, B6 y el minicubo llevan φ: 1,0196 en B5 y 5,0189 en el minicubo; en B6, uno por grupo. φ mide la variación entre trimestres y no la que pueda haber dentro de un trimestre.
- El último año de los datos, 2025, llega hasta el 30/06: su «sin aviso» por año va marcado como incompleto.
- Ninguna cifra se ha medido en la reserva, del 01/07/2025 al 30/06/2026 (reglas, apartado 5).
- Pendiente: el auditor sin memoria del cierre del paso (método §8) necesita el sí del responsable del caso, porque es un agente.

