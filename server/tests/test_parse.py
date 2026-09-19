"""攻击解析:主题编码、HTML 退化、附件、线程头。"""

from __future__ import annotations

from conftest import make_raw
from mail2leads.ingest.parse import html_to_text, parse


def test_plain_text_body_and_headers():
    p = parse(
        make_raw(
            subject="询价:DDR5 RDIMM ×200",
            body="您好,请报价。",
            from_="王婷 <wangting@huaxin.test>",
        )
    )
    assert p.subject == "询价:DDR5 RDIMM ×200"
    assert p.from_name == "王婷"
    assert p.from_email == "wangting@huaxin.test"
    assert p.text == "您好,请报价。"
    assert p.to_emails == ("sales@example.test",)
    assert p.sent_at.startswith("2026-09-19T08:12")


def test_html_only_mail_falls_back_to_text():
    p = parse(
        make_raw(
            body="",
            html="<html><body><p>Hi,</p><p>We need <b>48</b> units.</p>"
            "<style>p{}</style></body></html>",
        )
    )
    assert "Hi," in p.text
    assert "We need 48 units." in p.text
    assert "<" not in p.text and "p{}" not in p.text


def test_plain_part_preferred_over_html():
    p = parse(make_raw(body="plain wins", html="<p>html loses</p>"))
    assert p.text == "plain wins"


def test_attachments_are_listed_with_hash():
    p = parse(make_raw(attachments=[("B300-spec.pdf", b"%PDF-1.4 fake", "application/pdf")]))
    assert [a.filename for a in p.attachments] == ["B300-spec.pdf"]
    assert p.attachments[0].content == b"%PDF-1.4 fake"
    assert len(p.attachments[0].sha256) == 64
    assert "PDF" not in p.text


def test_thread_headers_are_parsed():
    p = parse(
        make_raw(
            message_id="<m3@x.test>",
            in_reply_to="<m2@x.test>",
            references="<m1@x.test> <m2@x.test>",
        )
    )
    assert p.message_id == "<m3@x.test>"
    assert p.in_reply_to == "<m2@x.test>"
    assert p.references == ("<m1@x.test>", "<m2@x.test>")


def test_missing_message_id_is_synthesized_from_bytes():
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = "a@b.test"
    msg["To"] = "sales@example.test"
    msg["Subject"] = "x"
    msg.set_content("y")
    p = parse(msg.as_bytes())
    assert p.message_id.startswith("sha256:")


def test_garbage_bytes_do_not_crash_the_parser():
    p = parse(b"\xff\xfe not an email at all \x00")
    assert p.message_id.startswith("sha256:")


def test_html_to_text_keeps_paragraph_breaks():
    assert html_to_text("<div>a</div><div>b</div>") == "a\n\nb"
