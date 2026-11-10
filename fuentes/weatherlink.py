"""Fuente: estaciones Davis que sus dueños publican en el mapa de WeatherLink
(weatherlink.com/map): productores, acopios, terminales portuarias, clubes...

El índice mundial de estaciones pesa unos 8 MB: se baja una vez por día y se
filtra por el contorno de la Argentina. Los datos se piden estación por
estación (más de mil), por eso esta fuente se actualiza cada hora. Es un
servicio no documentado: no conviene bajar ese intervalo.
"""
from .comun import (cacheado, descargar_json, en_argentina, en_paralelo, estacion, ms_a_iso,
                    numero, presion_mar, pulgadas_a_mm)

ID = "weatherlink"
NOMBRE = "WeatherLink (Davis)"
SITIO = "https://www.weatherlink.com/map"
TIPO = "privada"
MINUTOS = 60

URL_INDICE = "https://www.weatherlink.com/map/data"
URL_ESTACION = "https://www.weatherlink.com/map/data/station/{id}?aqiSchemeId=10&woodsmokeEnabled=false"
CABECERAS = {"Referer": "https://www.weatherlink.com/map", "X-Requested-With": "XMLHttpRequest"}


def _descargar_ids():
    todas = descargar_json(URL_INDICE, timeout=120, cabeceras=CABECERAS)
    # tb = -1 marca estaciones que dejaron de transmitir.
    return [e["id"] for e in todas
            if numero(e.get("lat")) is not None and numero(e.get("lng")) is not None
            and e.get("tb") != -1 and en_argentina(e["lat"], e["lng"])]


def _ids_en_zona():
    return cacheado("weatherlink_ids", 24, _descargar_ids)


def _texto(s):
    """Los nombres llegan con doble codificación ('NicolÃ¡s')."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeError, AttributeError):
        return s


def _f_a_c(f):
    return None if f is None else round((f - 32) / 1.8, 1)


def obtener():
    ids = _ids_en_zona()
    datos = en_paralelo(lambda i: descargar_json(URL_ESTACION.format(id=i), cabeceras=CABECERAS), ids, hilos=4)
    salida = []
    for id_estacion, d in zip(ids, datos):
        if not d or numero(d.get("lat")) is None or numero(d.get("temperature")) is None:
            continue
        viento = numero(d.get("windSpeed"))
        barometro = numero(d.get("barometer"))
        unidad_temp = (d.get("temperatureUnit") or "").upper()
        temp = numero(d.get("temperature"))
        lluvia = numero(d.get("dailyRain"))
        if lluvia is not None and (d.get("rainUnit") or "").strip().lower() == "in":
            lluvia = pulgadas_a_mm(lluvia)
        salida.append(estacion(
            id=f"weatherlink:{id_estacion}",
            nombre=f"{_texto(d.get('sStation') or id_estacion)} (WeatherLink)",
            fuente=ID,
            lat=numero(d["lat"]), lon=numero(d["lng"]),
            hora_utc=ms_a_iso(numero(d.get("lastTimestamp")) * 1000) if d.get("lastTimestamp") else None,
            temp_c=_f_a_c(temp) if "F" in unidad_temp else temp,
            humedad_pct=numero(d.get("humidity")),
            viento_kmh=None if viento is None else (
                viento * 1.609 if "mph" in (d.get("windSpeedUnit") or "") else viento),
            viento_dir_grados=numero(d.get("windDirection")) if viento else None,
            presion_hpa=None if barometro is None else presion_mar(round(
                barometro * 33.8639 if "in" in (d.get("barometerUnit") or "") else barometro, 1)),
            precip_hoy_mm=lluvia,  # dailyRain: la consola Davis la reinicia a medianoche
        ))
    return salida
