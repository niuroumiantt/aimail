"""攻击切分:各家客户端的引用格式。认不出来时整封算新增。"""

from __future__ import annotations

from mail2leads.ingest.quote import split

NEW = "Hi,\n\nWe were told this model is EOL. Can you still supply?\n\nRegards,\nDaniel"


def test_gmail_on_wrote_splits():
    text = (
        NEW
        + "\n\nOn Fri, 12 Sep 2026 at 15:20, Sales <sales@x.test> wrote:"
        + "\n> Please find our quotation"
    )
    new, quoted = split(text)
    assert new == NEW
    assert quoted.startswith("On Fri")


def test_gmail_wrapped_over_two_lines_splits():
    text = (
        NEW
        + "\n\nOn Fri, 12 Sep 2026 at 15:20, Glocalstorage Sales\n<sales@x.test> wrote:\n> quote"
    )
    new, quoted = split(text)
    assert new == NEW


def test_outlook_from_sent_block_splits():
    text = (
        NEW
        + "\n\nFrom: sales@x.test\nSent: Friday, 12 September 2026 3:20 pm"
        + "\nSubject: Quotation\n\nHi Daniel"
    )
    new, quoted = split(text)
    assert new == NEW
    assert quoted.startswith("From:")


def test_original_message_marker_splits():
    text = NEW + "\n\n-----Original Message-----\nFrom: x"
    assert split(text)[0] == NEW


def test_chinese_reply_marker_splits():
    text = "收到,谢谢。\n\n在 2026年9月12日,sales@x.test 写道:\n> 报价如下"
    new, quoted = split(text)
    assert new == "收到,谢谢。"
    assert quoted.startswith("在 2026")


def test_chinese_outlook_marker_splits():
    text = "好的。\n\n发件人: sales@x.test\n发送时间: 2026年9月12日\n主题: 报价"
    assert split(text)[0] == "好的。"


def test_angle_bracket_lines_split():
    text = "Yes please.\n> earlier line\n> another"
    new, quoted = split(text)
    assert new == "Yes please."
    assert quoted == "> earlier line\n> another"


def test_no_quote_keeps_everything_as_new():
    text = "We need 48 units.\nPlease quote CIF Helsinki."
    assert split(text) == (text, "")


def test_earliest_marker_wins():
    text = "new\n\n> quoted first\n\nOn x wrote:\nlater"
    new, _ = split(text)
    assert new == "new"
