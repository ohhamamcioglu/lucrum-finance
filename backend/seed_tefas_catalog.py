import os
import sqlite3
import time
from datetime import date, timedelta
from pytefas import Crawler

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "twelve_data.db")

def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def seed_tefas():
    print("Initializing TEFAS Crawler...")
    crawler = Crawler()
    today = date.today()
    start = today - timedelta(days=7)
    
    print(f"Fetching TEFAS data from {start} to {today}...")
    try:
        df = crawler.fetch_many(start.isoformat(), today.isoformat(), kinds=("YAT",))
    except Exception as e:
        print(f"Error fetching data from TEFAS: {e}")
        return

    if df.empty:
        print("No TEFAS data retrieved.")
        return
        
    print(f"Retrieved {len(df)} price history rows.")
    
    # 1. Unique Funds Catalog
    unique_funds = df[["fund_code", "fund_name", "kind"]].drop_duplicates("fund_code")
    ts = time.time()
    
    conn = _conn()
    c = conn.cursor()
    
    print(f"Writing {len(unique_funds)} funds to td_tefas_funds table...")
    funds_inserted = 0
    for _, row in unique_funds.iterrows():
        try:
            # Fix encoding issues in names if any
            name = str(row["fund_name"])
            c.execute("""
                INSERT OR REPLACE INTO td_tefas_funds (fund_code, fund_name, kind, fetched_at)
                VALUES (?, ?, ?, ?)
            """, (row["fund_code"], name, row["kind"], ts))
            funds_inserted += 1
        except Exception as e:
            print(f"Failed to insert fund {row['fund_code']}: {e}")
            
    # 2. Historical price snapshots
    print(f"Writing {len(df)} historical snapshots to td_tefas_nav table...")
    navs_inserted = 0
    for _, row in df.iterrows():
        try:
            c.execute("""
                INSERT OR REPLACE INTO td_tefas_nav 
                (fund_code, dt, price, shares_outstanding, investor_count, portfolio_size, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                row["fund_code"],
                str(row["date"]),
                float(row["price"]) if row["price"] is not None else None,
                float(row["shares_outstanding"]) if row["shares_outstanding"] is not None else None,
                int(row["investor_count"]) if row["investor_count"] is not None else None,
                float(row["portfolio_size"]) if row["portfolio_size"] is not None else None,
                ts
            ))
            navs_inserted += 1
        except Exception as e:
            pass
            
    conn.commit()
    conn.close()
    
    print(f"\nSeeding complete!")
    print(f"Total funds seeded in catalog: {funds_inserted}")
    print(f"Total price histories seeded: {navs_inserted}")

if __name__ == "__main__":
    seed_tefas()
