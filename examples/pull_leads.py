#!/usr/bin/env python3
"""只凭接口拿确认过的线索——给 OA / PO / 合同系统接线的样例,只用标准库。

    MAIL2LEADS_URL=http://mini:8900 MAIL2LEADS_TOKEN=... python examples/pull_leads.py
    python examples/pull_leads.py --since 2026-09-01T00:00:00+00:00 --status won --json

接口说明见 docs/api/v1.md。拿到的永远是人确认过的事实,不是模型的建议。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request

COLUMNS = ("id", "status", "company", "contact", "email", "wants", "quantity", "updated_at")


def fetch(base_url: str, token: str, since: str = "", after: int = 0, status: str = "") -> dict:
    params = {k: v for k, v in (("since", since), ("after", after), ("status", status)) if v}
    url = base_url.rstrip("/") + "/v1/leads"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="", help="上一页的 next_since(ISO 8601)")
    parser.add_argument("--after", type=int, default=0, help="上一页的 next_after(线索 id)")
    parser.add_argument("--status", default="", help="quote / quoted / following / won / lost")
    parser.add_argument("--json", action="store_true", help="原样输出 JSON,不转 CSV")
    args = parser.parse_args(argv)
    base_url, token = os.environ.get("MAIL2LEADS_URL", ""), os.environ.get("MAIL2LEADS_TOKEN", "")
    if not base_url or not token:
        print("要设 MAIL2LEADS_URL 与 MAIL2LEADS_TOKEN", file=sys.stderr)
        return 2
    data = fetch(base_url, token, args.since, args.after, args.status)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    writer = csv.writer(sys.stdout)
    writer.writerow(COLUMNS)
    for lead in data["leads"]:
        writer.writerow([lead[k] for k in COLUMNS])
    print(f"next_since={data['next_since']} next_after={data['next_after']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
