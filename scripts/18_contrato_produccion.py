"""Contrato de producción del caso 68, averías de discos duros en Backblaze (método preproduccion, parte 1).

Lee el ganador aprobado en informes/modelado.json, saca de él y de la matriz las finalistas, y tira del hilo de cada una
en el registro de transformaciones y en las reglas de transformación: desde las columnas de data/raw/podado/ hasta la
columna que entra al modelo. Cada paso del hilo va a una de las cuatro clases de el método (quita filas, no aprende,
necesita otras filas, aprende) y dice qué se hace con él al reentrenar y al ejecutar.

Comprobaciones que paran con ERROR, antes de escribir nada: cada finalista tiene su cadena con fichas y apartados que
existen y una definición; cada ficha del registro está clasificada (en la cadena o fuera de ella, con su motivo);
ningún paso que aprende se ajustó antes de la partición; el contrato no tiene campos vacíos. Si el modelado no está en
OK, el ganador no está aprobado o la validación no lo dio por bueno, para con PARADO sin escribir el contrato.

Escribe config/modelo/contrato_produccion.md e informes/preproduccion.json, con la aprobación de el responsable del caso (19/11/2026,
«Sí, con el arreglo», en APROBADO_POR). Solo lee JSON y Markdown: no abre ningún dato.

Uso: python -W error scripts/18_contrato_produccion.py [--raiz CARPETA_DEL_CASO]
Método: preproduccion (versión 11/11/2026, una nota del método), con programacion-del-caso y transmision-conocimiento.
"""

# =================================================================================================================
# 1. Configuración
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
METODO = "preproduccion"
VERSION_METODO = "11/11/2026"
SCRIPT = "scripts/18_contrato_produccion.py"
MODELADO = "informes/modelado.json"
PRESELECCION = "informes/preseleccion.json"
ASIGNACION = "informes/modelado_asignacion.json"
REGISTRO = "config/modelo/registro-transformaciones.md"
REGLAS = "config/negocio/reglas-transformacion.md"
MATRIZ = "config/modelo/matriz_transformaciones.md"
PROTECCION = "config/fuentes/proteccion-datos.json"
CONTRATO = "config/modelo/contrato_produccion.md"
SALIDA_JSON = "informes/preproduccion.json"

# Las cuatro clases de el método (§1.3) y la ficha de la partición, que separa lo que puede aprender de lo que no
CLASES = ("quita filas", "no aprende", "necesita otras filas", "aprende")
FICHA_PARTICION = "R-020"
# El identificador, el objetivo y su horizonte (reglas, apartado 7; reglas de transformación §3)
IDENTIFICADOR = ["serial_number", "fecha"]
OBJETIVO = "falla_30d"
HORIZONTE = "horizonte_hasta"
GRUPO_DEL_CORTE = "fecha"
# La aprobación del contrato (El responsable del caso, 19/11/2026), con el arreglo de la historia de ventanas en P06 y P12
APROBADO_POR = "El responsable del caso, 19/11/2026: «Sí, con el arreglo»"
FECHA_APROBACION = "2026-11-19"
DESEMPATE = "serial_number"
ALGORITMOS = {"hgb": "HistGradientBoostingClassifier"}
PATRON_SMART = re.compile(r"^smart_\d+_(raw|normalized)$")
CONTADORES = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]
CONTADORES_CAMBIO = ["smart_5_raw", "smart_187_raw", "smart_197_raw", "smart_198_raw"]

# Los parámetros de el método (preproduccion/parametros.md), con el valor que se usará en la parte 2
PARAMETROS = [
    {"nombre": "tolerancia de la prueba por otro camino", "valor": 1e-12, "origen": "preproduccion/parametros.md, por defecto"},
    {"nombre": "semilla", "valor": None, "origen": "informes/modelado.json, ganador.semilla"},
    {"nombre": "corte", "valor": None, "origen": "informes/modelado.json (validacion.por_mes y aprobado_antes); reglas, apartado 7, cuestión 010"},
    {"nombre": "carpeta de reentrenos", "valor": "modelos/reentrenos/AAAA-MM-DD/", "origen": "preproduccion/parametros.md"},
    {"nombre": "carpeta de predicciones", "valor": "data/predicciones/AAAA-MM-DD/", "origen": "preproduccion/parametros.md"},
    {"nombre": "formato de guardado", "valor": "joblib con el módulo .py", "origen": "preproduccion/parametros.md"},
]

TEORIA = [
    "39.2, la preproducción: se tira del hilo hacia atrás desde el ganador y sus finalistas, y solo pasa a producción lo "
    "que transforma una finalista; el registro de transformaciones ya hace el primer filtro.",
    "39.4, las reglas del pipeline: lo que quita filas va fuera del Pipeline y solo al reentrenar; lo que no aprende puede "
    "ir como función; lo que aprende, con fit en entrenamiento.",
    "39.8, los dos scripts: al ejecutar no se tira ninguna fila; lo que no se puede puntuar sale con su motivo.",
]

# -----------------------------------------------------------------------------------------------------------------
# 1.1 Los pasos del hilo, en orden. Cada uno cita su ficha del registro y, si la ficha remite a las reglas de
#     transformación, el apartado que lo define. `define` son las variables que el paso produce, `lee` lo que lee de la
#     foto en bruto e `historia` las otras filas que necesita.
# -----------------------------------------------------------------------------------------------------------------
HISTORIA_FOTOS_HASTA = {"tabla": "fotos mensuales anteriores y la propia foto",
                        "columnas": ["serial_number", "fecha", "model", "capacity_bytes", "smart_9_raw"],
                        "hasta": "la fecha de la foto, incluida"}
HISTORIA_VENTANAS = {"tabla": "ventanas de fallo",
                     "columnas": ["serial_number", "fecha", "date", "dia_fallo", "model", "capacity_bytes"],
                     "hasta": "las ventanas de fallos ocurridos antes del día de la foto (dia_fallo anterior a su fecha)"}
HISTORIA_FOTO_ANTERIOR = {"tabla": "fotos mensuales anteriores",
                          "columnas": ["serial_number", "fecha", *CONTADORES_CAMBIO],
                          "hasta": "el día anterior a la foto: la última foto del mismo disco, de cualquier mes anterior"}

