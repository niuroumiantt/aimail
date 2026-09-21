"""Grounding regression baseline; --live additionally evaluates the configured model."""

import json
import sys
from pathlib import Path

from mail2leads import backends
from mail2leads.tasks.ask_mailbox import Answer, ask, validate_answer


def main():
    cases = [
        json.loads(line)
        for line in Path(__file__).with_name("dataset.sample.jsonl").read_text().splitlines()
    ]
    for index, case in enumerate(cases):
        sources = [
            {**s, "thread_id": s["id"], "subject": "Fixture", "sent_at": ""}
            for s in case["sources"]
        ]
        if "--live" in sys.argv:
            result = ask(case["question"], sources, [])
            assert sorted({f["source_id"] for f in result}) == case["expected_ids"]
            assert not any(f["unverified"] for f in result)
            if index == 2:
                assert all("999" not in f["text"] for f in result)
            print(f"PASS model case {index + 1}", flush=True)
        else:
            for source in sources:
                valid = Answer(
                    findings=[
                        {"text": "有原文依据", "source_id": source["id"], "quote": source["text"]}
                    ]
                )
                assert len(validate_answer(valid, sources)) == 1
            try:
                validate_answer(
                    Answer(findings=[{"text": "错误", "source_id": 999, "quote": "invented"}]),
                    sources,
                )
            except backends.LLMError:
                pass
            else:
                raise AssertionError("Fabricated citation accepted")
    mode = "model" if "--live" in sys.argv else "grounding contract only"
    print(f"PASS: {len(cases)} cases ({mode})")


if __name__ == "__main__":
    main()
