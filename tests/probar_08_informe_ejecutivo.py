"""Prueba de scripts/08_informe_ejecutivo.py.

Parte 1, las funciones de parada del script, cada una con un caso que tiene que fallar y un control que no debe
disparar (el script se carga con importlib; su trabajo está dentro de if __name__ == "__main__"):
  - comprobar_cifras: una cifra del JSON que ya no se escribe como la escribe el texto (coste de 2024 + 1 dólar);
  - comprobar_topes: un apartado que pasa de su tope (límites con una palabra más);
  - sin_jerga: una palabra vetada en el texto para, y dentro de un nombre de fichero entre comillas invertidas no;
  - exigir: cada una de las seis frases con sentido, rota por separado;
  - comprobar_paginas: cuatro páginas, el anexo compartiendo página y el resumen en tres páginas.
Parte 2, de punta a punta en tests/tmp_informe_ejecutivo/, con una copia del JSON real de consultas:
  - con el JSON bueno, el script acaba bien, deja HTML, PDF y JSON, y el texto visible del HTML, con los espacios
    normalizados, es el del borrador (de «# Los fallos de los discos de datos» al final) sin las marcas de Markdown;
  - con el coste de 2024 cambiado, para con ERROR y no escribe el HTML.
Parte 3: el HTML real, si existe, tiene el mismo texto que el borrador, y su JSON dice OK y como mucho tres páginas.
Además, que el script no escribe ninguna comprobación con su resultado puesto.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "08_informe_ejecutivo.py"
TMP = CASO / "tests" / "tmp_informe_ejecutivo"
CONSULTAS = "informes/consultas-informe-ejecutivo.json"
BORRADOR = CASO / "config" / "metodo" / "borrador_informe_ejecutivo.md"
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


# ---------------------------------------------------------------------------------------------------------------
# 2. El texto del borrador y el texto visible del HTML
# ---------------------------------------------------------------------------------------------------------------
def texto_borrador():
    """El texto aprobado, sin las marcas de Markdown y con los espacios normalizados."""
    t = BORRADOR.read_text(encoding="utf-8")
    t = t[t.index("# Los fallos de los discos de datos"):]
    lineas = []
    for linea in t.splitlines():
        # La fila que separa la cabecera de la tabla no es texto
        if re.fullmatch(r"\s*\|[-:| ]+\|\s*", linea):
            continue
        # Las barras de la tabla separan celdas; la del subtítulo es texto y se queda
        if linea.lstrip().startswith("|"):
            linea = linea.replace("|", " ")
        # Marcas de título y de lista al principio de la línea
        linea = re.sub(r"^\s*#+\s+", "", linea)
        linea = re.sub(r"^\s*(-|\d+\.)\s+", "", linea)
        lineas.append(linea.replace("**", "").replace("`", ""))
    return " ".join(" ".join(lineas).split())


class Visible(HTMLParser):
    """Junta el texto que se ve del HTML: fuera de head, style y title."""

    def __init__(self):
        super().__init__()
        self.partes, self.oculto = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("head", "style", "title", "script"):
            self.oculto += 1
        # Cada bloque o celda separa palabras; la negrita y la letra de código van dentro de la frase
        if tag not in ("strong", "b", "code", "em"):
            self.partes.append(" ")

    def handle_endtag(self, tag):
        if tag in ("head", "style", "title", "script"):
            self.oculto -= 1
        if tag not in ("strong", "b", "code", "em"):
            self.partes.append(" ")

    def handle_data(self, data):
        if not self.oculto:
            self.partes.append(data)


def texto_html(ruta):
    """Texto visible de un HTML con los espacios normalizados."""
    p = Visible()
    p.feed(Path(ruta).read_text(encoding="utf-8"))
    return " ".join("".join(p.partes).split())


def primera_diferencia(a, b):
    """Trozo de los dos textos donde empiezan a ser distintos."""
    i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f"html «{a[max(0, i - 40):i + 40]}» / borrador «{b[max(0, i - 40):i + 40]}»"


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1: las funciones de parada
# ---------------------------------------------------------------------------------------------------------------
def cargar_script():
    """Carga el script como módulo sin ejecutar su trabajo."""
    spec = importlib.util.spec_from_file_location("informe_ejecutivo_08", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def parte_1(m, cifras):
    """Cada condición de parada con su caso que falla y su control."""
    # Cifras: control y una que ya no se escribe igual
    comprobar(m.comprobar_cifras(cifras) == [], "cifras: con el JSON real no para")
    malas = dict(cifras, coste_fallos_usd_2024=cifras["coste_fallos_usd_2024"] + 1)
    comprobar(any("832.698" in e for e in m.comprobar_cifras(malas)), "cifras: coste de 2024 + 1 dólar para")
    # Una cifra que falta en el JSON también para
    sin = {k: v for k, v in cifras.items() if k != "media_fallos_mes_2024"}
    comprobar(m.comprobar_cifras(sin) != [], "cifras: una que falta en el JSON para")

    # Topes: control y límites con una palabra más
    palabras = m.contar_palabras(m.BLOQUES, cifras)
    comprobar(m.comprobar_topes(palabras) == [], f"topes: el texto aprobado cabe ({palabras})")
    bloques = copy.deepcopy(m.BLOQUES)
    for b in bloques:
        if b[0] == "limites" and b[1] == "ul":
            b[2][0] = b[2][0] + " más"
    comprobar(any("limites" in e for e in m.comprobar_topes(m.contar_palabras(bloques, cifras))),
              "topes: límites con una palabra más para")

    # Palabras vetadas: en el texto para; dentro de un nombre de fichero no
    comprobar(m.sin_jerga(m.texto_plano(m.BLOQUES, cifras)) == [], "jerga: el texto aprobado no tiene ninguna")
    comprobar(m.sin_jerga("Cada avería cuesta dinero.") != [], "jerga: «avería» para")
    comprobar(m.sin_jerga("La " + "Flo" + "ta creció.") != [], "jerga: la palabra vetada con mayúscula para")
    comprobar(m.sin_jerga("Se lee `data/processed/fotos_riesgo.parquet` y ya.") == [],
              "jerga: dentro de comillas invertidas no para")
    comprobar(m.sin_jerga("La reconstrucción del tomo.") == [], "jerga: «reconstrucción» no es «construcción»")

    # Frases con sentido: control y cada una rota por separado
    comprobar(m.exigir(cifras) == [], "exigir: con el JSON real no para")
    roturas = {
        "aumentó de forma ininterrumpida": dict(cifras, coste_fallos_usd_2022=cifras["coste_fallos_usd_2021"] - 1),
        "3,3 veces el de 2020": dict(cifras, razon_coste_2024_2020=3.36),
        "2,5 veces": dict(cifras, razon_discos_ultimo_primero=2.46),
        "creció en todos los trimestres": dict(cifras, subidas_trimestre=20),
        "máximo del 1,7 % en 2023": dict(cifras, tasa_anual_pct_2022=1.8),
        "frente al 0,9 % de 2020": dict(cifras, tasa_anual_pct_2020=1.7),
    }
    for frase, c in roturas.items():
        comprobar(any(frase in e for e in m.exigir(c)), f"exigir: «{frase}» rota para")

    # Páginas: control y tres formas de romperlo
    bien = ["Los fallos ... Resumen ejecutivo", "Recomendaciones ...", "Anexo: trabajo realizado ..."]
    comprobar(m.comprobar_paginas(bien) == [], "páginas: tres, con el anexo solo en la tercera, no para")
    comprobar(m.comprobar_paginas(bien + ["más anexo"]) != [], "páginas: cuatro páginas para")
    comprobar(m.comprobar_paginas(["Los fallos ...", "Recomendaciones ... Anexo: trabajo realizado ..."]) != [],
              "páginas: el anexo en la página de las recomendaciones para")
    comprobar(m.comprobar_paginas(["Los fallos", "más", "Recomendaciones", "Anexo: trabajo realizado"]) != [],
              "páginas: lo anterior al anexo en tres páginas para")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 2: de punta a punta en la carpeta temporal
# ---------------------------------------------------------------------------------------------------------------
def montar(datos):
    """Carpeta temporal con informes/ y el JSON de consultas dado."""
    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "informes").mkdir(parents=True)
    (TMP / CONSULTAS).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def ejecutar():
    """Ejecuta el script sobre la carpeta temporal con -W error."""
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)], capture_output=True,
                       text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=300)
    return r.returncode, r.stdout + r.stderr


def parte_2(datos):
    """Con el JSON bueno, informe completo y texto igual al borrador; con uno malo, ERROR y sin HTML."""
    montar(datos)
    codigo, salida = ejecutar()
    comprobar(codigo == 0, f"punta a punta: el script acaba bien ({salida[-800:]})")
    html = TMP / "informes" / "informe_ejecutivo.html"
    for nombre in ("informe_ejecutivo.html", "informe_ejecutivo.pdf", "informe_ejecutivo.json"):
        comprobar((TMP / "informes" / nombre).exists(), f"punta a punta: deja {nombre}")
    if html.exists():
        a, b = texto_html(html), texto_borrador()
        comprobar(a == b, "punta a punta: texto visible del HTML = borrador sin marcas"
                  + ("" if a == b else f" ({primera_diferencia(a, b)})"))

    malos = copy.deepcopy(datos)
    for c in malos["cifras"]:
        if c["nombre"] == "coste_fallos_usd_2024":
            c["valor"] += 1000
    montar(malos)
    codigo, salida = ejecutar()
    comprobar(codigo != 0 and "ERROR" in salida and not (TMP / "informes" / "informe_ejecutivo.html").exists(),
              "punta a punta: coste de 2024 cambiado para con ERROR y no escribe el HTML")


# ---------------------------------------------------------------------------------------------------------------
# 5. Parte 3: lo que deja el script en el caso
# ---------------------------------------------------------------------------------------------------------------
def parte_3():
    """El HTML real con el texto del borrador y su JSON en OK, con tres páginas como mucho."""
    html = CASO / "informes" / "informe_ejecutivo.html"
    resumen = CASO / "informes" / "informe_ejecutivo.json"
    comprobar(html.exists() and resumen.exists(), "real: existen el HTML y el JSON del informe")
    if not (html.exists() and resumen.exists()):
        return
    a, b = texto_html(html), texto_borrador()
    comprobar(a == b, "real: texto visible del HTML = borrador sin marcas"
              + ("" if a == b else f" ({primera_diferencia(a, b)})"))
    r = json.loads(resumen.read_text(encoding="utf-8"))
    comprobar(r.get("estado") == "OK", "real: el JSON del informe dice OK")
    comprobar(r.get("paginas", {}).get("total", 99) <= 3, "real: como mucho tres páginas")


# ---------------------------------------------------------------------------------------------------------------
# 6. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        if not SCRIPT.exists():
            comprobar(False, "existe scripts/08_informe_ejecutivo.py")
        else:
            fuente = SCRIPT.read_text(encoding="utf-8")
            # el responsable del caso, 17/11: la palabra vetada para el conjunto de discos no sale en ningún texto del repositorio
            #. Se escribe partida para que esta prueba tampoco la lleve.
            comprobar(("flo" + "ta") not in fuente.lower(), "el script no lleva la palabra vetada")
            comprobar(not re.search(r"[\"'](cumple|coincide|estado)[\"']\s*:\s*(True|\"OK\")", fuente),
                      "el script no escribe ninguna comprobación con su resultado puesto")
            datos = json.loads((CASO / CONSULTAS).read_text(encoding="utf-8"))
            m = cargar_script()
            parte_1(m, m.cargar_cifras(datos))
            parte_2(datos)
        parte_3()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\nTodos los casos pasan")
    sys.exit(1 if FALLOS else 0)
