"""Utilidades compartidas por todas las fuentes de datos.

Cada fuente devuelve una lista de estaciones en el mismo formato
(ver CAMPOS), así el mapa no necesita saber de dónde vino cada dato.
"""
import gzip
import json
import math
import os
import re
import threading
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

AGENTE = "Mozilla/5.0 (compatible; estaciones-ar/0.2)"
HORA_ARGENTINA = timezone(timedelta(hours=-3))
CARPETA_CACHE = Path(__file__).resolve().parent.parent / "cache"
_cache_memoria = {}
_candado_cache = threading.Lock()

# Contorno aproximado de la Argentina continental y Tierra del Fuego (lon, lat),
# para separar las estaciones de plataformas mundiales de las de países vecinos.
# Las fronteras son precisas a unos 20-30 km; el lado del mar es generoso.
CONTORNO_ARGENTINA = [
    (-67.2, -22.8), (-66.2, -21.8), (-65.0, -22.05), (-64.3, -22.8), (-63.9, -22.0),
    (-62.6, -22.2), (-61.0, -23.2), (-59.5, -24.2), (-58.2, -24.8), (-57.6, -25.35),
    (-58.1, -26.1), (-58.6, -27.25), (-56.0, -27.45), (-55.9, -27.4), (-54.62, -25.5),
    (-53.65, -25.95), (-53.8, -27.1), (-55.0, -27.85), (-55.75, -28.3), (-56.6, -29.3),
    (-57.6, -30.2), (-57.9, -31.5), (-58.15, -32.4), (-58.4, -33.1), (-58.4, -34.0),
    (-57.4, -35.1), (-56.0, -36.0), (-55.0, -38.0), (-58.0, -42.0), (-60.0, -47.0),
    (-62.0, -52.0), (-63.0, -55.3), (-66.5, -55.3), (-68.6, -54.85), (-68.6, -52.65),
    (-69.5, -52.1), (-71.0, -52.0), (-72.3, -51.6), (-73.3, -49.5), (-72.5, -48.0),
    (-71.9, -46.8), (-71.7, -45.5), (-71.4, -44.5), (-71.8, -43.5), (-71.7, -42.1),
    (-71.9, -40.5), (-71.6, -39.5), (-71.1, -37.8), (-70.5, -36.2), (-70.0, -34.0),
    (-70.0, -32.65), (-70.3, -31.0), (-69.6, -29.5), (-69.0, -28.0), (-68.5, -27.0),
    (-68.3, -26.0), (-67.6, -25.0), (-67.0, -23.6),
]


def en_argentina(lat, lon):
    """Punto en polígono (trazado de rayo) sobre CONTORNO_ARGENTINA."""
    dentro = False
    j = len(CONTORNO_ARGENTINA) - 1
    for i, (xi, yi) in enumerate(CONTORNO_ARGENTINA):
        xj, yj = CONTORNO_ARGENTINA[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


CAMPOS = (
    "id",                 # único entre fuentes, p. ej. "metar:SAAR"
    "nombre",
    "fuente",             # id de la fuente, p. ej. "metar"
    "lat", "lon",         # grados decimales
    "altura_m",
    "hora_utc",           # ISO 8601 en UTC
    "temp_c", "rocio_c", "humedad_pct", "sensacion_c",
    "viento_dir_grados",  # desde dónde sopla; None si es variable o calma
    "viento_kmh", "rafaga_kmh",
    "presion_hpa",
    "visibilidad",        # texto, p. ej. "10 km" o "16+ km"
    "cielo",              # texto en castellano
    "fenomenos",          # lluvia, niebla, etc., tal como lo informa la fuente
    "crudo",              # observación original (METAR u otra)
    "enlace",             # página de la estación en el sitio de la fuente, si existe
)


def estacion(**campos):
    """Arma un registro normalizado y avisa si se pasó un campo inexistente."""
    desconocidos = set(campos) - set(CAMPOS)
    if desconocidos:
        raise ValueError(f"Campos desconocidos: {sorted(desconocidos)}")
    return {c: campos.get(c) for c in CAMPOS}


def descargar(url, timeout=30, datos=None, cabeceras=None):
    """GET (o POST si se pasan `datos`) y devuelve los bytes de la respuesta."""
    encabezados = {"User-Agent": AGENTE}
    encabezados.update(cabeceras or {})
    if "Range" not in encabezados:  # comprimir un pedido parcial no tiene sentido
        encabezados["Accept-Encoding"] = "gzip"
    pedido = urllib.request.Request(url, data=datos, headers=encabezados)
    with urllib.request.urlopen(pedido, timeout=timeout) as resp:
        cuerpo = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            cuerpo = gzip.decompress(cuerpo)
        return cuerpo


def leer_json(nombre):
    """Contenido de cache/<nombre>.json, o None si no existe o está dañado."""
    try:
        return json.loads((CARPETA_CACHE / f"{nombre}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cacheado(nombre, horas, funcion):
    """Resultado de `funcion()` guardado en memoria y en disco durante `horas`, para
    no repetir descargas pesadas (índices, listados) en cada arranque del servidor.
    El resultado tiene que poder pasarse a JSON."""
    guardado = _cache_memoria.get(nombre) or leer_json(nombre)
    if guardado and time.time() - guardado["momento"] < horas * 3600:
        _cache_memoria[nombre] = guardado
        return guardado["datos"]
    guardado = {"momento": time.time(), "datos": funcion()}
    _cache_memoria[nombre] = guardado
    guardar_json(nombre, guardado)
    return guardado["datos"]


def guardar_json(nombre, datos):
    """Escribe cache/<nombre>.json de forma atómica (un corte no deja el archivo a medias)."""
    CARPETA_CACHE.mkdir(exist_ok=True)
    with _candado_cache:
        temporal = CARPETA_CACHE / f"{nombre}.json.tmp"
        temporal.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporal, CARPETA_CACHE / f"{nombre}.json")


def descargar_json(url, timeout=30, datos=None, cabeceras=None):
    return json.loads(descargar(url, timeout, datos, cabeceras))


def en_paralelo(funcion, elementos, hilos=8):
    """Aplica `funcion` a cada elemento con varios hilos; los errores quedan como None."""
    def seguro(x):
        try:
            return funcion(x)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=hilos) as ejecutor:
        return list(ejecutor.map(seguro, elementos))


def numero(valor):
    if valor is None:
        return None
    try:
        n = float(str(valor).strip().replace(",", "."))
    except ValueError:
        return None
    return n if math.isfinite(n) else None


def primer_numero(texto):
    """Primer número que aparece en un texto, p. ej. '13.6 &ordm;C' -> 13.6."""
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(texto or ""))
    return numero(m[0]) if m else None


