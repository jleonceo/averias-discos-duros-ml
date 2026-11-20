# Los seis problemas del caso 68

**Qué contesta.** Qué modelo de disco sale más barato por terabyte y año contando las averías, a qué edad sube la tasa anual de fallo, qué centros de datos o tomos fallan de más y qué discos tienen más riesgo de fallar en 30 días (`negocio/cuestiones-pendientes.md`).
**Con qué datos.** Backblaze Drive Stats, del 01/01/2020 al 30/06/2025: 14.851.669 fotos mensuales (cada una, el estado de un disco un día del mes) y 17.960 fallos (`calidad-datos.md`). El año siguiente se apartó para la prueba final.
**Con qué método.** Tasas anuales de fallo con su intervalo y un HistGradientBoosting que ordena los discos por riesgo frente a la regla de los cinco avisos SMART (`modelado.md`). Esa regla marca un disco cuando pasa de cero alguno de los cinco contadores de avería (`negocio/reglas-negocio.md`).

Las fuentes están en `informes/` si no se nombra otra carpeta.

## 1. Los datos nunca estarán bien

**Qué se encontró.** El diagnóstico abrió 30 problemas en las cuatro tablas (`calidad-datos.md`, también las tres cifras siguientes). Había 2.729 fotos con una capacidad de -1 o 0,1 TB. Cuatro modelos WDC tenían dos espacios en el nombre, así que el historial de 3.285 discos salía partido en dos modelos. El contador 188 pasaba de mil millones en 192.593 fotos.

**Qué se hizo y por qué.** La corrección aplicó 16 cambios y dejó 23 problemas como estaban, con su motivo (`correccion-datos.md`). A la capacidad errónea se le asignó la de su modelo. Los nombres WDC se juntaron porque eran los mismos números de serie. El 188 solo se usa para saber si vale cero o no. No se rellenó ningún vacío: un contador vacío quiere decir que ese modelo no lo registra.

**Lo que queda abierto.** Las horas encendido bajan 3.468 veces entre dos fotos del mismo disco (`calidad-datos.md`). La corrección cuenta 4.049 fallos sin aviso y la transformación 4.046 (`negocio/reglas-transformacion.md`). Ninguna medida explica esa diferencia.

## 2. No conocerás los datos

**Qué se encontró.** El centro de datos, el vault y la ranura de cada disco solo constan desde el 01/07/2023 (`calidad-datos.md`). Por eso el centro falta en el 71,66 % de las fotos de construcción y en el 4,38 % de las de validación (`analisis-exploratorio__fotos_riesgo.json`). Según el estudio del sector, los discos que desaparecen sin fallo son migraciones, retiradas sanas o ausencias temporales.

**Qué se hizo y por qué.** El centro de datos no mejoró el modelo en los 12 meses con ese dato y no entró (`modelado.md`). Los 71.328 discos que desaparecen cuentan como censurados: no fallaron mientras se vieron (`negocio/reglas-transformacion.md`). Desde el 15/11/2022 hay modelos con precio inferido, el 14,1 % de los días de disco (`analisis-exploratorio__modelo_trimestre.json`); su coste vale lo que valga ese precio.

**Lo que queda abierto.** Desde abril de 2023, 22.746 de 35.635 desapariciones no coinciden con un vault que deja de aparecer en los datos (`reconocimiento/reconocimiento_de_los_datos.ipynb`). Se desconoce qué son.

## 3. Las variables no serán numéricas ni perfectas

**Qué se encontró.** Los datos traen una foto por disco y mes, sin objetivo y con contadores acumulados.

**Qué se hizo y por qué.** La tabla del modelo tiene 14.604.861 fotos, cada una con lo que se sabía ese día (`transformacion-datos.md`). Se construyeron estas variables: la edad; si el disco avisa; cuántos contadores avisan; la suma de los contadores 5, 187, 197 y 198; el cambio de cada contador desde la foto anterior. De las variables, 64 entran en el modelo y 71 no (`preparacion.json`, también las dos siguientes). Otras 9 quedan fuera desde el principio. La regresión logística recibe 62, en tramos de 0 y 1, sin escalar.

