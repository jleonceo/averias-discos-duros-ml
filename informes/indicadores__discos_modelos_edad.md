# Indicadores de los discos por modelo y edad

Caso 68, paso 5, bloques 1 a 3 del plan de la analítica. Datos hasta el 30/06/2025; ejecutado el 18/11/2026. Estado: **AVISO**, riesgo medio.

Tres bloques calculados con 85 cifras, todas con su segunda vía, y las nueve validaciones en verde. B2 compara cada modelo a igual edad y en los mismos trimestres, con φ en el intervalo, y ordena el ranking por la razón (peticiones 17 y 19). Sin conclusión por el mínimo: 147 años de modelo (29 modelos sin ningún año en el ranking), 5 modelos con menos de 20 fallos sin puesto (cuestión 012), 20 años de edad de algún grupo con menos de 20 fallos y 7 curvas de supervivencia cortadas; contar a los que desaparecen avisando cambia la lectura en los años de edad 1, 4 y 8.

## Las preguntas y su planteamiento

Las tres preguntas salen del plan de la analítica, aprobado por el responsable del caso el 16/11/2026, y del planteamiento 1.A. La población es la misma en las tres: los discos de datos, sin los de arranque, del 01/01/2020 al 30/06/2025. La tasa anual de fallo es 100 × 365 × fallos / días de disco, siempre con sus fallos y sus días.

- **B1.** Qué discos de datos tiene Backblaze, cuánta capacidad suman y cómo ha cambiado el conjunto de discos de enero de 2020 a junio de 2025: altas, bajas, modelos principales y centros.
  - Decisión que apoya: ninguna por sí sola; da los discos y los días de disco sobre los que se leen el ranking de B2 y la edad de B3, que son los que deciden compras y renovaciones.
  - Medida: discos el día 1 de cada mes y capacidad = discos × capacidad del modelo / 1.000, en PB; altas = discos con su primera aparición en el trimestre; bajas = fallos y discos que desaparecen sin fallo; discos medios del año = días de disco / días del año en los datos; parte de cada centro en los días del año.
  - Mínimo: 50.000 días de disco en el año para entrar entre los diez de cada año (reglas, apartado 7).
  - Referencia: el total del conjunto de discos de cada mes y de cada año, frente al que se leen las partes por capacidad, fabricante y centro.
- **B2.** Qué modelos de disco fallan más, por tasa anual de fallo, y si el ranking se mantiene de un año a otro.
  - Decisión que apoya: qué modelos comprar y cuáles evitar, porque es la base de la decisión de compra (plan, bloque 2).
  - Medida: tasa anual de fallo = 100 × 365 × fallos / días de disco (reglas, apartado 6), con su intervalo exacto de Poisson al 95 %; a igual edad, razón = fallos observados / esperados con la tasa de cada año de edad, con el intervalo de Poisson de los observados, y tasa a igual edad = razón × tasa de todas las celdas.
  - Mínimo: 50.000 días de disco del modelo en el año, y 20 fallos en sus años que pasan el mínimo para llevar puesto y sacar conclusión (reglas, apartado 7, cuestión 012).
  - Referencia: razón 1: los fallos que tendría el modelo con la tasa de cada año de edad de todos los modelos del ranking juntos, en sus mismas celdas; la tasa de todas esas celdas.
- **B3.** A qué edad empiezan a fallar los discos y qué parte sigue funcionando a los 1, 3 y 5 años.
  - Decisión que apoya: cuándo renovar, por el año de vida en que sube el riesgo de cada modelo (plan, bloque 3).
  - Medida: tasa anual por año de edad (0 a 10) desde dias_por_tramo; supervivencia S(k) = exp(−suma de las tasas de los años 0 a k − 1), con la tasa de cada año = primeros fallos / años de exposición de vida_discos.
  - Mínimo: 20 fallos en el año de edad (reglas, apartado 7, cuestión 009).
  - Referencia: el año de edad anterior del mismo grupo (para «sube») y la tasa del conjunto de discos a la misma edad (para fabricantes y modelos), calculada con las mismas filas de dias_por_tramo.

La teoría del manual que se aplicó:

- 42.1: elegir la función por la pregunta; B1 no tiene función y va con consultas.
- 38.1: el objetivo de negocio: reducir costes y alargar la vida útil.
- 42.6: grupos frente al conjunto de discos con intervalo y cuántos saldrían por azar (B2).
- 4.2: los fallos por días de disco siguen una Poisson: de ahí el intervalo exacto.
- 4.5: confianza del 95 % de todos los intervalos.
- 4.7: el mínimo de casos no lo fija el manual: lo fijan las reglas del caso.
- 4.11 y 4.12: se compara una tasa con otra por intervalos, no con una z de proporciones.
- 11.10: ranking con empates por el método «min».
- 13.6 y 13.7: consultas agrupadas y conteos de B1.
- 5.5: tasa de un grupo = suma de fallos / suma de días; cada tasa con su base.
- 5.6: Simpson: fabricante y capacidad mezclan edades, con la edad media al lado; cada modelo se compara a igual edad por estandarización indirecta.
- assets/18_consultas_interactivas.md §8, §9, §11, §13, §14 y §18: top N, framework agrupado, filtro por mínimo, tabla cruzada, tabla dinámica y el grano.

## B1 · Cómo es y cómo ha cambiado el conjunto de discos

El conjunto de discos de datos pasó de 122.696 discos y 1.090,9 PB el 01/01/2020 a 314.758 discos y 4.790,1 PB el 01/06/2025. La serie de los 66 meses, por capacidad y por fabricante, está en el JSON para el gráfico de áreas.

Entre los 402.643 discos que salen en los datos, 16.984 acaban en un fallo, 71.328 desaparecen sin fallo y 314.331 siguen en la última foto. El primer trimestre de 2020 no da altas: sus 126.605 discos incluyen todos los que ya estaban antes.

