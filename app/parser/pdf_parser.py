"""PDF 解析模块

使用 pdfplumber 提取文本和表格，pymupdf 作为降级方案。
"""

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedReport:
    """解析后的研报数据"""
    pdf_path: str
    full_text: str
    tables: list[dict] = field(default_factory=list)
    page_count: int = 0
    parse_error: str | None = None

    @property
    def text_length(self) -> int:
        return len(self.full_text)

    @property
    def is_valid(self) -> bool:
        return self.text_length > 500 and self.parse_error is None


def extract_with_pdfplumber(pdf_path: str) -> ParsedReport:
    """
    使用 pdfplumber 提取 PDF 文本和表格

    pdfplumber 对中文 PDF 和表格的提取效果较好
    """
    import pdfplumber

    full_text = ""
    tables = []
    page_count = 0

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                # 提取文本
                page_text = page.extract_text() or ""
                if page_text.strip():
                    full_text += page_text + "\n\n"

                # 提取表格
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table and len(table) > 1:
                        tables.append({
                            "page": i + 1,
                            "headers": table[0] if table[0] else [],
                            "rows": table[1:],
                        })

        # 文本清洗
        full_text = _clean_text(full_text)

        return ParsedReport(
            pdf_path=pdf_path,
            full_text=full_text,
            tables=tables,
            page_count=page_count,
        )

    except Exception as e:
        logger.error(f"pdfplumber 解析失败 ({pdf_path}): {e}")
        return ParsedReport(
            pdf_path=pdf_path,
            full_text="",
            parse_error=f"pdfplumber error: {str(e)}",
        )


def extract_with_pymupdf(pdf_path: str) -> ParsedReport:
    """
    使用 pymupdf (fitz) 提取 PDF 文本

    作为 pdfplumber 的降级方案，速度更快但表格提取能力较弱
    """
    import fitz

    full_text = ""
    page_count = 0

    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)

        for page in doc:
            text = page.get_text("text")
            if text.strip():
                full_text += text + "\n\n"

        doc.close()
        full_text = _clean_text(full_text)

        return ParsedReport(
            pdf_path=pdf_path,
            full_text=full_text,
            page_count=page_count,
        )

    except Exception as e:
        logger.error(f"pymupdf 解析失败 ({pdf_path}): {e}")
        return ParsedReport(
            pdf_path=pdf_path,
            full_text="",
            parse_error=f"pymupdf error: {str(e)}",
        )


def parse_pdf(pdf_path: str) -> ParsedReport:
    """
    解析 PDF 文件，自动选择解析器

    优先使用 pdfplumber，失败则降级到 pymupdf
    """
    if not os.path.exists(pdf_path):
        return ParsedReport(
            pdf_path=pdf_path,
            full_text="",
            parse_error=f"文件不存在: {pdf_path}",
        )

    # 优先 pdfplumber
    result = extract_with_pdfplumber(pdf_path)
    if result.is_valid:
        logger.info(
            f"pdfplumber 解析成功: {os.path.basename(pdf_path)} "
            f"({result.page_count}页, {result.text_length}字符)"
        )
        return result

    # 降级到 pymupdf
    logger.info(f"pdfplumber 结果不佳，尝试 pymupdf: {os.path.basename(pdf_path)}")
    result = extract_with_pymupdf(pdf_path)
    if result.is_valid:
        logger.info(
            f"pymupdf 解析成功: {os.path.basename(pdf_path)} "
            f"({result.page_count}页, {result.text_length}字符)"
        )
        return result

    logger.warning(f"PDF 解析失败: {pdf_path}")
    return result


def _clean_text(text: str) -> str:
    """清洗研报文本"""
    import re

    # 移除常见页眉页脚
    noise_patterns = [
        r"请务必阅读正文之后的.*?免责声明.*",
        r"免责声明.*?(?=\n\n|\Z)",
        r"第\s*\d+\s*页\s*共\s*\d+\s*页",
        r"-?\s*\d+\s*-",  # 页码
        r"本公司具备证券投资咨询业务资格.*",
    ]

    for pattern in noise_patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL)

    # 合并连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 移除行首行尾空白
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def smart_chunk(text: str, max_chars: int = 50000, overlap: int = 500) -> list[str]:
    """
    智能文本分段

    按段落边界分段，每段不超过 max_chars 字符，段间有 overlap 字符重叠

    Args:
        text: 原始文本
        max_chars: 每段最大字符数
        overlap: 段间重叠字符数
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            # 保留重叠部分
            current_chunk = current_chunk[-overlap:] + "\n\n" + para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks
