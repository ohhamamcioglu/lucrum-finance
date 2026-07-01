import os
import json
from datetime import datetime, date
from sqlalchemy.orm import Session
from auth import get_password_hash
from db_models import (
    engine, Base, SessionLocal, DBUser, DBPosition, DBTransaction
)

HOLDINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings_full.json")

def init_database():
    """Veritabanı tablolarını siler ve ORM modellerini kullanarak yeniden oluşturur."""
    print("Recreating database schema via SQLAlchemy ORM...")
    
    # SQLite specific file removal if applicable
    db_url = str(engine.url)
    if db_url.startswith("sqlite:///"):
        db_file = db_url.replace("sqlite:///", "")
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
                print(f"Removed local SQLite database: {db_file}")
            except Exception as e:
                print(f"Warning: Could not delete SQLite file: {e}")

    # Recreate tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Add default user (id=1)
    session = SessionLocal()
    try:
        hashed_pwd = get_password_hash("demo123")
        demo_user = DBUser(
            id=1,
            email="demo@lucrum.finance",
            name="Demo User",
            password_hash=hashed_pwd,
            currency="TRY"
        )
        session.add(demo_user)
        session.commit()
        print("Database schema created successfully.")
    except Exception as e:
        session.rollback()
        print(f"Error seeding default user: {e}")
        raise e
    finally:
        session.close()

def load_holdings_to_db():
    """holdings_full.json dosyasını okur ve varsayılan pozisyonları yükler."""
    print("Loading holdings to database via ORM...")
    if not os.path.exists(HOLDINGS_FILE):
        print(f"Holdings file not found: {HOLDINGS_FILE}")
        return
        
    with open(HOLDINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    holdings = data.get("holdings", [])
    session = SessionLocal()
    
    try:
        for h in holdings:
            ticker = h["ticker"].upper().strip()
            asset_class = h["asset_class"]
            qty = float(h["quantity"])
            price = float(h["buy_price"])
            buy_date = datetime.strptime(h["buy_date"], "%Y-%m-%d").date()
            currency = h["buy_currency"]
            cost_basis = h.get("invested_tl", qty * price)
            
            # 1. Pozisyon ekle
            pos = DBPosition(
                user_id=1,
                ticker=ticker,
                asset_class=asset_class,
                quantity=qty,
                buy_price=price,
                buy_date=buy_date,
                buy_currency=currency,
                cost_basis_tly=cost_basis
            )
            session.add(pos)
            session.flush()  # Populates pos.id for transaction record
            
            # 2. İşlem geçmişi (transaction) ekle
            txn = DBTransaction(
                user_id=1,
                position_id=pos.id,
                ticker=ticker,
                asset_class=asset_class,
                transaction_type="BUY",
                quantity=qty,
                price=price,
                currency=currency,
                transaction_date=buy_date,
                notes="Initial seeding"
            )
            session.add(txn)
            
        session.commit()
        print("Holdings loaded successfully.")
    except Exception as e:
        session.rollback()
        print(f"Error loading holdings: {e}")
        raise e
    finally:
        session.close()

if __name__ == "__main__":
    init_database()
    load_holdings_to_db()