PASOS = [
    {"id": "P01", "nombre": "leer la foto en un fichero", "fichas": ["R-008"], "apartado": None, "fuente": None,
     "clase": "no aprende", "lee": ["serial_number", "fecha"], "define": [], "historia": [],
     "que": "La foto mensual se lee como un solo fichero, con sus columnas por nombre; una columna que su pieza no trae queda vacía y no se rellena.",
     "por_que": "Solo junta las piezas de un mes; no mira otras filas ni aprende nada.",
     "reentrenar": "Ya está aplicado en la tabla de entrenamiento.",
     "ejecutar": "La entrada es la foto de un mes; sus columnas se comprueban por nombre."},
    {"id": "P02", "nombre": "el centro como texto", "fichas": ["R-001"], "apartado": None, "fuente": None,
     "clase": "no aprende", "lee": ["datacenter"], "define": [], "historia": [],
     "que": "datacenter pasa a texto; donde no consta sigue vacío.",
     "por_que": "Es un cambio de tipo de la propia fila.",
     "reentrenar": "Ya está aplicado en la tabla de entrenamiento.", "ejecutar": "Se aplica a la foto."},
    {"id": "P03", "nombre": "el nombre del modelo", "fichas": ["R-004"], "apartado": None, "fuente": None,
     "clase": "no aprende", "lee": ["model"], "define": [], "historia": [],
     "que": "Los modelos escritos con dos espacios tras «WDC» pasan a su nombre con el mapeo cerrado de decisiones-correccion.json; lo que no está en el mapeo se queda como está.",
     "por_que": "El mapeo es una lista fija aprobada por el responsable del caso, no algo aprendido de los datos.",
     "reentrenar": "Ya está aplicado en la tabla de entrenamiento.", "ejecutar": "Se aplica a la foto y a su historia."},
    {"id": "P04", "nombre": "la capacidad del modelo", "fichas": ["R-005"], "apartado": None, "fuente": None,
     "clase": "necesita otras filas", "lee": ["model", "capacity_bytes"], "define": [],
     "historia": [HISTORIA_FOTOS_HASTA, HISTORIA_VENTANAS],
     "que": "Una capacidad no válida (-1 o 0,1 TB, por debajo del mínimo de decisiones-correccion.json) pasa a la única capacidad válida de su modelo.",
     "por_que": "No aprende nada de la tabla de entrenamiento: aplica la regla, apartado 3, la capacidad de un disco es la de su modelo, y para saberla mira otras filas del mismo modelo con capacidad válida. En el desarrollo se miró todo el periodo y cada modelo tenía una sola; al ejecutar se mira solo lo que hay hasta el día de la foto, la propia foto incluida. Si un modelo no tiene ninguna capacidad válida hasta ese día, su fila sale sin puntuar y con su motivo.",
     "reentrenar": "Ya está aplicado en la tabla de entrenamiento.",
     "ejecutar": "Se calcula con la foto y su historia, modelo a modelo."},
    {"id": "P05", "nombre": "los contadores vacíos se quedan vacíos", "fichas": ["R-009"], "apartado": None,
     "fuente": None, "clase": "no aprende", "lee": [], "define": [], "historia": [],
     "que": "Un contador vacío quiere decir que el modelo no lo apunta: no se rellena (C-12).",
     "por_que": "No cambia ningún valor.", "reentrenar": "Ya está así en la tabla de entrenamiento.",
     "ejecutar": "No se rellena ningún vacío."},
    {"id": "P06", "nombre": "la historia de las ventanas sin los días copiados", "fichas": ["R-007"], "apartado": None,
     "fuente": None, "clase": "necesita otras filas", "lee": [], "define": [], "historia": [HISTORIA_VENTANAS],
     "que": "De la historia de ventanas salen las filas cuya fecha no es la de su texto (date), que son copia del día siguiente, y las ventanas de fallos que no han ocurrido antes del día de la foto (dia_fallo igual o posterior a su fecha).",
     "por_que": "Quita filas de la tabla de historia, nunca de la foto que se puntúa; por eso no es de la clase que quita filas. Sirve para la primera aparición de la edad y para la capacidad del modelo. Una ventana son los 30 días anteriores a un fallo: que exista una fila de ventana el día de la foto anuncia un fallo que ese día no se conoce (arreglo aprobado por el responsable del caso el 19/11/2026).",
     "reentrenar": "Ya está aplicado en la tabla de entrenamiento.",
     "ejecutar": "Se aplica a la historia de ventanas antes de usarla."},
    {"id": "P07", "nombre": "capacidad en TB", "fichas": ["R-011"], "apartado": "`dim_modelo`", "fuente": None,
     "clase": "no aprende", "lee": [], "define": ["capacidad_tb"], "historia": [],
     "que": "capacidad_tb es la capacidad del modelo entre 10^12, redondeada a un decimal, con el medio hacia arriba.",
     "por_que": "Con la capacidad del modelo ya puesta (P04) es una división y un redondeo de la propia fila.",
     "reentrenar": "Llega hecha en la tabla de entrenamiento.", "ejecutar": "Se calcula en la foto."},
    {"id": "P08", "nombre": "disco de arranque o de datos", "fichas": ["R-011"], "apartado": "`dim_modelo`",
     "fuente": None, "clase": "no aprende", "lee": [], "define": ["tipo_disco"], "historia": [],
     "que": "tipo_disco es «arranque» si la capacidad del modelo no pasa del límite de las reglas, apartado 3 y §7 y «datos» si lo pasa.",
     "por_que": "Es un corte fijo de las reglas sobre la capacidad del modelo, ya puesta en P04.",
     "reentrenar": "Decide la población, ya aplicada en la tabla.", "ejecutar": "Se calcula en la foto para el motivo de P11."},
    {"id": "P09", "nombre": "el fabricante", "fichas": ["R-011"], "apartado": "`dim_modelo`", "fuente": None,
     "clase": "no aprende", "lee": ["model"], "define": ["fabricante"], "historia": [],
     "que": "fabricante sale del nombre del modelo: «ST» es Seagate; TOSHIBA, WDC y HGST delante dan su nombre; dos excepciones escritas en las reglas, apartado 3.",
     "por_que": "Es una regla fija sobre el nombre. En el desarrollo se guardó en dim_modelo, una tabla por modelo, pero esa tabla solo repite la regla: un modelo nuevo la cumple igual. Un modelo que no sigue ningún patrón queda vacío.",
     "reentrenar": "Llega hecho en la tabla de entrenamiento.", "ejecutar": "Se calcula en la foto."},
    {"id": "P10", "nombre": "la garantía", "fichas": ["R-011"], "apartado": "`dim_modelo`", "fuente": None,
     "clase": "no aprende", "lee": ["model"], "define": ["garantia_anos"], "historia": [],
     "que": "garantia_anos sale del nombre del modelo, solo en los discos de datos (reglas, apartado 6); un modelo sin garantía comprobada queda vacío.",
     "por_que": "Igual que el fabricante: una regla fija sobre el nombre, que la tabla dim_modelo solo guarda.",
     "reentrenar": "Llega hecha en la tabla de entrenamiento.", "ejecutar": "Se calcula en la foto."},
    {"id": "P11", "nombre": "la población", "fichas": ["R-013"], "apartado": "3. `fotos_riesgo`", "fuente": None,
     "clase": "quita filas", "lee": ["failure"], "define": [], "historia": [],
     "que": "Entran los discos de datos y sale la foto del día en que el disco falla (failure = 1).",
     "por_que": "Son los discos del modelo (reglas, apartado 3 y §7); la foto del día del fallo ya está marcada como fallada.",
     "reentrenar": "La tabla ya llega sin esas filas: se comprueba que no queda ninguna y se cuenta.",
     "ejecutar": "No se quita ninguna: el disco de arranque y la foto del día del fallo salen con la puntuación vacía y su motivo."},
    {"id": "P12", "nombre": "la edad", "fichas": ["R-013"], "apartado": "3. `fotos_riesgo`",
     "apartado_extra": "De qué se parte", "fuente": None, "clase": "necesita otras filas",
     "lee": ["serial_number", "fecha", "smart_9_raw"], "define": ["edad_anos"],
     "historia": [HISTORIA_FOTOS_HASTA, HISTORIA_VENTANAS],
     "que": "edad_anos son las horas encendido entre 8.766; sin horas, los días desde la primera aparición del disco entre 365,25. Al ejecutar, la primera aparición solo usa las ventanas de fallos con dia_fallo anterior a la fecha de la foto.",
     "por_que": "Con horas es la propia fila. Sin horas cuenta desde la primera aparición, que es su primera foto o, si sale antes, el primer día de una ventana suya: eso pide la historia del disco hasta el día de la foto, nunca después. La ventana de un fallo que aún no ha ocurrido no cuenta, porque anuncia ese fallo (arreglo de el responsable del caso, 19/11/2026). En el desarrollo sí contó: de las 2.735 fotos de fotos_riesgo sin horas, en una sola la primera aparición sale de una ventana, y esa foto puede salir distinta.",
     "reentrenar": "Llega hecha en la tabla de entrenamiento.", "ejecutar": "Se calcula con la foto y su historia."},
    {"id": "P13", "nombre": "los avisos", "fichas": ["R-013"], "apartado": "3. `fotos_riesgo`", "fuente": None,
     "clase": "no aprende", "lee": CONTADORES,
     "define": ["avisa", "contadores_que_avisan", "suma_contadores_sin_188", "smart_188_no_cero"], "historia": [],
     "que": "avisa, contadores_que_avisan, suma_contadores_sin_188 y smart_188_no_cero salen de los cinco contadores de avería de la fila; un vacío no cuenta como aviso.",
     "por_que": "Solo miran la propia fila.",
     "reentrenar": "Llegan hechos en la tabla de entrenamiento.", "ejecutar": "Se calculan en la foto."},
    {"id": "P14", "nombre": "los cambios contra la foto anterior", "fichas": ["R-013"], "apartado": "3. `fotos_riesgo`",
     "fuente": None, "clase": "necesita otras filas", "lee": ["serial_number", "fecha", *CONTADORES_CAMBIO],
     "define": ["cambio_smart_5", "cambio_smart_187", "cambio_smart_197", "cambio_smart_198", "meses_desde_foto_anterior"],
     "historia": [HISTORIA_FOTO_ANTERIOR],
     "que": "cambio_smart_5, 187, 197 y 198 restan al contador de la fila el de la foto anterior del mismo disco; meses_desde_foto_anterior cuenta los meses entre las dos. Sin foto anterior, o con uno de los dos valores vacío, quedan vacíos.",
     "por_que": "Necesitan la foto anterior del mismo disco, de cualquier mes anterior: una fila que no es la que se puntúa.",
     "reentrenar": "Llegan hechos en la tabla de entrenamiento.", "ejecutar": "Se calculan con la foto y su historia."},
    {"id": "P15", "nombre": "lo que pasa sin cambios", "fichas": ["R-013"], "apartado": "3. `fotos_riesgo`",
     "fuente": None, "clase": "no aprende", "lee": ["serial_number", "fecha", "model", "datacenter"],
     "define": ["serial_number", "fecha", "model", "datacenter", "smart_*"], "historia": [],
     "que": "serial_number, fecha, model, datacenter y los contadores smart_* pasan tal como están en la fila.",
     "por_que": "No se transforman.", "reentrenar": "Llegan así en la tabla de entrenamiento.",
     "ejecutar": "Se toman de la foto."},
    {"id": "P16", "nombre": "el horizonte del objetivo", "fichas": ["R-013"], "apartado": "3. `fotos_riesgo`",
     "fuente": None, "clase": "no aprende", "lee": ["fecha"], "define": [HORIZONTE], "historia": [],
     "que": "horizonte_hasta son 30 días después de la foto, recortado al final de su periodo.",
     "por_que": "Es una cuenta de calendario sobre la fecha de la fila.",
     "reentrenar": "Llega hecho en la tabla de entrenamiento y lo usa P18.", "ejecutar": "No se usa."},
    {"id": "P17", "nombre": "el objetivo", "fichas": ["R-010", "R-013"], "apartado": "3. `fotos_riesgo`",
     "fuente": None, "clase": "necesita otras filas", "lee": ["serial_number", "fecha"], "define": [OBJETIVO],
     "historia": [], "que": "falla_30d vale 1 si el disco tiene un fallo de la lista del día siguiente a la foto a horizonte_hasta, con dia_fallo igualado a milisegundos antes de cruzar.",
     "por_que": "Es el objetivo: mira los fallos posteriores a la foto, que al ejecutar no se conocen. Llega hecho en la tabla de entrenamiento; ejecutar no lo calcula ni lo usa.",
     "reentrenar": "Llega hecho en la tabla de entrenamiento.", "ejecutar": "No se calcula ni se usa: si llega, se ignora."},
    {"id": "P18", "nombre": "el objetivo conocido al entrenar", "fichas": ["R-020"], "apartado": None,
     "fuente": "informes/modelado.json, validacion_cruzada.objetivo_sin_conocer", "clase": "quita filas", "lee": [],
     "define": [], "historia": [],
     "que": "Entrenan las fotos anteriores a la fecha del entrenamiento cuyo horizonte_hasta también es anterior a esa fecha; las demás se quitan y se cuentan, con los fallos que llevan.",
     "por_que": "El objetivo tarda 30 días en saberse: es la regla del modelado (aprendizaje-automatico §3 y §7).",
     "reentrenar": "Antes del Pipeline, contado.", "ejecutar": "No aplica: no se quita ninguna fila."},
    {"id": "P19", "nombre": "la muestra", "fichas": [], "apartado": None,
     "fuente": "informes/modelado.json, ganador.muestra; reglas de negocio §7", "clase": "quita filas", "lee": [],
     "define": [], "historia": [],
     "que": "Entrenan todas las fotos con fallo y una parte de las sanas de cada mes, sorteada con la semilla, como en el modelado.",
     "por_que": "Es el tratamiento del desequilibrio, que se hace solo al entrenar (reglas, apartado 7).",
     "reentrenar": "Antes del Pipeline, contado.", "ejecutar": "No aplica: se puntúan todas las filas."},
    {"id": "P20", "nombre": "las numéricas tal cual", "fichas": ["R-021", "R-022"], "apartado": None, "fuente": None,
     "clase": "no aprende", "lee": [], "define": [], "historia": [],
     "que": "Las numéricas entran al modelo tal cual, con el vacío como vacío (rama «numericas», passthrough).",
     "por_que": "Los árboles cortan por orden: no hay escalado ni relleno.",
     "reentrenar": "Dentro del Pipeline.", "ejecutar": "Dentro del Pipeline."},
    {"id": "P21", "nombre": "el centro se vacía", "fichas": ["R-021"], "apartado": None,
     "fuente": "informes/modelado.json, ganador.datacenter y sitio", "clase": "no aprende", "lee": [], "define": [],
     "historia": [],
     "que": "datacenter se lee y se vacía antes de codificarlo, porque el sitio no entró en el modelo.",
     "por_que": "Pone un vacío fijo, sin mirar los datos.",
     "reentrenar": "Dentro del Pipeline, como función.", "ejecutar": "Dentro del Pipeline, como función."},
    {"id": "P22", "nombre": "las categorías raras", "fichas": ["R-021", "R-022"], "apartado": None, "fuente": None,
     "clase": "aprende", "lee": [], "define": [], "historia": [],
     "que": "En model, fabricante y datacenter el vacío pasa a «sin dato» y las categorías con menos fotos, fallos o sanas que el mínimo de la matriz van a «otras»; una categoría que no estaba en el entrenamiento va a «otras» si existe y, si no, a la referencia (P-03 de la matriz).",
     "por_que": "Qué categorías son raras se aprende de la tabla de entrenamiento, con el objetivo: va con fit.",
     "reentrenar": "Dentro del Pipeline, con fit.", "ejecutar": "Dentro del Pipeline, ya ajustado."},
    {"id": "P23", "nombre": "el código de categoría", "fichas": ["R-021"], "apartado": None, "fuente": None,
     "clase": "aprende", "lee": [], "define": [], "historia": [],
     "que": "Cada categoría pasa a un código ordinal, que el HistGradientBoosting trata como categórica nativa; lo que no conoce sale vacío.",
     "por_que": "La lista de categorías se aprende en el entrenamiento: va con fit.",
     "reentrenar": "Dentro del Pipeline, con fit.", "ejecutar": "Dentro del Pipeline, ya ajustado."},
    {"id": "P24", "nombre": "el modelo", "fichas": [], "apartado": None, "fuente": "informes/modelado.json, ganador",
     "clase": "aprende", "lee": [], "define": [], "historia": [],
     "que": "El HistGradientBoosting con la receta fija del ganador.",
     "por_que": "Es lo que se entrena.", "reentrenar": "Dentro del Pipeline, con fit.",
     "ejecutar": "Dentro del Pipeline, con predict_proba."},
    {"id": "P25", "nombre": "la recalibración", "fichas": [], "apartado": None,
     "fuente": "informes/modelado.json, ganador.recalibracion", "clase": "aprende", "lee": [], "define": [],
     "historia": [],
     "que": "La probabilidad del modelo pasa a la escala real con la corrección del prior sobre el logit, con la tasa de fallo de la muestra y la real del entrenamiento.",
     "por_que": "Las dos tasas se miden en cada reentreno, con su tabla: no se copian del modelado.",
     "reentrenar": "Se miden las dos tasas al entrenar y viajan con el modelo.", "ejecutar": "Se aplica a la probabilidad."},
]

