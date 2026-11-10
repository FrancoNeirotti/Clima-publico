"""Fuente: SNIH, Sistema Nacional de Información Hídrica (snih.hidricosargentina.gob.ar).

Reúne redes nacionales y regionales con estaciones meteorológicas telemétricas
(RMET, SiNaRaMe, Red Hidrológica Nacional, CIRHBAS, etc.). No hay un pedido
masivo: se consulta estación por estación, en paralelo. Para no repetir cientos
de pedidos inútiles, cada tantas horas se revisan todas y en el medio solo las
que vienen informando temperatura.
"""
import json
import re
import time

from .comun import (cacheado, descargar_json, en_paralelo, estacion, guardar_json, leer_json,
                    ms_a_iso, numero)

ID = "snih"
NOMBRE = "SNIH (Secretaría de Recursos Hídricos)"
SITIO = "https://snih.hidricosargentina.gob.ar/Filtros.aspx"
MINUTOS = 15

BASE = "https://snih.hidricosargentina.gob.ar/"
CABECERAS = {"Content-Type": "application/json; charset=utf-8", "Referer": BASE + "Filtros.aspx"}
RED_INTA = 11  # figura en el listado pero no devuelve datos; el INTA ya tiene su fuente
HORAS_REVISION_COMPLETA = 6
CODIGOS = {14: "temp_c", 18: "humedad_pct", 4: "viento_kmh", 5: "viento_dir_grados", 218: "presion_hpa"}
LLUVIA = 20  # "Precipitación": lo que llovió en el intervalo de cada registro (1 o 4 h según la red)
CAMPOS_LISTADO = ("Codigo", "Descripcion", "Red", "Latitud", "Longitud", "Cota")


def _post(metodo, cuerpo):
    datos = json.dumps(cuerpo).encode("utf-8")
    return descargar_json(BASE + metodo, timeout=60, datos=datos, cabeceras=CABECERAS)["d"]


def _ms(texto):
    m = re.search(r"-?\d+", texto or "")
    return int(m[0]) if m else None


def _descargar_listado():
    redes = {str(r.get("Codigo")): r.get("Descripcion") for r in _post("Filtros.aspx/leerListaRedes", {})
             if isinstance(r, dict)}
    estaciones = [{c: e.get(c) for c in CAMPOS_LISTADO} for e in _post("Filtros.aspx/LeerEstaciones", {})
                  if "M" in (e.get("Tipo") or "") and e.get("Transmision") == "T"
                  and e.get("Habilitada") and e.get("Red") != RED_INTA
                  and e.get("Latitud") and e.get("Longitud")]
    return {"estaciones": estaciones, "redes": redes}


def _actuales(e):
    resp = _post("MuestraDatos.aspx/LeerDatosActuales", {"estacion": str(e["Codigo"])})
    valores, horas, lluvia = {}, [], None
    for m in resp.get("Mediciones") or []:
        valor, ms = numero(m.get("Valor")), _ms(m.get("FechaHora"))
        if valor is None or valor <= -999 or ms is None or ms <= 0:
            continue
        if m.get("Codigo") == LLUVIA:
            lluvia = (valor, ms)
        campo = CODIGOS.get(m.get("Codigo"))
        if campo is None:
            continue
        valores[campo] = valor
        horas.append(ms)
    if "temp_c" not in valores:
        return None
    return valores, max(horas), lluvia


def _lluvia_24h(codigo):
    """(mm, fin en ms, intervalo en minutos) sumando los registros de las últimas 24 h hasta
    el último; None si faltan registros."""
    hoy = time.time() - 3 * 3600
    dia = lambda dias: time.strftime("%Y-%m-%d", time.gmtime(hoy + dias * 86400))
    resp = _post("MuestraDatos.aspx/LeerUltimosRegistros",
                 {"fechaDesde": dia(-1), "fechaHasta": dia(1), "estacion": str(codigo), "codigo": str(LLUVIA)})
    registros = {}
    for r in resp.get("Mediciones") or []:
        ms = _ms(r.get("FechaHora"))
        for m in r.get("Mediciones") or []:
            valor = numero(m.get("Valor"))
            if m.get("Codigo") == LLUVIA and ms and valor is not None and valor > -999:
                registros[ms] = valor
    momentos = sorted(registros)
    if len(momentos) < 3:
        return None
    pasos = sorted(b - a for a, b in zip(momentos, momentos[1:]))
    intervalo = pasos[len(pasos) // 2]
    fin = momentos[-1]
    del_periodo = [t for t in momentos if t > fin - 86400000]
    # Cada registro es la lluvia del intervalo que termina en su hora: hacen falta todos.
    if not intervalo or len(del_periodo) < 86400000 // intervalo:
        return None
    return round(sum(registros[t] for t in del_periodo), 1), fin, intervalo // 60000


def _lluvias(codigos):
    return cacheado("snih_lluvia", 1, lambda: {
        str(c): r for c, r in zip(codigos, en_paralelo(_lluvia_24h, codigos, hilos=8)) if r})


def obtener():
    listado = cacheado("snih_listado", 24, _descargar_listado)
    revision = leer_json("snih_activas")  # códigos que informaron en la última revisión completa
    completa = not revision or time.time() - revision["momento"] > HORAS_REVISION_COMPLETA * 3600
    activas_previas = set() if completa else set(revision["codigos"])
    a_consultar = [e for e in listado["estaciones"] if completa or e["Codigo"] in activas_previas]
    resultados = en_paralelo(_actuales, a_consultar, hilos=8)
    con_lluvia = [e["Codigo"] for e, r in zip(a_consultar, resultados) if r and r[2]]
    try:
        lluvias = _lluvias(con_lluvia)
    except Exception:
        lluvias = {}

    salida, activas = [], set()
    for e, r in zip(a_consultar, resultados):
        if r is None:
            continue
        valores, ms, actual = r
        activas.add(e["Codigo"])
        lluvia = {}
        historia = lluvias.get(str(e["Codigo"]))
        if historia:
            mm, fin, intervalo = historia
            lluvia = {"precip_mm": mm, "precip_horas": 24, "precip_hasta_utc": ms_a_iso(fin)}
            # El registro horario es la lluvia de la última hora (si es el último disponible).
            if intervalo == 60 and actual and actual[1] >= fin and abs(actual[1] - ms) <= 3600000:
                lluvia["precip_1h_mm"] = actual[0]
        lat, lon = -abs(e["Latitud"]), -abs(e["Longitud"])  # el SNIH las guarda en positivo
        red = listado["redes"].get(str(e.get("Red")))
        nombre = (e.get("Descripcion") or str(e["Codigo"])).strip()
        salida.append(estacion(
            id=f"snih:{e['Codigo']}",
            nombre=f"{nombre} ({red})" if red else nombre,
            fuente=ID,
            lat=lat, lon=lon,
            altura_m=numero(e.get("Cota")) or None,
            hora_utc=ms_a_iso(ms),
            **valores,
            **lluvia,
        ))
    if completa:
        guardar_json("snih_activas", {"momento": time.time(), "codigos": sorted(activas)})
    return salida
