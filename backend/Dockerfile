FROM python:3.13-slim

WORKDIR /app

# lxml/psycopg2 gibi paketler için derleme bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --retries 15 --timeout 120 -r /app/requirements.txt

COPY backend/ /app/

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
