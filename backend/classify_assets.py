"""
ADIM 1: Otomatik Varlik Siniflandirilmasi
23 pozisyonu sirayla test et ve siniflandir
"""
import twelve_data as td
import requests
import json
from datetime import datetime
import sys
import os

# UTF-8 support for Windows console
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Siniflandirilacak tickers (kullanici tarafindan saglanan)
TICKERS = [
    "JET", "SAS", "TI3", "YAS", "KZL", "AFA", "AFT", "GESAN",
    "PATEK", "GWIND", "GO2", "GO3", "GO4", "CWENE", "SDTTR", "ASELS",
    "TAO", "BRETT", "BTC", "YAY", "AFV", "BIH", "HBU",
    "DXYZ", "PTF", "ARKQ", "AIQ", "JMOM", "SMH",
    "QQQ", "BOTZ", "VEA", "VOO", "VTI", "QQQM", "ARKK", "VNQ",
    "BRK.B", "URNM", "UPST"
]

def get_tefas_funds():
    """pytefas'tan tum TEFAS fon kodlarini al"""
    try:
        from pytefas.client import tefas
        # pytefas.client.tefas.get_funds() var
        funds = tefas.get_funds()
        fund_codes = {f.code: f.name for f in funds}
        return fund_codes
    except Exception as e:
        try:
            from pytefas import Crawler
            crawler = Crawler()
            funds = crawler.get_all_funds()
            fund_codes = {f.code: f.name for f in funds}
            return fund_codes
        except Exception as e2:
            return {}

def check_twelve_data(symbol):
    """Twelve Data'dan veri alınabilir mi kontrol et"""
    try:
        price = td.get_price(symbol)
        return price is not None and price > 0
    except:
        return False

def check_coingecko(symbol):
    """CoinGecko'dan kripto verisini kontrol et"""
    try:
        # Yaygın kripto sembol haritalandırması
        crypto_map = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "BNB": "binancecoin",
            "SOL": "solana",
            "XRP": "ripple",
            "ADA": "cardano",
            "DOGE": "dogecoin",
            "AVAX": "avalanche-2",
            "DOT": "polkadot",
            "LTC": "litecoin",
            "NEAR": "near",
            "SUI": "sui"
        }
        coin_id = crypto_map.get(symbol.upper(), symbol.lower())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        resp = requests.get(url, timeout=5)
        if resp.ok:
            data = resp.json()
            return coin_id in data
    except:
        pass
    return False

def classify_ticker(ticker):
    """
    Varlik sinifini belirle.
    Returns: {class, source, note}
    """

    # 1. TEFAS fon kontrolü
    tefas_funds = get_tefas_funds()
    if ticker.upper() in tefas_funds:
        return {
            "class": "TEFAS Fonu",
            "source": "pytefas",
            "note": f"Kod: {ticker}, Adı: {tefas_funds[ticker.upper()]}"
        }

    # 2. BIST kontrolü
    if check_twelve_data(f"{ticker}.IS"):
        try:
            p = td.get_profile(f"{ticker}.IS") or {}
            name = p.get("name", ticker)
            return {
                "class": "BIST Hissesi",
                "source": "Twelve Data (.IS)",
                "note": f"Sembol: {ticker}.IS"
            }
        except:
            pass

    # 3. ABD borsası kontrolü
    if check_twelve_data(ticker):
        try:
            p = td.get_profile(ticker) or {}
            exchange = p.get("exchange", "N/A")
            return {
                "class": "ABD Hisse/ETF",
                "source": "Twelve Data",
                "note": f"Borsası: {exchange}"
            }
        except:
            pass

    # 4. Kripto kontrolü
    if check_coingecko(ticker.upper()):
        return {
            "class": "Kripto",
            "source": "CoinGecko",
            "note": f"Sembol: {ticker}"
        }

    # Twelve Data üzerinden kripto kontrolü (BTC-USD vs)
    for suffix in ["-USD", "USD"]:
        crypto_ticker = f"{ticker}{suffix}" if not ticker.endswith(suffix) else ticker
        if check_twelve_data(crypto_ticker):
            try:
                q = td.get_quote(crypto_ticker) or {}
                # Kriptolar Twelve Data'da genellikle Forex/Crypto olarak geçer
                if q.get("exchange") in ("Crypto", "Forex") or "Spot" in q.get("name", ""):
                    return {
                        "class": "Kripto",
                        "source": "Twelve Data",
                        "note": f"Sembol: {crypto_ticker}"
                    }
            except:
                pass

    # 5. Siniflandirilamamis
    return {
        "class": "[WARN] Siniflandirilamamis",
        "source": "MANUEL KONTROL GEREKLI",
        "note": "Hicbir kaynakta bulunamadi - manual arastirma gerekli"
    }

def main():
    print("\n" + "="*80)
    print("ADIM 1: OTOMATIK VARLIK SINIFLANDIRILMASI")
    print("="*80)

    classifications = {}
    results = []

    for ticker in TICKERS:
        print(f"Kontrol ediliyor: {ticker}...", end=" ", flush=True)
        result = classify_ticker(ticker)
        classifications[ticker] = result
        results.append({
            "Ticker": ticker,
            "Tespit Edilen Sinif": result["class"],
            "Kaynagi": result["source"],
        })
        print(f"[OK] {result['class']}")

    # Tablo göster
    print("\n" + "-"*100)
    print(f"{'Ticker':<12} | {'Tespit Edilen Sinif':<25} | {'Kaynagi':<30} | Notlar")
    print("-"*100)

    for ticker in TICKERS:
        r = classifications[ticker]
        print(f"{ticker:<12} | {r['class']:<25} | {r['source']:<30} | {r['note']}")

    print("-"*100)

    # Ozet
    class_counts = {}
    for ticker, r in classifications.items():
        cls = r["class"]
        class_counts[cls] = class_counts.get(cls, 0) + 1

    print("\nOZET:")
    for cls, count in sorted(class_counts.items()):
        print(f"  {cls}: {count}")

    # JSON'a kaydet (ADIM 3'te kullanilacak)
    with open("classifications.json", "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "classifications": classifications,
            "summary": class_counts
        }, f, indent=2, ensure_ascii=False)

    print("\n[OK] Siniflandiirmalar classifications.json'a kaydedildi.")

    # Hata kontrolu
    unclassified = [t for t, r in classifications.items() if "[WARN]" in r["class"]]
    if unclassified:
        print(f"\n[WARN] {len(unclassified)} ticker siniflandirilamamadi: {', '.join(unclassified)}")
        print("Bu tickers'i manuel olarak kontrol et!")

    return classifications

if __name__ == "__main__":
    classifications = main()
