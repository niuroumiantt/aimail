"""Live synthetic evaluation; never writes CRM facts or sends mail."""

from __future__ import annotations

import json
from pathlib import Path

from aimail.tasks.register_contact import extract


def main():
    rows = [
        json.loads(line)
        for line in Path(__file__).with_name("dataset.sample.jsonl").read_text().splitlines()
    ]
    failed = 0
    for row in rows:
        result = extract([{"id": 1, "text": row["source"]}])
        good = not result["warnings"] and all(
            result["fields"][key].rstrip(".") == value.rstrip(".")
            if key == "company"
            else result["fields"][key] == value
            for key, value in row["reference"].items()
        )
        failed += not good
        print(row["id"], "PASS" if good else "FAIL")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
