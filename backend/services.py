import twelve_data as td
import requests
import json
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List

from crud import (
    get_positions, get_exchange_rate, get_eur_exchange_rate, get_gbp_exchange_rate,
    save_exchange_rate, save_price_history,
    get_transactions, create_notification, get_price_alerts, trigger_price_alert, get_target_allocations
)
from models import ExchangeRateCreate, PriceHistoryCreate
from database import get_db_session
import historical_db
import pandas as pd
import math
from cache import finance_cache as _svc_fc

# TEFAS DataFrame cache
_tefas_cache = None
_tefas_cache_date = None

# CoinGecko ticker → ID eşlemesi (API key gerektirmez)
COINGECKO_IDS: Dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
    "SOL": "solana", "XRP": "ripple", "ADA": "cardano",
    "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
    "MATIC": "matic-network", "LINK": "chainlink", "UNI": "uniswap",
    "LTC": "litecoin", "ATOM": "cosmos", "XLM": "stellar",
    "TAO": "bittensor", "BRETT": "based-brett", "OP": "optimism",
    "ARB": "arbitrum", "INJ": "injective-protocol", "TIA": "celestia",
    "NEAR": "near", "APT": "aptos", "SUI": "sui",
}

# yfinance için özel kripto ticker eşlemeleri (normal -USD formatı çalışmayanlar)
YFINANCE_CRYPTO_MAP: Dict[str, str] = {
    "TAO": "TAO22974-USD",
    "BRETT": "BRETT29743-USD",
    "SUI": "SUI20947-USD",
    "APT": "APT21794-USD",
}

# Coinpaprika ticker → ID eşlemesi (firewall bypass için stabil fallback)
COINPAPRIKA_IDS: Dict[str, str] = {
    "BTC": "btc-bitcoin", "ETH": "eth-ethereum", "BNB": "bnb-binance-coin",
    "SOL": "sol-solana", "XRP": "xrp-xrp", "ADA": "ada-cardano",
    "DOGE": "doge-dogecoin", "AVAX": "avax-avalanche", "DOT": "dot-polkadot",
    "MATIC": "matic-polygon", "LINK": "link-chainlink", "UNI": "uni-uniswap",
    "LTC": "ltc-litecoin", "ATOM": "atom-cosmos", "XLM": "xlm-stellar",
    "TAO": "tao-bittensor", "BRETT": "brett-brett-base", "OP": "op-optimism",
    "ARB": "arb-arbitrum", "INJ": "inj-injective-protocol", "TIA": "tia-celestia",
    "NEAR": "near-near-protocol", "APT": "apt-aptos", "SUI": "sui-sui",
}

_COINGECKO_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def _coinpaprika_batch(tickers: List[str]) -> Dict[str, float]:
    """Coinpaprika batch fiyat çek. Az sayıda ise tek tek, çok ise toplu çekim yapar."""
    result = {}
    known_tickers = [t.upper() for t in tickers if t.upper() in COINPAPRIKA_IDS]
    if not known_tickers:
        return {}
        
    if len(known_tickers) <= 3:
        # Az sayıda ise hızlıca tekil API istekleri yap
        for ticker in known_tickers:
            cp_id = COINPAPRIKA_IDS[ticker]
            try:
                r = requests.get(f"https://api.coinpaprika.com/v1/tickers/{cp_id}", timeout=5)
                if r.ok:
                    data = r.json()
                    result[ticker] = float(data["quotes"]["USD"]["price"])
            except Exception as e:
                print(f"[WARN] Coinpaprika single fetch error for {ticker}: {e}")
    else:
        # Çok sayıda ise tüm listeyi bir kerede çek ve filtrele
        try:
            r = requests.get("https://api.coinpaprika.com/v1/tickers", timeout=10)
            if r.ok:
                data = r.json()
                id_map = {c["id"]: float(c["quotes"]["USD"]["price"]) for c in data if "quotes" in c and "USD" in c["quotes"]}
                for ticker in known_tickers:
                    cp_id = COINPAPRIKA_IDS[ticker]
                    if cp_id in id_map:
                        result[ticker] = id_map[cp_id]
        except Exception as e:
            print(f"[WARN] Coinpaprika batch fetch error: {e}")
    return result

def _coingecko_batch(tickers: List[str]) -> Dict[str, float]:
    """CoinGecko batch fiyat çek. Dönen dict: {TICKER: usd_price}"""
    ids_map = {t: COINGECKO_IDS.get(t.upper()) for t in tickers}
    known = {t: cg for t, cg in ids_map.items() if cg}
    if not known:
        return {}
    ids_str = ",".join(set(known.values()))
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={ids_str}&vs_currencies=usd",
            timeout=10, headers=_COINGECKO_UA
        )
        if not r.ok:
            return {}
        data = r.json()
        result = {}
        for ticker, cg_id in known.items():
            try:
                result[ticker] = float(data[cg_id]["usd"])
            except Exception:
                pass
        return result
    except Exception as e:
        print(f"[WARN] CoinGecko batch: {e}")
        return {}

def get_price_currency(asset_class: str) -> str:
    """get_current_price'ın belirli bir asset_class için döndürdüğü fiyatın hangi para
    biriminde olduğunu söyler (piyasanın kendi native para birimi — buy_currency değil).
    TEFAS Fonu ve BIST Hissesi TRY'de fiyatlanır, ABD Hisse/ETF ve Kripto USD'de."""
    if asset_class in ("TEFAS Fonu", "BIST Hissesi"):
        return "TRY"
    return "USD"


def get_current_price(ticker: str, asset_class: str) -> Optional[float]:
    """Guncel fiyat al (yfinance / CoinMarketCap / pytefas)"""
    global _tefas_cache, _tefas_cache_date
    try:
        if asset_class == "TEFAS Fonu":
            return td.get_tefas_current_price(ticker)

        elif asset_class == "BIST Hissesi":
            return td.get_price(ticker)

        elif asset_class == "ABD Hisse/ETF":
            return td.get_price(ticker)

        elif asset_class == "Kripto":
            price = td.get_price(f"{ticker}-USD")
            if price and price > 0.0001:
                return price
            # Coinpaprika fallback
            result = _coinpaprika_batch([ticker])
            if ticker.upper() in result:
                return result[ticker.upper()]
            # CoinGecko fallback
            result = _coingecko_batch([ticker])
            if ticker in result:
                return result[ticker]
        return None
    except Exception as e:
        print(f"[WARN] {ticker} fiyati alinamadi: {e}")
        return None

def _fetch_current_rates_fast() -> dict:
    """USD/TRY, EUR/TRY ve GBP/TRY kurlarını hızlıca çek (CORS/Sınır aşımı önleyici)"""
    try:
        import requests
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=1.5)
        if r.ok:
            data = r.json()
            rates = data.get("rates", {})
            try_rate = rates.get("TRY")
            eur_rate = rates.get("EUR")
            gbp_rate = rates.get("GBP")
            if try_rate:
                eur_try = try_rate / eur_rate if eur_rate else 1.08 * try_rate
                gbp_try = try_rate / gbp_rate if gbp_rate else 1.27 * try_rate
                return {
                    "usd": float(try_rate),
                    "eur": float(eur_try),
                    "gbp": float(gbp_try)
                }
    except Exception as e:
        print(f"[WARN] Fast rates fetch failed: {e}")
    return {}

