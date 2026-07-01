"""
Database Connection and Session Management (SQLAlchemy Bridge)
"""
from contextlib import contextmanager
from typing import Generator
from sqlalchemy.orm import Session
from db_models import SessionLocal, engine, Base, get_db

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for SQLAlchemy database sessions.
    Keeps compatibility with legacy code calling with get_db_session().
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

# SQLite raw fallback connection if needed (deprecated)
def get_db_connection():
    """sqlite3 connection (Legacy raw connection fallback)"""
    import sqlite3
    import os
    db_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.db")
    conn = sqlite3.connect(db_file, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn
