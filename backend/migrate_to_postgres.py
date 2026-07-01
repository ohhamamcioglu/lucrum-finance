import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_models import (
    Base, DBUser, DBPosition, DBTransaction, DBPriceHistory, 
    DBExchangeRate, DBPortfolioSnapshot, DBAssetClassSummary, 
    DBPerformanceHistory, DBLiability, DBTargetAllocation, 
    DBPriceAlert, DBNotification
)

def migrate():
    # 1. Source Database (SQLite)
    sqlite_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.db")
    if not os.path.exists(sqlite_db_path):
        print(f"Error: SQLite source database not found at {sqlite_db_path}")
        return
    
    sqlite_url = f"sqlite:///{sqlite_db_path}"
    print(f"Connecting to source SQLite: {sqlite_url}")
    source_engine = create_engine(sqlite_url)
    SourceSession = sessionmaker(bind=source_engine)
    source_db = SourceSession()

    # 2. Target Database (PostgreSQL from env)
    pg_url = os.getenv("DATABASE_URL")
    if not pg_url or not pg_url.startswith(("postgres://", "postgresql://")):
        print("Error: DATABASE_URL environment variable must be set to a valid postgresql:// connection string.")
        print("Example: DATABASE_URL=postgresql://user:password@localhost:5432/lucrum")
        return
        
    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)
        
    print(f"Connecting to target PostgreSQL: {pg_url.split('@')[-1]}")  # Hide credentials in logs
    target_engine = create_engine(pg_url)
    
    # Create tables on target
    print("Creating tables on PostgreSQL if not exist...")
    Base.metadata.create_all(bind=target_engine)
    
    TargetSession = sessionmaker(bind=target_engine)
    target_db = TargetSession()

    # Ordered list of models to migrate to preserve foreign keys
    models_to_migrate = [
        (DBUser, "users"),
        (DBPosition, "positions"),
        (DBTransaction, "transactions"),
        (DBPriceHistory, "price_history"),
        (DBExchangeRate, "exchange_rates"),
        (DBPortfolioSnapshot, "portfolio_snapshots"),
        (DBAssetClassSummary, "asset_class_summaries"),
        (DBPerformanceHistory, "performance_history"),
        (DBLiability, "liabilities"),
        (DBTargetAllocation, "target_allocations"),
        (DBPriceAlert, "price_alerts"),
        (DBNotification, "notifications")
    ]

    try:
        # Clear existing data on target (optional/safe mode)
        print("\nStarting migration...")
        
        for model, name in models_to_migrate:
            # Fetch all from SQLite
            sqlite_records = source_db.query(model).all()
            print(f"Found {len(sqlite_records)} records in SQLite table '{name}'")
            
            if not sqlite_records:
                continue
                
            # Clear target records first to avoid duplicates
            target_db.query(model).delete()
            target_db.flush()
            
            # Map and insert to Postgres
            for record in sqlite_records:
                # Get dictionary of attributes excluding sqlalchemy internals
                attrs = {c.name: getattr(record, c.name) for c in record.__table__.columns}
                
                # Instantiate new target ORM object
                target_record = model(**attrs)
                target_db.add(target_record)
                
            target_db.commit()
            print(f"Successfully migrated {len(sqlite_records)} records to PostgreSQL table '{name}'")
            
        print("\nData migration completed successfully.")
        
        # 3. Reset PostgreSQL sequences to prevent Primary Key conflicts on new inserts
        print("\nResetting PostgreSQL primary key sequence auto-increment counters...")
        for _, name in models_to_migrate:
            try:
                # Find maximum ID
                res = target_db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {name}"))
                max_id = res.scalar()
                
                # Update sequence value to max_id + 1
                seq_name = f"{name}_id_seq"
                target_db.execute(text(f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), :max_val)"), {"max_val": max_id})
                target_db.commit()
                print(f"Reset sequence for table '{name}' to {max_id}")
            except Exception as seq_err:
                # Some tables may not have sequences or already reset
                target_db.rollback()
                pass
                
        print("\nSequence auto-increment counters reset successfully.")
        print("Database migration finalized!")
        
    except Exception as e:
        target_db.rollback()
        print(f"\nMigration failed with error: {e}")
    finally:
        source_db.close()
        target_db.close()

if __name__ == "__main__":
    migrate()
