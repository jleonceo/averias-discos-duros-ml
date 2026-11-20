"""Informe final del caso 68 para la dirección de operaciones de los centros de datos: un HTML por resultados y el CSV
de sus gráficos.

Lee (y no cambia) cuatro JSON de informes/, que tienen que existir, traer la misma fecha de datos y ser más nuevos que
el script que los crea:
- indicadores__discos_modelos_edad.json (scripts/09_...): los discos, la edad y la supervivencia;
- indicadores__coste_prevision.json (scripts/10_...): el coste por terabyte y año y la previsión por trimestre;
- indicadores__centros_avisos_tomos.json (scripts/11_...): los centros, los avisos y los tomos;
- modelado.json (scripts/15_modelado.py): el modelo de riesgo y su validación;
- consultas-informe-ejecutivo.json (scripts/07_...): lo que costaron los fallos de 2024.
Y dos más de la prueba final, con la fecha del año guardado (30/06/2026) en lugar de la del análisis:
- prueba_final.json (scripts/19_...): la lista de riesgo frente a la regla en el año guardado;
- prueba_final_prevision.json (scripts/20_...): la previsión de repuestos en el año guardado;
- punto_ciego.json (scripts/22_punto_ciego.py): la parte de los fallos a 30 días cuya foto mensual no avisa, medida
  como la ve el modelo (auditor antes de entregar, 20/11/2026, una nota del caso).
Y la medida del modelo en uso en el año guardado, de modelos/reentrenos/2026-11-19/reentreno.json, con la huella de
modelos/en_uso/ (el año guardado se usó para elegirlo, y el anexo lo dice).

Deja informes/informe_final.html e informes/informe_final_graficos.csv.

No calcula ninguna cifra: las lee de los JSON y las escribe a la española; solo hace medias de las cifras por mes que el
JSON ya trae. Los textos son los de config/metodo/borrador_informe_final.md, versión 3 (19/11/2026, con la prueba final): la de
la versión 1 corregida con la revisión de un auditor de reporting y la de un lector simulado de la dirección. Cada frase
que nombra un sentido lleva delante un exigir() que para si los datos ya no la sostienen. No importa ningún script del
caso: solo las piezas comunes de assets/ (informe.py y graficos.py), que no ejecutan nada al importarse.

Uso, desde cualquier carpeta:
    python -W error scripts/17_informe_final.py
"""

# csv escribe las cifras de los gráficos
import csv
# html limpia el texto visible para las guardias
import html
# json lee las entradas
import json
# re busca la jerga y las palabras vetadas
import re
# sys añade assets/ a la ruta de importación y comprueba el intérprete
import sys
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

# =====================================================================================================================
# CONFIGURACIÓN
# =====================================================================================================================

# Carpeta del caso, calculada desde el propio script para que funcione lo lance quien lo lance
RAIZ = Path(__file__).resolve().parents[1]
# Las piezas comunes se usan desde assets/, sin copiarlas
sys.path.insert(0, str(RAIZ / "assets"))

# Piezas comunes: el informe y los gráficos
from informe import Informe  # noqa: E402
from graficos import (numero, barras_ordenadas, barras_con_intervalo, columnas_tiempo,  # noqa: E402
                      linea_tiempo)

# Intérprete del caso
# El entorno del caso, el que crea environment.yml: los scripts se lanzan dentro de él
ENTORNO = "68_averias_discos_duros"
# Carpeta de los informes y salidas
INFORMES = RAIZ / "informes"
SALIDA_HTML = INFORMES / "informe_final.html"
SALIDA_CSV = INFORMES / "informe_final_graficos.csv"
# Los JSON que lee el informe; todos con la misma fecha de datos
FECHA_DATOS = "2025-06-30"
EDAD = "indicadores__discos_modelos_edad.json"
COSTE = "indicadores__coste_prevision.json"
CENTROS = "indicadores__centros_avisos_tomos.json"
MODELO = "modelado.json"
EJECUTIVO = "consultas-informe-ejecutivo.json"
ENTRADAS = [EDAD, COSTE, CENTROS, MODELO, EJECUTIVO]
# Los JSON de la prueba final, con la fecha del año guardado
FECHA_RESERVA = "2026-06-30"
FINAL = "prueba_final.json"
PREVISION_FINAL = "prueba_final_prevision.json"
PUNTO_CIEGO = "punto_ciego.json"
ENTRADAS_RESERVA = [FINAL, PREVISION_FINAL, PUNTO_CIEGO]
# La medida del modelo en uso en el año guardado y las dos fichas con su huella
REENTRENO = RAIZ / "modelos" / "reentrenos" / "2026-11-19" / "reentreno.json"
FICHA_REENTRENO = RAIZ / "modelos" / "reentrenos" / "2026-11-19" / "modelo_riesgo_versiones.json"
FICHA_EN_USO = RAIZ / "modelos" / "en_uso" / "modelo_riesgo_versiones.json"
# Centros que se comparan en la página 5: los que tienen conclusión
CENTROS_CON_CONCLUSION = ["ams5", "iad1", "phx1", "sac0", "sac2"]
# Tamaños de lista de la página 8
LISTAS = ["20", "100", "500", "1000"]

# Título del informe y línea del lector (versión A del borrador)
TITULO = "Coste por terabyte y riesgo de fallo de los discos de Backblaze"
LECTOR = ("Para la dirección de operaciones de los centros de datos. Discos de datos de Backblaze, de enero de 2020 a "
          "junio de 2025.")
# Definiciones del caso, en el anexo (revisión externa del 19/11/2026: en la página 2 frenaban la lectura)
DEFINICIONES_CASO = [
    ["Backblaze", "Proveedor estadounidense de almacenamiento en la nube. Aloja la información de sus clientes en "
                  "discos duros propios, repartidos en seis centros de datos."],
    ["Fallo de un disco", "El disco deja de funcionar o Backblaze lo retira antes por signos de degradación."],
    ["Aviso SMART", "SMART es el sistema con el que cada disco anota sus propios errores en contadores internos. "
                    "Un ejemplo son los sectores que ya no se pueden leer. El disco avisa cuando alguno de sus cinco "
                    "contadores de avería pasa de cero."],
    ["Tomo", "Conjunto de 20 discos que almacenan de forma repartida los mismos ficheros. Cada fichero se divide en 20 "
             "fragmentos, uno por disco. Entre 3 y 5 de ellos son de redundancia."],
    ["Pérdida de datos", "Ocurre cuando fallan a la vez más discos de un tomo de los que cubre su redundancia. Sus "
                         "ficheros ya no se pueden reconstruir."],
    ["Redundancia", "Fragmentos adicionales que almacena un tomo para reconstruir la información de los discos que fallan. Se da por "
                    "hecho que son 3 discos hasta 8 TB, 4 entre 10 y 14 TB y 5 desde 16 TB."]]
# Definiciones de la lista de riesgo, en la página de los cálculos del anexo
DEFINICIONES_LISTA = [
    ["Modelo de riesgo", "Ordena cada mes los discos por su riesgo de fallar en 30 días. Su puntuación sirve para "
                         "ordenar; no es una probabilidad exacta."],
    ["Lista de riesgo", "Los discos con más riesgo según el modelo. Un técnico decide qué hacer con cada uno."],
    # Auditor del 20/11/2026: la definición anterior («la cifra verdadera está dentro con un 95 % de seguridad») es
    # incorrecta
    ["Intervalo de confianza", "Margen que, al repetir la medida muchas veces, contendría la cifra verdadera 95 de "
                               "cada 100."]]