**Lo que queda abierto.** Hay 808 fallos de discos de datos que no aparecen como fallo en ninguna foto (`transformacion-datos.md`). La mayoría caen a más de 30 días de su última foto.

## 4. Tendrás cientos de variables

**Qué se encontró.** En la regresión logística, las variables se convertían en 496 columnas (`preseleccion.json`). El tope era una columna por cada 10 fallos, es decir, 1.196 (`preseleccion.md`).

**Qué se hizo y por qué.** Solo se preseleccionó la regresión logística. El modelo entregado es un árbol y no pasó por ella (`modelado.md`). Entraba una variable si la marcaban dos de los tres métodos: información mutua, permutación y eliminación recursiva. Los contadores 5, 187, 197 y 198 entraban siempre, para explicar la lista con lo que los técnicos ya vigilan. La regresión logística pasó de 496 columnas a 169 (`preseleccion.json`).

**Lo que queda abierto.** Con otra semilla la lista cambia en dos variables (`modelo/registro-transformaciones.md`). La validación cruzada de esa regresión resulta algo optimista; cuánto, no se ha medido (`preseleccion.md`).

## 5. El evento que interesa tendrá menos datos

**Qué se encontró.** El fallo a 30 días es raro en las dos partes (`particion.json`):

- construcción: 11.026.052 fotos y 11.962 con el evento, el 0,1085 %;
- validación: 3.578.809 fotos y 4.304 con el evento, el 0,1203 %.

**Qué se hizo y por qué.** El desequilibrio se trató solo al entrenar, con todas las fotos de fallo y el 2 % de las sanas de cada mes (`modelado.md`). Después, la probabilidad se devolvió a la escala real. La validación conservó la proporción real. En lugar de la exactitud se contaron los fallos en la lista de 100, donde un modelo que no aprende nada encuentra 0,13 al mes.

**Lo que queda abierto.** En dos de los cinco bloques de la validación cruzada, la probabilidad media se aleja de la tasa de fallo observada (`modelado.md`). Se aceptó como límite antes de medir la validación.

## 6. Del modelo a la empresa

### 6.1 El objetivo de negocio y la variable objetivo

**Qué se encontró.** La marca de fallo mezcla el disco que se rompe con el que Backblaze retira porque avisa (`fuentes/ficha_de_los_datos.md`). De las siete trampas del objetivo aparecieron cinco:

- esa mezcla;
- los discos que desaparecen avisando sin marcarse como fallo;
- la etiqueta, que se conoce 30 días después;
- el plazo del proceso;
- el retraso de carga en el sistema interno, que no consta.

Entre los fallos a 90 días, el 39,7 % llega sin aviso en la última foto mensual. En ese grupo el modelo apenas distingue los que fallan: su AUC es 0,58 (`negocio/cuestiones-pendientes.md`). A 30 días, en el año apartado, llegó sin aviso el 32 %: 1.215 de 3.773 fallos (`punto_ciego.json`). La regla de los cinco avisos SMART no puede marcarlos.

**Qué se hizo y por qué.** El negocio decidió que el modelo aprenda con todos los fallos y que avise a 30 días (`negocio/cuestiones-pendientes.md`). Los que desaparecen avisando no cuentan como fallo; se dan aparte como sensibilidad.

**Lo que queda abierto.** No se puede saber qué parte de los fallos son retiradas. El modelo puede estar aprendiendo, en parte, la propia regla de Backblaze.

### 6.2 La decisión y el corte

**Qué se encontró.** La salida es una puntuación de riesgo por disco, de 0 a 100 en el cuadro de mando. Ordena los discos y no es una probabilidad: su media no siempre coincide con la tasa de fallo observada (apartado 5).

**Qué se hizo y por qué.** No hay corte fijo: cada mes salen listas de 20, 100, 500 y 1.000 discos, con la de 100 como principal (`produccion/configuracion.json`). En la validación, el modelo encontró 16,33 fallos más al mes que la regla (`modelado.md`). La prueba final midió 11 meses del año apartado (`prueba_final.json` y `prueba_final.md`):

