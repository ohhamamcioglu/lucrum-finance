"""
cache.py — SQLite / Redis Hybrid TTL Cache (LUCRUM Finance SaaS)
"""
from __future__ import annotations
import logging
import os
import pickle
import sqlite3
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("lucrum.cache")

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_HERE, "cache.db")

_write_lock = threading.Lock()

class FinanceCache:
    TTL_FINANCIALS = 7 * 24 * 3600    # 7 gün — Z/F/PEG (çeyreklik veri)
    TTL_PRICE      = 1 * 24 * 3600    # 1 gün — fiyat & momentum
    TTL_SCAN       = 1 * 24 * 3600    # 1 gün — tam scan_ticker sonucu
    TTL_KAP        = 7 * 24 * 3600    # 7 gün — KAP bildirim verisi
    TTL_NEWS       = 1800             # 30 dakika — haber akışı

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db = db_path
        self._redis = None
        self._use_redis = False
        
        # Check for REDIS_URL in environment variables
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                # Normalize rediss:// (SSL) or redis:// connection
                self._redis = redis.Redis.from_url(redis_url, socket_timeout=2.0)
                # Quick connection test
                self._redis.ping()
                self._use_redis = True
                logger.info("Redis cache'e bağlanıldı.")
            except Exception as e:
                logger.warning("Redis bağlantısı başarısız, SQLite cache'e düşülüyor: %s", e)
                self._redis = None
                self._use_redis = False
        
        if not self._use_redis:
            self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db, timeout=10)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key        TEXT    PRIMARY KEY,
                    data       BLOB    NOT NULL,
                    fetched_at REAL    NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_key ON cache(key)")

    def get(self, key: str, ttl: float) -> Optional[Any]:
        """Cache'ten al. TTL geçmişse ya da kayıt yoksa None döner."""
        if self._use_redis:
            try:
                data = self._redis.get(key)
                if data is None:
                    return None
                val, fetched_at = pickle.loads(data)
                if time.time() - fetched_at > ttl:
                    return None
                return val
            except Exception as e:
                logger.debug("Redis get('%s') başarısız: %s", key, e)
                return None

        # SQLite Fallback
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT data, fetched_at FROM cache WHERE key=?", (key,)
                ).fetchone()
        except Exception as e:
            logger.debug("SQLite cache get('%s') başarısız: %s", key, e)
            return None
        if row is None:
            return None
        data_blob, fetched_at = row
        if time.time() - fetched_at > ttl:
            return None
        try:
            return pickle.loads(data_blob)
        except Exception as e:
            logger.warning("Cache girdisi '%s' unpickle edilemedi (bozuk kayıt olabilir): %s", key, e)
            return None

    def set(self, key: str, value: Any) -> None:
        """Cache'e yaz (mevcut kaydı güncelle)."""
        if self._use_redis:
            try:
                blob = pickle.dumps((value, time.time()), protocol=5)
                # Keep keys alive for at most the max financial TTL (7 days)
                self._redis.set(key, blob, ex=self.TTL_FINANCIALS)
            except Exception as e:
                logger.warning("Redis set('%s') başarısız: %s", key, e)
            return

        # SQLite Fallback
        try:
            blob = pickle.dumps(value, protocol=5)
            with _write_lock:
                with self._conn() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO cache(key, data, fetched_at) VALUES(?,?,?)",
                        (key, blob, time.time()),
                    )
        except Exception as e:
            logger.warning("SQLite cache set('%s') başarısız: %s", key, e)

    def invalidate(self, key: str) -> None:
        """Belirli bir anahtarı sil."""
        if self._use_redis:
            try:
                self._redis.delete(key)
            except Exception as e:
                logger.warning("Redis invalidate('%s') başarısız: %s", key, e)
            return

        # SQLite Fallback
        try:
            with _write_lock:
                with self._conn() as conn:
                    conn.execute("DELETE FROM cache WHERE key=?", (key,))
        except Exception as e:
            logger.warning("SQLite cache invalidate('%s') başarısız: %s", key, e)

    def invalidate_prefix(self, prefix: str) -> int:
        """Belirli bir önek ile başlayan tüm girişleri sil. Silinen sayısını döner."""
        if self._use_redis:
            try:
                keys = []
                cursor = 0
                while True:
                    cursor, keys_chunk = self._redis.scan(cursor, match=prefix + "*", count=100)
                    keys.extend(keys_chunk)
                    if cursor == 0:
                        break
                if keys:
                    self._redis.delete(*keys)
                return len(keys)
            except Exception as e:
                logger.warning("Redis invalidate_prefix('%s') başarısız: %s", prefix, e)
                return 0

        # SQLite Fallback
        try:
            with _write_lock:
                with self._conn() as conn:
                    cur = conn.execute(
                        "DELETE FROM cache WHERE key LIKE ?", (prefix + "%",)
                    )
                    return cur.rowcount
        except Exception as e:
            logger.warning("SQLite cache invalidate_prefix('%s') başarısız: %s", prefix, e)
            return 0

    def stats(self) -> dict:
        """Cache istatistikleri."""
        if self._use_redis:
            try:
                info = self._redis.info()
                return {
                    "type": "Redis",
                    "connected": True,
                    "redis_version": info.get("redis_version"),
                    "used_memory_human": info.get("used_memory_human"),
                    "total_keys": self._redis.dbsize(),
                }
            except Exception as e:
                logger.warning("Redis stats() başarısız: %s", e)
                return {"type": "Redis", "error": str(e)}
                
        # SQLite Fallback
        try:
            with self._conn() as conn:
                total    = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
                expired_7d = conn.execute(
                    "SELECT COUNT(*) FROM cache WHERE ? - fetched_at > ?",
                    (time.time(), self.TTL_FINANCIALS)
                ).fetchone()[0]
                expired_1d = conn.execute(
                    "SELECT COUNT(*) FROM cache WHERE ? - fetched_at > ?",
                    (time.time(), self.TTL_PRICE)
                ).fetchone()[0]
            size = os.path.getsize(self._db) if os.path.exists(self._db) else 0
            return {
                "type":              "SQLite",
                "total_entries":     total,
                "expired_7d":        expired_7d,
                "expired_1d":        expired_1d,
                "fresh":             total - expired_7d,
                "db_size_mb":        round(size / 1e6, 2),
                "db_path":           self._db,
            }
        except Exception as e:
            logger.warning("SQLite cache stats() başarısız: %s", e)
            return {"error": str(e)}

    def vacuum(self) -> int:
        """7 günden eski tüm girişleri temizle. Silinen sayısını döner."""
        if self._use_redis:
            # Redis auto-evicts keys, so vacuum is a no-op
            return 0
            
        # SQLite Fallback
        try:
            with _write_lock:
                with self._conn() as conn:
                    cur = conn.execute(
                        "DELETE FROM cache WHERE ? - fetched_at > ?",
                        (time.time(), self.TTL_FINANCIALS)
                    )
                    deleted = cur.rowcount
                    conn.execute("VACUUM")
            return deleted
        except Exception as e:
            logger.warning("SQLite cache vacuum() başarısız: %s", e)
            return 0

finance_cache = FinanceCache()

if __name__ == "__main__":
    s = finance_cache.stats()
    print("Cache istatistikleri:")
    for k, v in s.items():
        print(f"  {k:<20}: {v}")
    print()
    if s.get("type") == "SQLite":
        ans = input("Süresi dolmuş girişleri temizle? (e/N): ").strip().lower()
        if ans == "e":
            deleted = finance_cache.vacuum()
            print(f"  {deleted} eski kayıt silindi.")
