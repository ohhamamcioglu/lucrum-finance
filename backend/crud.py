from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import desc, and_
from sqlalchemy.orm import Session

from models import (
    Position, PositionCreate, PositionUpdate,
    Transaction, TransactionCreate,
    PriceHistoryCreate, ExchangeRateCreate,
    LiabilityCreate, LiabilityUpdate, TargetAllocationCreate, PriceAlertCreate
)
from db_models import (
    SessionLocal, DBUser, DBPosition, DBTransaction, DBPriceHistory,
    DBExchangeRate, DBPortfolioSnapshot, DBAssetClassSummary,
    DBPerformanceHistory, DBLiability, DBTargetAllocation,
    DBPriceAlert, DBNotification, DBAuthToken
)

# ----------------- HELPERS -----------------

def to_dict(obj) -> Optional[Dict[str, Any]]:
    """Converts a SQLAlchemy ORM model object to a plain python dictionary."""
    if obj is None:
        return None
    # Use __table__.columns to extract database column values
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def to_dict_list(objs) -> List[Dict[str, Any]]:
    """Converts a list of SQLAlchemy ORM objects into a list of dictionaries."""
    return [to_dict(o) for o in objs if o is not None]

# Decorator-like helper to inject DB Session if omitted
def _get_db(db: Optional[Session] = None):
    if db is not None:
        return db, False
    return SessionLocal(), True

# ============ USERS ============

def get_or_create_user(email: str, name: str = "User", db: Optional[Session] = None) -> int:
    """Kullanıcı al veya oluştur"""
    session, must_close = _get_db(db)
    try:
        email_clean = email.lower().strip()
        user = session.query(DBUser).filter(DBUser.email == email_clean).first()
        if user:
            return user.id

        user = DBUser(email=email_clean, name=name, currency="TRY")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id
    finally:
        if must_close:
            session.close()

def get_user_by_id(user_id: int, db: Optional[Session] = None) -> Optional[Dict]:
    """Kullanıcı detayını al"""
    session, must_close = _get_db(db)
    try:
        user = session.query(DBUser).filter(DBUser.id == user_id).first()
        return to_dict(user)
    finally:
        if must_close:
            session.close()

def create_user(email: str, name: str, password_hash: str, db: Optional[Session] = None) -> int:
    """Yeni bir kullanıcı oluşturur ve ID'sini döner."""
    session, must_close = _get_db(db)
    try:
        user = DBUser(email=email.lower().strip(), name=name, password_hash=password_hash, currency="TRY")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id
    finally:
        if must_close:
            session.close()

def get_user_by_email(email: str, db: Optional[Session] = None) -> Optional[Dict]:
    """Email adresine göre kullanıcı detayını al"""
    session, must_close = _get_db(db)
    try:
        user = session.query(DBUser).filter(DBUser.email == email.lower().strip()).first()
        return to_dict(user)
    finally:
        if must_close:
            session.close()

# ============ AUTH TOKENS (refresh / email-verify / password-reset) ============

def create_auth_token(user_id: int, token_hash: str, token_type: str, expires_at: datetime, db: Optional[Session] = None) -> None:
    """Yeni bir auth token kaydı oluşturur (ham token asla saklanmaz, sadece hash)."""
    session, must_close = _get_db(db)
    try:
        record = DBAuthToken(
            user_id=user_id,
            token_hash=token_hash,
            token_type=token_type,
            expires_at=expires_at,
        )
        session.add(record)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def get_valid_auth_token(token_hash: str, token_type: str, db: Optional[Session] = None) -> Optional[DBAuthToken]:
    """Süresi dolmamış, iptal edilmemiş ve kullanılmamış bir auth token'ı bulur."""
    session, must_close = _get_db(db)
    try:
        record = session.query(DBAuthToken).filter(
            DBAuthToken.token_hash == token_hash,
            DBAuthToken.token_type == token_type,
            DBAuthToken.revoked_at.is_(None),
            DBAuthToken.used_at.is_(None),
            DBAuthToken.expires_at > datetime.utcnow(),
        ).first()
        if record is not None:
            session.expunge(record)
        return record
    finally:
        if must_close:
            session.close()

