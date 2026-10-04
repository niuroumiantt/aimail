#!/usr/bin/env python3
"""在标注集上跑 summarize_inquiry，报告分类和引用数字核验指标。

    uv run python evals/summarize_inquiry/run.py evals/summarize_inquiry/dataset.jsonl --no-judge
    LOCAL_MODEL=brain uv run python evals/summarize_inquiry/run.py ... --out .../brain.tsv

结构合规、引用数字核验和人工分类标签由代码评分；覆盖率由 Claude 当裁判，是估计值。
引用数字核验不代表所有语义都正确。裁判绝不是被测模型本身。
数字未通过、有不合规样本或分类不符时退出码非零；可保存真实模型基线比较。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server" / "src"))

from aimail import backends  # noqa: E402
from aimail.tasks.summarize import SYSTEM, TASK_VERSION, InquirySummary, summarize  # noqa: E402

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
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--baseline", type=Path, help="同一数据集的真实模型基线 JSON")
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
    dataset_hash = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    model_label = backends.describe()
    baseline = None
    if args.baseline:
        try:
            baseline = json.loads(args.baseline.read_text("utf-8"))
            compatible = (
                baseline["dataset_sha256"] == dataset_hash
                and baseline["model"] == model_label
                and baseline["sample_count"] == len(rows)
                and [p["id"] for p in baseline["predictions"]] == [r["id"] for r in rows]
                and isinstance(baseline["metrics"], dict)
                and {"malformed", "unverified_numbers", "is_inquiry"} <= baseline["metrics"].keys()
            )
        except (OSError, ValueError, KeyError, TypeError):
            compatible = False
        if not compatible:
            print("基线模型、数据集或报告不一致，未调用模型", file=sys.stderr)
            return 2
    type_expected = sum("mail_type" in row["reference"] for row in rows)
    trade_expected = sum("is_trade" in row["reference"] for row in rows)
    role_expected = sum("trade_role" in row["reference"] for row in rows)

    judge_client = None
    if not args.no_judge:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("没有 ANTHROPIC_API_KEY,裁判跑不了——只报确定性指标(不拿被测模型给自己打分)")
            args.no_judge = True
        else:
            import anthropic

            judge_client = anthropic.Anthropic()

    malformed = hallucinated = inquiry_ok = covered_total = facts_total = 0
    type_ok = type_total = 0
    trade_ok = trade_total = role_ok = role_total = 0
    predictions = []
    lines = [
        "id\ttrap\t不合规\t引用数字未核验\tis_inquiry对\tis_trade对\ttrade_role对"
        "\t覆盖\t摘要\tmail_type对\tmail_type\tis_trade\ttrade_role\t耗时秒"
    ]
    started = time.monotonic()
    for row in rows:
        ref = row["reference"]
        sample_started = time.monotonic()
        try:
            result = summarize(row["source"])
        except backends.LLMError as exc:
            elapsed = time.monotonic() - sample_started
            malformed += 1
            reason = str(exc).replace("\t", " ").replace("\n", " ")[:120]
            lines.append(
                f"{row['id']}\t{row.get('trap', '')}\tYES\t\t\t\t\t\t{reason}"
                f"\t\t\t\t\t{elapsed:.3f}"
            )
            predictions.append(
                {"id": row["id"], "status": "failed", "reason": reason, "elapsed_seconds": elapsed}
            )
            print(f"  {row['id']}  ✘ 不合规:{reason}")
            continue
        elapsed = time.monotonic() - sample_started
        s = result.summary
        bad = not result.trustworthy
        hallucinated += int(bad)
        right = s.is_inquiry == ref["is_inquiry"]
        inquiry_ok += int(right)
        predicted_type = (
            "inquiry" if s.is_inquiry else (s.mail_type if s.mail_type != "inquiry" else "other")
        )
        # @4 没有明确交易字段，基线沿用旧界面的 inquiry/business 判定。
        # 这只是旧合同兼容，不从正文用关键词猜测语义。
        explicit_trade = getattr(s, "is_trade", None)
        predicted_trade = s.is_inquiry or (
            explicit_trade if explicit_trade is not None else predicted_type == "business"
        )
        predicted_role = getattr(s, "trade_role", None)
        if predicted_role is None:
            predicted_role = (
                "buyer" if s.is_inquiry else ("transaction" if predicted_trade else "none")
            )
        trade_right = role_right = type_right = "-"
        if "is_trade" in ref:
            trade_total += 1
            trade_right = predicted_trade == ref["is_trade"]
            trade_ok += int(trade_right)
        if "trade_role" in ref:
            role_total += 1
            role_right = predicted_role == ref["trade_role"]
            role_ok += int(role_right)
        if "mail_type" in ref:
            type_total += 1
            type_right = predicted_type == ref["mail_type"]
            type_ok += int(type_right)
        cov = "-"
        if judge_client:
            covered = judge(judge_client, s.summary_zh, ref["facts"])
            covered_total += sum(covered)
            facts_total += len(covered)
            cov = f"{sum(covered)}/{len(covered)}"
        flag = ",".join(result.unverified)
        clean = s.summary_zh.replace("\t", " ").replace("\n", " ")
        lines.append(
            f"{row['id']}\t{row.get('trap', '')}\t\t{flag}\t{right}\t{trade_right}"
            f"\t{role_right}\t{cov}\t{clean}\t{type_right}\t{predicted_type}"
            f"\t{predicted_trade}\t{predicted_role}\t{elapsed:.3f}"
        )
        predictions.append(
            {
                "id": row["id"],
                "status": "ok",
                "is_inquiry": s.is_inquiry,
                "is_trade": predicted_trade,
                "trade_role": predicted_role,
                "mail_type": predicted_type,
                "unverified": list(result.unverified),
                "parsed_output": s.model_dump(mode="json"),
                "elapsed_seconds": elapsed,
            }
        )
        actual = {
            "is_inquiry": s.is_inquiry,
            "mail_type": predicted_type,
            "is_trade": predicted_trade,
            "trade_role": predicted_role,
        }
        diagnostic = "  ".join(
            f"{field}={value} expected={ref[field]} [{'对' if value == ref[field] else '错'}]"
            for field, value in actual.items()
            if field in ref
        )
        print(f"  {row['id']}  {diagnostic}  引用数字未核验={flag or '无'}  覆盖={cov}")

    total, answered = len(rows), len(rows) - malformed
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"\n=== {model_label} · 确定性指标 ===")
    print(f"  不合规率    {malformed}/{total} = {malformed / total:.1%}  ← 及格线 0%")
    if answered:
        print(
            f"  引用数字未核验率 {hallucinated}/{answered} = {hallucinated / answered:.1%}"
            "  ← 及格线 0%"
        )
        print(f"  is_inquiry  {inquiry_ok}/{answered} = {inquiry_ok / answered:.1%}")
    if type_total:
        print(f"  mail_type   {type_ok}/{type_total} = {type_ok / type_total:.1%}")
    if trade_total:
        print(f"  is_trade    {trade_ok}/{trade_total} = {trade_ok / trade_total:.1%}")
    if role_total:
        print(f"  trade_role  {role_ok}/{role_total} = {role_ok / role_total:.1%}")
    if facts_total:
        print("\n=== 估计值(裁判 Claude,务必抽查)===")
        print(f"  事实覆盖率  {covered_total}/{facts_total} = {covered_total / facts_total:.1%}")
    print(f"\n逐条对照:{args.out}")
    metrics = {
        "malformed": malformed / total,
        "unverified_numbers": hallucinated / answered if answered else 1,
        "is_inquiry": inquiry_ok / total,
        "mail_type": type_ok / type_expected if type_expected else None,
        "is_trade": trade_ok / trade_expected if trade_expected else None,
        "trade_role": role_ok / role_expected if role_expected else None,
    }
    report = {
        "model": model_label,
        "model_identity": "configured route; resolved upstream model ID is not exposed",
        "task_version": TASK_VERSION,
        "system_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(
                InquirySummary.model_json_schema(), ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest(),
        "dataset_sha256": dataset_hash,
        "sample_count": total,
        "elapsed_seconds": time.monotonic() - started,
        "metrics": metrics,
        "predictions": predictions,
    }
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
    regressed = False
    if baseline:
        for key, score in metrics.items():
            before = baseline["metrics"].get(key)
            if score is None or before is None:
                continue
            failed = (
                score > before if key in {"malformed", "unverified_numbers"} else score < before
            )
            if failed:
                regressed = True
                print(f"指标倒退：{key} {before:.1%} → {score:.1%}", file=sys.stderr)
    return (
        1
        if (
            hallucinated
            or malformed
            or inquiry_ok != answered
            or type_ok != type_total
            or trade_ok != trade_total
            or role_ok != role_total
            or regressed
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
