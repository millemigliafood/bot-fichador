import os
import json
import math
import shutil
import calendar
import imgkit
from datetime import datetime, timedelta

# Librerías nuevas para la base de datos
import sqlalchemy

# Asegúrate de tener instalada la librería: pip install python-telegram-bot
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ParseMode

# --- CONFIGURACIÓN PRINCIPAL ---
TOKEN = "8174097868:AAFzP4wkQFh9gxJhir0rIo5I-Q9JEfsADZ4"
ADMIN_ID = 1110585143
SEDE = (42.57169128484613, -0.5488306092087197)
RADIO_METROS = 100

# --- RUTAS (ahora solo como referencia) ---
RUTA_EMPLEADOS = "datos/empleados.json"
RUTA_FICHAJES = "datos/fichajes.json"
RUTA_CALENDARIO = "datos/calendario.json"

# --- CONFIGURACIÓN DE BASE DE DATOS ---
DATABASE_URL = os.environ.get("DATABASE_URL")
# Corrección para Render: SQLAlchemy espera 'postgresql://' en lugar de 'postgres://'
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = sqlalchemy.create_engine(DATABASE_URL) if DATABASE_URL else None
metadata = sqlalchemy.MetaData()

# Definimos la estructura de nuestras "tablas" en la base de datos
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
    """Crea las tablas en la base de datos si no existen."""
    if engine:
        metadata.create_all(engine)
        print("Tablas de la base de datos verificadas/creadas.")

# --- NUEVAS FUNCIONES DE UTILIDAD (para leer y escribir en la DB) ---

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

# El resto del código usará estas funciones sin saber que está usando una DB
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

# --- FUNCIONES DE LÓGICA DEL BOT (Sin cambios) ---
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

# --- COMANDOS DEL BOT (Sin cambios) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    empleado = validar_usuario(user.id)
    if not empleado:
        await update.message.reply_text("⛔ *Usuario no autorizado.*\nContacta con un administrador.", parse_mode=ParseMode.MARKDOWN)
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ *Intento de acceso no autorizado:*\nID: `{user.id}`\nNombre: {user.full_name}\n\nUsa:\n`/autorizar {user.id} Nombre Apellido`",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Error notificando al admin: {e}")
        return
    await mostrar_menu(update, empleado)

async def autorizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ Solo para administradores.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Uso: `/autorizar ID_USUARIO Nombre Apellido`")
        return
    nuevo_id, nombre = context.args[0], " ".join(context.args[1:])
    empleados = leer_json(RUTA_EMPLEADOS, {})
    if nuevo_id in empleados:
        await update.message.reply_text(f"⚠️ El usuario `{nuevo_id}` ya está autorizado.")
        return
    empleados[nuevo_id] = {"nombre": nombre, "es_admin": False}
    if guardar_json(RUTA_EMPLEADOS, empleados):
        await update.message.reply_text(f"✅ Usuario *{nombre}* (`{nuevo_id}`) autorizado.", parse_mode=ParseMode.MARKDOWN)
        try:
            await context.bot.send_message(chat_id=int(nuevo_id), text="🎉 ¡Has sido autorizado! Escribe /start.")
        except Exception as e:
            print(f"No se pudo notificar al nuevo usuario {nuevo_id}: {e}")
    else:
        await update.message.reply_text("❌ Error al guardar los datos.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    empleado = validar_usuario(update.effective_user.id)
    if empleado:
        await mostrar_menu(update, empleado)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) == str(ADMIN_ID):
        await update.message.reply_text("🛑 Deteniendo el bot...")
        await context.application.shutdown()
    else:
        await update.message.reply_text("⛔ Solo el administrador puede detener el bot.")