# Nombre de la regla, siempre entero (El responsable del caso, 19/11/2026: «la regla actual» no lo entiende quien lo lee)
REGLA = "regla de los cinco avisos SMART"
# Fuentes en palabras del lector (F1)
FUENTE_TODO = "registro diario de los discos de Backblaze, enero de 2020 a junio de 2025"
FUENTE_SITIO = "registro diario de los discos de Backblaze, julio de 2023 a junio de 2025"
FUENTE_VALIDACION = "estado de los discos de Backblaze el primer día de cada mes, julio de 2024 a junio de 2025"
# Junio de 2026 no se mide: sus 30 días siguientes pasan del final de los datos
FUENTE_FINAL = "estado de los discos de Backblaze el primer día de cada mes, julio de 2025 a mayo de 2026"

# Jerga que no puede salir fuera del anexo: nombres internos, de columna y de fichero
JERGA = [r"\bparidad", r"\bvaults?\b", r"\bfoto\b", r"\bpliegue", r"\bbloque\b", r"\bφ\b", r"\bphi\b", r"\bminicubo", r"\bwape\b", r"\bcanario",
         r"\b[a-z0-9]+_[a-z0-9_]+\b", r"\.(?:json|csv|py|parquet|md|html)\b", r"\bCP-\d", r"\bB\d\b"]
# Palabras vetadas en todo el informe: las de la hoja de vocabulario del lector y las que corrigió el responsable del caso el 19/11
PROHIBIDAS = [r"\bflota\b", r"\bparque\b", r"\bunidades\b", r"regla actual", r"gastar menos", r"\bbajar el coste",
              r"\bimpagad", r"\bcontadores,"]


# =====================================================================================================================
# AYUDAS
# =====================================================================================================================

def exigir(condicion, frase):
    """Para si los datos ya no sostienen la frase que se va a escribir."""
    # Una frase falsa no se escribe
    if not condicion:
        raise ValueError(f"exigir: los datos ya no sostienen «{frase}»")


def leer_entradas(carpeta):
    """Lee los JSON de entrada, en UTF-8, y los devuelve por nombre."""
    # Cada uno tiene que existir
    faltan = [n for n in ENTRADAS + ENTRADAS_RESERVA if not (Path(carpeta) / n).is_file()]
    if faltan:
        raise ValueError(f"faltan entradas en {carpeta}: {faltan}")
    return {n: json.loads((Path(carpeta) / n).read_text(encoding="utf-8")) for n in ENTRADAS + ENTRADAS_RESERVA}


def comprobar_fechas(entradas):
    """Para si algún JSON no trae su fecha de datos (programacion-del-caso): la del análisis o, en los de la
    prueba final, la del año guardado."""
    esperada = {n: FECHA_RESERVA if n in ENTRADAS_RESERVA else FECHA_DATOS for n in entradas}
    distintas = {n: d.get("fecha_datos") for n, d in entradas.items() if d.get("fecha_datos") != esperada[n]}
    if distintas:
        raise ValueError(f"fecha_datos distinta de la esperada ({FECHA_DATOS}; {FECHA_RESERVA} en la prueba final) "
                         f"o ausente: {distintas}")


def comprobar_orden(entradas):
    """Para si algún JSON es más viejo que el script que lo crea."""
    viejos = [n for n, d in entradas.items()
              if (INFORMES / n).stat().st_mtime < (RAIZ / d["script"]).stat().st_mtime]
    if viejos:
        raise ValueError(f"orden: estos JSON son más viejos que el script que los crea; relánzalo: {viejos}")


def pregunta(datos, ident):
    """La pregunta con ese id dentro de un JSON de indicadores."""
    encontradas = [p for p in datos["preguntas"] if p["id"] == ident]
    exigir(len(encontradas) == 1, f"el JSON trae la pregunta {ident}")
    return encontradas[0]


def dolares(x):
    """Dólares sin decimales: 2044860,17 -> «2.044.860 $»."""
    return numero(x, 0) + " $"


def pct(x, decimales=2):
    """Un porcentaje ya en tanto por cien: 2,5835 -> «2,58 %»."""
    return numero(x, decimales) + " %"


def media(valores):
    """Media de una lista de cifras por mes que ya trae el JSON."""
    return sum(valores) / len(valores)


def apuntar(filas, pagina, grafico, grupo, medida, cifra, unidad):
    """Apunta una cifra de un gráfico para el CSV (F3)."""
    filas.append({"pagina": pagina, "grafico": grafico, "grupo": grupo, "medida": medida, "cifra": cifra,
                  "unidad": unidad})


def escribir_csv(ruta, filas):
    """CSV de las cifras de los gráficos: punto y coma, coma decimal y UTF-8 con marca (patrón §6)."""
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(["pagina", "grafico", "grupo", "medida", "cifra", "unidad"])
        # Cada cifra con coma decimal, hasta cuatro decimales y sin ceros de más
        for fila in filas:
            cifra = f"{float(fila['cifra']):.4f}".rstrip("0").rstrip(".").replace(".", ",")
            escritor.writerow([fila["pagina"], fila["grafico"], fila["grupo"], fila["medida"], cifra, fila["unidad"]])


# =====================================================================================================================
# GUARDIAS
# =====================================================================================================================

def _visible(texto_html):
    """Texto visible de un HTML, sin estilos, scripts ni comentarios."""
    limpio = re.sub(r"<(script|style)\b.*?</\1>", " ", texto_html, flags=re.S)
    return re.sub(r"<!--.*?-->", " ", limpio, flags=re.S)


def sin_jerga(texto_html, excluir):
    """Para si el texto visible fuera del anexo lleva jerga. `excluir`: ids del anexo."""
    encontrados = []
    # Cada página, por su id; el anexo queda fuera
    for ident, cuerpo in re.findall(r'<section id="([^"]+)"[^>]*>(.*?)</section>', _visible(texto_html), flags=re.S):
        if ident in excluir:
            continue
        visible = html.unescape(re.sub(r"<[^>]+>", " ", cuerpo))
        for patron in JERGA:
            encontrados += [f"{ident}: «{m.group(0)}»" for m in re.finditer(patron, visible, flags=re.I)]
    if encontrados:
        raise ValueError("jerga fuera del anexo: " + "; ".join(sorted(set(encontrados))))


def sin_prohibidas(texto_html):
    """Para si cualquier página, anexo incluido, lleva una palabra o una frase vetada."""
    visible = html.unescape(re.sub(r"<[^>]+>", " ", _visible(texto_html)))
    encontrados = [m.group(0) for p in PROHIBIDAS for m in re.finditer(p, visible, flags=re.I)]
    if encontrados:
        raise ValueError("palabra o frase vetada en el informe: " + "; ".join(sorted(set(encontrados))))


def titulos_claros(titulos):
    """Para si un título va partido por una coma o por dos puntos (método de redacción, «No escribas»)."""
    malos = [f"«{t}»" for t in titulos if "," in t or ":" in t]
    if malos:
        raise ValueError("título partido por una coma o por dos puntos: " + "; ".join(malos))


# =====================================================================================================================
# CIFRAS
# =====================================================================================================================