# Prefijos y finales comunes de las cadenas
POBLACION = ["P01", "P03", "P04", "P08", "P11"]
ENTRENAR = ["P18", "P19"]
MODELO = ["P24", "P25"]
NUMERICA = ["P20", *MODELO]
CATEGORICA = ["P22", "P23", *MODELO]

# -----------------------------------------------------------------------------------------------------------------
# 1.2 La cadena de cada finalista, por los pasos de arriba. Los contadores smart_* que pasan sin cambios tienen la
#     cadena genérica; las demás, la suya.
# -----------------------------------------------------------------------------------------------------------------
CADENA_SMART = POBLACION + ["P05", "P15"] + ENTRENAR + NUMERICA
CADENAS = {
    "serial_number": ["P01", "P15"],
    "fecha": ["P01", "P15"],
    OBJETIVO: POBLACION + ["P17"] + ENTRENAR[:1],
    HORIZONTE: POBLACION + ["P16"] + ENTRENAR[:1],
    "capacidad_tb": POBLACION + ["P07"] + ENTRENAR + NUMERICA,
    "garantia_anos": POBLACION + ["P09", "P10"] + ENTRENAR + NUMERICA,
    "fabricante": POBLACION + ["P09"] + ENTRENAR + CATEGORICA,
    "model": POBLACION + ["P15"] + ENTRENAR + CATEGORICA,
    "datacenter": ["P02"] + POBLACION + ["P15"] + ENTRENAR + ["P21"] + CATEGORICA,
    "edad_anos": POBLACION + ["P05", "P06", "P12"] + ENTRENAR + NUMERICA,
    **{v: POBLACION + ["P05", "P13"] + ENTRENAR + NUMERICA
       for v in ["avisa", "contadores_que_avisan", "suma_contadores_sin_188", "smart_188_no_cero"]},
    **{v: POBLACION + ["P05", "P14"] + ENTRENAR + NUMERICA
       for v in ["cambio_smart_5", "cambio_smart_187", "cambio_smart_197", "cambio_smart_198", "meses_desde_foto_anterior"]},
}

