#!/usr/bin/env python3
"""守卫:STATUS.md 里每个 ✅ 必须指向真实存在的测试。

能力只认机器验证。一行标 ✅ 却指不出测试名,或指的测试不存在,CI 就红。
测试名在「测试」列,逗号分隔;Python 找 `def 名(`,前端找 `it("名"` / `test("名"`。

用法:python tools/guard_status.py [STATUS.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PY_ROOTS = ("server/tests", "tools/tests")
TS_ROOTS = ("web/src",)


def parse_rows(text: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[1]) <= {"-", ":", ""} or cells[1] in {"状态"}:
            continue
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def test_exists(name: str, repo: Path) -> bool:
    py = re.compile(rf"^\s*def {re.escape(name)}\(", re.M)
    ts = re.compile(rf"""(?:\bit|\btest)\(\s*["'`]{re.escape(name)}["'`]""")
    for root in PY_ROOTS:
        for path in (repo / root).rglob("*.py"):
            if py.search(path.read_text("utf-8")):
                return True
    for root in TS_ROOTS:
        for path in (repo / root).rglob("*.test.ts*"):
            if ts.search(path.read_text("utf-8")):
                return True
    return False


def check(status_text: str, repo: Path) -> list[str]:
    problems: list[str] = []
    for capability, status, tests in parse_rows(status_text):
        if "✅" not in status:
            continue
        names = [n.strip() for n in re.split(r"[,，]", tests) if n.strip()]
        if not names:
            problems.append(f"「{capability}」标了 ✅ 却没有测试名——没有测试就写 ⏳")
            continue
        for name in names:
            if not test_exists(name, repo):
                problems.append(f"「{capability}」引用的测试 {name} 不存在")
    return problems


def main(argv: list[str]) -> int:
    status = Path(argv[1] if len(argv) > 1 else "STATUS.md")
    repo = status.resolve().parent
    problems = check(status.read_text("utf-8"), repo)
    for p in problems:
        print(p)
    verdict = f"✘ {len(problems)} 处违规" if problems else "✔ 每个 ✅ 都有测试"
    print(f"guard_status: {verdict}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