| Trimestre | Altas | Fallos | Desaparecen sin fallo |
|---|---:|---:|---:|
| 2020T1 | no se da | 336 | 3 |
| 2020T2 | 11.418 | 272 | 2.092 |
| 2020T3 | 15.996 | 327 | 6.026 |
| 2020T4 | 19.588 | 372 | 5.779 |
| 2021T1 | 15.675 | 350 | 9.454 |
| 2021T2 | 20.676 | 441 | 10.009 |
| 2021T3 | 16.224 | 510 | 2.045 |
| 2021T4 | 8.432 | 522 | 176 |
| 2022T1 | 12.371 | 618 | 9 |
| 2022T2 | 5.376 | 763 | 18 |
| 2022T3 | 11.579 | 916 | 16 |
| 2022T4 | 9.004 | 702 | 20 |
| 2023T1 | 6.709 | 892 | 84 |
| 2023T2 | 6.302 | 1.341 | 932 |
| 2023T3 | 17.781 | 943 | 4.477 |
| 2023T4 | 18.378 | 1.025 | 5.295 |
| 2024T1 | 11.768 | 949 | 6.230 |
| 2024T2 | 18.965 | 1.199 | 5.334 |
| 2024T3 | 9.744 | 1.389 | 7.024 |
| 2024T4 | 11.689 | 1.001 | 1.846 |
| 2025T1 | 17.053 | 1.067 | 4.206 |
| 2025T2 | 11.310 | 1.061 | 253 (incompleto) |

Los fallos de la tabla son todos los fallos (16.996); 12 son el segundo fallo de un disco que volvió.

El modelo con más discos de cada año, en discos medios (días de disco del año entre los días del año en los datos):

- 2020: ST12000NM0007, 32.643 discos medios; con días de disco de 2020T1 a 2025T2.
- 2021: TOSHIBA MG07ACA14TA, 31.830 discos medios; con días de disco de 2020T1 a 2025T2.
- 2022: TOSHIBA MG07ACA14TA, 38.141 discos medios; con días de disco de 2020T1 a 2025T2.
- 2023: TOSHIBA MG07ACA14TA, 37.912 discos medios; con días de disco de 2020T1 a 2025T2.
- 2024: TOSHIBA MG08ACA16TA, 38.497 discos medios; con días de disco de 2020T1 a 2025T2.
- 2025, con 181 días: TOSHIBA MG08ACA16TA, 40.146 discos medios; con días de disco de 2020T1 a 2025T2.

Los diez de cada año, con su primer y su último trimestre, están en el JSON. Un primer trimestre 2020T1 quiere decir que el modelo ya estaba antes de los datos, y un último 2025T2, que sigue.

Reparto de los días de disco por centro desde julio de 2023, cuando el centro empieza a constar:

| Centro | 2023 (parcial) | 2024 | 2025 (parcial) |
|---|---:|---:|---:|
| ams5 | 2.407.143 (5,1 %) | 5.824.408 (5,6 %) | 3.879.504 (6,9 %) |
| iad1 | 2.475.498 (5,2 %) | 8.478.792 (8,2 %) | 7.053.189 (12,6 %) |
| phx1 | 15.171.255 (31,9 %) | 32.742.589 (31,5 %) | 17.809.861 (31,9 %) |
| sac0 | 16.046.441 (33,7 %) | 29.018.756 (27,9 %) | 14.052.555 (25,1 %) |
| sac2 | 10.584.306 (22,2 %) | 22.044.267 (21,2 %) | 12.436.195 (22,3 %) |
| yyz1 | sin días | sin días | 651.306 (1,2 %) |
| sin dato | 890.329 (1,9 %) | 5.730.884 (5,5 %) | sin días |

Las comprobaciones de B1:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: sí.
- La referencia: sí.
- El azar en muchos grupos: no aplica, porque B1 cuenta discos y días de disco; no compara tasas de grupos con el total.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: no aplica, porque B1 describe el conjunto de discos; no predice nada que se pueda medir en el periodo siguiente.
- La cobertura: sí.
- Los periodos: sí.

## B2 · Qué modelos fallan más

De los 299 años de modelo con días de disco, 152 pasan el mínimo de 50.000 días, de 32 modelos. Con esos años, la tasa bruta va del 0,33 % del HGST HMS5C4040BLE640 al 5,90 % del ST14000NM0138.

Cada modelo se compara a igual edad y en los mismos trimestres (reglas, apartado 7): sus fallos frente a los que tendría con la tasa de cada año de edad y trimestre de todos los modelos del ranking juntos. La razón entre los dos dice cuánto falla por encima o por debajo de lo esperado a su edad, y el ranking se ordena por ella. 27 modelos tienen 20 fallos o más y llevan puesto; 5 no llegan y salen con su tasa, sin puesto y sin conclusión (cuestión 012).

Los fallos de un modelo varían de un trimestre a otro más de lo que supone el intervalo de Poisson. Esa variación de más, φ, vale 3,3668 (medida en 536 celdas de modelo y trimestre, con 504 grados de libertad), y cada intervalo de la razón la lleva dentro: observados y esperados entre φ. La razón no cambia; el intervalo se ensancha.

Frente a la comparación de antes, solo a igual edad y sin φ, cambian de veredicto 3 modelos: WDC WUH721816ALE6L0 (de por debajo a no se distingue), HGST HUH721212ALN604 (de por encima a no se distingue) y ST8000DM002 (de por debajo a por encima). La correlación de orden de Spearman entre las dos razones es de 0,9516.

La comparación usa 443.929.499 días de disco y 16.895 fallos, con una tasa del 1,3891 %. Son 897.016 días menos que los del ranking (444.826.515), porque la tabla por año de edad deja fuera los días sin foto.