def leer_cifras(entradas):
    """Saca de los JSON las cifras que usan las páginas y comprueba cada frase que nombra un sentido."""
    c = {}
    b1 = pregunta(entradas[EDAD], "B1")["tablas"]
    b2 = pregunta(entradas[EDAD], "B2")["tablas"]
    b3 = pregunta(entradas[EDAD], "B3")["tablas"]
    b4 = pregunta(entradas[COSTE], "B4")["tablas"]
    b9 = pregunta(entradas[COSTE], "B9")["tablas"]
    b5 = pregunta(entradas[CENTROS], "B5")["tablas"]
    b6 = pregunta(entradas[CENTROS], "B6")["tablas"]
    b7 = pregunta(entradas[CENTROS], "B7")["tablas"]
    mod = entradas[MODELO]

    # Página 2: los discos, los fallos y su coste en 2024
    serie = {r["mes"]: r["discos"] for r in b1["serie_mensual"]}
    c["discos_inicio"], c["discos_fin"] = serie["2020-01-01"], serie["2025-06-01"]
    c["fallos"] = b1["cuadre_discos"]["fallos_de_la_serie"]
    exigir(c["discos_fin"] > 300000, "más de 300.000 discos")
    coste = [x for x in entradas[EJECUTIVO]["cifras"] if x["nombre"] == "coste_fallos_usd_2024"]
    exigir(len(coste) == 1 and coste[0]["periodo"] == "año 2024", "el coste de los fallos de 2024 está en el JSON")
    c["coste_2024"] = coste[0]["valor"]
    # Lo mismo si la garantía pagara los discos que fallan dentro de ella (reglas, coste de un fallo; auditor del
    # 19/11/2026: es la segunda cifra en dólares y no estaba en el resumen)
    cifras_ej = {x["nombre"]: x for x in entradas[EJECUTIVO]["cifras"]}
    exigir(cifras_ej["coste_fallos_garantia_usd_2024"]["periodo"] == "año 2024", "el coste con garantía es de 2024")
    c["coste_2024_garantia"] = cifras_ej["coste_fallos_garantia_usd_2024"]["valor"]
    exigir(c["coste_2024_garantia"] < c["coste_2024"], "con garantía los fallos cuestan menos")

    # Página 3: dentro de cada grupo de compra, el más barato es el que falla menos
    resumen = b4["resumen_ranking"]
    # Precio de compra y tasa de cada modelo, para comprobar que dentro de un grupo el precio cambia menos que la tasa.
    # Error del 19/11/2026: la página decía que dentro de un grupo el precio era el mismo, y solo lo es en uno
    # de los siete grupos (los 14 TB de 2020); en los demás difiere hasta un 13 %
    precio = {r["model"]: r["precio_usd"] for r in b4["ranking"]}
    grupos = [g for g in resumen["grupos_compra"]["grupos"] if len(g["modelos"]) >= 2]
    exigir(len(grupos) == resumen["grupos_compra"]["grupos_con_dos_o_mas"],
           "los grupos con dos modelos o más son los del JSON")
    c["grupos_total"] = resumen["grupos_compra"]["grupos_con_puesto"]
    c["grupos"] = []
    for g in grupos:
        orden = sorted(g["modelos"], key=lambda m: m["puesto"])
        exigir(all(orden[0]["coste_tb_ano"] < m["coste_tb_ano"] for m in orden[1:]),
               "el primero de cada grupo es el más barato")
        exigir(all(orden[0]["tasa"] < m["tasa"] for m in orden[1:]),
               "dentro de cada grupo de compra el más barato es el que falla menos")
        precios = [precio[m["model"]] for m in orden]
        tasas = [m["tasa"] for m in orden]
        exigir(max(precios) / min(precios) < max(tasas) / min(tasas),
               "dentro de cada grupo de compra el precio cambia menos que la tasa de fallo")
        c["grupos"].append((g, orden))
    c["mediana_fallos"] = resumen["mediana_parte_fallos_pct"]
    exigir(c["mediana_fallos"] < 10, "los fallos pesan poco en el coste")
    c["modelos_con_puesto"] = resumen["con_puesto"]
    # El coste por terabyte y año de cada modelo es precio más fallos, así que la mediana de la parte del precio es 100
    # menos la de los fallos; con un número impar de modelos, la mediana es un modelo concreto y la resta es exacta
    exigir(c["modelos_con_puesto"] % 2 == 1, "la mediana de la parte del precio es 100 menos la de los fallos")
    c["parte_precio"] = 100 - c["mediana_fallos"]
    c["inferidos"] = resumen["primeros_diez_inferidos"]
    sens = {s["factor"]: s for s in b4["sensibilidad_precio"]}
    c["sens_baja"], c["sens_sube"] = sens[0.8]["siguen"], sens[1.2]["siguen"]
    exigir(sens[0.8]["de"] == 10 and sens[1.2]["de"] == 10, "la prueba del precio mira los 10 más baratos")
    exigir(sens[0.8]["siguen"] == 10, "con precios un 20 % más bajos no cambia ninguno de los 10 más baratos")
    st14 = [r for r in b4["ranking"] if r["model"] == "ST14000NM0138"][0]
    c["st14"] = (st14["coste_tb_ano"], st14["coste_tb_ano_garantia"])
    # Con garantía el ST14000NM0138 pasaría a ser el más barato de su grupo (auditor del 19/11/2026)
    grupo14 = [o for g, o in c["grupos"] if any(m["model"] == "ST14000NM0138" for m in o)]
    exigir(len(grupo14) == 1 and grupo14[0][0]["model"] != "ST14000NM0138"
           and st14["coste_tb_ano_garantia"] < grupo14[0][0]["coste_tb_ano"],
           "con garantía el ST14000NM0138 sería el más barato de su grupo")
    c["st14_grupo"] = (st14["capacidad_tb"], st14["ano_compra"])

    # Página 4: los repuestos; repetir el trimestre anterior prevé mejor
    err = b9["error"]
    exigir(not err["gana_la_cuenta"] and err["cuenta"]["wape"] > err["referencia"]["wape"],
           "repetir el trimestre anterior prevé mejor")
    exigir(err["cuenta"]["sesgo"] > 0 and err["referencia"]["sesgo"] < 0,
           "la previsión prevé de más y repetir el trimestre anterior se queda corto")
    c["error"] = err
    c["serie9"] = b9["serie_lineas"]
    exigir(round(sum(r["previsto"] for r in c["serie9"])) == round(err["previsto"])
           and sum(r["real"] for r in c["serie9"]) == err["real"], "los totales previstos y reales son los de la serie")
    peor = max(c["serie9"], key=lambda r: abs(r["previsto"] - r["real"]))
    exigir(peor["trimestre"] == "2024T4", "el error más grande es el del cuarto trimestre de 2024")
    c["peor9"] = peor

    # Página 5: la tasa por edad, que sube de 1 a 5 años cumplidos, y la supervivencia
    edades = [r for r in b3["tasa_por_edad"]["todos"] if r["edad"] <= 8]
    c["edades"] = edades
    tasa = {r["edad"]: r for r in edades}
    exigir([e for e in range(9) if tasa[e]["sube"]] == [2, 3, 4, 5], "la tasa sube en los años 2, 3, 4 y 5")
    c["tasa0"], c["tasa5"] = tasa[0]["tasa"], tasa[5]["tasa"]
    c["sobreviven1"] = b3["supervivencia"]["todos"]["s_en"]["1"]
    c["sobreviven5"] = b3["supervivencia"]["todos"]["s_en"]["5"]
    c["viejos"] = b3["discos_8_o_mas"]
    exigir(c["viejos"]["pct"] < 5, "quedan pocos discos de 8 años o más")
    c["tasa_todos"] = b2["todos_los_discos"]["tasa"]

    # Página 6: los centros a igual mezcla
    centros = {r["centro"]: r for r in b5["centros"]}
    c["centros"] = [centros[k] for k in CENTROS_CON_CONCLUSION]
    c["sac2"], c["sac0"], c["yyz1"] = centros["sac2"], centros["sac0"], centros["yyz1"]
    exigir(centros["sac2"]["veredicto"] == "falla más por sí mismo", "sac2 falla más")
    exigir(centros["sac0"]["veredicto"] == "falla menos", "sac0 falla menos")
    exigir(all(centros[k]["veredicto"] == "no se distingue" for k in ("phx1", "ams5", "iad1")),
           "phx1, ams5 e iad1 no se distinguen")
    exigir(centros["yyz1"]["veredicto"] == "sin conclusión", "yyz1 no permite sacar conclusiones")
    c["sac2_mas"] = round((centros["sac2"]["razon"] - 1) * 100)
    exigir(c["sac2_mas"] == 10, "sac2 falla un 10 % más de lo esperado")
    c["sac2_rango"] = (round((centros["sac2"]["razon_desde"] - 1) * 100), round((centros["sac2"]["razon_hasta"] - 1) * 100))
    exigir(c["sac2_rango"][0] > 0, "el intervalo de sac2 queda entero por encima de lo esperado")
    temperatura = {r["centro"]: r["media"] for r in b5["temperatura"]["por_centro"]}
    exigir(max(temperatura, key=temperatura.get) == "sac2", "sac2 tiene la temperatura media más alta")
    c["temp_sac2"], c["temp_sac0"] = temperatura["sac2"], temperatura["sac0"]
    exigir(centros["sac0"]["tasa_bruta"] > centros["phx1"]["tasa_bruta"]
           and centros["sac0"]["razon"] < centros["phx1"]["razon"], "sac0 parecía peor que phx1 sin igualar")

    # Página 7: los tomos
    azar = [r for r in b7["azar"]["resultados"] if r["k"] == 2 and r["d"] == 30][0]
    c["tomos"] = azar
    exigir(azar["observados"] > azar["p95"], "los fallos de un tomo van más juntos que al azar")
    c["tomos_mas"] = round((azar["observados"] / azar["media"] - 1) * 100)
    exigir(5 <= c["tomos_mas"] <= 20, "los tomos con dos fallos son algo más que al azar")
    c["coinciden"], c["con_tomo"] = b7["fallos"]["coinciden"], b7["fallos"]["con_tomo"]
    c["paridad"] = b7["a_la_vez"]["llegan_a_paridad"]
    a_tres = [r for r in b7["a_la_vez"]["por_capacidad"] if r["a_la_vez"] == 3 and r["capacidad_tb"] <= 8]
    exigir(sum(r["fallos"] for r in a_tres) == c["paridad"] and max(b7["a_la_vez"]["reparto"], key=int) == "3",
           "al límite fueron tres discos a la vez en tomos de 8 TB y nunca más de tres")

    # Página 9: la lista de riesgo en la validación, la prueba anterior a la final
    val = mod["validacion"]
    meses_val = val["por_mes"]
    exigir(all(m["modelo_lista_100"] > m["regla_lista_100"] for m in meses_val),
           "en la prueba anterior el modelo encontró más fallos que la regla todos los meses")
    c["validacion_100"] = media([m["modelo_lista_100"] for m in meses_val])

    # Página 8: la lista de riesgo en la prueba final, con el año guardado (19/11/2026). Solo los meses que se miden:
    # el último no, porque sus 30 días siguientes pasan del final de los datos
    fin = entradas[FINAL]
    exigir(fin["modo"] == "--reserva" and fin["se_da_por_bueno"] and fin["frente_a"]["frente_a_la_regla"] == "supera",
           "la lista de riesgo supera a la regla en la prueba final")
    meses = [m for m in fin["por_mes"] if m["se_mide"]]
    exigir(len(meses) == fin["totales"]["meses"] and meses[0]["mes"][:7] == "2025-07"
           and meses[-1]["mes"][:7] == "2026-05", "la prueba final mide de julio de 2025 a mayo de 2026")
    c["listas"] = {n: (media([m[f"modelo_lista_{n}"] for m in meses]), media([m[f"regla_lista_{n}"] for m in meses]))
                   for n in LISTAS}
    c["meses"] = meses
    exigir(all(m["modelo_lista_100"] > m["regla_lista_100"] for m in meses),
           "en la prueba final el modelo encuentra más fallos que la regla todos los meses")
    exigir(fin["intervalo"]["bajo"] > 0, "la diferencia con la regla es mayor que cero")
    exigir(fin["intervalo"]["remuestreos"] == 1000, "el intervalo sale de 1.000 remuestreos")
    modelo100, regla100 = c["listas"]["100"]
    c["final_mas"] = round((modelo100 / regla100 - 1) * 100)
    exigir(0 < c["final_mas"] < 100, "la lista encuentra más fallos que la regla, pero no el doble")
    exigir(modelo100 < c["validacion_100"], "en la prueba final la lista encontró menos fallos que en la anterior")
    c["no_fallan"] = 1 - modelo100 / 100
    exigir(0.72 <= c["no_fallan"] <= 0.8, "unos tres de cada cuatro discos de la lista no fallan en 30 días")
    c["intervalo"] = fin["intervalo"]

    # Página 4: los repuestos en el año guardado; repetir el trimestre anterior vuelve a prever mejor
    pf = entradas[PREVISION_FINAL]
    exigir(pf["modo"] == "--reserva" and not pf["gana_la_cuenta"]
           and pf["total"]["wape_cuenta"] > pf["total"]["wape_referencia"],
           "en el año guardado repetir el trimestre anterior vuelve a prever mejor")
    c["error_final"] = pf["total"]

    # Página 9: el punto ciego (auditor antes de entregar, 20/11/2026). Antes daba el 25 % de fallos sin aviso el día
    # anterior (B6), que no es lo que ve el modelo: el modelo ve el estado del primer día del mes, y el punto ciego se
    # mide con esa foto
    ciego = entradas[PUNTO_CIEGO]
    exigir(ciego["estado"] == "OK" and all(ciego["validaciones"].values()),
           "el punto ciego está medido y cuadra con los fallos del modelo")
    c["punto_ciego"] = ciego["ano_guardado"]["parte"]
    exigir(0.25 <= c["punto_ciego"] <= 0.4, "uno de cada tres fallos del último año no avisaba el primer día del mes")
    # El modelo en uso, medido en el año guardado antes de aprobarlo
    reentreno = json.loads(REENTRENO.read_text(encoding="utf-8"))["comparacion_con_el_en_uso"]
    huellas = [json.loads(f.read_text(encoding="utf-8"))["huella"] for f in (FICHA_REENTRENO, FICHA_EN_USO)]
    exigir(huellas[0] == huellas[1], "el reentreno medido es el modelo en uso")
    exigir(abs(reentreno["en_uso"]["lista_100"] - modelo100) < 1e-9,
           "el reentreno se comparó con el modelo examinado en la prueba final")
    c["en_uso_100"] = reentreno["reentrenado"]["lista_100"]
    return c


