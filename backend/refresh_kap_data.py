# -*- coding: utf-8 -*-
"""
refresh_kap_data.py — KAP verisi önbellekleme scripti (ADIM 3)

BIST100 evrenindeki tüm ticker'lar için KAP'tan son iki yıllık finansal
veriyi sıralı olarak çeker (rate-limit: ~10 req/dk) ve kap_cache.json
dosyasına yazar (TTL=7 gün).

server.py ve scanner.py'nin KAP çağrıları bu cache'i önce kontrol eder;
sadece TTL dolmuş kayıtlar için live KAP isteği gider.

Kullanım:
    python refresh_kap_data.py                   # tüm BIST100
    python refresh_kap_data.py --force           # cache'i yoksay, yeniden çek
    python refresh_kap_data.py --ticker THYAO    # tek ticker
    python refresh_kap_data.py --limit 10        # ilk N ticker (test)
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from universe import BIST_100
from kap_scraper import (
    get_kap_financials_annual_pair,
    _kap_disk_get,
    _kap_disk_set,
    _kap_cache_load,
    _kap_cache_save,
    _KAP_CACHE_TTL,
)

_REQ_INTER_SLEEP = 6.0   # iki bildirim arasındaki bekleme (saniye) — KAP 10 req/dk
_BETWEEN_SLEEP   = 3.0   # ticker'lar arası ek bekleme


def _needs_refresh(clean: str, force: bool) -> bool:
    if force:
        return True
    cached = _kap_disk_get(clean)
    return cached is None   # None: yok ya da TTL dolmuş


def run_refresh(
    tickers: list[str],
    force:   bool = False,
) -> None:
    total    = len(tickers)
    refreshed = 0
    skipped   = 0
    failed    = 0

    print(f"\n{'='*65}")
    print(f"KAP Veri Yenileme — {total} BIST ticker")
    print(f"Mod: {'ZORLA' if force else 'TTL kontrollü (7 gün)'}")
    print(f"Baslangic: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tahmini sure: ~{total * _REQ_INTER_SLEEP / 60:.1f} dk")
    print(f"{'='*65}\n")

    for i, ticker in enumerate(tickers, 1):
        clean = ticker.upper().replace(".IS", "")
        prefix = f"[{i:>3}/{total}] {clean:<12}"

        if not _needs_refresh(clean, force):
            print(f"{prefix} ATLA (cache taze)")
            skipped += 1
            continue

        print(f"{prefix} cekiliyor...", end=" ", flush=True)
        t0 = time.time()
        try:
            curr, prev = get_kap_financials_annual_pair(ticker)
            elapsed = time.time() - t0

            if curr:
                disc_info = f"{curr.get('year','')} {curr.get('period','')[:15]}"
                prev_info = f" | onceki: {prev.get('year','')} {prev.get('period','')[:10]}" if prev else ""
                print(f"ok  {disc_info}{prev_info}  ({elapsed:.1f}s)")
                refreshed += 1
            else:
                print(f"veri yok  ({elapsed:.1f}s)")
                # Boş sonucu da cache'e yaz (tekrar denemeyiz)
                _kap_disk_set(clean, None, None)
                refreshed += 1   # girdi yazıldı, tekrar denenmesin

        except Exception as e:
            elapsed = time.time() - t0
            print(f"HATA: {e}  ({elapsed:.1f}s)")
            failed += 1

        # Ticker'lar arası ek bekleme (rate-limit)
        if i < total:
            time.sleep(_BETWEEN_SLEEP)

    print(f"\n{'='*65}")
    print(f"TAMAMLANDI")
    print(f"  Yenilendi : {refreshed}")
    print(f"  Atlandı   : {skipped}")
    print(f"  Hata      : {failed}")

    # Cache özeti
    cache = _kap_cache_load()
    now   = datetime.now(timezone.utc)
    fresh = 0
    for entry in cache.values():
        try:
            fetched_at = datetime.fromisoformat(entry.get("fetched_at", ""))
            age = (now - fetched_at.replace(tzinfo=timezone.utc)).total_seconds()
            if age <= _KAP_CACHE_TTL:
                fresh += 1
        except Exception:
            pass
    print(f"  Cache'de toplam taze kayıt: {fresh} / {len(cache)}")

    kap_path = os.path.join(_HERE, "kap_cache.json")
    if os.path.exists(kap_path):
        size_kb = os.path.getsize(kap_path) / 1024
        print(f"  kap_cache.json: {size_kb:.1f} KB")
    print(f"{'='*65}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="KAP finansal veri cache yenileme")
    parser.add_argument("--force",  action="store_true",
                        help="TTL'e bakma, tüm ticker'ları yenile")
    parser.add_argument("--ticker", help="Tek ticker (ör: THYAO veya THYAO.IS)")
    parser.add_argument("--limit",  type=int, default=0,
                        help="BIST100'den ilk N ticker (test için)")
    args = parser.parse_args()

    if args.ticker:
        t = args.ticker.upper()
        if not t.endswith(".IS"):
            t += ".IS"
        tickers = [t]
    else:
        tickers = BIST_100[:]
        if args.limit > 0:
            tickers = tickers[:args.limit]

    run_refresh(tickers, force=args.force)


if __name__ == "__main__":
    main()
