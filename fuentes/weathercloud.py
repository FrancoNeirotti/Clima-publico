"""Fuente: Weathercloud (weathercloud.net), plataforma donde particulares y
empresas publican sus estaciones.

Un solo pedido trae la última lectura de todas las estaciones del mundo
(~12 MB); se filtran las que están en la Argentina y figuran en línea. Esa
lista no trae la hora de cada lectura: las estaciones "en línea" informaron
en los últimos minutos, así que se usa la hora de la descarga.
"""
from datetime import datetime, timezone

from .comun import descargar_json, en_argentina, estacion, numero, presion_mar

ID = "weathercloud"
NOMBRE = "Weathercloud"
SITIO = "https://app.weathercloud.net/"
TIPO = "privada"
MINUTOS = 15

URL = "https://app.weathercloud.net/map/bgdevices"
CABECERAS = {"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}
EN_LINEA = 2
# Posiciones de cada lectura: código, nombre, lat, lon, estado, webcam,
# temp×10, humedad, presión×10, viento (m/s)×10, dirección, lluvia del día (mm)×10...
CODIGO, TITULO, LAT, LON, ESTADO, TEMP, HUMEDAD, PRESION, VIENTO, DIRECCION = 0, 1, 2, 3, 4, 6, 7, 8, 9, 10
LLUVIA, INTENSIDAD = 11, 12  # décimas de mm y de mm/h


def _decimos(valor):
    v = numero(valor)
    return None if v is None else v / 10


def obtener():
    datos = descargar_json(URL, timeout=180, datos=b"user=", cabeceras=CABECERAS)
    ahora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    salida = []
    for d in datos.get("devices") or []:
        lat, lon = numero(d[LAT]), numero(d[LON])
        if (len(d) <= DIRECCION or d[ESTADO] != EN_LINEA or lat is None or lon is None
                or not en_argentina(lat, lon) or _decimos(d[TEMP]) is None):
            continue
        viento = _decimos(d[VIENTO])
        salida.append(estacion(
            id=f"weathercloud:{d[CODIGO]}",
            # La página pública usa el código (base 36) pasado a decimal con 10 dígitos.
            enlace=f"https://app.weathercloud.net/d{int(d[CODIGO], 36):010d}",
            nombre=f"{(d[TITULO] or d[CODIGO]).strip()} (Weathercloud)",
            fuente=ID,
            lat=lat, lon=lon,
            hora_utc=ahora,
            temp_c=_decimos(d[TEMP]),
            humedad_pct=numero(d[HUMEDAD]),
            presion_hpa=presion_mar(_decimos(d[PRESION])),
            viento_kmh=None if viento is None else round(viento * 3.6, 1),
            viento_dir_grados=numero(d[DIRECCION]) if viento else None,
            precip_hoy_mm=_decimos(d[LLUVIA]) if len(d) > LLUVIA else None,
            precip_intensidad_mmh=_decimos(d[INTENSIDAD]) if len(d) > INTENSIDAD else None,
        ))
    return salida
