# -*- coding: utf-8 -*-
"""
LUCRUM Finance — Ticker Evreni
BIST_100: Borsa İstanbul 100 endeksi bileşenleri (.IS uzantılı)
SP500   : S&P 500 bileşenleri (statik top-100 + Wikipedia fetch)

Kaynak: Borsa İstanbul KAP açıklamaları (Haziran 2025)
        Wikipedia — List of S&P 500 companies (Haziran 2025)
"""

import pandas as pd

# ── BIST 100 ──────────────────────────────────────────────────────────────────
# Borsa İstanbul BIST 100 endeksi bileşenleri (Haziran 2025 itibarıyla ~100 hisse)
BIST_100 = [
    "ACSEL.IS", "ADEL.IS",  "AEFES.IS", "AGESA.IS", "AHGAZ.IS",
    "AKBNK.IS", "AKGRT.IS", "AKSA.IS",  "AKSEN.IS", "ALARK.IS",
    "ALBRK.IS", "ALFAS.IS", "ALKIM.IS", "ANACM.IS", "ARCLK.IS",
    "ARDYZ.IS", "ASELS.IS", "ASUZU.IS", "AVOD.IS",  "AYDEM.IS",
    "BERA.IS",  "BIMAS.IS", "BRISA.IS", "BRYAT.IS", "BTCIM.IS",
    "CCOLA.IS", "CIMSA.IS", "CWENE.IS", "DOAS.IS",  "DOHOL.IS",
    "ECILC.IS", "EGEEN.IS", "EKGYO.IS", "ENKAI.IS", "EREGL.IS",
    "EUPWR.IS", "FROTO.IS", "GARAN.IS", "GESAN.IS", "GUBRF.IS",
    "GWIND.IS", "HALKB.IS", "HEKTS.IS", "HLGYO.IS", "INDES.IS",
    "IPEKE.IS", "ISCTR.IS", "ISGYO.IS", "ISMEN.IS", "KAPLM.IS",
    "KARTN.IS", "KCHOL.IS", "KERVT.IS", "KORDS.IS", "KOZAA.IS",
    "KOZAL.IS", "KRDMD.IS", "LOGO.IS",  "MAVI.IS",  "MGROS.IS",
    "MIATK.IS", "MPARK.IS", "NTHOL.IS", "ODAS.IS",  "OTKAR.IS",
    "OYAKC.IS", "PAPIL.IS", "PEHOL.IS", "PETKM.IS", "PGSUS.IS",
    "PRARK.IS", "QUAGR.IS", "RODRG.IS", "SAHOL.IS", "SASA.IS",
    "SISE.IS",  "SKBNK.IS", "SNPAM.IS", "SOKM.IS",  "TAVHL.IS",
    "TCELL.IS", "THYAO.IS", "TKFEN.IS", "TOASO.IS", "TRGYO.IS",
    "TTKOM.IS", "TTRAK.IS", "TUPRS.IS", "TURSG.IS", "ULKER.IS",
    "VAKBN.IS", "VESBE.IS", "VESTEL.IS","YATAS.IS", "YKBNK.IS",
    "ZOREN.IS", "GLRYH.IS", "FENER.IS", "NTHOL.IS", "GESAN.IS",
]
# Tekrarları kaldır, sırayla koru
_seen: set[str] = set()
BIST_100 = [x for x in BIST_100 if not (x in _seen or _seen.add(x))]  # type: ignore


