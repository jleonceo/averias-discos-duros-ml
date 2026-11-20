English version: [README.en.md](README.en.md)

# Predicción de fallos y coste de compra de discos duros (Backblaze, 2020-2026)

Proyecto de análisis de datos y aprendizaje automático sobre el registro público de los discos duros de Backblaze, un proveedor de almacenamiento en la nube. Responde a dos problemas de operaciones: qué modelo de disco sale más barato por terabyte contando sus fallos y qué discos conviene revisar cada mes antes de que fallen.

## Resultados principales

- **Qué modelo comprar:** el precio de compra es el **93,56 %** del coste por terabyte y año; los fallos son el resto. Es la mediana de 27 modelos, la cifra del modelo que queda en el centro al ordenarlos. En los siete grupos de compra comparables, del mismo año y la misma capacidad, el modelo más barato por terabyte es también el que menos falla.
- **Qué discos revisar:** un modelo de aprendizaje automático prepara cada mes una lista de los 100 discos con más riesgo de fallar en los 30 días siguientes. Encuentra de media **22,6 fallos al mes**, un **52 % más** que la regla de los cinco avisos SMART, que ordena los discos por los contadores de avería que pasan de cero. Se midió en los 11 meses guardados para la prueba final, de julio de 2025 a mayo de 2026.
- **Qué vigilar:** la tasa anual de fallo sube cada año de edad entre el primero y el quinto, del 0,79 % al 2,58 %. El centro de datos sac2, en Sacramento, falla un 10 % más de lo esperado para sus modelos y edades.

