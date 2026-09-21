"""确定性核对:模型引用的每个数字都要能在原文里找到(宪法第四条)。

不调模型、纯函数。千分位逗号和空白抹平,免得 1,000 和 1000 被误判成两个数。
"""

from __future__ import annotations

import re


def _normalize(text: str) -> str:
    """Normalise only thousands separators.

    Removing every whitespace previously turned unrelated text such as ``10 00`` into a number and
    allowed ``32`` to match inside ``132``.  Whitespace is meaningful in prose; commas are not for
    the quantities we verify here.
    """
    return re.sub(r"[,，]", "", text)


def unverified_numbers(quoted: list[str], source: str) -> tuple[str, ...]:
    """返回原文里找不到的引用值。空元组 = 通过。"""
    haystack = _normalize(source)
    missing = []
    for value in quoted:
        needle = _normalize(value)
        if not needle:
            continue
        # A numeric value must not be a substring of another numeric value (32 != 132).
        boundary = r"(?<!\d)" if needle[0].isdigit() else ""
        tail = r"(?!\d)" if needle[-1].isdigit() else ""
        if not re.search(boundary + re.escape(needle) + tail, haystack, re.IGNORECASE):
            missing.append(value)
    return tuple(missing)
