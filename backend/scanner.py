# -*- coding: utf-8 -*-
"""
LUCRUM Finance Scanner — bağımsız toplu tarama scripti.
server.py fonksiyonlarını içe aktarır, MCP olmadan doğrudan çalışır.

Kullanım:
    python scanner.py                    # BIST 100
    python scanner.py --subset sp500     # S&P 500
    python scanner.py --subset all       # BIST 100 + S&P 500
    python scanner.py --limit 20         # ilk N ticker (test için)
    python scanner.py --no-cache         # cache'i yoksay, her şeyi yeniden çek
"""

import sys
import os
import time
import json
import csv
import types
import importlib.util
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ── MCP stub (server.py'nin FastMCP import'unu kırmamak için) ─────────────────
class _StubMCP:
    def __init__(self, *args, **kwargs): pass
    def tool(self):
        def decorator(fn): return fn
        return decorator
    def run(self): pass

_stub_mod = types.ModuleType("mcp.server.fastmcp")
_stub_mod.FastMCP = _StubMCP
sys.modules.setdefault("mcp", types.ModuleType("mcp"))
sys.modules.setdefault("mcp.server", types.ModuleType("mcp.server"))
sys.modules["mcp.server.fastmcp"] = _stub_mod

# ── server.py yükle ───────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("server", os.path.join(_HERE, "server.py"))
_srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_srv)

get_altman_zscore    = _srv.get_altman_zscore
get_piotroski_fscore = _srv.get_piotroski_fscore
get_valuation        = _srv.get_valuation
get_momentum         = _srv.get_momentum
compare_kap_yfinance = _srv.compare_kap_yfinance
_fmt_large           = _srv._fmt_large

# ── universe ──────────────────────────────────────────────────────────────────
sys.path.insert(0, _HERE)
from universe import BIST_100, SP500

# ── cache ─────────────────────────────────────────────────────────────────────
from cache import finance_cache

# KAP çağrılarını serialize etmek için kilit (KAP rate-limit: ~10 req/dk)
_kap_lock = threading.Lock()

# ── KAP veri kalitesi değerlendirmesi ─────────────────────────────────────────
_KAP_BAD_THRESHOLD_COUNT = 4
_KAP_BAD_THRESHOLD_PCT   = 20.0
_KAP_BALANCE_SHEET_ITEMS = {
    "total_assets", "total_liabilities", "current_assets", "current_liabilities",
    "working_capital", "equity", "retained_earnings", "cash",
}


def _kap_quality(sym: str) -> dict:
    """KAP veri kalitesi özeti. KAP kilidi altında çalışır (rate-limit)."""
    cache_key = f"kap_quality_{sym.upper()}"
    cached = finance_cache.get(cache_key, finance_cache.TTL_KAP)
    if cached is not None:
        return cached

    with _kap_lock:
        try:
            result = compare_kap_yfinance(sym)
            flagged    = result.get("flagged_items", [])
            comparison = result.get("comparison", [])
            bad_items  = [
                r for r in comparison
                if r.get("kalem") in _KAP_BALANCE_SHEET_ITEMS
                and r.get("flag")
                and r.get("pct_diff") is not None
                and abs(r["pct_diff"]) >= _KAP_BAD_THRESHOLD_PCT
            ]
            meta = result.get("kap_meta", {})
            out = {
                "kap_flagged_count":        len(flagged),
                "kap_bs_bad_diff_count":    len(bad_items),
                "kap_data_quality_warning": len(bad_items) >= _KAP_BAD_THRESHOLD_COUNT,
                "kap_period":               f"{meta.get('year','')} {meta.get('period','')}".strip(),
                "kap_disclosure":           meta.get("disclosure_index"),
                "kap_error":                result.get("kap_error", ""),
            }
            time.sleep(1.5)
        except Exception as e:
            out = {
                "kap_flagged_count":        None,
                "kap_bs_bad_diff_count":    None,
                "kap_data_quality_warning": None,
                "kap_period":               "",
                "kap_disclosure":           None,
                "kap_error":                str(e)[:80],
            }

    finance_cache.set(cache_key, out)
    return out