A igual edad, 13 modelos fallan por encima de lo esperado, 9 por debajo y 5 no se distinguen. Solo por azar saldrían distintos unos 1,4 de los 27, y salen 22.

Con la tasa bruta, el conjunto de discos de las mismas celdas falla al 1,39 % (16.895 fallos en 444.826.515 días de disco). 10 modelos cambian de lectura entre esa comparación y la de igual edad. Las dos difieren por la edad media de cada modelo: la tasa bruta de un modelo joven se compara con discos más viejos, que fallan más, y la de uno viejo con discos más jóvenes.

- HGST HUH728080ALE600: edad media 4,53 años; con la tasa bruta, no se distingue; a igual edad, por debajo.
- WDC WUH721816ALE6L0: edad media 1,82 años; con la tasa bruta, por debajo; a igual edad, no se distingue.
- TOSHIBA MG10ACA20TE: edad media 0,50 años; con la tasa bruta, por debajo; a igual edad, no se distingue.
- HGST HUH721212ALN604: edad media 3,37 años; con la tasa bruta, por encima; a igual edad, no se distingue.
- WDC WUH722222ALE6L4: edad media 0,63 años; con la tasa bruta, por debajo; a igual edad, no se distingue.
- ST14000NM001G: edad media 2,17 años; con la tasa bruta, no se distingue; a igual edad, por encima.
- TOSHIBA MG08ACA16TEY: edad media 1,85 años; con la tasa bruta, no se distingue; a igual edad, por encima.
- TOSHIBA MG08ACA16TA: edad media 1,25 años; con la tasa bruta, por debajo; a igual edad, por encima.
- TOSHIBA MG08ACA16TE: edad media 1,88 años; con la tasa bruta, no se distingue; a igual edad, por encima.
- ST24000NM002H: edad media 0,50 años; con la tasa bruta, no se distingue; a igual edad, por encima.

| Puesto | Modelo | Días de disco | Fallos | Edad media | Tasa bruta | Razón (intervalo al 95 %) | Tasa a igual edad | A igual edad | Bruta frente al conjunto |
|---:|---|---:|---:|---:|---:|---|---:|---|---|
| 1 | HGST HMS5C4040BLE640 | 21.590.966 | 193 | 5,49 | 0,33 % | 0,2034 (0,1542 a 0,2634) | 0,28 % | por debajo | por debajo |
| 2 | HGST HUH721212ALE600 | 5.074.561 | 78 | 3,01 | 0,56 % | 0,2644 (0,1679 a 0,3962) | 0,37 % | por debajo | por debajo |
| 3 | HGST HMS5C4040ALE640 | 5.104.016 | 88 | 5,67 | 0,63 % | 0,3909 (0,2557 a 0,5723) | 0,54 % | por debajo | por debajo |
| 4 | WDC WUH721414ALE6L4 | 13.978.204 | 190 | 2,26 | 0,50 % | 0,4319 (0,3266 a 0,5603) | 0,60 % | por debajo | por debajo |
| 5 | WDC WUH721816ALE6L4 | 21.131.309 | 214 | 1,26 | 0,37 % | 0,4558 (0,3507 a 0,5826) | 0,63 % | por debajo | por debajo |
| 6 | HGST HUH728080ALE600 | 2.175.081 | 76 | 4,53 | 1,28 % | 0,6407 (0,4042 a 0,9650) | 0,89 % | por debajo | no se distingue |
| 7 | TOSHIBA MG07ACA14TA | 64.132.410 | 1.811 | 2,36 | 1,03 % | 0,7576 (0,6949 a 0,8244) | 1,05 % | por debajo | por debajo |
| 8 | ST16000NM001G | 34.669.630 | 683 | 1,66 | 0,72 % | 0,7929 (0,6875 a 0,9098) | 1,10 % | por debajo | por debajo |
| 9 | ST12000NM001G | 21.487.178 | 584 | 2,25 | 0,99 % | 0,7945 (0,6806 a 0,9219) | 1,10 % | por debajo | por debajo |
| 10 | WDC WUH721816ALE6L0 | 3.848.250 | 78 | 1,82 | 0,74 % | 0,8074 (0,5128 a 1,2098) | 1,12 % | no se distingue | por debajo |
| 11 | TOSHIBA MG10ACA20TE | 2.469.154 | 46 | 0,50 | 0,68 % | 0,8759 (0,4748 a 1,4788) | 1,22 % | no se distingue | por debajo |
| 12 | HGST HUH721212ALN604 | 21.311.976 | 1.367 | 3,37 | 2,34 % | 0,9666 (0,8748 a 1,0653) | 1,34 % | no se distingue | por encima |
| 13 | WDC WUH722222ALE6L4 | 10.978.372 | 243 | 0,63 | 0,81 % | 1,0311 (0,8071 a 1,2982) | 1,43 % | no se distingue | por debajo |
| 14 | ST12000NM0008 | 37.582.572 | 2.084 | 2,59 | 2,02 % | 1,1123 (1,0264 a 1,2035) | 1,55 % | por encima | por encima |
| 15 | ST8000DM002 | 19.043.449 | 937 | 5,87 | 1,80 % | 1,1514 (1,0201 a 1,2949) | 1,60 % | por encima | por encima |
| 16 | ST8000NM0055 | 28.364.773 | 1.819 | 4,99 | 2,34 % | 1,2375 (1,1353 a 1,3463) | 1,72 % | por encima | por encima |
| 17 | ST4000DM000 | 27.930.661 | 1.942 | 6,17 | 2,54 % | 1,2712 (1,1696 a 1,3793) | 1,77 % | por encima | por encima |
| 18 | ST14000NM001G | 17.140.132 | 663 | 2,17 | 1,41 % | 1,2717 (1,1003 a 1,4623) | 1,77 % | por encima | no se distingue |
| 19 | TOSHIBA MG08ACA16TEY | 6.654.440 | 227 | 1,85 | 1,25 % | 1,3178 (1,0222 a 1,6724) | 1,83 % | por encima | no se distingue |
| 20 | TOSHIBA MG08ACA16TA | 26.976.653 | 852 | 1,25 | 1,15 % | 1,3860 (1,2205 a 1,5677) | 1,93 % | por encima | por debajo |
| 21 | TOSHIBA MG07ACA14TEY | 969.253 | 39 | 1,99 | 1,47 % | 1,3870 (0,7069 a 2,4463) | 1,93 % | no se distingue | no se distingue |
| 22 | TOSHIBA MG08ACA16TE | 7.868.882 | 279 | 1,88 | 1,29 % | 1,4389 (1,1458 a 1,7840) | 2,00 % | por encima | no se distingue |
| 23 | HGST HUH721212ALE604 | 20.386.683 | 878 | 2,10 | 1,57 % | 1,4622 (1,2901 a 1,6509) | 2,03 % | por encima | por encima |
| 24 | ST12000NM0007 | 16.241.695 | 813 | 2,22 | 1,83 % | 1,6532 (1,4512 a 1,8754) | 2,30 % | por encima | por encima |
| 25 | ST10000NM0086 | 2.293.552 | 243 | 4,76 | 3,87 % | 1,9905 (1,5580 a 2,5061) | 2,77 % | por encima | por encima |
| 26 | ST24000NM002H | 663.057 | 35 | 0,50 | 1,93 % | 2,4516 (1,1954 a 4,4578) | 3,41 % | por encima | no se distingue |
| 27 | ST14000NM0138 | 2.417.642 | 391 | 2,21 | 5,90 % | 5,1950 (4,2932 a 6,2302) | 7,22 % | por encima | por encima |
| sin puesto | ST6000DX000 | 1.389.650 | 15 | 6,63 | 0,39 % | 0,2090 (0,0622 a 0,5112) | 0,29 % | sin conclusión | por debajo |
| sin puesto | ST8000NM000A | 139.294 | 2 | 1,35 | 0,52 % | 0,5562 (0,0016 a 4,5393) | 0,77 % | sin conclusión | no se distingue |
| sin puesto | ST16000NM002J | 425.347 | 6 | 1,40 | 0,51 % | 0,6762 (0,0676 a 2,6089) | 0,94 % | sin conclusión | por debajo |
| sin puesto | ST14000NM000J | 55.394 | 2 | 0,59 | 1,32 % | 1,5390 (0,0043 a 12,5607) | 2,14 % | sin conclusión | no se distingue |
| sin puesto | ST12000NM000J | 332.279 | 17 | 0,70 | 1,87 % | 2,3179 (0,7579 a 5,3882) | 3,22 % | sin conclusión | no se distingue |

