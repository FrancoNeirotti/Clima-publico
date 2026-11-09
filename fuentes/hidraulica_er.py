"""Fuente: Entre Ríos, estaciones meteorológicas automáticas de la Dirección
de Hidráulica (www.hidraulica.gob.ar/ema.php).

Cada estación publica el archivo de texto mensual de WeatherLink; se leen solo
la cabecera y las últimas líneas. Las coordenadas salen de la ficha de cada
estación y se guardan una semana.
"""
import re

from .comun import (cacheado, descargar, en_paralelo, estacion, hora_local_a_utc, numero,
                    rumbo_a_grados)

ID = "hidraulica_er"
NOMBRE = "Entre Ríos (Hidráulica)"
SITIO = "https://www.hidraulica.gob.ar/ema.php"
MINUTOS = 10

URL_ARCHIVO = "https://www.hidraulica.gob.ar/ema/ema-{id}/downld08.txt"
URL_FICHA = "https://www.hidraulica.gob.ar/ema.php?station={id}&inf=datos"
ESTACIONES = {
    "basavilbaso": "Basavilbaso", "bovril": "Bovril", "ceibas": "Ceibas",
    "curuguay": "Concepción del Uruguay", "concordia": "Concordia", "feliciano": "Feliciano",
    "racedo": "General Racedo", "gualeguay": "Gualeguay", "gualeguaychu": "Gualeguaychú",
    "lapaz": "La Paz", "larroque": "Larroque", "loscharruas": "Los Charrúas", "macia": "Maciá",
    "parana": "Paraná", "sanjose": "San José", "sansalvador": "San Salvador",
    "sauceluna": "Sauce de Luna", "urdinarrain": "Urdinarrain",
    "villaparanacito": "Villa Paranacito", "villaguay": "Villaguay",
}
# Columnas fijas del archivo de WeatherLink (la de presión se busca en la cabecera).
TEMP, HUMEDAD, ROCIO, VIENTO, DIRECCION, RAFAGA = 2, 5, 6, 7, 8, 10

_DMS = re.compile(r"(Latitud|Longitud)\s*(\d+)&deg;\s*(\d+)'\s*([\d.]+)&quot;\s*([NSEWO])")


def _ubicacion(id_estacion):
    pagina = descargar(URL_FICHA.format(id=id_estacion)).decode("utf-8", "replace")
    pagina = re.sub(r"<[^>]+>", " ", pagina)
    coords = {}
    for eje, g, m, s, hemisferio in _DMS.findall(pagina):
        valor = int(g) + int(m) / 60 + float(s) / 3600
        coords[eje] = -valor if hemisferio in "SWO" else valor
    return (coords["Latitud"], coords["Longitud"]) if len(coords) == 2 else None


def _ubicaciones_estaciones():
    ids = list(ESTACIONES)
    return cacheado("hidraulica_er_ubicaciones", 24 * 7,
                    lambda: dict(zip(ids, en_paralelo(_ubicacion, ids, hilos=5))))


def _hora(fecha, hora):
    """WeatherLink usa '21:40' o '9:40p' según la configuración de la consola."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})([ap])?", hora)
    if not m:
        return None
    h = int(m[1]) % 12 + (12 if m[3] == "p" else 0) if m[3] else int(m[1])
    return hora_local_a_utc(f"{fecha} {h}:{m[2]}", "%d/%m/%y %H:%M")


def _fahrenheit_a_c(f):
    return None if f is None else round((f - 32) / 1.8, 1)


def _ultima_lectura(id_estacion):
    url = URL_ARCHIVO.format(id=id_estacion)
    cabecera = descargar(url, cabeceras={"Range": "bytes=0-800"}).decode("latin-1").splitlines()
    cola = descargar(url, cabeceras={"Range": "bytes=-800"}).decode("latin-1").splitlines()
    nombres = cabecera[1].split() if len(cabecera) > 1 else []
    if "Bar" not in nombres:
        return None
    col_presion = nombres.index("Bar")
    for linea in reversed(cola):
        c = linea.split()
        if len(c) > col_presion and re.fullmatch(r"\d{1,2}/\d{2}/\d{2}", c[0]):
            return c, col_presion
    return None


def obtener():
    ubicaciones = _ubicaciones_estaciones()
    ids = [i for i in ESTACIONES if ubicaciones.get(i)]
    salida = []
    for id_estacion, lectura in zip(ids, en_paralelo(_ultima_lectura, ids, hilos=5)):
        if lectura is None:
            continue
        c, col_presion = lectura
        temp, rocio = numero(c[TEMP]), numero(c[ROCIO])
        viento, rafaga = numero(c[VIENTO]), numero(c[RAFAGA])
        presion = numero(c[col_presion])
        if presion is not None and presion < 40:  # consola en unidades inglesas (°F, mph, inHg)
            temp, rocio = _fahrenheit_a_c(temp), _fahrenheit_a_c(rocio)
            viento = None if viento is None else viento * 1.609
            rafaga = None if rafaga is None else rafaga * 1.609
            presion *= 33.8639
        elif presion is not None and 600 < presion < 800:  # mmHg
            presion *= 1.33322
        lat, lon = ubicaciones[id_estacion]
        salida.append(estacion(
            id=f"hidraulica_er:{id_estacion}",
            enlace=f"https://www.hidraulica.gob.ar/ema.php?station={id_estacion}",
            nombre=f"{ESTACIONES[id_estacion]} (Hidráulica ER)",
            fuente=ID,
            lat=lat, lon=lon,
            hora_utc=_hora(c[0], c[1]),
            temp_c=temp,
            humedad_pct=numero(c[HUMEDAD]),
            rocio_c=rocio,
            viento_kmh=viento,
            viento_dir_grados=rumbo_a_grados(c[DIRECCION]),
            rafaga_kmh=rafaga,
            presion_hpa=None if presion is None else round(presion, 1),
            crudo=" ".join(c[:col_presion + 2]),
        ))
    return salida
