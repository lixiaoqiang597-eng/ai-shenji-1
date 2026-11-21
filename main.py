"""
AI 费用报销自动审计原型 —— 主流程
加载数据 -> 规则扫描 -> 语义复核 -> 裁决 -> 证据包输出
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules.engine import run_rules
from llm.adapter import semantic_review
from core.verdict import adjudicate
from core.evidence import build_evidence_package, compute_hash

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def load_claims(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    claims = load_claims(os.path.join(DATA_DIR, "sample_reimbursements.json"))

    # 路径一：规则引擎全量扫描
    rule_results = run_rules(claims)

    audit_records = []
    summary = {"high": 0, "medium": 0, "low": 0, "pass": 0}

    for claim in claims:
        cid = claim["claim_id"]
        rule_result = rule_results[cid]

        # 路径二：大模型语义复核
        llm_decision = semantic_review(claim)

        # 双路径裁决
        verdict = adjudicate(rule_result, llm_decision)

        # 组装证据包 + 哈希
        evidence_package = build_evidence_package(
            claim, rule_result["findings"], llm_decision, verdict
        )

        audit_records.append({
            "claim_id": cid,
            "submitter": claim["submitter"],
            "category": claim["category"],
            "amount": claim["amount"],
            "verdict": verdict,
            "rule_findings": rule_result["findings"],
            "llm_decision": llm_decision,
            "evidence": evidence_package,
        })
        summary[verdict["level"]] += 1

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "audit_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {"summary": summary, "records": audit_records},
            f, ensure_ascii=False, indent=2,
        )

    # 控制台汇总
    print("=== 审计分级汇总 ===")
    for level, count in summary.items():
        print(f"{level:8s}: {count}")
    print(f"\n明细已写入: {out_path}")

    # 哈希自检：重算并比对
    for rec in audit_records:
        pkg = rec["evidence"]
        stored = pkg.pop("evidence_hash")
        recomputed = compute_hash(pkg)
        pkg["evidence_hash"] = stored
        assert stored == recomputed, f"哈希不一致: {rec['claim_id']}"
    print("证据哈希自检通过：每条结论均可被第三方复算。")


if __name__ == "__main__":
    main()
