"""Fuente: EEAOC, red agrometeorológica de la Estación Experimental
Agroindustrial Obispo Colombres (Tucumán y alrededores, agromet.eeaoc.gob.ar).
"""
from .comun import descargar_json, estacion, hora_local_a_utc, numero, rumbo_a_grados

ID = "eeaoc"
NOMBRE = "Tucumán (EEAOC)"
SITIO = "https://agromet.eeaoc.gob.ar/"
MINUTOS = 10

URL_DATOS = "https://agromet.eeaoc.gob.ar/services/datos-online.php"
# datos-online.php trae la dirección del viento siempre en 0; acá viene como texto.
URL_ESTACIONES = "https://agromet.eeaoc.gob.ar/services/estaciones.php"


def obtener():
    datos = descargar_json(URL_DATOS).get("data") or []
    try:
        lista = descargar_json(URL_ESTACIONES)
        if isinstance(lista, dict):
            lista = lista.get("data") or []
        rumbos = {str(e.get("Identificacion")): e.get("direc") for e in lista}
    except Exception:  # sin rumbos igual se muestran los demás datos
        rumbos = {}
    salida = []
    for e in datos:
        lat, lon = numero(e.get("lat")), numero(e.get("lon"))
        if lat is None or lon is None:
            continue
        ident = str(e.get("identificacion"))
        viento = numero(e.get("viento_medio"))
        salida.append(estacion(
            id=f"eeaoc:{ident}",
            nombre=f"{e.get('nombre')} (EEAOC)",
            fuente=ID,
            lat=lat, lon=lon,
            altura_m=numero(e.get("alt")),
            hora_utc=hora_local_a_utc(e.get("fecha_i"), "%Y-%m-%d %H:%M:%S"),
            temp_c=numero(e.get("temp_af")),
            humedad_pct=numero(e.get("hum_af")),
            presion_hpa=numero(e.get("presion")) or None,
            viento_kmh=viento,
            viento_dir_grados=rumbo_a_grados(rumbos.get(ident)) if viento else None,
            rafaga_kmh=numero(e.get("viento_max")) or None,
            precip_hoy_mm=numero(e.get("rr_dia")),
            precip_mes_mm=numero(e.get("rr_mes")),
        ))
    return salida