def get_usd_try_rate(date_str: Optional[str] = None) -> float:
    """USD/TRY kurunu al"""
    try:
        cache_key = f"usdtry_{date_str}" if date_str else "usdtry_current"
        cached = _svc_fc.get(cache_key, ttl=3600)
        if cached:
            return float(cached)

        if date_str:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_obj > datetime.now().date():
                return get_usd_try_rate()

            # DB'den kontrol et
            cached_db = get_exchange_rate(date_obj)
            if cached_db:
                _svc_fc.set(cache_key, cached_db)
                return cached_db

            # Twelve Data'dan geçmiş kur (DESC sıralı)
            days_back = (datetime.now().date() - date_obj).days + 5
            series = td.get_time_series("USD/TRY", days=max(30, min(730, days_back)), interval="1day")
            for item in series:
                if item.get("date", "")[:10] <= date_str and item.get("close"):
                    rate = float(item["close"])
                    try:
                        save_exchange_rate(ExchangeRateCreate(
                            rate_date=date_obj, usd_try_rate=rate, source="twelve_data"
                        ))
                    except Exception:
                        pass
                    _svc_fc.set(cache_key, rate)
                    return rate

        # Güncel kur — önce hızlı servis
        fast = _fetch_current_rates_fast()
        if fast:
            _svc_fc.set("usdtry_current", fast["usd"])
            _svc_fc.set("eurtry_current", fast["eur"])
            _svc_fc.set("gbptry_current", fast["gbp"])
            return fast["usd"]

        # Twelve Data fallback
        rate = td.get_exchange_rate("USD/TRY")
        if rate:
            _svc_fc.set(cache_key, rate)
            return rate

        return 35.0
    except Exception as e:
        print(f"[WARN] USD/TRY kuru alinamadi: {e}")
        return 35.0

def get_eur_try_rate(date_str: Optional[str] = None) -> float:
    """EUR/TRY kurunu al"""
    try:
        cache_key = f"eurtry_{date_str}" if date_str else "eurtry_current"
        cached = _svc_fc.get(cache_key, ttl=3600)
        if cached:
            return float(cached)

        if date_str:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_obj > datetime.now().date():
                return get_eur_try_rate()

            # DB'den kontrol et (kalıcı, geçmiş tarihli kurlar değişmez)
            cached_db = get_eur_exchange_rate(date_obj)
            if cached_db:
                _svc_fc.set(cache_key, cached_db)
                return cached_db

            days_back = (datetime.now().date() - date_obj).days + 5
            series = td.get_time_series("EUR/TRY", days=max(30, min(730, days_back)), interval="1day")
            for item in series:
                if item.get("date", "")[:10] <= date_str and item.get("close"):
                    rate = float(item["close"])
                    try:
                        save_exchange_rate(ExchangeRateCreate(
                            rate_date=date_obj, eur_try_rate=rate, source="twelve_data"
                        ))
                    except Exception:
                        pass
                    _svc_fc.set(cache_key, rate)
                    return rate

        # Güncel kur — önce hızlı servis
        fast = _fetch_current_rates_fast()
        if fast:
            _svc_fc.set("usdtry_current", fast["usd"])
            _svc_fc.set("eurtry_current", fast["eur"])
            _svc_fc.set("gbptry_current", fast["gbp"])
            return fast["eur"]

        # Twelve Data fallback
        rate = td.get_exchange_rate("EUR/TRY")
        if rate:
            _svc_fc.set(cache_key, rate)
            return rate

        return 38.0
    except Exception as e:
        print(f"[WARN] EUR/TRY kuru alinamadi: {e}")
        return 38.0


def get_gbp_try_rate(date_str: Optional[str] = None) -> float:
    """GBP/TRY kurunu al"""
    try:
        cache_key = f"gbptry_{date_str}" if date_str else "gbptry_current"
        cached = _svc_fc.get(cache_key, ttl=3600)
        if cached:
            return float(cached)

        if date_str:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_obj > datetime.now().date():
                return get_gbp_try_rate()

            # DB'den kontrol et (kalıcı, geçmiş tarihli kurlar değişmez)
            cached_db = get_gbp_exchange_rate(date_obj)
            if cached_db:
                _svc_fc.set(cache_key, cached_db)
                return cached_db

            days_back = (datetime.now().date() - date_obj).days + 5
            series = td.get_time_series("GBP/TRY", days=max(30, min(730, days_back)), interval="1day")
            for item in series:
                if item.get("date", "")[:10] <= date_str and item.get("close"):
                    rate = float(item["close"])
                    try:
                        save_exchange_rate(ExchangeRateCreate(
                            rate_date=date_obj, gbp_try_rate=rate, source="twelve_data"
                        ))
                    except Exception:
                        pass
                    _svc_fc.set(cache_key, rate)
                    return rate

        # Güncel kur — önce hızlı servis
        fast = _fetch_current_rates_fast()
        if fast:
            _svc_fc.set("usdtry_current", fast["usd"])
            _svc_fc.set("eurtry_current", fast["eur"])
            _svc_fc.set("gbptry_current", fast["gbp"])
            return fast["gbp"]

        # Twelve Data fallback
        rate = td.get_exchange_rate("GBP/TRY")
        if rate:
            _svc_fc.set(cache_key, rate)
            return rate

        return 43.0
    except Exception as e:
        print(f"[WARN] GBP/TRY kuru alinamadi: {e}")
        return 43.0


# Portföy özeti önbelleği — Redis üzerinden (finance_cache/_svc_fc), KULLANICI BAŞINA anahtarlı.
# ÖNEMLİ (iki ayrı hata düzeltildi):
# 1. Eskiden tek bir global değişkendi (kullanıcı ayrımı yoktu) — bir kullanıcı portföyünü
#    çektikten sonra 5 dakika içinde gelen HERHANGİ BİR başka kullanıcı da o kullanıcının
#    verisini görüyordu (canlıda bulundu: yeni bir Google hesabına demo'nun 40 pozisyonu
#    gösterildi).
# 2. Sonra user_id ile anahtarlanan bir Python dict'e çevrildi, AMA bu hâlâ her servisin
#    (api, celery-worker) kendi belleğinde AYRI AYRI tutuluyordu — celery-worker'daki arka
#    plan ısıtma görevi kendi belleğini dolduruyor, api servisinin gerçek istekleri karşılayan
#    belleğine hiç yansımıyordu (ısıtma görevi fiilen boşa çalışıyordu). Artık Redis'te
#    (REDIS_URL varsa) tutuluyor — tüm servisler AYNI önbelleği paylaşıyor.
CACHE_TTL_SECONDS = 300  # Cache for 5 minutes

