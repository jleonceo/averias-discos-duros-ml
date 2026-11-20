# Preselección de variables

La logística queda con 25 de sus 62 variables (169 columnas en el ajuste con la muestra), por consenso amplio y con las cuatro obligatorias; los árboles reciben sus 64 columnas sin votar. La segunda muestra da otra lista aun con la muestra entera: el detalle está en «intentos».

## ¿Hacía falta?

En la regresión logística sí. Es un modelo lineal: scikit-learn no da la significación de cada coeficiente y el tope de columnas obliga (método §1), y el responsable del caso lo fijó en las reglas, apartado 7 el 18/11/2026. El bosque y el HistGradientBoosting no se preseleccionan por votación y reciben las 64 columnas de la matriz.

La muestra de partida tiene 232.243 fotos: las 11.962 con fallo y 220.281 sanas, el 2 % de cada mes.
La preselección usó 232.243 de ellas, de 2020-01-01 a 2024-06-01, la muestra entera.
Con la segunda muestra, sorteada con semilla 43, la lista final cambia; el detalle de cada intento está en el JSON.

## Lo que no podía entrar

Entran a la logística 62 variables de la matriz, que el preprocesador del script 13 convierte en 496 columnas con la muestra de partida. Ninguna es un identificador, el objetivo ni una de las que la matriz deja fuera: la validación 5 lo comprueba.
Ninguna variable vale lo mismo para todas las fotos de una fecha.

## Alarmas de fuga

Ninguna variable sola llega a |2·AUC − 1| de 0,90, el umbral de posible fuga del exploratorio del caso. La que más separa es contadores_que_avisan, con un AUC de 0,801.

## Cómo se votó

Modo comparativo y escenario de consenso amplio, fijado por el responsable del caso antes de ver el resultado: entra una variable si la marcan dos o más de los tres métodos. La unidad de voto es la variable de origen: recibe el voto de un método si alguna de sus columnas pasa su corte, y entra o sale con todas.

Entran siempre, sin votar: smart_5_raw, smart_187_raw, smart_197_raw, smart_198_raw, para poder explicar la lista a los técnicos con lo que ya vigilan.

- En información mutua, el mayor salto va de 0,00000 a 0,00000, un cociente de 2,12; pasan 492 columnas.
- En importancia por permutación, el mayor salto va de 0,00000 a 0,00000, un cociente de 3,65; pasan 243 columnas.
- En RFECV pasan las 496 columnas de ranking 1.