# -----------------------------------------------------------------------------------------------------------------
# 1.3 Las fichas del registro que no están en el hilo de ninguna finalista, cada una con su motivo
# -----------------------------------------------------------------------------------------------------------------
FICHAS_FUERA = {
    "R-002": "pod_slot_num no es finalista: es un código de posición fuera de la matriz",
    "R-003": "date sale de fotos_riesgo, que se queda con fecha (reglas de transformación §3); solo la usa P06 en la historia de ventanas, que compara fecha con su texto",
    "R-006": "el recuento diario no entra en ninguna finalista",
    "R-012": "dim_precio_gb no entra en ninguna finalista",
    "R-014": "fallos_detalle no entra en ninguna finalista; el objetivo sale de la lista de fallos (P17)",
    "R-015": "vida_discos no entra en ninguna finalista",
    "R-016": "dias_por_tramo no entra en ninguna finalista",
    "R-017": "inicio_trimestre no entra en ninguna finalista",
    "R-018": "modelo_trimestre no entra en ninguna finalista",
    "R-019": "centro_mes no entra en ninguna finalista",
    "R-024": "es la ficha de este contrato aprobado: no cambia ningún dato",
    "R-023": "la preselección es de la regresión logística; el ganador es el HistGradientBoosting, que no se preseleccionó",
}


class Parada(Exception):
    """El script para: `estado` es PARADO si para a propósito por una regla y ERROR si falla una comprobación."""

    def __init__(self, mensaje, estado="ERROR"):
        super().__init__(mensaje)
        self.estado = estado


# =================================================================================================================
# 2. Utilidades
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def a_json(valor):
    """Pasa a tipos que JSON acepta, sin NaN ni infinitos."""
    if isinstance(valor, dict):
        return {str(k): a_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [a_json(v) for v in valor]
    if isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor)):
        return None
    return valor


def numero(n, decimales=None):
    """Un número escrito en español: punto de miles y coma decimal."""
    if decimales is None:
        return f"{int(n):,}".replace(",", ".")
    texto = f"{n:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def leer_texto(raiz, ruta):
    """Lee un documento del caso; para con ERROR si no existe."""
    p = raiz / ruta
    if not p.exists():
        raise Parada(f"no existe {ruta}")
    return p.read_text(encoding="utf-8")


# =================================================================================================================
# 3. Lectura de las entradas
# =================================================================================================================
def leer_modelado(raiz):
    """Lee informes/modelado.json y para si no deja empezar (resultado.md, «Al empezar»)."""
    if (raiz / ASIGNACION).exists():
        raise Parada("hay un modelo por clase (informes/modelado_asignacion.json) y el método todavía no lo admite", "PARADO")
    m = json.loads(leer_texto(raiz, MODELADO))
    estado = m.get("resultado", {}).get("estado")
    if estado != "OK":
        raise Parada(f"informes/modelado.json está en {estado}, no en OK: no se empieza", "PARADO")
    g = m.get("ganador") or {}
    if not g.get("aprobado_por"):
        raise Parada("el ganador de informes/modelado.json no está aprobado (ganador.aprobado_por vacío)", "PARADO")
    if (m.get("validacion") or {}).get("se_da_por_bueno") is not True:
        raise Parada("la validación de informes/modelado.json no da el modelo por bueno", "PARADO")
    if g.get("algoritmo") not in ALGORITMOS:
        raise Parada(f"el contrato describe el HistGradientBoosting y el ganador es {g.get('algoritmo')}")
    return m


def leer_registro(texto):
    """Las fichas del registro, en el orden del fichero: número, título y cuerpo."""
    partes = re.split(r"^## (R-\d{3}) · (.+)$", texto, flags=re.M)
    fichas = []
    for i in range(1, len(partes), 3):
        fichas.append({"numero": partes[i], "titulo": partes[i + 1].strip(), "cuerpo": partes[i + 2]})
    numeros = [f["numero"] for f in fichas]
    repetidas = sorted({n for n in numeros if numeros.count(n) > 1})
    if repetidas:
        raise Parada(f"el registro tiene fichas repetidas: {repetidas}")
    return fichas


def leer_apartados(texto):
    """Los apartados de las reglas de transformación: título y texto hasta el siguiente de su nivel o superior."""
    lineas = texto.splitlines()
    cabeceras = [(i, len(m.group(1)), m.group(2).strip()) for i, l in enumerate(lineas)
                 if (m := re.match(r"^(#{2,4}) (.+)$", l))]
    apartados = []
    for k, (i, nivel, titulo) in enumerate(cabeceras):
        fin = next((j for j, n, _ in cabeceras[k + 1:] if n <= nivel), len(lineas))
        apartados.append({"titulo": titulo, "texto": "\n".join(lineas[i + 1:fin])})
    return apartados


def apartado(apartados, clave):
    """El texto del apartado cuyo título empieza por `clave`; None si no está."""
    return next((a["texto"] for a in apartados if a["titulo"].startswith(clave)), None)


def leer_matriz(texto):
    """Las variables de la tabla «Columnas que entran» de la matriz, con su tipo y si entran en el HistGradientBoosting."""
    m = re.search(r"^## Columnas que entran.*?$(.*?)(?=^## )", texto + "\n## fin", flags=re.M | re.S)
    if not m:
        raise Parada("la matriz no tiene el apartado «Columnas que entran»")
    filas = [l for l in m.group(1).splitlines() if l.startswith("|")]
    cab = [c.strip() for c in filas[0].strip("|").split("|")]
    iv, it, ie = cab.index("Variable"), cab.index("Tipo"), cab.index("Entra")
    variables = []
    for l in filas[2:]:
        celdas = [c.strip() for c in l.strip("|").split("|")]
        entra = celdas[ie]
        variables.append({"variable": celdas[iv].strip("`"), "tipo": celdas[it],
                          "hgb": entra == "sí" or "hgb" in entra})
    return variables


