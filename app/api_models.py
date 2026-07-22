"""API 请求/响应模型"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    industry_name: str
    max_reports: int = 30
    date_range_days: int = 180


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    industry_name: str
    status: str
    progress: int
    progress_message: str
    report_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReportMetaResponse(BaseModel):
    """研报元数据响应"""
    id: str
    title: str
    stock_name: Optional[str]
    stock_code: Optional[str]
    publish_date: Optional[str]
    source: str
    report_type: str
    parse_status: str


class ChainVisualization(BaseModel):
    """产业链可视化数据"""
    categories: list
    nodes: list
    links: list
    chain_flow: str


class TaskDetailResponse(BaseModel):
    """任务详情响应"""
    task: TaskResponse
    reports: list[ReportMetaResponse] = []
    visualization: Optional[ChainVisualization] = None
    summary: Optional[dict] = None
    chain_data: Optional[dict] = None
