from fastapi import FastAPI, Request
from sqlalchemy import create_engine, Column, Integer, Float, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Session
from datetime import datetime, timezone

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
    vin             = Column(Float)   # Voltaje batería (V)

Base.metadata.create_all(engine)

def f_a_c(f): return round((float(f) - 32) * 5 / 9, 1)
def mph_a_kmh(mph): return round(float(mph) * 1.60934, 1)
def in_a_mm(i): return round(float(i) * 25.4, 2)
def inhg_a_hpa(i): return round(float(i) * 33.8639, 1)
def entero(x): return int(float(x))

def valor(datos, clave, conv=float):
    """campo convertido, o None si la estación no lo mandó (por ej. sensor exterior caído)"""
    v = datos.get(clave)
    if v is None or v == '' or float(v) == -9999:
        return None
    return conv(v)

from estaciones import ESTACIONES, CHALTEN

CHALTEN_PASSKEYS = set(CHALTEN.keys())

app = FastAPI()

async def _procesar_datos(request: Request):
    datos = await request.form()

    vin_raw = datos.get("vin") or datos.get("Vin")
    medicion = Medicion(
        estacion_id     = datos.get("PASSKEY"),
        timestamp       = datetime.now(timezone.utc),
        temp_c          = valor(datos, "tempf", f_a_c),
        temp_interior_c = valor(datos, "tempinf", f_a_c),
        humedad         = valor(datos, "humidity", entero),
        humedad_interior= valor(datos, "humidityin", entero),
        viento_vel      = valor(datos, "windspeedmph", mph_a_kmh),
        viento_racha    = valor(datos, "windgustmph", mph_a_kmh),
        viento_dir      = valor(datos, "winddir", entero),
        presion_rel     = valor(datos, "baromrelin", inhg_a_hpa),
        presion_abs     = valor(datos, "baromabsin", inhg_a_hpa),
        lluvia_rate     = valor(datos, "rainratein", in_a_mm),
        lluvia_hora     = valor(datos, "hourlyrainin", in_a_mm),
        lluvia_dia      = valor(datos, "dailyrainin", in_a_mm),
        lluvia_semana   = valor(datos, "weeklyrainin", in_a_mm),
        lluvia_mes      = valor(datos, "monthlyrainin", in_a_mm),
        lluvia_anio     = valor(datos, "yearlyrainin", in_a_mm),
        radiacion_solar = valor(datos, "solarradiation"),
        uv              = valor(datos, "uv" if "uv" in datos else "UV", entero),  # china manda "UV"
        vin            = float(vin_raw) if vin_raw else None,
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
        temp_c          = valor(datos, "tempf", f_a_c),
        temp_interior_c = valor(datos, "tempinf", f_a_c),
        humedad         = valor(datos, "humidity", entero),
        humedad_interior= None,
        viento_vel      = valor(datos, "windspeedmph", mph_a_kmh),
        viento_racha    = valor(datos, "windgustmph", mph_a_kmh),
        viento_dir      = valor(datos, "winddir", entero),
        presion_rel     = valor(datos, "baromin", inhg_a_hpa),
        presion_abs     = valor(datos, "absbaromin", inhg_a_hpa) or valor(datos, "baromin", inhg_a_hpa),
        lluvia_rate     = valor(datos, "rainratein", in_a_mm),
        lluvia_hora     = valor(datos, "rainin", in_a_mm),
        lluvia_dia      = valor(datos, "dailyrainin", in_a_mm),
        lluvia_semana   = None,
        lluvia_mes      = None,
        lluvia_anio     = None,
        radiacion_solar = valor(datos, "solarradiation"),
        uv              = valor(datos, "UV", entero),
    )
    with Session(engine) as session:
        session.add(medicion)
        session.commit()
    return {"ok": True}

@app.get("/")
def home():
    return {"status": "BariMet online"}

def punto_rocio(temp_c, humedad, presion_hpa=None):
    if temp_c is None or humedad is None or humedad <= 0:
        return None
    gamma = (17.27 * temp_c) / (temp_c + 237.3) + math.log(humedad / 100.0)
    return round(237.3 * gamma / (17.27 - gamma), 1)

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
        mediciones_dict = {m.estacion_id: m for m in mediciones}
        resultado = []
        vistos = set()
        for estacion_id, info in ESTACIONES.items():
            m = mediciones_dict.get(estacion_id)
            if not m:
                continue
            vistos.add(estacion_id)
            resultado.append({
                "nombre": info.get("nombre", estacion_id),
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
                "vin": m.vin,
            })
        for m in mediciones:
            if m.estacion_id not in vistos and m.estacion_id not in CHALTEN_PASSKEYS:
                resultado.append({
                    "nombre": m.estacion_id,
                    "altura": None,
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
                    "vin": m.vin,
                })
        return resultado

@app.get("/api/chalten")
def estaciones_chalten():
    with Session(engine) as session:
        from sqlalchemy import func
        ultimos = (
            session.query(
                Medicion.estacion_id,
                func.max(Medicion.timestamp).label("ultimo")
            )
            .group_by(Medicion.estacion_id)
            .subquery()
        )
        mediciones = (
            session.query(Medicion)
            .join(ultimos, (Medicion.estacion_id == ultimos.c.estacion_id) & 
                           (Medicion.timestamp == ultimos.c.ultimo))
            .all()
        )
        mediciones_dict = {m.estacion_id: m for m in mediciones}
        resultado = []
        for estacion_id, info in CHALTEN.items():
            m = mediciones_dict.get(estacion_id)
            if not m:
                continue
            resultado.append({
                "nombre": info.get("nombre", estacion_id),
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
                "vin": m.vin,
            })
        return resultado
