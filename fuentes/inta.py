"""Fuente: INTA, red de estaciones automáticas (SIGA, siga.inta.gob.ar).

El mismo listado que usa el mapa del SIGA trae la última temperatura y humedad
de las estaciones que transmiten en tiempo real.
"""
import re

from .comun import descargar, descargar_json, estacion, hora_local_a_utc, numero

ID = "inta"
NOMBRE = "INTA (estaciones automáticas)"
SITIO = "https://siga.inta.gob.ar/"
MINUTOS = 10

# El nombre del .php cambia cada tanto; el sitio lo publica en urlserver.js.
URL_CONFIG = "https://siga.inta.gob.ar/js/urlserver.js"
URL_BASE = "https://siga.inta.gob.ar/"


def _url_estaciones():
    config = descargar(URL_CONFIG).decode("utf-8", "replace")
    m = re.search(r"^\s*var URL_MYSQL_ESTACION_AUTOMATICA\s*=\s*'([^']+)'", config, re.MULTILINE)
    if not m:
        raise ValueError("no se encontró la URL de estaciones en urlserver.js")
    return URL_BASE + m[1]


def _hora(texto):
    """'2026-11-08T21:20:00Z[UTC]': aunque dice UTC, es la hora local de Argentina."""
    return hora_local_a_utc((texto or "")[:19], "%Y-%m-%dT%H:%M:%S")


def obtener():
    salida = []
    for e in descargar_json(_url_estaciones(), timeout=60):
        lat, lon = numero(e.get("latitud")), numero(e.get("longitud"))
        if (lat is None or lon is None or e.get("provincia") == "Sin asignar"
                or e.get("temperaturaActual") is None):
            continue
        if e.get("temperaturaActual") == 0 and not e.get("humedad"):
            continue  # 0 °C exacto y sin humedad: casi seguro un sensor sin datos
        salida.append(estacion(
            id=f"inta:{e['id']}",
            nombre=f"{e.get('nombre') or e.get('localidad')} (INTA)",
            fuente=ID,
            lat=lat, lon=lon,
            altura_m=numero(e.get("altura")),
            hora_utc=_hora(e.get("ultimoRegistro")),
            temp_c=numero(e.get("temperaturaActual")),
            humedad_pct=numero(e.get("humedad")),
            # El SIGA la suma como la lluvia del día de ultimoRegistro.
            precip_hoy_mm=numero(e.get("precipitacion")),
            crudo=(f"Mín. {e.get('temperaturaMinima')} °C, máx. {e.get('temperaturaMaxima')} °C, "
                   f"lluvia {e.get('precipitacion')} mm, "
                   f"lluvia de los últimos 4 días {e.get('precipitacionAcumulada4dias')} mm"),
        ))
    return salida
