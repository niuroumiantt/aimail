"""RFC822 字节 → 结构。只用标准库。解析失败不丢原文——原文由调用方先落库。"""

from __future__ import annotations

import email
import hashlib
import re
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class Parsed:
    message_id: str
    in_reply_to: str
    references: tuple[str, ...]
    subject: str
    from_name: str
    from_email: str
    to_emails: tuple[str, ...]
    sent_at: str
    text: str
    attachments: tuple[Attachment, ...]


class _HtmlText(HTMLParser):
    """HTML 邮件退化成文本:块级标签换行,脚本样式丢掉,其余只留文字。"""

    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "blockquote", "table"}
    SKIP = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        return re.sub(r"\n{3,}", "\n\n", joined).strip()


def html_to_text(html: str) -> str:
    p = _HtmlText()
    p.feed(html)
    return p.text()


def _message_ids(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"<[^<>]+>", value or ""))


def _body_text(msg: EmailMessage) -> str:
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        return ""
    content = body.get_content()
    if body.get_content_type() == "text/html":
        return html_to_text(content)
    return str(content).replace("\r\n", "\n").strip()


def parse(raw: bytes) -> Parsed:
    msg = email.message_from_bytes(raw, policy=policy.default)
    assert isinstance(msg, EmailMessage)

    from_name, from_email = parseaddr(str(msg.get("From", "")))
    to_emails = tuple(
        addr for _, addr in getaddresses([str(msg.get("To", "")), str(msg.get("Cc", ""))]) if addr
    )

    sent_at = ""
    if msg.get("Date"):
        try:
            sent_at = parsedate_to_datetime(str(msg["Date"])).isoformat()
        except (TypeError, ValueError):
            sent_at = ""

    mids = _message_ids(str(msg.get("Message-ID", "")))
    message_id = mids[0] if mids else f"sha256:{hashlib.sha256(raw).hexdigest()}"
    in_reply_to = (_message_ids(str(msg.get("In-Reply-To", ""))) or ("",))[0]

    attachments = tuple(
        Attachment(
            filename=part.get_filename() or "unnamed",
            content_type=part.get_content_type(),
            content=part.get_payload(decode=True) or b"",
        )
        for part in msg.iter_attachments()
    )

    return Parsed(
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=_message_ids(str(msg.get("References", ""))),
        subject=str(msg.get("Subject", "")).strip(),
        from_name=from_name.strip(),
        from_email=from_email.strip().lower(),
        to_emails=tuple(a.lower() for a in to_emails),
        sent_at=sent_at,
        text=_body_text(msg),
        attachments=attachments,
    )
