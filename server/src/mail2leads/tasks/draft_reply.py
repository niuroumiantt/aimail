"""model task: draft_reply —— 给一封询盘起一封回信的草稿。

草稿是给人改的,不是给客户看的:发送只能由人点(宪法第二条),这里连发送函数都 import 不到。
硬规矩写进提示词:不报价、不承诺交期、缺的信息问清楚;数字照样回原文核对。
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from mail2leads import backends
from mail2leads.verify.numbers import unverified_numbers

TASK_VERSION = "draft_reply@1"

SYSTEM = """你在帮一家做外贸的小公司(卖服务器、内存、GPU、存储等数据中心硬件)给客户回信。
写的是**草稿**,业务员会改完再发。

回信要做的事,按顺序:
1. 确认收到,用一句话复述客户要什么(型号、数量、条件),让客户知道我们看懂了
2. 缺什么信息就问清楚(交货地、数量、预算、要不要保修、目标价、时间)
3. 说明下一步:我们会在多久内给正式报价(写"within 1–2 business days"这类,不要具体日期)
4. 署名留 [姓名] 占位,业务员自己填

硬规矩:
- 绝不报价、绝不承诺交期、绝不承诺库存——这些由人决定
- 用客户来信的语言写(英文来信英文回,中文来信中文回,混杂就用英文)
- 你引用的每个数字、型号,都要原样放进 quoted_numbers;邮件里没有的数字一个都不要写
- 语气:专业、简短、具体。不要套话堆砌。"""


class ReplyDraft(BaseModel):
    language: str = Field(description="回信语言,如 en / zh")
    subject: str = Field(description="回信主题,通常是 Re: 原主题")
    body: str = Field(description="回信正文,纯文本,含 [姓名] 占位")
    open_questions: list[str] = Field(description="回信里向客户提出的问题,每条一句")
    quoted_numbers: list[str] = Field(description="正文里引用的所有数字/型号,原样照抄")


@dataclass(frozen=True)
class DraftResult:
    draft: ReplyDraft
    unverified: tuple[str, ...]
    backend: str


def draft_reply(source: str) -> DraftResult:
    draft = backends.complete(SYSTEM, source, ReplyDraft)
    assert isinstance(draft, ReplyDraft)
    return DraftResult(
        draft=draft,
        unverified=unverified_numbers(draft.quoted_numbers, source),
        backend=backends.describe(),
    )