def hora_local_a_utc(texto, formato):
    """Convierte una hora local de Argentina (texto sin zona) a ISO 8601 UTC."""
    try:
        local = datetime.strptime(texto.strip(), formato).replace(tzinfo=HORA_ARGENTINA)
    except (ValueError, AttributeError):
        return None
    return local.astimezone(timezone.utc).isoformat()


def ms_a_iso(ms):
    return None if ms is None else datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


_RUMBOS_16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
_RUMBOS = {r: i * 22.5 for i, r in enumerate(_RUMBOS_16)}
_RUMBOS.update({r.replace("O", "W"): g for r, g in _RUMBOS.items()})  # variante en inglés
_RUMBOS.update({"NORTE": 0, "NORDESTE": 45, "NORESTE": 45, "ESTE": 90, "SUDESTE": 135,
                "SURESTE": 135, "SUR": 180, "SUDOESTE": 225, "SUROESTE": 225,
                "OESTE": 270, "NOROESTE": 315})


def rumbo_a_grados(texto):
    """'NNE', 'OSO', 'Sudeste'... -> grados. None si es calma, variable o desconocido."""
    return _RUMBOS.get(sin_tildes(str(texto or "")).strip().upper())


# Rangos físicamente posibles en Argentina; lo que cae afuera es un error del sensor.
_RANGOS = {
    "temp_c": (-45, 47), "rocio_c": (-60, 35), "sensacion_c": (-60, 60),
    "humedad_pct": (1, 100), "viento_kmh": (0, 250), "rafaga_kmh": (0, 300),
    "viento_dir_grados": (0, 360), "presion_hpa": (450, 1090), "altura_m": (-50, 7000),
}


def limpiar(est):
    """Descarta valores imposibles y completa los que se pueden calcular."""
    for campo, (minimo, maximo) in _RANGOS.items():
        v = est.get(campo)
        if v is not None and not (minimo <= v <= maximo):
            est[campo] = None
    t, td, hr = est["temp_c"], est["rocio_c"], est["humedad_pct"]
    if t is not None and td is not None and td > t + 0.5:
        est["rocio_c"] = td = None
    if hr is None and td is not None:
        est["humedad_pct"] = humedad_desde_rocio(t, td)
    elif td is None and hr is not None:
        est["rocio_c"] = rocio_desde_humedad(t, hr)
    if est["viento_kmh"] is not None:
        est["viento_kmh"] = round(est["viento_kmh"])
    if est["rafaga_kmh"] is not None:
        est["rafaga_kmh"] = round(est["rafaga_kmh"])
    return est


def valores_atipicos(estaciones, campo, tolerancia, radio_km=100, minimo_vecinas=3):
    """Ids de las estaciones cuyo `campo` se aparta más de `tolerancia` de la mediana
    de sus vecinas (sensores rotos: -30 °C en una noche templada, humedad 10 %...)."""
    grilla = {}
    for e in estaciones:
        if e[campo] is not None:
            grilla.setdefault((math.floor(e["lat"]), math.floor(e["lon"])), []).append(e)
    atipicas = set()
    for e in estaciones:
        if e[campo] is None:
            continue
        ci, cj = math.floor(e["lat"]), math.floor(e["lon"])
        vecinas = sorted(
            o[campo] for di in (-1, 0, 1) for dj in (-1, 0, 1) for o in grilla.get((ci + di, cj + dj), ())
            if o is not e and distancia_km(e["lat"], e["lon"], o["lat"], o["lon"]) <= radio_km
        )
        if len(vecinas) >= minimo_vecinas and abs(e[campo] - vecinas[len(vecinas) // 2]) > tolerancia:
            atipicas.add(e["id"])
    return atipicas


_A, _B = 17.625, 243.04  # constantes de Magnus


def humedad_desde_rocio(t, td):
    if t is None or td is None:
        return None
    return round(100 * math.exp(_A * td / (_B + td) - _A * t / (_B + t)))


def rocio_desde_humedad(t, hr):
    if t is None or not hr:
        return None
    g = math.log(hr / 100) + _A * t / (_B + t)
    return round(_B * g / (_A - g), 1)


def nudos_a_kmh(v):
    return None if v is None else round(v * 1.852)


def ms_a_kmh(v):
    return None if v is None else round(v * 3.6, 1)


def presion_mar(hpa):
    """Para presiones que deberían estar reducidas al nivel del mar: fuera de rango es un error."""
    return hpa if hpa is not None and 960 <= hpa <= 1060 else None


def distancia_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
