"""Consultas del informe ejecutivo del caso 68 (patrón assets/07_patron_informe_ejecutivo.md, §5).

Mide las cifras que escribe el informe ejecutivo y las deja, cada una con su nombre, su población y su periodo, en
informes/consultas-informe-ejecutivo.json. El informe (scripts/08_informe_ejecutivo.py) las lee sin calcular nada nuevo.

  - Por año, de 2020 al año de fecha_datos, desde modelo_trimestre: días de disco, fallos, fallos en garantía, tasa
    anual de fallo (fallos / días de disco × 365, en porcentaje), coste de los fallos, coste con garantía y si el año
    está completo.
  - Desde inicio_trimestre: los discos del primer día de cada trimestre (suma de discos por año y trimestre), cuántas
    subidas hay de un trimestre al siguiente y la razón entre el último y el primero.
  - La razón entre el coste del último año completo y el del primero, la media de fallos al mes del último año completo
    y la parte de sus fallos que estaba en garantía.
  - Desde fallos_detalle: los fallos de todo el periodo por tipo de disco, y por año los fallos y los dos costes de los
    discos de datos, que tienen que ser los de modelo_trimestre.

Para con ERROR, sin escribir el JSON, si la huella de una tabla no es la de su salida en informes/transformacion-datos.json,
si falta un trimestre en medio de la serie o si fallos_detalle no da los fallos o los costes de modelo_trimestre.

Depende de scripts/05_transformacion_datos.py: lee su JSON y tres de sus tablas, que no modifica. No lee fotos_riesgo.

Uso: python -W error scripts/07_consultas_informe_ejecutivo.py [--raiz CARPETA_DEL_CASO]
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

CASO = Path(__file__).resolve().parents[1]

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/07_consultas_informe_ejecutivo.py"
TRANSFORMACION = "informes/transformacion-datos.json"
SALIDA = "informes/consultas-informe-ejecutivo.json"
# Fecha de referencia de los datos (reglas del caso: el análisis llega al 30/06/2025)
FECHA_DATOS = dt.date(2025, 6, 30)
# Primer año del periodo analizado (1 de enero de 2020)
PRIMER_ANO = 2020
TABLAS = ["modelo_trimestre", "inicio_trimestre", "fallos_detalle"]
POBLACION_DATOS = "discos de datos (sin los de arranque de los servidores)"
# Un coste de fallos_detalle coincide con el de modelo_trimestre si difiere menos de medio céntimo
TOLERANCIA_USD = 0.005


class Parada(Exception):
    """Condición que impide escribir el JSON; el mensaje dice cuál."""


# =================================================================================================================
# 3. Utilidades
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def cifra(nombre, valor, unidad, poblacion, periodo, calculo):
    """Una cifra del JSON con su nombre, su población y su periodo."""
    return {"nombre": nombre, "valor": valor, "unidad": unidad, "poblacion": poblacion, "periodo": periodo,
            "calculo": calculo}


def periodo_del_ano(ano):
    """Periodo de un año en palabras: el año natural o, el de fecha_datos, hasta ese día."""
    if ano == FECHA_DATOS.year and FECHA_DATOS < dt.date(ano, 12, 31):
        return f"de {ano}-01-01 a {FECHA_DATOS.isoformat()}"
    return f"año {ano}"


# =================================================================================================================
# 4. Entradas: huellas y lectura
# =================================================================================================================
def comprobar_huellas(raiz):
    """Compara la huella de cada tabla con la de su salida en transformacion-datos.json; para si una no coincide."""
    ruta = raiz / TRANSFORMACION
    if not ruta.exists():
        raise Parada(f"falta {TRANSFORMACION}")
    salidas = {s["tabla"]: s for s in json.loads(ruta.read_text(encoding="utf-8"))["salidas"]}
    entradas = []
    for t in TABLAS:
        if t not in salidas:
            raise Parada(f"{t} no está entre las salidas de {TRANSFORMACION}")
        huella = sha256(raiz / salidas[t]["ruta"])
        coincide = huella == salidas[t]["sha256"]
        entradas.append({"ruta": salidas[t]["ruta"], "sha256": huella,
                         "sha256_transformacion": salidas[t]["sha256"], "coincide": coincide})
        if not coincide:
            raise Parada(f"la huella de {salidas[t]['ruta']} no es la de su salida en {TRANSFORMACION}")
    return entradas


def leer(raiz):
    """Lee solo las columnas que usan las consultas de las tres tablas."""
    p = raiz / "data" / "processed"
    mt = pd.read_parquet(p / "modelo_trimestre.parquet",
                         columns=["ano", "dias_disco", "fallos", "fallos_en_garantia", "coste_fallos_usd",
                                  "coste_fallos_garantia_usd"])
    it = pd.read_parquet(p / "inicio_trimestre.parquet", columns=["ano", "trimestre", "discos"])
    fd = pd.read_parquet(p / "fallos_detalle.parquet",
                         columns=["tipo_disco", "ano", "coste_fallo_usd", "coste_fallo_garantia_usd"])
    return mt, it, fd


# =================================================================================================================
# 5. Consultas
# =================================================================================================================
# -----------------------------------------------------------------------------------------------------------------
# 5.1 Por año, desde modelo_trimestre
# -----------------------------------------------------------------------------------------------------------------
def por_ano(mt):
    """Sumas por año de modelo_trimestre y la tasa anual de fallo; devuelve las filas y las cifras."""
    anos = list(range(PRIMER_ANO, FECHA_DATOS.year + 1))
    suma = mt.groupby("ano")[["dias_disco", "fallos", "fallos_en_garantia", "coste_fallos_usd",
                              "coste_fallos_garantia_usd"]].sum()
    filas, cifras = {}, []
    for ano in anos:
        if ano not in suma.index or suma.loc[ano, "dias_disco"] <= 0:
            raise Parada(f"modelo_trimestre no tiene días de disco en {ano}")
        s = suma.loc[ano]
        fila = {"dias_disco": int(s["dias_disco"]), "fallos": int(s["fallos"]),
                "fallos_en_garantia": int(s["fallos_en_garantia"]),
                "coste_fallos_usd": float(s["coste_fallos_usd"]),
                "coste_fallos_garantia_usd": float(s["coste_fallos_garantia_usd"])}
        # Tasa anual: fallos por cada 100 discos que estuvieran en servicio un año entero
        fila["tasa_anual_pct"] = fila["fallos"] / fila["dias_disco"] * 365 * 100
        # Completo si los datos llegan al 31 de diciembre de ese año
        fila["completo"] = FECHA_DATOS >= dt.date(ano, 12, 31)
        filas[ano] = fila
        per = periodo_del_ano(ano)
        cifras += [
            cifra(f"dias_disco_{ano}", fila["dias_disco"], "días de disco", POBLACION_DATOS, per,
                  "suma de dias_disco de modelo_trimestre"),
            cifra(f"fallos_{ano}", fila["fallos"], "fallos", POBLACION_DATOS, per, "suma de fallos de modelo_trimestre"),
            cifra(f"fallos_en_garantia_{ano}", fila["fallos_en_garantia"], "fallos", POBLACION_DATOS, per,
                  "suma de fallos_en_garantia de modelo_trimestre"),
            cifra(f"tasa_anual_pct_{ano}", fila["tasa_anual_pct"], "%", POBLACION_DATOS, per,
                  "fallos / días de disco × 365 × 100"),
            cifra(f"coste_fallos_usd_{ano}", fila["coste_fallos_usd"], "dólares", POBLACION_DATOS, per,
                  "suma de coste_fallos_usd de modelo_trimestre"),
            cifra(f"coste_fallos_garantia_usd_{ano}", fila["coste_fallos_garantia_usd"], "dólares", POBLACION_DATOS,
                  per, "suma de coste_fallos_garantia_usd de modelo_trimestre"),
            cifra(f"ano_completo_{ano}", fila["completo"], "sí o no", POBLACION_DATOS, per,
                  f"los datos llegan al 31 de diciembre (fecha_datos {FECHA_DATOS.isoformat()})"),
        ]
    return filas, cifras


# -----------------------------------------------------------------------------------------------------------------
# 5.2 Discos del primer día de cada trimestre, desde inicio_trimestre
# -----------------------------------------------------------------------------------------------------------------
def trimestres(it):
    """Discos del primer día de cada trimestre, subidas al siguiente y razón último / primero."""
    serie = it.groupby(["ano", "trimestre"])["discos"].sum().sort_index()
    claves = list(serie.index)
    # La serie tiene que ser seguida: sin un trimestre en medio, una subida se mediría entre dos no consecutivos
    for (a0, t0), (a1, t1) in zip(claves, claves[1:]):
        if a1 * 4 + t1 != a0 * 4 + t0 + 1:
            raise Parada(f"inicio_trimestre salta de {a0}-T{t0} a {a1}-T{t1}: falta un trimestre en medio")
    valores = [int(v) for v in serie.to_numpy()]
    subidas = sum(1 for x, y in zip(valores, valores[1:]) if y > x)
    pasos = len(valores) - 1
    (a_ini, t_ini), (a_fin, t_fin) = claves[0], claves[-1]
    pob = f"{POBLACION_DATOS} en servicio el primer día del trimestre"
    cifras = [cifra(f"discos_inicio_{a}_T{t}", v, "discos", pob, f"primer día de {a}-T{t}",
                    "suma de discos de inicio_trimestre por año y trimestre")
              for (a, t), v in zip(claves, valores)]
    periodo = f"de {a_ini}-T{t_ini} a {a_fin}-T{t_fin}"
    cifras += [
        cifra("trimestres", len(valores), "trimestres", pob, periodo, "trimestres distintos de inicio_trimestre"),
        cifra("primer_trimestre", f"{a_ini}-T{t_ini}", "trimestre", pob, periodo, "el primero de la serie"),
        cifra("ultimo_trimestre", f"{a_fin}-T{t_fin}", "trimestre", pob, periodo, "el último de la serie"),
        cifra("subidas_trimestre", subidas, "trimestres", pob, periodo,
              "trimestres con más discos que el anterior"),
        cifra("pasos_trimestre", pasos, "trimestres", pob, periodo, "pasos de un trimestre al siguiente"),
        cifra("razon_discos_ultimo_primero", valores[-1] / valores[0], "veces", pob,
              f"{a_fin}-T{t_fin} frente a {a_ini}-T{t_ini}", "discos del último trimestre / discos del primero"),
    ]
    return cifras


# -----------------------------------------------------------------------------------------------------------------
# 5.3 Razones y partes del último año completo
# -----------------------------------------------------------------------------------------------------------------
def del_ultimo_ano(filas):
    """Razón de coste frente al primer año, media de fallos al mes y parte en garantía del último año completo."""
    completos = [a for a, f in filas.items() if f["completo"]]
    ultimo, primero = max(completos), min(completos)
    f = filas[ultimo]
    return [
        cifra(f"razon_coste_{ultimo}_{primero}", f["coste_fallos_usd"] / filas[primero]["coste_fallos_usd"], "veces",
              POBLACION_DATOS, f"año {ultimo} frente a año {primero}", "coste de los fallos de un año / del otro"),
        cifra(f"media_fallos_mes_{ultimo}", f["fallos"] / 12, "fallos al mes", POBLACION_DATOS, f"año {ultimo}",
              "fallos del año / 12"),
        cifra(f"parte_fallos_garantia_pct_{ultimo}", f["fallos_en_garantia"] / f["fallos"] * 100, "%",
              POBLACION_DATOS, f"año {ultimo}", "fallos en garantía / fallos × 100"),
        cifra(f"dias_disco_millones_{ultimo}", f["dias_disco"] / 1e6, "millones de días de disco", POBLACION_DATOS,
              f"año {ultimo}", "días de disco / 1.000.000"),
    ]


# -----------------------------------------------------------------------------------------------------------------
# 5.4 fallos_detalle: por tipo de disco y, por año, frente a modelo_trimestre
# -----------------------------------------------------------------------------------------------------------------
def desde_detalle(fd, filas):
    """Fallos por tipo de disco y, por año, fallos y costes de los discos de datos; para si no son los de modelo_trimestre."""
    periodo = f"1 de enero de {PRIMER_ANO} a {FECHA_DATOS.isoformat()}"
    tipos = fd["tipo_disco"].value_counts()
    cifras = [cifra(f"fallos_tipo_{t}", int(tipos.get(t, 0)), "fallos", f"discos de {t}", periodo,
                    "filas de fallos_detalle con ese tipo_disco") for t in ("datos", "arranque")]
    datos = fd[fd["tipo_disco"] == "datos"]
    suma = datos.groupby("ano")[["coste_fallo_usd", "coste_fallo_garantia_usd"]].sum()
    cuenta = datos.groupby("ano").size()
    comprobaciones = []
    for ano, f in filas.items():
        n = int(cuenta.get(ano, 0))
        coste = float(suma["coste_fallo_usd"].get(ano, 0.0))
        coste_g = float(suma["coste_fallo_garantia_usd"].get(ano, 0.0))
        iguales = {"fallos": n == f["fallos"],
                   "coste_fallos_usd": abs(coste - f["coste_fallos_usd"]) < TOLERANCIA_USD,
                   "coste_fallos_garantia_usd": abs(coste_g - f["coste_fallos_garantia_usd"]) < TOLERANCIA_USD}
        comprobaciones.append({"ano": ano, "fallos_detalle": {"fallos": n, "coste_fallos_usd": coste,
                                                              "coste_fallos_garantia_usd": coste_g},
                               "coincide": all(iguales.values())})
        distintos = [k for k, v in iguales.items() if not v]
        if distintos:
            raise Parada(f"fallos_detalle no da los {', '.join(distintos)} de {ano} de modelo_trimestre "
                         f"({n} fallos, {coste:.2f} y {coste_g:.2f} frente a {f['fallos']}, "
                         f"{f['coste_fallos_usd']:.2f} y {f['coste_fallos_garantia_usd']:.2f})")
        per = periodo_del_ano(ano)
        cifras += [
            cifra(f"detalle_fallos_{ano}", n, "fallos", POBLACION_DATOS, per, "filas de fallos_detalle de datos"),
            cifra(f"detalle_coste_fallos_usd_{ano}", coste, "dólares", POBLACION_DATOS, per,
                  "suma de coste_fallo_usd de fallos_detalle"),
            cifra(f"detalle_coste_fallos_garantia_usd_{ano}", coste_g, "dólares", POBLACION_DATOS, per,
                  "suma de coste_fallo_garantia_usd de fallos_detalle"),
        ]
    return cifras, comprobaciones


# =================================================================================================================
# 6. Ejecución
# =================================================================================================================
def principal(raiz):
    """Comprueba las entradas, hace las consultas y escribe el JSON solo si todo pasa."""
    entradas = comprobar_huellas(raiz)
    mt, it, fd = leer(raiz)
    filas, cifras = por_ano(mt)
    cifras += trimestres(it)
    cifras += del_ultimo_ano(filas)
    de_detalle, comprobaciones = desde_detalle(fd, filas)
    cifras += de_detalle
    # Las huellas tienen que seguir siendo las mismas al acabar: nadie ha cambiado las tablas a mitad
    if [e["sha256"] for e in entradas] != [sha256(raiz / e["ruta"]) for e in entradas]:
        raise Parada("una tabla ha cambiado mientras se leía")
    resultado = {
        "script": SCRIPT,
        "fecha_datos": FECHA_DATOS.isoformat(),
        "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
        # Estado calculado con lo que se ha comprobado, no escrito a mano (programacion-del-caso, error 24)
        "estado": "OK" if all(e["coincide"] for e in entradas) and all(x["coincide"] for x in comprobaciones)
        else "ERROR",
        "versiones": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                      "pyarrow": pa.__version__},
        "entradas": entradas,
        "comprobaciones": {"fallos_detalle_frente_a_modelo_trimestre": comprobaciones},
        "cifras": cifras,
    }
    (raiz / "informes").mkdir(exist_ok=True)
    (raiz / SALIDA).write_text(json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                               encoding="utf-8")
    print(f"OK: {len(cifras)} cifras en {SALIDA}")


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
