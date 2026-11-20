# Coste por terabyte de cada modelo y previsión de fallos por trimestre

Caso 68, paso 5, bloques 4 y 9 del plan de la analítica. Datos hasta el 30/06/2025; ejecutado el 18/11/2026. Estado: **AVISO**, riesgo medio.

Dos bloques calculados con 143 cifras, todas con su segunda vía, y las nueve validaciones en verde. La cuenta no gana: no vale y se usa la referencia (reglas, apartado 7), con un error absoluto ponderado de 0,2670 frente a 0,2504. Quedan 20 grupos sin conclusión por el mínimo o por falta de precio, y el coste depende de precios inferidos.

## Las preguntas y su planteamiento

Las dos preguntas salen del plan de la analítica, aprobado por el responsable del caso el 16/11/2026, y de los planteamientos 1.A y 1.B. Entran los discos de datos, sin los de arranque, del 01/01/2020 al 30/06/2025. La tasa anual de fallo es 100 × 365 × fallos / días de disco.

- **B4.** Cuánto cuesta cada modelo de disco por terabyte y año, contando los que se rompen.
  - Decisión que apoya: qué modelos comprar: un disco barato que falla mucho puede salir más caro (plan, bloque 4).
  - Medida: coste por TB y año = precio / capacidad / 6 + tasa anual × (disco nuevo del año del fallo + 37 dólares) / capacidad, que se calcula como suma del coste de los fallos / terabytes-año (reglas, apartado 6).
  - Mínimo: 50.000 días de disco del modelo en el año (reglas, apartado 7).
  - Referencia: el coste por TB y año del conjunto de discos en las mismas celdas del ranking; para el mejor modelo, el coste real de todos los modelos con precio de su capacidad y año.
- **B9.** Cuántos discos fallarán el próximo trimestre, por capacidad.
  - Decisión que apoya: cuántos discos de repuesto comprar y cuántas horas de técnico hacen falta (plan, bloque 9).
  - Medida: previstos = suma de discos del primer día × días del trimestre × tasa diaria de su modelo y año de edad, con los meses anteriores al primer día; error absoluto ponderado = suma de |previsto − real| / suma de reales, y el sesgo con signo (reglas, apartado 7, cuestión 011).
  - Mínimo: 50.000 días de disco en la celda de modelo y edad, o de capacidad y edad (reglas, apartado 7; criterio 5).
  - Referencia: repetir los fallos reales del trimestre anterior de la misma capacidad.

La teoría del manual que se aplicó:

- 42.1: elegir la función por la pregunta: ninguna del capítulo calcula un coste con averías ni prevé un recuento, y se usan la fórmula de las reglas y una cuenta.
- 38.1: el objetivo de negocio, reducir costes y alargar la vida útil, da la decisión de cada bloque.
- 11.10: ranking de coste con empates por el método «min».
- 13.6 y 13.7: consultas agrupadas por modelo y año, por año y capacidad y por trimestre y capacidad.
- 5.5: el coste del conjunto de discos es suma de costes entre suma de terabytes-año, no la media de los costes, y cada cifra va con su base.
- 5.6: el ranking mezcla capacidades y años de compra; el mejor modelo se busca dentro de cada capacidad y año.
- 4.5 y 4.7: intervalo al 95 % de la tasa; el mínimo de casos lo fijan las reglas del caso, no el manual.
- 4.11 y 4.12: no se contrastan proporciones: el intervalo de la tasa es el exacto de Poisson, como en la petición 13.
- 31.9: la previsión se mide con el error absoluto ponderado y el sesgo aparte, frente a la referencia ingenua de repetir el periodo anterior.

## B4 · Cuánto cuesta cada modelo

El modelo más barato por terabyte y año es el TOSHIBA MG10ACA20TE, con 1,8758 dólares, y el más caro el ST8000DM002, con 6,0234 dólares. Entran 32 modelos, con los 152 años de modelo que pasan el mínimo de 50.000 días de disco. 27 llevan puesto; los 5 con menos de 20 fallos salen con su coste, sin puesto y al final de la tabla (reglas, apartado 7, cuestión 012).

Los fallos pesan poco en el coste: su parte tiene una mediana del 6,44 % entre los 27 modelos con puesto, y el resto es la amortización del precio de compra. El orden por coste se parece poco al orden por tasa de fallo: la correlación de Spearman entre los dos es de 0,495. Además, 5 de los 10 primeros tienen el precio inferido, así que su puesto vale lo que valga ese precio.

El puesto se da dentro de cada capacidad y año de compra, que es donde la tasa de fallo decide: entre años de compra, el orden lo pone el precio de cada año (reglas, apartado 7). Hay 19 grupos con algún modelo con puesto, y 7 con dos o más, que son los únicos donde el puesto compara modelos:

- 4 TB comprados en 2016: 1.º HGST HMS5C4040BLE640, 4,0303 dólares; 2.º HGST HMS5C4040ALE640, 4,3286 dólares.
- 12 TB comprados en 2019: 1.º HGST HUH721212ALE600, 3,0510 dólares; 2.º HGST HUH721212ALN604, 3,6937 dólares.
- 12 TB comprados en 2021: 1.º ST12000NM001G, 2,7922 dólares; 2.º HGST HUH721212ALE604, 2,8399 dólares.
- 14 TB comprados en 2020: 1.º TOSHIBA MG07ACA14TA, 2,7967 dólares; 2.º ST14000NM0138, 3,5818 dólares.
- 14 TB comprados en 2021: 1.º WDC WUH721414ALE6L4, 2,6526 dólares; 2.º ST14000NM001G, 2,7931 dólares.
- 16 TB comprados en 2021: 1.º WDC WUH721816ALE6L0, 2,7186 dólares; 2.º TOSHIBA MG08ACA16TEY, 2,8029 dólares; 3.º TOSHIBA MG08ACA16TE, 2,8279 dólares.
- 16 TB comprados en 2023: 1.º WDC WUH721816ALE6L4, 2,3437 dólares; 2.º TOSHIBA MG08ACA16TA, 2,3881 dólares.

El orden de todos juntos va al lado, como contexto, en la columna «De todos» y en el resumen de arriba.

Cada coste va en dólares por TB y año. El intervalo pone en la parte de los fallos el intervalo al 95 % de la tasa; con garantía, un fallo dentro de ella cuesta solo los 37 dólares del cambio.