def consume_auth_token(token_hash: str, db: Optional[Session] = None) -> None:
    """Tek kullanımlık token'ı (email verify / password reset) kullanıldı olarak işaretler."""
    session, must_close = _get_db(db)
    try:
        session.query(DBAuthToken).filter(DBAuthToken.token_hash == token_hash).update({"used_at": datetime.utcnow()})
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def revoke_auth_token(token_hash: str, db: Optional[Session] = None) -> None:
    """Refresh token'ı iptal eder (logout / rotation)."""
    session, must_close = _get_db(db)
    try:
        session.query(DBAuthToken).filter(DBAuthToken.token_hash == token_hash).update({"revoked_at": datetime.utcnow()})
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def revoke_all_refresh_tokens(user_id: int, db: Optional[Session] = None) -> None:
    """Kullanıcının tüm refresh token'larını iptal eder (şifre sıfırlama sonrası tüm oturumları kapatır)."""
    session, must_close = _get_db(db)
    try:
        session.query(DBAuthToken).filter(
            DBAuthToken.user_id == user_id,
            DBAuthToken.token_type == "REFRESH",
            DBAuthToken.revoked_at.is_(None),
        ).update({"revoked_at": datetime.utcnow()})
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def mark_email_verified(user_id: int, db: Optional[Session] = None) -> None:
    session, must_close = _get_db(db)
    try:
        session.query(DBUser).filter(DBUser.id == user_id).update({"email_verified": True})
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def update_user_password(user_id: int, password_hash: str, db: Optional[Session] = None) -> None:
    session, must_close = _get_db(db)
    try:
        session.query(DBUser).filter(DBUser.id == user_id).update({"password_hash": password_hash})
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

# ============ POSITIONS ============

def create_position(user_id: int, pos: PositionCreate, db: Optional[Session] = None) -> Position:
    """Yeni pozisyon ekle"""
    session, must_close = _get_db(db)
    try:
        db_pos = DBPosition(
            user_id=user_id,
            ticker=pos.ticker.upper().strip(),
            asset_class=pos.asset_class,
            quantity=pos.quantity,
            buy_price=pos.buy_price,
            buy_date=pos.buy_date,
            buy_currency=pos.buy_currency,
            cost_basis_tly=pos.cost_basis_tly,
            asset_type=pos.asset_type,
            interest_rate=pos.interest_rate,
            maturity_date=pos.maturity_date,
            commodity_type=pos.commodity_type,
            unit=pos.unit
        )
        session.add(db_pos)
        session.flush()  # Populates db_pos.id

        # İşlem geçmişine ekle (BUY işlemi)
        db_txn = DBTransaction(
            user_id=user_id,
            position_id=db_pos.id,
            ticker=pos.ticker.upper().strip(),
            asset_class=pos.asset_class,
            transaction_type="BUY",
            quantity=pos.quantity,
            price=pos.buy_price,
            currency=pos.buy_currency,
            transaction_date=pos.buy_date
        )
        session.add(db_txn)
        session.commit()
        session.refresh(db_pos)

        return Position(
            id=db_pos.id,
            user_id=user_id,
            ticker=db_pos.ticker,
            asset_class=db_pos.asset_class,
            quantity=db_pos.quantity,
            buy_price=db_pos.buy_price,
            buy_date=db_pos.buy_date,
            buy_currency=db_pos.buy_currency,
            cost_basis_tly=db_pos.cost_basis_tly,
            asset_type=db_pos.asset_type,
            interest_rate=db_pos.interest_rate,
            maturity_date=db_pos.maturity_date,
            commodity_type=db_pos.commodity_type,
            unit=db_pos.unit,
            created_at=db_pos.created_at or datetime.now(),
            updated_at=db_pos.updated_at or datetime.now()
        )
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def get_positions(user_id: int, db: Optional[Session] = None) -> List[Dict]:
    """Kullanıcının pozisyonlarını al"""
    session, must_close = _get_db(db)
    try:
        positions = session.query(DBPosition).filter(DBPosition.user_id == user_id).order_by(DBPosition.ticker).all()
        return to_dict_list(positions)
    finally:
        if must_close:
            session.close()

def get_position_by_id(user_id: int, position_id: int, db: Optional[Session] = None) -> Optional[Dict]:
    """Belirli pozisyonu al"""
    session, must_close = _get_db(db)
    try:
        pos = session.query(DBPosition).filter(DBPosition.id == position_id, DBPosition.user_id == user_id).first()
        return to_dict(pos)
    finally:
        if must_close:
            session.close()

