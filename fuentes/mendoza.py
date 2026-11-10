"""Fuente: Mendoza, red agrometeorológica de la Dirección de Agricultura y
Contingencias Climáticas (agrometeo.mendoza.gov.ar).

Usa el feed público que el propio sitio indica para consumo externo.
"""
from .comun import descargar_json, estacion, hora_local_a_utc, ms_a_kmh, numero

ID = "mendoza"
NOMBRE = "Mendoza (DACC)"
SITIO = "https://agrometeo.mendoza.gov.ar/"
MINUTOS = 10

URL = "https://agrometeo.mendoza.gov.ar/api/todas_instantaneas.json"


def obtener():
    salida = []
    for e in descargar_json(URL):
        lat, lon = numero(e.get("lat")), numero(e.get("lng"))
        if lat is None or lon is None:
            continue
        salida.append(estacion(
            id=f"mendoza:{e.get('estacion')}",
            nombre=f"{e.get('Nombre')} (DACC Mendoza)",
            fuente=ID,
            lat=lat, lon=lon,
            altura_m=numero(e.get("Altura")),
            hora_utc=hora_local_a_utc(e.get("fechaIngles"), "%Y-%m-%d %H:%M:%S"),
            temp_c=numero(e.get("tempAire")),
            humedad_pct=numero(e.get("humedad")),  # 999.9 = sin dato, lo descarta limpiar()
            rocio_c=numero(e.get("puntoRocio")),
            viento_dir_grados=numero(e.get("direccionViento")),
            viento_kmh=ms_a_kmh(numero(e.get("velocidadViento"))),
            # No está documentado; crece a lo largo de la mañana y no baja: acumulada del día.
            precip_hoy_mm=numero(e.get("precipitacion")),
        ))
    return salida
