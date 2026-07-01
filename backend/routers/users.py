import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from models import User, UserCreate, UserLogin, Token
from crud import get_user_by_id, get_user_by_email, create_user
from dependencies import get_current_user_id, get_db
from auth import verify_password, get_password_hash, create_access_token
from rate_limit import limiter

router = APIRouter(prefix="/api/users", tags=["Users"])

@router.get("/me", response_model=User)
def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Mevcut kullanıcı bilgisini al"""
    user = get_user_by_id(user_id, db=db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/register", response_model=Token)
@limiter.limit("5/minute")
def register(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """Yeni kullanıcı kaydı oluşturur"""
    existing_user = get_user_by_email(user_data.email, db=db)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresiyle kayıtlı bir kullanıcı zaten mevcut."
        )
    
    hashed_pwd = get_password_hash(user_data.password)
    try:
        user_id = create_user(
            email=user_data.email,
            name=user_data.name,
            password_hash=hashed_pwd,
            db=db
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kayıt oluşturulurken bir hata oluştu."
        )
    
    access_token = create_access_token(data={"sub": str(user_id), "email": user_data.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(
    request: Request,
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """Kullanıcı girişi yapar ve access token döner"""
    user = get_user_by_email(login_data.email, db=db)
    if not user or not verify_password(login_data.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta adresi veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": str(user["id"]), "email": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

from pydantic import BaseModel

class SubscribeRequest(BaseModel):
    plan: str  # FREE, PRO, ENTERPRISE

@router.post("/subscribe", response_model=dict)
def subscribe(
    req: SubscribeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Kullanıcı abonelik planını günceller (Mocked Payment Checkout/Webhook)"""
    plan = req.plan.upper().strip()
    if plan not in ("FREE", "PRO", "ENTERPRISE"):
        raise HTTPException(status_code=400, detail="Geçersiz plan seçimi.")
        
    from db_models import DBUser
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
        
    user.subscription_tier = plan
    user.subscription_status = "active"
    from datetime import datetime, timedelta
    user.subscription_ends_at = datetime.utcnow() + timedelta(days=30)
    
    db.commit()
    
    return {
        "status": "success",
        "message": f"Abonelik planınız başarıyla {plan} olarak güncellendi.",
        "subscription_tier": plan,
        "subscription_status": "active",
        "subscription_ends_at": user.subscription_ends_at.isoformat()
    }