- en la lista de 100, el modelo encontró 22,64 fallos al mes y la regla 14,91;
- la diferencia, 7,73 fallos al mes, tiene un intervalo de 4,82 a 11,45;
- el AUC fue de 0,873 para el modelo y de 0,816 para la regla.

**Lo que queda abierto.** Ningún informe mide por qué la ventaja bajó de la validación a la prueba final. En los tomos donde acaba de fallar un disco hubo 113 fallos (`prueba_final.md`). En el 5 % de fotos de más riesgo de cada mes, el modelo encontró 63 y la regla 55: pocos para decidir.

### 6.3 La economía

**Qué se encontró.** En la lista de riesgo, acertar un fallo no ahorra nada: el disco se cambia igual, antes o después (`negocio/matriz_de_impacto.md`). Una falsa alarma retira un disco sano. En la compra, los fallos pesan el 6,44 % del coste por terabyte y año en la mediana de los modelos del ranking, medido (`cuadro_mando.json`).

**Qué se hizo y por qué.** El negocio decidió las dos formas:

- la lista de riesgo es «Actuar sobre los N primeros», medida en fallos encontrados frente a la regla y no en dinero;
- la compra de modelos es «Informar sin decisión automática», con el coste por terabyte y año como la cifra que mide valor.

Ese coste reparte el precio del disco entre su capacidad y su vida. Después añade la tasa anual de fallo por el disco nuevo más el cambio (`negocio/reglas-negocio.md`). Datos de partida, decididos por el negocio:

- el 17/11/2026: 37 $ por cambio, 6 años de vida y la garantía por familia de modelo;
- el 16/11/2026: los precios inferidos de los discos sin precio publicado.

Con ellos, los fallos de 2024 costaron 832.698 $ sin garantía y 305.124 $ con ella, medido (`cuadro_mando.json`).

**Lo que queda abierto.** No consta si Backblaze reclama la garantía; por eso el coste va con y sin ella. Ningún informe da cuánto se ahorraría comprando los modelos de menor coste.

### 6.4 Los procesos

**Qué se encontró.** Los datos traen una foto al mes, así que la lista es mensual. Usan el resultado los técnicos de los centros de datos y el equipo de compras (supuesto). Un técnico revisa la lista antes de cambiar un disco (supuesto).

**Qué se hizo y por qué.** En producción, la edad de un disco sin horas encendido solo usa datos de fallos anteriores a la foto, porque los posteriores no se conocen ese día (`modelo/registro-transformaciones.md`). Cuando falla un disco, su tomo queda en peligro mientras se rehace: un día por terabyte más uno (`negocio/reglas-negocio.md`).

**Lo que queda abierto.** No consta cuántos discos al mes pueden atender los técnicos.

### 6.5 El producto

**Qué se encontró.** El caso entrega cuatro piezas:

- el informe ejecutivo, en HTML y PDF (`informe_ejecutivo.html`);
- el informe final (`informe_final.html`);
- el cuadro de mando, con la lista del mes descargable en CSV (`cuadro_mando.html`);
- el proceso de producción mensual, en `produccion/`.

**Qué se hizo y por qué.** Cada mes, `produccion/ejecutar.py` puntúa la foto nueva sin quitar ningún disco. En junio de 2026 leyó 353.401 fotos y dejó sin puntuar 3.893 de discos de arranque, que no guardan datos (`preproduccion.md`). `produccion/reentrenar.py` rehace el modelo aparte, porque el cambio de modelo lo aprueba el negocio.

El modelo en uso es un reentreno con todo lo anterior al 01/07/2025, distinto del de la prueba final (`produccion/configuracion.json`). En el año apartado encontró 23,73 fallos al mes en la lista de 100, con un AUC de 0,896.

**Lo que queda abierto.** El reentreno se aprobó después de medirlo en el año apartado, que ya no es una prueba independiente para él. Ningún documento dice cómo se rehacen cada mes los dos informes ni quién lanza el proceso.