# =================================================================================================================
# 4. Las finalistas (método §1.1)
# =================================================================================================================
def finalistas_de(m, matriz, preseleccion):
    """Las variables de origen que lee el preprocesador del ganador, más el identificador, el objetivo y su horizonte.

    Salen de la preselección si el ganador se preseleccionó y, si no, de la matriz. Para con ERROR si una columna del
    ganador no sale de ninguna finalista, o si la matriz y el preprocesador del ganador no casan.
    """
    g = m["ganador"]
    familia = (preseleccion or {}).get("familias", {}).get(g["algoritmo"], {})
    if familia.get("se_preselecciona"):
        de_origen = list(familia.get("variables_finales") or familia.get("columnas_finales") or [])
        fuente = f"{PRESELECCION}, familias.{g['algoritmo']}"
    else:
        de_origen = [v["variable"] for v in matriz if v["hgb"]]
        fuente = f"{MATRIZ}, columnas que entran en el HistGradientBoosting"
    lee = list(g["columnas_que_lee_el_preprocesador"])
    sin_finalista = [c for c in lee + list(g["columnas"]) if c not in de_origen]
    if sin_finalista:
        raise Parada(f"columnas del ganador que no salen de ninguna finalista ({fuente}): {sorted(set(sin_finalista))}")
    sobran = [v for v in de_origen if v not in lee]
    if sobran:
        raise Parada(f"variables de {fuente} que el preprocesador del ganador no lee: {sobran}")
    return lee, fuente


# =================================================================================================================
# 5. Tirar del hilo (método §1.2) y separar (§1.3)
# =================================================================================================================
def cadena_de(variable):
    """Los pasos de la cadena de una variable, en el orden de PASOS; None si no tiene."""
    ids = CADENAS.get(variable) or (CADENA_SMART if PATRON_SMART.match(variable) else None)
    if ids is None:
        return None
    orden = [p["id"] for p in PASOS]
    return sorted(set(ids), key=orden.index)


def define(paso, variable):
    """Si el paso es el que produce la variable (los smart_* por su patrón)."""
    return variable in paso["define"] or ("smart_*" in paso["define"] and PATRON_SMART.match(variable) is not None)


def tirar_del_hilo(variables, fichas, apartados):
    """La cadena de cada finalista; para con ERROR si a una le falta la cadena, una ficha, un apartado o su definición."""
    por_id = {p["id"]: p for p in PASOS}
    numeros = {f["numero"]: f for f in fichas}
    sin_cadena, sin_definicion, resultado = [], [], []
    for v in variables:
        ids = cadena_de(v)
        if ids is None:
            sin_cadena.append(f"{v} (no tiene pasos)")
            continue
        pasos = [por_id[i] for i in ids]
        faltan = [f for p in pasos for f in p["fichas"] if f not in numeros]
        faltan += [p[k] for p in pasos for k in ("apartado", "apartado_extra") if p.get(k) and apartado(apartados, p[k]) is None]
        if faltan:
            sin_cadena.append(f"{v} (faltan {sorted(set(faltan))})")
            continue
        # La definición: la variable se nombra en el apartado o en la ficha del paso que la produce
        productores = [p for p in pasos if define(p, v)]
        token = "`smart_*`" if PATRON_SMART.match(v) else f"`{v}`"
        definida = any(token in (apartado(apartados, p[k]) or "") for p in productores for k in ("apartado", "apartado_extra")
                       if p.get(k)) or any(token in numeros[f]["cuerpo"] for p in productores for f in p["fichas"])
        if not definida:
            sin_definicion.append(v)
            continue
        resultado.append({"variable": v, "pasos": ids})
    if sin_cadena:
        raise Parada(f"finalistas sin cadena en el registro: {sin_cadena}")
    if sin_definicion:
        raise Parada(f"finalistas sin definición en el registro ni en las reglas de transformación: {sin_definicion}")
    return resultado


def v_fichas_con_clase(fichas):
    """Cada ficha del registro está en un paso del hilo, con su clase, o fuera del hilo con su motivo."""
    en_el_hilo = {f for p in PASOS for f in p["fichas"]}
    sin_clase = [f"{f['numero']} · {f['titulo']}" for f in fichas
                 if f["numero"] not in en_el_hilo and f["numero"] not in FICHAS_FUERA]
    malas = [p["id"] for p in PASOS if p["clase"] not in CLASES]
    if sin_clase or malas:
        raise Parada(f"pasos sin clase: fichas del registro sin clasificar {sin_clase}; pasos con una clase que no es de "
                     f"las cuatro {malas}")
    return not sin_clase and not malas


def v_aprende_tras_la_particion(fichas, m):
    """Ningún paso que aprende se ajustó antes de la partición: su ficha va después de R-020 y el modelado entrenó
    con la parte de entrenamiento."""
    orden = [f["numero"] for f in fichas]
    if FICHA_PARTICION not in orden:
        raise Parada(f"el registro no tiene la ficha de la partición ({FICHA_PARTICION}): no se puede comprobar cuándo se ajusta lo que aprende")
    corte = orden.index(FICHA_PARTICION)
    antes = [f"{p['id']} ({f})" for p in PASOS if p["clase"] == "aprende" for f in p["fichas"]
             if f in orden and orden.index(f) < corte]
    entrena_con = [e.get("ruta", "") for e in m.get("entradas", [])]
    sin_ficha = [p["id"] for p in PASOS if p["clase"] == "aprende" and not p["fichas"]]
    if sin_ficha and not any("entrenamiento" in r for r in entrena_con):
        antes += [f"{i} (el modelado no dice que entrenó con la parte de entrenamiento)" for i in sin_ficha]
    if antes:
        raise Parada(f"pasos que aprenden ajustados antes de la partición: {antes}")
    return not antes


def vacios(objeto, ruta="contrato", permitidos=("hiperparametros",)):
    """Las rutas de los campos vacíos del contrato: texto vacío, None, lista o diccionario vacíos."""
    encontrados = []
    if isinstance(objeto, dict):
        if not objeto:
            encontrados.append(ruta)
        for k, v in objeto.items():
            if k in permitidos:
                continue
            encontrados += vacios(v, f"{ruta}.{k}", permitidos)
    elif isinstance(objeto, list):
        if not objeto:
            encontrados.append(ruta)
        for i, v in enumerate(objeto):
            encontrados += vacios(v, f"{ruta}[{i}]", permitidos)
    elif objeto is None or (isinstance(objeto, str) and not objeto.strip()):
        encontrados.append(ruta)
    return encontrados


def v_contrato_sin_vacios(contrato):
    """El contrato no tiene campos vacíos. Las columnas del modelo de una finalista pueden ser cero y se dice por qué."""
    encontrados = [r for r in vacios(contrato, permitidos=("hiperparametros", "columnas_del_modelo"))]
    if encontrados:
        raise Parada(f"el contrato tiene campos vacíos: {encontrados[:10]}")
    return not encontrados


# =================================================================================================================
# 6. La receta, el corte y la historia
# =================================================================================================================
def hoja_de(filas):
    """La hoja mínima: max(20, 1 % de las filas de la muestra), redondeada al entero (parametros del modelado)."""
    return max(20, int(math.floor(0.01 * filas + 0.5)))