def trimestre(t):
    """«2024T4» -> «T4 2024», como lo lee la dirección."""
    return f"T{t[-1]} {t[:4]}"


# =====================================================================================================================
# PÁGINAS
# =====================================================================================================================

def pagina_resumen(inf, c, filas):
    """Página 1: la recomendación con el dinero, sus cifras clave y los límites que pesan (D1, D2).

    Sin tabla de preguntas: el modelo de informe por resultados que aprobó el responsable del caso el 10/11 no la lleva, y con ella la
    página mide unos 873 px. La lista de control 08 y sus lectores (19/11/2026) pidieron: la acción en la primera
    frase, la garantía al lado del coste de los fallos, por qué los fallos pesan poco frente a lo que costaron y que el
    ahorro de la compra no se puede calcular.
    """
    m100, r100 = c["listas"]["100"]
    p = inf.pagina("Reducir costes depende más del precio de compra de los discos que de sus fallos", "resumen",
                   panel="Resumen")
    p.cifra_clave(pct(c["parte_precio"], 2), "Parte del coste por terabyte y año que corresponde al precio de compra",
                  f"Mediana de {c['modelos_con_puesto']} modelos de disco")
    p.cifra_clave(dolares(c["coste_2024"]), "Lo que costaron los fallos de discos en 2024",
                  f"{dolares(c['coste_2024_garantia'])} si la garantía pagara los discos")
    p.cifra_clave(numero(m100, 1), "Discos que fallan al mes de los 100 de la lista de riesgo",
                  f"Un {c['final_mas']} % más que con la {REGLA}, {numero(r100, 1)}")
    p.apartado("Análisis ejecutivo",
               "Para reducir costes, elige en cada compra el modelo con menor coste por terabyte y año. Los fallos "
               "suman mucho dinero porque hay muchos discos, pero en el coste de cada terabyte pesan poco frente al "
               "precio del disco.",
               "Dos límites condicionan estas cifras. El precio desde 2023 es estimado y no se puede calcular el ahorro "
               "en dólares, porque depende de los modelos y terabytes de cada compra. La lista de riesgo dice qué "
               "discos revisar, pero no cuánto ahorra.")
    p.apartado("Próximo paso", "Aprueba las cinco decisiones de la página 10. La primera es comprar en cada capacidad "
                               "el modelo de menor coste por terabyte y año. Después vienen la lista de riesgo, la "
                               "vigilancia por edad, la revisión del centro de datos sac2 y los repuestos.")


