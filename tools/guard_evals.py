#!/usr/bin/env python3
"""守卫:每个模型任务必须有评测集(宪法第七条:评测先于提示词)。

约定:server/src/mail2leads/tasks/ 下声明了 `TASK_VERSION = "<name>@N"` 的模块是模型任务;
evals/<name>/ 必须存在,且带 run.py 和 dataset.sample.jsonl(编的示例;真实数据 gitignore)。

用法:python tools/guard_evals.py [tasks目录] [evals目录]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_VERSION = re.compile(r'^TASK_VERSION\s*=\s*"([a-z_][a-z0-9_]*)@\d+"', re.M)


def check(tasks_dir: Path, evals_dir: Path) -> list[str]:
    problems: list[str] = []
    for module in sorted(tasks_dir.glob("*.py")):
        for name in TASK_VERSION.findall(module.read_text("utf-8")):
            folder = evals_dir / name
            for required in ("run.py", "dataset.sample.jsonl"):
                if not (folder / required).exists():
                    problems.append(
                        f"任务 {name}({module.name})没有 {folder / required}:没有评测集的任务不上线"
                    )
    return problems


def main(argv: list[str]) -> int:
    tasks_dir = Path(argv[1] if len(argv) > 1 else "server/src/mail2leads/tasks")
    evals_dir = Path(argv[2] if len(argv) > 2 else "evals")
    problems = check(tasks_dir, evals_dir) if tasks_dir.exists() else []
    for p in problems:
        print(p)
    verdict = f"✘ {len(problems)} 处违规" if problems else "✔ 每个任务都有评测集"
    print(f"guard_evals: {verdict}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
