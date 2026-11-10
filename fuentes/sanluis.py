"""Fuente: San Luis, Red de Estaciones Meteorológicas (REM, clima.sanluis.gob.ar).

El mapa del sitio trae en un solo pedido ubicación, hora y temperatura de
todas las estaciones; humedad, viento y presión salen de la página de cada una.
"""
import html
import json
import re

from .comun import descargar, en_paralelo, estacion, ms_a_iso, numero, primer_numero

ID = "sanluis"
NOMBRE = "San Luis (REM)"
SITIO = "https://clima.sanluis.gob.ar/"
MINUTOS = 10

URL_MAPA = "https://clima.sanluis.gob.ar/InfoEstaciones.aspx"
URL_ESTACION = "https://clima.sanluis.gob.ar/Estacion.aspx?Estacion={id}"
_ETIQUETA = re.compile(r'id="ContentPlaceHolder1_(lbl\w+)"[^>]*>([^<]*)<')


def _detalle(id_estacion):
    pagina = descargar(URL_ESTACION.format(id=id_estacion)).decode("utf-8", "replace")
    return {k: html.unescape(v).strip() for k, v in _ETIQUETA.findall(pagina)}


def obtener():
    texto = descargar(URL_MAPA).decode("cp1252")
    texto = re.sub(r"new Date\((-?\d+)\)", r"\1", texto[texto.index("["):].rstrip().rstrip(";"))
    filas = [f for f in json.loads(texto) if f[7] == "REM" and f[5] is not None]
    detalles = en_paralelo(lambda f: _detalle(f[0]), filas, hilos=6)

    salida = []
    for f, d in zip(filas, detalles):
        d = d or {}
        direccion = d.get("lblDireccionViento", "")
        salida.append(estacion(
            id=f"sanluis:{f[0]}",
            enlace=URL_ESTACION.format(id=f[0]),
            nombre=f"{f[1]} (REM San Luis)",
            fuente=ID,
            lat=f[2], lon=f[3],
            altura_m=primer_numero(d.get("lblAltura")) or None,
            hora_utc=ms_a_iso(f[4]),
            temp_c=numero(f[5]),
            humedad_pct=primer_numero(d.get("lblHumedad")),
            viento_kmh=primer_numero(d.get("lblVelocidadViento")),
            viento_dir_grados=primer_numero(direccion.split("/")[-1]) if "/" in direccion else None,
            presion_hpa=primer_numero(d.get("lblPresion")),
            precip_1h_mm=primer_numero(d.get("lblPrecipitacion")),  # "Última hora"
            precip_24h_mm=primer_numero(d.get("lblPrecipitacion24h")),
        ))
    return salida
