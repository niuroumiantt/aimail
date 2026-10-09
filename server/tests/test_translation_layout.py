import json

import pytest

from aimail import backends
from aimail.tasks import translate_mail as task
from aimail.translation_layout import Layout, from_raw
from conftest import make_raw


def test_table_spans_links_and_inline_text_survive_without_generated_markup(monkeypatch):
    layout = Layout(
        '<p>Need <b>2</b> servers.</p><table><tr><th rowspan="2">Memory</th>'
        "<td>64GB</td></tr><tr><td>32GB</td></tr></table>"
        '<a href="https://example.test/spec">Datasheet</a><script>evil()</script>'
    )

    def complete(_system, source, shape, **_kwargs):
        segments = json.loads(source)["segments"]
        words = {
            "Need ": "需要 ",
            " servers.": " 台服务器。",
            "Memory": "内存",
            "Datasheet": "<img src=x onerror=evil()>",
        }
        return shape(
            segments=[
                {"id": s["id"], "text": words.get(s["text"], s["text"])} for s in reversed(segments)
            ]
        )

    monkeypatch.setattr(backends, "complete", complete)
    result = task.translate_layout(layout)
    assert '<th rowspan="2">内存</th>' in result["html_zh"]
    assert result["html_zh"].count("<tr>") == 2
    assert "需要 <b>2</b> 台服务器。" in result["html_zh"]
    assert 'href="https://example.test/spec"' in result["html_zh"]
    assert "&lt;img" in result["html_zh"] and "<script" not in result["html_zh"]


@pytest.mark.parametrize("mode", ["omit", "duplicate", "move-number"])
def test_incomplete_or_misaligned_cells_never_saved(monkeypatch, mode):
    layout = Layout("<table><tr><td>12 units</td><td>24 units</td></tr></table>")

    def complete(_system, source, shape, **_kwargs):
        segments = json.loads(source)["segments"]
        if mode == "omit":
            segments.pop()
        elif mode == "duplicate":
            segments[1]["id"] = 0
        else:
            segments[0]["text"], segments[1]["text"] = segments[1]["text"], segments[0]["text"]
        return shape(segments=segments)

    monkeypatch.setattr(backends, "complete", complete)
    with pytest.raises(backends.LLMError):
        task.translate_layout(layout)


def test_history_and_different_html_alternative_fall_back_to_new_plain_text():
    from email import policy
    from email.parser import BytesParser

    mail = BytesParser(policy=policy.default).parsebytes(make_raw(body="Need 12 units."))
    mail.add_alternative(
        "<p>Need 12 units.</p><blockquote>Old 24 units.</blockquote>", subtype="html"
    )
    assert from_raw(mail.as_bytes(), "Need 12 units.", "Old 24 units.") is None
    assert from_raw(mail.as_bytes(), "Need 12 units.", "") is None


def test_known_quote_boundary_keeps_new_table_and_excludes_old_reply():
    from email.message import EmailMessage

    mail = EmailMessage()
    mail.set_content("Need 12 units. Memory 64GB")
    mail.add_alternative(
        "<p>Need 12 units.</p><table><tr><td>Memory</td><td>64GB</td></tr></table>"
        '<div class="gmail_quote">Old 24 units.</div>',
        subtype="html",
    )
    layout = from_raw(mail.as_bytes(), "Need 12 units. Memory 64GB", "Old 24 units.")
    assert layout is not None
    assert "<table>" in layout.render() and "24" not in layout.render()
