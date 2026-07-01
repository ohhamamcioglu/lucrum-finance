# Lucrum Finance — Proje Bağlamı ve Kararlar

Son güncelleme: 2026-06-30

---

## Proje Nedir?

**Lucrum Finance** — kişisel portföy takip platformu. Hedef: "Yerel Bloomberg Terminali" gibi çalışan, tüm veriyi kendi SQLite DB'sinde tutan, hızlı ve doğru bir sistem.

**Stack:**
- Backend: FastAPI (Python) — `backend/app.py`
- Frontend: React + TypeScript — `frontend/src/`
- Veri kaynağı: **Twelve Data API** (birincil), yfinance (BIST/Kripto fallback), pytefas (TEFAS)
- DB: SQLite — `portfolio.db`, `cache.db`, `historical_data.db`, **`twelve_data.db`** (yeni)

---

## Twelve Data API

**Key:** `.env` dosyasında `TWELVE_DATA_API_KEY` olarak tutulur, ASLA hardcode edilmez veya bu dosyaya yazılmaz.

**Plan:** Grow/Level A
- 55 istek/dakika
- Çalışan endpoint'ler: `quote`, `time_series`, `exchange_rate`, `statistics`, `earnings`, `balance_sheet`, `key_executives`, `rsi`, `macd`, `bbands`, `ema`, `beta`, `profile`, `stocks`, `exchanges`
- **Çalışmayan:** `/news` (404 — plan dışı)

---

## Yapılan Değişiklikler

### 1. `backend/twelve_data.py` — KOMPLE YENİDEN YAZILDI

Merkezi veri katmanı. Strateji: **DB önce, API gerekirse.**

**SQLite tabloları (`twelve_data.db`):**

| Tablo | İçerik | TTL |
|---|---|---|
| `td_instruments` | BIST/US enstrüman listesi | 14 gün |
| `td_quotes` | Anlık fiyat (OHLCV + 52W) | 5 dk |
| `td_exchange_rates` | USD/TRY, EUR/TRY, GBP/TRY | 1 sa |
| `td_time_series` | OHLCV geçmişi | 30 dk |
| `td_statistics` | P/E, Market Cap, ROE, Margins | 7 gün |
| `td_earnings` | EPS actual vs estimate | 30 gün |
| `td_balance_sheet` | Aktifler, borçlar, özkaynak | 30 gün |
| `td_indicators` | RSI, MACD, BB, EMA, Beta | 1 gün |
| `td_profiles` | Şirket profili | 30 gün |
| `td_executives` | Yöneticiler | 30 gün |

**Önemli fonksiyonlar:**
- `batch_quotes(symbols)` → toplu anlık fiyat
- `get_exchange_rate(pair)` → `"USD/TRY"`, `"GBP/TRY"` vb.
- `get_time_series(symbol, days, interval)` → OHLCV geçmişi
- `get_statistics(symbol)` → P/E, market cap, margins, ROE
- `get_earnings(symbol, n)` → EPS geçmişi
- `get_balance_sheet(symbol)` → bilanço
- `get_rsi/macd/bbands/ema(symbol, ...)` → teknik indikatörler
- `get_beta_value(symbol)` → tek sayı beta
- `get_profile(symbol)` → şirket bilgisi
- `get_executives(symbol)` → yöneticiler
- `enrich_symbol(symbol)` → tek sembol için HER şeyi çekip DB'ye kaydet
- `fetch_instruments(exchange)` → `"XIST"` ile tüm BIST sembollerini listele

**Rate limiter:** 55 istek/dk, `deque`-tabanlı token bucket, `threading.Lock` ile thread-safe.

### 2. `backend/app.py` — Güncellendi

- `/api/exchange-rate` → GBP/TRY artık `td.get_exchange_rate("GBP/TRY")` (yfinance kaldırıldı)
- `/api/assets/{ticker}/overview` → US hisseler için P/E, market cap, margins, ROE, EPS dahil (Twelve Data)
- **YENİ** `/api/assets/{ticker}/fundamentals` → statistics + earnings + balance sheet + executives
- **YENİ** `/api/assets/{ticker}/indicators` → RSI(14) + MACD + BB(20)
- **YENİ** `/api/assets/{ticker}/enrich` → tek sembol seed endpoint'i
- Risk skoru → US için `td.get_beta_value()`, BIST için yfinance
- `_fetch_twelve_data_overview` kaldırıldı (artık `td.batch_quotes` + `td.get_profile` kullanılıyor)

