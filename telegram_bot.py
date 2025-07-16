import os
import json
import math
import shutil
import calendar
import imgkit
from datetime import datetime, timedelta

import sqlalchemy

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ParseMode

# --- CONFIGURACIÓN PRINCIPAL ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = 1110585143
SEDE = (42.57169128484613, -0.5488306092087197)
RADIO_METROS = 100

# --- RUTAS (solo como referencia) ---
RUTA_EMPLEADOS = "datos/empleados.json"
RUTA_FICHAJES = "datos/fichajes.json"
RUTA_CALENDARIO = "datos/calendario.json"

# --- CONFIGURACIÓN DE BASE DE DATOS ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = sqlalchemy.create_engine(DATABASE_URL) if DATABASE_URL else None
metadata = sqlalchemy.MetaData()

tabla_empleados = sqlalchemy.Table('empleados', metadata,
    sqlalchemy.Column('id', sqlalchemy.String, primary_key=True),
    sqlalchemy.Column('data', sqlalchemy.JSON)
)
tabla_fichajes = sqlalchemy.Table('fichajes', metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column('data', sqlalchemy.JSON)
)
tabla_calendario = sqlalchemy.Table('calendario', metadata,
    sqlalchemy.Column('id', sqlalchemy.String, primary_key=True),
    sqlalchemy.Column('data', sqlalchemy.JSON)
)

def inicializar_db():
    if engine:
        metadata.create_all(engine)
        print("Tablas de la base de datos verificadas/creadas.")

def leer_datos(tabla):
    if not engine: return {} if tabla.name != 'fichajes' else []
    with engine.connect() as connection:
        if tabla.name == 'fichajes':
            result = connection.execute(sqlalchemy.select(tabla.c.data)).fetchall()
            return [row[0] for row in result]
        else:
            result = connection.execute(sqlalchemy.select(tabla.c.id, tabla.c.data)).fetchall()
            return {row[0]: row[1] for row in result}

def guardar_datos(tabla, datos):
    if not engine: return False
    with engine.connect() as connection:
        trans = connection.begin()
        try:
            connection.execute(tabla.delete())
            if tabla.name == 'fichajes':
                if datos: connection.execute(tabla.insert(), [{"data": d} for d in datos])
            else:
                if datos: connection.execute(tabla.insert(), [{"id": k, "data": v} for k, v in datos.items()])
            trans.commit()
            return True
        except Exception as e:
            trans.rollback()
            print(f"Error al guardar en DB en tabla {tabla.name}: {e}")
            return False

def leer_json(ruta, por_defecto):
    if 'empleados' in ruta: return leer_datos(tabla_empleados)
    if 'fichajes' in ruta: return leer_datos(tabla_fichajes)
    if 'calendario' in ruta: return leer_datos(tabla_calendario)
    return por_defecto

def guardar_json(ruta, datos):
    if 'empleados' in ruta: return guardar_datos(tabla_empleados, datos)
    if 'fichajes' in ruta: return guardar_datos(tabla_fichajes, datos)
    if 'calendario' in ruta: return guardar_datos(tabla_calendario, datos)
    return False

# --- Aquí continúa el resto del código igual ---
# (No necesitas cambiar nada más en tu archivo original)
# Pega todo el resto del código a partir de aquí, desde "def validar_usuario(user_id):" hasta el final.

def validar_usuario(user_id):
    empleados = leer_json(RUTA_EMPLEADOS, {})
    return empleados.get(str(user_id))

def tiene_entrada_abierta(uid):
    return any(f.get("id") == str(uid) and not f.get("hora_salida") for f in leer_json(RUTA_FICHAJES, []))

def distancia_metros(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Hola {user.first_name}, bienvenido al bot de Mille Miglia. Usa /menu para comenzar."
    )

# --- FUNCIÓN PRINCIPAL DE EJECUCIÓN --- #
def main():
    inicializar_db()
    if not leer_json(RUTA_EMPLEADOS, {}):
        guardar_json(RUTA_EMPLEADOS, {str(ADMIN_ID): {"nombre": "Administrador", "es_admin": True}})
    if not TOKEN:
        print("❌ TELEGRAM_TOKEN no definido en variables de entorno.")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("autorizar", autorizar))
    app.add_handler(MessageHandler(filters.LOCATION, recibir_ubicacion))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_general))
    print("✅ Bot Mille Miglia iniciado. Presiona Ctrl+C para detener.")
    app.run_polling()

if __name__ == "__main__":
    main()