# In-memory cache for TWRR/performance
_twrr_cache: dict = {}
_twrr_cache_time: dict = {}
TWRR_CACHE_TTL = 1200  # 20 minutes

def batch_fetch_prices(positions: List[Dict]) -> tuple[Dict[str, float], Dict[str, float]]:
    """Fiyatları ve (varsa) günlük değişim yüzdelerini birlikte döner.
    Returns: (prices, changes) — changes içinde veri bulunamayan semboller yer almaz."""
    prices = {}
    changes: Dict[str, float] = {}

    bist_tickers = []
    us_tickers = []
    crypto_tickers = []
    tefas_tickers = []
    
    for pos in positions:
        ticker = pos['ticker']
        ac = pos['asset_class']
        if ac == "BIST Hissesi":
            bist_tickers.append(ticker)
        elif ac == "ABD Hisse/ETF":
            us_tickers.append(ticker)
        elif ac == "Kripto":
            crypto_tickers.append(ticker)
        elif ac == "TEFAS Fonu":
            tefas_tickers.append(ticker)
            
    # Dövizler, emtialar ve hisselerin tamamı için Twelve Data listesini hazırla
    extra_tickers = ["USDTRY=X", "EURTRY=X", "GBPTRY=X", "GC=F", "SI=F"]
    # BIST: bare symbol çalışıyor (ASELS), ASELS:XIST ücretsiz planda null döner
    all_raw = list(set(bist_tickers + us_tickers + extra_tickers))

    # 1. Twelve Data batch_quotes ile indir (veya veritabanı önbelleğinden al)
    try:
        print(f"[BATCH] Downloading {len(all_raw)} tickers from Twelve Data...")
        quotes = td.batch_quotes(all_raw)
        for orig_sym, q_data in quotes.items():
            val = q_data.get("close")
            if val is not None:
                prices[orig_sym] = float(val)
            chg = q_data.get("change_pct")
            if chg is not None:
                changes[orig_sym] = float(chg)
    except Exception as e:
        print(f"[WARN] Twelve Data batch download failed: {e}")
        
    # Kriptolar için
    if crypto_tickers:
        unique_crypto = list(set(crypto_tickers))
        cryptos_to_fetch = [f"{c}-USD" for c in unique_crypto]
        try:
            print(f"[BATCH] Fetching {len(cryptos_to_fetch)} cryptos from Twelve Data...")
            c_quotes = td.batch_quotes(cryptos_to_fetch)
            for orig_sym, q_data in c_quotes.items():
                val = q_data.get("close")
                if val is not None and float(val) > 0.0001:
                    val_float = float(val)
                    clean_c = orig_sym.replace("-USD", "")
                    prices[clean_c] = val_float
                    prices[orig_sym] = val_float
                chg = q_data.get("change_pct")
                if chg is not None:
                    clean_c = orig_sym.replace("-USD", "")
                    changes[clean_c] = float(chg)
                    changes[orig_sym] = float(chg)
        except Exception as e:
            print(f"[WARN] Crypto Twelve Data batch failed: {e}")
            
        # Coinpaprika & Coingecko fallbacks
        missing = [c for c in unique_crypto if c not in prices]
        if missing:
            print(f"[BATCH] Fetching {len(missing)} cryptos from Coinpaprika fallback: {missing}")
            cp_prices = _coinpaprika_batch(missing)
            for k, v in cp_prices.items():
                prices[k] = v
                prices[f"{k}-USD"] = v
                
            missing_still = [c for c in missing if c not in prices]
            if missing_still:
                print(f"[BATCH] Fetching {len(missing_still)} cryptos from CoinGecko fallback: {missing_still}")
                cg_prices = _coingecko_batch(missing_still)
                for k, v in cg_prices.items():
                    prices[k] = v
                    prices[f"{k}-USD"] = v

    # TEFAS Fonları için paralel fiyat sorgulama
    if tefas_tickers:
        unique_tefas = list(set(tefas_tickers))
        print(f"[BATCH] Fetching {len(unique_tefas)} TEFAS funds in parallel...")
        from concurrent.futures import ThreadPoolExecutor
        def _fetch_one_tefas(code):
            try:
                price = td.get_tefas_current_price(code)
                chg = td.get_tefas_daily_change_pct(code) if price is not None else None
                return code, price, chg
            except Exception as e:
                print(f"[WARN] Failed to fetch TEFAS price for {code}: {e}")
                return code, None, None

        with ThreadPoolExecutor(max_workers=len(unique_tefas)) as executor:
            res = list(executor.map(_fetch_one_tefas, unique_tefas))
            for code, p, chg in res:
                if p is not None:
                    prices[code] = p
                if chg is not None:
                    changes[code] = chg

    return prices, changes

