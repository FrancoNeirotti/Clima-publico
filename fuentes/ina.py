"""Fuente: INA (Instituto Nacional del Agua), base de datos del sistema de alerta.

Incluye las estaciones automáticas de la Red Hidrológica Nacional (RHN-SAT) y
otras redes que el INA integra. Primero se piden las series de cada variable
(se guardan un día) y después las observaciones recientes de todas juntas.
"""
from datetime import datetime, timedelta, timezone

from .comun import cacheado, descargar_json, en_paralelo, estacion, ms_a_kmh, numero

ID = "ina"
NOMBRE = "INA / Red Hidrológica Nacional"
SITIO = "https://alerta.ina.gob.ar/a5/"
MINUTOS = 15

BASE = "https://alerta.ina.gob.ar/a5/obs/puntual/"
VARIABLES = {53: "temp_c", 58: "humedad_pct", 55: "viento_kmh", 57: "viento_dir_grados", 60: "presion_hpa"}
SERIES_POR_PEDIDO = 150
HORAS_ATRAS = 6


def _convertir(valor, unidad):
    unidad = (unidad or "").lower()
    if unidad == "m/s":
        return ms_a_kmh(valor)
    if unidad == "mmhg":
        return round(valor * 1.33322, 1)
    return valor


def _descargar_series():
    var_ids = ",".join(str(v) for v in VARIABLES)
    datos = descargar_json(f"{BASE}series?format=json&var_id={var_ids}", timeout=120)
    hace_una_semana = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    lista = []  # pares [id de serie, datos]; JSON no admite claves numéricas
    for s in datos.get("rows", []):
        fin = (s.get("date_range") or {}).get("timeend") or ""
        est = s.get("estacion") or {}
        coords = (est.get("geom") or {}).get("coordinates") or []
        if fin < hace_una_semana or len(coords) < 2 or est.get("pais", "Argentina") != "Argentina":
            continue
        lista.append([s["id"], {
            "campo": VARIABLES[s["var"]["id"]],
            "unidad": (s.get("unidades") or {}).get("abrev"),
            "estacion": {k: est.get(k) for k in ("id", "nombre", "geom", "altitud", "red", "tabla")},
        }])
    return lista


def _listado_series():
    return dict(cacheado("ina_series", 24, _descargar_series))


def obtener():
    series = _listado_series()
    ahora = datetime.now(timezone.utc)
    desde = (ahora - timedelta(hours=HORAS_ATRAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hasta = (ahora + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    ultimas = {}  # series_id -> observación más reciente
    ids = list(series)
    lotes = [",".join(str(x) for x in ids[i:i + SERIES_POR_PEDIDO])
             for i in range(0, len(ids), SERIES_POR_PEDIDO)]
    url = f"{BASE}observaciones?tipo=puntual&series_id={{}}&timestart={desde}&timeend={hasta}"
    respuestas = en_paralelo(lambda lote: descargar_json(url.format(lote), timeout=120), lotes, hilos=4)
    if lotes and all(r is None for r in respuestas):
        raise ConnectionError("el INA no respondió ningún pedido de observaciones")
    for o in (o for r in respuestas if r for o in r):
        previa = ultimas.get(o["series_id"])
        if previa is None or o["timestart"] > previa["timestart"]:
            ultimas[o["series_id"]] = o

    por_estacion = {}
    for sid, o in ultimas.items():
        s = series.get(sid)
        valor = numero(o.get("valor"))
        if s is None or valor is None:
            continue
        est = s["estacion"]
        datos = por_estacion.setdefault(est["id"], {"est": est, "hora": None, "valores": {}})
        datos["valores"][s["campo"]] = _convertir(valor, s["unidad"])
        if s["campo"] == "temp_c" or datos["hora"] is None:
            datos["hora"] = o["timestart"]

    salida = []
    for datos in por_estacion.values():
        est, v = datos["est"], datos["valores"]
        if "temp_c" not in v:
            continue
        lon, lat = est["geom"]["coordinates"][:2]
        red = (est.get("red") or {}).get("nombre") or est.get("tabla")
        salida.append(estacion(
            id=f"ina:{est['id']}",
            nombre=f"{est.get('nombre')} ({red})",
            fuente=ID,
            lat=lat, lon=lon,
            altura_m=numero(est.get("altitud")),
            hora_utc=datos["hora"].replace("Z", "+00:00"),
            **v,
        ))
    return salida
