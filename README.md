# 金融领域问答系统

基于 **LLM API + 本地 RAG + 提示词注入** 的金融领域问答系统。针对上市公司定期报告，提供**带原文溯源**的可信问答。

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 效果演示

```
问：公司2023年的营业收入是多少？

答：公司 2023 年实现营业收入 1505.60 亿元，同比增长 18.04% [1]。

引用：[1]  置信度：100%
────────────────────────────────────
[1] 贵州茅台 2023 年度报告 · 第二节 公司简介和主要财务指标
    公司2023年实现营业收入1505.60亿元，同比增长18.04%。归属于上市公司
    股东的净利润为747.34亿元，同比增长19.16%。...
```

对于无依据的问题，系统会主动拒答而非编造：

```
问：公司明天的股价会涨吗？

答：参考资料中未包含股价预测相关信息，无法回答该问题。
```

---

## 核心特性

| 特性 | 说明 |
|---|---|
| **混合检索** | BM25 关键词召回 + 向量语义召回，RRF 融合，兼顾事实查询与语义查询 |
| **重排序** | bge-reranker cross-encoder 精排，显著提升 top-5 命中率 |
| **语义分块** | 按财报章节结构切分，避免不同主题内容混入同一片段 |
| **强制引用** | 每个事实性陈述必须标注来源编号，答案可逐句溯源 |
| **拒答机制** | 引用越界、无引用支撑、参考资料不足时主动拒答 |
| **可视化溯源** | Web 界面展示答案对应的原文片段 |

---

## 快速开始

### 环境要求

| 配置 | 启动时间 | 单次问答检索 | 体验 |
|---|---|---|---|
| GPU 6GB+ | 约 11 秒 | 0.4 秒 | 流畅 |
| CPU 8 核 | 约 10 秒 | 2.7 秒 | 可用 |
| CPU 低压 U | 约 20 秒 | 5-8 秒 | 较慢 |

- **Python 3.10+**（必需）
- **内存 3GB+**（实测峰值 2.2GB）
- **磁盘 6GB+**（模型约 4.3GB）
- **GPU 非必需**，CPU 也能完整运行

> **低配机器建议**：在 `.env` 中设置 `ENABLE_RERANK=0`，
> 单次检索可从 2.7 秒降至 0.5 秒，准确率从 100% 降至 96%。
> 重排模型占检索耗时的 94%，是性价比最高的取舍点。

### 一条命令完成安装

```bash
git clone https://github.com/tt1bt/financial-qa-system.git
cd financial-qa-system
python setup.py
```

`setup.py` 会自动完成：

1. 检查 Python 版本、磁盘空间、GPU 情况
2. 安装缺失的依赖（可选清华镜像加速）
3. 下载模型（ModelScope 国内源，约 4.3GB，支持断点续传）
4. 生成 `.env` 配置文件
5. 校验整体配置并给出下一步指引

装完后编辑 `.env` 填入 API Key，再启动：

```bash
streamlit run app/streamlit_app.py
```

> **提示**：项目已包含预建索引和示例语料，clone 后无需重新建索引。
> **换机器或想检查状态**：`python setup.py --check`（只检查，不安装任何东西）。
> **网络慢想分步做**：`python setup.py --skip-models`，之后再单独下载。

### 只检查环境状态

```bash
python setup.py --check
```

输出示例：

```
[1/5] 环境检查
  ✓ Python 3.12.13
  ✓ 磁盘空间充足（剩余 255.2GB）
  ✓ GPU 可用: NVIDIA GeForce RTX 3070 Ti Laptop GPU (8.0GB)
  ✓ 嵌入模型: 已就绪  (D:\hf_cache\bge-m3)
  ✓ 重排模型: 已就绪  (D:\hf_cache\bge-reranker-v2-m3)
  ✓ 检索索引已就绪（372 KB）
  ✓ 语料分块已就绪（15 个片段）
```

---

### 手动安装（如需分步执行）

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 下载模型（约 4.3GB）

```bash
python tools/download_models.py
```

使用 ModelScope 国内源，速度远快于 HuggingFace。默认下载到项目内 `models/` 目录。
下载失败可直接重跑，支持断点续传。

