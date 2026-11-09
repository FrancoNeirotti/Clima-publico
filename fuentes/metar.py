"""Fuente: METAR de aeropuertos argentinos (API pública de aviationweather.gov)."""
import json
from datetime import datetime, timezone

from .comun import descargar, estacion, humedad_desde_rocio, nudos_a_kmh, numero

ID = "metar"
NOMBRE = "Aeropuertos (METAR)"
SITIO = "https://aviationweather.gov/data/metar/"

# bbox = latMín,lonMín,latMáx,lonMáx. Incluye partes de países vecinos,
# por eso después se filtra por el prefijo OACI argentino "SA".
URL = "https://aviationweather.gov/api/data/metar?bbox=-56,-74,-21,-53&format=json&hours=3"

CIELO = {
    "CLR": "Despejado", "SKC": "Despejado", "CAVOK": "Despejado",
    "NSC": "Sin nubes significativas", "FEW": "Algunas nubes",
    "SCT": "Parcialmente nublado", "BKN": "Mayormente nublado",
    "OVC": "Cubierto", "OVX": "Cielo no visible",
}


def _visibilidad(valor):
    """La API informa la visibilidad en millas terrestres ("10+" = 10 o más)."""
    if valor is None:
        return None
    texto = str(valor).strip()
    millas = numero(texto.rstrip("+"))
    if millas is None:
        return None
    km = round(millas * 1.609)
    return f"{km}+ km" if texto.endswith("+") else f"{km} km"


def _nombre(nombre, oaci):
    base = (nombre or oaci).removesuffix(", AR")
    return f"{base} ({oaci})"


def obtener():
    crudo = descargar(URL)
    datos = json.loads(crudo) if crudo.strip() else []  # 204 = sin datos

    # La consulta trae varias horas: nos quedamos con la última de cada aeropuerto.
    ultimas = {}
    for m in datos:
        oaci = str(m.get("icaoId") or "")
        if not oaci.startswith("SA"):
            continue
        previa = ultimas.get(oaci)
        if previa is None or (m.get("obsTime") or 0) > (previa.get("obsTime") or 0):
            ultimas[oaci] = m

    salida = []
    for oaci, m in ultimas.items():
        lat, lon = numero(m.get("lat")), numero(m.get("lon"))
        if lat is None or lon is None:
            continue
        t, td = numero(m.get("temp")), numero(m.get("dewp"))
        wdir = m.get("wdir")
        obs = m.get("obsTime")
        salida.append(estacion(
            id=f"metar:{oaci}",
            enlace=f"https://aviationweather.gov/data/metar/?ids={oaci}&hours=12",
            nombre=_nombre(m.get("name"), oaci),
            fuente=ID,
            lat=lat, lon=lon,
            altura_m=numero(m.get("elev")),
            hora_utc=datetime.fromtimestamp(obs, timezone.utc).isoformat() if obs else None,
            temp_c=t,
            rocio_c=td,
            humedad_pct=humedad_desde_rocio(t, td),
            viento_dir_grados=None if wdir == "VRB" else numero(wdir),
            viento_kmh=nudos_a_kmh(numero(m.get("wspd"))),
            rafaga_kmh=nudos_a_kmh(numero(m.get("wgst"))),
            presion_hpa=numero(m.get("slp")) or numero(m.get("altim")),
            visibilidad=_visibilidad(m.get("visib")),
            cielo=CIELO.get(m.get("cover")),
            fenomenos=m.get("wxString"),
            crudo=m.get("rawOb"),
        ))
    return salida
