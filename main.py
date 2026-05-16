from fastapi import FastAPI, Request
from sqlalchemy import create_engine, Column, Integer, Float, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Session
from datetime import datetime, timezone, timedelta

from fastapi.responses import JSONResponse
import math

import os
from dotenv import load_dotenv
load_dotenv()
#DATABASE_URL = "postgresql://usuario:passwd@localhost/barimet"
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

class Base(DeclarativeBase):
    pass

class Medicion(Base):
    __tablename__ = "mediciones"
    id              = Column(Integer, primary_key=True)
    estacion_id     = Column(String, nullable=False)  # PASSKEY
    timestamp       = Column(DateTime(timezone=True))
    # Temperatura
    temp_c          = Column(Float)   # exterior
    temp_interior_c = Column(Float)
    # Humedad
    humedad         = Column(Integer)
    humedad_interior= Column(Integer)
    # Viento
    viento_vel      = Column(Float)   # km/h
    viento_racha    = Column(Float)   # km/h
    viento_dir      = Column(Integer) # grados
    # Presión
    presion_rel     = Column(Float)   # hPa
    presion_abs     = Column(Float)   # hPa
    # Lluvia
    lluvia_rate     = Column(Float)   # mm/h
    lluvia_hora     = Column(Float)
    lluvia_dia      = Column(Float)
    lluvia_semana   = Column(Float)
    lluvia_mes      = Column(Float)
    lluvia_anio     = Column(Float)
    # Solar
    radiacion_solar = Column(Float)   # W/m²
    uv              = Column(Integer)

Base.metadata.create_all(engine)

def f_a_c(f): return round((float(f) - 32) * 5 / 9, 1)
def mph_a_kmh(mph): return round(float(mph) * 1.60934, 1)
def in_a_mm(i): return round(float(i) * 25.4, 2)
def inhg_a_hpa(i): return round(float(i) * 33.8639, 1)

from estaciones import ESTACIONES

app = FastAPI()

async def _procesar_datos(request: Request):
    datos = await request.form()

#    print("FORM:", dict(datos))
#    print("QUERY:", dict(request.query_params))

    medicion = Medicion(
        estacion_id     = datos.get("PASSKEY"),
        timestamp       = datetime.now(timezone.utc),
        temp_c          = f_a_c(datos.get("tempf", 32)),
        temp_interior_c = f_a_c(datos.get("tempinf", 32)),
        humedad         = int(datos.get("humidity", 0)),
        humedad_interior= int(datos.get("humidityin", 0)),
        viento_vel      = mph_a_kmh(datos.get("windspeedmph", 0)),
        viento_racha    = mph_a_kmh(datos.get("windgustmph", 0)),
        viento_dir      = int(datos.get("winddir", 0)),
        presion_rel     = inhg_a_hpa(datos.get("baromrelin", 0)),
        presion_abs     = inhg_a_hpa(datos.get("baromabsin", 0)),
        lluvia_rate     = in_a_mm(datos.get("rainratein", 0)),
        lluvia_hora     = in_a_mm(datos.get("hourlyrainin", 0)),
        lluvia_dia      = in_a_mm(datos.get("dailyrainin", 0)),
        lluvia_semana   = in_a_mm(datos.get("weeklyrainin", 0)),
        lluvia_mes      = in_a_mm(datos.get("monthlyrainin", 0)),
        lluvia_anio     = in_a_mm(datos.get("yearlyrainin", 0)),
        radiacion_solar = float(datos.get("solarradiation", 0)),
        uv              = int(datos.get("uv", 0)),
    )

    with Session(engine) as session:
        session.add(medicion)
        session.commit()

    return {"ok": True}

@app.post("/data/report/")
async def recibir_datos(request: Request):
    return await _procesar_datos(request)

