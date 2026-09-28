"""Streamlit Web Demo —— 金融问答界面

设计重点：
- 答案区 + 溯源区分离，突出可信度
- 引用编号可追溯，点击展开原文
- 侧边栏暴露检索参数，便于现场演示对比实验
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# 让 streamlit run 能 import 到 src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import (  # noqa: E402
    ENABLE_RERANK,
    LLM_BASE_URL,
    LLM_MODEL,
    TOP_K_FINAL,
    TOP_K_RECALL,
    check_config,
)
from src.pipeline import answer_question  # noqa: E402
from src.retrieval import Retriever  # noqa: E402

st.set_page_config(
    page_title="金融问答系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_setup_guide(problems: list[str]) -> None:
    """配置缺失时显示引导页"""
    st.markdown("## ⚙️ 首次使用需要完成配置")
    st.markdown("检测到以下配置问题，完成后刷新页面即可：")

    for i, p in enumerate(problems, 1):
        st.error(f"**问题 {i}**  \n{p}")

    st.divider()
    st.markdown("### 完整配置步骤")
    st.code(
        """# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载模型（约 4.3GB，使用 ModelScope 国内源）
python tools/download_models.py

# 3. 配置 API Key
#    Linux / macOS
cp .env.example .env
#    Windows
copy .env.example .env
#    然后编辑 .env，填入你的 LLM_API_KEY

# 4. 检查配置
python -m src.pipeline config

