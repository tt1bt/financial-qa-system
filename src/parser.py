"""文档解析：PDF / HTML / TXT → 纯文本

设计取舍：优先走 HTML（东方财富等财经门户的财报文本页），
避开 PDF 解析的三大坑——表格错乱、双栏串行、扫描件无文本层。
PDF 仅作为兜底方案。
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup


# --- 通用清洗 ---

_WS_RE = re.compile(r"[ \t\u3000]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """归一化空白：合并空格、压缩空行、去掉页眉页脚残留"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    # 去掉孤立的页码行（如 "12" / "- 12 -" / "第 12 页"）
    text = re.sub(r"^\s*[-—]?\s*\d{1,3}\s*[-—]?\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*第\s*\d{1,3}\s*页\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def parse_html(path: Path) -> str:
    """解析 HTML 财报页，剔除导航/脚本/样式，保留正文段落"""
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "lxml")

    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "iframe"]):
        tag.decompose()

    # 优先找正文容器，找不到就取全 body
    main = (
        soup.find("div", class_=re.compile(r"content|article|detail|main", re.I))
        or soup.find("article")
        or soup.body
        or soup
    )

    # 用换行拼接块级元素，保住段落边界（后续分块依赖它）
    parts = [el.get_text(" ", strip=True) for el in main.find_all(["p", "div", "tr", "h1", "h2", "h3", "li"])]
    parts = [p for p in parts if p]
    return clean_text("\n".join(parts))


def parse_pdf(path: Path) -> str:
    """PDF 兜底解析。注意：表格会串行，仅在没有 HTML 源时使用。"""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if txt.strip():
                pages.append(txt)
    return clean_text("\n\n".join(pages))


def parse_txt(path: Path) -> str:
    return clean_text(path.read_text(encoding="utf-8", errors="ignore"))


def parse_document(path: Path) -> str:
    """按扩展名分发解析器"""
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return parse_html(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix in (".txt", ".md"):
        return parse_txt(path)
    raise ValueError(f"不支持的格式: {suffix} ({path.name})")


# --- 财报章节识别 ---

# 中文财报的典型章节标题，用于语义分块
SECTION_PATTERNS = [
    r"第[一二三四五六七八九十]+节\s*.{0,30}",
    r"第[一二三四五六七八九十]+章\s*.{0,30}",
    r"[一二三四五六七八九十]+、\s*.{0,25}",
    r"（[一二三四五六七八九十]+）\s*.{0,25}",
]


def split_by_section(text: str) -> list[tuple[str, str]]:
    """按财报章节结构切分，返回 [(章节标题, 正文), ...]

    财报有明确层级（如"第三节 管理层讨论与分析"），按标题切分
    能避免"营收数据"和"风险提示"被切进同一个 chunk 导致检索串台。
    """
    pattern = re.compile("|".join(f"({p})" for p in SECTION_PATTERNS))
    lines = text.split("\n")

    sections: list[tuple[str, list[str]]] = []
    cur_title = "正文"
    cur_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # 短行且能匹配章节模式 → 判定为新章节标题
        is_heading = (
            stripped
            and len(stripped) <= 40
            and pattern.match(stripped)
            and not stripped.endswith("。")
        )
        if is_heading:
            if cur_lines:
                sections.append((cur_title, cur_lines))
            cur_title = stripped
            cur_lines = []
        else:
            cur_lines.append(line)

    if cur_lines:
        sections.append((cur_title, cur_lines))

    out: list[tuple[str, str]] = []
    for title, body_lines in sections:
        body_text = "\n".join(body_lines).strip()
        if body_text:
            out.append((title, body_text))
    return out


def load_documents(raw_dir: Path) -> list[dict]:
    """加载 raw_dir 下所有文档

    Returns:
        [{"text": str, "source": str, "path": str}, ...]
    """
    docs: list[dict] = []
    exts = {".html", ".htm", ".pdf", ".txt", ".md"}
    files = sorted(p for p in raw_dir.rglob("*") if p.suffix.lower() in exts)

    for path in files:
        try:
            text = parse_document(path)
        except Exception as exc:  # 单个文件失败不该中断整批
            print(f"[跳过] {path.name}: {exc}")
            continue
        if len(text) < 100:
            print(f"[跳过] {path.name}: 内容过短({len(text)}字)")
            continue
        docs.append({"text": text, "source": path.name, "path": str(path)})

    return docs
