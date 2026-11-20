"""Informe ejecutivo del caso 68 (patrón assets/07_patron_informe_ejecutivo.md), en HTML A4 y en PDF.

El texto es el aprobado en contexto-proyecto/metodo/borrador_informe_ejecutivo.md, desde «# Los fallos de los discos de
datos» hasta el final, copiado tal cual en BLOQUES. Cada cifra va marcada como [[nombre|cifra]]: «nombre» es la cifra
de informes/consultas-informe-ejecutivo.json y «cifra», cómo la escribe el texto aprobado. El HTML lleva la cifra del
JSON escrita con numero() de assets/graficos.py, con tantos decimales como la del texto; si no sale igual, para.

Antes de escribir el HTML para con ERROR si:
  - una cifra del texto no es la de su JSON, redondeada como la escribe el texto, o hay un número sin marcar que no es
    una fecha, un año ni un dato fijo de las reglas (37 y 50 dólares, 0,74 horas, 365 días);
  - un apartado pasa de su tope de palabras (§1 del patrón);
  - aparece una palabra vetada, salvo dentro de un nombre de fichero entre comillas invertidas;
  - deja de cumplirse una frase con sentido (exigir()).
Después imprime el PDF con Edge sin ventana, espera a que exista y deje de crecer, y para con ERROR si el anexo no
empieza en una página solo suya, si lo anterior no cabe en dos páginas o si pasa de tres.

Cómo se cuentan las palabras: en el texto visible, una palabra es un trozo entre espacios con al menos una letra o
una cifra (la barra del subtítulo no cuenta). Cada apartado cuenta su texto sin su encabezado H2 o H3; el primero
cuenta el título, el subtítulo y el resumen.

Depende de scripts/07_consultas_informe_ejecutivo.py: lee su JSON. No usa assets/informe.py.

Uso: python -W error scripts/08_informe_ejecutivo.py [--raiz CARPETA_DEL_CASO]
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from pypdf import PdfReader

CASO = Path(__file__).resolve().parents[1]
# Las piezas comunes se usan desde assets/, sin copiarlas (programacion-del-caso §1)
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/08_informe_ejecutivo.py"
CONSULTAS = "informes/consultas-informe-ejecutivo.json"
HTML = "informes/informe_ejecutivo.html"
PDF = "informes/informe_ejecutivo.pdf"
RESUMEN = "informes/informe_ejecutivo.json"
FECHA_DATOS = "2025-06-30"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
# Espera al PDF: Edge puede devolver el control antes de terminar de escribirlo (patrón §6)
ESPERA_MAXIMA_S = 120
INTERVALO_S = 0.5

# Topes de palabras de cada apartado (patrón §1)
TOPES = {"resumen": 300, "encontrado": 400, "limites": 100, "recomendaciones": 200, "anexo": 500}
# Palabras que no salen en el informe (encargo)
# La palabra vetada para el conjunto de discos va partida para que el script tampoco la lleve (R68-93)
VETADAS = ["foto", "fotos", "construcción", "validación", "suceso", "entidad", "avería", "averías", "flo" + "ta", "pliegue"]
# Números que el texto escribe sin sacarlos del JSON: años y días de las fechas, la fecha de emisión y los datos fijos
# de las reglas (37 dólares de mano de obra por disco, 50 dólares por hora, 0,74 horas por disco, 365 días)
SIN_JSON = {"2020", "2021", "2022", "2023", "2024", "2025", "2026", "1", "30", "17", "11", "365", "37", "50", "0,74"}
TITULO_ANEXO = "Anexo: trabajo realizado"

MARCA = re.compile(r"\[\[(\w+)\|([^\]]+)\]\]")
CODIGO = re.compile(r"`[^`]*`")


class Parada(Exception):
    """Condición que impide dar el informe por bueno; el mensaje dice cuál."""


# =================================================================================================================
# 3. El texto aprobado
# =================================================================================================================
# Cada bloque: [apartado, tipo, contenido]. Tipos: h1, h2, h3, p, ul (una viñeta es un texto o [texto, [viñetas]]),
# ol y tabla ({"cabecera": [...], "filas": [[...]]}). Las cifras, [[nombre|como la escribe el texto]].
def _fila(ano, etiqueta):
    """Una fila del resumen anual con sus cinco cifras marcadas."""
    return [etiqueta, f"[[dias_disco_{ano}|{{d}}]]", f"[[fallos_{ano}|{{f}}]]", f"[[tasa_anual_pct_{ano}|{{t}}]] %",
            f"[[coste_fallos_usd_{ano}|{{c}}]]", f"[[coste_fallos_garantia_usd_{ano}|{{g}}]]"]


def _con(fila, d, f, t, c, g):
    """Pone en una fila las cifras como las escribe el texto aprobado."""
    return [x.format(d=d, f=f, t=t, c=c, g=g) for x in fila]


BLOQUES = [
    # -------------------------------------------------------------------------------------------------------------
    # 3.1 Título, subtítulo y resumen
    # -------------------------------------------------------------------------------------------------------------
    ["resumen", "h1", "Los fallos de los discos de datos supusieron un coste de [[coste_fallos_usd_2024|832.698]] "
                      "dólares en 2024, [[razon_coste_2024_2020|3,3]] veces el de 2020"],
    ["resumen", "p", "Informe para la Dirección de Operaciones de los Centros de Datos"],
    ["resumen", "p", "Periodo analizado: 1 de enero de 2020 al 30 de junio de 2025 | Cierre de datos: "
                     "[[fecha_datos|30/06/2025]] | Emisión: 17/11/2026"],
    ["resumen", "h2", "Resumen ejecutivo"],
    ["resumen", "ul", [
        "Los **[[fallos_2024|4.538]] fallos** registrados en los discos de datos durante 2024 supusieron un coste de "
        "**[[coste_fallos_usd_2024|832.698]] dólares** en unidades nuevas y mano de obra de sustitución. Si se "
        "descuentan los discos cubiertos por la garantía del fabricante, el coste baja a "
        "**[[coste_fallos_garantia_usd_2024|305.124]] dólares**.",
        ["Ese coste aumentó de forma ininterrumpida entre 2020 y 2024, pasando de **[[coste_fallos_usd_2020|250.485]] "
         "a [[coste_fallos_usd_2024|832.698]] dólares**. En esos años se dieron dos cambios a la vez:", [
             "**El crecimiento del parque.** El 1 de abril de 2025 había **[[discos_inicio_2025_T2|308.836]] discos de "
             "datos** en servicio, [[razon_discos_ultimo_primero|2,5]] veces los [[discos_inicio_2020_T1|122.696]] del "
             "1 de enero de 2020.",
             "**El aumento de la tasa de fallo.** La tasa anual alcanzó el **[[tasa_anual_pct_2024|1,6]] %** en 2024, "
             "frente al [[tasa_anual_pct_2020|0,9]] % de 2020, tras marcar un máximo del [[tasa_anual_pct_2023|1,7]] % "
             "en 2023."]],
        "Además, el **[[parte_fallos_garantia_pct_2024|71,8]] %** de los discos que fallaron en 2024 "
        "([[fallos_en_garantia_2024|3.258]] de [[fallos_2024|4.538]]) seguía dentro del periodo de garantía del "
        "fabricante.",
    ]],
    ["resumen", "p", "Se solicita a la Dirección de Operaciones que apruebe tres líneas de actuación:"],
    ["resumen", "ol", [
        "**Calcular el coste por terabyte y año de cada modelo de disco.**",
        "**Analizar a qué antigüedad aumentan los fallos, comprobar si algún centro registra una mayor incidencia y "
        "estimar el volumen de fallos por trimestre.**",
        "**Elaborar un listado mensual con los discos que presenten mayor riesgo de fallo.**",
    ]],
    ["resumen", "p", "**La primera medida es la que condiciona la compra de nuevo equipamiento** y, por tanto, la que "
                     "tiene mayor impacto económico."],
    # -------------------------------------------------------------------------------------------------------------
    # 3.2 Conclusiones: lo que hemos encontrado
    # -------------------------------------------------------------------------------------------------------------
    ["conclusiones", "h2", "Conclusiones y recomendaciones"],
    ["encontrado", "h3", "Lo que hemos encontrado"],
    ["encontrado", "ul", [
        "**[[coste_fallos_usd_2024|832.698]] dólares en 2024.** Esta cifra corresponde a los [[fallos_2024|4.538]] "
        "fallos del año, calculando para cada uno el precio de un disco nuevo de igual capacidad a tarifa de 2024 más "
        "37 dólares de mano de obra. Para las unidades en garantía, el coste se limitaría a esos 37 dólares.",
        "**De [[coste_fallos_usd_2020|250.485]] a [[coste_fallos_usd_2024|832.698]] dólares.** El coste por año "
        "completo fue de [[coste_fallos_usd_2020|250.485]] dólares en 2020, [[coste_fallos_usd_2021|352.674]] en 2021, "
        "[[coste_fallos_usd_2022|565.844]] en 2022, [[coste_fallos_usd_2023|755.879]] en 2023 y "
        "[[coste_fallos_usd_2024|832.698]] en 2024.",
        "**[[discos_inicio_2025_T2|308.836]] discos activos.** Es el total de unidades en servicio al inicio del "
        "segundo trimestre de 2025. Desde los [[discos_inicio_2020_T1|122.696]] discos contabilizados el 1 de enero de "
        "2020, el parque creció en todos los trimestres.",
        "**Tasa anual del [[tasa_anual_pct_2024|1,6]] % en 2024.** Este indicador se obtiene dividiendo los fallos del "
        "año entre los días de disco acumulados y multiplicando el resultado por 365; en 2024 fueron "
        "[[fallos_2024|4.538]] fallos sobre [[dias_disco_millones_2024|103,8]] millones de días de disco. La serie por "
        "año completo es la siguiente: [[tasa_anual_pct_2020|0,9]] % en 2020, [[tasa_anual_pct_2021|1,0]] % en 2021, "
        "[[tasa_anual_pct_2022|1,4]] % en 2022, [[tasa_anual_pct_2023|1,7]] % en 2023 y [[tasa_anual_pct_2024|1,6]] % "
        "en 2024.",
        "**[[parte_fallos_garantia_pct_2024|71,8]] % bajo garantía.** En 2024, [[fallos_en_garantia_2024|3.258]] de "
        "los [[fallos_2024|4.538]] discos que fallaron seguían cubiertos por los años de garantía del fabricante, "
        "calculados según sus horas de funcionamiento.",
    ]],
    # -------------------------------------------------------------------------------------------------------------
    # 3.3 Límites
    # -------------------------------------------------------------------------------------------------------------
    ["limites", "h3", "Límites"],
    ["limites", "ul", [
        "Los datos de 2025 llegan solo al 30 de junio y no se comparan con los años completos.",
        "Desde 2023, el precio de los discos es estimado, ya que Backblaze solo publicó esos precios hasta 2022.",
        "No consta si Backblaze reclama la garantía, por lo que la cifra principal no la descuenta.",
        "La mano de obra supone 50 dólares por hora.",
        "La garantía se calcula por las horas de encendido, no por la fecha de compra.",
        "Cuenta como fallo también la retirada de discos por avisos de sus contadores.",
        "Los datos no explican por qué aumentó la tasa de fallo.",
    ]],
    # -------------------------------------------------------------------------------------------------------------
    # 3.4 Recomendaciones
    # -------------------------------------------------------------------------------------------------------------
    ["recomendaciones", "h3", "Recomendaciones"],
    ["recomendaciones", "ol", [
        "**Calcular el coste por terabyte y año de cada modelo.** El equipo de análisis realizará este cálculo con los "
        "precios de cada año, a petición de la Dirección de Operaciones, con plazo por definir. Esta medida parte del "
        "coste de [[coste_fallos_usd_2024|832.698]] dólares de 2024.",
        "**Determinar a qué edad aumentan los fallos, la incidencia por centro y la previsión trimestral.** El equipo "
        "de análisis realizará este estudio para la Dirección de Operaciones, con plazo por definir, a partir de la "
        "tasa de fallo del [[tasa_anual_pct_2024|1,6]] % de 2024.",
        "**Elaborar un listado mensual de discos con alto riesgo de fallo.** El equipo de análisis lo preparará y lo "
        "contrastará con una regla basada en los avisos de cinco contadores, y los técnicos de sala lo revisarán; el "
        "plazo está por definir. Esta acción toma como referencia los [[fallos_2024|4.538]] fallos de 2024. Su "
        "objetivo es organizar el trabajo operativo y prevenir la pérdida de datos; no reduce el coste, ya que un disco "
        "que falla hay que sustituirlo igualmente.",
    ]],
    # -------------------------------------------------------------------------------------------------------------
    # 3.5 Anexo, en página nueva
    # -------------------------------------------------------------------------------------------------------------
    ["anexo", "h2", TITULO_ANEXO],
    ["anexo", "ul", [
        "**Origen de los datos.** Registros públicos de discos duros de Backblaze comprendidos entre el 1 de enero de "
        "2020 y el 30 de junio de 2025; los posteriores se reservan para la prueba final del modelo. El estudio se "
        "centra en los discos de datos ([[fallos_tipo_datos|16.996]] fallos en el periodo) y excluye las unidades de "
        "arranque de los servidores, que no almacenan información de clientes ([[fallos_tipo_arranque|964]] fallos).",
        "**Definiciones.** Se considera fallo cualquier unidad dada de baja por Backblaze, ya sea por rotura o por "
        "retirada tras los avisos de sus contadores. Un día de disco equivale a una unidad en servicio durante una "
        "jornada. El coste por fallo suma el precio de un disco nuevo de igual capacidad en el año del fallo más 37 "
        "dólares de mano de obra.",
        "**Procedimiento.** Se trabajó sobre una copia depurada de los datos de origen y se prepararon las tablas para "
        "su análisis descriptivo. Los fallos y los costes de cada año se han calculado con dos tablas independientes y "
        "coinciden.",
    ]],
    ["anexo", "p", "**Resumen anual**"],
    ["anexo", "tabla", {
        "cabecera": ["Año", "Días de disco", "Fallos", "Tasa anual", "Coste total (dólares)",
                     "Coste con garantía (dólares)"],
        "filas": [
            _con(_fila(2020, "2020"), "51.345.918", "1.307", "0,9", "250.485", "80.209"),
            _con(_fila(2021, "2021"), "66.072.034", "1.823", "1,0", "352.674", "109.169"),
            _con(_fila(2022, "2022"), "78.890.669", "2.999", "1,4", "565.844", "200.888"),
            _con(_fila(2023, "2023"), "90.077.756", "4.201", "1,7", "755.879", "284.507"),
            _con(_fila(2024, "2024"), "103.839.696", "4.538", "1,6", "832.698", "305.124"),
            _con(_fila(2025, "2025 (hasta el 30 de junio)"), "55.882.610", "2.128", "1,4", "366.916", "170.296"),
        ]}],
    ["anexo", "ul", [
        "**Consultas complementarias.** La media mensual de fallos en 2024 fue de [[media_fallos_mes_2024|378]] discos. "
        "El número de unidades activas al inicio de cada trimestre pasó de [[discos_inicio_2020_T1|122.696]] el 1 de "
        "enero de 2020 a [[discos_inicio_2025_T2|308.836]] el 1 de abril de 2025, con incrementos en todos los "
        "trimestres.",
        "**Protección de datos.** Los registros no contienen información personal, ya que cada unidad se identifica "
        "únicamente por su número de serie y su modelo, por lo que no fue necesario aplicar medidas de protección.",
        "**Trazabilidad interna.** Los datos proceden de `informes/analisis-exploratorio__modelo_trimestre.json` y de "
        "`informes/consultas-informe-ejecutivo.json` (lo creará el script de consultas del informe).",
        "**Fuentes externas.** Base de datos pública Hard Drive Data and Stats de Backblaze (2020-2025); coste por "
        "gigabyte según capacidad, publicado por Backblaze hasta 2022 y estimado a partir de 2023; tiempo medio de "
        "sustitución de 0,74 horas por disco, del informe anual de Backblaze de 2025.",
    ]],
]


# =================================================================================================================
# 4. Cifras: del JSON al texto
# =================================================================================================================
def cargar_cifras(datos):
    """Diccionario nombre -> valor de las cifras del JSON de consultas, con su fecha_datos."""
    cifras = {c["nombre"]: c["valor"] for c in datos["cifras"]}
    cifras["fecha_datos"] = datos.get("fecha_datos")
    return cifras


def escribir(nombre, valor, como_texto):
    """La cifra del JSON escrita como la escribe el texto: con sus decimales, coma decimal y punto de miles."""
    if nombre == "fecha_datos":
        return dt.date.fromisoformat(valor).strftime("%d/%m/%Y")
    decimales = len(como_texto.split(",")[1]) if "," in como_texto else 0
    return numero(valor, decimales)


def textos(bloques):
    """Todos los textos de los bloques, con su apartado y su tipo: viñetas anidadas y celdas incluidas."""
    for apartado, tipo, contenido in bloques:
        if tipo in ("ul", "ol"):
            for item in contenido:
                if isinstance(item, list):
                    yield apartado, tipo, item[0]
                    for sub in item[1]:
                        yield apartado, tipo, sub
                else:
                    yield apartado, tipo, item
        elif tipo == "tabla":
            for celda in contenido["cabecera"] + [x for fila in contenido["filas"] for x in fila]:
                yield apartado, tipo, celda
        else:
            yield apartado, tipo, contenido


def con_json(texto, cifras):
    """El texto con cada cifra marcada sustituida por la del JSON (o por la del texto, si falta en el JSON)."""
    return MARCA.sub(lambda m: escribir(m[1], cifras[m[1]], m[2]) if m[1] in cifras else m[2], texto)


def comprobar_cifras(cifras, bloques=BLOQUES):
    """Errores de cifras: una que no sale como la escribe el texto, una que falta en el JSON o un número sin marcar."""
    errores = []
    for apartado, _, texto in textos(bloques):
        for m in MARCA.finditer(texto):
            if m[1] not in cifras:
                errores.append(f"{apartado}: la cifra {m[1]} ({m[2]}) no está en {CONSULTAS}")
                continue
            sale = escribir(m[1], cifras[m[1]], m[2])
            if sale != m[2]:
                errores.append(f"{apartado}: {m[1]} sale {sale} del JSON y el texto escribe {m[2]}")
        # Un número que no viene del JSON solo puede ser un año, un día de fecha o un dato fijo de las reglas
        resto = CODIGO.sub(" ", MARCA.sub(" ", texto))
        for n in re.findall(r"\d+(?:,\d+)?", resto):
            if n not in SIN_JSON:
                errores.append(f"{apartado}: el número {n} no sale del JSON ni es un año, una fecha o un dato fijo")
    return errores


# =================================================================================================================
# 5. Palabras: topes y vetadas
# =================================================================================================================
def plano(texto, cifras):
    """Texto visible: las cifras del JSON, sin marcas de negrita; las comillas invertidas se quedan."""
    return con_json(texto, cifras).replace("**", "")


def texto_plano(bloques, cifras):
    """Todo el texto visible del informe en una cadena."""
    return "\n".join(plano(t, cifras) for _, _, t in textos(bloques))


def contar_palabras(bloques, cifras):
    """Palabras de cada apartado, sin sus encabezados H2 y H3: trozos entre espacios con una letra o una cifra."""
    cuenta = {a: 0 for a in TOPES}
    for apartado, tipo, texto in textos(bloques):
        if tipo in ("h2", "h3") or apartado not in cuenta:
            continue
        cuenta[apartado] += sum(1 for w in plano(texto, cifras).replace("`", "").split() if re.search(r"\w", w))
    return cuenta


def comprobar_topes(palabras):
    """Errores de los apartados que pasan de su tope."""
    return [f"el apartado {a} tiene {n} palabras y su tope es {TOPES[a]}" for a, n in palabras.items()
            if n > TOPES[a]]


def sin_jerga(texto):
    """Errores por cada palabra vetada fuera de un nombre de fichero entre comillas invertidas."""
    fuera = CODIGO.sub(" ", texto)
    patron = re.compile(r"\b(" + "|".join(VETADAS) + r")\b", re.IGNORECASE)
    return [f"palabra vetada: «{m[0]}»" for m in patron.finditer(fuera)]


# =================================================================================================================
# 6. Frases con sentido
# =================================================================================================================
def exigir(c, bloques=BLOQUES):
    """Errores de las frases que dicen un sentido o un grupo y que las cifras ya no sostienen."""
    aprobado = " ".join(MARCA.sub(lambda m: m[2], t) for _, _, t in textos(bloques)).replace("**", "")
    errores = []

    def frase(texto, condicion):
        """Apunta un error si la frase no está en el texto o si su condición no se cumple."""
        try:
            cumple = bool(condicion())
        except (KeyError, TypeError, ZeroDivisionError) as e:
            cumple = False
            texto = f"{texto} (falta {e})"
        if texto.split(" (falta")[0] not in aprobado:
            errores.append(f"exigir: la frase «{texto}» ya no está en el texto")
        elif not cumple:
            errores.append(f"exigir: «{texto}» no se cumple con las cifras del JSON")

    coste = lambda a: c[f"coste_fallos_usd_{a}"]  # noqa: E731
    tasa = lambda a: c[f"tasa_anual_pct_{a}"]  # noqa: E731
    # El coste de cada año de 2020 a 2024 es mayor que el del anterior
    frase("aumentó de forma ininterrumpida entre 2020 y 2024", lambda: all(coste(a) > coste(a - 1)
                                                                          for a in range(2021, 2025)))
    # La razón de coste es la de 2024 entre 2020 y, con un decimal, 3,3
    frase("3,3 veces el de 2020", lambda: abs(c["razon_coste_2024_2020"] - coste(2024) / coste(2020)) < 1e-9
          and numero(c["razon_coste_2024_2020"], 1) == "3,3")
    # La razón de discos es la del 1 de abril de 2025 entre la del 1 de enero de 2020 y, con un decimal, 2,5
    frase("2,5 veces", lambda: c["primer_trimestre"] == "2020-T1" and c["ultimo_trimestre"] == "2025-T2"
          and abs(c["razon_discos_ultimo_primero"] - c["discos_inicio_2025_T2"] / c["discos_inicio_2020_T1"]) < 1e-9
          and numero(c["razon_discos_ultimo_primero"], 1) == "2,5")
    # Todas las subidas de un trimestre al siguiente lo son
    todas = lambda: c["pasos_trimestre"] > 0 and c["subidas_trimestre"] == c["pasos_trimestre"] \
        == c["trimestres"] - 1  # noqa: E731
    frase("creció en todos los trimestres", todas)
    frase("con incrementos en todos los trimestres", todas)
    # La tasa de 2023 es la mayor de 2020 a 2024
    frase("tras marcar un máximo del 1,7 % en 2023", lambda: tasa(2023) == max(tasa(a) for a in range(2020, 2025)))
    # La tasa de 2024 es mayor que la de 2020
    frase("frente al 0,9 % de 2020", lambda: tasa(2024) > tasa(2020))
    # 2025 no está completo y los datos acaban el 30 de junio
    frase("Los datos de 2025 llegan solo al 30 de junio", lambda: c["ano_completo_2025"] is False
          and c["fecha_datos"] == FECHA_DATOS)
    # Las dos tablas dan los mismos fallos y costes de cada año
    frase("se han calculado con dos tablas independientes y coinciden", lambda: all(
        c[f"detalle_fallos_{a}"] == c[f"fallos_{a}"]
        and abs(c[f"detalle_coste_fallos_usd_{a}"] - coste(a)) < 0.005
        and abs(c[f"detalle_coste_fallos_garantia_usd_{a}"] - c[f"coste_fallos_garantia_usd_{a}"]) < 0.005
        for a in range(2020, 2026)))
    return errores


# =================================================================================================================
# 7. HTML
# =================================================================================================================
ESTILO = """
@page { size: A4; margin: 20mm; }
html, body { background: #ffffff; color: #0b0b0b; }
body { margin: 0; font-family: "Segoe UI", sans-serif; font-size: 11pt; line-height: 1.4; }
h1, h2, h3 { font-weight: bold; color: #0b0b0b; line-height: 1.25; }
h1 { font-size: 18pt; margin: 0 0 6pt; }
h2 { font-size: 14pt; margin: 14pt 0 4pt; }
h3 { font-size: 12pt; margin: 10pt 0 4pt; }
p { margin: 0 0 6pt; }
ul { list-style: disc; margin: 0 0 6pt; padding-left: 18pt; }
ul ul { list-style: circle; margin: 3pt 0 0; }
ol { list-style: decimal; margin: 0 0 6pt; padding-left: 18pt; }
li { margin: 0 0 3pt; }
strong { font-weight: bold; }
code { font-family: Consolas, "Courier New", monospace; }
* { text-decoration: none; box-shadow: none; }
table { border-collapse: collapse; margin: 0 0 8pt; }
th, td { border: 0; padding: 1pt 6pt 1pt 0; text-align: left; vertical-align: top; }
th { font-weight: bold; }
.num { text-align: right; }
section.anexo { break-before: page; }
"""


def en_linea(texto, cifras):
    """Un texto en HTML: cifras del JSON, negrita y nombres de fichero en letra de código."""
    t = html.escape(con_json(texto, cifras), quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)


def lista(tipo, items, cifras):
    """Una lista con viñetas o numerada; una viñeta [texto, [viñetas]] lleva su lista anidada."""
    partes = []
    for item in items:
        if isinstance(item, list):
            partes.append(f"<li>{en_linea(item[0], cifras)}{lista('ul', item[1], cifras)}</li>")
        else:
            partes.append(f"<li>{en_linea(item, cifras)}</li>")
    return f"<{tipo}>" + "".join(partes) + f"</{tipo}>"


def tabla(contenido, cifras):
    """La tabla del anexo, con las cifras alineadas a la derecha (todas las columnas menos la primera)."""
    clase = lambda i: "" if i == 0 else ' class="num"'  # noqa: E731
    cab = "".join(f"<th{clase(i)}>{en_linea(x, cifras)}</th>" for i, x in enumerate(contenido["cabecera"]))
    filas = "".join("<tr>" + "".join(f"<td{clase(i)}>{en_linea(x, cifras)}</td>" for i, x in enumerate(f)) + "</tr>"
                    for f in contenido["filas"])
    return f"<table><thead><tr>{cab}</tr></thead><tbody>{filas}</tbody></table>"


def montar_html(cifras, bloques=BLOQUES):
    """El documento entero; el anexo va en su sección, que empieza en página nueva."""
    cuerpo, en_anexo = [], False
    for apartado, tipo, contenido in bloques:
        if apartado == "anexo" and not en_anexo:
            cuerpo.append('<section class="anexo">')
            en_anexo = True
        if tipo in ("h1", "h2", "h3", "p"):
            cuerpo.append(f"<{tipo}>{en_linea(contenido, cifras)}</{tipo}>")
        elif tipo in ("ul", "ol"):
            cuerpo.append(lista(tipo, contenido, cifras))
        elif tipo == "tabla":
            cuerpo.append(tabla(contenido, cifras))
    if en_anexo:
        cuerpo.append("</section>")
    return ("<!DOCTYPE html>\n<html lang=\"es\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<title>Informe ejecutivo · fallos de los discos de datos</title>\n"
            f"<style>{ESTILO}</style>\n</head>\n<body>\n" + "\n".join(cuerpo) + "\n</body>\n</html>\n")


# =================================================================================================================
# 8. PDF y páginas
# =================================================================================================================
def imprimir_pdf(ruta_html, ruta_pdf):
    """Imprime el HTML a PDF con Edge sin ventana y espera a que el PDF exista y deje de crecer."""
    if ruta_pdf.exists():
        ruta_pdf.unlink()
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={ruta_pdf}", ruta_html.resolve().as_uri()],
                   capture_output=True, timeout=ESPERA_MAXIMA_S)
    limite, anterior = time.monotonic() + ESPERA_MAXIMA_S, -1
    while time.monotonic() < limite:
        tam = ruta_pdf.stat().st_size if ruta_pdf.exists() else -1
        if tam > 0 and tam == anterior:
            return
        anterior = tam
        time.sleep(INTERVALO_S)
    raise Parada(f"Edge no dejó un PDF terminado en {ESPERA_MAXIMA_S} s")


def comprobar_paginas(paginas):
    """Errores de paginación: el anexo en página solo suya, lo anterior en dos páginas y tres como mucho en total."""
    errores = []
    if len(paginas) > 3:
        errores.append(f"el PDF tiene {len(paginas)} páginas y el tope es 3")
    normal = [" ".join(p.split()) for p in paginas]
    donde = [i for i, p in enumerate(normal) if TITULO_ANEXO in p]
    if not donde:
        return errores + ["el PDF no tiene el anexo"]
    i = donde[0]
    if not normal[i].startswith(TITULO_ANEXO):
        errores.append(f"el anexo empieza en la página {i + 1} detrás de otro texto: no tiene la página para él")
    if i > 2:
        errores.append(f"lo anterior al anexo ocupa {i} páginas y tiene que caber en dos")
    return errores


# =================================================================================================================
# 9. Ejecución
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def principal(raiz):
    """Comprueba el texto contra el JSON, escribe el HTML, imprime el PDF y comprueba sus páginas."""
    ruta_consultas = raiz / CONSULTAS
    if not ruta_consultas.exists():
        raise Parada(f"falta {CONSULTAS}: se crea con scripts/07_consultas_informe_ejecutivo.py")
    datos = json.loads(ruta_consultas.read_text(encoding="utf-8"))
    if datos.get("estado") != "OK" or datos.get("fecha_datos") != FECHA_DATOS:
        raise Parada(f"{CONSULTAS} no está en OK o su fecha_datos no es {FECHA_DATOS}")
    cifras = cargar_cifras(datos)

    # Las cuatro comprobaciones del texto, todas antes de escribir nada
    palabras = contar_palabras(BLOQUES, cifras)
    errores = (comprobar_cifras(cifras) + comprobar_topes(palabras) + sin_jerga(texto_plano(BLOQUES, cifras))
               + exigir(cifras))
    if errores:
        raise Parada("\nERROR: ".join(errores))

    # HTML y PDF
    ruta_html, ruta_pdf = raiz / HTML, raiz / PDF
    ruta_html.write_text(montar_html(cifras), encoding="utf-8")
    imprimir_pdf(ruta_html, ruta_pdf)
    paginas = [p.extract_text() or "" for p in PdfReader(ruta_pdf).pages]
    errores_pdf = comprobar_paginas(paginas)
    anexo = next((i + 1 for i, p in enumerate(paginas) if TITULO_ANEXO in " ".join(p.split())), None)

    # Resumen del informe, con su estado calculado
    estado = "ERROR" if errores_pdf else "OK"
    resumen = {
        "script": SCRIPT,
        "fecha_datos": FECHA_DATOS,
        "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
        "estado": estado,
        "errores": errores_pdf,
        "palabras": {a: {"palabras": n, "tope": TOPES[a]} for a, n in palabras.items()},
        "regla_de_palabras": "texto visible sin los encabezados H2 y H3 del apartado; palabra = trozo entre espacios "
                             "con una letra o una cifra; el resumen cuenta el título y el subtítulo",
        "paginas": {"total": len(paginas), "anexo_empieza_en": anexo},
        "huellas": {CONSULTAS: sha256(ruta_consultas), HTML: sha256(ruta_html), PDF: sha256(ruta_pdf)},
    }
    (raiz / RESUMEN).write_text(json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                encoding="utf-8")
    if errores_pdf:
        raise Parada("\nERROR: ".join(errores_pdf))
    print(f"OK: {HTML}, {PDF} ({len(paginas)} páginas, anexo en la {anexo}) y {RESUMEN}; palabras {palabras}")


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso")
    raiz = Path(argumentos.parse_args().raiz).resolve()
    print(f"Python: {sys.executable}")
    try:
        principal(raiz)
    except Parada as e:
        print(f"ERROR: {e}")
        sys.exit(1)
