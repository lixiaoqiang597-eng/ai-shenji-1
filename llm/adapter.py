"""
大模型适配层（语义路径，可切换后端）
- mock：离线演示，不调用外部模型
- openai：兼容 OpenAI 协议，接 DeepSeek（base_url 指向 api.deepseek.com）
模型只输出一致性判断、置信度、理由，不做最终通过/驳回裁决。
"""
from __future__ import annotations

import json
import os
from dotenv import load_dotenv
load_dotenv()
from typing import Any

PROMPT_TEMPLATE = """你是费用报销合规复核助手。请判断以下报销单据的“业务实质”与“报销科目/事由”是否相符。

单据信息：
- 提交人：{submitter}
- 部门：{department}
- 费用类别：{category}
- 金额：{amount}
- 供应商：{vendor}
- 报销事由：{business_purpose}

只依据以上信息判断，不要臆造未给出的事实。输出 JSON，字段如下：
- consistent: true/false（业务实质与类别是否相符）
- confidence: 0~1 的置信度
- reason: 一句话理由
- risk_type: 若不相符，指出问题类型（科目不符/事由与实质矛盾/证据不足/无）

输出必须是纯 JSON，不要包含 Markdown 代码块。"""


def _mock_decision(claim: dict) -> dict[str, Any]:
    """离线占位：未接 API 时跑通流程，不代表真实模型判断。"""
    return {
        "consistent": True,
        "confidence": 0.75,
        "reason": "离线 mock 默认判断一致，接 API 后由模型生成",
        "risk_type": "无",
    }


def _deepseek_decision(claim: dict, api_key: str) -> dict[str, Any]:
    """调用 DeepSeek（兼容 OpenAI 协议）。"""
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
    )
    prompt = PROMPT_TEMPLATE.format(**claim)
    resp = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "deepseek-flash"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = (resp.choices[0].message.content or "{}").strip()

    # 剥离可能出现的 ```json ... ``` 包裹
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    return json.loads(content.strip())


def semantic_review(claim: dict, backend: str | None = None) -> dict[str, Any]:
    """
    统一入口。
    backend: mock / openai / None（读环境变量 LLM_BACKEND，默认 mock）
    """
    backend = backend or os.getenv("LLM_BACKEND", "mock")

    try:
        if backend == "mock":
            decision = _mock_decision(claim)
        elif backend == "openai":
            decision = _deepseek_decision(
                claim,
                api_key=os.getenv("LLM_API_KEY", ""),
            )
        else:
            raise ValueError(f"未知后端: {backend}")

        confidence = float(decision.get("confidence", 0))
        if not (0 <= confidence <= 1):
            confidence = 0.0

        return {
            "consistent": bool(decision.get("consistent")),
            "confidence": confidence,
            "reason": decision.get("reason", ""),
            "risk_type": decision.get("risk_type", "无"),
            "backend": backend,
            "raw": decision,
        }
    except Exception as exc:
        # 调用失败/解析失败 -> 证据不足，降级人工
        return {
            "consistent": None,
            "confidence": 0.0,
            "reason": f"模型调用或解析失败: {type(exc).__name__}",
            "risk_type": "证据不足",
            "backend": backend,
            "raw": None,
        }