| Variable | Votos | Puesto combinado | Información mutua | Permutación | Ranking RFECV | Obligatoria |
|---|---|---|---|---|---|---|
| contadores_que_avisan | 3 | 1 | 0,01845 | 0,14554 | 1 | no |
| cambio_smart_187 | 3 | 2 | 0,00867 | 0,00567 | 1 | no |
| cambio_smart_197 | 3 | 3 | 0,01008 | 0,00325 | 1 | no |
| cambio_smart_5 | 3 | 4 | 0,00547 | 0,00711 | 1 | no |
| smart_188_no_cero | 3 | 5 | 0,00397 | 0,00558 | 1 | no |
| cambio_smart_198 | 3 | 6 | 0,01001 | 0,00061 | 1 | no |
| smart_184_raw | 3 | 7 | 0,00254 | 0,00227 | 1 | no |
| fabricante | 3 | 8 | 0,00137 | 0,00217 | 1 | no |
| model | 3 | 9 | 0,00135 | 0,00261 | 1 | no |
| capacidad_tb | 3 | 10 | 0,00111 | 0,00223 | 1 | no |
| smart_198_raw | 3 | 11 | 0,01091 | 0,00165 | 1 | sí |
| smart_12_raw | 3 | 12 | 0,00175 | 0,00076 | 1 | no |
| smart_187_raw | 3 | 13 | 0,00846 | 0,00030 | 1 | sí |
| smart_197_raw | 3 | 14 | 0,00705 | 0,00090 | 1 | sí |
| smart_193_raw | 3 | 15 | 0,00120 | 0,00246 | 1 | no |
| smart_240_raw | 3 | 16 | 0,00190 | 0,00691 | 1 | no |
| smart_2_normalized | 3 | 17 | 0,00291 | 0,00447 | 1 | no |
| smart_5_raw | 3 | 18 | 0,01025 | 0,00174 | 1 | sí |
| garantia_anos | 3 | 19 | 0,00146 | 0,00015 | 1 | no |
| smart_1_normalized | 3 | 20 | 0,00154 | 0,00121 | 1 | no |
| datacenter | 3 | 21 | 0,00030 | 0,00102 | 1 | no |
| smart_4_raw | 3 | 22 | 0,00213 | 0,00239 | 1 | no |
| suma_contadores_sin_188 | 3 | 23 | 0,01463 | 0,00116 | 1 | no |
| smart_192_normalized | 3 | 24 | 0,00077 | 0,00070 | 1 | no |
| smart_198_normalized | 3 | 25 | 0,00605 | 0,00011 | 1 | no |
| smart_189_raw | 3 | 26 | 0,00254 | 0,00001 | 1 | no |
| edad_anos | 3 | 27 | 0,00097 | 0,00010 | 1 | no |
| smart_241_raw | 3 | 28 | 0,00237 | 0,00058 | 1 | no |
| smart_3_normalized | 3 | 29 | 0,00109 | 0,00336 | 1 | no |
| smart_195_normalized | 3 | 30 | 0,00217 | 0,00002 | 1 | no |
| smart_193_normalized | 3 | 31 | 0,00089 | 0,00025 | 1 | no |
| smart_196_normalized | 2 | 32 | 0,00291 | 0,00000 | 1 | no |
| smart_242_raw | 3 | 33 | 0,00171 | 0,00033 | 1 | no |
| smart_183_raw | 2 | 34 | 0,00122 | 0,00000 | 1 | no |
| smart_192_raw | 3 | 35 | 0,00051 | 0,00032 | 1 | no |
| smart_196_raw | 3 | 36 | 0,00130 | 0,00012 | 1 | no |
| smart_22_normalized | 3 | 37 | 0,00063 | 0,00173 | 1 | no |
| smart_194_raw | 3 | 38 | 0,00061 | 0,00033 | 1 | no |
| smart_194_normalized | 3 | 39 | 0,00113 | 0,00009 | 1 | no |
| smart_191_normalized | 3 | 40 | 0,00081 | 0,00006 | 1 | no |
| smart_223_raw | 3 | 41 | 0,00061 | 0,00098 | 1 | no |
| smart_5_normalized | 3 | 42 | 0,00318 | 0,00014 | 1 | no |
| smart_7_raw | 3 | 43 | 0,00070 | 0,00176 | 1 | no |
| smart_9_normalized | 3 | 44 | 0,00163 | 0,00040 | 1 | no |
| smart_191_raw | 3 | 45 | 0,00034 | 0,00011 | 1 | no |
| smart_8_normalized | 3 | 46 | 0,00121 | 0,00064 | 1 | no |
| smart_220_raw | 3 | 47 | 0,00041 | 0,00041 | 1 | no |
| smart_3_raw | 3 | 48 | 0,00059 | 0,00113 | 1 | no |
| smart_199_normalized | 2 | 49 | 0,00137 | −0,00055 | 1 | no |
| meses_desde_foto_anterior | 3 | 50 | 0,00006 | 0,00002 | 1 | no |
| smart_1_raw | 3 | 51 | 0,00018 | 0,00017 | 1 | no |
| smart_222_raw | 3 | 52 | 0,00013 | 0,00025 | 1 | no |
| smart_2_raw | 3 | 53 | 0,00071 | 0,00014 | 1 | no |
| smart_226_raw | 3 | 54 | 0,00011 | 0,00031 | 1 | no |
| smart_195_raw | 3 | 55 | 0,00024 | 0,00001 | 1 | no |
| smart_8_raw | 3 | 56 | 0,00128 | 0,00003 | 1 | no |
| smart_199_raw | 3 | 57 | 0,00001 | 0,00007 | 1 | no |
| smart_200_normalized | 3 | 58 | 0,00017 | 0,00006 | 1 | no |
| smart_7_normalized | 3 | 59 | 0,00045 | 0,00019 | 1 | no |
| smart_24_normalized | 2 | 60 | 0,00048 | 0,00000 | 1 | no |
| smart_22_raw | 2 | 61 | 0,00016 | 0,00000 | 1 | no |
| smart_90_raw | 1 | 62 | 0,00000 | 0,00000 | 1 | no |

Las cifras de los modelos auxiliares solo ordenan: no se citan como rendimiento.

## Una variante por variable

