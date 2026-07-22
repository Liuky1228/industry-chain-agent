"""数据库初始化与会话管理"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings
import os

settings = get_settings()
os.makedirs("data", exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    """创建所有数据库表"""
    from app.database_models import Task, Report  # noqa: F401
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