| En su grupo | De todos | Modelo | TB | Año de compra | Tasa | Precio | Amortización | Fallos | Coste | Intervalo | Con garantía | A igual edad |
|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---|---:|---:|
| 1 | 1 | TOSHIBA MG10ACA20TE | 20 | 2024 | 0,68 % | 215 (inferido) | 1,7919 | 0,0839 | 1,8758 | 1,8534 a 1,9039 | 1,8045 | 1,9421 |
| 1 | 2 | WDC WUH722222ALE6L4 | 22 | 2024 | 0,81 % | 249 (inferido) | 1,8839 | 0,1015 | 1,9854 | 1,9731 a 1,9990 | 1,8975 | 2,0639 |
| 1 | 3 | ST24000NM002H | 24 | 2025 | 1,93 % | 254 (inferido) | 1,7642 | 0,2224 | 1,9865 | 1,9191 a 2,0734 | 1,7939 | 2,1572 |
| 1 | 4 | WDC WUH721816ALE6L4 | 16 | 2023 | 0,37 % | 220 (inferido) | 2,2922 | 0,0515 | 2,3437 | 2,3370 a 2,3511 | 2,3007 | 2,3804 |
| 2 | 5 | TOSHIBA MG08ACA16TA | 16 | 2023 | 1,15 % | 214 (inferido) | 2,2292 | 0,1589 | 2,3881 | 2,3776 a 2,3991 | 2,2558 | 2,4946 |
| 1 | 6 | ST16000NM001G | 16 | 2022 | 0,72 % | 240 (curva) | 2,4963 | 0,1087 | 2,6050 | 2,5970 a 2,6135 | 2,5129 | 2,6629 |
| 1 | 7 | WDC WUH721414ALE6L4 | 14 | 2021 | 0,50 % | 217 (curva) | 2,5778 | 0,0748 | 2,6526 | 2,6423 a 2,6640 | 2,5909 | 2,6683 |
| 1 | 8 | WDC WUH721816ALE6L0 | 16 | 2021 | 0,74 % | 251 (curva) | 2,6175 | 0,1011 | 2,7186 | 2,6974 a 2,7437 | 2,6346 | 2,7708 |
| 1 | 9 | TOSHIBA MG07ACA14TEY | 14 | 2022 | 1,47 % | 212 (vecinas) | 2,5180 | 0,2302 | 2,7482 | 2,6817 a 2,8327 | 2,5568 | 2,8200 |
| 1 | 10 | ST12000NM001G | 12 | 2021 | 0,99 % | 189 (vecinas) | 2,6313 | 0,1609 | 2,7922 | 2,7794 a 2,8058 | 2,6630 | 2,8103 |
| 2 | 11 | ST14000NM001G | 14 | 2021 | 1,41 % | 216 (curva) | 2,5710 | 0,2222 | 2,7931 | 2,7765 a 2,8107 | 2,6083 | 2,8489 |
| 1 | 12 | TOSHIBA MG07ACA14TA | 14 | 2020 | 1,03 % | 221 (curva) | 2,6333 | 0,1634 | 2,7967 | 2,7893 a 2,8044 | 2,6710 | 2,8002 |
| 2 | 13 | TOSHIBA MG08ACA16TEY | 16 | 2021 | 1,25 % | 252 (curva) | 2,6224 | 0,1805 | 2,8029 | 2,7802 a 2,8280 | 2,6512 | 2,8878 |
| 3 | 14 | TOSHIBA MG08ACA16TE | 16 | 2021 | 1,29 % | 253 (curva) | 2,6313 | 0,1966 | 2,8279 | 2,8055 a 2,8524 | 2,6612 | 2,9349 |
| 2 | 15 | HGST HUH721212ALE604 | 12 | 2021 | 1,57 % | 188 (vecinas) | 2,6050 | 0,2349 | 2,8399 | 2,8247 a 2,8560 | 2,6535 | 2,9086 |
| 1 | 16 | HGST HUH721212ALE600 | 12 | 2019 | 0,56 % | 213 (curva) | 2,9605 | 0,0905 | 3,0510 | 3,0320 a 3,0734 | 2,9966 | 3,0197 |
| 1 | 17 | ST12000NM0008 | 12 | 2020 | 2,02 % | 200 (curva) | 2,7833 | 0,3313 | 3,1146 | 3,1005 a 3,1291 | 2,8632 | 3,0362 |
| 2 | 18 | ST14000NM0138 | 14 | 2020 | 5,90 % | 221 (curva) | 2,6333 | 0,9485 | 3,5818 | 3,4901 a 3,6807 | 2,7893 | 3,7929 |
| 2 | 19 | HGST HUH721212ALN604 | 12 | 2019 | 2,34 % | 240 (curva) | 3,3334 | 0,3604 | 3,6937 | 3,6749 a 3,7134 | 3,5273 | 3,5400 |
| 1 | 20 | HGST HMS5C4040BLE640 | 4 | 2016 | 0,33 % | 95 (curva) | 3,9527 | 0,0776 | 4,0303 | 4,0198 a 4,0421 | 4,0287 | 4,0199 |
| 1 | 21 | HGST HUH728080ALE600 | 8 | 2018 | 1,28 % | 188 (vecinas) | 3,9249 | 0,2290 | 4,1539 | 4,1053 a 4,2115 | 4,0677 | 4,0847 |
| 1 | 22 | ST12000NM0007 | 12 | 2018 | 1,83 % | 279 (curva) | 3,8761 | 0,3283 | 4,2044 | 4,1823 a 4,2278 | 3,9475 | 4,2888 |
| 2 | 23 | HGST HMS5C4040ALE640 | 4 | 2016 | 0,63 % | 100 (curva) | 4,1767 | 0,1519 | 4,3286 | 4,2985 a 4,3639 | 4,3275 | 4,3078 |
| 1 | 24 | ST10000NM0086 | 10 | 2017 | 3,87 % | 247 (vecinas) | 4,1180 | 0,6570 | 4,7751 | 4,6951 a 4,8631 | 4,5924 | 4,5878 |
| 1 | 25 | ST8000NM0055 | 8 | 2017 | 2,34 % | 216 (curva) | 4,4923 | 0,4240 | 4,9163 | 4,8970 a 4,9362 | 4,7896 | 4,8037 |
| 1 | 26 | ST4000DM000 | 4 | 2015 | 2,54 % | 126 (curva) | 5,2432 | 0,6037 | 5,8469 | 5,8204 a 5,8744 | 5,8469 | 5,6633 |
| 1 | 27 | ST8000DM002 | 8 | 2016 | 1,80 % | 273 (curva) | 5,6956 | 0,3278 | 6,0234 | 6,0027 a 6,0451 | 6,0191 | 5,9875 |
| sin puesto | sin puesto | ST14000NM000J | 14 | 2024 | 1,32 % | 161 (inferido) | 1,9212 | 0,1864 | 2,1075 | 1,9437 a 2,5944 | 1,9560 | 2,2235 |
| sin puesto | sin puesto | ST12000NM000J | 12 | 2024 | 1,87 % | 138 (inferido) | 1,9184 | 0,2707 | 2,1890 | 2,0760 a 2,3518 | 1,9759 | 2,3851 |
| sin puesto | sin puesto | ST8000NM000A | 8 | 2023 | 0,52 % | 112 (inferido) | 2,3436 | 0,0845 | 2,4281 | 2,3538 a 2,6489 | 2,3678 | 2,4682 |
| sin puesto | sin puesto | ST16000NM002J | 16 | 2022 | 0,51 % | 235 (curva) | 2,4440 | 0,0789 | 2,5229 | 2,4729 a 2,6158 | 2,4559 | 2,5880 |
| sin puesto | sin puesto | ST6000DX000 | 6 | 2015 | 0,39 % | 198 (vecinas) | 5,5097 | 0,0815 | 5,5913 | 5,5554 a 5,6442 | 5,5913 | 5,5698 |

