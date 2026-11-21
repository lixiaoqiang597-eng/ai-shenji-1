"""
双路径裁决层
裁决规则（阈值可在实验中校准）：
- 模型证据不足/调用失败 -> 降级人工；
- 命中确定性规则 -> 规则结论优先，人工复核；
- 语义规则与模型均提示不符 -> 高风险人工；
- 语义规则命中但模型判一致 -> 路径冲突，人工抽复核；
- 规则未命中但模型提示不符 -> 人工复核；
- 双路径一致且置信度达标 -> 自动通过。
"""
from __future__ import annotations

from typing import Any

CONFIDENCE_THRESHOLD = 0.7


def _severity_of(findings: list[dict]) -> str:
    if any(f["severity"] == "high" for f in findings):
        return "high"
    if any(f["severity"] == "medium" for f in findings):
        return "medium"
    if findings:
        return "low"
    return "pass"


def adjudicate(rule_result: dict, llm_decision: dict) -> dict[str, Any]:
    rule_hit = rule_result["rule_flag"] == "flag"
    findings = rule_result["findings"]

    # 区分确定性规则与语义辅助规则
    deterministic_hits = [f for f in findings if f.get("deterministic")]
    semantic_hits = [f for f in findings if not f.get("deterministic")]

    llm_consistent = llm_decision.get("consistent")
    confidence = float(llm_decision.get("confidence", 0))
    llm_ok = llm_consistent is True and confidence >= CONFIDENCE_THRESHOLD
    llm_insufficient = llm_consistent is None or confidence < CONFIDENCE_THRESHOLD

    if llm_insufficient:
        level = "high"
        action = "manual"
        reason = "大模型证据不足或调用失败，按保守原则降级人工"
    elif deterministic_hits:
        level = "high"
        action = "manual"
        reason = "命中确定性规则（重复票/拆单/超限/超预算等），规则结论优先，人工复核"
    elif semantic_hits and not llm_ok:
        level = "high"
        action = "manual"
        reason = "语义规则与大模型均提示实质不符，列入高风险复核"
    elif semantic_hits and llm_ok:
        level = "medium"
        action = "manual_sample"
        reason = "语义规则命中但模型判断一致，存在路径冲突，人工抽复核"
    elif not rule_hit and not llm_ok:
        level = "medium"
        action = "manual"
        reason = "规则未命中但模型提示实质不符，人工复核"
    else:
        level = "pass"
        action = "auto_pass"
        reason = "双路径一致通过，置信度达标"

    return {
        "level": level,
        "action": action,
        "reason": reason,
        "rule_severity": _severity_of(findings),
        "rule_hit": rule_hit,
        "deterministic_rule_ids": [f["rule_id"] for f in deterministic_hits],
        "semantic_rule_ids": [f["rule_id"] for f in semantic_hits],
        "llm_consistent": llm_consistent,
        "llm_confidence": confidence,
    }