La correlación de orden de Spearman entre la tasa bruta y la razón es de 0,813 con todos los modelos y de 0,781 con los que llevan puesto.

Si se quita cada modelo uno a uno y se rehacen las tasas por año de edad sin él, 11 de las 32 retiradas cambian el veredicto de algún otro modelo, como mucho 4 (al quitar el TOSHIBA MG07ACA14TA). Sin 2025, el año parcial, cambian 4: HGST HUH728080ALE600, ST24000NM002H, TOSHIBA MG08ACA16TEY y TOSHIBA MG10ACA20TE.

Lo que no llega al mínimo se da aparte: 147 años de modelo con 1.282.168 días de disco y 101 fallos; 29 modelos no llegan ningún año. La tabla de modelo por año, con la tasa de cada celda que pasa y el recuento de las que no, está en el JSON para el mapa de calor.

Por fabricante y por capacidad entran todos los discos de datos, y todos los discos juntos fallan al 1,39 % (16.996 fallos en 446.108.683 días de disco). Cada grupo mezcla modelos de edades distintas, y por eso va con la edad media de sus días de disco al lado.

| Fabricante | Días de disco | Fallos | Tasa | Intervalo al 95 % | Edad media | Frente al conjunto de discos |
|---|---:|---:|---:|---|---:|---|
| HGST | 75.939.245 | 2.702 | 1,30 % | 1,25 % a 1,35 % | 3,8 años | por debajo |
| Seagate | 210.816.183 | 10.284 | 1,78 % | 1,75 % a 1,82 % | 3,5 años | por encima |
| Toshiba | 109.368.087 | 3.279 | 1,09 % | 1,06 % a 1,13 % | 2,0 años | por debajo |
| WDC | 49.985.168 | 731 | 0,53 % | 0,50 % a 0,57 % | 1,4 años | por debajo |

| Capacidad | Días de disco | Fallos | Tasa | Intervalo al 95 % | Edad media | Frente al conjunto de discos |
|---|---:|---:|---:|---|---:|---|
| 4 TB | 54.965.690 | 2.238 | 1,49 % | 1,43 % a 1,55 % | 5,9 años | por encima |
| 6 TB | 1.408.490 | 15 | 0,39 % | 0,22 % a 0,64 % | 6,6 años | por debajo |
| 8 TB | 50.048.476 | 2.870 | 2,09 % | 2,02 % a 2,17 % | 5,3 años | por encima |
| 10 TB | 2.367.914 | 245 | 3,78 % | 3,32 % a 4,28 % | 4,7 años | por encima |
| 12 TB | 122.453.793 | 5.825 | 1,74 % | 1,69 % a 1,78 % | 2,5 años | por encima |
| 14 TB | 98.833.167 | 3.114 | 1,15 % | 1,11 % a 1,19 % | 2,3 años | por debajo |
| 16 TB | 101.798.391 | 2.354 | 0,84 % | 0,81 % a 0,88 % | 1,5 años | por debajo |
| 18 TB | 103.947 | 11 | 3,86 % | 1,93 % a 6,91 % | 2,3 años | por encima |
| 20 TB | 2.469.386 | 46 | 0,68 % | 0,50 % a 0,91 % | 0,5 años | por debajo |
| 22 TB | 10.978.372 | 243 | 0,81 % | 0,71 % a 0,92 % | 0,6 años | por debajo |
| 24 TB | 681.057 | 35 | 1,88 % | 1,31 % a 2,61 % | 0,5 años | no se distingue |