# ── BIST 100 Metadata ─────────────────────────────────────────────────────────
BIST_100_METADATA = {
    "ACSEL": {"name": "Acıpayam Selüloz", "sector": "Materials"},
    "ADEL": {"name": "Adel Kalemcilik", "sector": "Consumer Discretionary"},
    "AEFES": {"name": "Anadolu Efes", "sector": "Consumer Staples"},
    "AGESA": {"name": "Agesa Hayat ve Emeklilik", "sector": "Financials"},
    "AHGAZ": {"name": "Ahlatcı Doğal Gaz", "sector": "Utilities"},
    "AKBNK": {"name": "Akbank", "sector": "Financials"},
    "AKGRT": {"name": "Aksigorta", "sector": "Financials"},
    "AKSA": {"name": "Aksa Akrilik", "sector": "Materials"},
    "AKSEN": {"name": "Aksa Enerji", "sector": "Utilities"},
    "ALARK": {"name": "Alarko Holding", "sector": "Industrials"},
    "ALBRK": {"name": "Albaraka Türk", "sector": "Financials"},
    "ALFAS": {"name": "Alfa Solar Enerji", "sector": "Utilities"},
    "ALKIM": {"name": "Alkim Kimya", "sector": "Materials"},
    "ARCLK": {"name": "Arçelik", "sector": "Consumer Discretionary"},
    "ARDYZ": {"name": "Ard Grup Bilişim", "sector": "Technology"},
    "ASELS": {"name": "Aselsan", "sector": "Industrials"},
    "ASUZU": {"name": "Anadolu Isuzu", "sector": "Industrials"},
    "AVOD": {"name": "Avod Gıda", "sector": "Consumer Staples"},
    "AYDEM": {"name": "Aydem Enerji", "sector": "Utilities"},
    "BERA": {"name": "Bera Holding", "sector": "Industrials"},
    "BIMAS": {"name": "Bim Birleşik Mağazalar", "sector": "Consumer Staples"},
    "BRISA": {"name": "Brisa", "sector": "Consumer Discretionary"},
    "BRYAT": {"name": "Borusan Yatırım Pazarlama", "sector": "Industrials"},
    "BTCIM": {"name": "Batıçim Batı Anadolu Çimento", "sector": "Materials"},
    "CCOLA": {"name": "Coca-Cola İçecek", "sector": "Consumer Staples"},
    "CIMSA": {"name": "Çimsa", "sector": "Materials"},
    "CWENE": {"name": "CW Enerji", "sector": "Utilities"},
    "DOAS": {"name": "Doğuş Otomotiv", "sector": "Consumer Discretionary"},
    "DOHOL": {"name": "Doğan Holding", "sector": "Industrials"},
    "ECILC": {"name": "Eczacıbaşı İlaç", "sector": "Health Care"},
    "EGEEN": {"name": "Ege Endüstri", "sector": "Industrials"},
    "EKGYO": {"name": "Emlak Konut GYO", "sector": "Real Estate"},
    "ENKAI": {"name": "Enka İnşaat", "sector": "Industrials"},
    "EREGL": {"name": "Ereğli Demir Çelik", "sector": "Materials"},
    "EUPWR": {"name": "Europower Enerji", "sector": "Utilities"},
    "FROTO": {"name": "Ford Otosan", "sector": "Consumer Discretionary"},
    "GARAN": {"name": "Garanti Bankası", "sector": "Financials"},
    "GESAN": {"name": "Girişim Elektrik Sanayi", "sector": "Utilities"},
    "GUBRF": {"name": "Gübre Fabrikaları", "sector": "Materials"},
    "GWIND": {"name": "Galata Wind Enerji", "sector": "Utilities"},
    "HALKB": {"name": "Halk Bankası", "sector": "Financials"},
    "HEKTS": {"name": "Hektaş", "sector": "Materials"},
    "HLGYO": {"name": "Halk GYO", "sector": "Real Estate"},
    "INDES": {"name": "İndeks Bilgisayar", "sector": "Technology"},
    "IPEKE": {"name": "İpek Doğal Enerji", "sector": "Energy"},
    "ISCTR": {"name": "İş Bankası", "sector": "Financials"},
    "ISGYO": {"name": "İş GYO", "sector": "Real Estate"},
    "ISMEN": {"name": "İş Yatırım Menkul Değerler", "sector": "Financials"},
    "KCHOL": {"name": "Koç Holding", "sector": "Industrials"},
    "KOZAA": {"name": "Koza Anadolu Metal", "sector": "Materials"},
    "KOZAL": {"name": "Koza Altın", "sector": "Materials"},
    "KRDMD": {"name": "Kardemir (D)", "sector": "Materials"},
    "LOGO": {"name": "Logo Yazılım", "sector": "Technology"},
    "MAVI": {"name": "Mavi Giyim", "sector": "Consumer Discretionary"},
    "MGROS": {"name": "Migros", "sector": "Consumer Staples"},
    "MIATK": {"name": "Mia Teknoloji", "sector": "Technology"},
    "MPARK": {"name": "MLP Sağlık Hizmetleri", "sector": "Health Care"},
    "NTHOL": {"name": "Net Holding", "sector": "Consumer Discretionary"},
    "ODAS": {"name": "Odaş Elektrik", "sector": "Utilities"},
    "OTKAR": {"name": "Otokar", "sector": "Industrials"},
    "OYAKC": {"name": "Oyak Çimento", "sector": "Materials"},
    "PGSUS": {"name": "Pegasus Hava Taşımacılığı", "sector": "Industrials"},
    "SAHOL": {"name": "Sabancı Holding", "sector": "Industrials"},
    "SASA": {"name": "Sasa Polyester", "sector": "Materials"},
    "SISE": {"name": "Şişecam", "sector": "Materials"},
    "SKBNK": {"name": "Şekerbank", "sector": "Financials"},
    "SOKM": {"name": "Şok Marketler", "sector": "Consumer Staples"},
    "TAVHL": {"name": "TAV Havalimanları", "sector": "Industrials"},
    "TCELL": {"name": "Turkcell", "sector": "Communication Services"},
    "THYAO": {"name": "Türk Hava Yolları", "sector": "Industrials"},
    "TKFEN": {"name": "Tekfen Holding", "sector": "Industrials"},
    "TOASO": {"name": "Tofaş Türk Otomobil Fabrikası", "sector": "Consumer Discretionary"},
    "TRGYO": {"name": "Torunlar GYO", "sector": "Real Estate"},
    "TTKOM": {"name": "Türk Telekom", "sector": "Communication Services"},
    "TTRAK": {"name": "Türk Traktör", "sector": "Industrials"},
    "TUPRS": {"name": "Tüpraş", "sector": "Energy"},
    "TURSG": {"name": "Türkiye Sigorta", "sector": "Financials"},
    "ULKER": {"name": "Ülker Bisküvi", "sector": "Consumer Staples"},
    "VAKBN": {"name": "Vakıfbank", "sector": "Financials"},
    "VESBE": {"name": "Vestel Beyaz Eşya", "sector": "Consumer Discretionary"},
    "VESTEL": {"name": "Vestel Elektronik", "sector": "Consumer Discretionary"},
    "YKBNK": {"name": "Yapı Kredi Bankası", "sector": "Financials"},
    "ZOREN": {"name": "Zorlu Enerji", "sector": "Utilities"},
}

