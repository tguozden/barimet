# BariMet

Sistema de recolección y visualización de datos meteorológicos para Bariloche. Recibe datos de estaciones Fine Offset vía HTTP POST y los almacena en PostgreSQL, sin necesidad de IP pública.

## Arquitectura

```
Estación meteorológica
        │
        │  POST /data/report/
        ▼
barimet.com.ar (Cloudflare)
        │
        │  Tunnel QUIC
        ▼
Servidor local (sin IP pública)
        │
        ├── cloudflared   → maneja el tunnel con Cloudflare
        ├── uvicorn       → servidor web Python
        ├── FastAPI       → recibe y procesa los datos
        └── PostgreSQL    → almacena las mediciones
```

## Requisitos

- Ubuntu 24.04
- Python 3.12
- PostgreSQL
- Cuenta en Cloudflare con dominio propio
- Estación meteorológica compatible con protocolo Wunderground/Ecowitt (Fine Offset, etc.)

## Instalación

### 1. Clonar el repositorio

```bash
git clone git@github.com:tguozden/barimet.git
cd barimet
```

### 2. Entorno virtual y dependencias

```bash
python3 -m venv ~/.venv/barimet
source ~/.venv/barimet/bin/activate
python -m pip install fastapi uvicorn python-multipart sqlalchemy psycopg2-binary python-dotenv
```

### 3. Base de datos

```bash
sudo apt install postgresql postgresql-contrib -y
sudo -u postgres psql
```

```sql
CREATE USER tuusuario WITH PASSWORD 'tupassword';
CREATE DATABASE barimet OWNER tuusuario;
\q
```

### 4. Variables de entorno

Crear el archivo `.env` en la raíz del proyecto:

```
DATABASE_URL=postgresql://tuusuario:tupassword@localhost/barimet
```

### 5. Cloudflare Tunnel

Instalar `cloudflared`:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

Autenticar y crear el tunnel:

```bash
cloudflared tunnel login
cloudflared tunnel create barimet
```

Crear `~/.cloudflared/config.yml`:

```yaml
tunnel: <ID-del-tunnel>
credentials-file: /home/tuusuario/.cloudflared/<ID>.json

ingress:
  - hostname: tudominio.com.ar
    service: http://localhost:8080
  - service: http_status:404
```

Apuntar el DNS y instalar el servicio:

```bash
cloudflared tunnel route dns barimet tudominio.com.ar
sudo cloudflared --config /home/tuusuario/.cloudflared/config.yml service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### 6. Servicio systemd para la API

Crear `/etc/systemd/system/barimet.service`:

```ini
[Unit]
Description=BariMet API
After=network.target postgresql.service

[Service]
User=tuusuario
WorkingDirectory=/home/tuusuario/barimet
ExecStart=/home/tuusuario/.venv/barimet/bin/uvicorn main:app --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable barimet
sudo systemctl start barimet
```

## Servicios del sistema

El sistema corre con tres servicios systemd:

| Servicio | Función |
|---|---|
| `cloudflared` | Tunnel entre Cloudflare e internet y el servidor local |
| `barimet` | API FastAPI que recibe los datos de las estaciones |
| `postgresql` | Base de datos |

```bash
# Ver estado
sudo systemctl status cloudflared
sudo systemctl status barimet
sudo systemctl status postgresql

# Reiniciar
sudo systemctl restart barimet
```

## Estructura del proyecto

```
barimet/
├── main.py          # API FastAPI
├── .env             # Variables de entorno (no se sube al repo)
├── .env.example     # Ejemplo de variables de entorno
└── .gitignore
```

## Configuración de la estación

En la consola de la estación Fine Offset configurar:

- **Host:** tudominio.com.ar
- **Puerto:** 80 (o 443 para HTTPS)
- **Path:** /data/report/

## Variables que se almacenan

La estación manda los datos en sistema imperial, la API los convierte automáticamente a métrico:

| Variable | Unidad |
|---|---|
| Temperatura exterior | °C |
| Temperatura interior | °C |
| Humedad exterior | % |
| Humedad interior | % |
| Velocidad del viento | km/h |
| Racha máxima | km/h |
| Dirección del viento | grados |
| Presión relativa | hPa |
| Presión absoluta | hPa |
| Lluvia (rate, hora, día, semana, mes, año) | mm |
| Radiación solar | W/m² |
| Índice UV | — |

## API

| Endpoint | Método | Descripción |
|---|---|---|
| `/data/report/` | POST | Recibe datos de las estaciones |
| `/api/ultimo` | GET | Último dato recibido |
| `/api/ultimas24` | GET | Temperatura y punto de rocío últimas 24hs |
| `/` | GET | Estado del servidor |

## Monitoreo

El estado del tunnel se puede ver en el dashboard de Cloudflare en **Zero Trust → Networks → Tunnels**.

## Logs

```bash
# Logs de la API en tiempo real
sudo journalctl -u barimet.service -f

# Logs del tunnel
sudo journalctl -u cloudflared.service -f
```