# --- INTERFAZ DEL BOT (Sin cambios) ---
async def mostrar_menu(update: Update, empleado: dict):
    uid = str(update.effective_user.id)
    botones_base = [["📅 Horas por mes", "📊 Resumen"]]
    if empleado.get("es_admin"):
        botones_base.extend([["🔍 Ver fichajes detallados"], ["✍️ Fichaje manual", "📑 Planificar turnos"]])
    
    fichar_btn = ["🏁 Fichar salida"] if tiene_entrada_abierta(uid) else ["📍 Fichar entrada"]
    botones = [fichar_btn] + botones_base
    markup = ReplyKeyboardMarkup(botones, resize_keyboard=True)
    await update.message.reply_text(f"👋 Hola {empleado.get('nombre', '')}, ¿qué deseas hacer?", reply_markup=markup)

async def limpiar_y_mostrar_menu(context, update, empleado):
    context.user_data.clear()
    await mostrar_menu(update, empleado)

# --- MANEJADOR PRINCIPAL DE MENSAJES (Sin cambios) ---
async def mensaje_general(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    empleado = validar_usuario(user.id)
    if not empleado:
        await start(update, context)
        return

    texto = update.message.text
    context.user_data['empleado'] = empleado
    siguiente_accion = context.user_data.get("siguiente_accion")

    if not siguiente_accion:
        if texto in ["📍 Fichar entrada", "🏁 Fichar salida"]:
            context.user_data["siguiente_accion"] = "recibir_ubicacion"
            context.user_data["accion_fichaje"] = "entrada" if texto == "📍 Fichar entrada" else "salida"
            await update.message.reply_text(f"Para fichar tu *{context.user_data['accion_fichaje']}*, comparte tu ubicación.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 Enviar mi ubicación actual", request_location=True)]], resize_keyboard=True, one_time_keyboard=True))
            return
        
        if texto == "📅 Horas por mes":
            if empleado.get("es_admin"):
                context.user_data["siguiente_accion"] = "procesar_horas_mes_admin"
                await update.message.reply_text("📆 ¿De qué mes quieres ver el resumen de TODOS los empleados? (Ej: 07/2025 o julio)")
            else:
                context.user_data["siguiente_accion"] = "pedir_mes_calendario"
                await update.message.reply_text("📅 ¿De qué mes quieres ver tu calendario laboral? (Ej: 07/2025 o julio)")
            return

        if texto == "📊 Resumen":
            context.user_data["siguiente_accion"] = "resumen_pedir_fecha_inicio"
            await update.message.reply_text("🗓️ Introduce la fecha de inicio para tu resumen (DD/MM/AAAA):", reply_markup=ReplyKeyboardRemove())
            return

        if empleado.get("es_admin"):
            if texto == "🔍 Ver fichajes detallados":
                empleados_lista = [(k, v["nombre"]) for k, v in leer_json(RUTA_EMPLEADOS, {}).items()]
                botones = [[KeyboardButton(f"{nombre} ({eid})")] for eid, nombre in empleados_lista] + [[KeyboardButton("❌ Cancelar")]]
                context.user_data["siguiente_accion"] = "seleccionar_empleado_fichajes"
                await update.message.reply_text("👤 Selecciona el empleado:", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
                return
            if texto == "✍️ Fichaje manual":
                empleados_lista = [(k, v["nombre"]) for k, v in leer_json(RUTA_EMPLEADOS, {}).items()]
                botones = [[KeyboardButton(f"{nombre} ({eid})")] for eid, nombre in empleados_lista] + [[KeyboardButton("❌ Cancelar")]]
                context.user_data["siguiente_accion"] = "fichaje_manual_seleccionar_empleado"
                await update.message.reply_text("👤 ¿Para qué empleado quieres añadir un fichaje manual?", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
                return
            if texto == "📑 Planificar turnos":
                empleados_lista = [(k, v["nombre"]) for k, v in leer_json(RUTA_EMPLEADOS, {}).items()]
                botones = [[KeyboardButton(f"{nombre} ({eid})")] for eid, nombre in empleados_lista] + [[KeyboardButton("❌ Cancelar")]]
                context.user_data["siguiente_accion"] = "planificar_seleccionar_empleado"
                await update.message.reply_text("👤 Selecciona el empleado para planificar su calendario:", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
                return
        
        await mostrar_menu(update, empleado)
        return

    if texto == "❌ Cancelar":
        return await limpiar_y_mostrar_menu(context, update, empleado)

    if siguiente_accion == "pedir_mes_calendario":
        mes_input = texto.strip().lower()
        mes, anio = parse_mes_anio(mes_input)
        if not (mes and anio):
            await update.message.reply_text("❌ Formato no válido. Usa MM/AAAA o 'julio 2025'.")
        else:
            await update.message.reply_text("⚙️ Un momento, estoy generando tu calendario...")
            try:
                uid = str(user.id)
                nombre_empleado = empleado.get("nombre", "")
                ruta_imagen = await generar_imagen_calendario(uid, nombre_empleado, anio, mes)
                if ruta_imagen:
                    with open(ruta_imagen, 'rb') as photo_file:
                        await update.message.reply_photo(photo=photo_file)
                    os.remove(ruta_imagen)
                else:
                    await update.message.reply_text("📭 No tienes turnos planificados para ese mes.")
            except Exception as e:
                await update.message.reply_text(f"❌ Ocurrió un error al generar la imagen. Asegúrate de que 'wkhtmltoimage' está instalado y accesible en el sistema.\nError: {e}")
        return await limpiar_y_mostrar_menu(context, update, empleado)

    if siguiente_accion == "resumen_pedir_fecha_inicio":
        try:
            context.user_data["resumen_fecha_inicio"] = datetime.strptime(texto, "%d/%m/%Y").date()
            context.user_data["siguiente_accion"] = "resumen_pedir_fecha_fin"
            await update.message.reply_text("🗓️ Introduce la fecha de fin (DD/MM/AAAA):")
        except ValueError:
            await update.message.reply_text("❌ Formato de fecha incorrecto.")
        return await limpiar_y_mostrar_menu(context, update, empleado)

    if siguiente_accion == "resumen_pedir_fecha_fin":
        try:
            fecha_fin = datetime.strptime(texto, "%d/%m/%Y").date()
            fecha_inicio = context.user_data["resumen_fecha_inicio"]
            uid = str(user.id)
            nombre_empleado = empleado.get("nombre")
            descripcion = f"del {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}"
            await mostrar_fichajes_por_fecha(update, context, uid, nombre_empleado, fecha_inicio, fecha_fin, descripcion)
        except ValueError:
            await update.message.reply_text("❌ Formato de fecha incorrecto.")
        return await limpiar_y_mostrar_menu(context, update, empleado)
    
    if siguiente_accion == "seleccionar_empleado_fichajes":
        if texto.endswith(")") and "(" in texto:
            nombre, eid = texto.rsplit("(", 1)
            context.user_data["fichaje_empleado_id"] = eid.replace(")", "").strip()
            context.user_data["fichaje_empleado_nombre"] = nombre.strip()
            context.user_data["siguiente_accion"] = "seleccionar_periodo_fichajes"
            botones = [["📅 Hoy", "🗓️ Ayer"], ["📆 Esta semana", "📆 Este mes"], ["🗓️ Mes específico", "🔎 Fecha específica"], ["❌ Cancelar"]]
            await update.message.reply_text(f"📅 Selecciona el período para {nombre.strip()}:", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
        else: await update.message.reply_text("❗ Usa los botones.")
        return

    if siguiente_accion == "seleccionar_periodo_fichajes":
        emp_id, emp_nombre = context.user_data["fichaje_empleado_id"], context.user_data["fichaje_empleado_nombre"]
        hoy = datetime.now().date()
        periodos = {"📅 Hoy": (hoy, hoy, "hoy"), "🗓️ Ayer": (hoy - timedelta(1), hoy - timedelta(1), "ayer"), "📆 Esta semana": (hoy - timedelta(hoy.weekday()), hoy, "esta semana"), "📆 Este mes": (hoy.replace(day=1), hoy, "este mes")}
        if texto in periodos:
            await mostrar_fichajes_por_fecha(update, context, emp_id, emp_nombre, *periodos[texto])
        elif texto == "🔎 Fecha específica":
            context.user_data["siguiente_accion"] = "pedir_fecha_especifica"
            await update.message.reply_text("📆 Introduce la fecha (DD/MM/AAAA):", reply_markup=ReplyKeyboardRemove())
        elif texto == "🗓️ Mes específico":
            context.user_data["siguiente_accion"] = "pedir_mes_especifico"
            await update.message.reply_text("📆 Introduce el mes (MM/AAAA o 'junio'):", reply_markup=ReplyKeyboardRemove())
        else: await update.message.reply_text("❗ Opción no válida.")
        return

    if siguiente_accion == "pedir_fecha_especifica":
        try:
            fecha = datetime.strptime(texto, "%d/%m/%Y").date()
            await mostrar_fichajes_por_fecha(update, context, context.user_data["fichaje_empleado_id"], context.user_data["fichaje_empleado_nombre"], fecha, fecha, texto)
        except ValueError:
            await update.message.reply_text("❌ Formato de fecha incorrecto.")
        return await limpiar_y_mostrar_menu(context, update, empleado)

    if siguiente_accion == "pedir_mes_especifico":
        mes, anio = parse_mes_anio(texto)
        if not (mes and anio):
            await update.message.reply_text("❌ Formato no válido. Usa MM/AAAA o 'junio 2025'.")
        else:
            primer_dia = datetime(anio, mes, 1).date()
            ultimo_dia = (primer_dia.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            await mostrar_fichajes_por_fecha(update, context, context.user_data["fichaje_empleado_id"], context.user_data["fichaje_empleado_nombre"], primer_dia, ultimo_dia, f"{mes:02d}/{anio}")
        return

    if siguiente_accion == "procesar_horas_mes_admin":
        await procesar_horas_mes_admin(update, context, texto)
        return

    if siguiente_accion == "fichaje_manual_seleccionar_empleado":
        if texto.endswith(")") and "(" in texto:
            nombre, eid = texto.rsplit("(", 1)
            context.user_data["manual_empleado_id"] = eid.replace(")", "").strip()
            context.user_data["manual_empleado_nombre"] = nombre.strip()
            context.user_data["siguiente_accion"] = "fichaje_manual_pedir_fecha"
            await update.message.reply_text(f"📆 Introduce la fecha para el fichaje de {nombre.strip()} (DD/MM/AAAA):", reply_markup=ReplyKeyboardRemove())
        else: await update.message.reply_text("❗ Usa los botones.")
        return

    if siguiente_accion == "fichaje_manual_pedir_fecha":
        try:
            context.user_data["manual_fecha"] = datetime.strptime(texto, "%d/%m/%Y").strftime("%Y-%m-%d")
            context.user_data["siguiente_accion"] = "fichaje_manual_pedir_entrada"
            await update.message.reply_text("🕒 Introduce la hora de entrada (HH:MM):")
        except ValueError: await update.message.reply_text("❌ Formato de fecha incorrecto. Vuelve a empezar.")
        return

    if siguiente_accion == "fichaje_manual_pedir_entrada":
        try:
            context.user_data["manual_entrada"] = datetime.strptime(texto, "%H:%M").strftime("%H:%M:%S")
            context.user_data["siguiente_accion"] = "fichaje_manual_pedir_salida"
            await update.message.reply_text("🕡 Introduce la hora de salida (HH:MM):")
        except ValueError: await update.message.reply_text("❌ Formato de hora incorrecto. Vuelve a empezar.")
        return

    if siguiente_accion == "fichaje_manual_pedir_salida":
        try:
            context.user_data["manual_salida"] = datetime.strptime(texto, "%H:%M").strftime("%H:%M:%S")
            context.user_data["siguiente_accion"] = "fichaje_manual_confirmar"
            msg = (f"Vas a añadir este fichaje:\n"
                   f"👤 *Empleado:* {context.user_data['manual_empleado_nombre']}\n"
                   f"📅 *Fecha:* {datetime.strptime(context.user_data['manual_fecha'], '%Y-%m-%d').strftime('%d/%m/%Y')}\n"
                   f"🕒 *Entrada:* {context.user_data['manual_entrada']}\n"
                   f"🕡 *Salida:* {context.user_data['manual_salida']}\n\n¿Es correcto?")
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup([["✅ Sí", "❌ No"]], resize_keyboard=True))
        except ValueError: await update.message.reply_text("❌ Formato de hora incorrecto. Vuelve a empezar.")
        return

    if siguiente_accion == "fichaje_manual_confirmar":
        if texto == "✅ Sí":
            fichajes = leer_json(RUTA_FICHAJES, [])
            fichajes.append({
                "id": context.user_data["manual_empleado_id"], "nombre": context.user_data["manual_empleado_nombre"],
                "fecha": context.user_data["manual_fecha"], "hora_entrada": context.user_data["manual_entrada"],
                "hora_salida": context.user_data["manual_salida"]
            })
            guardar_json(RUTA_FICHAJES, fichajes)
            await update.message.reply_text("✅ Fichaje manual añadido con éxito.")
        else: await update.message.reply_text("❌ Operación cancelada.")
        return await limpiar_y_mostrar_menu(context, update, empleado)

    if siguiente_accion == "planificar_seleccionar_empleado":
        if texto.endswith(")") and "(" in texto:
            nombre, eid = texto.rsplit("(", 1)
            context.user_data["plan_empleado_id"] = eid.replace(")", "").strip()
            context.user_data["plan_empleado_nombre"] = nombre.strip()
            context.user_data["siguiente_accion"] = "planificar_pedir_mes"
            await update.message.reply_text(f"📆 Introduce el mes a planificar para {nombre.strip()} (MM/AAAA):", reply_markup=ReplyKeyboardRemove())
        else: await update.message.reply_text("❗ Usa los botones.")
        return

    if siguiente_accion == "planificar_pedir_mes":
        mes, anio = parse_mes_anio(texto)
        if not (mes and anio):
            await update.message.reply_text("❌ Formato no válido. Usa MM/AAAA o 'julio 2025'.")
        else:
            context.user_data["plan_mes"] = mes
            context.user_data["plan_anio"] = anio
            context.user_data["siguiente_accion"] = "planificar_pedir_datos"
            await update.message.reply_text(f"✍️ Introduce los turnos para {context.user_data['plan_empleado_nombre']} en {mes:02d}/{anio}.\n\n*Formato:* `dia=turno`, separados por comas.\n*Ejemplo:* `1=Mañana, 2=Tarde, 3=Libre, 15=Vacaciones`", parse_mode=ParseMode.MARKDOWN)
        return

    if siguiente_accion == "planificar_pedir_datos":
        try:
            turnos_nuevos = {}
            entradas = [e.strip() for e in texto.split(',')]
            for entrada in entradas:
                dia, turno = entrada.split('=', 1)
                turnos_nuevos[f"{int(dia):02d}"] = turno.strip()
            
            calendario = leer_json(RUTA_CALENDARIO, {})
            clave_mes = f"{context.user_data['plan_anio']}-{context.user_data['plan_mes']:02d}"
            uid = context.user_data['plan_empleado_id']

            if clave_mes not in calendario: calendario[clave_mes] = {}
            if uid not in calendario[clave_mes]: calendario[clave_mes][uid] = {}
            
            calendario[clave_mes][uid].update(turnos_nuevos)
            guardar_json(RUTA_CALENDARIO, calendario)
            await update.message.reply_text(f"✅ Calendario actualizado para {context.user_data['plan_empleado_nombre']}.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error de formato. Asegúrate de usar `dia=turno, dia=turno`.\nError: {e}")
        return await limpiar_y_mostrar_menu(context, update, empleado)

# --- MANEJADOR DE UBICACIÓN (Sin cambios) ---
async def recibir_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("siguiente_accion") != "recibir_ubicacion": return
    
    user, empleado = update.effective_user, validar_usuario(update.effective_user.id)
    if not empleado: return

    accion = context.user_data.get("accion_fichaje")
    distancia = distancia_metros(update.message.location.latitude, update.message.location.longitude, *SEDE)
    
    if distancia > RADIO_METROS:
        await update.message.reply_text(f"❌ *Estás demasiado lejos* ({int(distancia)}m).", parse_mode=ParseMode.MARKDOWN)
        return await limpiar_y_mostrar_menu(context, update, empleado)

    fichajes, ahora = leer_json(RUTA_FICHAJES, []), datetime.now()
    
    if accion == "entrada":
        if tiene_entrada_abierta(user.id):
            await update.message.reply_text("⚠️ Ya tienes una entrada registrada.")
        else:
            fichajes.append({"id": str(user.id), "nombre": empleado.get("nombre"), "fecha": ahora.strftime("%Y-%m-%d"), "hora_entrada": ahora.strftime("%H:%M:%S"), "hora_salida": None})
            guardar_json(RUTA_FICHAJES, fichajes)
            await update.message.reply_text(f"✅ Entrada registrada a las *{ahora.strftime('%H:%M:%S')}*.", parse_mode=ParseMode.MARKDOWN)
    elif accion == "salida":
        actualizado = False
        for f in reversed(fichajes):
            if f.get("id") == str(user.id) and not f.get("hora_salida"):
                f["hora_salida"] = ahora.strftime("%H:%M:%S")
                guardar_json(RUTA_FICHAJES, fichajes)
                await update.message.reply_text(f"✅ Salida registrada a las *{ahora.strftime('%H:%M:%S')}*.", parse_mode=ParseMode.MARKDOWN)
                actualizado = True
                break
        if not actualizado: await update.message.reply_text("❌ No se encontró una entrada abierta.")
    
    await limpiar_y_mostrar_menu(context, update, empleado)

# --- FUNCIONES DE VISUALIZACIÓN Y LÓGICA (Sin cambios) ---
def parse_mes_anio(texto: str) -> tuple[int | None, int | None]:
    texto = texto.strip().lower()
    meses = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    mes, anio = None, None
    try:
        if "/" in texto:
            mes, anio = map(int, texto.split("/"))
        else:
            for nombre_mes, num_mes in meses.items():
                if nombre_mes in texto:
                    mes = num_mes
                    anio_str = texto.replace(nombre_mes, "").strip()
                    anio = int(anio_str) if anio_str else datetime.now().year
                    break
        if anio and 1 <= mes <= 12:
            return mes, anio
    except (ValueError, IndexError):
        pass
    return None, None

async def mostrar_fichajes_por_fecha(update, context, emp_id, emp_nombre, fecha_inicio, fecha_fin, descripcion):
    fichajes = leer_json(RUTA_FICHAJES, [])
    fichajes_filtrados = sorted([f for f in fichajes if f.get("id") == emp_id and fecha_inicio.strftime("%Y-%m-%d") <= f.get("fecha", "") <= fecha_fin.strftime("%Y-%m-%d")], key=lambda x: (x.get("fecha", ""), x.get("hora_entrada", "")))
    
    if not fichajes_filtrados:
        await update.message.reply_text(f"📭 No se encontraron fichajes para {emp_nombre} en {descripcion}.")
    else:
        fichajes_por_fecha, total_minutos_periodo = {}, 0
        for f in fichajes_filtrados: fichajes_por_fecha.setdefault(f.get("fecha"), []).append(f)
        
        mensaje = f"📋 *Fichajes de {emp_nombre} ({descripcion})*\n\n"
        for fecha, fichajes_dia in sorted(fichajes_por_fecha.items()):
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
            mensaje += f"📅 *{['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][fecha_obj.weekday()]} {fecha_obj.strftime('%d/%m/%Y')}*\n"
            total_minutos_dia = 0
            for f in fichajes_dia:
                entrada, salida = f.get("hora_entrada", "N/A"), f.get("hora_salida", "N/A")
                tiempo_trabajado = ""
                if entrada != "N/A" and salida != "N/A":
                    try:
                        t_entrada = datetime.strptime(entrada, "%H:%M:%S")
                        t_salida = datetime.strptime(salida, "%H:%M:%S")
                        delta = t_salida - t_entrada if t_salida > t_entrada else (t_salida + timedelta(days=1)) - t_entrada
                        minutos = int(delta.total_seconds() / 60)
                        if minutos >= 0:
                            total_minutos_dia += minutos
                            tiempo_trabajado = f" ⏱️ *{minutos // 60}h {minutos % 60:02d}m*"
                    except ValueError: tiempo_trabajado = " ⚠️"
                mensaje += f"  • {entrada.split(':')[0]}:{entrada.split(':')[1]} → {salida.split(':')[0]}:{salida.split(':')[1]}{tiempo_trabajado}\n"
            if total_minutos_dia > 0:
                total_minutos_periodo += total_minutos_dia
                mensaje += f"  *Total día: {total_minutos_dia // 60}h {total_minutos_dia % 60:02d}m*\n"
            mensaje += "\n"
        
        if total_minutos_periodo > 0:
            h_total, m_total = divmod(total_minutos_periodo, 60)
            mensaje += f"------------------------------------\n"
            mensaje += f"📊 *Total del período ({descripcion}): {h_total}h {m_total:02d}m*"

        for i in range(0, len(mensaje), 4096): await update.message.reply_text(mensaje[i:i + 4096], parse_mode=ParseMode.MARKDOWN)
    
    await limpiar_y_mostrar_menu(context, update, context.user_data.get('empleado'))

async def procesar_horas_mes_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, mes_input: str):
    mes, anio = parse_mes_anio(mes_input)
    if not (mes and anio):
        return await update.message.reply_text("❌ Formato no válido. Usa MM/AAAA o 'julio 2025'.")

    resumen = {}
    for f in leer_json(RUTA_FICHAJES, []):
        try:
            fecha_fichaje = datetime.strptime(f["fecha"], "%Y-%m-%d")
            if fecha_fichaje.month == mes and fecha_fichaje.year == anio and f.get("hora_salida"):
                emp_id = f["id"]
                if emp_id not in resumen: resumen[emp_id] = {"nombre": f.get("nombre", "N/A"), "total_min": 0}
                
                t_entrada = datetime.strptime(f["hora_entrada"], "%H:%M:%S")
                t_salida = datetime.strptime(f["hora_salida"], "%H:%M:%S")
                delta = t_salida - t_entrada if t_salida > t_entrada else (t_salida + timedelta(days=1)) - t_entrada
                minutos = int(delta.total_seconds() / 60)

                if minutos > 0: resumen[emp_id]["total_min"] += minutos
        except (ValueError, KeyError): continue

    if not resumen: await update.message.reply_text(f"📭 No hay fichajes para {mes:02d}/{anio}.")
    else:
        msg = f"📊 *Resumen de horas para {mes:02d}/{anio}*\n\n"
        total_general_min = 0
        for emp_id, data in sorted(resumen.items(), key=lambda item: item[1]['nombre']):
            horas, minutos = divmod(data["total_min"], 60)
            total_general_min += data["total_min"]
            msg += f"👤 *{data['nombre']}*: {horas}h {minutos:02d}m\n"
        
        h_total, m_total = divmod(total_general_min, 60)
        msg += f"\n------------------------------------\n"
        msg += f"📊 *Total general del mes: {h_total}h {m_total:02d}m*"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    
    await limpiar_y_mostrar_menu(context, update, context.user_data.get('empleado'))

async def generar_imagen_calendario(uid: str, nombre_empleado: str, anio: int, mes: int) -> str | None:
    calendario_completo = leer_json(RUTA_CALENDARIO, {})
    clave_mes = f"{anio}-{mes:02d}"
    
    turnos_empleado = calendario_completo.get(clave_mes, {}).get(uid)
    if not turnos_empleado:
        return None

    html_style = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f9f9f9; padding: 10px; }
        .container { border: 1px solid #ddd; border-radius: 8px; background-color: white; padding: 20px; max-width: 650px; margin: auto; box-shadow: 0 4px 8px rgba(0,0,0,0.05); }
        .header { text-align: center; margin-bottom: 20px; border-bottom: 1px solid #eee; padding-bottom: 15px; }
        .header h2 { margin: 0; color: #333; font-size: 24px; }
        .header p { margin: 5px; color: #555; font-size: 16px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #e9e9e9; padding: 8px; text-align: left; }
        th { background-color: #f7f7f7; color: #555; font-weight: 600; font-size: 12px; text-transform: uppercase; }
        td { height: 70px; vertical-align: top; }
        .day-number { font-weight: 600; font-size: 14px; color: #333; }
        .turno { font-size: 13px; color: #0056b3; display: block; margin-top: 5px; font-weight: 500; }
        .finde { background-color: #fafafa; }
        .otro-mes { color: #ccc; background-color: #fdfdfd; }
        .hoy .day-number { color: white; background-color: #007bff; border-radius: 50%; width: 24px; height: 24px; display: inline-block; text-align: center; line-height: 24px;}
    </style>
    """
    nombre_mes_str = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][mes-1]
    html_content = f"""
    <html><head><meta charset="UTF-8">{html_style}</head><body><div class="container">
        <div class="header"><h2>Calendario Laboral</h2><p>{nombre_empleado} &ndash; {nombre_mes_str} {anio}</p></div>
        <table><tr><th>Lunes</th><th>Martes</th><th>Miércoles</th><th>Jueves</th><th>Viernes</th><th>Sábado</th><th>Domingo</th></tr>
    """
    cal = calendar.monthcalendar(anio, mes)
    hoy = datetime.now()
    for semana in cal:
        html_content += "<tr>"
        for dia in semana:
            clase_css = []
            if dia != 0 and calendar.weekday(anio, mes, dia) >= 5: clase_css.append("finde")
            if dia == 0:
                html_content += f"<td class='otro-mes'></td>"
            else:
                if dia == hoy.day and mes == hoy.month and anio == hoy.year: clase_css.append("hoy")
                turno_dia = turnos_empleado.get(f"{dia:02d}", "")
                html_content += f"<td class='{' '.join(clase_css)}'><span class='day-number'>{dia}</span><span class='turno'>{turno_dia}</span></td>"
        html_content += "</tr>"
    html_content += "</table></div></body></html>"

    # La carpeta 'datos' no existirá en el servidor, guardamos la imagen temporalmente en la raíz
    ruta_salida = f"calendario_{uid}_{anio}_{mes}.png"
    try:
        options = {'width': 700, 'encoding': "UTF-8", 'enable-local-file-access': None, 'quality': 100, 'zoom': 1.1}
        imgkit.from_string(html_content, ruta_salida, options=options)
        return ruta_salida
    except Exception as e:
        print(f"Error al crear imagen con imgkit: {e}")
        raise e

# --- FUNCIÓN PRINCIPAL DE EJECUCIÓN ---

def main():
    # Esta función se ejecuta al arrancar el bot
    inicializar_db() # Crea las tablas en la base de datos
    
    # Comprueba si el usuario admin existe, si no, lo crea
    if not leer_json(RUTA_EMPLEADOS, {}):
        guardar_json(RUTA_EMPLEADOS, {str(ADMIN_ID): {"nombre": "Administrador", "es_admin": True}})

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
