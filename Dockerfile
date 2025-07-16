# Usamos una imagen de Python que incluye un sistema operativo base (Debian)
FROM python:3.11-slim-bookworm

# Actualizamos la lista de paquetes e instalamos wkhtmltopdf (que incluye wkhtmltoimage)
RUN apt-get update && apt-get install -y --no-install-recommends wkhtmltopdf

# Establecemos el directorio de trabajo
WORKDIR /app

# Copiamos el archivo de requerimientos de Python
COPY requirements.txt .

# Instalamos las librerías de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código del bot
COPY . .

# Comando final para arrancar el bot
CMD ["python", "telegram_bot.py"]
