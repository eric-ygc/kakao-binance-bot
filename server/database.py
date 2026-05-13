"""SQLAlchemy 데이터베이스 세션 관리"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_columns():
    """기존 테이블에 새 컬럼 추가 (없으면 무시)"""
    migrations = [
        ("computer_status", "recent_logs", "TEXT DEFAULT '[]'"),
        ("computer_status", "recent_errors", "TEXT DEFAULT '[]'"),
        ("computer_status", "agent_version", "TEXT DEFAULT ''"),
        ("screenshots", "computer_id", None),  # 새 테이블 체크용
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            if col_type is None:
                continue
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
            except Exception:
                pass  # 이미 존재하면 무시


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_columns()
