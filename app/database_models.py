"""数据库 ORM 模型"""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    industry_name = Column(String(200), nullable=False)
    status = Column(String(50), default="pending")
    progress = Column(Integer, default=0)
    progress_message = Column(Text, default="")
    result_json = Column(Text, nullable=True)
    report_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    reports = relationship("Report", back_populates="task", cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())[:12])
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    title = Column(Text)
    stock_name = Column(String(100), nullable=True)
    stock_code = Column(String(20), nullable=True)
    publish_date = Column(String(20), nullable=True)
    source = Column(String(50))  # eastmoney / cninfo
    report_type = Column(String(50))  # industry / stock / announcement
    pdf_url = Column(Text)
    info_code = Column(String(100), nullable=True)
    local_path = Column(String(500), nullable=True)
    parse_status = Column(String(50), default="pending")  # pending / parsed / failed
    extracted_json = Column(Text, nullable=True)

    task = relationship("Task", back_populates="reports")
