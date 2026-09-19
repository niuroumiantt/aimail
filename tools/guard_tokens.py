#!/usr/bin/env python3
"""守卫:令牌之外禁字面色值与 Tailwind 任意值;pages/ 只许布局类。

宪法第九条(好看是功能)与 ADR-0002 的三条规则在这里落地:
1. 字面色值(#hex、rgb()、hsl()、oklch()…)只许出现在 web/src/tokens/
2. Tailwind 任意值(p-[7px]、bg-[#abc]、[&_svg]:…)一律禁止——那是绕过令牌的逃生口
3. web/src/pages/ 只许布局类;颜色、圆角、阴影、边框一律在组件里

用法:python tools/guard_tokens.py [web/src]
退出码非零 = 有违规,逐条列出 文件:行:原因。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOKENS_DIR = "tokens"
PAGES_DIR = "pages"
SCAN_SUFFIXES = {".ts", ".tsx", ".css"}

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
COLOR_FN = re.compile(r"\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\(")
ARBITRARY_VALUE = re.compile(r"(?<![\w-])[a-z][\w-]*-\[[^\]\n]+\]")
ARBITRARY_VARIANT = re.compile(r"(?<![\w])\[&[^\]\n]*\]:")
STRING = re.compile(r"""(["'`])((?:\\.|(?!\1).)*)\1""")
# pages 里 text-* 只许字号与排版;其余 text-xxx 一律视为颜色
TEXT_OK = re.compile(
    r"^text-(?:xs|sm|base|lg|[2-9]?xl|left|center|right|justify|balance|pretty|"
    r"nowrap|ellipsis|clip|wrap)$"
)
VISUAL = re.compile(
    r"^(?:bg|border|shadow|rounded|ring|fill|stroke|outline|divide|decoration|text)(?:-|$)"
)


def _class_tokens(line: str):
    """只看字符串字面量里的类名,去掉 hover:/dark: 这类前缀。"""
    for match in STRING.finditer(line):
        for token in match.group(2).split():
            yield token.split(":")[-1]


def check(root: Path) -> list[str]:
    problems: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(root)
        in_tokens = TOKENS_DIR in rel.parts
        in_pages = PAGES_DIR in rel.parts
        for no, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            if not in_tokens and (HEX.search(line) or COLOR_FN.search(line)):
                problems.append(f"{rel}:{no}: 字面色值只许出现在 {TOKENS_DIR}/")
            if ARBITRARY_VALUE.search(line) or ARBITRARY_VARIANT.search(line):
                problems.append(f"{rel}:{no}: Tailwind 任意值 [...] 是绕过令牌的逃生口,禁止")
            if in_pages:
                for cls in _class_tokens(line):
                    if VISUAL.match(cls) and not TEXT_OK.match(cls):
                        problems.append(f"{rel}:{no}: pages/ 只许布局类,`{cls}` 属于组件")
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "web/src")
    if not root.exists():
        print(f"guard_tokens: {root} 不存在,没有可查的")
        return 0
    problems = check(root)
    for p in problems:
        print(p)
    print(f"guard_tokens: {'✘ ' + str(len(problems)) + ' 处违规' if problems else '✔ 干净'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
