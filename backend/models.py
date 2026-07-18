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
    is_admin: bool = False

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

# Admin
class AdminUserSummary(BaseModel):
    id: int
    email: str
    name: str
    subscription_tier: str
    subscription_status: str
    is_admin: bool
    is_active: bool
    email_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True

class AdminUserListResponse(BaseModel):
    items: List[AdminUserSummary]
    total: int
    page: int
    page_size: int

class AdminUpdateUserRequest(BaseModel):
    subscription_tier: Optional[str] = None
    is_active: Optional[bool] = None

class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    verified_users: int
    admin_users: int
    tier_breakdown: dict

# Ödeme
class LemonSqueezyCheckoutRequest(BaseModel):
    plan: str  # PRO | ENTERPRISE

class CheckoutResponse(BaseModel):
    checkout_url: str

class PaymentSummary(BaseModel):
    id: int
    provider: str
    plan_tier: str
    amount: float
    currency: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# Pozisyon
class PositionBase(BaseModel):
    ticker: str
    asset_class: str
    quantity: float = Field(gt=0)
    buy_price: float = Field(gt=0)
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
    # gt=0: delta_quantity/delta_price İSTİSNA — top-up/kısmi satış farkını temsil ettikleri
    # için delta_quantity negatif olabilir (kısmi satış), o yüzden onlara kısıt konmadı.
    quantity: Optional[float] = Field(default=None, gt=0)
    buy_price: Optional[float] = Field(default=None, gt=0)
    buy_date: Optional[date] = None
    buy_currency: Optional[str] = None
    cost_basis_tly: Optional[float] = None
    asset_type: Optional[str] = None
    interest_rate: Optional[float] = None
    maturity_date: Optional[str] = None
    commodity_type: Optional[str] = None
    unit: Optional[str] = None
    # Bir top-up (ekleme) veya kısmi satış (azaltma) düzenlemesini GERÇEK bir işlem olarak
    # kaydetmek için — delta_quantity pozitifse BUY, negatifse SELL olarak, bugünün tarihiyle
    # işlem geçmişine eklenir. Eski/mevcut işlemlere hiç dokunulmaz. Bkz. crud.update_position.
    delta_quantity: Optional[float] = None
    delta_price: Optional[float] = Field(default=None, gt=0)

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
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
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
    usd_try_rate: Optional[float] = None
    eur_try_rate: Optional[float] = None
    gbp_try_rate: Optional[float] = None
    source: str = "yfinance"

class ExchangeRate(ExchangeRateCreate):
    id: int

    class Config:
        from_attributes = True

# Borçlar (Liabilities)
class LiabilityBase(BaseModel):
    name: str
    liability_type: str
    amount: float = Field(gt=0)
    currency: str = "TRY"
    due_date: Optional[str] = None
    interest_rate: Optional[float] = None

class LiabilityCreate(LiabilityBase):
    pass

class LiabilityUpdate(BaseModel):
    name: Optional[str] = None
    liability_type: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
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
    target_pct: float = Field(ge=0, le=100)

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
