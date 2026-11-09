# Estaciones meteorológicas de Argentina

Mapa estilo Wunderground con las estaciones públicas del país. Un servidor
local en Python junta los datos de cada fuente, los pasa a un formato común y
los sirve a un mapa que se actualiza solo cada 5 minutos.

Fuentes incluidas (en orden de prioridad):

| Fuente | Qué trae | Estaciones aprox. |
|---|---|---|
| **Aeropuertos (METAR)** | API pública de aviationweather.gov, aeródromos argentinos (OACI "SA…") | 15–60 según la hora |
| **SMN, tiempo presente** | Datos abiertos del Servicio Meteorológico Nacional, cada hora | ~120 |
| **SMN, partes SYNOP** | Los mismos observatorios vía OGIMET, con número OMM; respaldo del anterior y bases antárticas | ~110 |
| **Mendoza (DACC)** | Red agrometeorológica de Contingencias Climáticas, feed público | ~60 |
| **San Luis (REM)** | Red de Estaciones Meteorológicas de la provincia | ~60 |
| **Tucumán (EEAOC)** | Red agrometeorológica de la Estación Experimental Obispo Colombres | ~40 |
| **Bahía Blanca (BCP)** | Red de la Bolsa de Cereales y Productos (sudoeste bonaerense, La Pampa) | ~35 |
| **Entre Ríos (Hidráulica)** | Estaciones automáticas de la Dirección de Hidráulica | 3–5 activas |
| **INTA** | Estaciones automáticas del SIGA que transmiten en tiempo real | ~70 |
| **SNIH** | Sistema Nacional de Información Hídrica: RMET, SiNaRaMe, Red Hidrológica Nacional, CIRHBAS… | ~250 |
| **INA** | Base del sistema de alerta del Instituto Nacional del Agua (RHN-SAT y otras) | ~190 |

Redes privadas y ciudadanas que publican sus datos abiertamente (en el mapa se
ven con borde punteado y se pueden ocultar desde el panel):

| Fuente | Qué trae | Estaciones aprox. |
|---|---|---|
| **WeatherLink** | Estaciones Davis que sus dueños dejan públicas en weatherlink.com/map (productores, acopios, terminales portuarias). Una consulta por estación: se actualiza cada hora | cientos |
| **Ambient Weather** | Mapa público de ambientweather.net | ~200 |
| **AWEKAS** | Red de estaciones particulares awekas.at (sesión anónima que entrega la propia API) | ~30 |
| **CWOP** | Estaciones ciudadanas CWOP/APRS vía findU.com | decenas |
| **Weathercloud** | Mapa público de weathercloud.net; no trae la hora de cada lectura, se usa la de la descarga | ~500 |
| **Sensor.Community** | Sensores ciudadanos de temperatura y humedad (datos abiertos) | ~6 |

Las plataformas mundiales se filtran con un contorno aproximado del país
(`CONTORNO_ARGENTINA` en `fuentes/comun.py`), preciso a unos 20–30 km en las fronteras.

Revisadas y no incluidas porque piden registro, clave o bloquean el acceso
externo: Weather Underground, Netatmo, Ecowitt, WeatherFlow Tempest, Windguru
(responde "Unauthorized" fuera de su sitio), Holfuy (una sola estación, con
contraseña), Meteoclimatic, Met Office WOW (dado de baja) y OpenWindMap (sin
estaciones en el país).

Cuando dos estaciones de fuentes distintas están a menos de 2 km, se muestra
una sola: la de la fuente que figura primero en la tabla.

Se revisaron y **no** se incluyen (por ahora): la red de Córdoba y la de la
Bolsa de Cereales de Entre Ríos (publican las lecturas solo como imagen), la
AIC y la red GEA de la Bolsa de Comercio de Rosario (solo datos diarios).

## Requisitos

Python 3.10 o superior. No usa librerías externas, así que no hace falta `pip install`.

Si no lo tenés instalado y la compu no te da permisos de administrador, instalalo desde python.org eligiendo la opción para el usuario actual ("Install for me only"), o desde la Microsoft Store.

## Cómo correrlo (PowerShell)

```powershell
cd ruta\a\estaciones-ar
python servidor.py
```

Se abre el navegador en http://127.0.0.1:8000. Para cortar el servidor, Ctrl+C en la consola.

Otras opciones:

```powershell
python servidor.py --puerto 8080
python servidor.py --sin-navegador
python servidor.py --red-local     # para abrirlo desde el celular en la misma red Wi-Fi
```

Con `--red-local` la consola muestra la dirección para el celular. En pantallas chicas el panel pasa a ser una hoja inferior: se arrastra o se toca la barrita de arriba para agrandarla o achicarla. Windows puede pedir permiso en el firewall la primera vez; usalo solo en redes de confianza.

Cada estación muestra su fuente con un enlace a la página de esa estación en el sitio de origen (o al sitio de la red cuando no hay página por estación).