def calculate_portfolio(user_id: int, bypass_cache: bool = False) -> Dict:
    """Portföyü hesapla"""
    cache_key = f"portfolio_cache:{user_id}"

    if not bypass_cache:
        cached = _svc_fc.get(cache_key, CACHE_TTL_SECONDS)
        if cached is not None:
            print(f"[CACHE] Returning cached portfolio calculations (user_id={user_id})")
            return cached

    with get_db_session() as conn:
        positions = get_positions(user_id)

    # Batch fetch all prices at once
    batch_prices, batch_changes = batch_fetch_prices(positions)

    results = []
    # Get current USDTRY and EURTRY rates from batch prices if available, otherwise fetch
    current_usd_try = batch_prices.get("USDTRY=X", get_usd_try_rate())
    current_eur_try = batch_prices.get("EURTRY=X", get_eur_try_rate())
    current_gbp_try = batch_prices.get("GBPTRY=X", get_gbp_try_rate())

    _usd_rate_cache: dict[str, float] = {}
    _eur_rate_cache: dict[str, float] = {}
    _gbp_rate_cache: dict[str, float] = {}

    def _buy_usd_rate(date_str: str) -> float:
        if date_str not in _usd_rate_cache:
            _usd_rate_cache[date_str] = get_usd_try_rate(date_str)
        return _usd_rate_cache[date_str]

    def _buy_eur_rate(date_str: str) -> float:
        if date_str not in _eur_rate_cache:
            _eur_rate_cache[date_str] = get_eur_try_rate(date_str)
        return _eur_rate_cache[date_str]

    def _buy_gbp_rate(date_str: str) -> float:
        if date_str not in _gbp_rate_cache:
            _gbp_rate_cache[date_str] = get_gbp_try_rate(date_str)
        return _gbp_rate_cache[date_str]

    for pos in positions:
        ticker = pos['ticker']
        asset_class = pos['asset_class']
        quantity = pos['quantity']
        buy_price = pos['buy_price']
        buy_currency = pos['buy_currency']
        buy_date = pos['buy_date']
        cost_basis_tly = pos.get('cost_basis_tly')
        
        # New fields
        asset_type = pos.get('asset_type')
        if not asset_type:
            if asset_class == 'TEFAS Fonu': asset_type = 'fund'
            elif asset_class == 'BIST Hissesi': asset_type = 'stock_tr'
            elif asset_class == 'ABD Hisse/ETF': asset_type = 'stock_us'
            elif asset_class == 'Kripto': asset_type = 'crypto'
            elif asset_class == 'Nakit': asset_type = 'cash'
            elif asset_class == 'Emtia': asset_type = 'commodity'
            else: asset_type = 'stock_tr'

        interest_rate = pos.get('interest_rate')
        maturity_date = pos.get('maturity_date')
        commodity_type = pos.get('commodity_type')
        unit = pos.get('unit')

        # Determine current price
        current_price = None
        if asset_type == 'cash':
            # Cash price is base 1.0, but grows with interest over time if interest_rate is set
            interest_factor = 1.0
            if interest_rate and interest_rate > 0:
                if isinstance(buy_date, str):
                    buy_date_obj = datetime.strptime(buy_date, "%Y-%m-%d").date()
                else:
                    buy_date_obj = buy_date
                days_held = (datetime.now().date() - buy_date_obj).days
                if days_held < 0:
                    days_held = 0
                interest_factor = 1.0 + (interest_rate / 100.0) * (days_held / 365.0)
            current_price = buy_price * interest_factor
            price_currency = buy_currency
        elif asset_type == 'commodity' and commodity_type == 'physical':
            # Physical commodity GOLD / SILVER
            futures_ticker = "GC=F" if ticker in ["GOLD", "XAU"] else "SI=F"
            futures_usd = batch_prices.get(futures_ticker)
            if futures_usd is None:
                futures_usd = get_current_price(futures_ticker, "ABD Hisse/ETF")
            if futures_usd is None:
                futures_usd = 2300.0 if futures_ticker == "GC=F" else 28.0
            
            # calculate price in USD based on unit
            if unit == 'gram':
                price_usd_val = futures_usd / 31.1034768
            else:
                price_usd_val = futures_usd
            
            # Convert USD price to native buy_currency
            if buy_currency == "TRY":
                current_price = price_usd_val * current_usd_try
            elif buy_currency == "USD":
                current_price = price_usd_val
            elif buy_currency == "EUR":
                current_price = price_usd_val * (current_usd_try / current_eur_try)
            price_currency = buy_currency
        else:
            # Stocks, funds, crypto, paper commodities
            current_price = batch_prices.get(ticker)
            if current_price is None:
                current_price = get_current_price(ticker, asset_class)
            price_currency = get_price_currency(asset_class)

        buy_date_str = buy_date if isinstance(buy_date, str) else str(buy_date)
        # Alım tarihindeki kurlar — pozisyon hangi para biriminde alınmış olursa olsun HER ZAMAN
        # hesaplanır. Böylece "yatırılan tutar" her para birimine KENDİ alım-tarihi paritesiyle
        # çevrilebilir (TL üzerinden bugünün kuruyla dolaylı çevrim yapılmaz — bu, fiyatı hiç
        # değişmemiş USD bir pozisyonun sırf TL arada dolaştığı için sahte kâr/zarar göstermesine
        # yol açan eski hataydı).
        buy_date_usd_try = _buy_usd_rate(buy_date_str)
        buy_date_eur_try = _buy_eur_rate(buy_date_str)
        buy_date_gbp_try = _buy_gbp_rate(buy_date_str)

        result = {
            "id": pos['id'],
            "ticker": ticker,
            "asset_class": asset_class,
            "quantity": quantity,
            "buy_price": buy_price,
            "buy_date": buy_date,
            "buy_currency": buy_currency,
            "cost_basis_tly": cost_basis_tly,
            "current_price": current_price,
            "price_currency": price_currency,
            "change_pct": batch_changes.get(ticker),
            "asset_type": asset_type,
            "interest_rate": interest_rate,
            "maturity_date": maturity_date,
            "commodity_type": commodity_type,
            "unit": unit
        }

        # 1) Yatırılan tutarı TRY'ye çevir (buy_currency'ye göre, alım tarihi kuruyla).
        #    cost_basis_tly elle kaydedilmişse (gerçek TL karşılığı biliniyorsa) o esas alınır
        #    ve o pozisyonun implicit alım-tarihi kuru buna göre geri türetilir.
        native_invested = quantity * buy_price
        if buy_currency == "TRY":
            invested_try = cost_basis_tly if cost_basis_tly is not None else native_invested
        elif buy_currency == "USD":
            if cost_basis_tly is not None:
                invested_try = cost_basis_tly
                if native_invested > 0:
                    buy_date_usd_try = cost_basis_tly / native_invested
            else:
                invested_try = native_invested * buy_date_usd_try
        elif buy_currency == "EUR":
            if cost_basis_tly is not None:
                invested_try = cost_basis_tly
                if native_invested > 0:
                    buy_date_eur_try = cost_basis_tly / native_invested
            else:
                invested_try = native_invested * buy_date_eur_try
        elif buy_currency == "GBP":
            if cost_basis_tly is not None:
                invested_try = cost_basis_tly
                if native_invested > 0:
                    buy_date_gbp_try = cost_basis_tly / native_invested
            else:
                invested_try = native_invested * buy_date_gbp_try
        else:
            invested_try = cost_basis_tly if cost_basis_tly is not None else native_invested

        # 2) TRY'deki yatırılan tutarı, HER para biriminin kendi alım-tarihi paritesiyle geri çevir.
        invested_usd = invested_try / buy_date_usd_try if buy_date_usd_try else None
        invested_eur = invested_try / buy_date_eur_try if buy_date_eur_try else None
        invested_gbp = invested_try / buy_date_gbp_try if buy_date_gbp_try else None

        result.update({
            "invested_tly": round(invested_try, 2),
            "invested_usd": round(invested_usd, 2) if invested_usd is not None else None,
            "invested_eur": round(invested_eur, 2) if invested_eur is not None else None,
            "invested_gbp": round(invested_gbp, 2) if invested_gbp is not None else None,
            "buy_date_usd_try": buy_date_usd_try,
            "buy_date_eur_try": buy_date_eur_try,
            "buy_date_gbp_try": buy_date_gbp_try,
            "current_usd_try": current_usd_try,
            "current_eur_try": current_eur_try,
            "current_gbp_try": current_gbp_try,
        })

        if current_price is None:
            result.update({
                "current_value_tly": None, "current_value_usd": None,
                "current_value_eur": None, "current_value_gbp": None,
                "gross_return_tly": None, "gross_return_pct": None,
                "gross_return_usd": None, "gross_return_usd_pct": None,
                "gross_return_eur": None, "gross_return_eur_pct": None,
                "gross_return_gbp": None, "gross_return_gbp_pct": None,
                "price_effect_pct": None, "fx_effect_pct": None,
            })
        else:
            # 3) Güncel değeri TRY'ye çevir (fiyatın kendi native para biriminden, BUGÜNÜN kuruyla).
            native_value = quantity * current_price
            if price_currency == "TRY":
                current_value_try = native_value
            elif price_currency == "USD":
                current_value_try = native_value * current_usd_try
            elif price_currency == "EUR":
                current_value_try = native_value * current_eur_try
            elif price_currency == "GBP":
                current_value_try = native_value * current_gbp_try
            else:
                current_value_try = native_value

            current_value_usd = current_value_try / current_usd_try if current_usd_try else None
            current_value_eur = current_value_try / current_eur_try if current_eur_try else None
            current_value_gbp = current_value_try / current_gbp_try if current_gbp_try else None

            gross_return_tly = current_value_try - invested_try
            gross_return_pct = (gross_return_tly / invested_try * 100.0) if invested_try else 0.0

            def _ret(cur, inv):
                if cur is None or inv is None:
                    return None, None
                r = cur - inv
                pct = (r / inv * 100.0) if inv else 0.0
                return round(r, 2), round(pct, 2)

            gross_return_usd, gross_return_usd_pct = _ret(current_value_usd, invested_usd)
            gross_return_eur, gross_return_eur_pct = _ret(current_value_eur, invested_eur)
            gross_return_gbp, gross_return_gbp_pct = _ret(current_value_gbp, invested_gbp)

            # Geriye dönük uyumluluk: price_effect_pct/fx_effect_pct, pozisyonun KENDİ alım
            # para biriminde fiyat hareketinin ve kur hareketinin TL getirisine katkısını ayırır.
            if buy_currency == "TRY":
                price_effect_pct = round(gross_return_pct, 2)
                fx_effect_pct = 0.0
            else:
                if price_currency == buy_currency and native_invested:
                    price_effect_pct = round((native_value - native_invested) / native_invested * 100.0, 2)
                else:
                    price_effect_pct = None
                buy_rate = {"USD": buy_date_usd_try, "EUR": buy_date_eur_try, "GBP": buy_date_gbp_try}.get(buy_currency)
                cur_rate = {"USD": current_usd_try, "EUR": current_eur_try, "GBP": current_gbp_try}.get(buy_currency)
                fx_effect_pct = round((cur_rate / buy_rate - 1.0) * 100.0, 2) if buy_rate and cur_rate else None

            result.update({
                "current_value_tly": round(current_value_try, 2),
                "current_value_usd": round(current_value_usd, 2) if current_value_usd is not None else None,
                "current_value_eur": round(current_value_eur, 2) if current_value_eur is not None else None,
                "current_value_gbp": round(current_value_gbp, 2) if current_value_gbp is not None else None,
                "gross_return_tly": round(gross_return_tly, 2),
                "gross_return_pct": round(gross_return_pct, 2),
                "gross_return_usd": gross_return_usd,
                "gross_return_usd_pct": gross_return_usd_pct,
                "gross_return_eur": gross_return_eur,
                "gross_return_eur_pct": gross_return_eur_pct,
                "gross_return_gbp": gross_return_gbp,
                "gross_return_gbp_pct": gross_return_gbp_pct,
                "price_effect_pct": price_effect_pct,
                "fx_effect_pct": fx_effect_pct,
            })

        results.append(result)

    # Portfolio özeti — TRY ve ayrıca USD/EUR/GBP cinsinden (her biri kendi alım-tarihi/bugünkü
    # paritesiyle doğrudan backend'de hesaplanır, frontend ek çevrim yapmaz).
    total_value_tly = sum(
        r.get("current_value_tly") or 0
        for r in results if r.get("current_value_tly") is not None
    )

    total_invested_tly = sum(
        r.get("invested_tly") or 0
        for r in results
    )

    total_return_tly = total_value_tly - total_invested_tly
    total_return_pct = (total_return_tly / total_invested_tly * 100) if total_invested_tly else 0

    def _totals(currency_key: str):
        invested = sum(r.get(f"invested_{currency_key}") or 0 for r in results)
        value = sum(
            r.get(f"current_value_{currency_key}") or 0
            for r in results if r.get(f"current_value_{currency_key}") is not None
        )
        ret = value - invested
        pct = (ret / invested * 100) if invested else 0
        return {
            "total_invested": round(invested, 2),
            "total_value": round(value, 2),
            "total_return": round(ret, 2),
            "total_return_pct": round(pct, 2),
        }

    totals_usd = _totals("usd")
    totals_eur = _totals("eur")
    totals_gbp = _totals("gbp")

    # Varlık sınıfı özeti
    summary_by_class = {}
    for r in results:
        cls = r["asset_class"]
        if cls not in summary_by_class:
            summary_by_class[cls] = {
                "count": 0,
                "invested_tly": 0,
                "current_value_tly": 0,
                "return_tly": 0,
                "return_pct": 0,
            }

        summary_by_class[cls]["count"] += 1
        invested = r.get("invested_tly") or 0
        current = r.get("current_value_tly") or 0

        summary_by_class[cls]["invested_tly"] += invested
        summary_by_class[cls]["current_value_tly"] += current

    for cls in summary_by_class:
        inv = summary_by_class[cls]["invested_tly"]
        curr = summary_by_class[cls]["current_value_tly"]
        summary_by_class[cls]["return_tly"] = round(curr - inv, 2)
        summary_by_class[cls]["return_pct"] = round((curr - inv) / inv * 100, 2) if inv else 0

    result = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_invested_tly": round(total_invested_tly, 2),
            "total_value_tly": round(total_value_tly, 2),
            "total_return_tly": round(total_return_tly, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_invested_usd": totals_usd["total_invested"],
            "total_value_usd": totals_usd["total_value"],
            "total_return_usd": totals_usd["total_return"],
            "total_return_usd_pct": totals_usd["total_return_pct"],
            "total_invested_eur": totals_eur["total_invested"],
            "total_value_eur": totals_eur["total_value"],
            "total_return_eur": totals_eur["total_return"],
            "total_return_eur_pct": totals_eur["total_return_pct"],
            "total_invested_gbp": totals_gbp["total_invested"],
            "total_value_gbp": totals_gbp["total_value"],
            "total_return_gbp": totals_gbp["total_return"],
            "total_return_gbp_pct": totals_gbp["total_return_pct"],
            "by_asset_class": summary_by_class,
        },
        "holdings": results,
    }
    _svc_fc.set(cache_key, result)
    
    # Run price alerts check and rebalance warnings in the background
    try:
        check_price_alerts_and_rebalancing(user_id, result)
    except Exception as ex:
        print(f"[WARN] Alerts check failed: {ex}")

    return result