# 5. 启动界面
streamlit run app/streamlit_app.py""",
        language="bash",
    )

    st.info(
        "**关于 API Key**：本系统支持任意 OpenAI 兼容接口。"
        "推荐使用 DeepSeek（性价比高、国内可直连），"
        "也可使用通义千问、智谱 GLM、Kimi，或本地部署的 Ollama / vLLM。"
        "详见 `.env.example` 中的注释。"
    )
    st.stop()

# --- 样式 ---
st.markdown(
    """
    <style>
    .main-title { font-size: 2rem; font-weight: 700; margin-bottom: 0.2rem; }
    .sub-title { color: #888; margin-bottom: 1.5rem; }
    .answer-box {
        background: #f8f9fa; border-left: 4px solid #2b6cb0;
        padding: 1rem 1.2rem; border-radius: 4px; margin: 0.5rem 0 1rem 0;
        line-height: 1.8;
    }
    .refuse-box {
        background: #fff5f5; border-left: 4px solid #c53030;
        padding: 1rem 1.2rem; border-radius: 4px; margin: 0.5rem 0 1rem 0;
    }
    .cite-tag {
        display: inline-block; background: #2b6cb0; color: white;
        padding: 1px 7px; border-radius: 3px; font-size: 0.8rem;
        margin-right: 4px;
    }
    .source-card {
        background: #fff; border: 1px solid #e2e8f0;
        padding: 0.8rem; border-radius: 4px; margin-bottom: 0.6rem;
    }
    .source-meta { color: #718096; font-size: 0.8rem; margin-bottom: 0.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- 检索器缓存 ---
@st.cache_resource(show_spinner="正在加载索引与模型...")
def load_retriever():
    return Retriever().load()


# --- 配置校验：缺失时显示引导页而非报错堆栈 ---
_config_problems = check_config(require_api=True)


# --- 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 检索设置")

    mode = st.selectbox(
        "检索模式",
        options=["hybrid", "vector", "bm25"],
        index=0,
        format_func=lambda x: {
            "hybrid": "混合检索 + Rerank（推荐）",
            "vector": "纯向量检索",
            "bm25": "纯关键词检索",
        }[x],
        help="用于现场对比实验：切换模式可直观看到检索策略的影响",
    )

    top_k = st.slider("返回片段数 (top_k)", 1, 10, TOP_K_FINAL)

    st.divider()
    st.caption(f"召回数: {TOP_K_RECALL} | Rerank: {'开启' if ENABLE_RERANK else '关闭'}")

    with st.expander("🔧 当前配置"):
        st.caption(f"**模型**: `{LLM_MODEL}`")
        st.caption(f"**端点**: `{LLM_BASE_URL}`")
        st.caption(f"**API Key**: {'已配置 ✓' if not _config_problems else '未配置 ✗'}")

    st.divider()

    st.markdown("**示例问题**")
    examples = [
        "公司2023年的营业收入是多少？",
        "公司主要面临哪些经营风险？",
        "公司的分红政策是怎样的？",
        "研发投入占营收比例是多少？",
        "公司明天的股价会涨吗？",
    ]
    for q in examples:
        if st.button(q, use_container_width=True, key=f"ex_{q}"):
            st.session_state.pending_question = q


# --- 配置缺失时拦截 ---
if _config_problems:
    render_setup_guide(_config_problems)


# --- 主区域 ---
st.markdown('<div class="main-title">📊 金融领域问答系统</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">基于检索增强生成（RAG）· 答案可溯源 · 拒绝无依据回答</div>',
    unsafe_allow_html=True,
)

retriever = load_retriever()

if not retriever.chunks:
    st.error("索引为空。请先在 `data/raw/` 放入年报，然后运行 `python -m src.pipeline build`")
    st.stop()

st.caption(f"已索引 {len(retriever.chunks):,} 个文档片段")

# 历史记录
if "history" not in st.session_state:
    st.session_state.history = []

# 处理侧边栏示例按钮
if "pending_question" in st.session_state:
    st.session_state.query_input = st.session_state.pop("pending_question")

question = st.text_input(
    "请输入你的问题",
    key="query_input",
    placeholder="例如：公司2023年的营业收入是多少？",
)

col1, col2 = st.columns([1, 5])
with col1:
    submit = st.button("提问", type="primary", use_container_width=True)
with col2:
    if st.button("清空历史", use_container_width=False):
        st.session_state.history = []
        st.rerun()

if submit and question.strip():
    with st.spinner("检索并生成回答中..."):
        try:
            ans = answer_question(question, retriever, mode=mode, top_k=top_k)
            st.session_state.history.insert(0, (question, ans))
        except Exception as exc:
            st.error(f"生成失败：{exc}")
            st.exception(exc)

# --- 渲染结果 ---
for idx, (q, ans) in enumerate(st.session_state.history):
    st.markdown(f"#### ❓ {q}")

    if ans.refused:
        st.markdown(f'<div class="refuse-box">🚫 <b>拒答</b><br>{ans.answer}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="answer-box">{ans.answer}</div>', unsafe_allow_html=True)

    meta_cols = st.columns(3)
    meta_cols[0].metric("置信度", f"{ans.confidence:.0%}")
    meta_cols[1].metric("引用数", len(ans.citations))
    meta_cols[2].metric("检索片段", len(ans.contexts))

    if ans.contexts:
        with st.expander(f"📄 查看溯源原文（{len(ans.contexts)} 个片段）", expanded=(idx == 0)):
            for i, c in enumerate(ans.contexts, start=1):
                is_cited = str(i) in ans.citations
                tag = '<span class="cite-tag">已引用</span>' if is_cited else ""
                meta = f"{c.company} · {c.year} · {c.metadata.get('section', '正文')}"
                st.markdown(
                    f'<div class="source-card">'
                    f'<div class="source-meta">[{i}] {tag} {meta} · 相关度 {c.score:.3f}</div>'
                    f'{c.text[:600]}{"..." if len(c.text) > 600 else ""}'
                    f"</div>",
                    unsafe_allow_html=True,
                )

    if idx < len(st.session_state.history) - 1:
        st.divider()

# --- 页脚 ---
st.divider()
st.caption(
    "⚠️ 本系统仅基于已披露的定期报告内容作答，不构成任何投资建议。"
    "所有回答均标注原文出处，无依据的问题会被拒绝回答。"
)
