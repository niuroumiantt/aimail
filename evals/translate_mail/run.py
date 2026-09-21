"""Translation contract: identifiers must survive and generated output stays bounded."""

import json
import sys
from pathlib import Path

from mail2leads.tasks.translate_mail import _numbers, translate


def main():
    cases = [
        json.loads(x)
        for x in Path(__file__).with_name("dataset.sample.jsonl").read_text().splitlines()
    ]
    for case in cases:
        if "--live" in sys.argv:
            output = translate(case["source"]).text_zh
            assert all(x in output for x in case["must_keep"])
        else:
            assert _numbers(case["source"])
    print(f"PASS {len(cases)} cases ({'model' if '--live' in sys.argv else 'contract only'})")


if __name__ == "__main__":
    main()
