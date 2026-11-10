"""Servidor local del mapa de estaciones.

Uso:  python servidor.py            (abre http://127.0.0.1:8000)
      python servidor.py --puerto 8080 --sin-navegador
      python servidor.py --generar salida   (una sola pasada: escribe salida/estaciones.json)

Cada fuente se actualiza sola en segundo plano, con su propio intervalo
(MINUTOS en cada módulo). El mapa recibe lo que haya en ese momento, así las
fuentes lentas no demoran a las rápidas.
"""
import argparse
import gzip
import hashlib
import json
import math
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fuentes import (ambient, awekas, bcp, cwop, eeaoc, hidraulica_er, ina, inta, mendoza, metar,
                     sanluis, sensor_community, smn, snih, synop, weathercloud, weatherlink)
from fuentes.comun import CAMPOS, distancia_km, guardar_json, leer_json, limpiar, valores_atipicos

# El orden es la prioridad: si dos estaciones de distintas fuentes están a menos
# de RADIO_DUPLICADO_KM, se muestra la de la fuente que aparece primero. Las redes
# privadas van al final; Weathercloud y Sensor.Community, últimas porque la primera no
# trae la hora de cada lectura y la segunda usa sensores de baja calidad.
FUENTES = [metar, smn, synop, mendoza, sanluis, eeaoc, bcp, hidraulica_er, inta, snih, ina,
           weatherlink, ambient, awekas, cwop, weathercloud, sensor_community]
MINUTOS_POR_DEFECTO = 10
MINUTOS_REINTENTO = 3          # si una fuente falla, se vuelve a probar antes
HORAS_MAXIMAS = 12             # observaciones más viejas no se muestran
MINUTOS_FUTURO_TOLERADO = 30   # relojes adelantados: más que esto, la hora no es confiable
RADIO_DUPLICADO_KM = 2.0
# Si una estación se descarta por duplicada pero es la misma estación física que la que
# se muestra (p. ej. el SYNOP de una estación del SMN), su lluvia pasa a la mostrada.
LLUVIA_DE_DUPLICADA = {"smn": {"synop"}, "metar": {"synop"}}
CAMPOS_LLUVIA = [c for c in CAMPOS if c.startswith("precip_") and c != "precip_fuente"]
CELDA_GRADOS = 0.05            # grilla para buscar duplicados (~5 km, mayor que el radio)
CARPETA_WEB = Path(__file__).parent / "static"

_candado = threading.Lock()
_estado = {f.ID: {"lista": [], "error": None, "momento": 0.0, "segundos": None,
                  "cargando": False, "cargada": False} for f in FUENTES}
_combinado = {"version": -1, "momento": 0.0, "datos": None}
_version = [0]


def _minutos(fuente):
    return getattr(fuente, "MINUTOS", MINUTOS_POR_DEFECTO)


def _refrescar(fuente):
    inicio = time.time()
    try:
        lista, error = [limpiar(e) for e in fuente.obtener()], None
    except Exception as e:  # una fuente caída no tumba a las demás
        lista, error = None, f"{type(e).__name__}: {e}"
    segundos = round(time.time() - inicio, 1)
    with _candado:
        est = _estado[fuente.ID]
        if lista is not None:
            est["lista"] = lista
            est["momento"] = time.time()
        else:  # se conservan los últimos datos buenos y se reintenta pronto
            est["momento"] = time.time() - (_minutos(fuente) - MINUTOS_REINTENTO) * 60
        est.update(error=error, segundos=segundos, cargando=False, cargada=True)
        _version[0] += 1
    if lista is not None:
        guardar_json(f"fuente_{fuente.ID}", {"momento": est["momento"], "lista": lista})
    if error:
        print(f"[{fuente.ID}] error: {error}", file=sys.stderr)
    else:
        print(f"[{fuente.ID}] {len(lista)} estaciones en {segundos} s")
    sin_ubicar = list(getattr(fuente, "sin_ubicar", []))
    if sin_ubicar:
        print(f"[{fuente.ID}] sin ubicar: {', '.join(sin_ubicar)}", file=sys.stderr)


def _cargar_guardado():
    """Al arrancar, retoma los últimos datos de cada fuente guardados en disco: el mapa
    aparece completo enseguida y solo se vuelven a pedir las fuentes vencidas."""
    for fuente in FUENTES:
        guardado = leer_json(f"fuente_{fuente.ID}")
        if guardado and time.time() - guardado["momento"] < HORAS_MAXIMAS * 3600:
            _estado[fuente.ID].update(lista=guardado["lista"], momento=guardado["momento"], cargada=True)


