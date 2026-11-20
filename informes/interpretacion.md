---
titulo: Interpretación del caso 68 · qué permiten decidir las cuatro preguntas, con cuánta confianza y hasta dónde llegan
estado: escrito por el analista el 19/11/2026 (paso 6, punto 2 del guion del informe final aprobado por el responsable del caso ese día); pendiente de que el responsable del caso lo lea
fecha_documento: 2026-11-19
fecha_datos: 2025-06-30
dueno: El responsable del caso (decide)
destinatario: El responsable del caso y quien redacte el informe final para la dirección de operaciones. Es la base del informe; la dirección no lo lee
fuentes: `config/negocio/01_ficha_del_caso.md` («El problema»); `config/metodo/04_planteamientos.md`; `config/metodo/06_borrador_de_hallazgos.md` (B1 a MC y MOD); los JSON y los informes de `informes/` citados en cada cifra
---

# El coste por terabyte lo decide sobre todo el precio de compra y el modelo de riesgo encuentra 32 fallos al mes en su lista de 100 discos frente a 16 de la regla de los cinco avisos SMART

## Pregunta y objetivo

El caso sirve para reducir costes: el coste anual de guardar cada terabyte, con lo que cuestan los fallos incluido
(ficha, «Objetivo y palancas»). Contesta cuatro preguntas:

1. qué modelo de disco sale más barato por TB y año en cada capacidad;
2. a partir de qué año de vida sube la tasa de fallo;
3. si hay centros de datos o tomos con más fallos de los que les tocan;
4. qué discos tienen más riesgo de fallar en los próximos 30 días.

El dinero está en la pregunta 1. La 4 no ahorra dinero: ordena el trabajo de los técnicos y avisa del riesgo de perder
datos (ficha, «El dinero está en la principal»).

**Conclusión principal.** Para reducir costes, lo que más pesa es el precio por TB del modelo que se compra: los fallos son
una parte pequeña del coste. Dentro de una misma capacidad y año de compra hay un modelo más barato en los 7 grupos que
se pueden comparar. La edad, el centro y los avisos SMART no cambian esa compra, pero sí dicen qué vigilar. Para eso el
modelo de riesgo mejora a la regla de los cinco avisos SMART, la referencia con la que se compara; los datos no dicen si Backblaze la usa.

## Grandes números

- **Los fallos son el 6,44 % del coste por TB y año** en la mediana de los 27 modelos con puesto · `indicadores__coste_prevision.json`, `preguntas[B4].tablas.resumen_ranking.mediana_parte_fallos_pct`
- **Los 2.044.860 dólares de 2024 no son un ahorro que se pueda prometer.** Es lo que habrían costado de menos ese año los discos en servicio con el modelo más barato de cada capacidad. La mayor parte (1.892.334) sale de comparar precios de años de compra distintos. Por eso el informe final no la usa: compara dentro de cada capacidad y año de compra (corrección del 19/11/2026, tras la revisión del auditor) · `preguntas[B4].tablas.mejor_modelo.por_ano[ano=2024]`
- **La tasa de fallo pasa del 0,79 % con 0 años cumplidos al 2,58 % con 5,** y sube en los años 2, 3, 4 y 5 con intervalos que no se solapan · `indicadores__discos_modelos_edad.json`, `preguntas[B3].tablas.tasa_por_edad`
- **En la validación, la lista de los 100 discos de más riesgo del modelo encuentra 32,17 fallos al mes; la de la regla 15,83.** La diferencia es de 16,33, con un intervalo de 14,00 a 18,92 · `modelado.json`, `validacion.por_mes` e `.intervalo`
- **La previsión de fallos por trimestre no gana a repetir el trimestre anterior** (error de 0,2670 frente a 0,2504): se usa la referencia · `indicadores__coste_prevision.json`, `preguntas[B9].tablas.error`

## La historia

**Pregunta 1, el coste.** El ranking de coste por TB y año ordena 27 modelos. Se parece poco al de la tasa de fallo
(correlación de Spearman de 0,495), porque los fallos pesan poco frente al precio (B4). Por eso el puesto se da dentro de
cada capacidad y año de compra: hay 19 grupos y solo 7 tienen dos modelos o más que comparar. En esos 7 hay un modelo más
barato; por ejemplo, en 14 TB de 2020 el TOSHIBA MG07ACA14TA cuesta 2,7967 dólares por TB y año, frente a 3,5818 del
ST14000NM0138, el modelo que más falla (B4). Comparar con la tasa a igual edad casi no cambia el orden (Spearman de 0,996).