@app.get("/data/report")
async def recibir_datos_weewx(request: Request):
    datos = request.query_params
    medicion = Medicion(
        estacion_id     = datos.get("ID"),
        timestamp       = datetime.now(timezone.utc),
        temp_c          = f_a_c(datos.get("tempf", 32)),
        temp_interior_c = f_a_c(datos.get("tempinf", 32)),
        humedad         = int(float(datos.get("humidity", 0))),
        humedad_interior= 0,
        viento_vel      = mph_a_kmh(datos.get("windspeedmph", 0)),
        viento_racha    = mph_a_kmh(datos.get("windgustmph", 0)),
        viento_dir      = int(float(datos.get("winddir", 0))),
        presion_rel     = inhg_a_hpa(datos.get("baromin", 0)),
        presion_abs     = inhg_a_hpa(datos.get("absbaromin", datos.get("baromin", 0))),
        lluvia_rate     = in_a_mm(datos.get("rainratein", 0)),
        lluvia_hora     = in_a_mm(datos.get("rainin", 0)),
        lluvia_dia      = in_a_mm(datos.get("dailyrainin", 0)),
        lluvia_semana   = 0,
        lluvia_mes      = 0,
        lluvia_anio     = 0,
        radiacion_solar = float(datos.get("solarradiation", 0)),
        uv              = int(float(datos.get("UV", 0))),
    )
    with Session(engine) as session:
        session.add(medicion)
        session.commit()
    return {"ok": True}

@app.get("/")
def home():
    return {"status": "BariMet online"}

def punto_rocio(temp_c, humedad, presion_hpa=1013.25):
    es = presion_hpa * 0.61078 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
    e = (humedad / 100.0) * es
    td = (237.3 * math.log(e / (presion_hpa * 0.61078))) / (17.27 - math.log(e / (presion_hpa * 0.61078)))
    return round(td, 1)

@app.get("/api/ultimo")
def ultimo_dato():
    with Session(engine) as session:
        m = session.query(Medicion).order_by(Medicion.timestamp.desc()).first()
        if not m:
            return JSONResponse(status_code=404, content={"error": "sin datos"})
        return {
            "timestamp": m.timestamp.isoformat(),
            "temp_c": m.temp_c,
            "humedad": m.humedad,
            "rocio": punto_rocio(m.temp_c, m.humedad),
            "viento_vel": m.viento_vel,
            "viento_dir": m.viento_dir,
            "presion_rel": m.presion_rel,
            "radiacion_solar": m.radiacion_solar,
            "uv": m.uv,
        }

@app.get("/api/ultimas24")
def ultimas_24hs():
    with Session(engine) as session:
        desde = datetime.now(timezone.utc) - timedelta(hours=24)
        mediciones = session.query(Medicion).filter(
            Medicion.timestamp >= desde
        ).order_by(Medicion.timestamp.asc()).all()
        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "temp_c": m.temp_c,
                "rocio": punto_rocio(m.temp_c, m.humedad),
            }
            for m in mediciones
        ]

@app.get("/api/estaciones")
def todas_estaciones():
    with Session(engine) as session:
        # Subconsulta: último timestamp por estación
        from sqlalchemy import func
        ultimos = (
            session.query(
                Medicion.estacion_id,
                func.max(Medicion.timestamp).label("ultimo")
            )
            .group_by(Medicion.estacion_id)
            .subquery()
        )
        # Join para traer todos los datos de esa fila
        mediciones = (
            session.query(Medicion)
            .join(ultimos, (Medicion.estacion_id == ultimos.c.estacion_id) & 
                           (Medicion.timestamp == ultimos.c.ultimo))
            .all()
        )
        resultado = []
        for m in mediciones:
            info = ESTACIONES.get(m.estacion_id, {})
            resultado.append({
                "nombre": info.get("nombre", m.estacion_id),
                "altura": info.get("altura"),
                "timestamp": m.timestamp.isoformat(),
                "temp_c": m.temp_c,
                "humedad": m.humedad,
                "rocio": punto_rocio(m.temp_c, m.humedad, m.presion_rel),
                "viento_vel": m.viento_vel,
                "viento_racha": m.viento_racha,
                "viento_dir": m.viento_dir,
                "presion_rel": m.presion_rel,
                "presion_abs": m.presion_abs,
                "radiacion_solar": m.radiacion_solar,
                "uv": m.uv,
            })
        return resultado
