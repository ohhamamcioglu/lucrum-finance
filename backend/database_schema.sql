-- LUCRUM Finance Portfolio Platform - SQLite Schema

-- Kullanıcılar
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT, -- Hashed password for authentication
    currency TEXT DEFAULT 'TRY',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Varlık Sınıfları (Enum-like)
-- TEFAS Fonu, BIST Hissesi, ABD Hisse/ETF, Kripto

-- Pozisyonlar (Aktif Pozisyonlar)
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    asset_class TEXT NOT NULL,  -- TEFAS Fonu, BIST Hissesi, ABD Hisse/ETF, Kripto
    quantity REAL NOT NULL,
    buy_price REAL NOT NULL,
    buy_date DATE NOT NULL,
    buy_currency TEXT NOT NULL,  -- TRY, USD
    cost_basis_tly REAL,  -- Alınış maliyeti TL cinsinden (hesaplanan)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, ticker)
);

-- İşlem Geçmişi (Tüm Al/Sat İşlemleri)
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    position_id INTEGER,  -- Null olabilir (silinmiş pozisyon)
    ticker TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    transaction_type TEXT NOT NULL,  -- BUY, SELL, DIVIDEND, SPLIT
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    transaction_date DATE NOT NULL,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (position_id) REFERENCES positions(id)
);

-- Günlük Fiyat Geçmişi (Sıkça Sorgulanan - Cache)
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    price_date DATE NOT NULL,
    price_usd REAL,  -- USD cinsinden
    price_try REAL,  -- TRY cinsinden
    usd_try_rate REAL,  -- O gün kuru
    source TEXT,  -- yfinance, pytefas, coinmarketcap
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, price_date)
);

-- USD/TRY Kurları Geçmişi
CREATE TABLE IF NOT EXISTS exchange_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rate_date DATE UNIQUE NOT NULL,
    usd_try_rate REAL NOT NULL,
    source TEXT,  -- yfinance, tcmb
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio Özeti (Daily Snapshot - Raporlama için)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    total_invested_try REAL,
    total_value_try REAL,
    total_return_try REAL,
    total_return_pct REAL,
    snapshot_data JSON,  -- Full JSON snapshot (detaylı veriler)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, snapshot_date)
);

-- Varlık Sınıfı Özetleri (Daily)
CREATE TABLE IF NOT EXISTS asset_class_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    asset_class TEXT NOT NULL,
    total_invested_try REAL,
    total_value_try REAL,
    total_return_try REAL,
    total_return_pct REAL,
    position_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, snapshot_date, asset_class)
);

-- Tarihsel Performance (Günlük/Aylık Trend)
CREATE TABLE IF NOT EXISTS performance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    period_date DATE NOT NULL,  -- Gün, Ay başı
    period_type TEXT NOT NULL,  -- DAILY, MONTHLY, YEARLY
    value_try REAL,
    return_pct REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, period_date, period_type)
);

-- İndeksler
CREATE INDEX IF NOT EXISTS idx_positions_user ON positions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_ticker ON transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_date ON portfolio_snapshots(user_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_asset_class_summaries_date ON asset_class_summaries(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_performance_history_user_date ON performance_history(user_id, period_date);
CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date ON price_history(ticker, price_date);
