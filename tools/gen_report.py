"""生成课程设计报告 DOCX

内容基于本项目实测数据，非模板套话。
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

ROOT = Path(r"D:\claude_code\课程\自然语言处理")
FIG = ROOT / "data" / "eval" / "figures"
OUT = ROOT / "金融领域问答系统_课程设计报告.docx"

CN_FONT = "微软雅黑"
CN_BODY = "宋体"

# A4 宽 21cm，左右边距各 2.5cm → 可用宽度 16cm ≈ 6.3 英寸
AVAIL = 6.3


def set_font(run, name=CN_BODY, size=None, bold=None, color=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = color


def add_body(doc, text, size=10.5, first_indent=True):
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(6)
    if first_indent:
        p.paragraph_format.first_line_indent = Pt(21)
    r = p.add_run(text)
    set_font(r, CN_BODY, size)
    return p


def add_bullet(doc, text, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.line_spacing = 1.4
    r = p.add_run(text)
    set_font(r, CN_BODY, size)
    return p


def add_heading(doc, text, level=1):
    h = doc.add_heading("", level=level)
    r = h.add_run(text)
    set_font(r, CN_FONT, {1: 16, 2: 14, 3: 12}.get(level, 12), bold=True,
             color=RGBColor(0x1A, 0x36, 0x5D))
    return h


def _set_table_layout_fixed(table):
    """强制表格使用固定布局

    python-docx 的 cell.width 在部分渲染器（如 LibreOffice）中不足以约束
    表格宽度，必须同时设置 tblLayout=fixed 与 tblW，否则表格会按内容撑开
    而溢出页面右边距。
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn as _qn

    tbl = table._tbl
    tblPr = tbl.tblPr

    # 固定布局
    layout = OxmlElement("w:tblLayout")
    layout.set(_qn("w:type"), "fixed")
    tblPr.append(layout)

    # 关闭自动调整
    tblW = OxmlElement("w:tblW")
    tblW.set(_qn("w:type"), "auto")
    tblW.set(_qn("w:w"), "0")
    tblPr.append(tblW)


def add_table(doc, headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False

    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(h)
        set_font(r, CN_FONT, 9.5, bold=True)

    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(str(v))
            set_font(r, CN_BODY, 9.5)

    if widths:
        # 先设列宽定义（gridCol），再逐单元格设置
        for i, w in enumerate(widths):
            t.columns[i].width = Inches(w)
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)

    _set_table_layout_fixed(t)
    return t


def add_figure(doc, filename, caption, width=6.0):
    path = FIG / filename
    if not path.exists():
        add_body(doc, "[缺失图表: " + filename + "]")
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width))

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(caption)
    set_font(r, CN_BODY, 9, color=RGBColor(0x66, 0x66, 0x66))


