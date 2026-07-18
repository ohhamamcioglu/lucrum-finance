FROM python:3.13-slim

# print() çıktısının tamponlanmasını kapatır — aksi halde container loglarındaki
# zaman damgaları gerçek çalışma sırasını yanıltıyor (loglar dakikalarca gecikmeli
# görünüyor), bu da canlıdaki performans sorunlarını teşhis etmeyi zorlaştırıyordu.
ENV PYTHONUNBUFFERED=1

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

# --proxy-headers + --forwarded-allow-ips='*': Railway'in kendi ters proxy'si arkasında
# çalışıyoruz. Bu bayraklar olmadan uvicorn/starlette istemci IP'si olarak proxy'nin
# kendi iç IP'sini görüyordu — bu da rate limiter'ın (giriş sayfası brute-force koruması)
# gerçek istemciyi değil proxy'yi sınırlamasına, dolayısıyla ya hiç işe yaramamasına ya da
# tüm kullanıcıları TEK bir "istemci" gibi paylaştırıp yanlışlıkla birbirini
# engellemesine yol açıyordu. Railway'in kendi proxy katmanı güvenilir olduğu için
# forwarded-allow-ips='*' burada kabul edilebilir.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
