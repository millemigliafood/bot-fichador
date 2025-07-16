FROM python:3.11

RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    fontconfig \
    libxrender1 \
    libxext6 \
    libx11-dev \
    && apt-get clean

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "telegram_bot.py"]