def update_position(user_id: int, position_id: int, update: PositionUpdate, db: Optional[Session] = None) -> Optional[Dict]:
    """Pozisyon güncelle"""
    session, must_close = _get_db(db)
    try:
        pos = session.query(DBPosition).filter(DBPosition.id == position_id, DBPosition.user_id == user_id).first()
        if not pos:
            return None

        # Update fields dynamically
        for key, value in update.model_dump(exclude_unset=True).items():
            setattr(pos, key, value)
            
        pos.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(pos)
        return to_dict(pos)
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def delete_position(user_id: int, position_id: int, db: Optional[Session] = None) -> bool:
    """Pozisyon sil"""
    session, must_close = _get_db(db)
    try:
        pos = session.query(DBPosition).filter(DBPosition.id == position_id, DBPosition.user_id == user_id).first()
        if not pos:
            return False

        # İşlem geçmişine SELL kaydı ekle
        db_txn = DBTransaction(
            user_id=user_id,
            position_id=position_id,
            ticker=pos.ticker,
            asset_class=pos.asset_class,
            transaction_type="SELL",
            quantity=pos.quantity,
            price=pos.buy_price,
            currency=pos.buy_currency,
            transaction_date=date.today()
        )
        session.add(db_txn)
        session.delete(pos)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

# ============ TRANSACTIONS ============

def get_transactions(user_id: int, ticker: Optional[str] = None, db: Optional[Session] = None) -> List[Dict]:
    """İşlem geçmişi al"""
    session, must_close = _get_db(db)
    try:
        query = session.query(DBTransaction).filter(DBTransaction.user_id == user_id)
        if ticker:
            query = query.filter(DBTransaction.ticker == ticker.upper().strip())
        txns = query.order_by(desc(DBTransaction.transaction_date)).all()
        return to_dict_list(txns)
    finally:
        if must_close:
            session.close()

def get_transaction_by_id(user_id: int, transaction_id: int, db: Optional[Session] = None) -> Optional[Dict]:
    """İşlem detayı al"""
    session, must_close = _get_db(db)
    try:
        txn = session.query(DBTransaction).filter(DBTransaction.id == transaction_id, DBTransaction.user_id == user_id).first()
        return to_dict(txn)
    finally:
        if must_close:
            session.close()

# ============ PRICE HISTORY ============

def save_price_history(data: PriceHistoryCreate, db: Optional[Session] = None) -> int:
    """Fiyat geçmişini kaydet"""
    session, must_close = _get_db(db)
    try:
        # Check if record already exists for ticker + date
        record = session.query(DBPriceHistory).filter(
            DBPriceHistory.ticker == data.ticker.upper().strip(),
            DBPriceHistory.price_date == data.price_date
        ).first()

        if record:
            record.asset_class = data.asset_class
            record.price_usd = data.price_usd
            record.price_try = data.price_try
            record.usd_try_rate = data.usd_try_rate
            record.source = data.source
            record.updated_at = datetime.utcnow()
        else:
            record = DBPriceHistory(
                ticker=data.ticker.upper().strip(),
                asset_class=data.asset_class,
                price_date=data.price_date,
                price_usd=data.price_usd,
                price_try=data.price_try,
                usd_try_rate=data.usd_try_rate,
                source=data.source
            )
            session.add(record)

        session.commit()
        session.refresh(record)
        return record.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def get_price_history(ticker: str, days: int = 90, db: Optional[Session] = None) -> List[Dict]:
    """Fiyat geçmişini al"""
    session, must_close = _get_db(db)
    try:
        limit_date = date.today() - timedelta(days=days)
        records = session.query(DBPriceHistory).filter(
            DBPriceHistory.ticker == ticker.upper().strip(),
            DBPriceHistory.price_date >= limit_date
        ).order_by(desc(DBPriceHistory.price_date)).all()
        return to_dict_list(records)
    finally:
        if must_close:
            session.close()

# ============ EXCHANGE RATES ============

def save_exchange_rate(data: ExchangeRateCreate, db: Optional[Session] = None) -> int:
    """Kur geçmişini kaydet"""
    session, must_close = _get_db(db)
    try:
        rate = session.query(DBExchangeRate).filter(DBExchangeRate.rate_date == data.rate_date).first()
        if rate:
            rate.usd_try_rate = data.usd_try_rate
            rate.source = data.source
            rate.updated_at = datetime.utcnow()
        else:
            rate = DBExchangeRate(
                rate_date=data.rate_date,
                usd_try_rate=data.usd_try_rate,
                source=data.source
            )
            session.add(rate)

        session.commit()
        session.refresh(rate)
        return rate.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def get_exchange_rate(rate_date: date, db: Optional[Session] = None) -> Optional[float]:
    """Belirli tarih için kuru al"""
    session, must_close = _get_db(db)
    try:
        rate = session.query(DBExchangeRate).filter(DBExchangeRate.rate_date == rate_date).first()
        return rate.usd_try_rate if rate else None
    finally:
        if must_close:
            session.close()

