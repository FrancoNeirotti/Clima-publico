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
URL_ANUAL = "https://www.hidraulica.gob.ar/ema/ema-{id}/NOAAYR.TXT"  # resumen NOAA del año
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
    filas = _filas(cola, col_presion)
    if not filas:
        return None
    ultima = filas[-1]
    # La lluvia de cada fila es la del intervalo (última columna, en minutos): para la del
    # día se suman las filas desde las 0 h, que se piden aparte (unos 280 bytes por fila).
    intervalo = numero(ultima[-1])
    minutos = _minutos(ultima[1])
    lluvia = None
    if intervalo and intervalo > 0 and minutos is not None:
        bytes_dia = int(minutos / intervalo + 3) * 300
        if bytes_dia > 800:
            cola = descargar(url, cabeceras={"Range": f"bytes=-{bytes_dia}"}).decode("latin-1").splitlines()
            filas = _filas(cola, col_presion)
        # La fila de las 0:00 es el intervalo que termina a medianoche: cuenta para el día anterior.
        del_dia = [c for c in filas if c[0] == ultima[0] and _minutos(c[1])]
        valores = [numero(c[col_presion + 1]) for c in del_dia]
        primera = _minutos(del_dia[0][1]) if del_dia else None
        # Solo si se llegó hasta la primera fila del día y todas tienen dato.
        if valores and None not in valores and primera is not None and primera <= intervalo:
            lluvia = sum(valores)
    return ultima, col_presion, lluvia


def _minutos(hora):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})([ap])?", hora)
    if not m:
        return None
    h = int(m[1]) % 12 + (12 if m[3] == "p" else 0) if m[3] else int(m[1])
    return h * 60 + int(m[2])


def _filas(lineas, col_presion):
    # La primera línea puede venir cortada por el Range.
    return [c for c in (linea.split() for linea in lineas[1:])
            if len(c) > col_presion + 1 and re.fullmatch(r"\d{1,2}/\d{2}/\d{2}", c[0])]


def lluvia_mensual(texto):
    """Del resumen NOAA anual: {(año de 2 dígitos, mes): total en mm}. El mes en curso
    incluye lo que va del día hasta que la consola subió el archivo."""
    lineas = texto.splitlines()
    inicio = next((i for i, l in enumerate(lineas) if "PRECIPITACION" in l.upper()), None)
    if inicio is None:
        return {}
    factor = 25.4 if "(in)" in lineas[inicio] else 1
    totales, en_tabla = {}, False
    for linea in lineas[inicio + 1:]:
        if linea.startswith("-"):
            if en_tabla:
                break
            en_tabla = True
            continue
        m = re.match(r"\s*(\d{1,2})\s+(\d{1,2})\s+(\d+\.\d+)", linea)
        if m:
            totales[(int(m[1]), int(m[2]))] = round(float(m[3]) * factor, 1)
    return totales


def _lluvia_mensual(id_estacion):
    return cacheado(f"hidraulica_er_noaa_{id_estacion}", 1, lambda: {
        f"{a}-{m}": v for (a, m), v in
        lluvia_mensual(descargar(URL_ANUAL.format(id=id_estacion)).decode("latin-1")).items()})


def _mes_y_anio(id_estacion, fecha):
    """Lluvia del mes y del año de la fecha 'dd/mm/aa' de la última lectura."""
    try:
        totales = _lluvia_mensual(id_estacion)
    except Exception:
        return None, None
    _, mes, anio = (int(x) for x in fecha.split("/"))
    del_anio = [v for k, v in totales.items() if int(k.split("-")[0]) == anio]
    return totales.get(f"{anio}-{mes}"), (round(sum(del_anio), 1) if del_anio else None)


def obtener():
    ubicaciones = _ubicaciones_estaciones()
    ids = [i for i in ESTACIONES if ubicaciones.get(i)]
    salida = []
    for id_estacion, lectura in zip(ids, en_paralelo(_ultima_lectura, ids, hilos=5)):
        if lectura is None:
            continue
        c, col_presion, lluvia = lectura
        temp, rocio = numero(c[TEMP]), numero(c[ROCIO])
        viento, rafaga = numero(c[VIENTO]), numero(c[RAFAGA])
        presion = numero(c[col_presion])
        intensidad = numero(c[col_presion + 2]) if len(c) > col_presion + 2 else None
        if presion is not None and presion < 40:  # consola en unidades inglesas (°F, mph, inHg)
            temp, rocio = _fahrenheit_a_c(temp), _fahrenheit_a_c(rocio)
            viento = None if viento is None else viento * 1.609
            rafaga = None if rafaga is None else rafaga * 1.609
            presion *= 33.8639
            lluvia = None if lluvia is None else lluvia * 25.4
            intensidad = None if intensidad is None else intensidad * 25.4
        elif presion is not None and 600 < presion < 800:  # mmHg
            presion *= 1.33322
        mes, anio = _mes_y_anio(id_estacion, c[0])
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
            precip_hoy_mm=lluvia,
            precip_mes_mm=mes,
            precip_anio_mm=anio,
            precip_intensidad_mmh=intensidad,  # máxima del último intervalo
            crudo=" ".join(c[:col_presion + 3]),
        ))
    return salida
