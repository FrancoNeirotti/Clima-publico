"""Fuente: Bolsa de Cereales y Productos de Bahía Blanca, red de estaciones
(sudoeste bonaerense y La Pampa, info.bcp.org.ar).

Los datos vienen como asignaciones JavaScript dentro de la página del mapa.
"""
import html
import re

from .comun import descargar, estacion, hora_local_a_utc, numero, primer_numero

ID = "bcp"
NOMBRE = "Bahía Blanca (BCP)"
SITIO = "https://info.bcp.org.ar/Estaciones/MapaG_NvoBCP.asp"
MINUTOS = 10

URL = "https://info.bcp.org.ar/Estaciones/MapaG_NvoBCP.asp"
# Índices de jsDatos[estación][sensor][0], según las constantes de la página.
LAT, LON, TEMP, HUMEDAD, ROCIO, PRESION, DIRECCION, VIENTO, RAFAGA, ACTUALIZADA = 0, 1, 5, 14, 15, 16, 18, 19, 20, 25
LLUVIA_DIA, LLUVIA_7D, LLUVIA_MES, LLUVIA_ANIO = 10, 11, 12, 13

_TITULO = re.compile(r"titleEstacion\[(\d+)\]\s*=\s*'([^']*)'")
_HABILITADA = re.compile(r"habilEstacion\[(\d+)\]\s*=\s*(\d+)")
_DATO = re.compile(r"jsDatos\[(\d+)\]\[(\d+)\]\[0\]\s*=\s*(?:'([^']*)'|(-?[\d.]+))")


def _texto(valor):
    return html.unescape(re.sub(r"<[^>]+>", "", valor or "")).strip()


def _valor(datos, sensor):
    texto = datos.get(sensor)
    return None if texto in (None, "N/D", "N/A", "N/C") else primer_numero(texto)


def obtener():
    pagina = descargar(URL, timeout=60).decode("latin-1")
    titulos = {int(i): _texto(t) for i, t in _TITULO.findall(pagina)}
    habilitadas = {int(i) for i, h in _HABILITADA.findall(pagina) if h == "1"}
    datos = {}
    for i, sensor, texto, num in _DATO.findall(pagina):
        datos.setdefault(int(i), {})[int(sensor)] = _texto(texto) if texto else num

    salida = []
    for i, d in datos.items():
        lat, lon = numero(d.get(LAT)), numero(d.get(LON))
        if i not in habilitadas or lat is None or lon is None:
            continue
        nombre = re.sub(r"^Estaci[oó]n\s*\d+\s*-\s*", "", titulos.get(i, str(i)))
        salida.append(estacion(
            id=f"bcp:{i}",
            nombre=f"{nombre} (BCP)",
            fuente=ID,
            lat=lat, lon=lon,
            hora_utc=hora_local_a_utc(d.get(ACTUALIZADA), "%d/%m/%Y %H:%M:%S"),
            temp_c=_valor(d, TEMP),
            humedad_pct=_valor(d, HUMEDAD),
            rocio_c=_valor(d, ROCIO),
            presion_hpa=_valor(d, PRESION),
            viento_dir_grados=_valor(d, DIRECCION),
            viento_kmh=_valor(d, VIENTO),
            rafaga_kmh=_valor(d, RAFAGA),
            precip_hoy_mm=_valor(d, LLUVIA_DIA),
            precip_7d_mm=_valor(d, LLUVIA_7D),
            precip_mes_mm=_valor(d, LLUVIA_MES),
            precip_anio_mm=_valor(d, LLUVIA_ANIO),
        ))
    return salida