def get_exchange_rate_history(days: int = 90, db: Optional[Session] = None) -> List[Dict]:
    """Kur geçmişini al"""
    session, must_close = _get_db(db)
    try:
        limit_date = date.today() - timedelta(days=days)
        rates = session.query(DBExchangeRate).filter(
            DBExchangeRate.rate_date >= limit_date
        ).order_by(desc(DBExchangeRate.rate_date)).all()
        return to_dict_list(rates)
    finally:
        if must_close:
            session.close()

# ============ PORTFOLIO SNAPSHOTS ============

def save_portfolio_snapshot(user_id: int, snapshot_date: date, portfolio_data: Dict, db: Optional[Session] = None) -> int:
    """Portföy snapshot'ı kaydet"""
    session, must_close = _get_db(db)
    try:
        snapshot = session.query(DBPortfolioSnapshot).filter(
            DBPortfolioSnapshot.user_id == user_id,
            DBPortfolioSnapshot.snapshot_date == snapshot_date
        ).first()

        summary_data = portfolio_data.get('summary', {})
        invested = summary_data.get('total_invested_tly', 0)
        val = summary_data.get('total_value_tly', 0)
        ret = summary_data.get('total_return_tly', 0)
        ret_pct = summary_data.get('total_return_pct', 0)

        if snapshot:
            snapshot.total_invested_try = invested
            snapshot.total_value_try = val
            snapshot.total_return_try = ret
            snapshot.total_return_pct = ret_pct
            snapshot.snapshot_data = portfolio_data
        else:
            snapshot = DBPortfolioSnapshot(
                user_id=user_id,
                snapshot_date=snapshot_date,
                total_invested_try=invested,
                total_value_try=val,
                total_return_try=ret,
                total_return_pct=ret_pct,
                snapshot_data=portfolio_data
            )
            session.add(snapshot)

        session.commit()
        session.refresh(snapshot)
        return snapshot.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def get_portfolio_snapshots(user_id: int, days: int = 90, db: Optional[Session] = None) -> List[Dict]:
    """Portföy snapshot'larını al"""
    session, must_close = _get_db(db)
    try:
        limit_date = date.today() - timedelta(days=days)
        snapshots = session.query(DBPortfolioSnapshot).filter(
            DBPortfolioSnapshot.user_id == user_id,
            DBPortfolioSnapshot.snapshot_date >= limit_date
        ).order_by(desc(DBPortfolioSnapshot.snapshot_date)).all()
        return to_dict_list(snapshots)
    finally:
        if must_close:
            session.close()

# ============ LIABILITIES ============

def get_liabilities(user_id: int, db: Optional[Session] = None) -> List[Dict]:
    """Borçları al"""
    session, must_close = _get_db(db)
    try:
        liabilities = session.query(DBLiability).filter(DBLiability.user_id == user_id).order_by(DBLiability.due_date.asc()).all()
        return to_dict_list(liabilities)
    finally:
        if must_close:
            session.close()

def create_liability(user_id: int, item: LiabilityCreate, db: Optional[Session] = None) -> Dict:
    """Borç oluştur"""
    session, must_close = _get_db(db)
    try:
        db_liab = DBLiability(
            user_id=user_id,
            name=item.name,
            liability_type=item.liability_type,
            amount=item.amount,
            currency=item.currency,
            due_date=item.due_date,
            interest_rate=item.interest_rate
        )
        session.add(db_liab)
        session.commit()
        session.refresh(db_liab)
        return to_dict(db_liab)
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def update_liability(user_id: int, item_id: int, item: LiabilityUpdate, db: Optional[Session] = None) -> Optional[Dict]:
    """Borç güncelle"""
    session, must_close = _get_db(db)
    try:
        liab = session.query(DBLiability).filter(DBLiability.id == item_id, DBLiability.user_id == user_id).first()
        if not liab:
            return None

        for key, val in item.model_dump(exclude_unset=True).items():
            setattr(liab, key, val)

        liab.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(liab)
        return to_dict(liab)
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def delete_liability(user_id: int, item_id: int, db: Optional[Session] = None) -> bool:
    """Borç sil"""
    session, must_close = _get_db(db)
    try:
        liab = session.query(DBLiability).filter(DBLiability.id == item_id, DBLiability.user_id == user_id).first()
        if not liab:
            return False
        session.delete(liab)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

# ============ TARGET ALLOCATIONS ============

