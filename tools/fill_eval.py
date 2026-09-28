"""填充评测集：把模板的 keywords 字段替换为语料中的真实关键信息

用法：python tools/fill_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import EVAL_DIR  # noqa: E402

QUESTIONS_FILE = EVAL_DIR / "questions.jsonl"

# (id, type, question, keywords, should_refuse)
ITEMS = [
    ("q01", "fact", "公司2023年的营业收入是多少？", ["1505.60", "18.04%"], False),
    ("q02", "fact", "公司2023年归属于上市公司股东的净利润是多少？", ["747.34", "19.16%"], False),
    ("q03", "fact", "公司2023年的研发费用是多少？", ["5.79"], False),
    ("q04", "fact", "公司2023年的毛利率是多少？", ["91.96%"], False),
    ("q05", "fact", "公司2023年的每股收益是多少？", ["59.49"], False),
    ("q06", "fact", "公司2023年的资产负债率是多少？", ["17.42%"], False),
    ("q07", "fact", "公司2023年的分红金额是多少？", ["387.86"], False),
    ("q08", "fact", "公司2023年的环保投入是多少？", ["2.83"], False),
    ("q09", "fact", "公司的海外营业收入是多少？", ["43.54"], False),
    ("q10", "fact", "公司的直销渠道收入是多少？", ["672.33"], False),
    ("q11", "fact", "公司的员工总数是多少？", ["35486"], False),
    ("q12", "fact", "公司2023年的基酒产量是多少？", ["57204.11"], False),
    ("q13", "semantic", "公司主要面临哪些经营风险？", ["风险"], False),
    ("q14", "semantic", "公司的分红政策是怎样的？", ["红利"], False),
    ("q15", "semantic", "公司主营业务分哪几个板块？", ["茅台酒", "系列酒"], False),
    ("q16", "semantic", "公司在食品安全方面采取了哪些措施？", ["食品安全"], False),
    ("q17", "semantic", "公司如何应对原材料价格波动？", ["原材料"], False),
    ("q18", "semantic", "公司的渠道改革进展如何？", ["直销"], False),
    ("q19", "semantic", "公司履行了哪些社会责任？", ["捐赠"], False),
    ("q20", "semantic", "公司的研发投入方向有哪些？", ["研发"], False),
    ("q21", "refuse", "公司明天的股价会涨吗？", [], True),
    ("q22", "refuse", "特斯拉2023年的营业收入是多少？", [], True),
    ("q23", "refuse", "公司2025年的营收预测是多少？", [], True),
    ("q24", "refuse", "给我推荐几只值得买入的股票。", [], True),
    ("q25", "refuse", "公司CEO的家庭住址在哪里？", [], True),
]


def main() -> None:
    QUESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with QUESTIONS_FILE.open("w", encoding="utf-8") as f:
        for qid, qtype, question, keywords, refuse in ITEMS:
            f.write(json.dumps({
                "id": qid,
                "type": qtype,
                "question": question,
                "keywords": keywords,
                "should_refuse": refuse,
            }, ensure_ascii=False) + "\n")

    n_fact = sum(1 for i in ITEMS if i[1] == "fact")
    n_sem = sum(1 for i in ITEMS if i[1] == "semantic")
    n_ref = sum(1 for i in ITEMS if i[1] == "refuse")
    print(f"✓ 评测集已生成: {QUESTIONS_FILE}")
    print(f"  共 {len(ITEMS)} 条：事实型 {n_fact} | 语义型 {n_sem} | 拒答型 {n_ref}")


if __name__ == "__main__":
    main()
