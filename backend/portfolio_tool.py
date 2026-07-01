"""
ADIM 3: get_full_portfolio() Tool
Holdings'teki tum varliklari islem veri ile hesapla
"""
import json
import twelve_data as td
import requests
from datetime import datetime, timedelta
from pathlib import Path

# TEFAS DataFrame cache
_tefas_cache = None

def get_current_price(ticker, asset_class):
    """Guncel fiyat al (yfinance / CoinGecko / pytefas)"""
    global _tefas_cache
    try:
        if asset_class == "TEFAS Fonu":
            try:
                from pytefas import Crawler
                # Cache'den al yoksa fetch et
                if _tefas_cache is None:
                    crawler = Crawler()
                    end = datetime.now()
                    start = end - timedelta(days=1)
                    _tefas_cache = crawler.fetch(start, end)

                # DataFrame'den fonu ara ve son fiyatı al
                fund_data = _tefas_cache[_tefas_cache['fund_code'] == ticker]
                if not fund_data.empty:
                    # Son tarihin fiyatını al
                    latest = fund_data.sort_values('date').iloc[-1]
                    return float(latest['price'])
            except Exception as e:
                print(f"[WARN] TEFAS {ticker} fiyati alinamadi: {e}")
            return None

        elif asset_class == "BIST Hissesi":
            return td.get_price(f"{ticker}.IS")

        elif asset_class == "ABD Hisse/ETF":
            return td.get_price(ticker)

        elif asset_class == "Kripto":
            # CoinMarketCap API kullan
            cmc_key = "b63d7c635d2a4fd6878d1b621795ebfc"
            cmc_map = {
                "BTC": "bitcoin",
                "BRETT": "brett",
                "TAO": "bittensor"
            }

            if ticker in cmc_map:
                try:
                    url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={ticker}"
                    headers = {"X-CMC_PRO_API_KEY": cmc_key}
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.ok:
                        data = resp.json()
                        if data.get("status", {}).get("error_code") == 0:
                            price_usd = data["data"][ticker]["quote"]["USD"]["price"]
                            return float(price_usd)
                except Exception as e:
                    print(f"[WARN] CoinMarketCap {ticker}: {e}")
                    # Fallback: CoinGecko
                    try:
                        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cmc_map[ticker]}&vs_currencies=usd"
                        resp = requests.get(url, timeout=5)
                        if resp.ok:
                            data = resp.json()
                            return float(data[cmc_map[ticker]]["usd"])
                    except:
                        pass
        return None
    except Exception as e:
        print(f"[WARN] {ticker} fiyati alinamadi: {e}")
        return None

def get_usd_try_rate(date_str=None):
    """USD/TRY kurunu al (guncel veya belirli tarih) — Twelve Data"""
    try:
        if date_str:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            if date_obj > datetime.now():
                print(f"[WARN] {date_str} gelecek tarih, guncel oran kullaniliyor")
                return get_usd_try_rate()
            days_back = (datetime.now().date() - date_obj.date()).days + 5
            series = td.get_time_series("USD/TRY", days=max(30, min(730, days_back)), interval="1day")
            for item in series:  # DESC sıralı
                if item.get("date", "")[:10] <= date_str and item.get("close"):
                    return float(item["close"])

        # Güncel kur
        rate = td.get_exchange_rate("USD/TRY")
        if rate:
            return rate
        return 35.0
    except Exception as e:
        print(f"[WARN] USD/TRY kuru alinamadi: {e}, fallback 35 TRY")
        return 35.0