[![CI](https://github.com/jleonceo/averias-discos-duros-ml/actions/workflows/ci.yml/badge.svg)](https://github.com/jleonceo/averias-discos-duros-ml/actions/workflows/ci.yml)

## Metodología

Una foto es el estado de un disco el primer día de un mes: sus contadores SMART, su modelo, su capacidad y su centro de datos. Es la unidad con la que trabajan la limpieza y el modelo.

1. **Calidad de los datos:** diagnóstico y corrección antes de analizar. Por ejemplo, 2.729 fotos con una capacidad de -1 o 0,1 TB recibieron la de su modelo. También se unificaron cuatro modelos escritos con dos espacios.
2. **Análisis económico:** el coste por terabyte y año de cada modelo suma dos partes. La primera es el precio de compra, repartido en 6 años de vida. La segunda es la tasa anual de fallo por el coste de cada cambio: disco nuevo y 37 $ de mano de obra. El precio es el publicado por Backblaze hasta 2022 y estimado desde 2023.
3. **Preparación de las variables:** cada foto lleva la edad del disco y cuánto ha cambiado cada contador desde la foto del mes anterior.
4. **Modelado y validación:** tres tipos de modelo comparados en cinco tramos trimestrales. Ganó un HistGradientBoosting, un modelo de árboles de decisión potenciados por gradiente. Se validó con los doce meses siguientes. El último año se guardó sin mirar hasta la prueba final.
5. **Producción:** dos procesos. El mensual puntúa la foto nueva sin quitar ningún disco: los que no se pueden puntuar salen con su motivo. El otro reentrena el modelo con datos nuevos.

## Límites

- Precios estimados: desde 2023 el precio de los discos es una estimación. El coste por terabyte vale lo que valga esa estimación.
- Fallos sin aviso: el 32 % de los fallos del año de la prueba final no daba ningún aviso el primer día del mes. La regla de los cinco avisos SMART no puede marcarlos. Para la lista de riesgo son los más difíciles de anticipar.
- El último mes: los datos llegan a junio de 2026, pero la prueba de la lista acaba en mayo. Para saber si un disco de junio falló en sus 30 días siguientes harían falta datos de julio, que no hay.
- Repuestos: la previsión por modelo y edad no mejora a repetir los fallos del trimestre anterior. En el año de la prueba final, su error medio fue del 31,8 %, frente al 30,6 %.
- El modelo en uso: se reentrenó con un año más de datos y se midió en el año de la prueba final antes de aprobarlo. Para él, ese año ya no es una prueba independiente.

## Las salidas

- **Informe final:** diez páginas para la dirección de operaciones, con cinco decisiones que aprobar ([`informes/informe_final.html`](https://jleonceo.github.io/averias-discos-duros-ml/informes/informe_final.html)).
- **Cuadro de mando:** cinco pestañas con filtros por centro de datos, fabricante, capacidad y edad. Incluye la lista de riesgo del mes, descargable en CSV ([`informes/cuadro_mando.html`](https://jleonceo.github.io/averias-discos-duros-ml/informes/cuadro_mando.html)).
- **Los seis problemas:** cómo se resolvieron en este caso los seis problemas típicos de un proyecto de datos ([`informes/los_seis_problemas.md`](informes/los_seis_problemas.md)).

## Estructura del repositorio

- `preparacion_datos/`: los dos scripts que sacan el extracto de los ficheros de Backblaze y apartan el año de la prueba final, cada uno con su prueba.
- `scripts/`: la cadena de 22 scripts numerados en el orden del proceso, de los datos en bruto al informe final y el cuadro de mando. La cabecera de cada uno dice qué lee, qué deja y cómo se lanza.
- `tests/`: un banco de pruebas por script, cada uno con casos que tienen que fallar.
- `produccion/`: el proceso mensual de puntuación y el reentreno.
- `modelos/`: el modelo en uso y su ficha.
- `informes/`: el informe final, el cuadro de mando, los seis problemas y los informes de cada paso.
- `config/`: las reglas de negocio, las de transformación y las decisiones que leen los scripts.

## Los datos

Los datos no están en el repositorio. Son públicos: Backblaze, [Drive Stats](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data), el registro diario de cada disco de sus centros de datos. Las condiciones de Backblaze piden citarla como fuente y no vender los datos. Son datos de discos: ninguna columna habla de una persona.

Lo que se hizo con ellos:

1. **La descarga:** los 26 ficheros trimestrales, de `data_Q1_2020.zip` a `data_Q2_2026.zip`, unos 25 GB. Cada uno trae un CSV por día, con una fila por disco.
2. **El extracto:** `podar_datos.py` guarda una foto de todos los discos el día 1 de cada mes, los 30 días anteriores a cada fallo, la lista de fallos y un recuento diario de discos y fallos por modelo, capacidad y centro de datos. Quita las 68 columnas vacías o constantes. Tarda unas dos horas y media.
3. **El año de la prueba final:** `apartar_reserva.py` separa lo que va del 01/07/2025 al 30/06/2026, que no se miró hasta el final. Quedan 17.960 fallos para el análisis y 4.751 para la prueba final.

El script `10` lee además las tablas de ingresos del informe anual de Backblaze de 2025, el [10-K presentado ante la SEC](https://www.sec.gov/Archives/edgar/data/1462056/000162828026016395/blze-20251231.htm). Es un documento de terceros y tampoco se incluye: el script lo busca en `config/sector/documentos/16_backblaze_10k_2025_tablas_ingresos.txt`.

## Cómo se ejecuta

Hace falta conda y el entorno de `environment.yml`:

```bash
git clone https://github.com/jleonceo/averias-discos-duros-ml.git && cd averias-discos-duros-ml
conda env create -f environment.yml && conda activate 68_averias_discos_duros
python -W error tests/probar_17_informe_final.py
```

El último comando pasa la prueba del informe final, que no necesita los datos: lee los informes que trae el repositorio. Sin datos pasan 14 de las 28 pruebas de `tests/`; las demás leen el extracto de Backblaze. Para repetir el caso entero, con los ZIP descargados en una carpeta `zips/`:

```bash
python preparacion_datos/podar_datos.py data/poda_entera zips/data_Q*.zip
python -I preparacion_datos/apartar_reserva.py data/poda_entera data/raw/podado data/raw/reserva
```

Después se lanzan los scripts de `scripts/` en su orden, del `01` al `22`, como dice la cabecera de cada uno.

## Repositorios relacionados

- [prediccion-cancelaciones-hotel-ml](https://github.com/jleonceo/prediccion-cancelaciones-hotel-ml): ordenar reservas por el riesgo de acabar sin check-in, con el mismo formato de cadena de scripts, informes y producción.
- [reposicion-inventario-prevision-ml](https://github.com/jleonceo/reposicion-inventario-prevision-ml): una decisión diaria apoyada en una previsión, medida en un semestre reservado para la prueba final.
- [store-sales-forecasting-ml](https://github.com/jleonceo/store-sales-forecasting-ml): previsión de ventas con validación temporal y despliegue por lotes simulado.
