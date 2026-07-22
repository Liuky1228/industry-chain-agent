"""LLM 公共工具：异常类型与可复用辅助函数"""

import logging
import re

logger = logging.getLogger(__name__)


class LLMQuotaExceeded(Exception):
    """LLM API 配额/余额耗尽（429），不应继续重试。

    所有直接调用 OpenAI API 的模块都应捕获 RateLimitError 并抛出此异常，
    以便上层 pipeline 能立即终止并给用户清晰的错误提示。
    """
    pass


def raise_quota_error(exc: Exception) -> None:
    """将 openai RateLimitError 转换为 LLMQuotaExceeded 并抛出。

    提取可读的错误消息，方便用户排查。
    """
    msg = str(exc)
    m = re.search(r"'message':\s*'([^']+)'", msg)
    readable = m.group(1) if m else msg
    raise LLMQuotaExceeded(f"LLM API 配额错误: {readable}") from exc
