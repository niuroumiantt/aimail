#!/usr/bin/env python3
"""在标注集上跑 summarize_inquiry,报四个指标。

    uv run python evals/summarize_inquiry/run.py evals/summarize_inquiry/dataset.jsonl --no-judge
    LOCAL_MODEL=brain uv run python evals/summarize_inquiry/run.py ... --out .../brain.tsv

确定性(不合规率、幻觉率、is_inquiry 准确率)由代码算,可信;覆盖率由 Claude 当裁判,是估计值。
裁判绝不是被测模型本身。幻觉率大于 0 或有不合规样本,退出码非零——能直接挂 CI。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server" / "src"))

from aimail import backends  # noqa: E402
from aimail.tasks.summarize import summarize  # noqa: E402

JUDGE_SYSTEM = (
    "你在核对一份摘要有没有覆盖到给定的事实点。对每一个参考事实点,判断它是否被摘要表达出来了"
    '(意思到了就算)。只回 JSON:{"covered": [true, false, ...]},数组长度必须和事实点数量一致。'
)


def judge(client, summary_zh: str, facts: list[str]) -> list[bool]:
    if not facts:
        return []
    payload = json.dumps({"摘要": summary_zh, "事实点": facts}, ensure_ascii=False)
    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=2000,
        system=JUDGE_SYSTEM,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {"covered": {"type": "array", "items": {"type": "boolean"}}},
                    "required": ["covered"],
                    "additionalProperties": False,
                },
            }
        },
        messages=[{"role": "user", "content": payload}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    covered = json.loads(text)["covered"]
    return (covered + [False] * len(facts))[: len(facts)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("evals/summarize_inquiry/results.tsv"))
    args = parser.parse_args()

    ok, why = backends.ready()
    if not ok:
        print(f"跑不了:{why}", file=sys.stderr)
        return 2
    rows = [
        json.loads(line) for line in args.dataset.read_text("utf-8").splitlines() if line.strip()
    ]
    rows = rows[: args.limit] if args.limit else rows
    if not rows:
        print("数据集是空的", file=sys.stderr)
        return 2

    judge_client = None
    if not args.no_judge:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("没有 ANTHROPIC_API_KEY,裁判跑不了——只报确定性指标(不拿被测模型给自己打分)")
            args.no_judge = True
        else:
            import anthropic

            judge_client = anthropic.Anthropic()

    malformed = hallucinated = inquiry_ok = covered_total = facts_total = 0
    lines = ["id\ttrap\t不合规\t幻觉\tis_inquiry对\t覆盖\t摘要"]
    for row in rows:
        ref = row["reference"]
        try:
            result = summarize(row["source"])
        except backends.LLMError as exc:
            malformed += 1
            reason = str(exc).replace("\t", " ").replace("\n", " ")[:120]
            lines.append(f"{row['id']}\t{row.get('trap', '')}\tYES\t\t\t\t{reason}")
            print(f"  {row['id']}  ✘ 不合规:{reason}")
            continue
        s = result.summary
        bad = not result.trustworthy
        hallucinated += int(bad)
        right = s.is_inquiry == ref["is_inquiry"]
        inquiry_ok += int(right)
        cov = "-"
        if judge_client:
            covered = judge(judge_client, s.summary_zh, ref["facts"])
            covered_total += sum(covered)
            facts_total += len(covered)
            cov = f"{sum(covered)}/{len(covered)}"
        flag = ",".join(result.unverified)
        clean = s.summary_zh.replace("\t", " ").replace("\n", " ")
        lines.append(f"{row['id']}\t{row.get('trap', '')}\t\t{flag}\t{right}\t{cov}\t{clean}")
        print(
            f"  {row['id']}  幻觉={flag or '无'}  is_inquiry={'对' if right else '错'}  覆盖={cov}"
        )

    total, answered = len(rows), len(rows) - malformed
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"\n=== {backends.describe()} · 确定性指标 ===")
    print(f"  不合规率    {malformed}/{total} = {malformed / total:.1%}  ← 及格线 0%")
    if answered:
        print(
            f"  幻觉率      {hallucinated}/{answered} = {hallucinated / answered:.1%}  ← 及格线 0%"
        )
        print(f"  is_inquiry  {inquiry_ok}/{answered} = {inquiry_ok / answered:.1%}")
    if facts_total:
        print("\n=== 估计值(裁判 Claude,务必抽查)===")
        print(f"  事实覆盖率  {covered_total}/{facts_total} = {covered_total / facts_total:.1%}")
    print(f"\n逐条对照:{args.out}")
    return 1 if (hallucinated or malformed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
