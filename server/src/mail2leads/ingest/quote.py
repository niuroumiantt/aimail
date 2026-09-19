"""把一封信切成「本封新增」和「引用的历史」。

业务员要看的是新增的那几行;历史折叠。切分是确定性的:认几种常见的分隔线,
再认以 > 开头的行。认不出来就整封当新增——宁可多显示,不能把新内容藏进历史。
"""

from __future__ import annotations

import re

SEPARATORS = [
    # Gmail / Apple Mail:On Fri, 12 Sep 2026 at 15:20, X <x@y> wrote:(可能折成两行)
    re.compile(r"^On [^\n]{1,200}?(?:\n[^\n]{1,200}?)?wrote:\s*$", re.M),
    # Outlook:-----Original Message-----
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}\s*$", re.M | re.I),
    # Outlook 块:From: … 紧跟 Sent:/Date:
    re.compile(r"^From:[^\n]*\n(?:Sent|Date):", re.M),
    # 中文客户端:在 2026年9月12日 … 写道:
    re.compile(r"^在[^\n]{1,120}写道[:：]\s*$", re.M),
    # 中文 Outlook:发件人: …
    re.compile(r"^发件人[:：]", re.M),
    # 原始邮件 / Forwarded message
    re.compile(r"^-{3,}\s*(?:原始邮件|Forwarded message)\s*-{3,}\s*$", re.M | re.I),
]


def split(text: str) -> tuple[str, str]:
    """返回 (新增, 引用)。没有引用时第二项为空串。"""
    cut = len(text)
    for pattern in SEPARATORS:
        m = pattern.search(text)
        if m and m.start() < cut:
            cut = m.start()
    quoted_line = re.search(r"^\s*>", text, re.M)
    if quoted_line and quoted_line.start() < cut:
        cut = quoted_line.start()
    return text[:cut].rstrip(), text[cut:].strip()