def esquema_tomo():
    """Esquema de un tomo de 20 discos con 3 de redundancia: con 3 fallos los datos se reconstruyen y con 4 se pierden.

    Es un dibujo fijo, sin cifras de los datos: los 20 discos y los 3 de redundancia son el ejemplo de Backblaze, y la
    redundancia supuesta por capacidad es la de las reglas de negocio.
    """
    # Medidas del dibujo: 20 cuadrados de 16 px con 4 px de hueco, empezando en x=150
    ancho, alto, x0, lado, paso = 560, 210, 150, 16, 20
    texto = 'font-family="Segoe UI, sans-serif" font-size="13"'
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}">']

    def fila(y, fallan, color_fallo, rotulo, resultado):
        """Una fila de 20 discos: los últimos `fallan`, del color del fallo; el rótulo a la izquierda y el
        resultado debajo."""
        partes.append(f'<text x="0" y="{y + 12}" {texto} fill="#0b0b0b">{rotulo}</text>')
        for i in range(20):
            relleno = color_fallo if i >= 20 - fallan else "#2a78d6"
            partes.append(f'<rect x="{x0 + i * paso}" y="{y}" width="{lado}" height="{lado}" fill="{relleno}"/>')
        partes.append(f'<text x="{x0}" y="{y + 36}" {texto} fill="#52514e">{resultado}</text>')

    # Las dos situaciones, una debajo de otra
    fila(20, 3, "#e1e0d9", "Fallan 3 a la vez", "Los datos se reconstruyen con los otros 17 discos")
    fila(90, 4, "#eb6834", "Fallan 4 a la vez", "Los datos del tomo se pierden")
    partes.append(f'<text x="0" y="{alto - 34}" {texto} fill="#52514e">Se supone una redundancia de 3 discos hasta '
                  f'8 TB,</text>')
    partes.append(f'<text x="0" y="{alto - 14}" {texto} fill="#52514e">de 4 de 10 a 14 TB y de 5 desde 16 TB.</text>')
    partes.append("</svg>")
    return "".join(partes)


def pagina_caso(inf, c, filas):
    """Página 2: el tamaño del problema y cómo se pierden datos en un tomo (revisión externa del 19/11/2026)."""
    p = inf.pagina("Varios fallos a la vez en un mismo grupo de 20 discos pueden hacer perder datos", "resultado",
                   panel="El caso")
    p.cifra_clave(numero(c["discos_fin"], 0), "Discos de datos el 01/06/2025, sin contar los de arranque",
                  f"El 01/01/2020 eran {numero(c['discos_inicio'], 0)}")
    p.cifra_clave(numero(c["fallos"], 0), "Fallos de discos de datos", "De enero de 2020 a junio de 2025")
    # El coste de 2024 ya está en el resumen; aquí, cuántas veces se llegó al límite de la redundancia, para que el
    # riesgo del esquema tenga su cifra (revisión externa del 19/11/2026)
    p.cifra_clave(numero(c["paridad"], 0), "Veces que un tomo llegó al límite de la redundancia",
                  "De julio de 2023 a junio de 2025. Nunca se superó")
    p.grafico(esquema_tomo(), "", "Ejemplo de un tomo de 20 discos con 3 de redundancia. Fuente: documentación "
                                  "técnica de Backblaze")
    p.apartado("Análisis ejecutivo",
               "Backblaze guarda los datos de sus clientes en discos propios, repartidos en seis centros de datos. Los "
               "discos se agrupan de 20 en 20 y cada grupo se llama tomo. Cada fichero se reparte entre los 20 discos "
               "de su tomo. Entre 3 y 5 de ellos guardan redundancia, que permite reconstruir los datos cuando falla "
               "un disco. Si fallan a la vez más discos de los que cubre la redundancia, los datos del tomo se pierden.")
    p.apartado("Próximo paso", "Aprueba primero la compra de discos y los repuestos (págs. 3 y 4). Después, la "
                               "vigilancia (págs. 5 a 8).")


def pagina_coste(inf, c, filas):
    """Página 3: qué modelo comprar dentro de cada capacidad y año de compra, con la tasa de fallo de cada modelo."""
    # Revisión externa del 19/11/2026: solo 7 de los 19 grupos tienen con qué comparar, y el título lo dice
    exigir(len(c["grupos"]) == 7, "son siete los grupos con dos modelos o más")
    p = inf.pagina("En los siete grupos con dos modelos o más el más barato por terabyte es el que menos falla",
                   "resultado", panel="Qué modelo comprar", columnas=False)
    tabla, terceros = [], []
    for g, orden in c["grupos"]:
        # Cifras como números, para que la tabla las alinee (TB2). Al lado va el modelo que le sigue; si el grupo tiene
        # más, el resto se dice debajo de la tabla, porque una celda con dos cifras no se alinea como número
        tabla.append([f"{numero(g['capacidad_tb'], 0)} TB, {g['ano_compra']}", orden[0]["model"],
                      orden[0]["coste_tb_ano"], orden[0]["tasa"], orden[1]["coste_tb_ano"], orden[1]["tasa"]])
        terceros += [f"en {numero(g['capacidad_tb'], 0)} TB de {g['ano_compra']} hay otro modelo más, a "
                     f"{numero(m['coste_tb_ano'], 2)} $ y {pct(m['tasa'])}" for m in orden[2:]]
    # Sin gráfico: la tabla de siete grupos no deja sitio en la pantalla (S3). La tasa va al lado del coste para que se
    # vea por qué gana el más barato (lector sin contexto del 19/11/2026)
    p.tabla(["Capacidad y año de compra", "Modelo más barato", "Dólares por TB y año", "Tasa de fallo, %",
             "Siguiente modelo, dólares", "Siguiente modelo, tasa %"],
            tabla, "; ".join(terceros + ["precios estimados desde 2023, " + FUENTE_TODO]),
            decimales=[0, 0, 2, 2, 2, 2], texto=False)
    p.apartado("Análisis ejecutivo",
               "Cada modelo se compara con los de su capacidad comprados el mismo año, porque cada año el terabyte "
               "sale más barato. Dentro de cada grupo los precios se parecen más que las tasas de fallo. En la mediana "
               f"de los {c['modelos_con_puesto']} modelos, los fallos son solo el {pct(c['mediana_fallos'])} del coste. "
               f"Solo {len(c['grupos'])} de los {c['grupos_total']} grupos tienen dos modelos o más.")
    p.apartado("Próximo paso", "Compra en cada capacidad el modelo de menor coste por terabyte y año. "
                               "Antes, confirma su precio si es de 2023 o posterior.")


