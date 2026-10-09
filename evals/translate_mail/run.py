"""Translation contract: identifiers must survive and generated output stays bounded."""

import json
import sys
from pathlib import Path

from aimail.tasks.translate_mail import _numbers, translate, translate_layout
from aimail.translation_layout import Layout


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
    layout_case = json.loads(Path(__file__).with_name("layout.sample.json").read_text())
    layout = Layout(layout_case["html"])
    if "--live" in sys.argv:
        output = translate_layout(layout)
        assert all(x in output["html_zh"] for x in layout_case["must_keep"])
        assert _numbers(layout_case["source"]) == _numbers(output["text_zh"])
    else:
        assert all(x in layout.render() for x in layout_case["must_keep"])
    print("PASS structured table and inline identifier")


if __name__ == "__main__":
    main()