# ── tek ticker tarama (önce cache, sonra API) ─────────────────────────────────
def scan_ticker(sym: str, kap: bool = False, use_cache: bool = True) -> dict:
    """
    Tek bir ticker'ı tarar.
    use_cache=True: SQLite cache'te TTL içindeyse API'ye hiç gitme.
      - Finansal veriler (Z/F/PEG): TTL 7 gün
      - Momentum (fiyat bazlı):     TTL 1 gün
    """
    sym_up = sym.upper()

    # ── finansal bileşen cache ──────────────────────────────────────────────
    fin_key = f"fin_{sym_up}"
    mom_key = f"mom_{sym_up}"

    cached_fin = finance_cache.get(fin_key, finance_cache.TTL_FINANCIALS) if use_cache else None
    cached_mom = finance_cache.get(mom_key, finance_cache.TTL_PRICE)      if use_cache else None

    row: dict = {
        "ticker":    sym_up,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    # ── Finansal bileşenler (Z, F, Valuation) ──────────────────────────────
    if cached_fin is not None:
        row.update(cached_fin)
    else:
        fin_data: dict = {}
        time.sleep(0.35)   # yfinance rate-limit — paralel worker başına bekleme

        try:
            z = get_altman_zscore(sym)
            fin_data["z_score"]      = z.get("z_score")
            fin_data["z_interp"]     = (z.get("interpretation") or "")[:40]
            fin_data["z_score_note"] = (z.get("z_score_note") or "")[:80]
        except Exception as e:
            fin_data["z_score"]      = None
            fin_data["z_score_note"] = ""
            fin_data["z_error"]      = str(e)[:100]

        try:
            f = get_piotroski_fscore(sym)
            fin_data["f_score"]   = f.get("f_score")
            fin_data["f_quality"] = f.get("quality", "")
        except Exception as e:
            fin_data["f_score"] = None
            fin_data["f_error"] = str(e)[:100]

        try:
            v = get_valuation(sym)
            fin_data["pe"]                  = v.get("trailing_pe")
            fin_data["pe_note"]             = (v.get("pe_note") or "")[:60]
            fin_data["peg"]                 = v.get("peg_ratio")
            fin_data["peg_note"]            = (v.get("peg_note") or "")[:60]
            fin_data["pb"]                  = v.get("price_to_book")
            fin_data["ev_ebitda"]           = v.get("ev_to_ebitda")
            fin_data["sector"]              = v.get("sector", "")
            fin_data["eps"]                 = v.get("trailing_eps")
            fin_data["earnings_growth_pct"] = v.get("earnings_growth_pct")
            fin_data["avg_volume"]          = v.get("avg_volume")
            fin_data["daily_vol_raw"]       = v.get("daily_vol_raw")
            fin_data["is_illiquid"]         = v.get("is_illiquid")
            fin_data["liq_cap_raw"]         = v.get("liq_cap_raw")
        except Exception as e:
            for k in ("pe","peg","pb","ev_ebitda","avg_volume","daily_vol_raw","is_illiquid","liq_cap_raw"):
                fin_data[k] = None
            fin_data["v_error"] = str(e)[:100]

        row.update(fin_data)
        finance_cache.set(fin_key, fin_data)

    # ── Momentum (her zaman 1 gün TTL) ─────────────────────────────────────
    if cached_mom is not None:
        row.update(cached_mom)
    else:
        mom_data: dict = {}
        try:
            m = get_momentum(sym)
            sc = m.get("stock_change", {})
            rs = m.get("relative_strength", {})
            mom_data["momentum_1m"]  = sc.get("1m")
            mom_data["momentum_3m"]  = sc.get("3m")
            mom_data["momentum_6m"]  = sc.get("6m")
            mom_data["momentum_12m"] = sc.get("12m")
            mom_data["rs_6m"]        = rs.get("rs_6m")
            mom_data["rs_12m"]       = rs.get("rs_12m")
            mom_data["benchmark"]    = m.get("benchmark", "")
        except Exception as e:
            mom_data["momentum_6m"] = mom_data["rs_6m"] = None
            mom_data["m_error"] = str(e)[:100]
        row.update(mom_data)
        finance_cache.set(mom_key, mom_data)

    # ── KAP kalitesi (opsiyonel, kilitli) ──────────────────────────────────
    if kap and sym_up.endswith(".IS"):
        kq = _kap_quality(sym)
        row.update(kq)

    # ── Etiket hesaplama ────────────────────────────────────────────────────
    row["api_error"] = row.get("f_score") is None and row.get("pe") is None
    z_v    = row.get("z_score")
    f_v    = row.get("f_score")
    z_note = (row.get("z_score_note") or "").lower()
    is_fin = "finansal sektör" in z_note

    if row["api_error"]:
        row["tag"] = "Hata"
    elif is_fin and f_v is not None and f_v >= 7:
        row["tag"] = "Kaliteli"
    elif not is_fin and z_v is not None and f_v is not None and z_v > 3 and f_v >= 7:
        row["tag"] = "Kaliteli"
    elif not is_fin and z_v is not None and z_v < 1.81:
        row["tag"] = "Risk"
    elif f_v is not None and f_v <= 3:
        row["tag"] = "Zayif"
    else:
        row["tag"] = "Notr"

    return row


# ── ana tarama döngüsü (paralel) ──────────────────────────────────────────────
def run_scan(
    tickers:   list[str],
    subset:    str,
    append:    bool = False,
    kap:       bool = False,
    use_cache: bool = True,
    workers:   int  = 6,
) -> None:
    csv_path  = os.path.join(_HERE, "results.csv")
    json_path = os.path.join(_HERE, "results.json")

    existing_results: list[dict] = []
    existing_tickers: set[str]  = set()
    if append and os.path.exists(csv_path):
        try:
            with open(csv_path, encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    existing_results.append(row)
                    if row.get("ticker"):
                        existing_tickers.add(row["ticker"].upper())
            print(f"--append: {len(existing_results)} mevcut satır, {len(existing_tickers)} ticker atlanacak")
        except Exception as e:
            print(f"--append: mevcut CSV okunamadı ({e}), sıfırdan başlanıyor")
            existing_results, existing_tickers = [], set()

    tickers = [t for t in tickers if t.upper() not in existing_tickers]
    total   = len(tickers)
    results: list[dict]  = []
    failed:  list[dict]  = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'='*65}")
    print(f"LUCRUM Finance Scanner — {subset.upper()} ({total} ticker)")
    print(f"Mod: {'KAP aktif' if kap else 'standart'} | "
          f"Cache: {'aktif' if use_cache else 'KAPALI'} | "
          f"Workers: {workers if not kap else 1}")
    print(f"Baslangic: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*65}\n")

    _print_lock    = threading.Lock()
    _results_lock  = threading.Lock()
    completed_count = [0]   # mutable container — thread-safe okuma

    def _do_scan(i: int, sym: str) -> tuple[int, str, dict | None, str | None]:
        try:
            row = scan_ticker(sym, kap=kap, use_cache=use_cache)
            return i, sym, row, None
        except Exception as e:
            return i, sym, None, str(e)

    # KAP modunda paralellisme KAP rate-limit nedeniyle kapatılır
    effective_workers = 1 if kap else workers

    with ThreadPoolExecutor(max_workers=effective_workers) as pool:
        futures = {
            pool.submit(_do_scan, i, sym): (i, sym)
            for i, sym in enumerate(tickers, 1)
        }

        for fut in as_completed(futures):
            i, sym, row, err = fut.result()

            with _print_lock:
                completed_count[0] += 1
                done = completed_count[0]
                prefix = f"[{done:>3}/{total}] {sym:<14}"

                if err:
                    failed_entry = {"ticker": sym, "error": err}
                    with _results_lock:
                        failed.append(failed_entry)
                    print(f"{prefix}  !! HATA: {err[:60]}")
                else:
                    with _results_lock:
                        results.append(row)

                    z    = row.get("z_score")
                    f    = row.get("f_score")
                    peg  = row.get("peg")
                    tag  = row.get("tag", "")
                    cache_str = ""

                    z_str   = f"Z={z:.2f}"   if z   is not None else "Z=N/A "
                    f_str   = f"F={f}"        if f   is not None else "F=N/A"
                    peg_str = f"PEG={peg:.2f}" if peg is not None else "PEG=N/A"
                    print(f"{prefix}  {z_str:<8} {f_str:<5} {peg_str:<10} [{tag}]{cache_str}")

                # Her 10 tamamlamada ara kayıt
                if done % 10 == 0:
                    with _results_lock:
                        _save(existing_results + results, failed, csv_path, json_path, ts, subset)
                    print(f"          >> Ara kayit: {done} ticker tamamlandi\n")

    # Final kayıt
    _save(existing_results + results, failed, csv_path, json_path, ts, subset)

    all_results = existing_results + results
    print(f"\n{'='*65}")
    print(f"TAMAMLANDI: {len(results)} yeni / {len(failed)} basarisiz / {len(all_results)} toplam")
    print(f"Kaydedildi: {csv_path}")
    print(f"            {json_path}")

    kaliteli     = [r for r in results     if r.get("tag") == "Kaliteli"]
    risk         = [r for r in results     if r.get("tag") == "Risk"]
    all_kaliteli = [r for r in all_results if r.get("tag") == "Kaliteli"]
    print(f"\nBu taramada Kaliteli (Z>3 ve F>=7) : {len(kaliteli)}")
    if kaliteli:
        print("  " + ", ".join(r["ticker"] for r in kaliteli[:10]))
    print(f"Toplam Kaliteli (tum evren)        : {len(all_kaliteli)}")
    print(f"Risk (Z<1.81)                      : {len(risk)}")
    if risk:
        print("  " + ", ".join(r["ticker"] for r in risk[:10]))
    if failed:
        print(f"\nBasarisiz ({len(failed)}):")
        for item in failed:
            print(f"  {item['ticker']:<14} {item['error'][:70]}")


def _save(
    results:   list[dict],
    failed:    list[dict],
    csv_path:  str,
    json_path: str,
    ts:        str,
    subset:    str,
) -> None:
    if not results:
        return
    all_keys:  list[str] = []
    seen_keys: set[str]  = set()
    for row in results:
        for k in row:
            if k not in seen_keys:
                all_keys.append(k)
                seen_keys.add(k)

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({
            "scan_timestamp": ts,
            "generated_at":   datetime.now().isoformat(),
            "subset":         subset,
            "total_scanned":  len(results),
            "failed_count":   len(failed),
            "results":        results,
            "failed":         failed,
        }, fh, ensure_ascii=False, indent=2, default=str)


# ── entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="LUCRUM Finance Toplu Tarama")
    parser.add_argument("--subset",   default="bist100",
                        choices=["bist100", "sp500", "all"])
    parser.add_argument("--limit",    type=int, default=0)
    parser.add_argument("--append",   action="store_true")
    parser.add_argument("--kap",      action="store_true",
                        help="BIST ticker icin KAP kalite kontrolu (tek thread, yavas)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Cache'i atla, her seyi yeniden cek")
    parser.add_argument("--workers",  type=int, default=6,
                        help="Paralel worker sayisi (varsayilan: 6)")
    args = parser.parse_args()

    if args.subset == "bist100":
        tickers = BIST_100[:]
    elif args.subset == "sp500":
        tickers = SP500[:]
    else:
        tickers = BIST_100 + [t for t in SP500 if t not in set(BIST_100)]

    if args.limit > 0:
        tickers = tickers[:args.limit]

    run_scan(
        tickers,
        args.subset,
        append=args.append,
        kap=args.kap,
        use_cache=not args.no_cache,
        workers=args.workers,
    )

    # Kısmi tarama sonrası: diğer subset'i results_prev.csv'den koru
    csv_path  = os.path.join(_HERE, "results.csv")
    prev_path = os.path.join(_HERE, "results_prev.csv")
    if args.subset in ("bist100", "sp500") and not args.append and os.path.exists(prev_path):
        try:
            with open(csv_path, encoding="utf-8") as fh:
                new_rows = list(csv.DictReader(fh))
            new_tickers = {r.get("ticker", "").upper() for r in new_rows}
            with open(prev_path, encoding="utf-8") as fh:
                prev_rows = list(csv.DictReader(fh))
            preserved = [r for r in prev_rows if r.get("ticker", "").upper() not in new_tickers]
            if preserved:
                all_rows  = new_rows + preserved
                all_keys:  list[str] = []
                seen_keys: set[str]  = set()
                for row in all_rows:
                    for k in row:
                        if k not in seen_keys:
                            all_keys.append(k)
                            seen_keys.add(k)
                with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=all_keys, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(all_rows)
                print(f"\n{len(preserved)} ticker onceki taramadan (results_prev.csv) birlestirildi.")
                print(f"Toplam results.csv: {len(all_rows)} satir.")
        except Exception as e:
            print(f"Birlestirme hatasi: {e}")


if __name__ == "__main__":
    main()