def pagina_repuestos(inf, c, filas):
    """Página 4: los repuestos por trimestre; repetir el anterior prevé igual de bien que la cuenta por modelo y edad."""
    e = c["error"]
    p = inf.pagina("La previsión por modelo y edad no es más precisa que el trimestre anterior",
                   "resultado", panel="Los repuestos")
    p.cifra_clave(numero(e["previsto"], 0), "Fallos previstos por modelo y edad, de 2021 a junio de 2025",
                  f"Los reales fueron {numero(e['real'], 0)}")
    p.cifra_clave(pct(e["referencia"]["wape"] * 100, 1), "Error medio al prever con los fallos del trimestre anterior",
                  f"Con la previsión por modelo y edad, {pct(e['cuenta']['wape'] * 100, 1)}")
    # Dos líneas y no tres: las tres se cruzaban y no se leían (revisión externa del 19/11/2026). La previsión con el
    # trimestre anterior es la línea de los reales desplazada un trimestre, así que no hace falta dibujarla aparte; el
    # subtítulo lo dice. Los reales van primero, en el color principal
    periodos = [trimestre(r["trimestre"]) for r in c["serie9"]]
    series = {"Reales": [r["real"] for r in c["serie9"]], "Por modelo y edad": [r["previsto"] for r in c["serie9"]]}
    exigir(all(b["referencia"] == a["real"] for a, b in zip(c["serie9"], c["serie9"][1:])),
           "la previsión con el trimestre anterior es la línea de los reales desplazada un trimestre")
    for nombre, valores in series.items():
        for per, v in zip(periodos, valores):
            apuntar(filas, 4, "fallos por trimestre", f"{per}, {nombre.lower()}", "fallos", v, "fallos")
    # «T1 21» en el eje: con el año entero solo caben uno de cada tres trimestres y el eje salta de forma irregular
    cortos = [f"{x[:2]} {x[-2:]}" for x in periodos]
    svg = linea_tiempo(cortos, series, decimales=0, medida="fallos")
    p.grafico(svg, "", "Fallos por trimestre. La previsión con el trimestre anterior es la línea de los reales "
                       "desplazada un trimestre. Fuente: " + FUENTE_TODO)
    p.apartado("Análisis ejecutivo",
               "La previsión por modelo y edad sobrestima los fallos totales en un "
               f"{pct(e['cuenta']['sesgo'] * 100, 1)}. Los fallos del trimestre anterior los subestiman en un "
               f"{pct(-e['referencia']['sesgo'] * 100, 1)}, con un error medio algo menor. La mayor desviación se "
               f"produjo en el {trimestre(c['peor9']['trimestre'])}, con {numero(c['peor9']['previsto'], 0)} fallos "
               f"previstos frente a {numero(c['peor9']['real'], 0)} reales. En el último año, que se guardó para la "
               "prueba final, repetir el trimestre anterior volvió a prever mejor, con un error medio del "
               f"{pct(c['error_final']['wape_referencia'] * 100, 1)} frente al "
               f"{pct(c['error_final']['wape_cuenta'] * 100, 1)}. Como la previsión no mejora, basta con el "
               "método más sencillo.")
    p.apartado("Próximo paso", "Planifica los repuestos de cada trimestre con los fallos del trimestre previo. Añade "
                               "un margen de seguridad que cubra su error medio.")


def pagina_edad(inf, c, filas):
    """Página 5: la tasa de fallo por año de edad, con su intervalo."""
    p = inf.pagina("La tasa de fallo sube cada año de edad entre el primero y el quinto",
                   "resultado", panel="La edad")
    p.cifra_clave(pct(c["sobreviven5"] * 100, 1), "Discos que siguen funcionando a los 5 años",
                  f"Al año, {pct(c['sobreviven1'] * 100, 1)}")
    v = c["viejos"]
    p.cifra_clave(pct(v["pct"], 1), "Discos de 8 años o más",
                  f"{numero(v['discos_8_o_mas'], 0)} de {numero(v['discos_total'], 0)} el 01/04/2025")
    etiquetas = [f"{r['edad']} años" if r["edad"] != 1 else "1 año" for r in c["edades"]]
    for e, r in zip(etiquetas, c["edades"]):
        apuntar(filas, 5, "tasa por año de edad", e, "tasa anual de fallo", r["tasa"], "%")
    svg = barras_con_intervalo(etiquetas, [r["tasa"] for r in c["edades"]], [r["desde"] for r in c["edades"]],
                               [r["hasta"] for r in c["edades"]], referencia=c["tasa_todos"],
                               rotulo_referencia=f"Todos los discos, {pct(c['tasa_todos'])}", decimales=2,
                               unidad=" %", intervalo="intervalo de confianza del 95 %",
                               medida="tasa anual de fallo")
    p.grafico(svg, "", "Tasa anual de fallo por años cumplidos, en %. Fuente: " + FUENTE_TODO)
    p.apartado("Análisis ejecutivo",
               "La subida entre el primer y el quinto año cumplido es real: los intervalos de cada año no se tocan. "
               "Desde los 6 años la tasa deja de subir, pero solo mide los discos que han llegado a esa edad. Quedan "
               "tan pocos discos de 8 años que no se puede saber si su bajada es real.")
    p.apartado("Próximo paso", "Compara los modelos de disco siempre a la misma edad: uno joven parece fallar poco "
                               "solo por su edad. Vigila más los discos desde los 2 años cumplidos.")


def pagina_centros(inf, c, filas):
    """Página 6: los centros de datos a igual mezcla de modelos, edades y trimestres."""
    s2, s0 = c["sac2"], c["sac0"]
    p = inf.pagina(f"El centro de datos sac2 falla un {c['sac2_mas']} % más de lo esperado para sus modelos y edades",
                   "resultado", panel="Los centros de datos")
    p.cifra_clave(numero(s2["observados"], 0), "Fallos en sac2",
                  f"Con sus discos se esperaban {numero(s2['esperados'], 0)}")
    p.cifra_clave(numero(s0["observados"], 0), "Fallos en sac0",
                  f"Con sus discos se esperaban {numero(s0['esperados'], 0)}")
    etiquetas = [r["centro"] for r in c["centros"]]
    for r in c["centros"]:
        apuntar(filas, 6, "fallos frente a los esperados", r["centro"], "razón", r["razon"], "veces")
    svg = barras_con_intervalo(etiquetas, [r["razon"] for r in c["centros"]], [r["razon_desde"] for r in c["centros"]],
                               [r["razon_hasta"] for r in c["centros"]], referencia=1,
                               rotulo_referencia="1: falla lo esperado", decimales=2,
                               intervalo="intervalo de confianza del 95 %", destacar=["sac2"],
                               medida="veces lo esperado")
    p.grafico(svg, "", "Fallos de cada centro frente a los esperados si fallara como la media con sus mismos discos. "
                       "Fuente: " + FUENTE_SITIO)
    lo, hi = c["sac2_rango"]
    p.apartado("Análisis ejecutivo",
               f"Con un 95 % de confianza, sac2 falla entre un {lo} % y un {hi} % más de lo esperado. phx1, ams5 e "
               "iad1 fallan lo esperado para sus discos. sac0 falla algo menos. yyz1 solo tuvo "
               f"{numero(c['yyz1']['observados'], 0)} fallos, que no bastan para concluir. La temperatura media de los "
               f"discos de sac2 es de {numero(c['temp_sac2'], 1)} °C, frente a {numero(c['temp_sac0'], 1)} °C en sac0, "
               "pero eso no demuestra que sea la causa.")
    p.apartado("Próximo paso", "Revisa con el equipo de sac2 en qué se diferencia su operación. La temperatura de sus "
                               "discos es la primera pista.")