### 3. `frontend/src/components/NewsView.tsx` — Bug Fix

**Problem:** Haberler sayfası sürekli loading skeleton gösteriyordu, `/api/news` çağrılmıyordu.  
**Kök neden:** `useCallback` içinde stale closure — `tickers` prop'u güncelleniyordu ama callback eski değeri okuyordu.  
**Çözüm:** `useRef` pattern:
```typescript
const tickersRef = useRef<string[]>(tickers);
tickersRef.current = tickers; // Her render'da güncelle
// fetchAll useCallback içinde tickersRef.current okur (hiç dep yok)
// useEffect tickerKey (join sonucu) değişince fetchAll çağırır
```

### 4. `.env` Dosyası

```
TCMB_EVDS_API_KEY=<.env dosyasında saklanır, buraya gerçek değeri yazma>
TWELVE_DATA_API_KEY=<.env dosyasında saklanır, buraya gerçek değeri yazma>
```

---

## Mevcut Mimari Kararlar

### Haber Kaynakları (Kesinleşti)
- US hisseler → Yahoo RSS (hızlı) + Google News RSS
- BIST → KAP bildirimleri
- TEFAS → pytefas fon adı + Google News RSS
- Twelve Data `/news` → **YOK** (plan dışı, 404 döner)

### Fiyat Kaynakları (Kesinleşti)
- US hisseler/ETF → **Twelve Data** (birincil)
- BIST → yfinance (hâlâ, Twelve Data BIST EOD denemesi yapılmadı)
- TEFAS → pytefas
- Kripto → yfinance
- Döviz kurları → Twelve Data `/exchange_rate`

### ThreadPoolExecutor Timeout Fix
`with ThreadPoolExecutor() as ex:` bloğu, `as_completed` timeout'u geçse bile tüm future'ları bekler.  
**Düzeltme:** context manager kullanma, `.shutdown(wait=False, cancel_futures=True)` çağır.

---

## Yapılacaklar (Öncelik Sırasıyla)

### Kısa Vadeli
- [ ] **BIST fiyatları Twelve Data ile** — EOD verisi `td.get_time_series("THYAO:XIST", ...)` ile denenebilir
- [ ] **Kripto fiyatları Twelve Data ile** — `td.batch_quotes(["BTC/USD", "ETH/USD"])` formatı
- [ ] **Frontend: Fundamentals paneli** — `/api/assets/{ticker}/fundamentals` çağrısı ile P/E, EPS, Revenue, Margins göster
- [ ] **Frontend: Teknik indikatörler** — `/api/assets/{ticker}/indicators` ile RSI/MACD/BB grafikleri
- [ ] **Arka plan scheduler** — portföy holding'leri için günlük `enrich_symbol()` çalıştır
- [ ] **`get_bist_instruments()`** → `fetch_instruments("XIST")` ile tüm BIST sembollerini DB'ye çek (ilk başlatmada)

### Uzun Vadeli (SaaS)
- [ ] **Auth** — Clerk entegrasyonu
- [ ] **DB** — Supabase PostgreSQL + RLS (SQLite → Postgres migration)
- [ ] **Deploy** — Railway (backend) + Vercel (frontend)
- [ ] **Mobil** — React Native Expo

---

## Kritik Kurallar

1. **EODHD API key** — `.env`'de saklanır, hardcode veya bu dosyaya gerçek değerle yazmak yasak
2. **Twelve Data API key** — `.env`'de, hardcode yasak
3. **agy-worker** — KALICI YASAK. Kullanıcı "bir daha hayatta kaldırma" dedi.
4. Tüm kod değişiklikleri doğrudan yapılır, delegate edilmez.

---

## Test Sonuçları (2026-06-30)

```
USD/TRY: 46.65
GBP/TRY: 61.83
AAPL: close=287.60, PE=34.15, MarketCap=4.14T, Beta=0.28
NVDA: close=199.10, 52W high=236.54
RSI, MACD, Earnings → DB'ye yazılıp okunuyor
Syntax check: app.py OK, twelve_data.py OK
```