Las comprobaciones de B2:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: sí.
- La referencia: sí.
- El azar en muchos grupos: sí.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: no aplica, porque la tasa describe el periodo; si un modelo malo lo sigue siendo después se mide en la reserva, que no se mira (reglas, apartado 5).
- La cobertura: sí.
- Los periodos: sí.
- Del petición, el veredicto a igual edad de cada modelo es el que dice el intervalo de su razón: sí.
- Del petición, los fallos esperados de todos los modelos suman los observados, como tiene que pasar por cómo se calculan (no es una segunda vía): sí.
- Del petición, el φ usado es el medido y nunca menor que 1: sí.

## B3 · A qué edad empiezan a fallar

La tasa del conjunto de discos va del 0,79 % con 0 años cumplidos al 2,58 % con 5. Sube frente al año anterior, con intervalos que no se solapan, en los años de edad 2, 3, 4 y 5.

Cada intervalo de esta parte lleva φ = 5,02, lo que varían los fallos de un modelo y año de edad de un trimestre a otro más de lo que supone Poisson (medido en 2.543 celdas, con 2.338 grados de libertad). Fallos y días se dividen entre φ: la tasa no cambia y el intervalo se ensancha.

Al lado va la misma tasa contando como fallo a los discos que desaparecen avisando, porque desaparecen más viejos y avisando más que el conjunto de discos (reglas, apartado 3).

| Edad | Días de disco | Fallos | Tasa | Intervalo al 95 % | Frente al año anterior | Contando los que desaparecen avisando |
|---:|---:|---:|---:|---|---|---:|
| 0 | 93.340.444 | 2.021 | 0,79 % | 0,71 % a 0,87 % | primer año | 0,83 % (primer año) |
| 1 | 87.628.780 | 2.064 | 0,86 % | 0,78 % a 0,95 % | no se distingue | 1,08 % (sube) |
| 2 | 75.893.932 | 2.502 | 1,20 % | 1,10 % a 1,31 % | sube | 2,14 % (sube) |
| 3 | 63.943.476 | 2.793 | 1,59 % | 1,46 % a 1,73 % | sube | 2,54 % (sube) |
| 4 | 47.330.285 | 2.491 | 1,92 % | 1,76 % a 2,10 % | sube | 1,97 % (baja) |
| 5 | 29.980.005 | 2.122 | 2,58 % | 2,34 % a 2,84 % | sube | 2,69 % (sube) |
| 6 | 22.283.007 | 1.462 | 2,39 % | 2,13 % a 2,69 % | no se distingue | 2,59 % (no se distingue) |
| 7 | 18.269.950 | 1.207 | 2,41 % | 2,12 % a 2,74 % | no se distingue | 2,88 % (no se distingue) |
| 8 | 6.421.014 | 334 | 1,90 % | 1,47 % a 2,41 % | no se distingue | 12,02 % (sube) |
| 9 | 96.647 | 0 | 0,00 % | 0,00 % a 6,99 % | sin conclusión | 4,53 % (sin conclusión) |
| 10 | 1.951 | 0 | 0,00 % | 0,00 % a 346,35 % | sin conclusión | 0,00 % (sin conclusión) |

Las dos cuentas dan una lectura distinta frente al año anterior en los años de edad 1, 4 y 8.

Por fabricante, tasa por año de edad («s. c.»: menos de 20 fallos, sin conclusión; «↑»: sube frente al año anterior):

| Edad | HGST | Seagate | Toshiba | WDC |
|---:|---:|---:|---:|---:|
| 0 | 0,78 % | 0,94 % | 0,80 % | 0,57 % |
| 1 | 0,47 % | 1,03 % | 1,06 % | 0,27 % |
| 2 | 0,73 % | 1,52 % ↑ | 1,12 % | 0,64 % ↑ |
| 3 | 1,75 % ↑ | 1,84 % | 1,15 % | 0,97 % |
| 4 | 2,01 % | 2,03 % | 1,65 % | 0,83 % |
| 5 | 2,43 % | 2,57 % | 4,04 % ↑ | 0,00 % s. c. |
| 6 | 0,87 % | 2,99 % | 4,71 % | 0,00 % s. c. |
| 7 | 0,36 % | 2,98 % | 3,13 % s. c. | 0,00 % s. c. |
| 8 | 0,20 % s. c. | 2,39 % | 1,80 % s. c. | 0,00 % s. c. |
| 9 | 0,00 % s. c. | sin días | sin días | sin días |
| 10 | 0,00 % s. c. | sin días | sin días | sin días |

Los cinco modelos con más días de disco, tasa por año de edad («s. c.»: menos de 20 fallos, sin conclusión; «↑»: sube frente al año anterior):

| Edad | TOSHIBA MG07ACA14TA | ST12000NM0008 | ST16000NM001G | ST8000NM0055 | ST4000DM000 |
|---:|---:|---:|---:|---:|---:|
| 0 | 0,73 % | 0,87 % | 0,64 % | 4,43 % | 0,00 % s. c. |
| 1 | 0,74 % | 1,26 % | 0,67 % | 2,54 % | 0,00 % s. c. |
| 2 | 0,94 % | 2,33 % ↑ | 0,69 % | 1,22 % | 3,76 % s. c. |
| 3 | 1,04 % | 2,88 % | 1,04 % | 1,33 % | 1,14 % s. c. |
| 4 | 1,65 % | 2,60 % | 1,72 % s. c. | 1,97 % | 1,35 % |
| 5 | 4,15 % ↑ | 3,28 % | 0,00 % s. c. | 3,24 % ↑ | 1,90 % |
| 6 | 4,72 % | sin días | sin días | 3,11 % | 2,98 % ↑ |
| 7 | sin días | sin días | sin días | 2,66 % | 3,67 % |
| 8 | sin días | sin días | sin días | 4,28 % | 3,29 % |
| 9 | sin días | sin días | sin días | sin días | sin días |
| 10 | sin días | sin días | sin días | sin días | sin días |

