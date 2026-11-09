"""Fuente: Sensor.Community (ex luftdaten), red ciudadana de sensores de
calidad del aire, muchos con temperatura, humedad y presión. Datos abiertos
(licencia Open Data Commons), con filtro por país.

Son sensores baratos (DHT22, BME280...): se descartan los de interior y las
lecturas típicas de sensor roto (0 °C y 0 %, humedad trabada en 99,9 %).
"""
from datetime import datetime, timezone

from .comun import descargar_json, estacion, numero

ID = "sensor_community"
NOMBRE = "Sensor.Community"
SITIO = "https://maps.sensor.community/"
TIPO = "privada"
MINUTOS = 10

URL = "https://data.sensor.community/airrohr/v1/filter/country=AR"


def _hora(texto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def obtener():
    por_lugar = {}  # un mismo lugar puede tener varios sensores (p. ej. DHT22 + BME280)
    for r in descargar_json(URL, timeout=60):
        lugar = r.get("location") or {}
        valores = {v.get("value_type"): numero(v.get("value")) for v in r.get("sensordatavalues") or []}
        if lugar.get("indoor") or valores.get("temperature") is None:
            continue
        temp, humedad = valores.get("temperature"), valores.get("humidity")
        if (temp == 0 and not humedad) or (humedad is not None and humedad >= 99.9):
            continue
        presion = valores.get("pressure_at_sealevel")
        if presion is not None and presion > 2000:  # algunos informan en Pa
            presion /= 100
        previo = por_lugar.get(lugar.get("id"))
        hora = _hora(r.get("timestamp"))
        if previo and (previo["hora_utc"] or "") >= (hora or ""):
            continue
        por_lugar[lugar.get("id")] = estacion(
            id=f"sensor_community:{lugar.get('id')}",
            enlace=f"https://maps.sensor.community/#15/{lugar.get('latitude')}/{lugar.get('longitude')}",
            nombre=f"Sensor {lugar.get('id')} ({(r.get('sensor') or {}).get('sensor_type', {}).get('name', '')}, Sensor.Community)",
            fuente=ID,
            lat=numero(lugar.get("latitude")), lon=numero(lugar.get("longitude")),
            altura_m=numero(lugar.get("altitude")),
            hora_utc=hora,
            temp_c=temp,
            humedad_pct=humedad,
            presion_hpa=presion,
        )
    return [e for e in por_lugar.values() if e["lat"] is not None and e["lon"] is not None]
