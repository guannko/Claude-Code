FROM python:3.11-slim

# tzdata нужен APScheduler (timezone Europe/Moscow)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Директории для SQLite и логов
RUN mkdir -p database logs

CMD ["python", "main.py"]
