"""Synthetic caption contract and optional live semantic review examples."""

import json
import sys
from pathlib import Path

from aimail.tasks.list_caption import Caption, generate


def main():
    cases = [
        json.loads(s)
        for s in Path(__file__).with_name("dataset.sample.jsonl").read_text().splitlines()
    ]
    for i, case in enumerate(cases):
        Caption(id=i, text_zh=case["expected"])
    if "--live" in sys.argv:
        from aimail import backends

        result = generate(
            [{"id": i, "backend": backends.backend(), **case} for i, case in enumerate(cases)]
        )
        for i, text in result.items():
            print(cases[i]["subject"], "=>", text)
    print(f"PASS {len(cases)} single-line Chinese description cases")


if __name__ == "__main__":
    main()