#### 3. 配置 API Key

```bash
# Linux / macOS
cp .env.example .env

# Windows
copy .env.example .env
```

编辑 `.env`，填入你的 LLM API Key。**支持任意 OpenAI 兼容接口**：

| 服务商 | Base URL | 推荐模型 | 获取 Key |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | [platform.deepseek.com](https://platform.deepseek.com/) |
| 阿里通义 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com/) |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | [open.bigmodel.cn](https://open.bigmodel.cn/) |
| 月之暗面 | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | [platform.moonshot.cn](https://platform.moonshot.cn/) |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` | 无需 Key |

### 4. 检查配置

```bash
python -m src.pipeline config
```

### 5. 启动

```bash
# 网页界面
streamlit run app/streamlit_app.py

# 或命令行问答
python -m src.pipeline chat
```

> **提示**：项目已包含预建索引和示例语料，clone 后可直接运行。
> 如需换成自己的数据，见下方「使用自己的数据」。

---

## 使用自己的数据

### 方式一：从网页抓取

```bash
python -m src.collect --url "https://财报页面URL" --company 公司名 --year 2023
```

### 方式二：本地文件

把年报放入 `data/raw/`，支持 PDF / HTML / TXT：

```bash
python -m src.collect --scan      # PDF/HTML 转纯文本
python -m src.collect --check     # 检查解析质量
```

### 重建索引

```bash
python -m src.pipeline build
```

---

## 项目结构

```
financial-qa-system/
├── setup.py            一键安装脚本（推荐入口）
├── src/
│   ├── config.py       全局配置 + 配置校验
│   ├── schema.py       数据结构（Chunk / Answer）—— 模块间契约
│   ├── parser.py       文档解析（HTML/PDF/TXT）
│   ├── chunker.py      语义分块
│   ├── retrieval.py    混合检索、RRF 融合、Rerank
│   ├── generator.py    提示词构建、LLM 调用、引用校验
│   ├── pipeline.py     端到端编排与命令行入口
│   ├── evaluate.py     测试集评测
│   ├── ablation.py     消融实验
│   └── collect.py      数据采集
├── app/
│   └── streamlit_app.py    Web 界面
├── tools/
│   ├── download_models.py  模型下载
│   ├── gen_corpus.py       语料生成
│   ├── fill_eval.py        评测集构建
│   ├── gen_figures.py      实验图表
│   └── gen_report.py       报告生成
├── tests/
│   ├── test_smoke.py       纯逻辑冒烟测试
│   ├── test_models.py      模型加载实测
│   └── test_retrieval.py   检索对比实验
├── data/
│   ├── raw/            原始年报文本
│   ├── chunks.jsonl    分块结果
│   └── eval/           评测集与实验数据
├── index/              Chroma 向量库 + BM25 索引（已预建）
├── models/             模型权重（需自行下载，已 gitignore）
├── .env.example        配置模板
└── requirements.txt
```

---

## 技术方案

### 系统架构

```
┌─────────────────────────────────────────────┐
│  L5 交互层    Streamlit Web 界面              │
├─────────────────────────────────────────────┤
│  L4 生成层    LLM API（任意 OpenAI 兼容端点）  │
│               结构化输出 · 引用校验 · 拒答控制  │
├─────────────────────────────────────────────┤
│  L3 提示词层  System Prompt + 上下文注入模板   │
├─────────────────────────────────────────────┤
│  L2 检索层    混合召回(BM25+向量) → RRF → Rerank│
├─────────────────────────────────────────────┤
│  L1 索引层    文档解析 → 语义分块 → 双索引     │
└─────────────────────────────────────────────┘
```

### 关键设计决策

**为什么用混合检索而非纯向量？**

金融问题分两类：语义型（"经营风险如何"）与事实型（"2023Q3 毛利率"）。实测数据显示，纯向量在事实型问题上 Recall@1 仅 67%，而 BM25 达 83%；语义型上向量（90%）则优于 BM25（80%）。两者存在明确的互补关系。

**为什么 RRF 之后还要 Rerank？**

RRF 只融合多个排序器的"意见"，不理解 query 与 document 的语义交互。cross-encoder 直接对二者打分，实测将"营业收入"与"净利润"的区分度从 0.216 提升至 0.959。

**为什么按章节分块而非固定长度？**

固定长度分块会把"营业收入数据"与"风险提示"切进同一片段，导致检索串台。财报有明确的章节层级，据此切分能保持语义完整，并将章节标题前置以增强检索信号。

---

## 实验结果

### 消融实验（25 条测试集）

| 方案 | 总体准确率 | 事实型 | 语义型 | 拒答型 |
|---|---|---|---|---|
| 无 RAG（基线） | 20.0% | 0.0% | 62.5% | 0.0% |
| 纯向量检索 | 96.0% | 100.0% | 87.5% | 100.0% |
| **混合检索 + Rerank** | **100.0%** | **100.0%** | **100.0%** | **100.0%** |

### 检索层对比（22 条可判定问题）

| 检索模式 | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---|---|---|---|
| 纯向量 | 77.3% | 100.0% | 100.0% | 0.879 |
| 纯 BM25 | 81.8% | 90.9% | 100.0% | 0.886 |
| **混合检索 + Rerank** | **100.0%** | **100.0%** | **100.0%** | **1.000** |

复现实验：

```bash
python -m tests.test_smoke        # 纯逻辑测试（不需 GPU/API）
python -m tests.test_retrieval    # 检索对比实验
python -m src.evaluate            # 端到端评测
python -m src.ablation            # 消融实验
python tools/gen_figures.py       # 生成图表
```

> **关于实验数据的说明**：仓库内的示例语料为**合成数据**（数值参考公开信息构造），
> 用于验证技术链路与实验方法。语料规模较小（15 个检索单元），会降低检索任务难度。
> 在真实的大规模年报语料上，对比结论的幅度可能变化。建议替换为真实数据后重新验证。

---

## 常见问题

**Q: 显存不够或没有 GPU 怎么办？**

在 `.env` 中设置 `ENABLE_RERANK=0` 跳过重排模型。实测数据（Ryzen 7 6800H 纯 CPU）：

| 配置 | 单次检索耗时 |
|---|---|
| 完整（含重排） | 2.7 秒 |
| 关闭重排 | 0.5 秒 |

重排模型占检索耗时的 94%，关闭后准确率从 100% 降至 96%，但内存占用降到 1GB 以内。

**Q: 必须用 GPU 吗？**

不必须。CPU 能完整运行，实测内存峰值仅 2.2GB。GPU 的主要收益是启动更快（11 秒 vs 10 秒，差别不大），检索环节 GPU 约 0.4 秒、CPU 约 2.7 秒。

**Q: 模型能不能不下载？**

不能。查询编码必须用与建索引时相同的 embedding 模型——索引里的文档向量是离线算好的可随仓库分发，但**每个用户问题都要现场编码成向量**才能做相似度比较。这是向量检索的机制决定的，无法省略。

**Q: 换 embedding 模型后检索结果很怪？**

向量库中的向量与 embedding 模型是**绑定**的。更换模型后必须重建索引：`python -m src.pipeline build`。

**Q: 别人 clone 后需要重新建索引吗？**

不需要。仓库已包含预建索引（`index/`，仅 372KB）和分块结果（`data/chunks.jsonl`）。但**模型权重需要自行下载**，因为体积过大未纳入版本控制——运行 `python setup.py` 会自动处理。

**Q: Python 环境已经装过一些依赖，会冲突吗？**

`setup.py` 只安装缺失的包，已存在的会跳过。也可以先运行 `python setup.py --check` 查看当前状态，再决定装什么。

**Q: 支持多公司检索吗？**

当前设计为单公司场景。扩展多公司需要在 `Retriever.search()` 中增加元数据过滤，并在前端加公司选择器。

---

## 许可证

MIT License，详见 [LICENSE](LICENSE)。

## 致谢

- [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) — 嵌入模型
- [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) — 重排模型
- [Chroma](https://www.trychroma.com/) — 向量数据库
- [Streamlit](https://streamlit.io/) — Web 界面框架
