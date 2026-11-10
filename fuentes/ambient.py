"""Fuente: Ambient Weather (ambientweather.net), estaciones que sus dueños
dejan públicas en el mapa de la plataforma (muchas Ecowitt/WS-2902).

El mapa devuelve hasta 300 estaciones por rectángulo con su última lectura;
donde se llega a ese tope, el rectángulo se divide en cuatro.
"""
from urllib.parse import urlencode

from .comun import descargar_json, en_argentina, estacion, ms_a_iso, numero, presion_mar, pulgadas_a_mm

ID = "ambient"
NOMBRE = "Ambient Weather"
SITIO = "https://ambientweather.net/"
TIPO = "privada"
MINUTOS = 15

URL = "https://lightning.ambientweather.net/devices?"
TOPE = 300
RECTANGULO_PAIS = (-55.5, -73.6, -21.7, -53.6)  # sur, oeste, norte, este


def _f_a_c(f):
    return None if f is None else round((f - 32) / 1.8, 1)


def _mph(v):
    return None if v is None else round(v * 1.609, 1)


def _pedir(sur, oeste, norte, este, profundidad=0):
    params = {"$publicBox[0][0]": oeste, "$publicBox[0][1]": sur,
              "$publicBox[1][0]": este, "$publicBox[1][1]": norte, "$limit": 500}
    respuesta = descargar_json(URL + urlencode(params), timeout=90)
    estaciones = respuesta.get("data", respuesta) if isinstance(respuesta, dict) else respuesta
    if len(estaciones) >= TOPE and profundidad < 6:
        lat_m, lon_m = (sur + norte) / 2, (oeste + este) / 2
        estaciones = []
        for s, n in ((sur, lat_m), (lat_m, norte)):
            for o, e in ((oeste, lon_m), (lon_m, este)):
                estaciones += _pedir(s, o, n, e, profundidad + 1)
    return estaciones


def _es_argentina(info, lat, lon):
    componentes = ((info.get("coords") or {}).get("address_components") or [])
    paises = [c.get("short_name") for c in componentes if "country" in (c.get("types") or [])]
    return paises == ["AR"] if paises else en_argentina(lat, lon)


def obtener():
    vistas, salida = set(), []
    for d in _pedir(*RECTANGULO_PAIS):
        info, ultimo = d.get("info") or {}, d.get("lastData") or {}
        coords = ((info.get("coords") or {}).get("coords") or {})
        lat, lon = numero(coords.get("lat")), numero(coords.get("lon"))
        clave = d.get("_id") or d.get("macAddress")
        if (clave in vistas or lat is None or lon is None or numero(ultimo.get("tempf")) is None
                or not _es_argentina(info, lat, lon)):
            continue
        vistas.add(clave)
        viento = _mph(numero(ultimo.get("windspeedmph")))
        presion = numero(ultimo.get("baromrelin"))
        lugar = ((info.get("coords") or {}).get("location") or "").strip()
        nombre = (info.get("name") or "").strip() or lugar or clave
        salida.append(estacion(
            id=f"ambient:{clave}",
            nombre=f"{nombre}{f' – {lugar}' if lugar and lugar != nombre else ''} (Ambient)",
            fuente=ID,
            lat=lat, lon=lon,
            altura_m=numero((info.get("coords") or {}).get("elevation")),
            hora_utc=ms_a_iso(numero(ultimo.get("dateutc"))),
            temp_c=_f_a_c(numero(ultimo.get("tempf"))),
            humedad_pct=numero(ultimo.get("humidity")),
            rocio_c=_f_a_c(numero(ultimo.get("dewPoint"))),
            sensacion_c=_f_a_c(numero(ultimo.get("feelsLike"))),
            viento_kmh=viento,
            viento_dir_grados=numero(ultimo.get("winddir")) if viento else None,
            rafaga_kmh=_mph(numero(ultimo.get("windgustmph"))) or None,
            presion_hpa=None if presion is None else presion_mar(round(presion * 33.8639, 1)),
            # hourlyrainin es intensidad (pulgadas/hora), no acumulado.
            precip_hoy_mm=pulgadas_a_mm(numero(ultimo.get("dailyrainin"))),
            precip_24h_mm=pulgadas_a_mm(numero(ultimo.get("24hourrainin"))),
            precip_intensidad_mmh=pulgadas_a_mm(numero(ultimo.get("hourlyrainin"))),
            precip_evento_mm=pulgadas_a_mm(numero(ultimo.get("eventrainin"))),
            precip_semana_mm=pulgadas_a_mm(numero(ultimo.get("weeklyrainin"))),
            precip_mes_mm=pulgadas_a_mm(numero(ultimo.get("monthlyrainin"))),
            precip_anio_mm=pulgadas_a_mm(numero(ultimo.get("yearlyrainin"))),
            precip_ultima_utc=ms_a_iso(ultimo.get("lastRain")) if isinstance(ultimo.get("lastRain"), (int, float)) else None,
        ))
    return salida