def check_price_alerts_and_rebalancing(user_id: int, portfolio: Dict) -> None:
    # 1. Check price alerts
    alerts = get_price_alerts(user_id)
    active_alerts = [a for a in alerts if not a.get('is_triggered')]
    
    for alert in active_alerts:
        ticker = alert['ticker']
        target = alert['target_price']
        cond = alert['condition']
        
        # Find position
        pos = next((h for h in portfolio['holdings'] if h['ticker'] == ticker), None)
        if pos and pos.get('current_price') is not None:
            curr_price = pos['current_price']
            triggered = False
            if cond == 'ABOVE' and curr_price >= target:
                triggered = True
            elif cond == 'BELOW' and curr_price <= target:
                triggered = True
                
            if triggered:
                trigger_price_alert(alert['id'])
                msg = f"{ticker} fiyatı {cond.lower()} {target} oldu. Güncel fiyat: {curr_price} {pos['buy_currency']}"
                create_notification(user_id, "Fiyat Alarmı Tetiklendi", msg, "price_alert")
                
    # 2. Check rebalancing deviation (only if total value is positive)
    total_val = portfolio['summary']['total_value_tly']
    if total_val > 0:
        targets = get_target_allocations(user_id)
        if targets:
            for target in targets:
                asset_class = target['asset_class']
                target_pct = target['target_pct']
                current_val = portfolio['summary']['by_asset_class'].get(asset_class, {}).get('current_value_tly', 0)
                current_pct = (current_val / total_val) * 100.0
                deviation = abs(current_pct - target_pct)
                if deviation > 5.0:
                    title = "Rebalans Sapma Uyarısı"
                    msg = f"{asset_class} varlık sınıfı hedefinden %{deviation:.2f} saptı. Hedef: %{target_pct:.2f}, Güncel: %{current_pct:.2f}"
                    # Check if already exists to prevent spam
                    from crud import has_recent_notification, create_notification
                    if not has_recent_notification(user_id, "rebalance_alert", title, hours=1):
                        create_notification(user_id, title, msg, "rebalance_alert")

_MAJOR_CRYPTO_YF = {'BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'AVAX', 'DOT', 'LTC', 'LINK', 'UNI', 'ATOM', 'NEAR', 'OP', 'ARB', 'INJ', 'TIA', 'APT', 'SUI', 'TAO', 'BRETT'}

def get_ticker_historical_prices(ticker: str, asset_type: str, start_date: date, end_date: date) -> Dict[date, float]:
    # DEX/meme coins not listed on Yahoo Finance → skip yfinance, use buy price fallback
    if asset_type == 'crypto' and ticker.upper() in COINGECKO_IDS and ticker.upper() not in _MAJOR_CRYPTO_YF:
        return {}

    yf_ticker = ticker
    if asset_type == 'stock_tr' and not ticker.endswith('.IS'):
        yf_ticker = f"{ticker}.IS"
    elif asset_type == 'crypto':
        t_upper = ticker.upper()
        yf_ticker = YFINANCE_CRYPTO_MAP.get(t_upper, t_upper if t_upper.endswith('-USD') else f"{t_upper}-USD")
    elif asset_type == 'commodity':
        if ticker in ['GOLD', 'XAU']:
            yf_ticker = "GC=F"
        elif ticker in ['SILVER', 'XAG']:
            yf_ticker = "SI=F"

    # Try loading from historical_data.db
    series = pd.Series()
    try:
        series = historical_db.load_prices(yf_ticker, start_date, end_date)
    except Exception as e:
        print(f"[WARN] Failed to load historical prices from db for {yf_ticker}: {e}")

    expected_days = (end_date - start_date).days
    cache_key = f"hist_checked_{yf_ticker}_{expected_days}"
    has_fetched = _svc_fc.get(cache_key, ttl=86400) # 24 saat TTL
    
    if len(series) < expected_days * 0.5 and not has_fetched:
        try:
            print(f"[HISTORICAL] Downloading {yf_ticker} from Twelve Data...")
            td_series = td.get_time_series(yf_ticker, days=max(expected_days, 30), interval="1day")
            
            _svc_fc.set(cache_key, True)
            
            if td_series:
                dates = [pd.to_datetime(p["date"][:10]) for p in td_series]
                prices_list = [p["close"] for p in td_series]
                close_series = pd.Series(prices_list, index=dates)
                historical_db.write_prices(yf_ticker, close_series)
                series = historical_db.load_prices(yf_ticker, start_date, end_date)
        except Exception as e:
            print(f"[WARN] Failed to fetch Twelve Data history for {yf_ticker}: {e}")

    # Sanity check: reject clearly wrong prices (yfinance ticker mismatch protection)
    if asset_type == 'crypto' and not series.empty:
        series = series[series < 1_000_000]

    price_dict = {}
    if not series.empty:
        for ts, val in series.items():
            price_dict[ts.date()] = float(val)
    return price_dict

def invalidate_twrr_cache():
    _twrr_cache.clear()
    _twrr_cache_time.clear()

def invalidate_portfolio_cache(user_id: Optional[int] = None):
    if user_id is None:
        # Şu an hiçbir çağıran taraf user_id'siz çağırmıyor (bkz. routers/positions.py) —
        # Redis'te tüm kullanıcıların anahtarlarını taramak için ayrı bir mekanizma
        # gerekecek, ihtiyaç olursa eklenir.
        return
    _svc_fc.invalidate(f"portfolio_cache:{user_id}")

def calculate_twrr_and_metrics(user_id: int, days: int = 90, currency: str = 'TRY') -> Dict:
    cache_key = f"{user_id}_{days}_{currency}"
    now = datetime.now()
    if cache_key in _twrr_cache:
        elapsed = (now - _twrr_cache_time[cache_key]).total_seconds()
        if elapsed < TWRR_CACHE_TTL:
            return _twrr_cache[cache_key]

    today = now.date()
    start_date = today - timedelta(days=days)
    date_list = [start_date + timedelta(days=i) for i in range(days + 1)]

    # 1. Get transactions
    txns = get_transactions(user_id)
    if not txns:
        # Reconstruct transactions from current positions
        positions = get_positions(user_id)
        for pos in positions:
            buy_dt = pos['buy_date']
            if isinstance(buy_dt, str):
                buy_dt = datetime.strptime(buy_dt, "%Y-%m-%d").date()
            
            asset_type = pos.get('asset_type')
            if not asset_type:
                if pos['asset_class'] == 'TEFAS Fonu': asset_type = 'fund'
                elif pos['asset_class'] == 'BIST Hissesi': asset_type = 'stock_tr'
                elif pos['asset_class'] == 'ABD Hisse/ETF': asset_type = 'stock_us'
                elif pos['asset_class'] == 'Kripto': asset_type = 'crypto'
                elif pos['asset_class'] == 'Nakit': asset_type = 'cash'
                elif pos['asset_class'] == 'Emtia': asset_type = 'commodity'

            txns.append({
                "ticker": pos['ticker'],
                "asset_class": pos['asset_class'],
                "asset_type": asset_type,
                "transaction_type": "BUY",
                "quantity": pos['quantity'],
                "price": pos['buy_price'],
                "currency": pos['buy_currency'],
                "transaction_date": buy_dt,
                "interest_rate": pos.get('interest_rate'),
                "maturity_date": pos.get('maturity_date'),
                "commodity_type": pos.get('commodity_type'),
                "unit": pos.get('unit')
            })
    else:
        # standardise dates and fields
        for t in txns:
            if isinstance(t['transaction_date'], str):
                t['transaction_date'] = datetime.strptime(t['transaction_date'], "%Y-%m-%d").date()
            # backfill asset_type if missing
            if not t.get('asset_type'):
                ac = t['asset_class']
                if ac == 'TEFAS Fonu': t['asset_type'] = 'fund'
                elif ac == 'BIST Hissesi': t['asset_type'] = 'stock_tr'
                elif ac == 'ABD Hisse/ETF': t['asset_type'] = 'stock_us'
                elif ac == 'Kripto': t['asset_type'] = 'crypto'
                elif ac == 'Nakit': t['asset_type'] = 'cash'
                elif ac == 'Emtia': t['asset_type'] = 'commodity'

    # Get daily exchange rates
    usd_try_history = get_ticker_historical_prices("USDTRY=X", "exchange_rate", start_date, today)
    eur_try_history = get_ticker_historical_prices("EURTRY=X", "exchange_rate", start_date, today)
    gbp_try_history = get_ticker_historical_prices("GBPTRY=X", "exchange_rate", start_date, today)

    def get_rate_on_day(rate_history, d, fallback=35.0):
        curr_d = d
        for _ in range(30):
            if curr_d in rate_history:
                return rate_history[curr_d]
            curr_d -= timedelta(days=1)
        return fallback

    # Download daily history for each unique ticker
    unique_tickers = list(set((t['ticker'], t.get('asset_type') or 'fund', t['asset_class']) for t in txns))
    ticker_histories = {}
    for ticker, asset_type, asset_class in unique_tickers:
        if asset_type == 'cash':
            continue
        ticker_histories[ticker] = get_ticker_historical_prices(ticker, asset_type, start_date, today)

    # Reconstruct daily portfolio value
    daily_portfolio = []
    
    # Helper to get asset price on a specific day
    def get_asset_price_on_day(ticker, asset_type, d, txn_meta):
        if asset_type == 'cash':
            # grow cash price with interest rate
            buy_dt = txn_meta.get('transaction_date')
            interest_rate = txn_meta.get('interest_rate')
            buy_price = txn_meta.get('price', 1.0)
            interest_factor = 1.0
            if interest_rate and interest_rate > 0:
                days_held = (d - buy_dt).days
                if days_held < 0:
                    days_held = 0
                interest_factor = 1.0 + (interest_rate / 100.0) * (days_held / 365.0)
            return buy_price * interest_factor
        
        elif asset_type == 'commodity' and txn_meta.get('commodity_type') == 'physical':
            # GOLD/SILVER futures
            hist = ticker_histories.get(ticker, {})
            futures_price = get_rate_on_day(hist, d, 2300.0 if ticker in ["GOLD", "XAU"] else 28.0)
            
            unit = txn_meta.get('unit')
            if unit == 'gram':
                price_usd = futures_price / 31.1034768
            else:
                price_usd = futures_price
                
            buy_currency = txn_meta.get('currency', 'TRY')
            if buy_currency == 'TRY':
                return price_usd * get_rate_on_day(usd_try_history, d, 35.0)
            elif buy_currency == 'USD':
                return price_usd
            elif buy_currency == 'EUR':
                return price_usd * (get_rate_on_day(usd_try_history, d, 35.0) / get_rate_on_day(eur_try_history, d, 38.0))
            return price_usd
            
        else:
            hist = ticker_histories.get(ticker, {})
            fallback_val = txn_meta.get('price', 1.0)
            # For cryptos with TRY buy_currency: fallback price must be in USD
            # because the calling code multiplies by usd_rate for asset_class=='Kripto'
            if asset_type == 'crypto' and txn_meta.get('currency', 'USD') == 'TRY':
                rate_d = get_rate_on_day(usd_try_history, d, 35.0)
                if rate_d > 0:
                    fallback_val = fallback_val / rate_d
            return get_rate_on_day(hist, d, fallback_val)

    # SELL işlemlerinde yatırılan sermayeyi (invested capital) SATIŞ FİYATIYLA değil, o ana
    # kadarki AĞIRLIKLI ORTALAMA ALIM MALİYETİYLE düşmek için ticker başına kronolojik bir
    # maliyet takibi yapıyoruz. Aksi halde karlı bir satış invested_capital'ı yapay şekilde
    # (hatta eksiye) düşürüp getiri oranını sonsuza (%inf) sıçratıyordu — örn. 1000 TL'lik bir
    # pozisyonun yarısı 1000 TL'ye (kâr ederek) satıldığında invested_capital 0'a düşüyordu.
    sell_cost_try: dict = {}  # transaction id -> bu satışla düşülecek TL cinsinden maliyet bazı
    _running_qty: dict = {}
    _running_cost_try: dict = {}
    for t in sorted(txns, key=lambda x: (x['transaction_date'], x.get('id') or 0)):
        ticker_ = t['ticker']
        buy_currency_ = t.get('currency', 'TRY')
        qty_ = t['quantity']
        price_ = t['price']
        t_date_ = t['transaction_date']

        if buy_currency_ == "TRY":
            native_cost_try = qty_ * price_
        elif buy_currency_ == "USD":
            native_cost_try = qty_ * price_ * get_rate_on_day(usd_try_history, t_date_, 35.0)
        elif buy_currency_ == "EUR":
            native_cost_try = qty_ * price_ * get_rate_on_day(eur_try_history, t_date_, 38.0)
        elif buy_currency_ == "GBP":
            native_cost_try = qty_ * price_ * get_rate_on_day(gbp_try_history, t_date_, 43.0)
        else:
            native_cost_try = qty_ * price_

        prev_qty = _running_qty.get(ticker_, 0.0)
        prev_cost = _running_cost_try.get(ticker_, 0.0)

        if t['transaction_type'] == "BUY":
            _running_qty[ticker_] = prev_qty + qty_
            _running_cost_try[ticker_] = prev_cost + native_cost_try
        elif t['transaction_type'] == "SELL":
            avg_cost_per_unit = (prev_cost / prev_qty) if prev_qty > 0 else 0.0
            removed = min(qty_, prev_qty) * avg_cost_per_unit
            sell_cost_try[t.get('id')] = removed
            _running_qty[ticker_] = max(0.0, prev_qty - qty_)
            _running_cost_try[ticker_] = max(0.0, prev_cost - removed)

    for d in date_list:
        # Transactions on or before day d
        active_txns = [t for t in txns if t['transaction_date'] <= d]
        
        total_value_d = 0.0
        total_invested_d = 0.0
        
        # Unique tickers held on or before day d
        tickers_held = list(set(t['ticker'] for t in active_txns))
        
        for ticker in tickers_held:
            ticker_txns = [t for t in active_txns if t['ticker'] == ticker]
            qty_d = sum(t['quantity'] if t['transaction_type'] == 'BUY' else -t['quantity'] for t in ticker_txns)
            
            if qty_d <= 0:
                continue
                
            # Use metadata from the first transaction
            txn_meta = ticker_txns[0]
            asset_type = txn_meta.get('asset_type') or 'fund'
            asset_class = txn_meta.get('asset_class')
            buy_currency = txn_meta.get('currency', 'TRY')
            
            # Get asset price on day d
            price_d = get_asset_price_on_day(ticker, asset_type, d, txn_meta)
            
            # Convert value to TRY
            usd_rate_d = get_rate_on_day(usd_try_history, d, 35.0)
            eur_rate_d = get_rate_on_day(eur_try_history, d, 38.0)
            gbp_rate_d = get_rate_on_day(gbp_try_history, d, 43.0)

            if buy_currency == "TRY":
                if asset_class == "Kripto":
                    val_tly = qty_d * price_d * usd_rate_d
                else:
                    val_tly = qty_d * price_d
            elif buy_currency == "USD":
                val_tly = qty_d * price_d * usd_rate_d
            elif buy_currency == "EUR":
                val_tly = qty_d * price_d * eur_rate_d
            elif buy_currency == "GBP":
                val_tly = qty_d * price_d * gbp_rate_d
            else:
                val_tly = qty_d * price_d
                
            total_value_d += val_tly

        # Cumulative invested TRY
        for t in active_txns:
            buy_currency = t.get('currency', 'TRY')
            qty = t['quantity']
            price = t['price']
            t_date = t['transaction_date']
            usd_rate_t = get_rate_on_day(usd_try_history, t_date, 35.0)
            eur_rate_t = get_rate_on_day(eur_try_history, t_date, 38.0)
            gbp_rate_t = get_rate_on_day(gbp_try_history, t_date, 43.0)

            if buy_currency == "TRY":
                cost = qty * price
            elif buy_currency == "USD":
                cost = qty * price * usd_rate_t
            elif buy_currency == "EUR":
                cost = qty * price * eur_rate_t
            elif buy_currency == "GBP":
                cost = qty * price * gbp_rate_t
            else:
                cost = qty * price
                
            if t['transaction_type'] == "BUY":
                total_invested_d += cost
            elif t['transaction_type'] == "SELL":
                # Satış fiyatı DEĞİL, yukarıda önceden hesaplanmış ağırlıklı ortalama maliyet
                # bazı düşülüyor — bkz. sell_cost_try'nin üstündeki not.
                total_invested_d -= sell_cost_try.get(t.get('id'), cost)

        daily_portfolio.append({
            "date": d,
            "value": total_value_d,
            "invested": total_invested_d
        })

    # Convert daily portfolio values to target currency (TRY is the base)
    if currency != 'TRY':
        for entry in daily_portfolio:
            d = entry["date"]
            if currency == 'USD':
                rate = get_rate_on_day(usd_try_history, d, 35.0)
            elif currency == 'EUR':
                rate = get_rate_on_day(eur_try_history, d, 38.0)
            elif currency == 'GBP':
                rate = get_rate_on_day(gbp_try_history, d, 43.0)
            else:
                rate = 1.0
            if rate > 0:
                entry["value"] = entry["value"] / rate
                entry["invested"] = entry["invested"] / rate

    # Calculate TWRR returns
    daily_returns = []
    for i in range(1, len(daily_portfolio)):
        v_prev = daily_portfolio[i-1]["value"]
        v_curr = daily_portfolio[i]["value"]
        i_prev = daily_portfolio[i-1]["invested"]
        i_curr = daily_portfolio[i]["invested"]
        
        cf = i_curr - i_prev
        
        if v_prev > 0:
            r = (v_curr - cf - v_prev) / v_prev
        else:
            r = 0.0
        daily_returns.append(r)

    # Compute compounded TWRR series
    twrr_series = []
    compounded = 1.0
    for r in daily_returns:
        compounded *= (1.0 + r)
        twrr_series.append((compounded - 1.0) * 100.0)

    if not twrr_series:
        twrr_series = [0.0]

    current_twrr = twrr_series[-1]

    # Reconstruct indexes
    bist100_history = get_ticker_historical_prices("XU100.IS", "index", start_date, today)
    sp500_history = get_ticker_historical_prices("^GSPC", "index", start_date, today)
    btc_history = get_ticker_historical_prices("BTC-USD", "crypto", start_date, today)

    def calculate_benchmark_return_series(history):
        if not history:
            return [0.0] * len(date_list)
        sorted_dates = sorted(history.keys())
        if not sorted_dates:
            return [0.0] * len(date_list)
        first_date = sorted_dates[0]
        base_price = history[first_date]
        if base_price == 0:
            base_price = 1.0
            
        bench_returns = []
        for d in date_list:
            p_d = get_rate_on_day(history, d, base_price)
            bench_returns.append(((p_d / base_price) - 1.0) * 100.0)
        return bench_returns

    bist_returns = calculate_benchmark_return_series(bist100_history)
    sp_returns = calculate_benchmark_return_series(sp500_history)
    btc_returns = calculate_benchmark_return_series(btc_history)

    # Volatility
    if len(daily_returns) > 1:
        mean_ret = sum(daily_returns) / len(daily_returns)
        var_ret = sum((x - mean_ret) ** 2 for x in daily_returns) / (len(daily_returns) - 1)
        daily_vol = math.sqrt(var_ret)
        volatility = daily_vol * math.sqrt(252) * 100.0
    else:
        volatility = 0.0

    # Max Drawdown
    max_dd = 0.0
    if daily_portfolio:
        peak = daily_portfolio[0]["value"]
        for p in daily_portfolio:
            val = p["value"]
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        max_dd_val = max_dd * 100.0
    else:
        max_dd_val = 0.0

    # Format output
    chart_data = []
    for idx, d in enumerate(date_list):
        p_ret = twrr_series[idx-1] if idx > 0 and (idx-1) < len(twrr_series) else 0.0
        chart_data.append({
            "date": d.isoformat(),
            "portfolio": round(p_ret, 2),
            "bist100": round(bist_returns[idx] if idx < len(bist_returns) else 0.0, 2),
            "sp500": round(sp_returns[idx] if idx < len(sp_returns) else 0.0, 2),
            "btc": round(btc_returns[idx] if idx < len(btc_returns) else 0.0, 2),
            "value": round(daily_portfolio[idx]["value"], 2),
            "invested": round(daily_portfolio[idx]["invested"], 2)
        })

    result = {
        "twrr": round(current_twrr, 2),
        "volatility": round(volatility, 2),
        "max_drawdown": round(max_dd_val, 2),
        "history": chart_data
    }
    _twrr_cache[cache_key] = result
    _twrr_cache_time[cache_key] = datetime.now()
    return result