Si la red de la empresa usa proxy y las fuentes no responden, configuralo antes de arrancar:

```powershell
$env:HTTPS_PROXY = "http://servidor-proxy:puerto"
python servidor.py
```

## Qué mirar la primera vez

La consola muestra cuántas estaciones trajo cada fuente. Cada fuente se actualiza en segundo plano con su propio intervalo, así que el mapa aparece enseguida con las rápidas y se va completando. La primera vez tarda unos 4 minutos en juntar todo (SNIH, WeatherLink y CWOP consultan estación por estación).

Los últimos datos de cada fuente y los listados pesados (índices de estaciones, que cambian poco) se guardan en la carpeta `cache/`. Al volver a arrancar, el mapa aparece completo al instante y solo se piden de nuevo las fuentes vencidas. Se puede borrar esa carpeta sin problema: se vuelve a armar sola.

Con el zoom alejado el mapa dibuja una estación por zona (priorizando las oficiales); al acercarse se ven todas. Revisá dos cosas:

1. **Que las fuentes respondan.** Si alguna falla, el mapa lo indica en el panel, la consola muestra el error y se reintenta a los pocos minutos conservando los últimos datos buenos.
2. **Estaciones del SMN sin ubicar.** El archivo de tiempo presente no trae coordenadas, así que se cruzan por nombre con el listado de estaciones del SMN. Las que no coinciden aparecen en la consola como `[smn] sin ubicar: …`. Para cargarlas a mano, agregalas en `fuentes/smn_coordenadas_manual.json` con el nombre exacto, con coordenadas o con el nombre que tienen en el listado del SMN:

```json
{
  "Nombre tal cual aparece en la consola": [-32.55, -60.85],
  "Otro nombre": "NOMBRE EN EL LISTADO DEL SMN"
}
```

Los valores imposibles (humedad 0 o 255, 50 °C, presión 0, etc., que algunas redes informan cuando falla un sensor) se descartan en `limpiar()` de `fuentes/comun.py`, y no se muestran observaciones de más de 12 horas.

## Cómo agregar otra fuente

1. Creá un archivo en `fuentes/` con `ID`, `NOMBRE`, opcionalmente `MINUTOS` (cada cuánto se actualiza; 10 por defecto) y una función `obtener()` que devuelva una lista de estaciones armadas con `estacion(...)` de `fuentes/comun.py`. Los campos posibles están listados en `CAMPOS`.
2. Importalo en `servidor.py` y sumalo a la lista `FUENTES`. El orden de la lista define qué fuente gana cuando hay dos estaciones en el mismo lugar.

Antes de publicar el mapa, revisá las condiciones de uso de cada red.

## Publicado en GitHub Pages

El mapa está publicado en **https://franconeirotti.github.io/Clima-publico/**, sin servidor propio:

- `.github/workflows/datos.yml` corre cada 5 minutos (GitHub suele demorar los programados unos minutos más): ejecuta `python servidor.py --generar salida`, que hace una sola pasada respetando el intervalo de cada fuente, y sube `estaciones.json` junto con la carpeta `cache/` a la rama `datos` (un único commit que se reemplaza en cada corrida).
- La página lee los datos de `https://raw.githubusercontent.com/FrancoNeirotti/Clima-publico/datos/estaciones.json` (con hasta 5 minutos de caché del CDN).
- `.github/workflows/pages.yml` despliega `static/index.html` solo cuando cambia `main`, apuntando la etiqueta `<meta name="url-datos">` a ese archivo.

Si una fuente no responde desde los servidores de GitHub, se publican sus últimos datos buenos (hasta 12 horas) y el panel marca el error. GitHub pausa los workflows programados tras 60 días sin actividad en el repositorio; se reactivan desde la pestaña Actions.

## Estructura

```
servidor.py                 servidor local, actualización en segundo plano, deduplicación y caché en disco
cache/                      últimos datos e índices guardados (se crea sola; se puede borrar)
fuentes/comun.py            formato común, conversiones y control de calidad
fuentes/metar.py            aeropuertos vía aviationweather.gov
fuentes/smn.py              SMN tiempo presente + listado de estaciones
fuentes/smn_coordenadas_manual.json
fuentes/synop.py            partes SYNOP del SMN vía OGIMET
fuentes/mendoza.py          DACC Mendoza
fuentes/sanluis.py          REM San Luis
fuentes/eeaoc.py            EEAOC Tucumán
fuentes/bcp.py              Bolsa de Cereales y Productos de Bahía Blanca
fuentes/hidraulica_er.py    Dirección de Hidráulica de Entre Ríos
fuentes/inta.py             INTA SIGA
fuentes/snih.py             Sistema Nacional de Información Hídrica
fuentes/ina.py              Instituto Nacional del Agua
static/index.html           mapa (Leaflet + OpenStreetMap)
.github/workflows/          datos cada 5 minutos (rama datos) y despliegue en GitHub Pages
```
