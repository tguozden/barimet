# BariMet — contexto del proyecto

Red de estaciones meteorológicas para Bariloche. Recibe datos de estaciones Fine Offset vía HTTP POST y los muestra en una página web.

## Arquitectura

```
Estación meteorológica (Fine Offset, protocolo Wunderground)
        │
        │  POST /data/report/  (form-urlencoded, cada ~16 segundos)
        ▼
barimet.com.ar (Cloudflare)
        │
        │  Tunnel QUIC
        ▼
Nginx (puerto 80)
        ├── /                  → /var/www/barimet/index.html
        ├── /chalten           → /var/www/barimet/chalten.html
        ├── /api/              → FastAPI (puerto 8080)
        └── /data/             → FastAPI (puerto 8080)
        │
        ▼
FastAPI / uvicorn (puerto 8080)
        │
        ▼
PostgreSQL (base de datos: barimet, usuario: tomi)
```

## Archivos importantes

- `~/barimet/main.py` — API FastAPI (recibe datos, sirve endpoints)
- `~/barimet/estaciones.py` — dicts ESTACIONES y CHALTEN con passkeys, nombres y alturas (no va al repo)
- `~/barimet/estaciones.example.py` — ejemplo sin passkeys reales (va al repo)
- `~/barimet/.env` — variables de entorno (no va al repo)
- `~/barimet/index.html` — página web principal
- `~/barimet/chalten.html` — página para estaciones de Chaltén
- `/var/www/barimet/index.html` — página servida por nginx
- `/var/www/barimet/chalten.html` — página /chalten servida por nginx
- `~/.cloudflared/config.yml` — configuración del tunnel Cloudflare
- `/etc/nginx/sites-available/barimet` — configuración de Nginx
- `/etc/systemd/system/barimet.service` — servicio systemd de uvicorn

## Servicios systemd

```bash
sudo systemctl status cloudflared   # tunnel Cloudflare
sudo systemctl status barimet       # FastAPI / uvicorn
sudo systemctl status postgresql    # base de datos
sudo systemctl restart barimet      # reiniciar después de cambios en main.py
```

## Entorno virtual Python

```bash
source ~/.venv/barimet/bin/activate
python -m pip install <paquete>
```

## Variables de entorno (.env)

```
DATABASE_URL=postgresql://tomi:PASSWORD@localhost/barimet
```

## Endpoints API

| Endpoint | Método | Descripción |
|---|---|---|
| `/data/report/` | POST | Recibe datos de las estaciones (form-urlencoded) |
| `/api/estaciones` | GET | Último dato de cada estación (excluye CHALTEN) |
| `/api/chalten` | GET | Último dato de cada estación de Chaltén |
| `/` | GET | Estado del servidor |

## Base de datos

```bash
sudo -u postgres psql -d barimet
```

### Tabla mediciones

Columnas: `id`, `estacion_id` (PASSKEY de la estación), `timestamp`, `temp_c`, `temp_interior_c`, `humedad`, `humedad_interior`, `viento_vel`, `viento_racha`, `viento_dir`, `presion_rel`, `presion_abs`, `lluvia_rate`, `lluvia_hora`, `lluvia_dia`, `lluvia_semana`, `lluvia_mes`, `lluvia_anio`, `radiacion_solar`, `uv`

Todos los datos están en sistema métrico (conversión desde imperial en el momento de recibir).

## Datos que manda la estación

- Path: `/data/report/`
- Formato: `application/x-www-form-urlencoded`
- Intervalo: ~16 segundos
- Variables: `PASSKEY`, `tempf`, `humidityin`, `baromrelin`, `baromabsin`, `tempf`, `humidity`, `winddir`, `windspeedmph`, `windgustmph`, `rainratein`, `hourlyrainin`, `dailyrainin`, `weeklyrainin`, `monthlyrainin`, `yearlyrainin`, `solarradiation`, `uv`, `wh65batt`, entre otras

## Conversiones imperial → métrico

```python
def f_a_c(f): return round((float(f) - 32) * 5 / 9, 1)
def mph_a_kmh(mph): return round(float(mph) * 1.60934, 1)
def in_a_mm(i): return round(float(i) * 25.4, 2)
def inhg_a_hpa(i): return round(float(i) * 33.8639, 1)
```

## Estaciones registradas

Los PASSKEY de las estaciones se identifican en el frontend en el objeto `ESTACIONES` dentro de `index.html`. Agregar nuevas estaciones ahí con su nombre descriptivo y altura en msnm.

| PASSKEY | Nombre | Altura |
|---|---|---|
| `D42CC28A6F2389B873ABB1F5D0729410` | Belgrano | 880 msnm |
| `fortin` | Fortín | 860 msnm |
| `DC3CCEADB75D00DB861BD419CA4FDBB2` | Frey | 1770 msnm |

### Estaciones Chaltén (en `/chalten`)

| PASSKEY | Nombre | Altura |
|---|---|---|
| `PUmH8FK0` | China | 2000 msnm |
| `jBEZGKDG` | Termo | 1500 msnm |
| `Of4gN8ev` | Repe | 1200 msnm |

## Pendiente

- Wind barbs: mostrar velocidad/racha con barbas meteorológicas. Intentado con SVG manual, quedó solo el círculo de calma. Requiere una librería apropiada.

## Página web

- Muestra una card por estación con último dato
- Actualiza automáticamente cada 10 segundos via fetch a `/api/estaciones`
- `/chalten` muestra estaciones de Chaltén con fetch a `/api/chalten`
- Indicador online/offline (verde/rojo) según si el último dato tiene menos de 5 minutos
- Muestra: temperatura / punto de rocío, humedad (con barra), viento / racha con flecha direccional, presión relativa y absoluta, radiación solar, UV

## Curl local

```bash
curl -s -H "Host: barimet.com.ar" http://localhost/api/estaciones
```

El reverse proxy enruta por Host header, sin él la conexión falla.

## Ver POST crudo de una estación

```bash
sudo tcpdump -i lo -A -s 0 'tcp port 8080' | grep "PASSKEY"
```

Esperar ~16 segundos. Muestra el body form-urlencoded completo con todos los parámetros en imperial.

## Logs

```bash
sudo journalctl -u barimet.service -f       # logs de FastAPI en tiempo real
sudo journalctl -u cloudflared.service -f   # logs del tunnel
```

## Usar 127.0.0.1, no localhost

En nginx (`proxy_pass`) y en cloudflared (`service:`) se usa `127.0.0.1`, nunca `localhost`. `localhost` también resuelve a `::1`, y uvicorn (8080) y nginx (80) escuchan solo en IPv4. Con `localhost`, nginx intentaba primero `[::1]:8080` en cada request y llenaba el error.log de "connection refused".

## Arranque después de un reinicio

Al arrancar, el DNS del proveedor puede tardar unos minutos. cloudflared falla hasta que el DNS responde ("server misbehaving" en el log). Por eso tiene un override en `/etc/systemd/system/cloudflared.service.d/override.conf` que le da más tiempo para arrancar y hace que reintente siempre.

## GitHub

- Repo: https://github.com/tguozden/barimet
- SSH key configurada en el servidor