La supervivencia sale de una tabla de vida: cada disco cuenta desde la edad que tenía al aparecer, los que desaparecen sin fallo quedan censurados y la vida acaba en el primer fallo.

| Grupo | Discos | A 1 año | A 3 años | A 5 años | Corte |
|---|---:|---:|---:|---:|---|
| Todos los discos | 402.643 | 99,15 % | 97,09 % | 93,62 % | el año de edad 9 tiene 0 fallos, menos de 20: la curva se corta después de S(9) |
| Todos los discos, contando a los que desaparecen avisando | 402.643 | 99,10 % | 95,90 % | 91,54 % | el año de edad 9 tiene 12 fallos, menos de 20: la curva se corta después de S(9) |
| TOSHIBA MG07ACA14TA | 39.297 | 99,23 % | 97,57 % | 94,90 % | el año de edad 7 tiene 0 fallos, menos de 20: la curva se corta después de S(7) |
| ST12000NM0008 | 21.024 | 99,08 % | 95,59 % | 90,48 % | el año de edad 6 tiene 0 fallos, menos de 20: la curva se corta después de S(6) |
| ST16000NM001G | 34.710 | 99,33 % | 97,96 % | sin dato | el año de edad 4 tiene 17 fallos, menos de 20: la curva se corta después de S(4) |
| ST8000NM0055 | 15.231 | 95,39 % | 91,71 % | 88,74 % | el año de edad 9 tiene 0 fallos, menos de 20: la curva se corta después de S(9) |
| ST4000DM000 | 19.506 | sin dato | sin dato | sin dato | el año de edad 0 tiene 0 fallos, menos de 20: la curva se corta después de S(0) |

Por la otra vía, con las tasas por edad de los días de disco, el conjunto de discos da 99,21 %, 97,19 % y 93,83 % a 1, 3 y 5 años. La diferencia con la tabla de vida queda por debajo de 0,5 puntos: una cuenta usa los días de las fotos y el primer fallo, y la otra los días del recuento y todos los fallos.

El 01/04/2025 había 11.038 discos de 8 años o más, el 3,6 % de 308.836. La tasa del conjunto de discos en esas edades:

- 7 años: 2,41 %, 1.207 fallos en 18.269.950 días de disco (primer año).
- 8 años: 1,90 %, 334 fallos en 6.421.014 días de disco (no se distingue).
- 9 a 10 años: 0,00 %, 0 fallos en 98.598 días de disco (sin conclusión).

Las comprobaciones de B3:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: no aplica, porque B3 no ordena entidades en un ranking.
- La referencia: sí.
- El azar en muchos grupos: no aplica, porque B3 compara cada año de edad con el anterior con el criterio de las reglas, apartado 7 (intervalos que no se solapan), no grupos frente al total.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: no aplica, porque la tasa por edad y la supervivencia describen el periodo; la previsión es el bloque 9.
- La cobertura: sí.
- Los periodos: no aplica, porque la tasa por edad y la supervivencia juntan todo el periodo, sin comparar años de calendario; 2025 aporta sus seis meses de días y fallos.
- Del petición, el φ usado es el medido y nunca menor que 1: sí.

## Lo que no saca conclusión

Estos grupos se enseñan con su recuento y no se comparan. Los años de edad sin ningún día de disco no están aquí: salen como «sin días» en su tabla.

- B2, 147 años de modelo por debajo de 50.000 días de disco: 101 fallos en 1.282.168 días de disco.
- B2, 29 modelos sin ningún año que llegue al mínimo: 89 fallos en 1.003.365 días de disco. La lista, modelo a modelo, está en el JSON.
- B2, ST6000DX000: 15 fallos en 1.389.650 días de disco, tasa bruta del 0,39 %; menos de 20 fallos, sin puesto y sin conclusión (cuestión 012).
- B2, ST8000NM000A: 2 fallos en 139.294 días de disco, tasa bruta del 0,52 %; menos de 20 fallos, sin puesto y sin conclusión (cuestión 012).
- B2, ST16000NM002J: 6 fallos en 425.347 días de disco, tasa bruta del 0,51 %; menos de 20 fallos, sin puesto y sin conclusión (cuestión 012).
- B2, ST14000NM000J: 2 fallos en 55.394 días de disco, tasa bruta del 1,32 %; menos de 20 fallos, sin puesto y sin conclusión (cuestión 012).
- B2, ST12000NM000J: 17 fallos en 332.279 días de disco, tasa bruta del 1,87 %; menos de 20 fallos, sin puesto y sin conclusión (cuestión 012).
- B3, todos los discos, años de edad con menos de 20 fallos: 9 (0 en 96.647 días) y 10 (0 en 1.951 días).
- B3, todos los discos contando a los que desaparecen avisando, años de edad con menos de 20 fallos: 9 (12 en 96.647 días) y 10 (0 en 1.951 días).
- B3, HGST, años de edad con menos de 20 fallos: 8 (8 en 1.431.111 días), 9 (0 en 96.647 días) y 10 (0 en 1.951 días).
- B3, Toshiba, años de edad con menos de 20 fallos: 7 (3 en 34.932 días) y 8 (1 en 20.283 días).
- B3, WDC, años de edad con menos de 20 fallos: 5 (0 en 1.095 días), 6 (0 en 1.095 días), 7 (0 en 1.095 días) y 8 (0 en 969 días).
- B3, ST16000NM001G, años de edad con menos de 20 fallos: 4 (17 en 361.052 días) y 5 (0 en 10.664 días).
- B3, ST4000DM000, años de edad con menos de 20 fallos: 0 (0 en 2.253 días), 1 (0 en 4.480 días), 2 (4 en 38.857 días) y 3 (13 en 417.408 días).
- B3, tramos de 7 años o más, años de edad con menos de 20 fallos: 9 a 10 (0 en 98.598 días).
- B3, supervivencia de el conjunto de discos: el año de edad 9 tiene 0 fallos, menos de 20: la curva se corta después de S(9).
- B3, supervivencia de el conjunto de discos contando a los que desaparecen avisando: el año de edad 9 tiene 12 fallos, menos de 20: la curva se corta después de S(9).
- B3, supervivencia de TOSHIBA MG07ACA14TA: el año de edad 7 tiene 0 fallos, menos de 20: la curva se corta después de S(7).
- B3, supervivencia de ST12000NM0008: el año de edad 6 tiene 0 fallos, menos de 20: la curva se corta después de S(6).
- B3, supervivencia de ST16000NM001G: el año de edad 4 tiene 17 fallos, menos de 20: la curva se corta después de S(4).
- B3, supervivencia de ST8000NM0055: el año de edad 9 tiene 0 fallos, menos de 20: la curva se corta después de S(9).
- B3, supervivencia de ST4000DM000: el año de edad 0 tiene 0 fallos, menos de 20: la curva se corta después de S(0).

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