En la logística cada variable tiene una sola rama: sus tramos, con el vacío cuando es tramo propio, o una columna por categoría. Cada variable es una familia y entra o sale entera; no hay alternativas entre las que elegir.

## Las que dicen lo mismo

Estos pares llegan a 0,5. De cada uno sale la de menos información mutua, salvo que la otra sea obligatoria, que gana el par:

- smart_195_raw y smart_1_raw, Spearman 1,000 con las 65.072 fotos que tienen dato en las dos: sale smart_1_raw (menos información mutua).
- smart_196_raw y smart_5_raw, Spearman 1,000 con las 111.223 fotos que tienen dato en las dos: sale smart_196_raw (la otra es obligatoria y gana el par).
- fabricante y smart_199_normalized, V de Cramér 1,000 con las 232.181 fotos que tienen dato en las dos: sale smart_199_normalized (menos información mutua).
- fabricante y smart_240_raw, V de Cramér 1,000 con las 167.257 fotos que tienen dato en las dos: sale fabricante (menos información mutua).
- model y smart_199_normalized, V de Cramér 1,000 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y model, V de Cramér 0,999 con las 231.123 fotos que tienen dato en las dos: sale model (menos información mutua).
- garantia_anos y smart_8_raw, V de Cramér 0,999 con las 111.071 fotos que tienen dato en las dos: sale smart_8_raw (menos información mutua).
- fabricante y model, V de Cramér 0,999 con las 232.243 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_12_raw y smart_4_raw, Spearman 0,996 con las 232.181 fotos que tienen dato en las dos: sale smart_12_raw (menos información mutua).
- edad_anos y smart_222_raw, Spearman 0,993 con las 46.299 fotos que tienen dato en las dos: sale smart_222_raw (menos información mutua).
- smart_222_raw y smart_9_normalized, Spearman 0,992 con las 46.299 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y model, V de Cramér 0,990 con las 232.243 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_8_normalized y smart_8_raw, V de Cramér 0,978 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y smart_8_normalized, V de Cramér 0,968 con las 111.071 fotos que tienen dato en las dos: sale smart_8_normalized (menos información mutua).
- fabricante y smart_194_normalized, V de Cramér 0,966 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_2_raw y smart_8_raw, Spearman 0,948 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_199_normalized y smart_3_raw, V de Cramér 0,917 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_22_normalized y smart_22_raw, V de Cramér 0,909 con las 44.313 fotos que tienen dato en las dos: sale smart_22_raw (menos información mutua).
- contadores_que_avisan y suma_contadores_sin_188, Spearman 0,901 con las 232.181 fotos que tienen dato en las dos: sale suma_contadores_sin_188 (menos información mutua).
- smart_194_normalized y smart_199_normalized, V de Cramér 0,900 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_2_normalized y smart_8_normalized, Spearman 0,893 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_199_normalized y smart_2_normalized, V de Cramér 0,882 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_197_raw y smart_198_raw, Spearman 0,871 con las 228.404 fotos que tienen dato en las dos: no sale ninguna (las dos son obligatorias).
- smart_195_raw y smart_1_normalized, Spearman 0,866 con las 65.072 fotos que tienen dato en las dos: sale smart_195_raw (menos información mutua).
- smart_2_normalized y smart_8_raw, Spearman 0,866 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_2_normalized, V de Cramér 0,852 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y smart_2_normalized, V de Cramér 0,846 con las 111.071 fotos que tienen dato en las dos: sale garantia_anos (menos información mutua).
- smart_240_raw y smart_242_raw, Spearman 0,845 con las 120.958 fotos que tienen dato en las dos: sale smart_242_raw (menos información mutua).
- smart_193_raw y smart_240_raw, Spearman 0,844 con las 167.257 fotos que tienen dato en las dos: sale smart_193_raw (menos información mutua).
- edad_anos y smart_242_raw, Spearman 0,842 con las 129.325 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_1_raw y smart_7_normalized, Spearman 0,842 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_3_raw, V de Cramér 0,841 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_240_raw y smart_3_normalized, Spearman 0,841 con las 167.257 fotos que tienen dato en las dos: sale smart_3_normalized (menos información mutua).
- smart_1_raw y smart_7_raw, Spearman 0,837 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_5_raw y suma_contadores_sin_188, Spearman 0,836 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y smart_2_raw, V de Cramér 0,834 con las 111.071 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_normalized y smart_193_raw, Spearman 0,832 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y smart_240_raw, Spearman 0,823 con las 167.257 fotos que tienen dato en las dos: sale capacidad_tb (menos información mutua).
- smart_191_normalized y smart_191_raw, Spearman 0,820 con las 97.117 fotos que tienen dato en las dos: sale smart_191_raw (menos información mutua).
- smart_194_normalized y smart_7_normalized, Spearman 0,817 con las 232.181 fotos que tienen dato en las dos: sale smart_7_normalized (menos información mutua).
- smart_2_normalized y smart_2_raw, Spearman 0,815 con las 111.221 fotos que tienen dato en las dos: sale smart_2_raw (menos información mutua).
- smart_2_raw y smart_8_normalized, Spearman 0,798 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- edad_anos y smart_240_raw, Spearman 0,797 con las 167.257 fotos que tienen dato en las dos: sale edad_anos (menos información mutua).
- smart_194_normalized y smart_1_raw, Spearman 0,796 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_242_raw y smart_9_normalized, Spearman 0,796 con las 129.325 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_8_normalized, V de Cramér 0,795 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_7_normalized y smart_7_raw, V de Cramér 0,794 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_197 y cambio_smart_198, V de Cramér 0,794 con las 221.248 fotos que tienen dato en las dos: sale cambio_smart_198 (menos información mutua).
- smart_199_normalized y smart_8_normalized, V de Cramér 0,787 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_187_raw y suma_contadores_sin_188, Spearman 0,784 con las 120.958 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_194_normalized y smart_7_raw, Spearman 0,783 con las 232.181 fotos que tienen dato en las dos: sale smart_7_raw (menos información mutua).
- garantia_anos y smart_240_raw, V de Cramér 0,774 con las 166.166 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_240_raw y smart_3_raw, Spearman 0,770 con las 167.257 fotos que tienen dato en las dos: sale smart_3_raw (menos información mutua).
- smart_197_raw y smart_198_normalized, V de Cramér 0,770 con las 228.404 fotos que tienen dato en las dos: sale smart_198_normalized (la otra es obligatoria y gana el par).
- smart_196_raw y suma_contadores_sin_188, Spearman 0,757 con las 111.223 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- contadores_que_avisan y smart_196_raw, Spearman 0,757 con las 111.223 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_3_normalized, V de Cramér 0,751 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- contadores_que_avisan y smart_5_raw, Spearman 0,748 con las 232.181 fotos que tienen dato en las dos: sale contadores_que_avisan (la otra es obligatoria y gana el par).
- smart_240_raw y smart_7_raw, Spearman 0,745 con las 167.257 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- model y smart_192_normalized, V de Cramér 0,740 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_normalized y smart_1_normalized, Spearman 0,739 con las 97.117 fotos que tienen dato en las dos: sale smart_191_normalized (menos información mutua).
- smart_191_normalized y smart_7_raw, Spearman 0,738 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y edad_anos, Spearman 0,736 con las 232.243 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_194_normalized y smart_194_raw, V de Cramér 0,734 con las 232.181 fotos que tienen dato en las dos: sale smart_194_raw (menos información mutua).
- smart_1_normalized y smart_1_raw, V de Cramér 0,731 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_normalized y smart_240_raw, Spearman 0,731 con las 167.257 fotos que tienen dato en las dos: sale smart_193_normalized (menos información mutua).
- smart_198_normalized y smart_198_raw, V de Cramér 0,730 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_raw y smart_1_normalized, Spearman 0,729 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_normalized y smart_3_normalized, Spearman 0,725 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_8_normalized y smart_9_normalized, Spearman 0,724 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_3_raw y smart_7_normalized, Spearman 0,722 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_3_raw y smart_7_raw, Spearman 0,721 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_1_raw y smart_3_raw, Spearman 0,721 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_8_raw, V de Cramér 0,717 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_2_raw, V de Cramér 0,714 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- contadores_que_avisan y smart_187_raw, Spearman 0,708 con las 120.958 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_194_normalized y smart_3_normalized, Spearman 0,701 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_raw y smart_7_raw, Spearman 0,698 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y garantia_anos, Spearman 0,697 con las 231.123 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_3_raw y smart_8_normalized, Spearman 0,693 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_raw y smart_3_raw, Spearman 0,692 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y smart_22_raw, V de Cramér 0,691 con las 44.313 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- model y smart_22_raw, V de Cramér 0,691 con las 44.313 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_199_normalized y smart_3_normalized, V de Cramér 0,689 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_191_raw, V de Cramér 0,684 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_194_normalized y smart_240_raw, Spearman 0,679 con las 167.257 fotos que tienen dato en las dos: sale smart_194_normalized (menos información mutua).
- cambio_smart_187 y smart_187_raw, Spearman 0,675 con las 117.408 fotos que tienen dato en las dos: sale cambio_smart_187 (la otra es obligatoria y gana el par).
- smart_241_raw y smart_242_raw, Spearman 0,674 con las 129.325 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- model y smart_8_normalized, V de Cramér 0,671 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y smart_3_normalized, V de Cramér 0,661 con las 231.061 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_199_normalized y smart_8_raw, V de Cramér 0,657 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_3_normalized y smart_7_raw, Spearman 0,655 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_199_normalized y smart_2_raw, V de Cramér 0,651 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_192_raw y smart_8_normalized, Spearman 0,651 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_normalized y smart_193_normalized, Spearman 0,649 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_240_raw y smart_9_normalized, V de Cramér 0,643 con las 167.257 fotos que tienen dato en las dos: sale smart_9_normalized (menos información mutua).
- smart_196_normalized y smart_5_normalized, V de Cramér 0,641 con las 111.223 fotos que tienen dato en las dos: sale smart_196_normalized (menos información mutua).
- model y smart_8_raw, V de Cramér 0,640 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- edad_anos y garantia_anos, Spearman 0,639 con las 231.123 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_5 y smart_5_raw, Spearman 0,639 con las 224.911 fotos que tienen dato en las dos: sale cambio_smart_5 (la otra es obligatoria y gana el par).
- cambio_smart_5 y smart_196_raw, Spearman 0,636 con las 107.503 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_2_normalized y smart_9_normalized, Spearman 0,634 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_raw y smart_1_raw, Spearman 0,633 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- datacenter y model, V de Cramér 0,632 con las 66.435 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_normalized y smart_193_raw, Spearman 0,631 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_198 y smart_198_normalized, V de Cramér 0,629 con las 224.911 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_187_raw y smart_197_raw, Spearman 0,624 con las 120.958 fotos que tienen dato en las dos: no sale ninguna (las dos son obligatorias).
- smart_187_raw y smart_198_raw, Spearman 0,624 con las 120.958 fotos que tienen dato en las dos: no sale ninguna (las dos son obligatorias).
- edad_anos y smart_9_normalized, Spearman 0,624 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_raw y smart_3_normalized, Spearman 0,623 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_191_normalized, V de Cramér 0,618 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_196_normalized y smart_196_raw, V de Cramér 0,617 con las 111.223 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_192_raw y smart_2_raw, Spearman 0,616 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y smart_8_raw, Spearman 0,611 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_1_raw y smart_240_raw, Spearman 0,609 con las 167.257 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_197 y smart_198_normalized, V de Cramér 0,609 con las 221.248 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_normalized y smart_241_raw, Spearman 0,609 con las 50.818 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_raw y smart_241_raw, Spearman 0,608 con las 50.818 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_192_raw y smart_2_normalized, Spearman 0,608 con las 111.221 fotos que tienen dato en las dos: sale smart_192_raw (menos información mutua).
- smart_2_normalized y smart_3_raw, Spearman 0,607 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_2_raw y smart_3_raw, Spearman 0,606 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- contadores_que_avisan y smart_188_no_cero, V de Cramér 0,606 con las 120.965 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_197_raw y suma_contadores_sin_188, Spearman 0,603 con las 228.404 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- model y smart_2_normalized, V de Cramér 0,599 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_normalized y smart_7_raw, Spearman 0,597 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_192_raw y smart_8_raw, Spearman 0,596 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- model y smart_3_raw, V de Cramér 0,595 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_194_normalized y smart_3_raw, Spearman 0,592 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y smart_1_normalized, V de Cramér 0,592 con las 231.061 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_1_raw y smart_3_normalized, Spearman 0,591 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_3_raw y smart_8_raw, Spearman 0,589 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_199_normalized y smart_9_normalized, V de Cramér 0,589 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y smart_3_raw, V de Cramér 0,583 con las 231.061 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_raw y smart_194_normalized, Spearman 0,582 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_raw y smart_7_normalized, Spearman 0,579 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_196_normalized y smart_5_raw, V de Cramér 0,579 con las 111.223 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_7_normalized, V de Cramér 0,577 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y smart_2_raw, Spearman 0,574 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_1_normalized, V de Cramér 0,570 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_1_normalized y smart_7_raw, Spearman 0,567 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_normalized y smart_3_raw, Spearman 0,566 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y smart_191_raw, V de Cramér 0,566 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y smart_2_normalized, V de Cramér 0,566 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y smart_9_normalized, V de Cramér 0,563 con las 231.061 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y smart_189_raw, V de Cramér 0,560 con las 50.818 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- contadores_que_avisan y smart_197_raw, Spearman 0,559 con las 228.404 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_187 y smart_197_raw, Spearman 0,558 con las 117.408 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_187 y smart_198_raw, Spearman 0,558 con las 117.408 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_2_raw y smart_9_normalized, Spearman 0,554 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- garantia_anos y smart_194_normalized, V de Cramér 0,553 con las 231.061 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_193_raw, V de Cramér 0,552 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_187 y cambio_smart_5, Spearman 0,550 con las 117.408 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_191_normalized y smart_1_raw, Spearman 0,548 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_3_normalized y smart_3_raw, Spearman 0,547 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_198_raw y suma_contadores_sin_188, Spearman 0,544 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_198 y smart_198_raw, Spearman 0,539 con las 224.911 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_187 y suma_contadores_sin_188, Spearman 0,539 con las 117.408 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- cambio_smart_5 y suma_contadores_sin_188, Spearman 0,537 con las 224.911 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_187_raw y smart_5_raw, Spearman 0,536 con las 120.958 fotos que tienen dato en las dos: no sale ninguna (las dos son obligatorias).
- smart_242_raw y smart_4_raw, Spearman 0,536 con las 129.325 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_3_normalized y smart_7_normalized, Spearman 0,536 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_8_raw y smart_9_normalized, Spearman 0,534 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_192_raw, V de Cramér 0,534 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y smart_191_normalized, V de Cramér 0,534 con las 97.117 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_12_raw y smart_242_raw, Spearman 0,534 con las 129.325 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_192_normalized y smart_192_raw, V de Cramér 0,525 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- capacidad_tb y fabricante, V de Cramér 0,522 con las 232.243 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- edad_anos y smart_193_normalized, Spearman 0,521 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_7_raw, V de Cramér 0,520 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_192_raw y smart_195_normalized, Spearman 0,520 con las 65.072 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_1_raw, V de Cramér 0,519 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_195_normalized y smart_1_normalized, V de Cramér 0,519 con las 65.072 fotos que tienen dato en las dos: sale smart_1_normalized (menos información mutua).
- capacidad_tb y smart_8_normalized, V de Cramér 0,516 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- fabricante y smart_9_normalized, V de Cramér 0,515 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_raw y smart_8_normalized, Spearman 0,512 con las 111.221 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- contadores_que_avisan y smart_198_raw, Spearman 0,508 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_240_raw y smart_7_normalized, Spearman 0,500 con las 167.257 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).
- smart_193_normalized y smart_1_raw, Spearman 0,500 con las 232.181 fotos que tienen dato en las dos: no sale ninguna (ya resuelto: una del par había salido).

