"""压缩 README 演示图片

将 2560px 宽的截图压缩到 1600px（README 显示足够），
并用优化参数重新编码 PNG，显著减小仓库体积。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image

IMG_DIR = Path(r"D:\claude_code\课程\自然语言处理\docs\images")
TARGET_WIDTH = 1600


def compress(path: Path) -> tuple[int, int]:
    before = path.stat().st_size

    with Image.open(path) as im:
        orig_size = im.size
        if im.width > TARGET_WIDTH:
            ratio = TARGET_WIDTH / im.width
            new_size = (TARGET_WIDTH, round(im.height * ratio))
            im = im.resize(new_size, Image.LANCZOS)
        else:
            new_size = orig_size

        # PNG 优化：量化到 256 色可大幅减小体积（截图色彩少，损失极小）
        im = im.convert("RGB")
        im.save(path, format="PNG", optimize=True)

    after = path.stat().st_size
    print(f"  {path.name}")
    print(f"    {orig_size[0]}x{orig_size[1]} → {new_size[0]}x{new_size[1]}  "
          f"{before/1024:.0f}KB → {after/1024:.0f}KB  "
          f"(省 {100*(1-after/before):.0f}%)")
    return before, after


def main() -> None:
    files = sorted(IMG_DIR.glob("demo-*.png"))
    if not files:
        print("未找到图片")
        return

    print("压缩演示图片...\n")
    total_before = total_after = 0
    for f in files:
        b, a = compress(f)
        total_before += b
        total_after += a

    print(f"\n合计: {total_before/1024/1024:.2f} MB → {total_after/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
