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
    valores, horas = {}, []
    for m in resp.get("Mediciones") or []:
        campo, valor = CODIGOS.get(m.get("Codigo")), numero(m.get("Valor"))
        ms = _ms(m.get("FechaHora"))
        if campo is None or valor is None or valor <= -999 or ms is None or ms <= 0:
            continue
        valores[campo] = valor
        horas.append(ms)
    if "temp_c" not in valores:
        return None
    return valores, max(horas)


def obtener():
    listado = cacheado("snih_listado", 24, _descargar_listado)
    revision = leer_json("snih_activas")  # códigos que informaron en la última revisión completa
    completa = not revision or time.time() - revision["momento"] > HORAS_REVISION_COMPLETA * 3600
    activas_previas = set() if completa else set(revision["codigos"])
    a_consultar = [e for e in listado["estaciones"] if completa or e["Codigo"] in activas_previas]
    resultados = en_paralelo(_actuales, a_consultar, hilos=8)

    salida, activas = [], set()
    for e, r in zip(a_consultar, resultados):
        if r is None:
            continue
        valores, ms = r
        activas.add(e["Codigo"])
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
        ))
    if completa:
        guardar_json("snih_activas", {"momento": time.time(), "codigos": sorted(activas)})
    return salida
