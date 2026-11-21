"""
证据链与可复算性模块
- 对每条结论的结构化内容计算 SHA-256 哈希；
- 第三方可用同一字段、同一规则版本重新计算哈希比对，验证结论未被篡改。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

RULE_ENGINE_VERSION = "rule-engine-v0.1"


def canonical_json(obj: Any) -> str:
    """生成稳定序列化字符串：键排序、无多余空白。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_hash(payload: Any) -> str:
    """计算 SHA-256 哈希值。"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_evidence_package(
    claim: dict,
    rule_findings: list[dict],
    llm_decision: dict,
    verdict: dict,
) -> dict:
    """
    组装可复算证据包。
    哈希输入：单据关键字段 + 规则命中 + 模型判断 + 裁决结论 + 引擎版本。
    """
    payload = {
        "claim_id": claim["claim_id"],
        "source_fields": {
            "submitter": claim["submitter"],
            "department": claim["department"],
            "expense_date": claim["expense_date"],
            "category": claim["category"],
            "amount": claim["amount"],
            "invoice_no": claim["invoice_no"],
            "vendor": claim["vendor"],
            "business_purpose": claim["business_purpose"],
        },
        "rule_findings": rule_findings,
        "llm_decision": {
            "consistent": llm_decision.get("consistent"),
            "confidence": llm_decision.get("confidence"),
            "risk_type": llm_decision.get("risk_type"),
            "reason": llm_decision.get("reason"),
        },
        "verdict": verdict,
        "rule_engine_version": RULE_ENGINE_VERSION,
    }
    payload["evidence_hash"] = compute_hash(payload)
    return payload
