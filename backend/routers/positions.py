from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import Position, PositionCreate, PositionUpdate
from crud import (
    get_positions, get_position_by_id, create_position,
    update_position, delete_position
)
from services import invalidate_twrr_cache, invalidate_portfolio_cache
from dependencies import get_current_user_id, get_db, check_position_limit

router = APIRouter(prefix="/api/positions", tags=["Positions"])

@router.get("", response_model=List[Position])
def list_positions(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Tüm pozisyonları listele"""
    positions = get_positions(user_id, db=db)
    return [Position(**p) for p in positions]

@router.post("", response_model=Position)
def add_position(
    pos: PositionCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    _limit_guard: None = Depends(check_position_limit)
):
    """Yeni pozisyon ekle"""
    invalidate_twrr_cache()
    invalidate_portfolio_cache()
    return create_position(user_id, pos, db=db)

@router.get("/{position_id}", response_model=Position)
def get_pos(
    position_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Belirli pozisyonu al"""
    pos = get_position_by_id(user_id, position_id, db=db)
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    return Position(**pos)

@router.put("/{position_id}", response_model=Position)
def update_pos(
    position_id: int,
    update: PositionUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Pozisyon güncelle"""
    invalidate_twrr_cache()
    invalidate_portfolio_cache()
    updated = update_position(user_id, position_id, update, db=db)
    if not updated:
        raise HTTPException(status_code=404, detail="Position not found")
    return Position(**updated)

@router.delete("/{position_id}")
def remove_pos(
    position_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Pozisyon sil"""
    invalidate_twrr_cache()
    invalidate_portfolio_cache()
    success = delete_position(user_id, position_id, db=db)
    if not success:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"message": "Position deleted"}
