from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from crud import get_liabilities, create_liability, update_liability, delete_liability
from models import Liability, LiabilityCreate, LiabilityUpdate
from dependencies import get_current_user_id, get_db

router = APIRouter(prefix="/api/liabilities", tags=["Liabilities"])

@router.get("", response_model=List[Liability])
def list_liabilities(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Kullanıcının borçlarını listele"""
    rows = get_liabilities(user_id, db=db)
    return [Liability(**r) for r in rows]

@router.post("", response_model=Liability)
def add_liability(
    item: LiabilityCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Yeni borç kaydı ekle"""
    row = create_liability(user_id, item, db=db)
    return Liability(**row)

@router.put("/{item_id}", response_model=Liability)
def update_liab(
    item_id: int,
    item: LiabilityUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Borç kaydı güncelle"""
    row = update_liability(user_id, item_id, item, db=db)
    if not row:
        raise HTTPException(status_code=404, detail="Liability record not found")
    return Liability(**row)

@router.delete("/{item_id}")
def remove_liability(
    item_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Borç kaydı sil"""
    success = delete_liability(user_id, item_id, db=db)
    if not success:
        raise HTTPException(status_code=404, detail="Liability record not found")
    return {"message": "Liability record deleted successfully"}