def receta_de(m, finalistas):
    """La receta fija del ganador, leída de modelado.json; para si la hoja que da la regla no es la del ajuste final."""
    g, af = m["ganador"], m["ajuste_final"]
    parametro = {p["nombre"]: p["valor"] for p in m.get("parametros", [])}
    hoja = hoja_de(af["muestra"]["filas"])
    if hoja != af["hoja"]:
        raise Parada(f"la hoja de la regla ({hoja}) no es la del ajuste final de modelado.json ({af['hoja']})")
    early = re.search(r"early_stopping=(\w+)", parametro.get("HistGradientBoosting", ""))
    if not early:
        raise Parada("modelado.json no dice early_stopping en el parámetro «HistGradientBoosting»")
    categoricas = [f"{f['variable']}_oe" for f in finalistas if "P23" in f["pasos"]]
    conocido = next((o for o in m["validacion_cruzada"]["objetivo_sin_conocer"] if o["entrenamiento"] == "ajuste final"), None)
    if conocido is None:
        raise Parada("modelado.json no trae la fecha del ajuste final en validacion_cruzada.objetivo_sin_conocer")
    fraccion = re.search(r"(\d+(?:[.,]\d+)?) ?% de las sanas", g.get("muestra", ""))
    return {
        "algoritmo": ALGORITMOS[g["algoritmo"]],
        "hiperparametros": g["hiperparametros"],
        "fijos": {"early_stopping": early.group(1) == "True", "random_state": g["semilla"],
                  "categorical_features": categoricas},
        "hoja": {"regla": parametro.get("hoja", ""), "con_la_muestra_del_modelado": af["muestra"]["filas"], "valor": hoja},
        "semilla": g["semilla"],
        "muestra": {"regla": g["muestra"], "fraccion_sanas": (float(fraccion.group(1).replace(",", ".")) / 100) if fraccion else None,
                    "en_el_modelado": af["muestra"]},
        "objetivo_conocido": {"regla": "entrenan las fotos con fecha y horizonte_hasta anteriores a la fecha del entrenamiento",
                              "fecha_en_el_modelado": conocido["conocido_desde"],
                              "fotos_en_el_modelado": af["filas_entrena"], "fallos_en_el_modelado": af["fallos_entrena"]},
        "recalibracion": {"metodo": g["recalibracion"]["metodo"],
                          "formula": "odds = p/(1-p) · [real/(1-real)] / [muestra/(1-muestra)]; probabilidad = odds/(1+odds)",
                          "tasa_muestra_en_el_modelado": g["recalibracion"]["tasa_muestra"],
                          "tasa_real_en_el_modelado": g["recalibracion"]["tasa_real"]},
        "columnas": list(g["columnas"]),
        "columnas_que_lee": list(g["columnas_que_lee_el_preprocesador"]),
        "datacenter": g["datacenter"],
        "fuente": MODELADO,
    }


def corte_de(m):
    """El corte: listas de cada foto mensual, con sus tamaños y la principal leídos del modelado."""
    meses = m["validacion"]["por_mes"]
    tamanos = sorted({int(k.rsplit("_", 1)[1]) for mes in meses for k in mes if re.fullmatch(r"modelo_lista_\d+", k)})
    principal = re.search(r"entre los (\d+) discos", m["aprobado_antes"]["medida_principal"])
    if not tamanos or not principal or int(principal.group(1)) not in tamanos:
        raise Parada("modelado.json no da los tamaños de las listas o la principal no es uno de ellos")
    return {"como": "parte de cada grupo", "valores": tamanos, "principal": int(principal.group(1)),
            "grupo": GRUPO_DEL_CORTE, "desempate": DESEMPATE,
            "regla": "cada foto mensual se ordena por la probabilidad, de mayor a menor; a igual probabilidad, por serial_number; cada lista marca los N primeros",
            "por_que": m["corte"]["por_que"],
            "donde_se_lee": "produccion/configuracion.json, que escribe la parte 2",
            "fuente": f"{MODELADO} (validacion.por_mes y aprobado_antes.medida_principal); reglas de negocio §7, cuestión 010"}


def historia_de(finalistas):
    """Las tablas de historia que pide ejecutar, juntando las de los pasos de las cadenas que necesitan otras filas."""
    por_id = {p["id"]: p for p in PASOS}
    usados = sorted({i for f in finalistas for i in f["pasos"]})
    tablas = {}
    for i in usados:
        p = por_id[i]
        if p["clase"] != "necesita otras filas" or p["ejecutar"].startswith("No"):
            continue
        for h in p["historia"]:
            t = tablas.setdefault(h["tabla"], {"tabla": h["tabla"], "columnas": [], "hasta": h["hasta"], "pasos": []})
            t["columnas"] += [c for c in h["columnas"] if c not in t["columnas"]]
            t["pasos"].append(i)
    return list(tablas.values())


def entrada_de(finalistas):
    """Las columnas que ejecutar necesita en la foto: lo que leen los pasos de las cadenas y los smart_* finalistas."""
    por_id = {p["id"]: p for p in PASOS}
    columnas = []
    for f in finalistas:
        for i in f["pasos"]:
            columnas += [c for c in por_id[i]["lee"] if c not in columnas]
        if PATRON_SMART.match(f["variable"]) and f["variable"] not in columnas:
            columnas.append(f["variable"])
    return columnas


# =================================================================================================================
# 7. El contrato
# =================================================================================================================
def construir_contrato(m, lee, fuente_finalistas, cadenas):
    """El contrato como diccionario: lo que se escribe en Markdown y en el JSON."""
    g = m["ganador"]
    por_id = {p["id"]: p for p in PASOS}
    finalistas = []
    for c in cadenas:
        v = c["variable"]
        columnas = [v] if v in g["columnas"] else []
        if v in lee and not columnas:
            nota = f"el preprocesador la lee y no saca columna: {g['datacenter']}"
        elif v not in lee:
            nota = "no entra al modelo: " + ("es el identificador" if v in IDENTIFICADOR else "es el objetivo" if v == OBJETIVO else "fija qué fotos entrenan")
        else:
            nota = "entra al modelo con su nombre"
        finalistas.append({"variable": v, "columnas_del_modelo": columnas, "nota": nota, "pasos": c["pasos"]})
    usados = sorted({i for f in finalistas for i in f["pasos"]}, key=[p["id"] for p in PASOS].index)
    pasos = []
    for orden, i in enumerate(usados, start=1):
        p = por_id[i]
        origen = ", ".join(p["fichas"]) if p["fichas"] else ""
        citas = [x for x in (origen, f"reglas de transformación, «{p['apartado']}»" if p["apartado"] else "",
                             f"«{p['apartado_extra']}»" if p.get("apartado_extra") else "", p["fuente"] or "") if x]
        pasos.append({"orden": orden, "id": i, "nombre": p["nombre"], "fuente": "; ".join(citas), "clase": p["clase"],
                      "que": p["que"], "por_que": p["por_que"], "reentrenar": p["reentrenar"], "ejecutar": p["ejecutar"],
                      "historia": [h["tabla"] for h in p["historia"]] or ["no necesita"]})
    receta = receta_de(m, finalistas)
    return {
        "identificador": {"columnas": IDENTIFICADOR, "que_es": "la foto: un disco (serial_number) el día de su foto mensual (fecha)"},
        "objetivo": {"columna": OBJETIVO, "que_es": "1 si el disco tiene un fallo en los 30 días siguientes a la foto (reglas, apartado 7, cuestión 003 y cuestión 004)",
                     "horizonte": HORIZONTE},
        "finalistas_fuente": fuente_finalistas,
        "finalistas": finalistas,
        "pasos": pasos,
        "receta": receta,
        "corte": corte_de(m),
        "entrada_de_ejecutar": {"tabla": "una foto mensual con las columnas de data/raw/podado/fotos_mensuales/",
                                "columnas_que_lee": entrada_de(finalistas),
                                "comprobaciones": "las columnas por nombre; los números no llegan como texto; la fecha de la foto es la del mes que se pide"},
        "historia": historia_de(finalistas),
    }


def tabla(cabecera, filas):
    """Una tabla Markdown."""
    return ["| " + " | ".join(cabecera) + " |", "|" + "---|" * len(cabecera)] + ["| " + " | ".join(map(str, f)) + " |" for f in filas]