## El tope

Con 11.962 fotos con fallo en entrenamiento, la logística admite como mucho 1.196 columnas. Tras los pares quedaban 169, así que no sale ninguna.

## Las columnas que entran

Entran 25 variables, con 169 columnas en el ajuste con la muestra: cambio_smart_197, datacenter, meses_desde_foto_anterior, smart_183_raw, smart_184_raw, smart_187_raw, smart_188_no_cero, smart_189_raw, smart_192_normalized, smart_195_normalized, smart_197_raw, smart_198_raw, smart_199_raw, smart_200_normalized, smart_220_raw, smart_223_raw, smart_226_raw, smart_22_normalized, smart_240_raw, smart_241_raw, smart_24_normalized, smart_2_normalized, smart_4_raw, smart_5_normalized, smart_5_raw.

El modelado guarda la lista de variables, no la de columnas: los tramos se aprenden en cada ajuste y sus nombres cambian de un pliegue a otro. El preprocesador se monta entero y después se quedan las columnas cuyo origen está en la lista. Por eso fabricante sigue sirviendo de clave a los tramos de smart_1_raw y smart_7_raw aunque no entre, y sus columnas propias solo salen si entra.

## Validaciones

- Nada se ajustó con la validación, que el script no abrió: en verde.
- Cada columna final tiene su variable de origen en la matriz: en verde.
- Ninguna familia quedó a medias: en verde.
- Las columnas finales no pasan del tope: en verde.
- No queda ningún identificador, el objetivo ni una variable que la matriz deja fuera: en verde.
- La lista final no está vacía ni tiene nombres repetidos: en verde.

