#!/usr/bin/env python3
"""在标注集上跑 extract_lead:报不合规率、幻觉率、优先级准确率、数量与公司命中率。

uv run python evals/extract_lead/run.py evals/extract_lead/dataset.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server" / "src"))

from mail2leads import backends  # noqa: E402
from mail2leads.tasks.extract_lead import extract_lead  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--out", type=Path, default=Path("evals/extract_lead/results.tsv"))
    args = parser.parse_args()
    ok, why = backends.ready()
    if not ok:
        print(f"跑不了:{why}", file=sys.stderr)
        return 2
    rows = [
        json.loads(line) for line in args.dataset.read_text("utf-8").splitlines() if line.strip()
    ]
    malformed = hallucinated = priority_ok = company_ok = quantity_ok = 0
    lines = ["id\ttrap\t不合规\t幻觉\t优先级对\t公司对\t数量对\t提取"]
    for row in rows:
        ref = row["reference"]
        try:
            result = extract_lead(row["source"])
        except backends.LLMError as exc:
            malformed += 1
            lines.append(f"{row['id']}\t{row.get('trap', '')}\tYES\t\t\t\t\t{str(exc)[:100]}")
            print(f"  {row['id']}  ✘ 不合规")
            continue
        lead = result.lead
        hallucinated += int(bool(result.unverified))
        p_ok = lead.priority == ref.get("priority")
        c_ok = lead.company.strip().lower() == str(ref.get("company", "")).strip().lower()
        q_ok = lead.quantity.replace(" ", "") == str(ref.get("quantity", "")).replace(" ", "")
        priority_ok += p_ok
        company_ok += c_ok
        quantity_ok += q_ok
        flag = ",".join(result.unverified)
        dump = lead.model_dump_json()
        lines.append(
            f"{row['id']}\t{row.get('trap', '')}\t\t{flag}\t{p_ok}\t{c_ok}\t{q_ok}\t{dump}"
        )
        yn = {True: "对", False: "错"}
        marks = f"优先级={yn[p_ok]} 公司={yn[c_ok]} 数量={yn[q_ok]}"
        print(f"  {row['id']}  幻觉={flag or '无'}  {marks}")
    n, answered = len(rows), len(rows) - malformed
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"\n=== {backends.describe()} · extract_lead ===")
    print(f"  不合规率  {malformed}/{n} = {malformed / n:.1%}  ← 及格线 0%")
    if answered:
        print(f"  幻觉率    {hallucinated}/{answered} = {hallucinated / answered:.1%}  ← 及格线 0%")
        print(f"  优先级对  {priority_ok}/{answered}   公司对 {company_ok}/{answered}")
        print(f"  数量对    {quantity_ok}/{answered}")
    return 1 if (malformed or hallucinated) else 0


if __name__ == "__main__":
    raise SystemExit(main())
