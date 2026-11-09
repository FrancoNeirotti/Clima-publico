"""Fuente: SMN, archivo "Estado del tiempo presente" (datos abiertos, se actualiza cada hora).

El archivo de tiempo presente trae el nombre de cada estación pero no sus
coordenadas, así que se cruzan por nombre con el listado de estaciones del SMN.
Las que no se pueden ubicar quedan en `sin_ubicar` y se pueden cargar a mano
en smn_coordenadas_manual.json:  {"Nombre tal cual aparece": [lat, lon]}
o apuntando a un nombre del listado:  {"Nombre tal cual aparece": "NOMBRE EN EL LISTADO"}
"""
import io
import json
import re
import time
import unicodedata
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .comun import descargar, estacion, numero, rocio_desde_humedad

ID = "smn"
NOMBRE = "SMN (tiempo presente)"
SITIO = "https://www.smn.gob.ar/"

URL_TIEMPO = "https://ssl.smn.gob.ar/dpd/zipopendata.php?dato=tiepre"
URL_ESTACIONES = "https://ssl.smn.gob.ar/dpd/zipopendata.php?dato=estaciones"
ARCHIVO_MANUAL = Path(__file__).with_name("smn_coordenadas_manual.json")

HORA_ARGENTINA = timezone(timedelta(hours=-3))
MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}
MESES["setiembre"] = 9
RUMBOS = {
    "norte": 0, "nordeste": 45, "noreste": 45, "este": 90, "sudeste": 135,
    "sureste": 135, "sur": 180, "sudoeste": 225, "suroeste": 225,
    "oeste": 270, "noroeste": 315,
}
PALABRAS_VACIAS = {"AERO", "AEROPUERTO", "AP", "OBSERVATORIO", "OBS", "DE", "DEL",
                   "LA", "EL", "LOS", "LAS", "Y", "BASE"}

sin_ubicar = []          # nombres que no se pudieron ubicar en la última corrida
_estaciones = {"momento": 0, "lista": []}


def _a_texto(contenido):
    """Acepta un zip o texto plano; prueba UTF-8 y después Latin-1."""
    if zipfile.is_zipfile(io.BytesIO(contenido)):
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            archivos = [n for n in z.namelist() if not n.endswith("/")]
            contenido = z.read(archivos[0])
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("latin-1")


def _tokens(texto, todas=False):
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto)
                         if not unicodedata.combining(c))
    palabras = re.sub(r"[^A-Z0-9 ]", " ", sin_tildes.upper()).split()
    return {p for p in palabras if todas or p not in PALABRAS_VACIAS}


# Una fila termina en: lat_grados lat_min lon_grados lon_min altura número [OACI]
_FILA_ESTACION = re.compile(
    r"^(?P<texto>.*?\S)\s+(?P<latg>-?\d{1,2})\s+(?P<latm>\d{1,2})\s+"
    r"(?P<long>-?\d{1,3})\s+(?P<lonm>\d{1,2})\s+(?P<alt>-?\d+)\s+(?P<nro>\d{5})"
    r"(?:\s+(?P<oaci>[A-Z]{4}))?\s*$"
)


def _grados(g, m):
    g, m = int(g), int(m)
    return g - m / 60 if g < 0 else g + m / 60


def listado_estaciones():
    """Listado oficial de estaciones del SMN (cambia poco: se descarga una vez por día)."""
    if time.time() - _estaciones["momento"] < 24 * 3600 and _estaciones["lista"]:
        return _estaciones["lista"]
    lista = []
    for linea in _a_texto(descargar(URL_ESTACIONES)).splitlines():
        fila = _FILA_ESTACION.match(linea)
        if not fila:
            continue
        # Nombre y provincia vienen en columnas separadas por varios espacios.
        partes = re.split(r"\s{2,}", fila["texto"], maxsplit=1)
        nombre, provincia = partes[0], (partes[1] if len(partes) > 1 else "")
        lista.append({
            "nombre": nombre.strip(),
            "provincia": provincia.strip(),
            "tokens": _tokens(nombre),
            "tokens_todos": _tokens(nombre, todas=True),
            "lat": _grados(fila["latg"], fila["latm"]),
            "lon": _grados(fila["long"], fila["lonm"]),
            "altura": numero(fila["alt"]),
            "nro": fila["nro"],
            "oaci": fila["oaci"],
        })
    _estaciones.update(momento=time.time(), lista=lista)
    return lista


def _manual():
    try:
        return json.loads(ARCHIVO_MANUAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ubicar(nombre, listado, manual):
    if nombre in manual:
        valor = manual[nombre]
        if isinstance(valor, str):  # nombre tal cual figura en el listado del SMN
            return next((e for e in listado if e["nombre"] == valor), None)
        lat, lon = valor[:2]
        return {"lat": lat, "lon": lon, "altura": None}
    buscados = _tokens(nombre)
    todos = _tokens(nombre, todas=True)
    if not buscados:
        return None
    candidatos = []
    for e in listado:
        comunes = len(buscados & e["tokens"])
        if comunes:
            # Desempate: parecido con todas las palabras ("Córdoba Observatorio" vs
            # "Córdoba Aero") y, si sigue igual, el aeropuerto, que es el nombre corto del SMN.
            parecido = len(todos & e["tokens_todos"]) / len(todos | e["tokens_todos"])
            clave = (round(comunes / len(buscados), 3), round(parecido, 3), "AERO" in e["tokens_todos"])
            candidatos.append((clave, e))
    if not candidatos:
        return None
    candidatos.sort(key=lambda c: c[0], reverse=True)
    mejor = candidatos[0]
    if mejor[0][0] < 0.6:
        return None
    if len(candidatos) > 1 and candidatos[1][0] == mejor[0]:
        return None  # empate: mejor no adivinar
    return mejor[1]


def _hora_utc(fecha, hora):
    try:
        dia, mes, anio = fecha.split("-")
        h, mi = hora.split(":")
        local = datetime(int(anio), MESES[mes.strip().lower()], int(dia),
                         int(h), int(mi), tzinfo=HORA_ARGENTINA)
        return local.astimezone(timezone.utc).isoformat()
    except (ValueError, KeyError):
        return None


def _viento(texto):
    t = texto.strip().lower()
    if not t or "calma" in t:
        return None, (0 if t else None)
    m = re.match(r"([a-záéíóú]+)\s+(\d+)", t)
    if not m:
        return None, None
    return RUMBOS.get(m[1]), numero(m[2])  # el SMN informa km/h


def obtener():
    listado = listado_estaciones()
    manual = _manual()
    salida, faltan = [], []
    for linea in _a_texto(descargar(URL_TIEMPO)).splitlines():
        partes = [p.strip() for p in linea.split(";")]
        if len(partes) < 10:
            continue
        nombre, fecha, hora, estado, visib, temp, sens, hum, viento, pres = partes[:10]
        lugar = _ubicar(nombre, listado, manual)
        if lugar is None:
            faltan.append(nombre)
            continue
        t, hr = numero(temp), numero(hum)
        direccion, velocidad = _viento(viento)
        vis_km = numero(visib.lower().replace("km", ""))
        salida.append(estacion(
            id=f"smn:{nombre}",
            nombre=nombre,
            fuente=ID,
            lat=lugar["lat"], lon=lugar["lon"],
            altura_m=lugar["altura"],
            hora_utc=_hora_utc(fecha, hora),
            temp_c=t,
            humedad_pct=hr,
            rocio_c=rocio_desde_humedad(t, hr),
            sensacion_c=numero(sens),
            viento_dir_grados=direccion,
            viento_kmh=velocidad,
            presion_hpa=numero(pres.split("/")[0]),
            visibilidad=f"{vis_km:g} km" if vis_km is not None else None,
            cielo=estado or None,
            crudo=linea.strip(),
        ))
    sin_ubicar[:] = faltan
    return salida
