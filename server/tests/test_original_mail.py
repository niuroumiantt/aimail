from email import policy
from email.message import EmailMessage

from aimail.ingest import original


def source(html=None):
    msg = EmailMessage()
    msg.set_content("Exact plain text\nwith intentional line breaks.")
    if html is not None:
        msg.add_alternative(html, subtype="html")
    return msg


def test_preserves_original_html_structure_and_inline_raster_images():
    html = (
        "<p>Exact part K4-123</p><ul><li>10 units</li></ul>"
        '<table><tr><td>USD 25</td></tr></table><img src="cid:logo@x">'
    )
    msg = source(html)
    msg.get_payload()[-1].add_related(b"png bytes", maintype="image", subtype="png", cid="<logo@x>")
    raw = msg.as_bytes(policy=policy.SMTP)
    result = original.display_parts(raw)
    assert "<ul><li>10 units</li></ul>" in result["body_html"]
    assert "<td>USD 25</td>" in result["body_html"]
    assert result["inline_images"] == {"logo@x": "data:image/png;base64,cG5nIGJ5dGVz"}
    assert raw == msg.as_bytes(policy=policy.SMTP)


def test_plaintext_and_attached_html_are_not_promoted_to_body():
    msg = source()
    msg.add_attachment(
        b"<p>Attached document</p>", maintype="text", subtype="html", filename="spec.html"
    )
    assert original.display_parts(msg.as_bytes()) == {"body_html": None, "inline_images": {}}


def test_html_body_only_and_non_utf8_charset():
    msg = EmailMessage()
    msg.set_content("<p>报价 10 台</p>", subtype="html", charset="gb2312")
    assert "报价 10 台" in original.display_parts(msg.as_bytes())["body_html"]


def test_limits_html_and_inline_images_without_changing_source(monkeypatch):
    msg = source("<p>Complete body</p>")
    part = msg.get_payload()[-1]
    part.add_related(b"12345", maintype="image", subtype="png", cid="<large>")
    part.add_related(b"<svg/>", maintype="image", subtype="svg+xml", cid="<vector>")
    raw = msg.as_bytes()
    monkeypatch.setattr(original, "MAX_IMAGE_BYTES", 4)
    result = original.display_parts(raw)
    assert "Complete body" in result["body_html"]
    assert result["inline_images"] == {}
    assert "图片过大" in result["original_notice"]
    monkeypatch.setattr(original, "MAX_HTML_BYTES", 4)
    result = original.display_parts(raw)
    assert result["body_html"] is None
    assert "HTML 正文过大" in result["original_notice"]
