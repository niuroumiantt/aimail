#!/usr/bin/env python3
"""在标注集上跑 draft_reply:报不合规率、幻觉率、语言对、有没有偷偷报价。

uv run python evals/draft_reply/run.py evals/draft_reply/dataset.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server" / "src"))

from mail2leads import backends  # noqa: E402
from mail2leads.tasks.draft_reply import draft_reply  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--out", type=Path, default=Path("evals/draft_reply/results.tsv"))
    args = parser.parse_args()
    ok, why = backends.ready()
    if not ok:
        print(f"跑不了:{why}", file=sys.stderr)
        return 2
    rows = [
        json.loads(line) for line in args.dataset.read_text("utf-8").splitlines() if line.strip()
    ]
    malformed = hallucinated = lang_ok = leaked = 0
    lines = ["id\ttrap\t不合规\t幻觉\t语言对\t偷报价\t正文"]
    for row in rows:
        ref = row["reference"]
        try:
            result = draft_reply(row["source"])
        except backends.LLMError as exc:
            malformed += 1
            lines.append(f"{row['id']}\t{row.get('trap', '')}\tYES\t\t\t\t{str(exc)[:100]}")
            continue
        d = result.draft
        hallucinated += int(bool(result.unverified))
        lang = d.language.lower().startswith(ref["language"])
        lang_ok += lang
        leak = any(token.lower() in d.body.lower() for token in ref.get("must_not_contain", []))
        leaked += leak
        body = d.body.replace("\t", " ").replace("\n", " ")
        unverified = ",".join(result.unverified)
        lines.append(f"{row['id']}\t{row.get('trap', '')}\t\t{unverified}\t{lang}\t{leak}\t{body}")
        print(
            f"  {row['id']}  幻觉={unverified or '无'}  语言={'对' if lang else '错'}  "
            f"偷报价={'是' if leak else '否'}"
        )
    n, answered = len(rows), len(rows) - malformed
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"\n=== {backends.describe()} · draft_reply ===")
    print(f"  不合规率  {malformed}/{n} = {malformed / n:.1%}  ← 及格线 0%")
    if answered:
        print(f"  幻觉率    {hallucinated}/{answered} = {hallucinated / answered:.1%}  ← 及格线 0%")
        print(f"  语言对    {lang_ok}/{answered}   偷报价 {leaked}/{answered}  ← 及格线 0")
    return 1 if (malformed or hallucinated or leaked) else 0


if __name__ == "__main__":
    raise SystemExit(main())
