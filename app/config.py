"""应用配置管理"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Qwen3.7-Plus (OpenAI-compatible) — 字段名保留 deepseek_* 以兼容旧代码
    deepseek_api_key: str = ""  # 必须在 .env 中填写你自己的密钥，切勿硬编码提交
    deepseek_base_url: str = "https://coding.dashscope.aliyuncs.com/v1"
    deepseek_model: str = "qwen3.7-plus"

    # 数据库
    database_url: str = "sqlite:///./data/industry_chain.db"

    # 爬虫
    crawl_delay_seconds: int = 3
    max_reports_per_task: int = 60
    report_date_range_days: int = 365

    # 路径
    pdf_dir: str = "data/pdfs"
    report_dir: str = "data/reports"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
