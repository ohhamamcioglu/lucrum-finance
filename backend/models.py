"""
Pydantic Models for Portfolio API
"""
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List

# Kullanıcı
class UserBase(BaseModel):
    email: str
    name: str
    currency: str = "TRY"
    subscription_tier: str = "FREE"
    subscription_status: str = "active"
    subscription_ends_at: Optional[datetime] = None
    email_verified: bool = False

class UserCreate(UserBase):
    password: str = Field(min_length=8)

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)

class VerifyEmailRequest(BaseModel):
    token: str

class User(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Pozisyon
class PositionBase(BaseModel):
    ticker: str
    asset_class: str
    quantity: float
    buy_price: float
    buy_date: date
    buy_currency: str = "TRY"
    cost_basis_tly: Optional[float] = None
    asset_type: Optional[str] = None
    interest_rate: Optional[float] = None
    maturity_date: Optional[str] = None
    commodity_type: Optional[str] = None
    unit: Optional[str] = None

class PositionCreate(PositionBase):
    pass

class PositionUpdate(BaseModel):
    quantity: Optional[float] = None
    buy_price: Optional[float] = None
    buy_date: Optional[date] = None
    buy_currency: Optional[str] = None
    cost_basis_tly: Optional[float] = None
    asset_type: Optional[str] = None
    interest_rate: Optional[float] = None
    maturity_date: Optional[str] = None
    commodity_type: Optional[str] = None
    unit: Optional[str] = None

class Position(PositionBase):
    id: int
    user_id: int
    cost_basis_tly: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# İşlem
class TransactionBase(BaseModel):
    ticker: str
    asset_class: str
    transaction_type: str  # BUY, SELL, DIVIDEND
    quantity: float
    price: float
    currency: str = "TRY"
    transaction_date: date
    notes: Optional[str] = None

class TransactionCreate(TransactionBase):
    pass

class Transaction(TransactionBase):
    id: int
    user_id: int
    position_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

# Portföy Özeti
class PositionDetail(BaseModel):
    ticker: str
    asset_class: str
    quantity: float
    buy_price: float
    buy_date: date
    buy_currency: str
    current_price: Optional[float]
    current_value_tly: Optional[float]
    invested_tly: float
    gross_return_tly: Optional[float]
    gross_return_pct: Optional[float]
    price_effect_pct: Optional[float]
    fx_effect_pct: Optional[float]

class AssetClassSummary(BaseModel):
    asset_class: str
    count: int
    invested_tly: float
    current_value_tly: float
    return_tly: float
    return_pct: float

class PortfolioSummary(BaseModel):
    timestamp: datetime
    total_invested_tly: float
    total_value_tly: float
    total_return_tly: float
    total_return_pct: float
    by_asset_class: dict[str, AssetClassSummary]
    holdings: List[PositionDetail]

# Fiyat Geçmişi
class PriceHistory(BaseModel):
    ticker: str
    price_date: date
    price_usd: Optional[float]
    price_try: Optional[float]
    usd_try_rate: Optional[float]
    source: str

class PriceHistoryCreate(PriceHistory):
    asset_class: str

# Kur Geçmişi
class ExchangeRateCreate(BaseModel):
    rate_date: date
    usd_try_rate: float
    source: str = "yfinance"

class ExchangeRate(ExchangeRateCreate):
    id: int

    class Config:
        from_attributes = True

# Borçlar (Liabilities)
class LiabilityBase(BaseModel):
    name: str
    liability_type: str
    amount: float
    currency: str = "TRY"
    due_date: Optional[str] = None
    interest_rate: Optional[float] = None

class LiabilityCreate(LiabilityBase):
    pass

class LiabilityUpdate(BaseModel):
    name: Optional[str] = None
    liability_type: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    due_date: Optional[str] = None
    interest_rate: Optional[float] = None

class Liability(LiabilityBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Hedef Dağılım (Target Allocation)
class TargetAllocationBase(BaseModel):
    asset_class: str
    target_pct: float

class TargetAllocationCreate(TargetAllocationBase):
    pass

class TargetAllocation(TargetAllocationBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True

# Fiyat Alarmı (Price Alert)
class PriceAlertBase(BaseModel):
    ticker: str
    target_price: float
    condition: str  # ABOVE, BELOW

class PriceAlertCreate(PriceAlertBase):
    pass

class PriceAlert(PriceAlertBase):
    id: int
    user_id: int
    is_triggered: int
    created_at: datetime

    class Config:
        from_attributes = True

# Bildirimler (Notifications)
class NotificationBase(BaseModel):
    title: str
    message: str
    type: str  # price_alert, rebalance_alert, info

class Notification(NotificationBase):
    id: int
    user_id: int
    is_read: int
    created_at: datetime

    class Config:
        from_attributes = True