Cada cifra se rehízo desde otra tabla. Las segundas vías:

| Cifra | Primera vía | Segunda vía | Comparación | Coinciden |
|---|---|---|---|---|
| días de disco por modelo y año | recuento_diario_corregido | modelo_trimestre | exacta, 299 claves, diferencia mayor 0,0000 | sí |
| fallos por modelo y año | recuento_diario_corregido | modelo_trimestre | exacta, 299 claves, diferencia mayor 0,0000 | sí |
| altas por trimestre (con el primero) | fotos_mensuales_corregido + ventanas_fallo_corregido | vida_discos | exacta, 22 claves, diferencia mayor 0,0000 | sí |
| primera aparición de cada disco | fotos_mensuales_corregido + ventanas_fallo_corregido | vida_discos | exacta, 402643 claves, diferencia mayor 0,0000 | sí |
| fallos por trimestre | recuento_diario_corregido | fallos_detalle | exacta, 22 claves, diferencia mayor 0,0000 | sí |
| discos el primer día de cada trimestre, por modelo | recuento_diario_corregido | inicio_trimestre | exacta, 995 claves, diferencia mayor 0,0000 | sí |
| supervivencia del conjunto de discos a 1, 3 y 5 años, en % | vida_discos (tabla de vida) | dias_por_tramo (tasas por año de edad) | diferencia menor que 0,5 puntos, 3 claves, diferencia mayor 0,2106 | sí |
| supervivencia del conjunto de discos contando a los que desaparecen avisando, a 1, 3 y 5 años, en % | vida_discos (tabla de vida) | dias_por_tramo (tasas por año de edad) | diferencia menor que 0,5 puntos, 3 claves, diferencia mayor 0,2482 | sí |
| supervivencia de los cinco modelos a 1, 3 y 5 años, en % (valores publicados) | vida_discos (tabla de vida) | dias_por_tramo (tasas por año de edad) | diferencia menor que 0,5 puntos, 11 claves, diferencia mayor 0,4262 | sí |
| discos el día 1 de cada mes, por modelo | recuento_diario_corregido | dias_por_tramo (fotos) | exacta, 3003 claves, diferencia mayor 0,0000 | sí |
| días de disco por centro y año desde el 01/07/2023 | recuento_diario_corregido | centro_mes | exacta, 18 claves, diferencia mayor 0,0000 | sí |
| fallos por modelo y año de edad | fallos_detalle (edad al fallar) | dias_por_tramo | exacta, 207 claves, diferencia mayor 0,0000 | sí |
| discos de 8 años o más y discos totales el primer día del último trimestre | inicio_trimestre | dias_por_tramo (fotos) | exacta, 2 claves, diferencia mayor 0,0000 | sí |
| desaparecen sin fallo por trimestre de su última foto | fotos_mensuales_corregido + fallos_detalle | vida_discos | exacta, 22 claves, diferencia mayor 0,0000 | sí |
| razón a igual edad por modelo | dias_por_tramo, agregado con pandas | dias_por_tramo, fila a fila con diccionarios | diferencia menor que 1e-9, 32 claves, diferencia mayor 0,0000 | sí |
| fallos por modelo en las celdas que pasan el mínimo | dias_por_tramo (observados) | modelo_trimestre (fallos del ranking) | exacta, 32 claves, diferencia mayor 0,0000 | sí |

## Parámetros usados

