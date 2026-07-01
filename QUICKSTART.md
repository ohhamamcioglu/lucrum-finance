# 🚀 LUCRUM Portfolio Platform - Hızlı Başlangıç

## Otomatik Başlat (Önerilen)

### **Seçenek 1: Batch Dosyası (En Kolay)**
Dosya Gezgini'nden çift tıklayın:
```
start.bat
```

### **Seçenek 2: PowerShell Script**
PowerShell açın ve çalıştırın:
```powershell
C:\Users\ohham\lucrum-finance-mcp\start-clean.ps1
```

---

## Manuel Başlat

### Terminal 1: Backend
```bash
cd C:\Users\ohham\lucrum-finance-mcp
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

### Terminal 2: Frontend
```bash
cd C:\Users\ohham\lucrum-finance-mcp\lucrum-analytics
npm run dev
```

### Tarayıcıda Açın
```
http://localhost:3000
```

---

## 🌐 URLs

| Bileşen | URL | Açıklama |
|---------|-----|---------|
| **Dashboard** | http://localhost:3000 | React Frontend |
| **API Docs** | http://localhost:8000/docs | Swagger UI |
| **API Root** | http://localhost:8000 | FastAPI Server |

---

## 📝 İlk Kullanım

### 1. Dashboard'u Açın
- Portföy özetini göreceksiniz
- 40 pozisyon otomatik yüklüdür

### 2. Pozisyonları Görün
- "📈 Pozisyonlar" sekmesine tıklayın
- Tüm hisse/fon/kripto'ları görün

### 3. Yeni Pozisyon Ekleyin
- "➕ Yeni Pozisyon" düğmesine tıklayın
- Form doldurun:
  - **Ticker**: AAPL, BTC, JET (vb)
  - **Varlık Sınıfı**: Seçin
  - **Adet**: Kaç tane aldığınız
  - **Alış Fiyatı**: Aldığınız fiyat
  - **Alış Tarihi**: Tarih seçin
- "Ekle" butonuna tıklayın

### 4. Sil
- Pozisyon satırındaki 🗑️ butonuna tıklayın

---

## 🔧 Teknik Bilgiler

### Teknoloji Stack
- **Backend**: FastAPI + Python 3.13
- **Frontend**: React 18 + TypeScript + Vite
- **Database**: SQLite3
- **API**: REST

### Dosya Yapısı
```
lucrum-finance-mcp/
├── app.py                 # FastAPI main app
├── models.py              # Pydantic models
├── database.py            # SQLite connection
├── crud.py                # Database operations
├── services.py            # Portfolio calculation
├── portfolio.db           # Veritabanı
├── requirements.txt       # Python dependencies
│
├── frontend/              # React Project
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/    # React components
│   │   ├── services/      # API client
│   │   └── styles/        # CSS files
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
└── start.bat              # Otomatik başlat (Windows)
```

---

## 🛠️ Troubleshooting

### Backend başlamıyor
```bash
# Bağlantı noktası kullanımda mı?
netstat -ano | findstr :8000

# Portu kill et (Windows PowerShell Admin)
Get-Process python | Stop-Process -Force
```

### Frontend başlamıyor
```bash
# npm kurulu mu?
npm --version

# npm install tekrar et
cd frontend
npm install
```

### Veritabanı sorunları
```bash
# Yeni veritabanı oluştur
python init_db.py
```

---

## 📖 API Örnekleri

### Portföy Özetini Al
```bash
curl http://localhost:8000/api/portfolio
```

### Pozisyonları Listele
```bash
curl http://localhost:8000/api/positions
```

### Yeni Pozisyon Ekle
```bash
curl -X POST http://localhost:8000/api/positions \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "MSFT",
    "asset_class": "ABD Hisse/ETF",
    "quantity": 5,
    "buy_price": 380,
    "buy_date": "2024-01-15",
    "buy_currency": "USD"
  }'
```

### Pozisyon Sil
```bash
curl -X DELETE http://localhost:8000/api/positions/1
```

---

## 💡 İpuçları

✅ Backend hot-reload: Kod değiştirince otomatik yenilenir
✅ Frontend hot-reload: React dosyaları anında güncellenir
✅ API Docs: http://localhost:8000/docs adresinden Swagger UI'ı kullanın
✅ Portföy verisi: Portfolio API ilk çağrıda fiyatları fetch eder (biraz yavaş olabilir)

---

**Başarılı kullanımlar! 🚀**
