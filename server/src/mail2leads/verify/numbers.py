"""确定性核对:模型引用的每个数字都要能在原文里找到(宪法第四条)。

不调模型、纯函数。千分位逗号和空白抹平,免得 1,000 和 1000 被误判成两个数。
"""

from __future__ import annotations

import re


def _normalize(text: str) -> str:
    return re.sub(r"[\s,，]", "", text)


def unverified_numbers(quoted: list[str], source: str) -> tuple[str, ...]:
    """返回原文里找不到的引用值。空元组 = 通过。"""
    haystack = _normalize(source)
    return tuple(n for n in quoted if n and _normalize(n) not in haystack)