- mínimo de días de disco en el año para un ranking: 50.000 (reglas-negocio §7; sustituye al mínimo de 30 casos de el método, que cambian las reglas del caso).
- mínimo de fallos en un año de edad para sacar conclusión: 20 (reglas-negocio §7, cuestión 009).
- mínimo de fallos de un modelo, en sus años que pasan el mínimo, para llevar puesto y sacar conclusión: 20 (reglas-negocio §7, cuestión 012 (el responsable del caso, 18/11/2026)).
- comparación a igual edad y en el mismo trimestre: razón = fallos observados / esperados con la tasa de cada año de edad y trimestre de calendario de las celdas de dias_por_tramo cuyo modelo y año pasan el mínimo, con todos los modelos juntos; intervalo exacto de Poisson con observados y esperados entre φ; tasa a igual edad = razón × tasa de todas las celdas (reglas-negocio §7 («Una tasa por modelo se compara a igual edad y en el mismo trimestre», el responsable del caso, 18/11/2026); peticiones 17 y 19).
- φ de B2: chi2 de Pearson / grados de libertad en las celdas de modelo × trimestre, con los esperados de arriba reescalados para que cada modelo sume sus fallos; gl = celdas − modelos; si sale menor que 1, vale 1 (criterio técnico (reglas, apartado 7, una nota del caso y una nota del caso); petición 19).
- φ de B3: el mismo cálculo en las celdas de modelo × año de edad × trimestre de dias_por_tramo, con el esperado = días × la tasa de su modelo y año de edad en todo el periodo; un solo φ para la tasa de cada año de edad de todos los grupos y su «sube» (criterio técnico (reglas, apartado 7, una nota del caso y una nota del caso); petición 19).
- veredicto a igual edad: por encima o por debajo si el intervalo de la razón con φ queda entero a un lado de 1; si no, no se distingue (peticiones 17 y 19).
- comparación con el método anterior: la razón solo a igual edad y sin φ, al lado: los veredictos que cambian y la Spearman de las razones (criterio, para que se vea qué mueve la petición 19).
- edad media de un modelo: años cumplidos + 0,5, ponderados por días de disco, en sus celdas (criterio: la misma edad media de fabricantes y capacidades de la petición 13).
- estabilidad de los veredictos a igual edad: quitando cada modelo uno a uno, con las tasas por edad rehechas sin él, y sin el año parcial (directriz 37 del auditor del cierre analítico; petición 17).
- correlación de Spearman entre la tasa bruta y la razón: con todos los modelos que tienen razón y con los que llevan puesto (criterio: la petición 17 no dice con cuáles, y se dan las dos).
- confianza de los intervalos: 0,95 (parametros.md de el método y 42.6 del manual).
- intervalo de una tasa: exacto de Poisson con scipy.stats.chi2 (criterio técnico, fijado en la petición).
- supervivencia: tabla de vida con entrada tardía, años de edad 0 a 10 (criterio técnico, fijado en la petición).
- diferencia máxima entre las dos vías de la supervivencia: 0,5 puntos (la petición la fija para el conjunto de discos; el script aplica la misma a los cinco modelos y a la cifra que cuenta a los que desaparecen avisando, por criterio.
- «baja» frente al año anterior: el intervalo del año queda por debajo del anterior (criterio, simétrico al «sube» de las reglas, apartado 7).
- días del año en los datos: los del calendario, con 2025 del 01/01 al 30/06 (calendario.parquet; petición).
- modelos de cada año en B1 y modelos en B3: 10 y 5 (plan, bloques 1 y 3; petición).
- parte de cada centro en su año: sobre todos los días del año, con «sin dato» dentro (criterio: así las partes suman 100 y «sin dato» se ve con su peso).
- semilla: no aplica (ningún cálculo usa azar).

## Datos personales

- No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección.
- No hay datos de personas (reglas-negocio §9): el número de serie identifica un disco, no a una persona.
- Este cálculo usa el número de serie solo para contar discos y no deja ninguno en el JSON ni en el informe.

## Límites

- La comparación a igual edad corrige la edad de cada modelo y el trimestre de calendario, no su centro. Usa las celdas por año de edad, que dejan fuera 897.016 días de disco sin foto de los años que pasan el mínimo.
- Los intervalos de B2 y B3 llevan φ, medido con la variación entre trimestres; es un criterio técnico y no cambia ninguna razón ni ninguna tasa, solo lo ancho del intervalo.
- 5 modelos tienen menos de 20 fallos en sus años que pasan el mínimo: salen con su tasa, sus fallos y sus días, pero sin puesto y sin conclusión (cuestión 012).
- Las cifras describen el periodo del 01/01/2020 al 30/06/2025. Ninguna dice por qué un modelo, un fabricante o una edad falla más: solo valen verbos de asociación.
- 2025 tiene seis meses. Sus discos medios, su columna del mapa y sus días por centro no se comparan con un año entero.
- Las bajas sin fallo de 2025T2 están incompletas: la última foto de los datos es del 01/06/2025, y un disco que la tiene cuenta como que sigue aunque se vaya en junio.
- Comparar fabricantes o capacidades mezcla modelos de edades distintas (reglas, apartado 7). La edad media al lado lo deja ver, pero no lo corrige.
- El centro solo consta desde el 01/07/2023. Desde entonces, 6.621.213 días de disco de 207.297.278 vienen sin centro y se cuentan aparte.
- La tasa por edad sale de dias_por_tramo, que reparte los días del recuento con las fotos de cada mes: deja fuera 919.192 días de disco sin foto, el 0,21 % del recuento. Los días por año de edad no tienen otra fuente exacta: se contrastan a través de la supervivencia.
- En la supervivencia, 3.359 discos tienen la edad final por debajo de la de entrada (horas encendido que bajan, R-009) y no aportan exposición.
- Un disco que desaparece se cuenta como censurado: se sabe que llegó vivo a su última foto, no si se migró, se retiró sano o falló fuera de los datos. Eso no se puede saber. Contándolos como fallo cuando avisaban, la supervivencia a 5 años pasa del 93,62 % al 91,54 %, y la lectura frente al año anterior cambia en los años de edad 1, 4 y 8.
- Si la tasa de los discos más viejos baja porque son los que han aguantado no se puede saber con estos datos: la tasa describe a los que quedan. Los datos no dicen por qué salieron los demás.
- Ninguna cifra se ha medido hacia adelante: la reserva, del 01/07/2025 al 30/06/2026, no se mira (reglas, apartado 5).
- Pendiente: el auditor sin memoria del cierre del paso (método §8) necesita el sí del responsable del caso, porque es un agente.