La última columna pone en la parte de los fallos la tasa a igual edad de cada modelo, la del bloque 2: la que tendría con la mezcla de edades de todos los discos. Con los 32 modelos, la correlación de Spearman entre el coste observado y el de igual edad es de 0,9960, y el mayor salto de puesto es de 3 (TOSHIBA MG07ACA14TA).

Si los precios inferidos estuvieran un 20 % por debajo o por encima, los diez primeros con puesto quedarían así:

- Precio inferido × 0,8: siguen 10 de 10. El primero es el TOSHIBA MG10ACA20TE.
- Precio inferido × 1,2: siguen 8 de 10; salen TOSHIBA MG08ACA16TA y WDC WUH721816ALE6L4 y entran ST14000NM001G y TOSHIBA MG07ACA14TA. El primero es el TOSHIBA MG10ACA20TE.

El conjunto de discos de esas mismas celdas cuesta 3,0760 dólares por TB y año. La serie del gráfico de dispersión, con la tasa, el coste y los discos medios de cada modelo, está en el JSON.

Fuera del ranking quedan 147 años de modelo por debajo del mínimo, con 1.282.168 días de disco y 101 fallos. Los 4 modelos sin precio suman 18.840 días de disco y 0 fallos, y ninguno de sus años llega al mínimo.

La vida real no se puede medir: ningún modelo baja del 50 % de discos vivos en su curva con base. De los 61 modelos de datos, 19 tienen algún año de edad con 20 fallos o más. La curva que más baja es la del ST14000NM0138, que se queda en el 73,72 % a 5 años. El coste usa la vida contable de 6 años.

Si cada año se hubieran comprado solo discos del modelo más barato de cada capacidad, el coste habría bajado en estas cifras, en dólares:

| Año | Capacidades | Coste real | Con el mejor | Diferencia | Del precio | De los fallos |
|---|---:|---:|---:|---:|---:|---:|
| 2020 | 6 | 5.130.975 | 4.111.088 | 1.019.887 | 931.056 | 88.831 |
| 2021 | 7 | 6.398.103 | 5.596.652 | 801.451 | 588.468 | 212.982 |
| 2022 | 7 | 7.887.450 | 6.896.905 | 990.544 | 652.365 | 338.179 |
| 2023 | 8 | 9.274.253 | 7.827.775 | 1.446.478 | 936.501 | 509.977 |
| 2024 | 9 | 11.107.178 | 9.062.318 | 2.044.860 | 1.892.334 | 152.527 |
| 2025 (parcial) | 9 | 6.058.691 | 5.366.915 | 691.776 | 496.474 | 195.303 |

En 2024, el año con más diferencia, 1.892.334 de los 2.044.860 dólares salen del precio de compra y 152.527 de los fallos. En la tabla de precios, dos modelos de la misma capacidad solo cambian de precio por su año de compra, así que la parte del precio sale de haber comprado en otro año.

En 6 combinaciones de año y capacidad la diferencia sale negativa (2020 con 10 TB, 2021 con 10 TB, 2022 con 10 TB, 2023 con 10 TB, 2024 con 10 TB y 2025 con 10 TB): el mejor modelo que pasa el mínimo cuesta más por TB y año que algún modelo de su capacidad que no llega a él.

9 combinaciones de año y capacidad no tienen ningún modelo que pase el mínimo y quedan fuera de esta tabla; van en el JSON con su coste real.

El ingreso de Backblaze por terabyte de disco es un orden de magnitud: la capacidad incluye la paridad y el espacio libre, y lo que guardan los clientes no se publica.

- 2023: 34,05 dólares de ingreso por TB, con 2.995.811 TB de media. El coste por TB y año de todos los discos con precio fue de 3,097 dólares, y de 2,940 dólares con garantía.
- 2024: 32,66 dólares de ingreso por TB, con 3.907.527 TB de media. El coste por TB y año de todos los discos con precio fue de 2,836 dólares, y de 2,701 dólares con garantía.
- 2025: no se calcula: necesita la capacidad de julio a diciembre de 2025, que es reserva (reglas, apartado 6).