def _programar(forzar=False):
    """Lanza en segundo plano la actualización de las fuentes vencidas (o de todas)."""
    ahora = time.time()
    for fuente in FUENTES:
        with _candado:
            est = _estado[fuente.ID]
            vencida = not est["cargando"] and (forzar or ahora - est["momento"] > _minutos(fuente) * 60)
            if vencida:
                est["cargando"] = True
                _version[0] += 1
        if vencida:
            threading.Thread(target=_refrescar, args=(fuente,), daemon=True).start()


def _programador():
    while True:
        _programar()
        time.sleep(15)


def _celda(lat, lon):
    return math.floor(lat / CELDA_GRADOS), math.floor(lon / CELDA_GRADOS)


def _duplicada(est, grilla):
    ci, cj = _celda(est["lat"], est["lon"])
    return next((
        o for di in (-1, 0, 1) for dj in (-1, 0, 1) for o in grilla.get((ci + di, cj + dj), ())
        if distancia_km(est["lat"], est["lon"], o["lat"], o["lon"]) < RADIO_DUPLICADO_KM
    ), None)


def _sumar_lluvia(mostrada, duplicada):
    """Pasa la lluvia de una duplicada a la estación mostrada si es la misma estación física
    y la mostrada no informa lluvia."""
    if duplicada["fuente"] not in LLUVIA_DE_DUPLICADA.get(mostrada["fuente"], ()):
        return
    if any(mostrada.get(c) is not None for c in CAMPOS_LLUVIA):
        return
    lluvia = {c: duplicada.get(c) for c in CAMPOS_LLUVIA if duplicada.get(c) is not None}
    if lluvia:
        mostrada.update(lluvia, precip_fuente=duplicada["fuente"])


def _combinar():
    ahora = datetime.now(timezone.utc)
    vigentes, viejas = {}, {}
    for fuente in FUENTES:
        vigentes[fuente.ID], viejas[fuente.ID] = [], 0
        for est in _estado[fuente.ID]["lista"]:
            if est["hora_utc"]:
                hora = datetime.fromisoformat(est["hora_utc"])
                if hora - ahora > timedelta(minutes=MINUTOS_FUTURO_TOLERADO):
                    est = dict(est, hora_utc=None)
                elif ahora - hora > timedelta(hours=HORAS_MAXIMAS):
                    viejas[fuente.ID] += 1
                    continue
            vigentes[fuente.ID].append(est)

    # Se revisa antes de deduplicar, para que un sensor roto no tape a una estación sana.
    todas = [e for lista in vigentes.values() for e in lista]
    temp_atipica = valores_atipicos(todas, "temp_c", 15)
    humedad_atipica = valores_atipicos(todas, "humedad_pct", 35)

    estaciones, informe, grilla = [], [], {}
    for fuente in FUENTES:
        est_fuente = _estado[fuente.ID]
        mostradas = 0
        for est in vigentes[fuente.ID]:
            if est["id"] in temp_atipica:
                est = dict(est, temp_c=None, rocio_c=None, sensacion_c=None)
            if est["id"] in humedad_atipica:
                est = dict(est, humedad_pct=None, rocio_c=None)
            if all(est[c] is None for c in ("temp_c", "humedad_pct", "viento_kmh")):
                continue
            previa = _duplicada(est, grilla)
            if previa is not None:
                _sumar_lluvia(previa, est)
                continue
            est = dict(est)  # copia: _sumar_lluvia puede agregarle campos
            estaciones.append(est)
            grilla.setdefault(_celda(est["lat"], est["lon"]), []).append(est)
            mostradas += 1
        informe.append({
            "id": fuente.ID, "nombre": fuente.NOMBRE, "tipo": getattr(fuente, "TIPO", "publica"),
            "sitio": getattr(fuente, "SITIO", None),
            "ok": est_fuente["error"] is None, "error": est_fuente["error"],
            "cargando": not est_fuente["cargada"] or est_fuente["cargando"],
            "recibidas": len(est_fuente["lista"]), "mostradas": mostradas,
            "viejas": viejas[fuente.ID],
            "sin_ubicar": list(getattr(fuente, "sin_ubicar", [])),
            "segundos": est_fuente["segundos"],
        })
    # Hora de la última actualización de datos (no la de ahora), para que la respuesta
    # no cambie si no hay datos nuevos y el navegador pueda reusar la que tiene.
    ultima = max((e["momento"] for e in _estado.values()), default=0) or time.time()
    generado = datetime.fromtimestamp(ultima, timezone.utc).isoformat()
    return {"generado_utc": generado, "fuentes": informe, "estaciones": estaciones}


def _serializar(datos):
    """JSON compacto (sin campos vacíos) y su versión comprimida, listos para enviar."""
    datos["estaciones"] = [{k: v for k, v in e.items() if v is not None} for e in datos["estaciones"]]
    cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {"cuerpo": cuerpo, "gzip": gzip.compress(cuerpo, 6),
            "etag": '"' + hashlib.sha1(cuerpo).hexdigest()[:16] + '"'}


