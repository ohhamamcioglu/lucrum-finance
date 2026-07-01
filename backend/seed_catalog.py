"""
seed_catalog.py — Küresel Arama Kataloğu Tohumlama Betiği
=========================================================
Bu betik, Twelve Data API'sinden BIST, NYSE, NASDAQ, 
Kripto Paralar ve Forex paritelerinin tüm sembol listelerini
çekerek yerel veritabanındaki `td_instruments` tablosuna kaydeder.

Bu işlem sadece 5-6 API isteği harcar ve yaklaşık 10-15 saniye sürer.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import twelve_data as td

def seed():
    print("=== KÜRESEL ARAMA KATALOĞU TOHUMLAMA BAŞLATILDI ===")
    
    # 1. BIST Hisseleri
    print("\n1/5. BIST (Borsa İstanbul) enstrümanları çekiliyor...")
    bist = td.get_bist_instruments()
    print(f"   -> BIST Kataloğu tamamlandı: {len(bist)} enstrüman kaydedildi.")
    
    # 2. NASDAQ Hisseleri
    print("\n2/5. NASDAQ enstrümanları çekiliyor...")
    nasdaq = td.fetch_instruments("NASDAQ")
    print(f"   -> NASDAQ Kataloğu tamamlandı: {len(nasdaq)} enstrüman kaydedildi.")
    
    # 3. NYSE Hisseleri
    print("\n3/5. NYSE enstrümanları çekiliyor...")
    nyse = td.fetch_instruments("NYSE")
    print(f"   -> NYSE Kataloğu tamamlandı: {len(nyse)} enstrüman kaydedildi.")

    # API limitini korumak için kısa bir bekleme
    time.sleep(2)

    # 4. Kripto Paralar
    print("\n4/5. Kripto Para çiftleri çekiliyor...")
    crypto = td._api("cryptocurrencies", {})
    if crypto and "data" in crypto:
        items = crypto["data"]
        ts = td._now()
        rows = [
            (
                item["symbol"], "Digital Currency",
                item.get("name"), item.get("currency_base"),
                "Digital Currency", "", "", "", ts
            )
            for item in items
        ]
        with td._db_lock:
            c = td._conn()
            c.executemany("""
                INSERT OR REPLACE INTO td_instruments
                (symbol,exchange,name,currency,type,country,mic_code,figi_code,fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, rows)
            c.commit()
            c.close()
        print(f"   -> Kripto Kataloğu tamamlandı: {len(rows)} kripto çifti kaydedildi.")

    # 5. Forex Pariteleri
    print("\n5/5. Forex Döviz Pariteleri çekiliyor...")
    forex = td._api("forex_pairs", {})
    if forex and "data" in forex:
        items = forex["data"]
        ts = td._now()
        rows = [
            (
                item["symbol"], "Forex",
                item.get("currency_to"), item.get("currency_to"),
                "Physical Currency", "", "", "", ts
            )
            for item in items
        ]
        with td._db_lock:
            c = td._conn()
            c.executemany("""
                INSERT OR REPLACE INTO td_instruments
                (symbol,exchange,name,currency,type,country,mic_code,figi_code,fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, rows)
            c.commit()
            c.close()
        print(f"   -> Forex Kataloğu tamamlandı: {len(rows)} döviz çifti kaydedildi.")

    print("\n=== TOHUMLAMA BAŞARIYLA TAMAMLANDI ===")
    print("Yerel arama kataloğunuz hazır. Artık arayüzden her varlığı anında aratabilirsiniz.")

if __name__ == "__main__":
    seed()