Las comprobaciones de B4:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: sí.
- La referencia: sí.
- El azar en muchos grupos: no aplica, porque B4 ordena los modelos por coste y no compara cada uno con el conjunto de discos; la tasa frente al conjunto, con su intervalo y lo que saldría por azar, está en B2.
- Los pesos: no aplica, porque el coste suma dos partes con su fórmula (reglas, apartado 6), sin pesos que se puedan mover.
- Hacia adelante: no aplica, porque B4 describe el coste del periodo; si un modelo barato lo sigue siendo después se mide en la reserva, que no se mira (reglas, apartado 5).
- La cobertura: sí.
- Los periodos: sí.
- Del petición, las dos partes de la diferencia con el mejor modelo suman el total en cada celda: sí.
- Del petición, ningún puesto compara modelos de distinta capacidad o año de compra (petición 19): sí.

## B9 · Cuántos discos fallarán el próximo trimestre

La cuenta no gana a la referencia: su error absoluto ponderado es 0,2670, frente a 0,2504 de repetir los fallos del trimestre anterior. Con la regla del caso (reglas, apartado 7), la cuenta no vale y se usa la referencia.

La cuenta prevé de más: su sesgo es de +0,0507, y el de la referencia, de −0,0439. En los 18 trimestres prevé 16.484,0 fallos, y hubo 15.689.

Cada trimestre se prevé con los discos del primer día y las tasas medidas hasta el día anterior. La serie de las tres líneas del gráfico es esta, en fallos:

| Trimestre | Previstos | Reales | Referencia | Error de la cuenta | Error de la referencia |
|---|---:|---:|---:|---:|---:|
| 2021T1 | 418,4 | 350 | 372 | 0,2079 | 0,1829 |
| 2021T2 | 410,4 | 441 | 350 | 0,2529 | 0,3379 |
| 2021T3 | 437,9 | 510 | 441 | 0,1420 | 0,1863 |
| 2021T4 | 477,4 | 522 | 510 | 0,1206 | 0,1533 |
| 2022T1 | 527,0 | 618 | 522 | 0,1949 | 0,1942 |
| 2022T2 | 589,7 | 763 | 618 | 0,2357 | 0,1900 |
| 2022T3 | 766,3 | 916 | 763 | 0,2111 | 0,1976 |
| 2022T4 | 862,1 | 702 | 916 | 0,3057 | 0,3305 |
| 2023T1 | 855,3 | 892 | 702 | 0,2288 | 0,2735 |
| 2023T2 | 977,0 | 1.341 | 892 | 0,2922 | 0,3348 |
| 2023T3 | 1.303,9 | 943 | 1.341 | 0,4141 | 0,5090 |
| 2023T4 | 1.206,9 | 1.025 | 943 | 0,3222 | 0,2400 |
| 2024T1 | 1.169,3 | 949 | 1.025 | 0,2401 | 0,1475 |
| 2024T2 | 1.128,4 | 1.199 | 949 | 0,2233 | 0,2168 |
| 2024T3 | 1.291,1 | 1.389 | 1.199 | 0,1951 | 0,1944 |
| 2024T4 | 1.430,0 | 1.001 | 1.389 | 0,4447 | 0,3896 |
| 2025T1 | 1.292,5 | 1.067 | 1.001 | 0,3006 | 0,1706 |
| 2025T2 | 1.340,4 | 1.061 | 1.067 | 0,2941 | 0,1904 |

Por capacidad, en todos los trimestres juntos:

| Capacidad | Previstos | Reales | Referencia | Error de la cuenta | Error de la referencia |
|---:|---:|---:|---:|---:|---:|
| 4 TB | 1.743,0 | 1.925 | 2.019 | 0,2359 | 0,2390 |
| 6 TB | 17,1 | 13 | 13 | 1,0149 | 1,0769 |
| 8 TB | 2.521,7 | 2.597 | 2.559 | 0,3295 | 0,3496 |
| 10 TB | 194,9 | 229 | 224 | 0,4217 | 0,4061 |
| 12 TB | 5.307,4 | 5.239 | 4.995 | 0,1925 | 0,2115 |
| 14 TB | 3.796,6 | 3.000 | 2.873 | 0,3138 | 0,1643 |
| 16 TB | 2.551,8 | 2.353 | 2.076 | 0,2819 | 0,3030 |
| 18 TB | 3,6 | 9 | 11 | 1,1735 | 1,7778 |
| 20 TB | 52,1 | 46 | 26 | 0,4373 | 0,4348 |
| 22 TB | 280,8 | 243 | 197 | 0,4347 | 0,3128 |
| 24 TB | 14,9 | 35 | 7 | 0,5741 | 0,8000 |

Las horas de técnico previstas son 0,74 por fallo previsto; van por trimestre y capacidad en el JSON, con los 157 pares.

La tasa de cada disco del primer día sale de su modelo y año de edad si esa celda tiene 50.000 días de disco o más; si no, de su capacidad y edad, y si tampoco, de su edad con todos los discos. Sumando los trimestres, el 96,8 % de los discos usó la de su modelo, 2,5 % la de su capacidad y 0,7 % la de su edad. El reparto por trimestre está en el JSON.