def calculate_portfolio():
    """Holdings'teki tum varliklari islem et"""

    with open("holdings_full.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    holdings = data.get("holdings", [])
    results = []

    # Her pozisyon icin guncel hesapla
    for h in holdings:
        ticker = h["ticker"]
        asset_class = h["asset_class"]
        quantity = h["quantity"]
        buy_price = h["buy_price"]
        buy_currency = h.get("buy_currency", "TRY")
        buy_date = h["buy_date"]

        # Guncel fiyat al
        current_price = get_current_price(ticker, asset_class)

        # Kur bilgisi
        current_usd_try = get_usd_try_rate()  # Guncel kur
        buy_date_usd_try = get_usd_try_rate(buy_date)  # Alis tarihindeki kur

        result = {
            "ticker": ticker,
            "asset_class": asset_class,
            "quantity": quantity,
            "buy_price": buy_price,
            "buy_date": buy_date,
            "buy_currency": buy_currency,
            "current_price": current_price,
        }

        if buy_currency == "TRY":
            # TL alisi - basit hesap
            invested_tl = quantity * buy_price
            if current_price:
                current_value_tl = quantity * current_price
                gross_return_tl = current_value_tl - invested_tl
                gross_return_pct = (gross_return_tl / invested_tl * 100) if invested_tl else 0
                price_effect_pct = gross_return_pct
                fx_effect_pct = 0
            else:
                current_value_tl = None
                gross_return_tl = None
                gross_return_pct = None
                price_effect_pct = None
                fx_effect_pct = None

            result.update({
                "invested_tl": invested_tl,
                "current_value_tl": current_value_tl,
                "gross_return_tl": gross_return_tl,
                "gross_return_pct": gross_return_pct,
                "price_effect_pct": price_effect_pct,
                "fx_effect_pct": fx_effect_pct,
            })

        else:  # USD
            # USD alisi - kur ayrustirmasi
            invested_usd = quantity * buy_price
            invested_tl_at_buy = invested_usd * buy_date_usd_try

            result.update({
                "invested_usd": invested_usd,
                "invested_tl_at_buy": invested_tl_at_buy,
                "buy_date_usd_try": buy_date_usd_try,
                "current_usd_try": current_usd_try,
            })

            if current_price and current_usd_try:
                current_value_usd = quantity * current_price
                current_value_tl = current_value_usd * current_usd_try

                # Brut getiri (toplam)
                gross_return_tl = current_value_tl - invested_tl_at_buy
                gross_return_pct = (gross_return_tl / invested_tl_at_buy * 100) if invested_tl_at_buy else 0

                # Fiyat etkisi (USD cinsinden)
                price_return_usd = current_value_usd - invested_usd
                price_return_pct = (price_return_usd / invested_usd * 100) if invested_usd else 0

                # Kur etkisi
                fx_effect_pct = ((current_usd_try / buy_date_usd_try - 1) * 100) if buy_date_usd_try else 0

                result.update({
                    "current_value_usd": current_value_usd,
                    "current_value_tl": current_value_tl,
                    "gross_return_tl": round(gross_return_tl, 2),
                    "gross_return_pct": round(gross_return_pct, 2),
                    "price_effect_pct": round(price_return_pct, 2),
                    "fx_effect_pct": round(fx_effect_pct, 2),
                })
            else:
                result.update({
                    "current_value_usd": None,
                    "current_value_tl": None,
                    "gross_return_tl": None,
                    "gross_return_pct": None,
                    "price_effect_pct": None,
                    "fx_effect_pct": None,
                })

        results.append(result)

    # Portfoy ozeti
    total_value_tl = sum(
        r.get("current_value_tl") or 0
        for r in results if r.get("current_value_tl") is not None
    )

    total_invested_tl = sum(
        r.get("invested_tl") or r.get("invested_tl_at_buy") or 0
        for r in results
    )

    total_return_tl = total_value_tl - total_invested_tl
    total_return_pct = (total_return_tl / total_invested_tl * 100) if total_invested_tl else 0

    # Varlik sinifina gore ozet
    summary_by_class = {}
    for r in results:
        cls = r["asset_class"]
        if cls not in summary_by_class:
            summary_by_class[cls] = {
                "count": 0,
                "invested_tl": 0,
                "current_value_tl": 0,
                "return_tl": 0,
                "return_pct": 0,
            }

        summary_by_class[cls]["count"] += 1

        invested = r.get("invested_tl") or r.get("invested_tl_at_buy") or 0
        current = r.get("current_value_tl") or 0

        summary_by_class[cls]["invested_tl"] += invested
        summary_by_class[cls]["current_value_tl"] += current

    for cls in summary_by_class:
        inv = summary_by_class[cls]["invested_tl"]
        curr = summary_by_class[cls]["current_value_tl"]
        summary_by_class[cls]["return_tl"] = round(curr - inv, 2)
        summary_by_class[cls]["return_pct"] = round((curr - inv) / inv * 100, 2) if inv else 0

    return {
        "timestamp": datetime.now().isoformat(),
        "holdings": results,
        "summary": {
            "total_invested_tl": round(total_invested_tl, 2),
            "total_value_tl": round(total_value_tl, 2),
            "total_return_tl": round(total_return_tl, 2),
            "total_return_pct": round(total_return_pct, 2),
            "by_asset_class": summary_by_class,
        }
    }

if __name__ == "__main__":
    print("\nPortfoy hesaplaniyor...\n")
    portfolio = calculate_portfolio()

    print("="*80)
    print("PORTFOLIO OZETI")
    print("="*80)

    s = portfolio["summary"]
    print(f"Toplam Yatirilan: {s['total_invested_tl']:,.2f} TRY")
    print(f"Guncel Deger: {s['total_value_tl']:,.2f} TRY")
    print(f"Brut Getiri: {s['total_return_tl']:,.2f} TRY ({s['total_return_pct']:.2f}%)")

    print("\nVarlik Sinifina Gore:")
    for cls, info in s["by_asset_class"].items():
        print(f"  {cls}: {info['current_value_tl']:,.2f} TRY ({info['return_pct']:.2f}%)")

    print("\nDetayli Holdings:")
    print(f"{'Ticker':<10} | {'Sinif':<15} | {'Adet':<8} | {'Guncel Deger (TRY)':<18} | {'Getiri %':<10}")
    print("-"*80)

    for h in portfolio["holdings"]:
        val = h.get("current_value_tl") or 0
        ret = h.get("gross_return_pct") or 0
        print(f"{h['ticker']:<10} | {h['asset_class']:<15} | {h['quantity']:<8} | {val:>16,.2f} | {ret:>9.2f}%")

    # portfolio_full.json'a kaydet
    with open("portfolio_full.json", "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)

    print("\n[OK] Portfoy portfolio_full.json'a kaydedildi.")