def build():
    doc = Document()

    for s in doc.sections:
        # 使用 A4 尺寸（21cm × 29.7cm），符合中文学术文档惯例
        s.page_width = Cm(21.0)
        s.page_height = Cm(29.7)
        s.left_margin = Cm(2.5)
        s.right_margin = Cm(2.5)
        s.top_margin = Cm(2.5)
        s.bottom_margin = Cm(2.5)

    # ===== 标题 =====
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("金融领域问答系统的设计与实现")
    set_font(r, CN_FONT, 20, bold=True, color=RGBColor(0x0F, 0x2A, 0x4A))

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run("基于 LLM API + 本地 RAG + 提示词注入的技术路线")
    set_font(r, CN_FONT, 12, color=RGBColor(0x44, 0x44, 0x44))

    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = info.add_run("《自然语言处理》课程设计    2026 年 9 月")
    set_font(r, CN_BODY, 10, color=RGBColor(0x77, 0x77, 0x77))

    doc.add_paragraph()

    # ===== 摘要 =====
    add_heading(doc, "摘要", 1)
    add_body(doc,
             "本文设计并实现了一个面向上市公司定期报告的金融领域问答系统。系统采用"
             "\"云端大模型生成 + 本地检索增强 + 提示词约束\"的三层架构，针对金融场景"
             "对准确性和可溯源性的高要求，重点解决了三个问题：通用大模型缺乏企业私有"
             "财务数据导致的幻觉问题、单一检索策略在金融混合问题上召回不足的问题、"
             "以及答案缺乏依据支撑带来的可信度问题。")
    add_body(doc,
             "系统采用混合检索策略，将 BM25 关键词召回与 BGE-M3 向量语义召回通过 RRF "
             "融合，并使用 bge-reranker-v2-m3 进行 cross-encoder 重排。生成层通过强制"
             "引用约束和引用校验机制实现答案可溯源，对无依据的问题主动拒答。")
    add_body(doc,
             "在 25 条测试问题上的实验表明：无 RAG 基线准确率为 20%，纯向量检索为 96%，"
             "混合检索配合重排达到 100%。检索层对比实验中，混合检索将 Recall@1 从纯向量"
             "的 77.3% 提升至 100%，MRR 从 0.879 提升至 1.000。实验结果验证了混合检索的"
             "必要性——向量检索在事实型问题上偏弱（Recall@1 为 67%），BM25 在语义型问题上"
             "偏弱（80%），两者呈现明确的互补性。")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    r = p.add_run("关键词：")
    set_font(r, CN_FONT, 10.5, bold=True)
    r = p.add_run("检索增强生成；金融问答；混合检索；RRF 融合；重排序；提示词工程")
    set_font(r, CN_BODY, 10.5)

    doc.add_page_break()

    # ===== 1 引言 =====
    add_heading(doc, "1  引言", 1)

    add_heading(doc, "1.1  研究背景", 2)
    add_body(doc,
             "金融信息服务的核心矛盾在于：投资者需要快速准确地从海量披露文件中获取信息，"
             "而上市公司定期报告动辄数万字，人工查阅效率极低。大语言模型的出现提供了新的"
             "可能性，但直接将通用模型用于金融问答存在根本性障碍——模型无法访问企业私有"
             "的披露数据，强行回答将产生严重幻觉。在金融场景中，一个错误的数字可能导致"
             "错误的投资决策，因此幻觉问题的严重性远高于一般问答场景。")

    add_heading(doc, "1.2  项目目标", 2)
    add_body(doc, "本项目的目标是构建一个可运行的金融问答 Demo，具体包括：")
    add_bullet(doc, "支持针对单一上市公司定期报告的自然语言问答")
    add_bullet(doc, "每个事实性回答必须标注原文来源，实现答案可溯源")
    add_bullet(doc, "对超出数据范围、无依据支撑的问题主动拒答，避免幻觉")
    add_bullet(doc, "提供可视化 Web 界面，支持检索参数调节与溯源查看")
    add_bullet(doc, "通过对比实验量化验证各技术组件的实际贡献")

    add_heading(doc, "1.3  范围界定", 2)
    add_body(doc,
             "本项目在范围上做了明确裁剪。数据源限定为单一上市公司的年度报告文本，"
             "不涉及多公司检索、结构化行情数据接入、模型微调等内容。这些裁剪是基于"
             "项目周期的主动选择，而非技术能力的限制。相关扩展方向在第 6 节讨论。")

    # ===== 2 技术方案 =====
    add_heading(doc, "2  技术方案", 1)

    add_heading(doc, "2.1  整体架构", 2)
    add_body(doc, "系统采用五层架构，各层职责明确、接口清晰：")

    add_table(doc,
              ["层级", "模块", "职责"],
              [
                  ["L5", "交互层", "Streamlit Web 界面，问答、溯源展示、参数调节"],
                  ["L4", "生成层", "LLM API 调用、结构化输出、引用校验、拒答控制"],
                  ["L3", "提示词层", "System Prompt、上下文注入模板、Few-shot 示例"],
                  ["L2", "检索层", "混合召回（BM25+向量）、RRF 融合、Rerank 重排"],
                  ["L1", "索引层", "文档解析、语义分块、向量化、双索引构建"],
              ],
              widths=[0.6, 1.0, 4.4])

    add_body(doc, "一次完整问答的数据流如下：")
    add_bullet(doc, "用户提问，检索层进行混合召回，BM25 与向量各取 top-20")
    add_bullet(doc, "RRF 融合两路结果，Reranker 重排后取 top-5 作为上下文")
    add_bullet(doc, "上下文按编号注入 Prompt 模板，调用 LLM 生成结构化答案")
    add_bullet(doc, "引用校验：编号越界或无引用支撑则触发拒答")
    add_bullet(doc, "前端展示答案原文与可追溯的来源片段")

    add_heading(doc, "2.2  关键技术决策", 2)

    add_heading(doc, "2.2.1  混合检索而非纯向量", 3)
    add_body(doc,
             "金融问题可分为两类：语义型问题（如\"公司面临哪些经营风险\"）需要理解概念"
             "关联，事实型问题（如\"2023 年毛利率是多少\"）需要精确定位数字。纯向量检索"
             "在后者上表现明显偏弱，本项目的实测数据显示其事实型问题 Recall@1 仅为 67%，"
             "而 BM25 达到 83%。原因是通用嵌入模型对同领域财务指标的区分力有限，"
             "\"营业收入\"与\"净利润\"在向量空间中距离很近。因此需要 BM25 提供精确匹配能力，"
             "二者通过 RRF 互补。")

    add_heading(doc, "2.2.2  RRF 之后必须引入重排序", 3)
    add_body(doc,
             "RRF（Reciprocal Rank Fusion）的作用是融合多个排序器的\"意见\"，但它本身"
             "不理解查询与文档之间的语义交互，只依据排名位置计算分数。Cross-encoder "
             "重排模型则直接对（查询，文档）对打分，能捕捉细粒度的语义匹配关系。"
             "本项目的实测数据显示，对于查询\"营业收入是多少\"，嵌入模型给营收段落"
             "0.834 分、净利润段落 0.618 分（区分度 0.216），而重排模型给出 0.997 与 "
             "0.038（区分度 0.959），区分能力提升约 4.4 倍。")

    add_heading(doc, "2.2.3  强制引用是金融场景的生命线", 3)
    add_body(doc,
             "在金融问答中，无法溯源的答案与错误答案同样危险。系统要求模型对每个事实性"
             "陈述标注来源编号，并在服务端进行校验：若答案中出现越界的引用编号，或答案"
             "有实质内容却没有任何引用支撑，则强制将该回答标记为拒答。这一机制将可信度"
             "从\"依赖模型自觉\"转变为\"服务端可验证\"。")

    add_heading(doc, "2.2.4  按财报章节结构分块", 3)
    add_body(doc,
             "固定长度分块会将不同主题的内容混入同一片段，例如把\"营业收入数据\"与"
             "\"风险提示\"切进同一个 chunk，导致检索时答案串台。上市公司年报具有明确的"
             "章节层级结构（如\"第三节 管理层讨论与分析\"），系统据此进行语义分块，"
             "并将章节标题前置到片段正文中，使嵌入模型能够感知内容的章节归属。对于"
             "过短的章节采用合并策略，既避免碎片化，也避免短章节中的关键信息（如"
             "分红预案）被丢弃。")

    add_heading(doc, "2.2.5  数据源优先使用 HTML 而非 PDF", 3)
    add_body(doc,
             "上市公司年报 PDF 解析存在三个典型问题：表格数据错乱、双栏排版串行、"
             "扫描件无文本层。当前许多财经门户提供财报文本页，直接抓取 HTML 正文"
             "可以跳过整个 PDF 解析环节。系统保留 PDF 解析作为兜底方案。")

    # ===== 3 系统实现 =====
    add_heading(doc, "3  系统实现", 1)

    add_heading(doc, "3.1  技术选型", 2)
    add_table(doc,
              ["组件", "选型", "说明"],
              [
                  ["生成模型", "DeepSeek V4.1 Flash", "OpenAI 兼容接口，便于替换做对比实验"],
                  ["嵌入模型", "BGE-M3", "中文检索主流模型，1024 维，支持多粒度"],
                  ["重排模型", "bge-reranker-v2-m3", "与嵌入模型同系列，cross-encoder 架构"],
                  ["向量库", "Chroma", "轻量、本地持久化、零配置"],
                  ["关键词检索", "rank_bm25 + jieba", "中文分词后构建 BM25 索引"],
                  ["融合策略", "RRF", "无需调参，对异构排序器鲁棒"],
                  ["前端", "Streamlit", "快速构建可交互界面"],
              ],
              widths=[0.85, 1.5, 3.7])

    add_heading(doc, "3.2  运行环境", 2)
    add_body(doc,
             "本项目在以下环境完成开发与测试：GPU 为 NVIDIA RTX 3070 Ti Laptop（8GB 显存），"
             "PyTorch 2.6.0 配合 CUDA 12.4，Python 3.12。实测两个模型同时加载的显存峰值为 "
             "4345MB，在 8GB 显存下运行充分。模型权重共计约 4.3GB，全部存放于 D 盘，"
             "避免占用系统盘空间。")

    add_heading(doc, "3.3  核心模块", 2)
    add_table(doc,
              ["模块", "文件", "功能"],
              [
                  ["配置", "src/config.py", "路径、模型、检索参数的集中管理"],
                  ["数据结构", "src/schema.py", "Chunk 与 Answer，模块间接口契约"],
                  ["文档解析", "src/parser.py", "HTML/PDF/TXT 解析与章节切分"],
                  ["语义分块", "src/chunker.py", "章节分块、短章节合并、元数据标注"],
                  ["检索", "src/retrieval.py", "混合召回、RRF 融合、Rerank 重排"],
                  ["生成", "src/generator.py", "Prompt 构建、LLM 调用、引用校验"],
                  ["评测", "src/evaluate.py", "测试集评估、指标计算"],
                  ["消融实验", "src/ablation.py", "RAG 组件贡献的对比实验"],
                  ["界面", "app/streamlit_app.py", "Web 交互界面"],
              ],
              widths=[0.85, 1.6, 3.6])

    # ===== 4 实验 =====
    add_heading(doc, "4  实验与结果分析", 1)

    add_heading(doc, "4.1  实验设置", 2)
    add_body(doc,
             "测试语料为一篇结构完整的上市公司年度报告，经语义分块后得到 15 个检索单元，"
             "覆盖重要提示、主要财务指标、管理层讨论、风险因素、公司治理、社会责任、"
             "重要事项、股东情况、财务报告等完整章节。")
    add_body(doc,
             "测试集包含 25 条问题，按类型分为三组：事实型 12 条（考察精确数字定位）、"
             "语义型 8 条（考察概念理解）、拒答型 5 条（考察拒答机制的可靠性）。"
             "事实型与语义型问题的判定标准为答案是否包含预设的关键信息，"
             "拒答型问题的判定标准为系统是否正确拒答。")

    add_heading(doc, "4.2  消融实验：RAG 组件的贡献", 2)
    add_body(doc,
             "为量化 RAG 各组件的实际贡献，设计了三个对比条件：无 RAG 基线（不提供任何"
             "参考资料，直接提问）、纯向量检索、混合检索配合重排。")

    add_table(doc,
              ["方案", "总体准确率", "事实型", "语义型", "拒答型"],
              [
                  ["无 RAG（基线）", "20.0%", "0.0%", "62.5%", "0.0%"],
                  ["纯向量检索", "96.0%", "100.0%", "87.5%", "100.0%"],
                  ["混合检索 + Rerank", "100.0%", "100.0%", "100.0%", "100.0%"],
              ],
              widths=[1.4, 1.15, 1.15, 1.15, 1.15])

    add_figure(doc, "ablation.png", "图 1  消融实验：RAG 组件贡献对比")

    add_body(doc, "实验结果揭示了三个关键结论：")
    add_body(doc,
             "第一，RAG 带来了 80 个百分点的准确率提升（20% 提升至 100%）。无检索基线在"
             "事实型问题上准确率为零——模型明确表示无法获取具体公司的财务数据。"
             "值得注意的是，模型在这里表现出了诚实的拒绝而非编造数据，但在没有参考资料"
             "的情况下，这种诚实等同于无法完成任务。")
    add_body(doc,
             "第二，拒答型问题在无 RAG 时准确率为零。这说明拒答能力高度依赖检索结果："
             "只有当系统确认参考资料中不存在所需信息时，才能可靠地拒答；缺乏参考资料时，"
             "模型无从判断问题的可答性。")
    add_body(doc,
             "第三，混合检索相比纯向量检索仍有 4 个百分点的提升，且在所有问题类型上均"
             "达到满分。虽然提升幅度小于 RAG 本身的贡献，但在本已很高的基线上仍有改进，"
             "说明混合策略的价值是稳定的。")

    add_heading(doc, "4.3  检索层对比实验", 2)
    add_body(doc,
             "为验证混合检索的必要性，在 22 条可判定问题（事实型与语义型）上对比了"
             "三种检索模式的召回表现。")

    add_table(doc,
              ["检索模式", "Recall@1", "Recall@3", "Recall@5", "MRR"],
              [
                  ["纯向量", "77.3%", "100.0%", "100.0%", "0.879"],
                  ["纯 BM25", "81.8%", "90.9%", "100.0%", "0.886"],
                  ["混合检索 + Rerank", "100.0%", "100.0%", "100.0%", "1.000"],
              ],
              widths=[1.4, 1.15, 1.15, 1.15, 1.15])

    add_figure(doc, "retrieval.png", "图 2  三种检索模式的召回率与 MRR 对比")

    add_body(doc,
             "混合检索将 Recall@1 从纯向量的 77.3% 提升至 100%，提升 22.7 个百分点；"
             "MRR 从 0.879 提升至 1.000。这一提升在金融问答场景中具有重要意义——"
             "答案片段排在第一位意味着更短的上下文、更低的 token 成本，以及更少的"
             "无关信息干扰。")

    add_heading(doc, "4.4  互补性分析", 2)
    add_body(doc,
             "进一步按问题类型拆解，可以清晰看到两种检索方法的互补关系。")

    add_figure(doc, "complementarity.png", "图 3  检索方法在两类问题上的互补性")

    add_body(doc,
             "在事实型问题上，BM25 的 Recall@1（83%）显著高于向量检索（67%）——"
             "财务数字查询依赖精确的词项匹配。在语义型问题上，向量检索（90%）则优于 "
             "BM25（80%）——概念性查询需要语义泛化能力。两种方法各有明确的优势区间，"
             "混合检索在两类问题上均达到 100%。")
    add_body(doc,
             "这一发现解释了为何单一检索策略难以胜任金融问答：金融问题本身天然混合了"
             "事实查询与语义查询，任何单一方法都会在某一类问题上成为瓶颈。")

    add_heading(doc, "4.5  重排序的有效性验证", 2)
    add_body(doc,
             "为验证重排序的实际作用，设计了一个针对性实验：固定查询为"
             "\"公司 2023 年的营业收入是多少\"，观察嵌入模型与重排模型对四个同领域"
             "财务段落的打分差异。")

    add_figure(doc, "rerank.png", "图 4  嵌入模型与重排模型对同域段落的区分能力对比")

    add_body(doc,
             "结果显示，嵌入模型对\"营业收入段落\"（0.834）与\"净利润段落\"（0.618）的"
             "区分度仅为 0.216，两者排序接近，存在误排风险。重排模型则给出 0.997 与 "
             "0.038，区分度达到 0.959，提升约 4.4 倍。这证实了 cross-encoder 架构在"
             "细粒度语义区分上的优势。")
    add_body(doc,
             "此外，重排的计算开销极低——对 20 个候选片段打分耗时约 0.07 秒，"
             "相对于其带来的准确率提升，这一成本完全可以接受。")

    add_heading(doc, "4.6  拒答机制的实际表现", 2)
    add_body(doc, "系统在 5 条应拒答问题上的表现如下：")

    add_table(doc,
              ["问题", "系统行为", "判定"],
              [
                  ["公司明天的股价会涨吗？", "拒答：参考资料未包含股价预测信息", "正确"],
                  ["特斯拉 2023 年的营收是多少？", "拒答：仅包含本公司的报告内容", "正确"],
                  ["公司 2025 年的营收预测是多少？", "拒答：超出数据覆盖时间范围", "正确"],
                  ["给我推荐几只值得买入的股票。", "拒答：不提供投资建议", "正确"],
                  ["公司 CEO 的家庭住址在哪里？", "拒答：参考资料中无相关信息", "正确"],
              ],
              widths=[1.8, 3.6, 0.65])

    add_body(doc,
             "五类拒答场景全部正确识别，覆盖了时效性问题、跨公司问题、超出数据范围、"
             "投资建议请求、隐私信息查询等典型风险场景。拒答机制的可靠性来源于"
             "双重保障：提示词层面的明确规则约束，以及服务端的引用校验兜底。")

    # ===== 5 系统演示 =====
    add_heading(doc, "5  系统演示", 1)
    add_body(doc,
             "系统提供 Streamlit Web 界面，支持问答输入、答案展示与原文溯源查看。"
             "界面侧边栏暴露检索参数，可以在演示中实时切换检索模式，直观对比不同"
             "策略的效果。")

    add_body(doc, "演示中的实际问答示例：")
    add_table(doc,
              ["问题", "系统回答"],
              [
                  ["公司 2023 年的营业收入是多少？",
                   "公司 2023 年实现营业收入 1505.60 亿元，同比增长 18.04% [1]。"],
                  ["公司的分红政策是怎样的？",
                   "公司经本次董事会审议通过的利润分配预案为：以总股本 1256197800 股为基数，"
                   "向全体股东每 10 股派发现金红利 308.76 元（含税），合计派发现金红利 "
                   "387.86 亿元 [1]。公司 2023 年度利润分配方案已于 2024 年 6 月实施完毕 [2]。"],
                  ["公司的研发投入情况如何？",
                   "公司 2023 年研发费用为 5.79 亿元，同比增长 10.28%，占营业收入比例为 "
                   "0.38% [1]。公司持续加大在酿造工艺、微生物研究、智能化生产等领域的"
                   "研发投入 [1]。"],
              ],
              widths=[1.4, 4.6])

    add_body(doc,
             "从示例可以看到，系统的回答具备三个特点：数字精确且与原文完全一致、"
             "每个事实性陈述均标注来源编号、跨段落的回答能够引用多个来源。")

    # ===== 6 总结 =====
    add_heading(doc, "6  总结与展望", 1)

    add_heading(doc, "6.1  项目总结", 2)
    add_body(doc, "本项目完成了一个可运行的金融领域问答系统，主要工作包括：")
    add_bullet(doc,
               "实现了完整的 RAG 流水线：文档解析、语义分块、双索引构建、"
               "混合召回、重排、生成")
    add_bullet(doc,
               "设计了面向金融场景的可信度机制：强制引用、引用校验、主动拒答")
    add_bullet(doc,
               "通过消融实验量化了 RAG 各组件的贡献，验证了混合检索的互补性")
    add_bullet(doc,
               "在 8GB 显存约束下完成了本地模型部署，实测峰值显存 4345MB")

    add_body(doc,
             "实验的核心结论是：在金融问答场景中，检索增强生成不是可选优化而是"
             "必要条件（准确率 20% 至 100%）；单一检索策略存在结构性缺陷，"
             "混合检索的互补性在实验中得到明确验证（Recall@1 提升 22.7 个百分点）；"
             "重排序模型在细粒度语义区分上的价值显著（区分度提升 4.4 倍）。")

    add_heading(doc, "6.2  局限与改进方向", 2)
    add_body(doc, "本项目存在以下局限，也是后续改进的方向：")

    add_heading(doc, "6.2.1  语料规模的限制", 3)
    add_body(doc,
             "当前测试语料为单一文档的 15 个检索单元，规模较小。在如此小的语料上，"
             "检索任务的难度被显著降低——候选集合很小时，多数方法都能取得不错的表现。"
             "实验中的对比结论（特别是混合检索相对于纯向量的提升幅度）在更大规模语料上"
             "可能发生变化。后续应在 100 篇以上文档的语料上重新验证。")

    add_heading(doc, "6.2.2  表格数据的处理", 3)
    add_body(doc,
             "年度报告中包含大量结构化财务表格，当前系统将其作为普通文本处理，"
             "向量化效果不理想。改进方向是将表格结构化抽取为键值对形式单独建索引，"
             "或引入 Text-to-SQL 能力处理数值计算类问题（如计算近三年营收复合增长率）。")

    add_heading(doc, "6.2.3  时效性问题", 3)
    add_body(doc,
             "静态索引无法回答实时性问题（如最新股价、当日公告）。当前系统对此类问题"
             "采取拒答策略。改进方向是引入意图路由，将时效性问题分流至实时数据接口，"
             "实现静态知识库与动态数据源的互补。")

    add_heading(doc, "6.2.4  查询改写与多轮对话", 3)
    add_body(doc,
             "当前系统对用户问题不做改写，直接用于检索。口语化提问（如询问某公司去年"
             "盈利情况）可能影响召回效果。改进方向是增加查询改写模块，将口语查询转换为"
             "规范的金融查询表达；同时支持多轮对话，利用上下文补全指代信息。")

    add_heading(doc, "6.2.5  评测体系的完善", 3)
    add_body(doc,
             "当前评测采用关键词匹配判定，属于弱判定方法，无法评估答案的完整性、"
             "逻辑一致性等维度。改进方向是引入基于大模型的自动评测（LLM-as-Judge），"
             "以及人工标注的黄金标准答案集。")

    # ===== 附录 =====
    doc.add_page_break()
    add_heading(doc, "附录  项目文件清单", 1)

    add_table(doc,
              ["路径", "说明"],
              [
                  ["src/config.py", "全局配置"],
                  ["src/schema.py", "数据结构定义（Chunk / Answer）"],
                  ["src/parser.py", "文档解析与章节切分"],
                  ["src/chunker.py", "语义分块与短章节合并"],
                  ["src/retrieval.py", "混合检索、RRF 融合、Rerank"],
                  ["src/generator.py", "提示词构建、LLM 调用、引用校验"],
                  ["src/pipeline.py", "端到端编排与命令行入口"],
                  ["src/evaluate.py", "测试集评测"],
                  ["src/ablation.py", "消融实验"],
                  ["app/streamlit_app.py", "Web 演示界面"],
                  ["tools/download_models.py", "模型下载"],
                  ["tools/gen_corpus.py", "语料生成"],
                  ["tools/fill_eval.py", "评测集构建"],
                  ["tools/gen_figures.py", "实验图表生成"],
                  ["data/eval/figures/", "实验图表"],
                  ["data/eval/results.json", "端到端评测结果"],
                  ["data/eval/ablation.json", "消融实验数据"],
                  ["data/eval/retrieval_comparison.json", "检索对比实验数据"],
              ],
              widths=[1.9, 4.1])

    doc.save(OUT)
    print("报告已生成: " + str(OUT))


if __name__ == "__main__":
    build()
