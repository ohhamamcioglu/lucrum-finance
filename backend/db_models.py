import os
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, UniqueConstraint, Index, JSON, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.db")
    DATABASE_URL = f"sqlite:///{db_path}"

# Modify postgresql:// to postgresql+psycopg2:// if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite specific config
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# pool_pre_ping: Supabase gibi yönetilen Postgres'ler idle bağlantıları arka planda
# kapatır — bu olmadan SQLAlchemy havuzdan ölü bir bağlantı verip aralıklı,
# nedeni belirsiz hatalara (örn. kayıt sırasında rastgele 400) yol açıyordu.
# pool_recycle: bağlantıları 30 dakikada bir yenileyerek aynı sorunu önceden önler.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ----------------- MODELS -----------------

class DBUser(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)
    currency = Column(String, default="TRY")
    subscription_tier = Column(String, default="FREE")  # FREE, PRO, ENTERPRISE
    subscription_status = Column(String, default="active")  # active, past_due, canceled
    subscription_ends_at = Column(DateTime, nullable=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    positions = relationship("DBPosition", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("DBTransaction", back_populates="user", cascade="all, delete-orphan")
    snapshots = relationship("DBPortfolioSnapshot", back_populates="user", cascade="all, delete-orphan")
    summaries = relationship("DBAssetClassSummary", back_populates="user", cascade="all, delete-orphan")
    performance = relationship("DBPerformanceHistory", back_populates="user", cascade="all, delete-orphan")
    liabilities = relationship("DBLiability", back_populates="user", cascade="all, delete-orphan")
    targets = relationship("DBTargetAllocation", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("DBPriceAlert", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("DBNotification", back_populates="user", cascade="all, delete-orphan")
    auth_tokens = relationship("DBAuthToken", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("DBPayment", back_populates="user", cascade="all, delete-orphan")


class DBPosition(Base):
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, nullable=False)
    asset_class = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    buy_date = Column(Date, nullable=False)
    buy_currency = Column(String, nullable=False)
    cost_basis_tly = Column(Float, nullable=True)
    
    # Fixed Income / Commodity custom fields (original positions table fields)
    asset_type = Column(String, nullable=True)
    interest_rate = Column(Float, nullable=True)
    maturity_date = Column(String, nullable=True)
    commodity_type = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Constraints & Relationships
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", name="uq_user_ticker"),
        Index("idx_positions_user", "user_id"),
    )
    
    user = relationship("DBUser", back_populates="positions")
    transactions = relationship("DBTransaction", back_populates="position", cascade="all, delete-orphan")


class DBTransaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id", ondelete="SET NULL"), nullable=True)
    ticker = Column(String, nullable=False)
    asset_class = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)  # BUY, SELL, DIVIDEND, SPLIT
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    transaction_date = Column(Date, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_transactions_user", "user_id"),
        Index("idx_transactions_ticker", "ticker"),
        Index("idx_transactions_date", "transaction_date"),
    )
    
    user = relationship("DBUser", back_populates="transactions")
    position = relationship("DBPosition", back_populates="transactions")


class DBPriceHistory(Base):
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, nullable=False)
    asset_class = Column(String, nullable=False)
    price_date = Column(Date, nullable=False)
    price_usd = Column(Float, nullable=True)
    price_try = Column(Float, nullable=True)
    usd_try_rate = Column(Float, nullable=True)
    source = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("ticker", "price_date", name="uq_ticker_date"),
        Index("idx_price_history_ticker_date", "ticker", "price_date"),
    )


class DBExchangeRate(Base):
    __tablename__ = "exchange_rates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    rate_date = Column(Date, unique=True, nullable=False)
    usd_try_rate = Column(Float, nullable=False)
    source = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DBPortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(Date, nullable=False)
    total_invested_try = Column(Float, nullable=True)
    total_value_try = Column(Float, nullable=True)
    total_return_try = Column(Float, nullable=True)
    total_return_pct = Column(Float, nullable=True)
    snapshot_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_user_snapshot_date"),
        Index("idx_portfolio_snapshots_user_date", "user_id", "snapshot_date"),
    )
    
    user = relationship("DBUser", back_populates="snapshots")


class DBAssetClassSummary(Base):
    __tablename__ = "asset_class_summaries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(Date, nullable=False)
    asset_class = Column(String, nullable=False)
    total_invested_try = Column(Float, nullable=True)
    total_value_try = Column(Float, nullable=True)
    total_return_try = Column(Float, nullable=True)
    total_return_pct = Column(Float, nullable=True)
    position_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", "asset_class", name="uq_user_date_asset_class"),
        Index("idx_asset_class_summaries_date", "snapshot_date"),
    )
    
    user = relationship("DBUser", back_populates="summaries")


class DBPerformanceHistory(Base):
    __tablename__ = "performance_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    period_date = Column(Date, nullable=False)
    period_type = Column(String, nullable=False)  # DAILY, MONTHLY, YEARLY
    value_try = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("user_id", "period_date", "period_type", name="uq_user_period_type"),
        Index("idx_performance_history_user_date", "user_id", "period_date"),
    )
    
    user = relationship("DBUser", back_populates="performance")


class DBLiability(Base):
    __tablename__ = "liabilities"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    liability_type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="TRY")
    due_date = Column(String, nullable=True)
    interest_rate = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("DBUser", back_populates="liabilities")


class DBTargetAllocation(Base):
    __tablename__ = "target_allocations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    asset_class = Column(String, nullable=False)
    target_pct = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("DBUser", back_populates="targets")


class DBPriceAlert(Base):
    __tablename__ = "price_alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, nullable=False)
    target_price = Column(Float, nullable=False)
    condition = Column(String, nullable=False)  # ABOVE, BELOW
    is_triggered = Column(Integer, default=0)  # 0 or 1
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("DBUser", back_populates="alerts")


class DBNotification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    type = Column(String, nullable=False)
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("DBUser", back_populates="notifications")


class DBAuthToken(Base):
    """Refresh token, email doğrulama ve şifre sıfırlama token'ları için ortak tablo.

    Ham token asla saklanmaz — sadece sha256 hash'i tutulur, böylece DB sızıntısı
    tek başına token'ların kullanılmasına izin vermez.
    """
    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    token_type = Column(String, nullable=False)  # REFRESH, EMAIL_VERIFY, PASSWORD_RESET
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_auth_tokens_user_type", "user_id", "token_type"),
    )

    user = relationship("DBUser", back_populates="auth_tokens")


class DBPayment(Base):
    """Ödeme geçmişi / audit trail. DBUser.subscription_* alanları yalnızca bir
    ödeme 'succeeded' olduğunda güncellenir — bu tablo o kararın kanıtını tutar."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String, nullable=False)  # 'lemonsqueezy'
    provider_reference = Column(String, nullable=False)  # benzersiz placeholder — asıl korelasyon DBPayment.id üzerinden
    plan_tier = Column(String, nullable=False)  # 'PRO' | 'ENTERPRISE'
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)  # 'USD' | 'TRY'
    status = Column(String, nullable=False, default="pending")  # pending | succeeded | failed
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "provider_reference", name="uq_provider_reference"),
        Index("idx_payments_user", "user_id"),
    )

    user = relationship("DBUser", back_populates="payments")


# Dependency for database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
