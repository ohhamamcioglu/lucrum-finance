import os
import sys
from celery import Celery

# backend/ dizinini Python arama yoluna MUTLAK bir yol olarak ekle. Celery worker
# daemonize olurken (veya prefork ile fork ederken) çalışma dizinini (CWD) değiştirebiliyor.
# services/crud/twelve_data gibi modüller worker açılışında (include=["tasks"] ile) hemen
# yüklendiği için soruna rastlamıyor, ama twelve_data.py'deki tefas_tools importu SADECE bir
# TEFAS fonu gerçekten istendiğinde (gecikmeli/lazy import) çalışıyor — o ana kadar CWD
# değişmişse ve sys.path buna dayanan göreli bir girdi içeriyorsa "No module named
# 'tefas_tools'" hatası alınıyordu (canlıda celery-worker'da gözlemlendi). Mutlak yol,
# CWD ne olursa olsun çalışır.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load env variables if available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
except ImportError:
    pass

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Upstash (ve diğer TLS gerektiren yönetilen Redis'ler) rediss:// şeması kullanır.
# Kombu'nun redis transport'u, ssl_cert_reqs query param'ı URL'de yoksa
# "A rediss:// URL must have parameter ssl_cert_reqs" hatasıyla patlıyor —
# kullanıcı bağlantı dizesine bunu eklemeyi unutursa diye burada otomatik ekleniyor.
if REDIS_URL.startswith("rediss://") and "ssl_cert_reqs" not in REDIS_URL:
    sep = "&" if "?" in REDIS_URL else "?"
    REDIS_URL = f"{REDIS_URL}{sep}ssl_cert_reqs=CERT_REQUIRED"

# Celery app configuration
celery_app = Celery(
    "lucrum_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"]
)

celery_app.conf.update(
    timezone="Europe/Istanbul",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Celery Beat Periodic Task Schedules (SaaS scale time-triggers)
    beat_schedule={
        "daily-portfolio-snapshots": {
            "task": "tasks.daily_snapshot_task",
            # Every day at 23:55 Europe/Istanbul
            "schedule": 86400.0,
        },
        "cache-enrichment-hourly": {
            "task": "tasks.enrich_portfolio_holdings_task",
            # Every hour
            "schedule": 3600.0,
        },
        "warm-portfolio-cache": {
            "task": "tasks.warm_portfolio_cache_task",
            # 5 dakikalık cache TTL'inden önce, her 4 dakikada bir — kullanıcı asla
            # soğuk/yavaş bir portföy hesaplamasına denk gelmesin diye.
            "schedule": 240.0,
        },
        "downgrade-expired-subscriptions-daily": {
            "task": "tasks.downgrade_expired_subscriptions_task",
            # Every day
            "schedule": 86400.0,
        },
        "refresh-instrument-catalog-weekly": {
            "task": "tasks.refresh_instrument_catalog_task",
            # Haftada bir — TTL 14 gün olsa da yeni listelenen hisse/fonları
            # daha hızlı yakalamak için
            "schedule": 604800.0,
        },
        "refresh-tefas-nav-cache": {
            "task": "tasks.refresh_tefas_nav_task",
            # Her 15 dakikada bir — performans grafiği artık get_tefas_nav'ı
            # live_fetch=False ile çağırıyor (isteği bloke etmemek için), bu görev
            # olmadan önbellek asla dolmaz/tazelenmez. Yeni eklenen bir TEFAS fonu
            # en fazla bu kadar süre "düz çizgi" gösterir.
            "schedule": 900.0,
        }
    }
)