## Parámetros usados

- Semillas: 42 en la muestra y en los tres métodos; 43 en la segunda muestra. Origen: parametros.md y petición 21.
- Muestra: todas las fotos con fallo y el 2 % de las sanas de cada mes; de ella, los meses más recientes enteros hasta pasar de 100.000 filas; si la lista cambia con la segunda muestra se dobla; si no cabe, se usa entera. Origen: reglas, apartado 7; parametros.md, «filas para muestrear»; nota de la petición 21, punto 5.
- Escenario de votación: consenso amplio, 2 votos o más. Origen: reglas, apartado 7, el responsable del caso, 18/11/2026.
- Obligatorias: smart_5_raw, smart_187_raw, smart_197_raw, smart_198_raw. Origen: reglas, apartado 7, el responsable del caso, 18/11/2026.
- Información mutua: mutual_info_classif con random_state=42 y la máscara de discretas. Origen: metodos.md; petición 21.
- RFECV: RandomForestClassifier(100 árboles, profundidad 5, semilla 42), TimeSeriesSplit(3) por fecha con el horizonte cerrado, step=0.05, min_features_to_select=1, average_precision. Origen: parametros.md; petición 21; nota de la petición 21, punto 3.
- Importancia por permutación: HistGradientBoostingClassifier por defecto con semilla 42 y early_stopping=False; el 80 % más antiguo entrena y el 20 % más reciente mide; 10 repeticiones; average_precision. Origen: parametros.md; petición 21; early_stopping escrito por aprendizaje-automatico §5 y algoritmos.md.
- Corte de información mutua y permutación: salto natural: el mayor cociente entre un valor y el siguiente. Origen: metodos.md, «El corte»; petición 21.
- Umbral de las que dicen lo mismo: Spearman o V de Cramér de 0,5 o más. Origen: parametros.md.
- Alarma de fuga: |2·AUC − 1| de 0,90 o más, con el AUC de la variable sola. Origen: UMBRAL_FUGA de scripts/06_analisis_exploratorio.py, línea 88; nota de la petición 21, punto 4.
- Tope: una columna por cada 10 fotos con fallo de entrenamiento. Origen: método §7.

