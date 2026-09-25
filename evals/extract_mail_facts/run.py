"""Run with --live for model evaluation; otherwise test grounding contracts."""

import json
import sys
from pathlib import Path

from aimail.tasks.extract_mail_facts import Extraction, extract, validate


def main():
    cases = [
        json.loads(s)
        for s in Path(__file__).with_name("dataset.sample.jsonl").read_text().splitlines()
    ]
    for case in cases:
        if "--live" in sys.argv:
            result = extract(case["source"])
            keys = {f["key"] for f in result}
            assert set(case["expected"]) <= keys
            assert not set(case["absent"]) & keys
        else:
            assert validate(Extraction(facts=[]), case["source"]) == []
            try:
                validate(
                    Extraction(
                        facts=[{"key": "price", "value": "999999", "quote": case["source"]}]
                    ),
                    case["source"],
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Invented value accepted")
    print(f"PASS {len(cases)} cases ({'model' if '--live' in sys.argv else 'grounding only'})")


if __name__ == "__main__":
    main()