def datos(forzar=False):
    if forzar:
        _programar(forzar=True)
    with _candado:
        vigente = (_combinado["version"] == _version[0]
                   and time.time() - _combinado["momento"] < 60)
        if not vigente:
            _combinado.update(version=_version[0], momento=time.time(), datos=_serializar(_combinar()))
        return _combinado["datos"]


def generar(carpeta, limite_segundos):
    """Una sola pasada, sin servidor (para publicarlo como sitio estático): retoma la
    caché, actualiza solo las fuentes vencidas y escribe <carpeta>/estaciones.json."""
    _cargar_guardado()
    _programar()
    fin = time.time() + limite_segundos
    while time.time() < fin:
        with _candado:
            if not any(e["cargando"] for e in _estado.values()):
                break
        time.sleep(1)
    with _candado:
        for fuente in FUENTES:
            est = _estado[fuente.ID]
            if est["cargando"]:  # se publica igual, con los últimos datos guardados
                est.update(cargando=False, cargada=True,
                           error=f"tardó más de {limite_segundos} s; se muestran los últimos datos guardados")
                print(f"[{fuente.ID}] error: {est['error']}", file=sys.stderr)
        respuesta = _serializar(_combinar())
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    temporal = carpeta / "estaciones.json.tmp"
    temporal.write_bytes(respuesta["cuerpo"])
    temporal.replace(carpeta / "estaciones.json")
    resumen = json.loads(respuesta["cuerpo"])
    print(f"{len(resumen['estaciones'])} estaciones escritas en {carpeta / 'estaciones.json'}")
    for f in resumen["fuentes"]:
        print(f"  {'ok   ' if f['ok'] else 'FALLA'} {f['id']:<17} {f['mostradas']:>4} mostradas"
              + (f"  ({f['error']})" if f["error"] else ""))


class Manejador(BaseHTTPRequestHandler):
    def do_GET(self):
        ruta, _, consulta = self.path.partition("?")
        if ruta == "/api/estaciones":
            respuesta = datos(forzar="actualizar=1" in consulta)
            if self.headers.get("If-None-Match") == respuesta["etag"]:
                self.send_response(304)
                self.send_header("ETag", respuesta["etag"])
                self.end_headers()
                return
            self._responder(respuesta, "application/json; charset=utf-8")
        elif ruta in ("/", "/index.html"):
            self._responder({"cuerpo": (CARPETA_WEB / "index.html").read_bytes()}, "text/html; charset=utf-8")
        else:
            self.send_error(404, "No existe")

    def _responder(self, respuesta, tipo):
        comprimir = "gzip" in respuesta and "gzip" in self.headers.get("Accept-Encoding", "")
        cuerpo = respuesta["gzip"] if comprimir else respuesta["cuerpo"]
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        # no-cache (no no-store): el navegador guarda la respuesta y la revalida con el ETag.
        self.send_header("Cache-Control", "no-cache")
        if "etag" in respuesta:
            self.send_header("ETag", respuesta["etag"])
        if comprimir:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato, *args):
        pass  # sin ruido en la consola por cada pedido


def main():
    p = argparse.ArgumentParser(description="Mapa de estaciones meteorológicas de Argentina")
    p.add_argument("--puerto", type=int, default=8000)
    p.add_argument("--sin-navegador", action="store_true")
    p.add_argument("--red-local", action="store_true",
                   help="aceptar conexiones de otros equipos de la red (p. ej. para abrirlo en el celular)")
    p.add_argument("--generar", metavar="CARPETA",
                   help="no levantar el servidor: actualizar las fuentes vencidas una vez y "
                        "escribir CARPETA/estaciones.json (para publicarlo como sitio estático)")
    p.add_argument("--limite", type=int, default=480, metavar="SEGUNDOS",
                   help="con --generar, cuánto esperar a las fuentes lentas (480 por defecto)")
    args = p.parse_args()

    if args.generar:
        generar(args.generar, args.limite)
        return

    servidor = ThreadingHTTPServer(("0.0.0.0" if args.red_local else "127.0.0.1", args.puerto), Manejador)
    _cargar_guardado()
    threading.Thread(target=_programador, daemon=True).start()
    url = f"http://127.0.0.1:{args.puerto}"
    print(f"Mapa disponible en {url}  (Ctrl+C para cortar)")
    if args.red_local:
        ip = socket.gethostbyname(socket.gethostname())
        print(f"Desde el celular (misma red Wi-Fi): http://{ip}:{args.puerto}")
    if not args.sin_navegador:
        threading.Timer(1, webbrowser.open, [url]).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