def pagina_tomos(inf, c, filas):
    """Página 7: los fallos de un mismo tomo frente al azar."""
    t = c["tomos"]
    p = inf.pagina(f"Hay un {c['tomos_mas']} % más grupos de 20 discos con dos fallos en 30 días de lo que daría el "
                   "azar", "resultado", panel="Los tomos")
    p.cifra_clave(numero(t["observados"], 0), "Tomos con dos fallos o más en 30 días",
                  f"Al azar, {numero(t['media'], 0)} de media")
    p.cifra_clave(numero(c["coinciden"], 0), "Fallos que llegaron antes de reconstruir el disco anterior del tomo",
                  f"De {numero(c['con_tomo'], 0)} fallos con tomo conocido")
    p.cifra_clave(numero(c["paridad"], 0), "Veces que se llegó al límite de la redundancia",
                  "Tres discos caídos a la vez con tres de redundancia. Nunca se superó")
    etiquetas = ["Lo que pasó", "Media al azar", "Máximo que daría el azar"]
    valores = [t["observados"], t["media"], t["p95"]]
    for e, v in zip(etiquetas, valores):
        apuntar(filas, 7, "tomos con dos fallos o más en 30 días", e, "tomos", v, "tomos")
    svg = barras_ordenadas(etiquetas, valores, decimales=0, ordenar=False, medida="tomos", destacar=["Lo que pasó"])
    p.grafico(svg, "", "Tomos con dos fallos o más en 30 días. Máximo que daría el azar: el que no se supera en 19 de "
                       "cada 20 simulaciones. Fuente: " + FUENTE_SITIO)
    p.apartado("Análisis ejecutivo",
               "Los datos no dicen si la causa es que los discos de un tomo son del mismo lote. Tampoco se sabe cuánto "
               "costaría perder datos.")
    p.apartado("Próximo paso", "Cuando falle un disco, avisa a los técnicos para que revisen su tomo mientras se "
                               "reconstruyen los datos.")


def pagina_lista(inf, c, filas):
    """Página 8: la lista de riesgo frente a la regla de los cinco avisos SMART, en la prueba final (19/11/2026)."""
    p = inf.pagina(f"La lista de riesgo encuentra un {c['final_mas']} % más de fallos que la {REGLA}", "resultado",
                   panel="La lista de riesgo", columnas=False)
    # Cifras como números, para que la tabla las alinee a la derecha (TB2), con dos decimales para que cuadren con la
    # diferencia de la frase (auditor del 19/11/2026: 32,2 menos 15,8 no daba 16,33)
    tabla = [[int(n), c["listas"][n][0], c["listas"][n][1]] for n in LISTAS]
    # Sin gráfico: tabla y texto llenan la pantalla (S3); los once meses van al CSV para el cuadro de mando
    for m in c["meses"]:
        apuntar(filas, 8, "fallos en la lista de 100", f"{m['mes'][:7]}, lista de riesgo", "fallos",
                m["modelo_lista_100"], "fallos")
        apuntar(filas, 8, "fallos en la lista de 100", f"{m['mes'][:7]}, regla", "fallos", m["regla_lista_100"],
                "fallos")
    p.tabla(["Discos señalados al mes", "Fallos al mes en la lista de riesgo", f"Fallos al mes con la {REGLA}"],
            tabla, f"media de los {len(c['meses'])} meses de la prueba final, " + FUENTE_FINAL, decimales=[0, 2, 2],
            texto=False)
    iv = c["intervalo"]
    p.apartado("Análisis ejecutivo",
               "En la prueba final, con un año que no se usó para construirla, la lista encontró más fallos que la "
               f"regla todos los meses: {numero(iv['media'], 2)} más al mes, con un intervalo de confianza de "
               f"{numero(iv['bajo'], 2)} a {numero(iv['alto'], 2)}.",
               "Unos tres de cada cuatro discos de la lista no fallan en 30 días.")
    p.apartado("Próximo paso", "Revisa cada mes los discos de la lista de riesgo. Decide cuántos según las horas que "
                               "puedan dedicar los técnicos.")


def pagina_limites(inf, c, filas):
    """Página 9: los límites que cambian una decisión."""
    cap, ano = c["st14_grupo"]
    # Seis desde la prueba final (19/11/2026): el límite de «Todas», que aún no se había medido el último año, sale; lo
    # que dio esa prueba va en la fila de la lista de riesgo, porque una séptima fila con ese rótulo no cabía (S3)
    filas_limites = [
        ["Qué modelo comprar", f"Desde 2023 el precio es estimado, en {c['inferidos']} de los 10 modelos más baratos. "
                               "Con precios un 20 % más bajos no cambia ninguno; con un 20 % más altos cambian "
                               f"{10 - c['sens_sube']}. El precio se reparte en 6 años de vida supuesta"],
        ["Qué modelo comprar", "No consta si Backblaze reclama la garantía. Si la reclamara, el ST14000NM0138 bajaría "
                               f"de {numero(c['st14'][0], 2)} $ a {numero(c['st14'][1], 2)} $ por TB y año y sería el "
                               f"más barato de los {numero(cap, 0)} TB de {ano}"],
        ["Usar la lista de riesgo", f"En el último año, el {pct(c['punto_ciego'] * 100, 0)} de los fallos no avisaba "
                                    "el primer día del mes. Con 100 discos bajó de "
                                    f"{numero(c['validacion_100'], 1)} a {numero(c['listas']['100'][0], 1)} fallos al "
                                    "mes"],
        ["Revisar sac2", "Solo hay dos años con el centro de cada disco. Los datos no dicen la causa"],
        ["Vigilar por edad", "Quedan pocos discos de 8 años o más para saber si su tasa baja"],
        ["Comprar repuestos", "Repetir el trimestre anterior tiene un error medio del "
                              f"{pct(c['error']['referencia']['wape'] * 100, 0)}"]]
    exigir(len(filas_limites) == 6, "son seis límites")
    p = inf.pagina("Seis límites pueden cambiar estas decisiones", "limites", panel="Límites")
    p.tabla(["Decisión a la que afecta", "Límite"], filas_limites,
            fuente="reglas de negocio del caso e informes de cada paso", texto=True)
    p.apartado("Próximo paso", "Facilita los precios de compra desde 2023, si Backblaze reclama la garantía y las "
                               "horas que pueden dedicar los técnicos.")


def pagina_decision(inf, c, filas):
    """Página 10: las cinco decisiones, en el orden de lo que hay en juego (la del tomo, desde el auditor del 19/11)."""
    p = inf.pagina("Cinco decisiones para la dirección de operaciones", "decision", panel="Decisiones propuestas")
    p.texto("Se proponen a la dirección de operaciones estas cinco decisiones, por este orden.")
    m100, r100 = c["listas"]["100"]
    e = c["error"]
    p.tabla(["Decisión", "Quién", "Plazo", "Por qué"], [
        ["Comprar en cada capacidad el modelo de menor coste por terabyte y año, con su precio "
         "confirmado desde 2023", "Departamento de compras", "En la siguiente compra",
         "En los siete grupos de compra comparables, el más barato por terabyte es el que menos falla (pág. 3)"],
        ["Revisar cada mes los discos de la lista de riesgo, con el tamaño que puedan atender los técnicos",
         "Dirección de operaciones, con los técnicos de los centros", "Cada mes",
         f"En la prueba final la lista encontró {numero(m100, 1)} fallos al mes entre 100 discos, frente a "
         f"{numero(r100, 1)} con la {REGLA} (pág. 8)"],
        ["Vigilar más los discos desde los 2 años cumplidos y revisar el tomo de cada disco que falle",
         "Técnicos de los centros", "Pendiente de fijar por la dirección",
         "La tasa sube cada año hasta los 5 (pág. 5). Los fallos de un tomo llegan algo más juntos (pág. 7)"],
        ["Revisar con el equipo del centro de datos sac2 en qué se diferencia su operación", "Dirección de operaciones",
         "Pendiente de fijar por la dirección", f"sac2 falla un {c['sac2_mas']} % más de lo esperado (pág. 6)"],
        ["Comprar los repuestos con los fallos del trimestre anterior, con un margen", "Departamento de compras",
         "Cada trimestre", f"Su error medio es del {pct(e['referencia']['wape'] * 100, 1)}, frente al "
                           f"{pct(e['cuenta']['wape'] * 100, 1)} de la previsión por modelo y edad (pág. 4)"]],
        fuente="páginas de este informe", texto=True)


