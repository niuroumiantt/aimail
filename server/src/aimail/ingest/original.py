"""Read display parts from the immutable RFC822 source, without changing stored text."""

from __future__ import annotations

import base64
import email
from email import policy
from email.errors import MessageError
from email.message import EmailMessage

IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"}
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def display_parts(raw: bytes) -> dict:
    result: dict = {"body_html": None, "inline_images": {}}
    try:
        msg = email.message_from_bytes(raw, policy=policy.default)
        if not isinstance(msg, EmailMessage):
            return result
        part = msg.get_body(preferencelist=("html",))
        if part is None:
            return result
        html = part.get_content()
        if not isinstance(html, str) or not html.strip():
            return result
        if len(html.encode("utf-8")) > MAX_HTML_BYTES:
            return {
                **result,
                "original_notice": "HTML 正文过大，当前显示纯文本。原始邮件保留完整。",
            }
        result["body_html"] = html
        total = 0
        for item in msg.walk():
            cid = str(item.get("Content-ID", "")).strip().strip("<>")
            mime = item.get_content_type()
            if not cid or mime not in IMAGE_TYPES or item.is_multipart():
                continue
            content = item.get_payload(decode=True) or b""
            if total + len(content) > MAX_IMAGE_BYTES:
                result["original_notice"] = "部分内嵌图片过大，未在正文加载。原始邮件保留完整。"
                continue
            total += len(content)
            result["inline_images"].setdefault(
                cid, f"data:{mime};base64," + base64.b64encode(content).decode("ascii")
            )
        return result
    except (LookupError, UnicodeError, MessageError, ValueError, TypeError):
        return {
            "body_html": None,
            "inline_images": {},
            "original_notice": "原始 HTML 暂无法显示，当前显示纯文本。",
        }
