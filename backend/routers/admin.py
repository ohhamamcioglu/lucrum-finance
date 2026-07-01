from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from models import AdminUserListResponse, AdminUpdateUserRequest, AdminUserSummary, AdminStatsResponse
from crud import list_users_paginated, update_user_subscription_tier, set_user_active, get_admin_stats
from dependencies import require_admin, get_db
from rate_limit import limiter

router = APIRouter(prefix="/api/admin", tags=["Admin"])

VALID_TIERS = ("FREE", "PRO", "ENTERPRISE")


@router.get("/users", response_model=AdminUserListResponse)
@limiter.limit("60/minute")
def admin_list_users(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    search: str = None,
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Kullanıcıları sayfalı ve aranabilir şekilde listeler (sadece admin)."""
    return list_users_paginated(page=page, page_size=page_size, search=search, db=db)


@router.patch("/users/{user_id}", response_model=AdminUserSummary)
@limiter.limit("60/minute")
def admin_update_user(
    request: Request,
    user_id: int,
    req: AdminUpdateUserRequest,
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: bir kullanıcının abonelik tier'ını ve/veya aktiflik durumunu günceller."""
    if req.subscription_tier is None and req.is_active is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Güncellenecek alan yok.")

    if req.subscription_tier is not None:
        tier = req.subscription_tier.upper().strip()
        if tier not in VALID_TIERS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz plan seçimi.")
        updated = update_user_subscription_tier(user_id, tier, db=db)
        if not updated:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    if req.is_active is not None:
        if user_id == admin_id and req.is_active is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kendi hesabınızı devre dışı bırakamazsınız.")
        updated = set_user_active(user_id, req.is_active, db=db)
        if not updated:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    return updated


@router.get("/stats", response_model=AdminStatsResponse)
@limiter.limit("60/minute")
def admin_stats(
    request: Request,
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: temel kullanıcı istatistikleri."""
    return get_admin_stats(db=db)