def contrato_md(c, m, fecha):
    """El texto del contrato para el responsable del caso, generado del diccionario (transmision-conocimiento)."""
    r, corte, af = c["receta"], c["corte"], m["ajuste_final"]
    n_modelo = len(r["columnas"])
    n_lee = len(r["columnas_que_lee"])
    clases = {k: sum(1 for p in c["pasos"] if p["clase"] == k) for k in CLASES}
    L = ["---",
         "titulo: Contrato de producción del caso 68 · qué pasos llevan cada foto de disco desde el dato en bruto hasta la probabilidad de fallo",
         f"estado: aprobado por {APROBADO_POR}",
         f"fecha_documento: {fecha}",
         "dueno: El responsable del caso (aprueba)",
         f"fuente: {MODELADO}; {REGISTRO}; {REGLAS}; {MATRIZ}; generado por {SCRIPT}",
         "---", "",
         "# Contrato de producción", "",
         f"Este contrato fija qué hace producción con cada foto mensual de un disco para darle su probabilidad de fallo a 30 "
         f"días con el modelo aprobado, un {r['algoritmo']}. Cada columna que entra al modelo tiene su cadena de pasos desde "
         f"el dato en bruto, y cada paso, su clase. Con él aprobado se escribe el código de producción; sin aprobar, no.", "",
         "## Lo que se aprueba", "",
         f"- **El modelo:** el ganador de la validación, con su receta fija; usa {n_modelo} columnas y su preprocesador lee "
         f"{n_lee}, porque lee también datacenter y lo vacía.",
         f"- **Las finalistas:** {len(c['finalistas'])} variables: las {n_lee} que lee el preprocesador, el identificador "
         f"(serial_number y fecha), el objetivo ({OBJETIVO}) y su horizonte ({HORIZONTE}).",
         f"- **Los pasos:** {len(c['pasos'])}, de ellos {clases['quita filas']} quitan filas, {clases['no aprende']} no "
         f"aprenden, {clases['necesita otras filas']} necesitan otras filas y {clases['aprende']} aprenden.",
         f"- **El corte:** las listas de {', '.join(numero(v) for v in corte['valores'][:-1])} y {numero(corte['valores'][-1])} "
         f"discos de más riesgo de cada foto mensual, con la de {numero(corte['principal'])} como principal.", "",
         "## El identificador y el objetivo", "",
         f"Cada fila es una foto: un disco ({c['identificador']['columnas'][0]}) el día de su foto mensual "
         f"({c['identificador']['columnas'][1]}). Al ejecutar sale una fila por cada fila de entrada, en el mismo orden y "
         f"con su identificador.", "",
         f"El objetivo es {OBJETIVO}: {c['objetivo']['que_es']}. Solo lo usa el reentreno, que lo recibe hecho en la tabla "
         f"de entrenamiento; al ejecutar no se calcula ni se usa.", "",
         "## Las finalistas y su cadena", "",
         f"Salen de {c['finalistas_fuente']}, porque el {r['algoritmo']} no se preseleccionó. La cadena se lee con los "
         f"pasos del apartado siguiente, en su orden.", ""]
    L += tabla(["Variable", "Columna del modelo", "Cadena", "Nota"],
               [[f"`{f['variable']}`", ", ".join(f"`{x}`" for x in f["columnas_del_modelo"]) or "ninguna",
                 " → ".join(f["pasos"]), f["nota"]] for f in c["finalistas"]])
    L += ["", "## Los pasos", "",
          "Cada paso cita la ficha del registro de transformaciones que lo hizo y, cuando la ficha remite a las reglas de "
          "transformación, el apartado que lo define. La clase decide dónde va: lo que quita filas, solo al reentrenar y "
          "contado; lo que no aprende, como función, igual en los dos scripts; lo que necesita otras filas, con la historia "
          "hasta el día de la foto; lo que aprende, dentro del Pipeline, con fit en el entrenamiento.", ""]
    L += tabla(["Orden", "Paso", "Fuente", "Clase", "Qué hace", "Al reentrenar", "Al ejecutar"],
               [[p["orden"], f"{p['id']} · {p['nombre']}", p["fuente"], p["clase"], p["que"], p["reentrenar"], p["ejecutar"]]
                for p in c["pasos"]])
    L += ["", "**Por qué va cada paso en su clase**, cuando no es evidente:", ""]
    L += [f"- **{p['id']}, {p['nombre']} ({p['clase']}).** {p['por_que']}" for p in c["pasos"]
          if p["clase"] in ("necesita otras filas", "aprende") or p["id"] in ("P09", "P10", "P11")]
    L += ["", "## La receta del modelo", "",
          f"El reentreno rehace el modelo con esta receta, leída de {r['fuente']}, y no vuelve a buscar algoritmo ni "
          f"hiperparámetros.", "",
          f"- **Algoritmo:** {r['algoritmo']}, con early_stopping={r['fijos']['early_stopping']}, "
          f"random_state={r['fijos']['random_state']} y las categóricas nativas "
          f"{', '.join('`' + x + '`' for x in r['fijos']['categorical_features'])}.",
          f"- **Hiperparámetros:** {json.dumps(r['hiperparametros'], ensure_ascii=False)}.",
          f"- **La hoja (min_samples_leaf):** {r['hoja']['regla']}. Con la muestra del modelado, de "
          f"{numero(r['hoja']['con_la_muestra_del_modelado'])} fotos, da {numero(r['hoja']['valor'])}, la del ajuste final.",
          f"- **La muestra:** {r['muestra']['regla']}. En el modelado fueron {numero(af['muestra']['filas'])} fotos, "
          f"{numero(af['muestra']['fallos'])} con fallo.",
          f"- **El objetivo conocido:** {r['objetivo_conocido']['regla']}. En el ajuste final la fecha fue el "
          f"{r['objetivo_conocido']['fecha_en_el_modelado']}, con {numero(af['filas_entrena'])} fotos y "
          f"{numero(af['fallos_entrena'])} con fallo.",
          f"- **La recalibración:** {r['recalibracion']['metodo']}, con {r['recalibracion']['formula']}. Las dos tasas "
          f"se miden en cada reentreno; en el modelado fueron {numero(r['recalibracion']['tasa_muestra_en_el_modelado'], 7)} "
          f"en la muestra y {numero(r['recalibracion']['tasa_real_en_el_modelado'], 7)} la real.",
          f"- **La semilla:** {r['semilla']}, en la muestra y en el modelo.", "",
          "## El corte", "",
          f"El modelo no decide con un umbral. Cada foto mensual se ordena por la probabilidad, de mayor a menor, y a igual "
          f"probabilidad por {corte['desempate']}. La salida lleva una marca por cada lista: los "
          f"{', '.join(numero(v) for v in corte['valores'][:-1])} y {numero(corte['valores'][-1])} primeros de la foto. "
          f"La lista principal es la de {numero(corte['principal'])}.", "",
          f"No se elige un solo tamaño porque {corte['por_que']}. Los tamaños se leen de {corte['donde_se_lee']}.", "",
          "## La historia que pide ejecutar", "",
          f"La entrada de ejecutar es {c['entrada_de_ejecutar']['tabla']}. Antes de puntuar comprueba "
          f"{c['entrada_de_ejecutar']['comprobaciones']}. Lee de la foto {len(c['entrada_de_ejecutar']['columnas_que_lee'])} "
          f"columnas. Además necesita esta historia, que nunca pasa del día de la foto:", ""]
    L += [f"- **{h['tabla']}**, hasta {h['hasta']}: {', '.join('`' + x + '`' for x in h['columnas'])}. La usan "
          f"{', '.join(h['pasos'])}." for h in c["historia"]]
    L += ["", "## Datos personales", "",
          "Los datos son de discos: serial_number identifica un disco y no a una persona (reglas, apartado 9), y el modelo no lo "
          "lee. El contrato no usa ni deja ninguna columna de datos personales. No existe "
          "config/fuentes/proteccion-datos.json: los datos no pasaron por la protección porque no hacía falta.", "",
          "## Límites", ""]
    L += [f"- {x}" for x in LIMITES]
    L += ["", "## La aprobación", "",
          f"{APROBADO_POR}, el {FECHA_APROBACION}. El arreglo es el de P06 y P12: al ejecutar, la primera aparición "
          "solo usa las ventanas de fallos ocurridos antes del día de la foto. Con el contrato aprobado se escriben el "
          "módulo del Pipeline, el reentreno, la ejecución y la prueba por otro camino.", ""]
    return "\n".join(L)


LIMITES = [
    "El contrato describe la parte 2, que todavía no existe: nada de él se ha ejecutado sobre los datos.",
    "La capacidad del modelo se toma al ejecutar de la historia de fotos y ventanas hasta el día de la foto. En el "
    "desarrollo salió de todo el periodo, también del recuento diario. Si algún modelo tiene su única capacidad válida "
    "solo en el recuento, NO SE PUEDE SABER sin medirlo; lo mide la parte 2 con las fotos de control.",
    "La primera aparición de un disco sin horas encendido solo usa las ventanas de fallos ocurridos antes del día de la "
    "foto. El desarrollo usó también las de fallos posteriores: en una de las 2.735 fotos sin horas de fotos_riesgo la "
    "edad puede salir distinta, y la prueba del módulo la cuenta aparte.",
    "En la validación, dos discos con la misma probabilidad cerca del borde de una lista se contaron con su valor "
    "esperado (por eso hay cifras con decimales); producción desempata por serial_number. Las listas pueden diferir en "
    "esos empates.",
]


