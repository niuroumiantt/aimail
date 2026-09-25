#!/usr/bin/env python3
"""守卫:派生表必须带四个署名字段(宪法第三条:派生物有署名)。

约定:schema.sql 里,独占一行的 `-- derived` 标记之后的 CREATE TABLE 是派生表。
它必须含 model、task_version、produced_at、source_id 四列,且都 NOT NULL。
没有署名的 AI 输出不许落库,更不许显示。

用法:python tools/guard_attribution.py [schema.sql]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_SCHEMA = Path("server/src/aimail/store/schema.sql")
REQUIRED = ("model", "task_version", "produced_at", "source_id")
# 标记必须独占一行:注释里顺嘴提到「-- derived」不算
DERIVED = re.compile(
    r"^[ \t]*--[ \t]*derived[ \t]*$\s*CREATE TABLE(?: IF NOT EXISTS)?\s+(\w+)\s*\((.*?)\)\s*;",
    re.S | re.I | re.M,
)


def check(schema_text: str) -> list[str]:
    problems: list[str] = []
    for name, body in DERIVED.findall(schema_text):
        for column in REQUIRED:
            if not re.search(rf"\b{column}\b[^,\n]*\bNOT NULL\b", body, re.I):
                problems.append(f"派生表 {name} 缺少 NOT NULL 的署名字段 {column}")
    return problems


def main(argv: list[str]) -> int:
    schema = Path(argv[1] if len(argv) > 1 else DEFAULT_SCHEMA)
    if not schema.exists():
        print("guard_attribution: 尚无 schema.sql,M2 起生效")
        return 0
    problems = check(schema.read_text("utf-8"))
    for p in problems:
        print(p)
    verdict = f"✘ {len(problems)} 处违规" if problems else "✔ 派生表都有署名"
    print(f"guard_attribution: {verdict}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
