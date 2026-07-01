import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import bcrypt

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY ortam değişkeni tanımlı değil. "
        ".env dosyasında ayarlayın (python -c \"import secrets; print(secrets.token_urlsafe(64))\")."
    )
ALGORITHM = "HS256"
# Access token artık kısa ömürlü — oturum, refresh token (httpOnly cookie) ile uzatılır.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
EMAIL_VERIFY_TOKEN_EXPIRE_HOURS = 24
PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Plain text şifre ile hash'lenmiş şifreyi doğrular."""
    if not hashed_password or not plain_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Şifreyi bcrypt kullanarak güvenli şekilde hash'ler."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Kullanıcı bilgisi (user_id/email) içeren bir JWT access token oluşturur."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """JWT token'ı doğrular ve payload'unu döner."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except (jwt.PyJWTError, ValueError):
        return None

def generate_opaque_token() -> str:
    """Refresh/email-verify/password-reset için kriptografik olarak güvenli, opak bir token üretir."""
    return secrets.token_urlsafe(48)

def hash_token(token: str) -> str:
    """Opak token'ın DB'de saklanacak sha256 hash'i. Ham token asla DB'ye yazılmaz."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
