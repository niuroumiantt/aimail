"""测试公用:内存库、一个邮箱、造 RFC822 原文的工具。"""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime

import pytest

from aimail.store import repo
from aimail.store.db import connect


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def mailbox(conn) -> int:
    return repo.ensure_mailbox(conn, "sales@example.test", "Sales")


def make_raw(
    *,
    subject: str = "RFQ",
    from_: str = "Mikko Laine <mikko@aurora.test>",
    to: str = "sales@example.test",
    body: str = "Hello",
    message_id: str = "<a@aurora.test>",
    in_reply_to: str = "",
    references: str = "",
    date: datetime | None = None,
    html: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_
    msg["To"] = to
    msg["Message-ID"] = message_id
    msg["Date"] = format_datetime(date or datetime(2026, 9, 19, 8, 12, tzinfo=UTC))
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    if html is not None and not body:
        msg.set_content(html, subtype="html")
    else:
        msg.set_content(body)
        if html is not None:
            msg.add_alternative(html, subtype="html")
    for filename, content, ctype in attachments or []:
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    return msg.as_bytes()
