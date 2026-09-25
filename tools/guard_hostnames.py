#!/usr/bin/env python3
"""守卫:适配器目录之外不出现主机名、内网地址或别的仓库的名字(宪法第八条)。

外物只借不靠:系统不依赖任何特定机器、网关或别的仓库的存在。
知道"Spark 在哪"的只有 server/src/aimail/backends/,别处一律通过配置拿地址。

用法:python tools/guard_hostnames.py [server/src web/src]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_DIR = "backends"
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".sql", ".toml", ".json"}
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\.ts\.net\b"), "tailnet 域名"),
    (re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b"), "tailnet 地址"),
    (re.compile(r"\b(?:192\.168|10)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "内网地址"),
    (re.compile(r"\b(?:dgx|spark-lan|macmini)\b"), "机器名"),
    (re.compile(r"niuroumiantt/(?:oa|infra)\b|\bkeel\b"), "别的仓库"),
]


def check(roots: list[Path]) -> list[str]:
    problems: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            rel = path.relative_to(root.parent)
            if ALLOWED_DIR in rel.parts:
                continue
            for no, line in enumerate(path.read_text("utf-8").splitlines(), 1):
                for pattern, what in PATTERNS:
                    if pattern.search(line):
                        problems.append(
                            f"{rel}:{no}: {what}只许出现在 {ALLOWED_DIR}/,别处通过配置拿"
                        )
    return problems


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in (argv[1:] or ["server/src", "web/src"])]
    problems = check(roots)
    for p in problems:
        print(p)
    print(f"guard_hostnames: {'✘ ' + str(len(problems)) + ' 处违规' if problems else '✔ 干净'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