**Pregunta 2, la edad.** La tasa sube con la edad de forma clara hasta los 5 años. A los 8 baja al 1,90 %, pero esa
bajada describe a los discos que han aguantado; si se debe a eso no se puede saber (B3 y límites del informe de
indicadores). Comparar modelos sin igualar la edad engaña: el TOSHIBA MG08ACA16TA parece fallar poco (1,15 % bruto)
porque es joven. A igual edad queda por encima del conjunto de discos (razón de 1,386) (B2).

**Pregunta 3, centros y tomos.** Con la misma mezcla de modelo, edad y trimestre, sac2 falla más que los demás centros
(razón de 1,100) y sac0 menos (0,906); phx1, ams5 e iad1 no se distinguen (B5). Antes de igualar la mezcla, sac0 parecía
peor que phx1: la diferencia bruta va con la mezcla de cada centro. En los tomos, 489 tienen dos fallos o más en 30
días, frente a 436,9 de media si los días se reparten al azar dentro de cada centro y trimestre, con un percentil 95 de
456 (B7). Los fallos de un mismo tomo van más juntos de lo que daría el azar. Los datos no dicen por qué.

**Pregunta 4, los discos de más riesgo.** Hoy la referencia es la regla de los cinco avisos SMART. Se compararon tres
algoritmos y ganó el HistGradientBoosting, con 36,13 fallos al mes en la lista de 100 frente a 20,47 de la regla, por
delante en los cinco bloques de la comparación (MOD). Abierta una sola vez, la validación lo confirma con datos que el
modelo no había visto: 32,17 fallos al mes frente a 15,83, por delante los 12 meses; un AUC de 0,898 frente a 0,846. Lo
que más pesa en el modelo son los propios avisos SMART y cómo cambian de un mes a otro (MOD). El centro de datos no
aporta. Las cuatro variables nuevas que se probaron tampoco (MOD).

**La previsión por trimestre.** La cuenta por modelo y edad prevé de más y no gana a repetir los fallos del trimestre
anterior. Ninguna de sus cuatro variantes gana (B9). Para comprar repuestos se usa la referencia.

## Nivel de confianza

**Pregunta 1, media.** A favor: 32 modelos pasan el mínimo de 50.000 días de disco al año, el orden casi no cambia a
igual edad y los primeros puestos se mantienen con el precio inferido un 20 % más bajo (siguen los 10 primeros) y un 20 %
más alto (siguen 8) (B4). En contra: el precio no está en los datos y desde 2023 es inferido; 5 de los 10 primeros lo
tienen inferido. Si Backblaze reclama la garantía no consta. Por eso el coste se da con y sin ella (B4; cuestión 005).

**Pregunta 2, alta para el conjunto de discos de 0 a 5 años.** Más de 1.200 fallos en cada año de edad de 0 a 7 (ficha,
veredicto), intervalos ensanchados con φ que siguen sin solaparse (B3). Baja para los años 8 y siguientes: contar como
fallo a los discos que desaparecen avisando cambia la lectura en los años 1, 4, 7 y 8 (B3).

**Pregunta 3, media para los centros y media para los tomos.** Centros: dos años de datos (el sitio solo consta desde el
01/07/2023), la lectura no cambia al quitar los modelos uno a uno y solo 21 modelos están en dos centros o más (B5).
Tomos: 489 frente a un percentil 95 de 456 es una diferencia corta, en 200 repeticiones (B7).

**Pregunta 4, alta para la lista de riesgo, baja para la probabilidad.** La lista: validación abierta una vez, sobre
12 meses y 4.304 fallos, con el intervalo de la diferencia lejos de cero y el modelo por delante cada mes; el canario con
el objetivo barajado da 1 fallo en la lista, así que el modelo no aprende del azar (`modelado.json`, `canario`). La
probabilidad media recalibrada se desvía más del 20 % de la tasa real en dos de los cinco bloques de la competición. En
la validación se queda entre un 13,7 % por debajo y un 35,6 % por encima de lo observado según el quinto de riesgo
(MOD). Sirve para ordenar discos, no para contar cuántos van a fallar.

**Lo que no se pudo comprobar:** ninguna cifra se ha medido en la reserva, del 01/07/2025 al 30/06/2026, que se abre al
cerrar el caso; y el auditor sin memoria del cierre de cada paso analítico no se lanzó, porque necesita el sí del responsable del caso
(límites de los tres informes de indicadores).

## Lo que no se puede afirmar

- **Causas.** Ninguna cifra dice por qué un modelo, una edad, un centro o un tomo falla más. Que un contador SMART pese en
  el modelo no dice que cause el fallo. Que los discos más calientes que la mediana de su modelo vayan con más fallos
  (B8) tampoco dice que el calor los cause.
- **Totales sin segmentos.** Comparar fabricantes o capacidades mezcla edades (B2, MC): esas cifras no se usan para
  decidir. El coste se compara dentro de cada capacidad y año de compra; los centros, a igual mezcla.
