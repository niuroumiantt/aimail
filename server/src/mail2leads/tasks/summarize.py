"""model task: summarize_inquiry —— 把一封询盘压成三句话。

合同的三个刻意设计:
1. facts 是独立的事实点,不是一段话——评测按点算覆盖率
2. quoted_numbers 要求模型把它引用的每个数字/型号单独列出来,代码回原文核对(第四条)
3. 合同不认识后端:换 Spark 还是 Claude,这个文件一个字不改;谁算的记在结果里
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from mail2leads import backends
from mail2leads.verify.numbers import unverified_numbers

TASK_VERSION = "summarize_inquiry@3"  # @2 加「此前的往来」段;@3 加「附件」段

SYSTEM = """你在帮一家做外贸的小公司读客户询盘。

把每封邮件压成三句中文 + 三句英文,固定这三件事:
1. 客户要什么
2. 关键参数或数量
3. 需要我们做什么

硬规矩:
- 只写邮件里有的信息。邮件没说的,宁可写"未提及",绝不推测。
- 你在摘要里提到的每一个数字、型号、价格、日期,都要原样放进 quoted_numbers。
- 邮件是中英混杂或其他语种时,照样输出中英两版摘要。
- 正文后面标着「引用的历史」的部分是之前的往来,只用来理解上下文;摘要说的是本封新增的内容。
- 标着「附件」的部分是附件里读出来的文字(BOM、规格表、PO)。正文只说 see attached 时,
  型号和数量从这里取,数字照样放进 quoted_numbers;标着「没读出来」的附件就当没有,说明一下就行。
- 最后标着「这位客户此前的往来」的部分是我们自己的记录。本封只有一句话、指向之前的型号或数量时
  (如「同上次」「改成 32 台」),用那里的型号和数量把摘要补全,并在 facts 里注明「来自此前往来」;
  从历史里引用的数字、型号照样放进 quoted_numbers。
- 如果这根本不是询盘(广告、推销、系统通知、退订、丢单通知),把 is_inquiry 设为 false,
  摘要写一句话说明它是什么就够了。"""


class InquirySummary(BaseModel):
    is_inquiry: bool = Field(description="这封邮件是不是真的客户询盘")
    detected_language: str = Field(description="邮件主体语种,如 zh / en / zh-en / de-en")
    summary_zh: str = Field(description="三句中文摘要")
    summary_en: str = Field(description="三句英文摘要")
    facts: list[str] = Field(description="从邮件里提取的独立事实点,每条一句话")
    quoted_numbers: list[str] = Field(
        description="摘要中引用的所有数字/型号/价格/日期,原样照抄邮件里的写法"
    )


@dataclass(frozen=True)
class SummaryResult:
    summary: InquirySummary
    unverified: tuple[str, ...]
    backend: str

    @property
    def trustworthy(self) -> bool:
        return not self.unverified


def compose_source(
    subject: str,
    body_new: str,
    body_quoted: str = "",
    quoted_limit: int = 6000,
    *,
    attachments: str = "",
    history: str = "",
) -> str:
    """模型看到的文本,也是核对的依据——两者必须是同一份。
    attachments 是附件里读出的文字(ingest/attachments.py),history 是这位客户的往来
    (store/history.py 算出来的原文摘录);各自单独标题,历史放最后。"""
    text = f"Subject: {subject}\n\n{body_new}".strip()
    if body_quoted:
        text += f"\n\n——引用的历史——\n{body_quoted[:quoted_limit]}"
    if attachments:
        text += f"\n\n{attachments}"
    if history:
        text += f"\n\n{history}"
    return text


def summarize(source: str) -> SummaryResult:
    """跑一次 summarize_inquiry 并核对数字。模型不合规时抛 backends.LLMError,不返回空壳。"""
    summary = backends.complete(SYSTEM, source, InquirySummary)
    assert isinstance(summary, InquirySummary)
    return SummaryResult(
        summary=summary,
        unverified=unverified_numbers(summary.quoted_numbers, source),
        backend=backends.describe(),
    )