La sensibilidad, solo para leer, cambia la regla de la tasa. El veredicto lo da la cuenta principal:

- 12 meses de historia: error de 0,2528, sesgo de +0,0414; no gana a la referencia.
- Mínimo de 1 día, toda la historia: error de 0,3264, sesgo de +0,1382; no gana a la referencia.
- Mínimo de 1 día, 12 meses de historia: error de 0,3313, sesgo de +0,1495; no gana a la referencia.
- Solo capacidad y año de edad: error de 0,2774, sesgo de +0,0609; no gana a la referencia.

La cuenta no puede ver 413 de los 15.689 fallos reales, el 2,63 %: son de discos que aparecen después del primer día de su trimestre, y la regla de la previsión solo cuenta los discos de ese día (reglas, apartado 7). La referencia sí los cuenta.

Las comprobaciones de B9:

- La unidad: sí.
- El mínimo de casos: sí.
- Los empates: no aplica, porque B9 no ordena entidades en un ranking.
- La referencia: sí.
- El azar en muchos grupos: no aplica, porque B9 compara dos previsiones con el mismo error ponderado, no grupos frente al total.
- Los pesos: no aplica, porque no hay ninguna puntuación con pesos.
- Hacia adelante: sí.
- La cobertura: sí.
- Los periodos: sí.
- Del petición, ninguna tasa de la previsión usa un mes igual o posterior al primer día de su trimestre: sí.
- Del petición, los fallos reales de los trimestres previstos suman lo mismo que el recuento: sí.

## Lo que no saca conclusión

- B4, 147 años de modelo por debajo de 50.000 días de disco: 101 fallos en 1.282.168 días. No entran en el ranking ni pueden ser el mejor modelo.
- B4, 4 modelos sin precio: 0 fallos en 18.840 días de disco. No tienen coste.
- B4, 2020, 16 TB: ningún modelo pasa el mínimo; coste real de 7.450 dólares.
- B4, 2020, 18 TB: ningún modelo pasa el mínimo; coste real de 1.417 dólares.
- B4, 2021, 18 TB: ningún modelo pasa el mínimo; coste real de 3.487 dólares.
- B4, 2022, 18 TB: ningún modelo pasa el mínimo; coste real de 3.461 dólares.
- B4, 2023, 18 TB: ningún modelo pasa el mínimo; coste real de 3.640 dólares.
- B4, 2023, 20 TB: ningún modelo pasa el mínimo; coste real de 23 dólares.
- B4, 2024, 18 TB: ningún modelo pasa el mínimo; coste real de 3.103 dólares.
- B4, 2024, 24 TB: ningún modelo pasa el mínimo; coste real de 2.088 dólares.
- B4, 2025, 18 TB: ningún modelo pasa el mínimo; coste real de 1.623 dólares.
- B4, 42 modelos sin ningún año de edad con 20 fallos o más: su curva no tiene base y no dan vida real.
- B4, ST14000NM000J: 2 fallos en 55.394 días de disco, menos de 20. Sale con su coste, 2,1075 dólares por TB y año, pero sin puesto (cuestión 012).
- B4, ST12000NM000J: 17 fallos en 332.279 días de disco, menos de 20. Sale con su coste, 2,1890 dólares por TB y año, pero sin puesto (cuestión 012).
- B4, ST8000NM000A: 2 fallos en 139.294 días de disco, menos de 20. Sale con su coste, 2,4281 dólares por TB y año, pero sin puesto (cuestión 012).
- B4, ST16000NM002J: 6 fallos en 425.347 días de disco, menos de 20. Sale con su coste, 2,5229 dólares por TB y año, pero sin puesto (cuestión 012).
- B4, ST6000DX000: 15 fallos en 1.389.650 días de disco, menos de 20. Sale con su coste, 5,5913 dólares por TB y año, pero sin puesto (cuestión 012).
- B9, 2021T3: 685 discos del primer día sin ninguna tasa, porque su año de edad no tiene días de disco antes del trimestre; entran con previsto 0.
- B9, 2022T3: 681 discos del primer día sin ninguna tasa, porque su año de edad no tiene días de disco antes del trimestre; entran con previsto 0.
- B9, 2023T3: 681 discos del primer día sin ninguna tasa, porque su año de edad no tiene días de disco antes del trimestre; entran con previsto 0.

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

Cada cifra se rehízo por otro camino. Las segundas vías:

| Cifra | Primera vía | Segunda vía | Comparación | Coinciden |
|---|---|---|---|---|
| días de disco por modelo y año | recuento_diario_corregido | modelo_trimestre | exacta, 299 claves, diferencia mayor 0 | sí |
| fallos por modelo y año | recuento_diario_corregido | modelo_trimestre | exacta, 299 claves, diferencia mayor 0 | sí |
| coste de los fallos por modelo y año, en dólares | fallos del recuento × (capacidad en GB × coste_gb de dim_precio_gb + 37) | modelo_trimestre (suma de coste_fallos_usd) | diferencia menor que 1e-06, 299 claves, diferencia mayor 0 | sí |
| coste por TB y año de cada modelo del ranking, en dólares | recuento_diario_corregido + dim_precio_gb (fórmula de las reglas, apartado 6) | modelo_trimestre | diferencia menor que 1e-06, 32 claves, diferencia mayor 0 | sí |
| coste por TB y año a igual edad de cada modelo, en dólares | recuento_diario_corregido + dim_precio_gb, con la tasa a igual edad del 09 | modelo_trimestre, con la tasa a igual edad del 09 | diferencia menor que 1e-06, 32 claves, diferencia mayor 0 | sí |
| diferencia con el mejor modelo por año y capacidad, en dólares | recuento_diario_corregido + dim_precio_gb | modelo_trimestre | diferencia menor que 1e-06, 46 claves, diferencia mayor 5,0e-10 | sí |
| capacidad media del año, en TB | recuento_diario_corregido × capacidad de dim_modelo | modelo_trimestre | diferencia menor que 1e-06, 2 claves, diferencia mayor 0 | sí |
| primeros fallos por modelo y año de edad (tabla de vida) | vida_discos, disco a disco | vida_discos, vectorizada por año de edad | exacta, 671 claves, diferencia mayor 0 | sí |
| puesto dentro de capacidad y año de compra de cada modelo | recuento_diario_corregido + dim_precio_gb | modelo_trimestre | exacta, 27 claves, diferencia mayor 0 | sí |
| años de exposición por modelo y año de edad (tabla de vida) | vida_discos, disco a disco | vida_discos, vectorizada por año de edad | diferencia menor que 0.001, 671 claves, diferencia mayor 5,0e-04 | sí |
| fallos reales por trimestre y capacidad | recuento_diario_corregido | fallos_detalle | exacta, 157 claves, diferencia mayor 0 | sí |
| discos el primer día de cada trimestre, por capacidad | recuento_diario_corregido | inicio_trimestre | exacta, 186 claves, diferencia mayor 0 | sí |
| fallos previstos por trimestre y capacidad | dias_por_tramo, fila a fila con diccionarios | dias_por_tramo, agregado y unido por clave | diferencia menor que 1e-06, 157 claves, diferencia mayor 0 | sí |
| error absoluto ponderado de las variantes de sensibilidad | fila a fila con diccionarios | agregado y unido por clave | diferencia menor que 1e-06, 4 claves, diferencia mayor 0 | sí |
| fallos de discos que aparecen después del primer día de su trimestre, por trimestre | fotos_mensuales_corregido + ventanas_fallo_corregido (primera fecha de cada disco) | vida_discos (primera_aparicion) | exacta, 18 claves, diferencia mayor 0 | sí |

## Parámetros usados

- mínimo de días de disco en el año para un ranking y para el mejor modelo: 50.000 (reglas-negocio §7; sustituye al mínimo de 30 casos de el método).
- mínimo de días de disco de una celda de tasa en la previsión: 50.000 (criterio técnico 5, con el mínimo de las reglas, apartado 7).
- vida contable: 6 años (reglas-negocio §3 y §6, cuestión 001).
- coste de un cambio: 37 dólares (reglas-negocio §6, cuestión 002).
- disco nuevo de un fallo: misma capacidad al coste por GB del año del fallo (dim_precio_gb) (reglas-negocio §6).
- horas de técnico por cambio: 0,74 (reglas, apartado 5, doc. 12b).
- coste de un modelo en todo el periodo: solo sus celdas de modelo y año que pasan el mínimo (criterio técnico 1, en la petición).
- intervalo del coste: la parte de los fallos con el intervalo exacto de Poisson de la tasa (petición, B4.1).
- vida real: edad a la que S baja de 0,5 en la tabla de vida, con la curva cortada antes del primer año de edad con menos de 20 fallos (criterio técnico 2, en la petición, con el método de la petición 13).
- mejor modelo de una capacidad y año: el de menor coste por TB y año entre los que pasan el mínimo; empates, por nombre (criterio técnico 3, en la petición).
- ingreso por TB: «Total revenue» del doc. 16 / capacidad media del año (días × capacidad / días del año en los datos) (criterio técnico 4, en la petición; reglas, apartado 6).
- tasa de la previsión: modelo y edad, capacidad y edad, o edad, con los meses anteriores al primer día del trimestre y toda la historia (criterio técnico 5, en la petición; reglas, apartado 7).
- filas de dias_por_tramo sin días de disco: cuentan 0 días, y sus fallos entran en la tasa (reglas de transformación §6 (los fallos de una fila sin días están en «fallos»); criterio, el mismo de las sumas por grupo de pandas, que dejan fuera el vacío).
- primer trimestre previsto: 2021T1 (plan, bloque 9; petición: tiene al menos un año de tasas detrás).
- medida de la previsión: error absoluto ponderado de todos los trimestres y capacidades a la vez, con el sesgo al lado (reglas-negocio §7, cuestión 011).
- confianza de los intervalos: 0,95 (parametros.md de el método y 42.6 del manual).
- tolerancia de las segundas vías en importes y cifras con decimales: 1e-06 (petición, «SEGUNDA VÍA»; en los años de exposición de la tabla de vida, 0,001 años, por el redondeo de sumar cientos de miles de discos en distinto orden (criterio).
- mínimo de fallos para tener puesto en el ranking de coste: 20 (reglas-negocio §7, cuestión 012; petición 17: con menos, el modelo sale con su coste y sin puesto, y el resumen del ranking se calcula sin él).
- coste a igual edad: amortización + tasa a igual edad / 100 × coste medio de un fallo del modelo × días de disco / 365 / terabytes-año, con la tasa a igual edad del ranking de B2 de informes/indicadores__discos_modelos_edad.json (petición 17, B4.2; reglas, apartado 7, «Una tasa por modelo se compara a igual edad»).
- sensibilidad al precio inferido: el precio de los modelos con origen «inferido» × 0,8 y × 1,2; cambia solo la amortización (el disco nuevo de un fallo sale de dim_precio_gb); con los modelos con puesto, cuántos de los 10 primeros siguen y cuál es el primero (criterio técnico, en la petición 17 (B4.3)).
- puesto del ranking de coste: dentro de cada capacidad y año de compra (el año de fecha_compra de dim_modelo), con cuestión 012; el puesto de todos juntos, al lado, con su resumen (reglas-negocio §7 («El coste por TB y año se ordena dentro de cada capacidad y año de compra», el responsable del caso, 18/11/2026); petición 19).
- tasa a igual edad del 09: la de cada año de edad y trimestre, con φ (petición 19) (petición 19; el script para si el JSON del 09 no trae φ).
- semilla: no aplica (ningún cálculo usa azar).

## Datos personales

- No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección, porque no traen datos de personas.
- No hay datos de personas (reglas-negocio §9): el número de serie identifica un disco, no a una persona.
- Este cálculo usa el número de serie solo para unir los fallos con la primera aparición de su disco y no deja ninguno en el JSON ni en el informe.

## Límites

- Las cifras describen el periodo del 01/01/2020 al 30/06/2025. Ninguna dice por qué un modelo cuesta más o por qué la previsión falla: solo valen verbos de asociación.
- El precio no está en los datos. Sale de la tabla de precios por capacidad y año de compra, inferida desde 2023, y 5 de los diez primeros del ranking lo tienen inferido. El coste y el mejor modelo valen lo que valgan esos precios.
- Dos modelos de la misma capacidad comprados el mismo año tienen el mismo precio, así que entre ellos el orden lo pone solo la tasa de fallo.
- 5 modelos tienen menos de 20 fallos y salen sin puesto (cuestión 012); su coste está en la tabla, pero no se ordena.
- El coste a igual edad depende de la tasa a igual edad del 09: si el 09 cambia, este coste cambia con él. La sensibilidad al precio inferido solo mueve la amortización.
- La cifra con garantía usa la garantía de la ficha de cada fabricante y la edad al fallar por horas encendido; si Backblaze reclama la garantía no consta (cuestión 005).
- 2025 tiene seis meses: su fila del mejor modelo no se compara con un año entero.
- El ingreso por TB es un orden de magnitud: la capacidad incluye paridad y espacio libre. El de 2025 necesita la reserva.
- La previsión no ve 413 fallos de 15.689 (2,63 %), de discos que entran después del primer día de su trimestre; es la regla de las reglas, apartado 7, y la referencia sí los cuenta.
- La sensibilidad es solo para leer: cambiar la regla de la tasa después de ver el resultado sería elegir la regla para que salga bien.
- Ninguna cifra se ha medido en la reserva, del 01/07/2025 al 30/06/2026 (reglas, apartado 5). La prueba final de la previsión usará la misma función, prever_trimestre, en esos cuatro trimestres.
- Pendiente: el auditor sin memoria del cierre del paso (método §8) necesita el sí de el responsable del caso, porque es un agente.

