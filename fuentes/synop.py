"""Fuente: partes SYNOP de las estaciones del SMN, vía OGIMET (ogimet.com).

Complementa el archivo de tiempo presente: los SYNOP traen el número OMM de
la estación, así que se ubican sin ambigüedad con el listado del SMN, y suman
punto de rocío, presión, ráfagas y fenómenos. Bloques 87 (Argentina) y 88/89
(bases antárticas). OGIMET pide no abusar: se consulta cada 30 minutos.
"""
from datetime import datetime, timedelta, timezone

from . import smn
from .comun import descargar, estacion, nudos_a_kmh, ms_a_kmh

ID = "synop"
NOMBRE = "SMN (partes SYNOP)"
SITIO = "https://www.ogimet.com/"
MINUTOS = 30

URL = "https://www.ogimet.com/cgi-bin/getsynop?block={bloque}&begin={desde}"
BLOQUES = ("87", "88", "89")
HORAS_ATRAS = 4

CIELO = {0: "Despejado", 1: "Algunas nubes", 2: "Algunas nubes", 3: "Parcialmente nublado",
         4: "Parcialmente nublado", 5: "Mayormente nublado", 6: "Mayormente nublado",
         7: "Mayormente nublado", 8: "Cubierto", 9: "Cielo no visible"}

# Tiempo presente (ww), agrupado por décadas de la tabla 4677 de la OMM.
FENOMENOS = [
    (4, 5, "Humo o bruma"), (6, 9, "Polvo en suspensión"), (10, 10, "Neblina"),
    (11, 12, "Niebla baja"), (13, 13, "Relámpagos"), (17, 17, "Tormenta"),
    (18, 18, "Turbonada"), (30, 35, "Tormenta de polvo"), (36, 39, "Ventisca de nieve"),
    (40, 49, "Niebla"), (50, 59, "Llovizna"), (60, 69, "Lluvia"), (70, 79, "Nieve"),
    (80, 84, "Chaparrones"), (85, 86, "Chaparrones de nieve"), (87, 90, "Granizo"),
    (91, 99, "Tormenta"),
]


def _fenomeno(ww):
    return next((texto for a, b, texto in FENOMENOS if a <= ww <= b), None)


def _temperatura(grupo):
    signo, valor = grupo[1], grupo[2:5]
    if "/" in valor or signo not in "01":
        return None
    return (-1 if signo == "1" else 1) * int(valor) / 10


def _presion(digitos):
    if "/" in digitos:
        return None
    p = int(digitos) / 10
    return p + 1000 if p < 100 else p


def _visibilidad(vv):
    if not vv.isdigit():
        return None
    v = int(vv)
    if v <= 50:
        km = v / 10
    elif 56 <= v <= 80:
        km = v - 50
    elif 81 <= v <= 88:
        km = (v - 80) * 5 + 30
    elif v == 89:
        return "70+ km"
    else:
        return None
    return f"{km:g} km"


def decodificar(texto):
    """Decodifica la sección 1 (y las ráfagas de la 3) de un parte SYNOP AAXX."""
    grupos = texto.replace("=", " ").split()
    if "AAXX" not in grupos:
        return None
    grupos = grupos[grupos.index("AAXX") + 1:]
    if len(grupos) < 4 or "NIL" in grupos[:4]:
        return None
    unidad_viento = grupos[0][4:5]  # iw: 0/1 = m/s, 3/4 = nudos
    irixhvv, nddff = grupos[2], grupos[3]
    resto = grupos[4:]
    r = {"visibilidad": _visibilidad(irixhvv[3:5])}

    n, dd, ff = nddff[0], nddff[1:3], nddff[3:5]
    r["cielo"] = CIELO.get(int(n)) if n.isdigit() else None
    if ff.isdigit():
        if ff == "99" and resto and resto[0].startswith("00"):
            ff = resto.pop(0)[2:5]
        convertir = nudos_a_kmh if unidad_viento in "34" else ms_a_kmh
        r["viento_kmh"] = convertir(int(ff)) if ff.isdigit() else None
    if dd.isdigit() and 1 <= int(dd) <= 36:
        r["viento_dir_grados"] = int(dd) * 10

    seccion = 1
    for g in resto:
        if g in ("333", "555"):
            seccion = int(g)
            continue
        if len(g) != 5:
            continue
        if seccion == 1:
            if g[0] == "1":
                r["temp_c"] = _temperatura(g)
            elif g[0] == "2" and g[1] != "9":
                r["rocio_c"] = _temperatura(g)
            elif g[0] == "2" and g[1] == "9" and g[2:].isdigit():
                r["humedad_pct"] = int(g[2:])
            elif g[0] == "4" and g[1] in "09":  # presión a nivel del mar (4PPPP)
                r["presion_hpa"] = _presion(g[1:])
            elif g[0] == "3" and "presion_hpa" not in r:
                r["presion_estacion"] = _presion(g[1:])
            elif g[0] == "7" and g[1:3].isdigit():
                r["fenomenos"] = _fenomeno(int(g[1:3]))
        elif seccion == 333 and g[:3] in ("910", "911") and g[3:].isdigit():
            convertir = nudos_a_kmh if unidad_viento in "34" else ms_a_kmh
            r["rafaga_kmh"] = max(r.get("rafaga_kmh") or 0, convertir(int(g[3:])))
    # Si no hay presión a nivel del mar, se usa la de la estación.
    estacion_p = r.pop("presion_estacion", None)
    if r.get("presion_hpa") is None:
        r["presion_hpa"] = estacion_p
    return r


def obtener():
    listado = {e["nro"]: e for e in smn.listado_estaciones()}
    desde = (datetime.now(timezone.utc) - timedelta(hours=HORAS_ATRAS)).strftime("%Y%m%d%H00")
    ultimos = {}
    for bloque in BLOQUES:
        texto = descargar(URL.format(bloque=bloque, desde=desde), timeout=60).decode("latin-1")
        for linea in texto.splitlines():
            partes = linea.split(",", 6)
            if len(partes) < 7 or partes[0] not in listado:
                continue
            hora = datetime(*map(int, partes[1:6]), tzinfo=timezone.utc)
            if partes[0] not in ultimos or hora > ultimos[partes[0]][0]:
                ultimos[partes[0]] = (hora, partes[6].strip())

    salida = []
    for nro, (hora, parte) in ultimos.items():
        datos = decodificar(parte)
        if not datos or datos.get("temp_c") is None:
            continue
        e = listado[nro]
        salida.append(estacion(
            id=f"synop:{nro}",
            enlace=f"https://www.ogimet.com/cgi-bin/gsynres?ind={nro}&lang=es",
            nombre=f"{e['nombre'].title()} (SYNOP {nro})",
            fuente=ID,
            lat=e["lat"], lon=e["lon"],
            altura_m=e["altura"],
            hora_utc=hora.isoformat(),
            crudo=parte,
            **datos,
        ))
    return salida
