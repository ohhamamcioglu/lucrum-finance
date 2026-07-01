# LUCRUM Finance MCP Server

Kişisel yatırım analizi için Python tabanlı MCP server.
**Veri kaynakları:** yfinance (Yahoo Finance) + SEC EDGAR API (ücretsiz)

## Kurulum

```bash
# 1. Bağımlılıkları yükle
pip install yfinance pandas numpy "mcp[cli]"

# 2. Claude Code'a kaydet (proje dizininden):
# .mcp.json dosyası zaten mevcut — Claude Code otomatik tanır

# 3. Alternatif: global kayıt
claude mcp add lucrum-finance -- python "C:\Users\ohham\lucrum-finance-mcp\server.py"
```

## Araçlar (Tools)

| # | Araç | Açıklama |
|---|------|----------|
| 1 | `get_stock_overview` | Şirket adı, sektör, piyasa değeri, fiyat, 52h aralığı |
| 2 | `get_financials` | Gelir tablosu, bilanço, nakit akış (2-4 yıl) |
| 3 | `get_price_history` | OHLCV + dönemsel % değişim (1A/3A/6A/12A) |
| 4 | `get_sec_filings` | SEC EDGAR 10-K/10-Q linkleri (sadece ABD) |
| 5 | `compare_peers` | Çoklu ticker karşılaştırma (P/E, marj, büyüme) |
| 6 | `get_altman_zscore` | Altman Z-Score + yorum (güvenli/gri/risk) |
| 7 | `get_piotroski_fscore` | Piotroski F-Score 0-9 (9 kriter ayrı ayrı) |
| 8 | `get_valuation` | P/E, P/B, EV/EBITDA, PEG, temettü |
| 9 | `get_momentum` | 1A/3A/6A/12A değişim + benchmark RS |
| 10 | `screen_watchlist` | Tüm metrikleri toplu tara, PEG'e göre sırala |

## Örnek Kullanım

```
# Tek hisse analizi
get_stock_overview("AAPL")
get_altman_zscore("THYAO.IS")
get_piotroski_fscore("NVDA")

# Karşılaştırma
compare_peers(["AAPL", "MSFT", "GOOGL"])

# Watchlist tarama
screen_watchlist(["AAPL", "NVDA", "AVGO", "THYAO.IS", "ASELS.IS", "EREGL.IS"])
```

## BIST Desteği

- Tüm araçlar `.IS` uzantılı BIST tickerlarını destekler
- `get_sec_filings`: BIST hisselerinde "SEC verisi yok" döndürür
- `get_momentum`: BIST için otomatik olarak XU100.IS benchmark kullanır
- Bazı BIST hisselerinde bilanço kalemleri eksik/gecikmeli olabilir

## Notlar

- **Cache:** 5 dakika in-memory cache, rate-limit koruması için 0.3-0.5s sleep
- **Hata yönetimi:** Eksik veri hata vermez, hangi kalemin eksik olduğunu raporlar
- **Z-Score kısmi hesaplama:** Eksik kalem varsa mevcut verilerle hesaplar, uyarır