# =================================================================================================================
# 8. El resultado (resultado.md)
# =================================================================================================================
def base(fecha_ejecucion):
    """El bloque común del JSON, para escribirlo también si el script para o falla."""
    return {"metodo": METODO, "version_metodo": VERSION_METODO, "script": SCRIPT, "fecha_datos": None,
            "fecha_ejecucion": fecha_ejecucion, "entradas": [], "resultado": {}, "pendientes": [],
            "contrato": {"ruta": CONTRATO, "aprobado_por": "", "fecha": ""}, "identificador": "", "objetivo": "",
            "finalistas": [], "receta": None,
            "codigo": {"modulo": "scripts/pipeline_riesgo.py", "reentrenar": "produccion/reentrenar.py",
                       "ejecutar": "produccion/ejecutar.py", "prueba": "tests/comprobar_produccion_por_otro_camino.py"},
            "reentreno": None, "lote": None, "prueba_por_otro_camino": None,
            "validaciones": {"cadenas_completas": None, "pasos_con_clase": None, "aprende_tras_la_particion": None,
                             "contrato_sin_vacios": None, "columnas_del_contrato": None, "filas_ejecucion": None,
                             "bit_a_bit": None, "otro_camino": None, "sin_quitar_filas_al_ejecutar": None,
                             "ficha_cuadra": None, "cambia_con_datos_nuevos": None},
            "parametros": PARAMETROS, "teoria": TEORIA, "datos_personales": None, "limites": LIMITES}


def resultado_json(r, c, m):
    """Pasa el contrato al JSON con la forma de resultado.md."""
    por_id = {p["id"]: p for p in c["pasos"]}
    r["fecha_datos"] = m.get("fecha_datos")
    r["identificador"] = " y ".join(c["identificador"]["columnas"]) + ": " + c["identificador"]["que_es"]
    r["objetivo"] = c["objetivo"]["columna"]
    r["finalistas"] = [{"variable": f["variable"], "columnas_del_modelo": f["columnas_del_modelo"],
                        "cadena": [{"ficha": por_id[i]["fuente"], "paso": f"{i} · {por_id[i]['nombre']}",
                                    "clase": por_id[i]["clase"]} for i in f["pasos"]]} for f in c["finalistas"]]
    rc = c["receta"]
    r["receta"] = {"algoritmo": rc["algoritmo"], "hiperparametros": rc["hiperparametros"], "fijos": rc["fijos"],
                   "hoja": rc["hoja"], "semilla": rc["semilla"], "muestra": rc["muestra"],
                   "objetivo_conocido": rc["objetivo_conocido"], "recalibracion": rc["recalibracion"],
                   "corte": {k: c["corte"][k] for k in ("como", "valores", "grupo", "principal", "desempate", "regla")},
                   "fuente": rc["fuente"]}
    r["pasos"] = c["pasos"]
    r["historia_de_ejecutar"] = c["historia"]
    r["entrada_de_ejecutar"] = c["entrada_de_ejecutar"]
    for p in r["parametros"]:
        if p["nombre"] == "semilla":
            p["valor"] = rc["semilla"]
        if p["nombre"] == "corte":
            p["valor"] = f"listas de {', '.join(map(str, c['corte']['valores']))} por foto mensual; principal {c['corte']['principal']}"


def escribir_json(raiz, r):
    """Escribe informes/preproduccion.json."""
    (raiz / "informes").mkdir(exist_ok=True)
    (raiz / SALIDA_JSON).write_text(json.dumps(a_json(r), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")


# =================================================================================================================
# 9. Ejecución
# =================================================================================================================
def principal(raiz):
    """Escribe el contrato y el JSON del caso que está en raiz; devuelve el diccionario del JSON."""
    fecha_ejecucion = dt.datetime.now().replace(microsecond=0).isoformat()
    r = base(fecha_ejecucion)
    try:
        # 9.1 Las entradas, con su huella
        for ruta in (MODELADO, PRESELECCION, REGISTRO, REGLAS, MATRIZ):
            if (raiz / ruta).exists():
                r["entradas"].append({"ruta": ruta, "sha256": sha256(raiz / ruta)})
        m = leer_modelado(raiz)
        r["fecha_datos"] = m.get("fecha_datos")
        preseleccion = json.loads(leer_texto(raiz, PRESELECCION)) if (raiz / PRESELECCION).exists() else None
        fichas = leer_registro(leer_texto(raiz, REGISTRO))
        apartados = leer_apartados(leer_texto(raiz, REGLAS))
        matriz = leer_matriz(leer_texto(raiz, MATRIZ))

        # 9.2 Finalistas, hilo y clases, con las comprobaciones que paran con ERROR
        lee, fuente = finalistas_de(m, matriz, preseleccion)
        variables = lee + [v for v in IDENTIFICADOR + [OBJETIVO, HORIZONTE] if v not in lee]
        cadenas = tirar_del_hilo(variables, fichas, apartados)
        r["validaciones"]["cadenas_completas"] = len(cadenas) == len(variables)
        r["validaciones"]["pasos_con_clase"] = v_fichas_con_clase(fichas)
        r["validaciones"]["aprende_tras_la_particion"] = v_aprende_tras_la_particion(fichas, m)
        contrato = construir_contrato(m, lee, fuente, cadenas)
        r["validaciones"]["contrato_sin_vacios"] = v_contrato_sin_vacios(contrato)

        # 9.3 Lo que se escribe: el contrato y el JSON, solo con todas las comprobaciones en verde
        resultado_json(r, contrato, m)
        proteccion = (raiz / PROTECCION).exists()
        r["datos_personales"] = ("Los datos son de discos: serial_number identifica un disco, no a una persona (reglas, apartado 9). "
                                 "El contrato no usa ni deja ninguna columna de datos personales. "
                                 + ("Existe config/fuentes/proteccion-datos.json." if proteccion else
                                    "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección."))
        fecha = dt.date.today().isoformat()
        (raiz / CONTRATO).parent.mkdir(parents=True, exist_ok=True)
        (raiz / CONTRATO).write_text(contrato_md(contrato, m, fecha), encoding="utf-8")
        r["contrato"].update(aprobado_por=APROBADO_POR, fecha=FECHA_APROBACION)
        r["pendientes"] = []
        r["resultado"] = {"estado": "AVISO", "riesgo": "medio",
                          "resumen": (f"Contrato aprobado ({APROBADO_POR}): {len(contrato['finalistas'])} finalistas, todas "
                                      f"con su cadena, y {len(contrato['pasos'])} pasos, cada uno con su clase. Falta la parte 2."),
                          "artefactos": [CONTRATO, SALIDA_JSON],
                          "siguiente": "la parte 2: el Pipeline, reentrenar, ejecutar y la prueba por otro camino"}
    except Parada as e:
        r["resultado"] = {"estado": e.estado, "riesgo": "alto" if e.estado == "ERROR" else "medio", "resumen": str(e),
                          "artefactos": [SALIDA_JSON],
                          "siguiente": "arreglar lo que dice el resumen y volver a ejecutar" if e.estado == "ERROR"
                          else "lo que dice el resumen, antes de empezar"}
        r["finalistas"], r["receta"] = [], None
    escribir_json(raiz, r)
    return r


def main():
    """Punto de entrada: --raiz es la carpeta del caso (por defecto, la de este script)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raiz", type=Path, default=CASO)
    args = ap.parse_args()
    r = principal(args.raiz.resolve())
    print(f"{r['resultado']['estado']}: {r['resultado']['resumen']}")
    sys.exit(0 if r["resultado"]["estado"] in ("OK", "PARADO", "AVISO") else 1)


if __name__ == "__main__":
    main()