# ── S&P 500 ────────────────────────────────────────────────────────────────────
# Kaynak: Wikipedia "List of S&P 500 companies" (otomatik çekilir, hata olursa fallback)
_SP500_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "LLY",
    "AVGO", "JPM", "UNH", "TSLA", "XOM", "V",    "MA",   "PG",   "COST",
    "HD",   "JNJ", "ABBV", "MRK",  "BAC", "NFLX", "CVX",  "AMD",  "KO",
    "PEP",  "WMT", "CRM",  "MCD",  "ACN", "ABT",  "LIN",  "TMO",  "CSCO",
    "WFC",  "NOW", "GS",   "ISRG", "AXP", "IBM",  "PM",   "RTX",  "CAT",
    "SPGI", "BLK", "INTU", "TXN",  "NEE", "DHR",  "LOW",  "AMGN", "SYK",
    "T",    "UNP", "VRTX", "ELV",  "MDT", "DE",   "BMY",  "ADP",  "GILD",
    "MS",   "C",   "ADI",  "MMC",  "PLD", "CB",   "SCHW", "BKNG", "SO",
    "ZTS",  "AMAT","PNC",  "USB",  "TJX", "ETN",  "GE",   "CME",  "CI",
    "MO",   "MDLZ","ITW",  "EOG",  "MCO", "MMM",  "AON",  "HCA",  "DUK",
    "SHW",  "LRCX","APD",  "EMR",  "ICE", "FIS",  "INTC", "NOC",  "GD",
    "ORLY", "MAR", "PSA",  "PH",   "BSX", "REGN", "KLAC", "HUM",  "NSC",
    "ECL",  "TGT", "WM",   "FCX",  "ROP", "CL",   "FTNT", "MET",  "D",
    "CTVA", "EW",  "MCHP", "PCAR", "MSI", "F",    "GM",   "NEM",  "AIG",
    "OKE",  "CARR","PWR",  "CPRT", "SRE", "AMP",  "CTAS", "DVN",  "MRNA",
    "HES",  "NUE", "TRGP", "CCI",  "O",   "GIS",  "DOW",  "DXCM", "BIIB",
    "KEYS", "IDXX","MPWR", "FANG", "MTD", "FAST", "CTSH", "EXC",  "XEL",
    "HIG",  "VRSK","WAT",  "SBAC", "RMD", "BALL", "IQV",  "ALGN", "FTV",
    "PPG",  "LDOS", "PAYC","POOL", "DDOG","MKC",  "FE",   "LH",   "STZ",
    "TSCO", "TDG", "TROW", "TT",   "VLO", "FSLR", "DHI",  "PHM",  "NVR",
    "LEN",  "TOL",  "BLDR","URI",  "SWK", "PNR",  "RHI",  "KIM",  "SPG",
]


