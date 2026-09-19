#!/usr/bin/env python3
"""守卫:抄来的文件必须登记(宪法第八条:借,带署名)。

文件头(前 12 行)出现「来源:」或「Source:」即视为抄来的,必须在 THIRD_PARTY.md 登记路径;
THIRD_PARTY.md 登记的路径必须存在且带头。两边由这里核对,免得"抄了什么"过半年说不清。

用法:python tools/guard_third_party.py [THIRD_PARTY.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCAN_ROOTS = ("server/src", "web/src", "tools")
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".svg", ".sql", ".js", ".mjs"}
HEADER = re.compile(r"^\s*(?:#|//|/\*|\*|<!--|--)?\s*(?:来源|Source)\s*[:：]", re.M)
LISTED = re.compile(r"^\|\s*`?([^|`]+?)`?\s*\|", re.M)


def sourced_files(repo: Path) -> set[str]:
    found = set()
    for root in SCAN_ROOTS:
        base = repo / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in SCAN_SUFFIXES:
                head = "\n".join(path.read_text("utf-8", errors="replace").splitlines()[:12])
                if HEADER.search(head):
                    found.add(path.relative_to(repo).as_posix())
    return found


def listed_files(registry_text: str) -> set[str]:
    return {
        m.group(1).strip()
        for m in LISTED.finditer(registry_text)
        if m.group(1).strip() not in {"路径", "---", ""} and not set(m.group(1)) <= {"-", " "}
    }


def check(registry_text: str, repo: Path) -> list[str]:
    sourced, listed = sourced_files(repo), listed_files(registry_text)
    problems = [f"{p} 头上写了来源,但 THIRD_PARTY.md 没登记" for p in sorted(sourced - listed)]
    problems += [
        f"THIRD_PARTY.md 登记了 {p},但文件不存在或头上没写来源" for p in sorted(listed - sourced)
    ]
    return problems


def main(argv: list[str]) -> int:
    registry = Path(argv[1] if len(argv) > 1 else "THIRD_PARTY.md")
    problems = check(registry.read_text("utf-8"), registry.resolve().parent)
    for p in problems:
        print(p)
    verdict = f"✘ {len(problems)} 处违规" if problems else "✔ 登记与文件头一致"
    print(f"guard_third_party: {verdict}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
