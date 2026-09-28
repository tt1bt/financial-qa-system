"""数据采集：从公开财经门户抓取上市公司年报文本

策略：优先走 HTML（避开 PDF 解析的三大坑），
本脚本提供两种模式：
  1. from-url   —— 给定财报文本页 URL，抓取正文
  2. from-dir   —— 批量解析本地 PDF/HTML 到纯文本

用法：
    python -m src.collect --url "https://..." --company 贵州茅台 --year 2023
    python -m src.collect --scan            # 扫描 data/raw 下的 PDF，转成 txt
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .config import RAW_DIR
from .parser import clean_text, parse_document

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def fetch_url(url: str) -> str:
    """抓取网页正文，剔除导航/脚本/广告"""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.encoding = resp.apparent_encoding or "utf-8"
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript",
                     "iframe", "aside", "form"]):
        tag.decompose()

    main = (
        soup.find("div", id=re.compile(r"content|detail|article|main", re.I))
        or soup.find("div", class_=re.compile(r"content|detail|article|main", re.I))
        or soup.find("article")
        or soup.body
        or soup
    )

    blocks = [
        el.get_text(" ", strip=True)
        for el in main.find_all(["p", "div", "h1", "h2", "h3", "tr", "li"])
    ]
    blocks = [b for b in blocks if len(b) > 20]  # 过滤导航碎片
    return clean_text("\n".join(blocks))


def save_text(text: str, company: str, year: str, doc_type: str = "年度报告") -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{company}{year}年{doc_type}.txt"
    path = RAW_DIR / name
    path.write_text(text, encoding="utf-8")
    print(f"✓ 已保存 {path}  ({len(text)} 字)")
    return path


def scan_local() -> None:
    """把 data/raw 下的 PDF/HTML 解析成同名 txt，便于人工检查解析质量"""
    exts = {".pdf", ".html", ".htm"}
    files = [p for p in RAW_DIR.rglob("*") if p.suffix.lower() in exts]
    if not files:
        print(f"✗ {RAW_DIR} 下没有 PDF/HTML 文件")
        return

    for path in files:
        try:
            text = parse_document(path)
        except Exception as exc:
            print(f"✗ {path.name}: {exc}")
            continue
        out = path.with_suffix(".txt")
        out.write_text(text, encoding="utf-8")
        preview = text[:150].replace("\n", " ")
        print(f"✓ {path.name} → {out.name} ({len(text)} 字)")
        print(f"  预览: {preview}...")


def check_quality() -> None:
    """抽查已有 txt 的解析质量：字数、章节识别情况、表格残留"""
    from .parser import split_by_section

    files = sorted(RAW_DIR.glob("*.txt"))
    if not files:
        print(f"✗ {RAW_DIR} 下没有 txt 文件")
        return

    print(f"检查 {len(files)} 个文件：\n")
    for path in files:
        text = path.read_text(encoding="utf-8")
        sections = split_by_section(text)
        print(f"📄 {path.name}")
        print(f"   字数: {len(text):,}")
        print(f"   识别章节: {len(sections)} 个")
        if sections:
            for title, _ in sections[:4]:
                print(f"     · {title}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="年报数据采集")
    parser.add_argument("--url", help="财报文本页 URL")
    parser.add_argument("--company", default="", help="公司简称")
    parser.add_argument("--year", default="", help="年份")
    parser.add_argument("--doc-type", default="年度报告", help="文档类型")
    parser.add_argument("--scan", action="store_true", help="解析本地 PDF/HTML 为 txt")
    parser.add_argument("--check", action="store_true", help="检查解析质量")
    args = parser.parse_args()

    if args.scan:
        scan_local()
    elif args.check:
        check_quality()
    elif args.url:
        print(f"抓取: {args.url}")
        text = fetch_url(args.url)
        if len(text) < 200:
            print(f"✗ 正文过短({len(text)}字)，可能被反爬或页面结构变了")
            sys.exit(1)
        company = args.company or "未知公司"
        year = args.year or "未知年份"
        save_text(text, company, year, args.doc_type)
    else:
        parser.print_help()
        print("\n提示：")
        print("  1. 到巨潮资讯网下载年报 PDF，放进 data/raw/，然后 --scan")
        print("  2. 或直接抓东方财富的财报文本页，用 --url")


if __name__ == "__main__":
    main()