def fetch_sp500_metadata_from_wiki() -> dict:
    """
    Wikipedia'dan güncel S&P 500 listesini ve şirket isimlerini/sektörlerini çeker.
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        r = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (compatible; lucrum-finance-mcp)"},
            timeout=15,
        )
        soup = BeautifulSoup(r.content, "html.parser")
        table = soup.find("table", {"id": "constituents"})
        if not table:
            return {}
        companies = {}
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if cells:
                sym = cells[0].get_text(strip=True).replace(".", "-")
                name = cells[1].get_text(strip=True)
                sector = cells[3].get_text(strip=True)
                if sym:
                    companies[sym] = {"name": name, "sector": sector}
        return companies
    except Exception:
        return {}


def get_sp500_metadata() -> dict:
    """S&P 500 metadata — önce Wikipedia BS4 dene, hata olursa statik fallback."""
    live = fetch_sp500_metadata_from_wiki()
    if len(live) >= 400:
        return live
    
    # Fallback to static top S&P 500
    fallback = {}
    for ticker in _SP500_FALLBACK:
        # Simple name fallback
        name = f"{ticker} Corporation"
        sector = "Technology"
        if ticker == "AAPL": name, sector = "Apple Inc.", "Technology"
        elif ticker == "MSFT": name, sector = "Microsoft Corp.", "Technology"
        elif ticker == "NVDA": name, sector = "NVIDIA Corp.", "Technology"
        elif ticker == "AMZN": name, sector = "Amazon.com Inc.", "Consumer Discretionary"
        elif ticker == "META": name, sector = "Meta Platforms Inc.", "Communication Services"
        elif ticker == "GOOGL": name, sector = "Alphabet Inc. (Class A)", "Communication Services"
        elif ticker == "GOOG": name, sector = "Alphabet Inc. (Class C)", "Communication Services"
        elif ticker == "TSLA": name, sector = "Tesla Inc.", "Consumer Discretionary"
        elif ticker == "BRK-B": name, sector = "Berkshire Hathaway Inc. (Class B)", "Financials"
        elif ticker == "LLY": name, sector = "Eli Lilly & Co.", "Health Care"
        elif ticker == "AVGO": name, sector = "Broadcom Inc.", "Technology"
        elif ticker == "JPM": name, sector = "JPMorgan Chase & Co.", "Financials"
        elif ticker == "UNH": name, sector = "UnitedHealth Group Inc.", "Health Care"
        elif ticker == "XOM": name, sector = "Exxon Mobil Corp.", "Energy"
        elif ticker == "V": name, sector = "Visa Inc.", "Financials"
        elif ticker == "MA": name, sector = "Mastercard Inc.", "Financials"
        elif ticker == "PG": name, sector = "Procter & Gamble Co.", "Consumer Staples"
        elif ticker == "COST": name, sector = "Costco Wholesale Corp.", "Consumer Staples"
        elif ticker == "HD": name, sector = "Home Depot Inc.", "Consumer Discretionary"
        fallback[ticker] = {"name": name, "sector": sector}
    return fallback


SP500_METADATA = get_sp500_metadata()
SP500 = list(SP500_METADATA.keys()) if SP500_METADATA else _SP500_FALLBACK

if __name__ == "__main__":
    print(f"BIST_100: {len(BIST_100)} ticker")
    print(f"SP500   : {len(SP500)} ticker")
    print("\nBIST_100 örnek:", BIST_100[:5])
    print("SP500 örnek   :", SP500[:5])
