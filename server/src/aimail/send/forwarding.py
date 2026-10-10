"""Forward original MIME content, without AI rewriting or reply threading headers."""

from copy import deepcopy
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from html import escape


def add_original(msg: EmailMessage, raw: bytes, comment: str, include_attachments: bool) -> None:
    original = BytesParser(policy=policy.default).parsebytes(raw)
    headers = "\n".join(
        f"{label}: {original.get(key, '')}"
        for key, label in [
            ("From", "发件人"),
            ("Date", "日期"),
            ("To", "收件人"),
            ("Cc", "抄送"),
            ("Subject", "主题"),
        ]
        if original.get(key)
    )
    prefix = f"{comment.strip()}\n\n---------- 转发邮件 ----------\n{headers}\n\n"
    plain = original.get_body(preferencelist=("plain",))
    html = original.get_body(preferencelist=("html",))
    msg.set_content(prefix + (plain.get_content() if plain else "请查看 HTML 正文。"))
    if html:
        msg.add_alternative(
            f"<div style='white-space:pre-wrap'>{escape(prefix)}</div>" + html.get_content(),
            subtype="html",
        )

    html_container = msg.get_payload()[-1] if html else None

    def copy_parts(part):
        # Stop at an attached MIME subtree, preserving .eml and its nested files once.
        if part is not original and (
            part.get_content_disposition() == "attachment"
            or part.get_filename()
            or part.get("Content-ID")
        ):
            inline = bool(part.get("Content-ID")) and part.get_content_disposition() != "attachment"
            if inline and html:
                target = html_container
                if target.get_content_type() != "multipart/related":
                    target.make_related()
                target.attach(deepcopy(part))
            elif include_attachments:
                if msg.get_content_type() != "multipart/mixed":
                    msg.make_mixed()
                msg.attach(deepcopy(part))
            return
        if part.is_multipart():
            for child in part.iter_parts():
                copy_parts(child)

    copy_parts(original)
