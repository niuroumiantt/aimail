"""model task: extract_lead —— 从一封确认是询盘的信里提出线索建议。

建议不是事实(宪法第五条):这里的输出进 lead_suggestion,人点确认才进 lead。
数字照样回原文核对——线索里的数量编错了,比没有线索更贵。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from mail2leads import backends
from mail2leads.verify.numbers import unverified_numbers

TASK_VERSION = "extract_lead@1"

SYSTEM = """你在帮一家做外贸的小公司从客户询盘里提线索。

从邮件里提出这几项,邮件没说的写"未提及",绝不推测:
- company:客户公司名(签名、域名、正文里出现的)
- contact:联系人姓名
- wants:要什么,一句话,带关键型号或规格
- quantity:数量,原样照抄邮件写法(例如 "48 台"、"1,000 pcs"、"10-15 pieces")
- region:客户所在城市或国家
- priority:high(有明确数量、型号、交期或紧急字眼)/ normal(一般询价)/ low(只有品类、没有数量或型号)
- quoted_numbers:你在以上各项里引用的每个数字、型号、价格、日期,原样照抄

正文后面标着「引用的历史」的部分只用来理解上下文。"""


class LeadExtraction(BaseModel):
    company: str = Field(description="客户公司名")
    contact: str = Field(description="联系人姓名")
    wants: str = Field(description="要什么,一句话")
    quantity: str = Field(description="数量,原样照抄")
    region: str = Field(description="城市或国家")
    priority: Literal["high", "normal", "low"] = Field(description="优先级")
    quoted_numbers: list[str] = Field(description="引用的所有数字/型号/价格/日期")


@dataclass(frozen=True)
class LeadResult:
    lead: LeadExtraction
    unverified: tuple[str, ...]
    backend: str


def extract_lead(source: str) -> LeadResult:
    lead = backends.complete(SYSTEM, source, LeadExtraction)
    assert isinstance(lead, LeadExtraction)
    return LeadResult(
        lead=lead,
        unverified=unverified_numbers(lead.quoted_numbers, source),
        backend=backends.describe(),
    )