def paginas_anexo(inf, c, filas):
    """Anexo: definiciones, cálculos, método, fuentes y datos personales (D6)."""
    d = inf.pagina("Definiciones", "anexo", panel="Definiciones")
    d.tabla(["Término", "Definición"], DEFINICIONES_CASO, fuente="documentación técnica de Backblaze y reglas del caso",
            texto=True)
    k = inf.pagina("Cómo se calculan las cifras", "anexo", panel="Cálculos")
    k.tabla(["Término", "Definición"], DEFINICIONES_LISTA, fuente="reglas de negocio del caso", texto=True)
    k.texto("Tasa anual de fallo: de cada 100 discos que funcionan un año entero, cuántos fallan. Se calcula con los "
            "fallos entre los días de disco, por 365 y por 100. Días de disco: la suma de los días que estuvo "
            "funcionando cada disco.",
            "Coste por terabyte y año: suma dos partes. La primera es el precio del disco, repartido entre su "
            "capacidad y 6 años de vida supuesta. La segunda, la tasa anual de fallo por el coste de cada cambio: "
            "disco nuevo y 37 $ de mano de obra.",
            f"La {REGLA} cuenta cuántos de los contadores 5, 187, 188, 197 y 198 pasan de cero. Ordena los discos "
            "por esa cuenta y, si empatan, por la suma de los contadores sin el 188. Es la referencia con la que se "
            "compara la lista de riesgo; los datos no dicen si Backblaze la usa.")
    a = inf.pagina("Método", "anexo", panel="Método")
    a.texto("Coste: los modelos con 50.000 días de disco al año como mínimo y 20 fallos o más.",
            "Repuestos: la tasa de fallo de cada modelo y edad por sus discos el primer día del trimestre. Se compara "
            "con repetir los fallos del trimestre anterior.",
            "Edad: tasa por año de edad cumplido, con intervalos más anchos para recoger lo que cambia entre "
            "trimestres.",
            "Centros: fallos observados frente a los esperados con la tasa de cada modelo, edad y trimestre.",
            "Tomos: los fallos reales frente a 200 simulaciones que los reparten al azar dentro de cada centro y "
            "trimestre.",
            "Lista de riesgo: tres tipos de modelo comparados en cinco tramos trimestrales, de abril de 2023 a junio "
            "de 2024. Ganó uno de árboles de decisión combinados (HistGradientBoosting), que se midió una sola vez "
            "con los doce meses siguientes. El intervalo de la página 8 sale de 1.000 repeticiones al azar.")
    b = inf.pagina("Fuentes y datos personales", "anexo", panel="Fuentes y datos personales")
    b.texto("Datos personales. Los datos son de discos. El número de serie identifica a cada disco y ninguna columna "
            "habla de una persona. Backblaze los publica en abierto, así que no hay datos personales.")
    # La prueba final, en su propia página del anexo: en «Método» no cabe (T2) y en esta pasaba de la pantalla (S3)
    f = inf.pagina("La prueba final", "anexo", panel="La prueba final")
    f.texto("La lista de riesgo y los repuestos se midieron con el último año, de julio de 2025 a junio de 2026, que "
            "se guardó hasta el final. En la lista no entra junio de 2026, porque sus 30 días siguientes pasan del "
            "final de los datos. Las cifras de la página 8 son las del modelo examinado.",
            "El modelo que se usa hoy se reentrenó con un año más de datos. También se midió en ese año antes de "
            f"aprobarlo, con {numero(c['en_uso_100'], 2)} fallos al mes en la lista de 100, así que ese año ya no es "
            "una prueba independiente para él.")
    b.tabla(["Cifra", "Fichero de informes", "Fecha de los datos"], [
        ["Coste por terabyte y repuestos", COSTE, "Enero de 2020 a junio de 2025"],
        ["Discos y edad", EDAD, "Enero de 2020 a junio de 2025"],
        ["Centros y tomos", CENTROS, "Julio de 2023 a junio de 2025"],
        ["Lista de riesgo, prueba anterior", MODELO, "Julio de 2024 a junio de 2025"],
        ["Lista de riesgo, prueba final", FINAL, "Julio de 2025 a junio de 2026"],
        ["Repuestos, prueba final", PREVISION_FINAL, "Julio de 2025 a junio de 2026"],
        ["Fallos sin aviso, punto ciego de la lista", PUNTO_CIEGO, "Julio de 2024 a mayo de 2026"],
        ["Coste de los fallos de 2024, con y sin garantía", EJECUTIVO, "Año 2024"],
        ["Cifras de los gráficos", SALIDA_CSV.name, "Las de cada gráfico"]],
        fuente="carpeta de informes del caso", texto=True)


# =====================================================================================================================
# MONTAJE
# =====================================================================================================================

def construir(entradas):
    """Comprueba las fechas, monta el informe y pasa las guardias: devuelve (HTML, filas del CSV, informe)."""
    comprobar_fechas(entradas)
    c = leer_cifras(entradas)
    inf = Informe(TITULO, LECTOR)
    filas = []
    # Páginas en su orden
    for funcion in (pagina_resumen, pagina_caso, pagina_coste, pagina_repuestos, pagina_edad, pagina_centros,
                    pagina_tomos, pagina_lista, pagina_limites, pagina_decision, paginas_anexo):
        funcion(inf, c, filas)
    # Las páginas que cita el texto son las de verdad: compra en la 3, repuestos en la 4, edad en la 5, centros en la
    # 6, lista en la 8 y decisiones en la 10
    paneles = [p.panel for p in inf.paginas]
    exigir(paneles[2:8] == ["Qué modelo comprar", "Los repuestos", "La edad", "Los centros de datos", "Los tomos",
                            "La lista de riesgo"] and [p.tipo for p in inf.paginas][8:10] == ["limites", "decision"],
           "las páginas citadas existen")
    texto = inf.html()
    sin_jerga(texto, {p.id for p in inf.paginas if p.tipo == "anexo"})
    sin_prohibidas(texto)
    titulos_claros([TITULO] + [p.titulo for p in inf.paginas if p.tipo != "anexo"])
    return texto, filas, inf


def palabras(pagina):
    """Palabras del texto de una página: párrafos y apartados, sin rótulos, tablas, gráficos ni cifras clave."""
    texto = " ".join(b["html"] for b in pagina.bloques if b["clase"] in ("parrafo", "apartado"))
    texto = re.sub(r"<h2>.*?</h2>", " ", texto)
    return len(html.unescape(re.sub(r"<[^>]+>", " ", texto)).split())


def main():
    """Comprueba el intérprete y el orden, monta el informe, lo escribe y dice cada página con su alto."""
    if Path(sys.prefix).name != ENTORNO:
        raise SystemExit(f"Lanza dentro del entorno {ENTORNO} (conda activate {ENTORNO}); este es {sys.prefix}")
    entradas = leer_entradas(INFORMES)
    comprobar_orden(entradas)
    texto, filas, inf = construir(entradas)
    SALIDA_HTML.write_text(texto, encoding="utf-8")
    escribir_csv(SALIDA_CSV, filas)
    for i, p in enumerate(inf.paginas, 1):
        print(f"{i:>2}. {p.tipo:<9} {p.alto():>4} px {palabras(p):>4} palabras  {p.titulo}")
    print(f"Escrito {SALIDA_HTML.relative_to(RAIZ)} y {SALIDA_CSV.relative_to(RAIZ)} ({len(filas)} cifras)")


if __name__ == "__main__":
    main()
