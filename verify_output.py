"""
离线校验已落盘的审计结果：
读取 output/audit_result.json，对每条证据包重算哈希并与归档哈希比对。
不重新调用规则引擎和大模型，只校验已保存文件是否完整、未被改动。
"""
from __future__ import annotations

import json
import os

from core.evidence import compute_hash

OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "output",
    "audit_result.json",
)


def main() -> None:
    if not os.path.exists(OUTPUT_PATH):
        raise FileNotFoundError(f"结果文件不存在: {OUTPUT_PATH}")

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", [])
    if not records:
        print("结果文件中没有记录。")
        return

    passed = 0
    failed = []

    for rec in records:
        cid = rec["claim_id"]
        pkg = rec["evidence"]

        stored = pkg.pop("evidence_hash")
        recomputed = compute_hash(pkg)
        pkg["evidence_hash"] = stored  # 还原，不改动原文件内容

        if stored == recomputed:
            passed += 1
            print(f"{cid} 哈希一致")
        else:
            failed.append(cid)
            print(f"{cid} 哈希不一致")

    print(f"\n校验完成：通过 {passed} 条，失败 {len(failed)} 条")
    if failed:
        raise AssertionError(f"以下单据证据包校验失败: {failed}")


if __name__ == "__main__":
    main()