def get_target_allocations(user_id: int, db: Optional[Session] = None) -> List[Dict]:
    """Hedef dağılımları al"""
    session, must_close = _get_db(db)
    try:
        targets = session.query(DBTargetAllocation).filter(DBTargetAllocation.user_id == user_id).all()
        return to_dict_list(targets)
    finally:
        if must_close:
            session.close()

def save_target_allocations(user_id: int, allocations: List[TargetAllocationCreate], db: Optional[Session] = None) -> List[Dict]:
    """Hedef dağılımları kaydet"""
    session, must_close = _get_db(db)
    try:
        session.query(DBTargetAllocation).filter(DBTargetAllocation.user_id == user_id).delete()
        for item in allocations:
            db_target = DBTargetAllocation(
                user_id=user_id,
                asset_class=item.asset_class,
                target_pct=item.target_pct
            )
            session.add(db_target)
        session.commit()
        targets = session.query(DBTargetAllocation).filter(DBTargetAllocation.user_id == user_id).all()
        return to_dict_list(targets)
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

# ============ PRICE ALERTS ============

def get_price_alerts(user_id: int, db: Optional[Session] = None) -> List[Dict]:
    """Fiyat alarmlarını al"""
    session, must_close = _get_db(db)
    try:
        alerts = session.query(DBPriceAlert).filter(DBPriceAlert.user_id == user_id).order_by(desc(DBPriceAlert.created_at)).all()
        return to_dict_list(alerts)
    finally:
        if must_close:
            session.close()

def create_price_alert(user_id: int, item: PriceAlertCreate, db: Optional[Session] = None) -> Dict:
    """Fiyat alarmı oluştur"""
    session, must_close = _get_db(db)
    try:
        db_alert = DBPriceAlert(
            user_id=user_id,
            ticker=item.ticker.upper().strip(),
            target_price=item.target_price,
            condition=item.condition
        )
        session.add(db_alert)
        session.commit()
        session.refresh(db_alert)
        return to_dict(db_alert)
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def delete_price_alert(user_id: int, alert_id: int, db: Optional[Session] = None) -> bool:
    """Fiyat alarmı sil"""
    session, must_close = _get_db(db)
    try:
        alert = session.query(DBPriceAlert).filter(DBPriceAlert.id == alert_id, DBPriceAlert.user_id == user_id).first()
        if not alert:
            return False
        session.delete(alert)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def trigger_price_alert(alert_id: int, db: Optional[Session] = None) -> None:
    """Fiyat alarmını tetiklendi olarak işaretle"""
    session, must_close = _get_db(db)
    try:
        alert = session.query(DBPriceAlert).filter(DBPriceAlert.id == alert_id).first()
        if alert:
            alert.is_triggered = 1
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

# ============ NOTIFICATIONS ============

def get_notifications(user_id: int, db: Optional[Session] = None) -> List[Dict]:
    """Bildirimleri al"""
    session, must_close = _get_db(db)
    try:
        notifications = session.query(DBNotification).filter(
            DBNotification.user_id == user_id
        ).order_by(desc(DBNotification.created_at)).limit(50).all()
        return to_dict_list(notifications)
    finally:
        if must_close:
            session.close()

def create_notification(user_id: int, title: str, message: str, type_str: str, db: Optional[Session] = None) -> Dict:
    """Bildirim oluştur"""
    session, must_close = _get_db(db)
    try:
        db_notif = DBNotification(
            user_id=user_id,
            title=title,
            message=message,
            type=type_str
        )
        session.add(db_notif)
        session.commit()
        session.refresh(db_notif)
        return to_dict(db_notif)
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def mark_notifications_read(user_id: int, db: Optional[Session] = None) -> None:
    """Bildirimleri okundu olarak işaretle"""
    session, must_close = _get_db(db)
    try:
        session.query(DBNotification).filter(DBNotification.user_id == user_id).update({"is_read": 1})
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if must_close:
            session.close()

def has_recent_notification(user_id: int, type_str: str, title: str, hours: int = 1, db: Optional[Session] = None) -> bool:
    """Son X saat içinde aynı türde ve başlıkta bir bildirim olup olmadığını kontrol eder."""
    session, must_close = _get_db(db)
    try:
        time_limit = datetime.utcnow() - timedelta(hours=hours)
        notif = session.query(DBNotification).filter(
            DBNotification.user_id == user_id,
            DBNotification.type == type_str,
            DBNotification.title == title,
            DBNotification.created_at >= time_limit
        ).first()
        return notif is not None
    finally:
        if must_close:
            session.close()
