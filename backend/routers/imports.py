"""
Esnek CSV/Excel içe aktarıcı (Faz 2, task #57).
İki adımlı akış: /preview dosyayı ayrıştırıp sütun eşlemesi önerir (henüz kaydetmez),
/confirm kullanıcının onayladığı/düzelttiği eşlemeyle gerçek Position kayıtlarını oluşturur.
Ayrıştırma/eşleme mantığı imports_engine.py'de — burada sadece HTTP, cache ve plan-limiti var.
"""
import uuid
from typing import Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

import imports_engine as engine
from cache import finance_cache
from crud import create_position
from db_models import DBPosition, DBUser
from dependencies import get_current_user_id, get_db
from models import (
    ImportConfirmRequest, ImportConfirmResponse, ImportPreviewResponse,
    ImportRowError, PositionCreate,
)
from services import invalidate_portfolio_cache, invalidate_twrr_cache

router = APIRouter(prefix="/api/imports", tags=["Imports"])

_IMPORT_TTL = 900  # 15 dakika — bu süre içinde confirm edilmezse oturum düşer


def _cache_key(user_id: int, import_id: str) -> str:
    return f"import_{user_id}_{import_id}"


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """Dosyayı ayrıştırır ve sütun eşleme önerisiyle ilk 10 satırı döner. Henüz hiçbir
    pozisyon oluşturmaz — kullanıcı önizlemeyi onaylayınca /confirm çağrılır."""
    content = await file.read()
    try:
        df = engine.parse_file(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    columns = list(df.columns)
    rows = engine.extract_rows(df)
    mapping = engine.suggest_mapping(columns)

    import_id = uuid.uuid4().hex[:16]
    finance_cache.set(_cache_key(user_id, import_id), {"columns": columns, "rows": rows})

    warnings: List[str] = []
    missing_required = [f for f in engine.REQUIRED_FIELDS if not mapping.get(f)]
    if missing_required:
        warnings.append(
            "Şu alanlar otomatik eşlenemedi, lütfen elle seçin: " + ", ".join(missing_required)
        )

    return ImportPreviewResponse(
        import_id=import_id,
        columns=columns,
        row_count=len(rows),
        preview_rows=rows[:10],
        suggested_mapping=mapping,
        warnings=warnings,
    )


@router.post("/confirm", response_model=ImportConfirmResponse)
def confirm_import(
    req: ImportConfirmRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Önizlemedeki satırları, kullanıcının onayladığı eşlemeyle gerçek pozisyonlara çevirir.
    Ayrıştırılamayan/eksik satırlar atlanır ve nedeniyle raporlanır — hiçbiri tahminle
    doldurulmaz. Aynı import_id ile ikinci kez çağrılamaz (tek kullanımlık, cache silinir)."""
    cache_key = _cache_key(user_id, req.import_id)
    cached = finance_cache.get(cache_key, ttl=_IMPORT_TTL)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="İçe aktarma oturumunun süresi doldu ya da zaten tamamlandı. Lütfen dosyayı tekrar yükleyin."
        )
    rows: List[Dict] = cached["rows"]

    # check_position_limit dependency'siyle aynı kural, ama toplu eklemede "kaç slot
    # kaldı" hesaplanması gerekiyor — tek satırlık kontrol yetersiz.
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    tier = (user.subscription_tier or "FREE").upper()
    remaining_slots = None
    if tier != "ENTERPRISE":
        current_count = db.query(DBPosition).filter(DBPosition.user_id == user_id).count()
        limit = 5 if tier == "FREE" else 50
        remaining_slots = max(0, limit - current_count)

    created = 0
    skipped = 0
    errors: List[ImportRowError] = []

    for idx, row in enumerate(rows):
        if req.row_indices is not None and idx not in req.row_indices:
            continue
        if remaining_slots is not None and created >= remaining_slots:
            errors.append(ImportRowError(row=idx, reason="Plan pozisyon sınırına ulaşıldı"))
            skipped += 1
            continue

        fields, err = engine.build_position_fields(
            row, req.mapping, req.asset_class_default, req.buy_currency_default or "TRY"
        )
        if err:
            errors.append(ImportRowError(row=idx, reason=err))
            skipped += 1
            continue

        try:
            create_position(user_id, PositionCreate(**fields), db=db)
            created += 1
        except Exception as e:
            errors.append(ImportRowError(row=idx, reason=f"Kayıt hatası: {e}"))
            skipped += 1

    finance_cache.invalidate(cache_key)

    if created > 0:
        invalidate_twrr_cache()
        invalidate_portfolio_cache(user_id)

    return ImportConfirmResponse(created=created, skipped=skipped, errors=errors)
