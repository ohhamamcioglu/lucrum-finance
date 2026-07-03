import os
from celery import Celery

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
        "downgrade-expired-subscriptions-daily": {
            "task": "tasks.downgrade_expired_subscriptions_task",
            # Every day
            "schedule": 86400.0,
        }
    }
)
