import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from models import User, UserCreate, UserLogin, Token, ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest
from crud import (
    get_user_by_id, get_user_by_email, create_user,
    create_auth_token, get_valid_auth_token, consume_auth_token,
    revoke_auth_token, revoke_all_refresh_tokens,
    mark_email_verified, update_user_password, delete_user,
)
from dependencies import get_current_user_id, get_db
from auth import (
    verify_password, get_password_hash, create_access_token,
    generate_opaque_token, hash_token,
    REFRESH_TOKEN_EXPIRE_DAYS, EMAIL_VERIFY_TOKEN_EXPIRE_HOURS, PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
)
from email_service import send_verification_email, send_password_reset_email
from rate_limit import limiter

router = APIRouter(prefix="/api/users", tags=["Users"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

REFRESH_COOKIE_NAME = "lucrum_refresh_token"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
# Frontend (Vercel) ve backend (Render) farklı domain'lerde barındığı için
# production'da cross-site cookie gönderimi gerekiyor — bu sadece Secure=true
# iken (yani zaten https üzerinde) izinli. Yerelde http olduğundan Lax kalır.
COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"


def _issue_refresh_cookie(user_id: int, response: Response, db: Session) -> None:
    """Yeni bir refresh token üretir, DB'ye (hash'lenmiş) kaydeder ve httpOnly cookie olarak set eder."""
    raw = generate_opaque_token()
    expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    create_auth_token(user_id, hash_token(raw), "REFRESH", expires_at, db=db)
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/api/users",
    )


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
    response: Response,
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

    # Email doğrulama linki gönder (RESEND_API_KEY yoksa dev modda log'a yazılır)
    verify_raw = generate_opaque_token()
    verify_expires = datetime.utcnow() + timedelta(hours=EMAIL_VERIFY_TOKEN_EXPIRE_HOURS)
    create_auth_token(user_id, hash_token(verify_raw), "EMAIL_VERIFY", verify_expires, db=db)
    send_verification_email(user_data.email, verify_raw)

    _issue_refresh_cookie(user_id, response, db)
    access_token = create_access_token(data={"sub": str(user_id), "email": user_data.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(
    request: Request,
    response: Response,
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
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hesabınız devre dışı bırakılmıştır."
        )

    _issue_refresh_cookie(user["id"], response, db)
    access_token = create_access_token(data={"sub": str(user["id"]), "email": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}


class GoogleLoginRequest(BaseModel):
    credential: str


@router.post("/google-login", response_model=Token)
@limiter.limit("10/minute")
def google_login(
    request: Request,
    response: Response,
    body: GoogleLoginRequest,
    db: Session = Depends(get_db),
):
    """Google Identity Services'ten gelen ID token'ı doğrulayıp giriş/kayıt yapar.
    Email, Google tarafından zaten doğrulanmış kabul edilir. Aynı email'le daha önce
    şifreyle kayıt olunmuşsa, o hesaba giriş yapılır (email tekil kimlik olarak kullanılır)."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google ile giriş şu an yapılandırılmamış.")

    try:
        idinfo = google_id_token.verify_oauth2_token(
            body.credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Geçersiz Google kimlik doğrulaması.")

    email = idinfo.get("email")
    if not email or not idinfo.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google hesabının e-postası doğrulanmamış.")
    name = idinfo.get("name") or email.split("@")[0]

    user = get_user_by_email(email, db=db)
    if not user:
        user_id = create_user(email=email, name=name, password_hash=None, db=db)
        mark_email_verified(user_id, db=db)
    else:
        if not user.get("is_active", True):
            raise HTTPException(status_code=403, detail="Hesabınız devre dışı bırakılmıştır.")
        user_id = user["id"]
        if not user.get("email_verified"):
            mark_email_verified(user_id, db=db)

    _issue_refresh_cookie(user_id, response, db)
    access_token = create_access_token(data={"sub": str(user_id), "email": email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh", response_model=Token)
@limiter.limit("30/minute")
def refresh_access_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """httpOnly refresh cookie ile yeni bir access token üretir (refresh token rotation)."""
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token bulunamadı.")

    token_hash = hash_token(raw)
    record = get_valid_auth_token(token_hash, "REFRESH", db=db)
    if not record:
        response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/users")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token geçersiz veya süresi dolmuş.")

    user = get_user_by_id(record.user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kullanıcı bulunamadı.")
    if not user.get("is_active", True):
        response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/users")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınız devre dışı bırakılmıştır.")

    # Rotation: eski token'ı iptal et, yenisini ver (çalınmış token replay'ini sınırlar)
    revoke_auth_token(token_hash, db=db)
    _issue_refresh_cookie(record.user_id, response, db)

    access_token = create_access_token(data={"sub": str(record.user_id), "email": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Refresh token'ı iptal eder ve cookie'yi temizler."""
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw:
        revoke_auth_token(hash_token(raw), db=db)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/users")
    return {"status": "success"}


@router.delete("/me")
@limiter.limit("3/minute")
def delete_account(
    request: Request,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Giriş yapmış kullanıcının kendi hesabını ve TÜM verilerini kalıcı olarak siler
    (KVKK madde 11 — Gizlilik Politikası'nın vaat ettiği silme hakkı). Geri alınamaz.
    Not: delete_user zaten kullanıcının auth_tokens kayıtlarını cascade ile sildiğinden
    ayrıca revoke_auth_token çağırmaya gerek yok — cookie'yi temizlemek yeterli."""
    deleted = delete_user(user_id, db=db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/users")
    return {"status": "success"}


@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(
    request: Request,
    req: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """Şifre sıfırlama linki gönderir. Kullanıcı enumeration'ı önlemek için her zaman aynı mesajı döner."""
    user = get_user_by_email(req.email, db=db)
    if user:
        raw = generate_opaque_token()
        expires_at = datetime.utcnow() + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
        create_auth_token(user["id"], hash_token(raw), "PASSWORD_RESET", expires_at, db=db)
        send_password_reset_email(user["email"], raw)

    return {
        "status": "success",
        "message": "Bu e-posta adresi kayıtlıysa, şifre sıfırlama bağlantısı gönderildi."
    }


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(
    request: Request,
    req: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """Şifre sıfırlama token'ını doğrular, yeni şifreyi kaydeder ve tüm oturumları kapatır."""
    token_hash = hash_token(req.token)
    record = get_valid_auth_token(token_hash, "PASSWORD_RESET", db=db)
    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz veya süresi dolmuş bağlantı.")

    consume_auth_token(token_hash, db=db)
    update_user_password(record.user_id, get_password_hash(req.new_password), db=db)
    revoke_all_refresh_tokens(record.user_id, db=db)

    return {"status": "success", "message": "Şifreniz güncellendi. Lütfen tekrar giriş yapın."}


@router.post("/verify-email")
@limiter.limit("10/minute")
def verify_email(
    request: Request,
    req: VerifyEmailRequest,
    db: Session = Depends(get_db)
):
    """Email doğrulama token'ını doğrular ve kullanıcıyı doğrulanmış olarak işaretler."""
    token_hash = hash_token(req.token)
    record = get_valid_auth_token(token_hash, "EMAIL_VERIFY", db=db)
    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz veya süresi dolmuş doğrulama bağlantısı.")

    consume_auth_token(token_hash, db=db)
    mark_email_verified(record.user_id, db=db)

    return {"status": "success", "message": "Email adresiniz doğrulandı."}


@router.post("/resend-verification")
@limiter.limit("3/minute")
def resend_verification(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Giriş yapmış kullanıcı için email doğrulama linkini tekrar gönderir."""
    user = get_user_by_id(user_id, db=db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if user.get("email_verified"):
        return {"status": "success", "message": "Email adresiniz zaten doğrulanmış."}

    raw = generate_opaque_token()
    expires_at = datetime.utcnow() + timedelta(hours=EMAIL_VERIFY_TOKEN_EXPIRE_HOURS)
    create_auth_token(user_id, hash_token(raw), "EMAIL_VERIFY", expires_at, db=db)
    send_verification_email(user["email"], raw)

    return {"status": "success", "message": "Doğrulama emaili gönderildi."}


class SubscribeRequest(BaseModel):
    plan: str  # FREE, PRO, ENTERPRISE

@router.post("/subscribe", response_model=dict)
def subscribe(
    req: SubscribeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Kullanıcının kendi kendine ücretsiz plana düşmesini sağlar.
    PRO/ENTERPRISE yükseltmesi artık gerçek ödeme gerektiriyor — bkz. /api/payments/*.
    (Bu endpoint eskiden ödeme olmadan doğrudan tier ataması yapan mock bir
    checkout'tu; ödeme entegrasyonuyla birlikte bu bypass kapatıldı.)"""
    plan = req.plan.upper().strip()
    if plan != "FREE":
        raise HTTPException(
            status_code=400,
            detail="Bu plan için ödeme gereklidir, lütfen fiyatlandırma sayfasını kullanın."
        )

    from db_models import DBUser
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    user.subscription_tier = plan
    user.subscription_status = "active"
    user.subscription_ends_at = None

    db.commit()

    return {
        "status": "success",
        "message": f"Abonelik planınız başarıyla {plan} olarak güncellendi.",
        "subscription_tier": plan,
        "subscription_status": "active",
        "subscription_ends_at": user.subscription_ends_at.isoformat() if user.subscription_ends_at else None
    }
