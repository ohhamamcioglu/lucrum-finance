"""
FastAPI Portfolio Platform - Main Application
"""
import os
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

# Ensure the backend directory is in the import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# .env yükleme
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
except ImportError:
    pass

# Hata izleme (Sentry) — SENTRY_DSN tanımlı değilse tamamen no-op, hiçbir şey göndermez.
_sentry_dsn = os.getenv("SENTRY_DSN")
if _sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
    )

# Import routers
from routers import (
    users,
    positions,
    portfolio,
    transactions,
    prices,
    assets,
    notifications,
    liabilities,
    admin,
    payments,
    imports as imports_router,
    tax,
    calendar as calendar_router,
)
from scheduler import start_scheduler, stop_scheduler
from rate_limit import limiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lucrum.main")

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Start background scheduler and crawler
    start_scheduler()
    logger.info("Scheduler and TwelveDataCrawler started successfully.")
    
    yield
    
    # Stop background scheduler and crawler
    stop_scheduler()
    logger.info("Scheduler and TwelveDataCrawler stopped successfully.")

app = FastAPI(
    title="LUCRUM Portfolio Platform",
    description="Professional Portfolio Tracking & Analytics",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting (brute-force koruması — auth endpoint'lerinde kullanılıyor)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — wildcard origin + credentials tarayıcılarca reddedilir ve güvenlik açığıdır.
# İzin verilen origin'leri .env üzerinden ALLOWED_ORIGINS ile yönetiyoruz.
_allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(users.router)
app.include_router(positions.router)
app.include_router(portfolio.router)
app.include_router(transactions.router)
app.include_router(prices.router)
app.include_router(assets.router)
app.include_router(notifications.router)
app.include_router(liabilities.router)
app.include_router(admin.router)
app.include_router(payments.router)
app.include_router(imports_router.router)
app.include_router(tax.router)
app.include_router(calendar_router.router)

# ============ HEALTH ============

@app.get("/health")
def health():
    """Health check"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "LUCRUM Portfolio Platform API",
        "docs": "/docs",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
