from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from models import (
    AdminUserListResponse, AdminUpdateUserRequest, AdminUserSummary, AdminStatsResponse,
    AuditLogListResponse,
)
from crud import (
    list_users_paginated, update_user_subscription_tier, set_user_active, get_admin_stats,
    get_user_by_id, create_audit_log, list_audit_logs,
)
from dependencies import require_admin, get_db
from rate_limit import limiter
from services import calculate_portfolio

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

    admin = get_user_by_id(admin_id, db=db)
    target_before = get_user_by_id(user_id, db=db)
    target_email = target_before.get("email") if target_before else None

    if req.subscription_tier is not None:
        tier = req.subscription_tier.upper().strip()
        if tier not in VALID_TIERS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz plan seçimi.")
        updated = update_user_subscription_tier(user_id, tier, db=db)
        if not updated:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
        create_audit_log(
            admin_id, admin.get("email") if admin else None, "tier_change",
            target_user_id=user_id, target_email=target_email,
            details=f"{(target_before or {}).get('subscription_tier')} -> {tier}", db=db,
        )

    if req.is_active is not None:
        if user_id == admin_id and req.is_active is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kendi hesabınızı devre dışı bırakamazsınız.")
        updated = set_user_active(user_id, req.is_active, db=db)
        if not updated:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
        create_audit_log(
            admin_id, admin.get("email") if admin else None, "toggle_active",
            target_user_id=user_id, target_email=target_email,
            details=f"is_active -> {req.is_active}", db=db,
        )

    return updated


@router.get("/users/{user_id}/portfolio")
@limiter.limit("30/minute")
def admin_view_user_portfolio(
    request: Request,
    user_id: int,
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: destek amaçlı, SADECE OKUNUR bir kullanıcının portföyünü görüntüler.
    Erişim her seferinde audit_logs'a kaydedilir — başka bir kullanıcının özel
    finansal verisine bakmak hesap verebilirlik gerektiren bir işlemdir."""
    target = get_user_by_id(user_id, db=db)
    if not target:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    admin = get_user_by_id(admin_id, db=db)
    create_audit_log(
        admin_id, admin.get("email") if admin else None, "view_portfolio",
        target_user_id=user_id, target_email=target.get("email"), db=db,
    )

    return calculate_portfolio(user_id)


@router.get("/audit-log", response_model=AuditLogListResponse)
@limiter.limit("60/minute")
def admin_audit_log(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: geçmiş admin işlemlerinin (tier/aktiflik değişimi, portföy görüntüleme) izi."""
    return list_audit_logs(page=page, page_size=page_size, db=db)


@router.get("/stats", response_model=AdminStatsResponse)
@limiter.limit("60/minute")
def admin_stats(
    request: Request,
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: temel kullanıcı istatistikleri."""
    return get_admin_stats(db=db)
