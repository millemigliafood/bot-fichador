FROM python:3.11

# Instala dependencias del sistema necesarias para imgkit
RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    wkhtmltoimage \
    fontconfig \
    libxrender1 \
    libxext6 \
    libx11-dev \
    && apt-get clean

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "telegram_bot.py"]
