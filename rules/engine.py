"""
规则引擎（代码路径）
只做可确定性计算的检查，输出结构化命中结果 + 字段级证据。
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any


# 可配置规则参数：实际项目应从制度表读取，这里先写死演示
POLICY = {
    "entertainment_amount_cap": 1500.00,   # 业务招待费单场上限
    "hotel_amount_cap": 600.00,           # 差旅费-住宿单张参考上限
    "min_purpose_length": 8,              # 事由最小长度
}

SPLIT_DAYS_WINDOW = 3  # 拆单识别：同人同供应商相邻日期间隔（天）


def _evidence(claim_id: str, field: str, field_value: Any,
               rule_id: str, message: str) -> dict:
    """组装一条字段级证据。"""
    return {
        "claim_id": claim_id,
        "rule_id": rule_id,
        "field": field,
        "field_value": field_value,
        "message": message,
    }

def check_duplicate_invoice(claims: list[dict]) -> dict[str, list[dict]]:
    """规则 D1：重复发票号（同一张票报销两次），确定性规则。"""
    by_invoice: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        by_invoice[c["invoice_no"]].append(c)

    results: dict[str, list[dict]] = defaultdict(list)
    for invoice_no, group in by_invoice.items():
        if len(group) > 1:
            ids = [g["claim_id"] for g in group]
            for g in group:
                results[g["claim_id"]].append({
                    "rule_id": "D1",
                    "rule_name": "重复发票",
                    "hit": True,
                    "severity": "high",
                    "deterministic": True,
                    "evidence": [_evidence(
                        g["claim_id"], "invoice_no", invoice_no, "D1",
                        f"发票号 {invoice_no} 出现在单据 {ids} 中，疑似重复报销",
                    )],
                    "message": f"发票号在 {len(group)} 张单据中重复出现",
                })
    return results

def check_split_order(claims: list[dict]) -> dict[str, list[dict]]:
    """规则 D2：同人同供应商近日期多张合计超限，疑似拆单规避审批。"""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for c in claims:
        groups[(c["submitter"], c["vendor"])].append(c)

    results: dict[str, list[dict]] = defaultdict(list)
    for (submitter, vendor), group in groups.items():
        if len(group) < 2:
            continue
        group_sorted = sorted(group, key=lambda x: x["expense_date"])
        total = sum(g["amount"] for g in group_sorted)

        # 相邻单据日期间隔 <= 窗口天数，视为同一批次
        from datetime import date
        dates = []
        for g in group_sorted:
            y, m, d = map(int, g["expense_date"].split("-"))
            dates.append(date(y, m, d))
        clustered = all(
            (dates[i] - dates[i - 1]).days <= SPLIT_DAYS_WINDOW
            for i in range(1, len(dates))
        )

        if clustered and total > POLICY["entertainment_amount_cap"]:
            for g in group_sorted:
                results[g["claim_id"]].append({
                    "rule_id": "D2",
                    "rule_name": "疑似拆单",
                    "hit": True,
                    "severity": "high",
                    "deterministic": True,
                    "evidence": [_evidence(
                        g["claim_id"], "amount", g["amount"], "D2",
                        f"{submitter} 在 {vendor} 多张单据合计 {total:.2f} 元，"
                        f"日期间隔<={SPLIT_DAYS_WINDOW}天，疑似拆单规避审批",
                    )],
                    "message": f"同人同供应商近窗口合计 {total:.2f} 元，疑似拆单",
                })
    return results

def check_amount_cap(claim: dict) -> list[dict]:
    """规则 D3：按类别政策上限检查单笔金额。"""
    findings: list[dict] = []
    category = claim["category"]
    amount = claim["amount"]
    cap = None
    if category == "业务招待费":
        cap = POLICY["entertainment_amount_cap"]
    elif category == "差旅费-住宿":
        cap = POLICY["hotel_amount_cap"]

    if cap is not None and amount > cap:
        findings.append({
            "rule_id": "D3",
            "rule_name": "金额超限",
            "hit": True,
            "severity": "high" if amount > cap * 1.5 else "medium",
            "deterministic": True,
            "evidence": [_evidence(
                claim["claim_id"], "amount", amount, "D3",
                f"{category} 上限 {cap:.2f} 元，本单 {amount:.2f} 元，超出 {amount - cap:.2f} 元",
            )],
            "message": "金额超出类别政策上限",
        })
    return findings

def check_budget(claim: dict) -> list[dict]:
    """规则 D4：单据金额是否超出部门预算额度。"""
    findings: list[dict] = []
    if claim["amount"] > claim["department_budget"]:
        findings.append({
            "rule_id": "D4",
            "rule_name": "超部门预算",
            "hit": True,
            "severity": "medium",
            "deterministic": True,
            "evidence": [_evidence(
                claim["claim_id"], "department_budget",
                {"amount": claim["amount"], "budget": claim["department_budget"]}, "D4",
                f"单据 {claim['amount']:.2f} 元 > 部门预算 {claim['department_budget']:.2f} 元",
            )],
            "message": "超出部门预算额度",
        })
    return findings

def check_purpose_length(claim: dict) -> list[dict]:
    """规则 D6：报销事由过短，信息不足以判断业务实质。"""
    findings: list[dict] = []
    if len(claim["business_purpose"].strip()) < POLICY["min_purpose_length"]:
        findings.append({
            "rule_id": "D6",
            "rule_name": "事由证据不足",
            "hit": True,
            "severity": "low",
            "deterministic": True,
            "evidence": [_evidence(
                claim["claim_id"], "business_purpose", claim["business_purpose"], "D6",
                f"事由长度 {len(claim['business_purpose'].strip())} < "
                f"{POLICY['min_purpose_length']}，信息不足以判断业务实质",
            )],
            "message": "报销事由过短，证据不足",
        })
    return findings

def check_category_consistency(claim: dict) -> list[dict]:
    """规则 D5：科目关键词粗匹配。未命中只标记待语义复核，最终由大模型判断。"""
    findings: list[dict] = []
    keywords = CATEGORY_KEYWORDS.get(claim["category"], [])
    purpose = claim["business_purpose"]
    if keywords and not any(k in purpose for k in keywords):
        findings.append({
            "rule_id": "D5",
            "rule_name": "科目关键词不符",
            "hit": True,
            "severity": "medium",
            "deterministic": False,
            "evidence": [_evidence(
                claim["claim_id"], "business_purpose", purpose, "D5",
                f"类别 {claim['category']} 的关键词 {keywords} 均未在事由中出现，"
                "是否实质不符需大模型复核",
            )],
            "message": "事由未命中类别关键词，待语义复核",
        })
    return findings

def run_rules(claims: list[dict]) -> dict[str, dict]:
    """执行全部规则，返回 {claim_id: {rule_flag, findings}}。"""
    dup = check_duplicate_invoice(claims)
    split = check_split_order(claims)

    result: dict[str, dict] = {}
    for claim in claims:
        cid = claim["claim_id"]
        findings: list[dict] = []
        findings += dup.get(cid, [])
        findings += split.get(cid, [])
        findings += check_amount_cap(claim)
        findings += check_budget(claim)
        findings += check_category_consistency(claim)
        findings += check_purpose_length(claim)

        result[cid] = {
            "rule_flag": "flag" if findings else "pass",
            "findings": findings,
        }
    return result


# 类别关键词映射：用于科目/实质一致性的规则侧粗判
CATEGORY_KEYWORDS = {
    "差旅费-住宿": ["住宿", "酒店", "宾馆", "旅店"],
    "差旅费-交通": ["机票", "车票", "高铁", "火车", "打车", "出行"],
    "业务招待费": ["接待", "客户", "宴请", "招待", "商务餐"],
    "办公费": ["文具", "纸张", "办公", "书籍", "耗材"],
}

