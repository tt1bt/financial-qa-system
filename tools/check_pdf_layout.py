"""检查 PDF 中的文本是否超出页边距

用法：
    python tools/check_pdf_layout.py <pdf路径> [边距pt]

说明：
PNG 栅格预览存在页面居中偏移，看起来像文字截断，实际可能是渲染偏差。
本脚本直接读 PDF 中每个词的坐标，与边距比较，是判断排版是否真实溢出的可靠方法。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 避免中文/符号输出报错
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pdfplumber


def check(pdf_path: str, margin_pt: float) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"文件: {pdf_path}")
        print(f"总页数: {len(pdf.pages)}")
        print(f"边距设定: {margin_pt}pt ({margin_pt/28.35:.1f}cm)")
        print()

        total_over = 0
        for i, page in enumerate(pdf.pages, 1):
            right_limit = page.width - margin_pt
            left_limit = margin_pt
            words = page.extract_words()

            over_right = [w for w in words if w["x1"] > right_limit + 2]
            over_left = [w for w in words if w["x0"] < left_limit - 2]

            if over_right:
                total_over += len(over_right)
                print(f"第{i}页: 右侧溢出 {len(over_right)} 个词 "
                      f"(页宽{page.width:.0f}pt, 右边界{right_limit:.0f}pt)")
                for w in over_right[:5]:
                    print(f"    '{w['text']}' 结束于 x={w['x1']:.1f}pt")
            if over_left:
                total_over += len(over_left)
                print(f"第{i}页: 左侧溢出 {len(over_left)} 个词")
                for w in over_left[:5]:
                    print(f"    '{w['text']}' 起始于 x={w['x0']:.1f}pt")

        print()
        print(f"总溢出词数: {total_over}")
        if total_over == 0:
            print("[OK] 无文本溢出，排版正常")
        else:
            print("[WARN] 存在溢出，需调整页边距或内容宽度")
        return total_over


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        # 无参数时用默认文件
        default = Path("data/eval/report_preview.pdf")
        if default.exists():
            print(f"使用默认文件: {default}\n")
            check(str(default), 70.9)
        sys.exit(0)

    pdf_path = sys.argv[1]
    margin = float(sys.argv[2]) if len(sys.argv) > 2 else 70.9

    if not Path(pdf_path).exists():
        print(f"[ERROR] 文件不存在: {pdf_path}")
        sys.exit(1)

    n = check(pdf_path, margin)
    sys.exit(1 if n else 0)


if __name__ == "__main__":
    main()
