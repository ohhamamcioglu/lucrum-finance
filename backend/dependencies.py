from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from auth import decode_access_token
from database import get_db

# TokenUrl is points to our login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login", auto_error=False)

def get_current_user_id(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> int:
    """
    HTTP Authorization Bearer token'ını doğrular ve çözerek kullanıcı ID'sini (sub) döner.
    SaaS ortamı için kesin 401 yetkilendirmesi uygular.

    GÜVENLİK DÜZELTMESİ: Eskiden burada sadece JWT decode ediliyordu, kullanıcının hâlâ
    aktif olup olmadığı veya var olup olmadığı hiç sorulmuyordu — bir kullanıcı askıya
    alınsa (is_active=False) bile elindeki token'ın süresi dolana kadar (varsayılan 30dk)
    sisteme erişmeye devam edebiliyordu, hesabı "hemen" kapatmanın bir yolu yoktu. Artık
    her istekte tek bir ekstra DB sorgusuyla bu kontrol ediliyor.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yetkilendirme token'ı bulunamadı. Lütfen giriş yapın.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş yetkilendirme token'ı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token içerisinde kullanıcı kimliği bulunamadı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kullanıcı kimlik formatı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from db_models import DBUser
    user = db.query(DBUser.is_active).filter(DBUser.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hesap bulunamadı veya devre dışı bırakılmış.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id

def check_position_limit(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Kullanıcının üyelik planına göre pozisyon sınırını denetler."""
    from db_models import DBUser, DBPosition
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
        
    tier = (user.subscription_tier or "FREE").upper()
    if tier == "ENTERPRISE":
        return
        
    count = db.query(DBPosition).filter(DBPosition.user_id == user_id).count()
    
    limit = 5 if tier == "FREE" else 50
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Pozisyon sınırına ulaştınız ({limit} adet). Devam etmek için lütfen planınızı yükseltin."
        )

def check_price_alert_limit(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Kullanıcının üyelik planına göre fiyat alarmı sınırını denetler."""
    from db_models import DBUser, DBPriceAlert
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
        
    tier = (user.subscription_tier or "FREE").upper()
    if tier == "ENTERPRISE":
        return
        
    count = db.query(DBPriceAlert).filter(DBPriceAlert.user_id == user_id).count()
    
    limit = 3 if tier == "FREE" else 20
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Fiyat alarmı sınırına ulaştınız ({limit} adet). Devam etmek için lütfen planınızı yükseltin."
        )

def require_admin(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)) -> int:
    """Yalnızca is_admin=True kullanıcıların admin uç noktalarına erişimini sağlar."""
    from db_models import DBUser
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yönetici yetkisi gereklidir."
        )
    return user_id
