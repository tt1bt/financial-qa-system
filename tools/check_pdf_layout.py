"""检查 PDF 中的文本是否超出右边距"""
import pdfplumber

PDF = r"data\eval\report_preview.pdf"
MARGIN_PT = 70.9  # 2.5cm

with pdfplumber.open(PDF) as pdf:
    print(f"总页数: {len(pdf.pages)}")
    total_over = 0
    for i, page in enumerate(pdf.pages, 1):
        right_limit = page.width - MARGIN_PT
        words = page.extract_words()
        over = [w for w in words if w["x1"] > right_limit + 2]
        if over:
            total_over += len(over)
            print(f"\n第{i}页: 页面宽{page.width:.0f}pt, 右边界{right_limit:.0f}pt, 溢出{len(over)}个词")
            for w in over[:5]:
                print(f"    '{w['text']}' 结束于 x={w['x1']:.1f}pt")
        # 也检查左边
        left_over = [w for w in words if w["x0"] < MARGIN_PT - 2]
        if left_over:
            print(f"第{i}页: 左侧溢出 {len(left_over)} 个词")

    print(f"\n总溢出词数: {total_over}")
    if total_over == 0:
        print("✓ 无文本溢出，排版正常")