Los apartados del manual aplicados:

- 36.2 y 36.3: la selección aprende de los datos, así que se hace solo con entrenamiento y sobre una muestra, porque detectar qué variables predicen pide menos filas que ajustar el modelo final.
- 36.5: información mutua con semilla y la máscara de discretas, porque todas las columnas de la logística son 0 y 1.
- 36.6: RFECV con un bosque, que expone importancias, y pliegues por fecha; el paso del 5 % porque con cientos de columnas quitar de una en una es lento.
- 36.7: importancia por permutación sobre filas que el modelo auxiliar no vio, la reserva más reciente de entrenamiento.
- 36.8: votación de los tres métodos, con el corte de los dos que dan un valor por salto natural.
- 36.9 y 5.2: entre las que pasaron, Spearman y V de Cramér para no dejar dos variables que dicen lo mismo en una regresión, donde se reparten el efecto y pueden salir con el signo al revés.

## Datos personales

Los datos son de discos: serial_number identifica un disco, no a una persona (reglas, apartado 9). Esta preselección no lo lee. No usa ni deja ninguna columna de datos personales. No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección porque no hacía falta.

## Límites

- La preselección se hizo una vez, sobre una muestra de entrenamiento, y su lista entra fija en cada pliegue del modelado: la validación cruzada del modelado sale algo optimista (método §9). Cuánto, NO SE PUEDE SABER sin medirlo.
- Los modelos auxiliares van sin búsqueda y solo ordenan; sus cifras no son rendimiento.
- El AUC de cada variable sola se mide en la misma muestra, con el valor en bruto y con cada tramo puntuado por su tasa de fallo: sirve para la alarma, no como medida del modelo.
- El parecido entre dos variables se mide solo con las fotos que tienen dato en las dos, para que el vacío de los contadores que solo registra algún modelo no fabrique parecidos; cada par dice con cuántas filas se midió.

Estado de esta ejecución: AVISO.
