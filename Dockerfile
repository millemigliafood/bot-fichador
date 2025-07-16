# filepath: c:\Users\Alejandro\Desktop\MilleMiglia_Fichador\bot_fichador\Dockerfile
# Usamos una imagen base de Python
FROM python:3.11-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos el archivo de requerimientos
COPY requirements.txt .

# Instalamos las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código de la aplicación
COPY . .

# Definimos el comando para ejecutar el bot
CMD ["python", "telegram_bot.py"]
