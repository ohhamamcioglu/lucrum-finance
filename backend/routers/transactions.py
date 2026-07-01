from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from models import Transaction
from crud import get_transactions, get_transaction_by_id
from dependencies import get_current_user_id, get_db

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])

@router.get("", response_model=List[Transaction])
def list_transactions(
    ticker: Optional[str] = Query(None),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Tüm işlemleri (veya filtreli) listele"""
    txns = get_transactions(user_id, ticker, db=db)
    return [Transaction(**t) for t in txns]

@router.get("/{transaction_id}", response_model=Transaction)
def get_transaction(
    transaction_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Belirli işlemi al"""
    txn = get_transaction_by_id(user_id, transaction_id, db=db)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return Transaction(**txn)
