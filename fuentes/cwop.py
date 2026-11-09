"""Fuente: estaciones ciudadanas de la red CWOP/APRS, vía findU.com.

findU devuelve como máximo 20 estaciones por consulta de cercanía, así que una
vez por día se recorre el país con una grilla (subdividiendo donde hay muchas)
para armar la lista de indicativos. En cada actualización se lee el último
paquete APRS de cada uno, que trae posición exacta y hora UTC.
"""
import re
from datetime import datetime, timezone

from .comun import cacheado, descargar, en_argentina, en_paralelo, estacion, presion_mar

ID = "cwop"
NOMBRE = "CWOP (estaciones ciudadanas)"
SITIO = "http://www.findu.com/"
TIPO = "privada"
MINUTOS = 30

URL_CERCANAS = "http://www.findu.com/cgi-bin/wxnear.cgi?lat={lat}&lon={lon}&radius={radio}"
URL_PAQUETES = "http://www.findu.com/cgi-bin/rawwx.cgi?call={indicativo}&last=1"
MAXIMO_POR_CONSULTA = 20
PASO_GRADOS = 2.0
MILLAS_POR_GRADO = 69
# Indicativos de radioaficionados de países vecinos (cerca de la frontera el contorno es aproximado).
PREFIJOS_VECINOS = ("CX", "CV", "CW", "CA", "CB", "CC", "CD", "CE", "XQ", "XR", "ZP", "CP",
                    "PP", "PQ", "PR", "PS", "PT", "PU", "PV", "PW", "PX", "PY")

_POSICION = re.compile(r"(\d{2})(\d{2}\.\d{2})([NS]).(\d{3})(\d{2}\.\d{2})([EW])")
_HORA = re.compile(r"[@/](\d{2})(\d{2})(\d{2})z")


def _campo(paquete, letra, digitos):
    m = re.search(rf"{letra}(-?\d{{{digitos}}})", paquete)
    return int(m[1]) if m else None


def _hora(paquete):
    m = _HORA.search(paquete)
    if not m:
        return None
    ahora = datetime.now(timezone.utc)
    dia, hora, minuto = map(int, m.groups())
    anio, mes = ahora.year, ahora.month
    if dia > ahora.day:  # el paquete es del mes anterior
        anio, mes = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    try:
        return datetime(anio, mes, dia, hora, minuto, tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def decodificar(paquete):
    """Paquete de tiempo APRS: posición, _ddd/sss (viento), gGGG, tTTT (°F), hHH, bBBBBB."""
    pos = _POSICION.search(paquete)
    viento = re.search(r"_(\d{3})/(\d{3})", paquete)
    temp_f = _campo(paquete, "t", 3)
    if not pos or temp_f is None:
        return None
    lat = (int(pos[1]) + float(pos[2]) / 60) * (-1 if pos[3] == "S" else 1)
    lon = (int(pos[4]) + float(pos[5]) / 60) * (-1 if pos[6] == "W" else 1)
    humedad, presion, rafaga = _campo(paquete, "h", 2), _campo(paquete, "b", 5), _campo(paquete, "g", 3)
    return {
        "lat": lat, "lon": lon,
        "hora_utc": _hora(paquete),
        "temp_c": round((temp_f - 32) / 1.8, 1),
        "humedad_pct": 100 if humedad == 0 else humedad,
        "presion_hpa": None if presion is None else presion_mar(presion / 10),
        "viento_kmh": round(int(viento[2]) * 1.609, 1) if viento else None,
        "viento_dir_grados": int(viento[1]) if viento and int(viento[2]) else None,
        "rafaga_kmh": None if rafaga is None else round(rafaga * 1.609, 1),
    }


def _cercanas(lat, lon, paso):
    """Indicativos alrededor de un punto; si las 20 que devuelve findU están todas
    dentro del radio, puede haber más y se subdivide."""
    radio = paso * MILLAS_POR_GRADO * 0.75
    pagina = descargar(URL_CERCANAS.format(lat=round(lat, 2), lon=round(lon, 2), radio=round(radio))).decode("latin-1")
    # findU ignora el radio y siempre devuelve las 20 más cercanas, con la distancia en millas.
    filas = re.findall(r'wxpage\.cgi\?call=([\w\-]+)">[^<]*</a>\s*</td><td>([\d.]+)', pagina)
    encontrados = {c for c, millas in filas if float(millas) <= radio}
    if len(encontrados) >= MAXIMO_POR_CONSULTA and paso > 0.6:
        medio = paso / 4
        for dlat in (-medio, medio):
            for dlon in (-medio, medio):
                encontrados |= _cercanas(lat + dlat, lon + dlon, paso / 2)
    return encontrados


def _buscar_indicativos():
    centros = []
    lat = -55.5 + PASO_GRADOS / 2
    while lat < -21.5:
        lon = -73.6 + PASO_GRADOS / 2
        while lon < -53.5:
            # Se incluyen celdas que tocan el país aunque su centro caiga afuera.
            if any(en_argentina(lat + a, lon + b) for a in (-1, 0, 1) for b in (-1, 0, 1)):
                centros.append((lat, lon))
            lon += PASO_GRADOS
        lat += PASO_GRADOS
    encontrados = set()
    for r in en_paralelo(lambda c: _cercanas(c[0], c[1], PASO_GRADOS), centros, hilos=3):
        encontrados |= r or set()
    return sorted(encontrados)


def _ultimo_paquete(indicativo):
    pagina = descargar(URL_PAQUETES.format(indicativo=indicativo)).decode("latin-1")
    paquetes = [re.sub(r"<[^>]+>", "", linea).strip() for linea in pagina.splitlines() if ">AP" in linea]
    return paquetes[-1] if paquetes else None


def obtener():
    indicativos = [i for i in cacheado("cwop_indicativos", 24, _buscar_indicativos)
                   if not i.upper().startswith(PREFIJOS_VECINOS)]
    salida = []
    for indicativo, paquete in zip(indicativos, en_paralelo(_ultimo_paquete, indicativos, hilos=4)):
        datos = decodificar(paquete) if paquete else None
        # Sin hora no se puede saber si la lectura es vieja.
        if not datos or not datos["hora_utc"] or not en_argentina(datos["lat"], datos["lon"]):
            continue
        salida.append(estacion(
            id=f"cwop:{indicativo.upper()}",
            enlace=f"http://www.findu.com/cgi-bin/wxpage.cgi?call={indicativo}",
            nombre=f"{indicativo.upper()} (CWOP)",
            fuente=ID,
            crudo=paquete,
            **datos,
        ))
    return salida