- **El precio.** El mejor modelo de cada grupo vale lo que valga el precio inferido desde 2023.
- **El ahorro de 2024.** Los 2.044.860 dólares mezclan años de compra: salen sobre todo de comparar el precio de discos
  comprados en años distintos. No miden lo que se ahorraría comprando hoy. El informe final no los usa.
- **Fallos sin aviso.** El modelo no ve los fallos que llegan sin aviso: el 25,1 % de los fallos con día anterior llega
  sin aviso ese día, aunque esa parte baja del 40,3 % en 2020 al 17,9 % en 2025 (B6).
- **Generalización y deriva.** Todo vale para los discos de datos de Backblaze de enero de 2020 a junio de 2025. Si
  cambian los modelos de disco que se compran o los centros, el modelo de riesgo puede perder rendimiento.
- **Modelos que no se distinguen.** Entre los tres algoritmos sí hay ganador pliegue a pliegue: 7,93 fallos más al mes que
  la logística (desviación 0,83) y 6,76 más que el bosque (2,68) (MOD). Las cuatro variables nuevas no se distinguen de
  no ponerlas (+0,60, desviación 1,52).
- **Los tomos.** Que los fallos vayan juntos en un tomo no separa si es porque sus discos son de la misma tanda y
  envejecen a la vez (B7).

## Decisión que permite

- **Comprar, dentro de cada capacidad, el modelo de menor coste por TB y año del ranking,** con su tasa de fallo a igual
  edad al lado. Lo decide quien compra los discos, en la siguiente compra. Se mide cada trimestre con la misma cifra, el
  coste por TB y año y con la tasa de fallo de los modelos nuevos en su primer año (ficha, «La cifra que mide valor»).
  Antes de usar un puesto con precio inferido, conviene confirmar ese precio.
- **Vigilar más los discos a partir de los 2 años y los de sac2,** sin cambiar ningún disco por la edad o el centro: no
  hay cifra que diga que cambiarlos antes salga a cuenta (ficha: la secundaria no da dinero; cuestión 008).
- **Usar la lista mensual del modelo en lugar de la regla de los cinco avisos SMART** para ordenar el trabajo de los
  técnicos. El tamaño de la lista lo elige Backblaze según lo que puedan atender sus técnicos. Se cambia sin
  reentrenar. Con lo medido en la validación, el modelo encuentra al mes 9,40 fallos en la lista de 20, 32,17 en la de
  100, 87,83 en la de 500 y 132,08 en la de 1.000; la regla, 3,67, 15,83, 42,44 y 70,64 (MOD). Una lista más larga
  encuentra más fallos y pide más horas de técnico. No se da en dólares, porque acertar un fallo no ahorra dinero: el disco se cambia una vez,
  antes o después (ficha, «La valoración»). Se pone en marcha en el paso 7 (preproducción y despliegue) y se vigila
  mes a mes con los fallos encontrados en la lista.
- **Para comprar repuestos, repetir los fallos del trimestre anterior,** no la previsión del caso (B9).

## Cifras pendientes

- **Fallos señalados en tomos donde acaba de fallar un disco,** del modelo frente a la regla y la correlación de
  Matthews: los planteamientos (1.C) los piden al lado de la medida principal y no están en `modelado.json`. Los
  produciría el script del modelo (`aprendizaje-automatico`) o la preproducción.
- **Las horas de técnico de cada tamaño de lista:** no constan (cuestión 010); sin ellas no se puede recomendar un tamaño.
- **El precio real de cada modelo desde 2023:** no está en los datos.
- **La reserva, del 01/07/2025 al 30/06/2026:** la prueba final del modelo y de la previsión, al cerrar el caso.

## Fuentes

- `config/negocio/01_ficha_del_caso.md` y `config/metodo/04_planteamientos.md`
- `config/metodo/06_borrador_de_hallazgos.md`, bloques B2 a B9, MC y MOD
- `informes/indicadores__discos_modelos_edad.json` y `.md`, de `scripts/09_indicadores_discos_modelos_edad.py`
- `informes/indicadores__coste_prevision.json` y `.md`, de `scripts/10_indicadores_coste_prevision.py`
- `informes/indicadores__centros_avisos_tomos.json` y `.md`, de `scripts/11_indicadores_centros_avisos_tomos.py`
- `informes/modelado.json`, de `scripts/15_modelado.py`
- `informes/variables_nuevas.json`, de `scripts/16_variables_nuevas.py`

## Límite de este documento

Solo interpreta lo que traen los informes anteriores y hereda sus límites. No calcula ninguna cifra nueva: cada cifra
está en el borrador de hallazgos o en el JSON citado. Los apartados «Límites» de los tres informes de indicadores y la
lista `limites` de `modelado.json` siguen valiendo enteros; aquí van solo los que cambian una decisión.
