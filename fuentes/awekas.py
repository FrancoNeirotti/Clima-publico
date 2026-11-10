"""Fuente: AWEKAS (awekas.at), red de estaciones particulares.

El mapa pide una sesión anónima (la API la entrega a cualquiera, sin
registro), lista las estaciones con temperatura de las últimas 3 horas y
después se lee cada estación, que trae la hora de la observación.
"""
from .comun import (descargar_json, en_argentina, en_paralelo, estacion, ms_a_iso, numero,
                    presion_mar)

ID = "awekas"
NOMBRE = "AWEKAS"
SITIO = "https://www.awekas.at/"
TIPO = "privada"
MINUTOS = 15

BASE = "https://app.awekas.at/map/v2/api/"
URL_SESION = BASE + "session.php"
URL_PUNTOS = BASE + "mappoints.php?p=temp&t=now&a=180&n=-21.7&e=-53.6&s=-55.5&w=-73.6&plt=web"
URL_ESTACION = BASE + "station.php?id={id}&plt=web&t=now"

_sesion = {"uuid": None}


def _cabeceras():
    if not _sesion["uuid"]:
        _sesion["uuid"] = descargar_json(URL_SESION)["data"]["uuid"]
    return {"Authentication": _sesion["uuid"]}


def _puntos():
    respuesta = descargar_json(URL_PUNTOS, cabeceras=_cabeceras())
    if respuesta.get("error"):  # sesión vencida: se pide otra
        _sesion["uuid"] = None
        respuesta = descargar_json(URL_PUNTOS, cabeceras=_cabeceras())
    return respuesta.get("data") or []


def obtener():
    puntos = [p for p in _puntos() if en_argentina(p["lat"], p["lon"])]
    cabeceras = _cabeceras()
    detalles = en_paralelo(lambda p: descargar_json(URL_ESTACION.format(id=p["id"]), cabeceras=cabeceras)["data"],
                           puntos, hilos=4)
    salida = []
    for p, d in zip(puntos, detalles):
        if not d:
            continue
        s = d.get("sensors") or {}
        viento = numero(s.get("wind"))
        salida.append(estacion(
            id=f"awekas:{p['id']}",
            enlace=f"https://www.awekas.at/es/instrument.php?id={p['id']}",
            nombre=f"{d.get('name') or p['id']} (AWEKAS)",
            fuente=ID,
            lat=p["lat"], lon=p["lon"],
            altura_m=numero(d.get("altitude")),
            hora_utc=ms_a_iso(d["timestamp"] * 1000) if d.get("timestamp") else None,
            temp_c=numero(s.get("temp")),
            humedad_pct=numero(s.get("hum")),
            rocio_c=numero(s.get("dew")),
            presion_hpa=presion_mar(numero(s.get("baro"))),
            viento_kmh=viento,
            viento_dir_grados=numero(s.get("wind_dir")) if viento else None,
            rafaga_kmh=numero(s.get("gust")) or None,
            precip_hoy_mm=numero(s.get("rain")),  # AWEKAS la reinicia a medianoche
        ))
    return salida
