"""A bounded inert HTML tree; models can replace text, never markup or URLs."""

from __future__ import annotations

import json
import re
from html import escape
from html.parser import HTMLParser

from aimail.ingest.original import display_parts
from aimail.ingest.quote import SEPARATORS

TAGS = set(
    (
        "div p span b strong em i u s a table thead tbody tfoot tr td th ul ol li br hr img "
        "h1 h2 h3 h4 h5 h6 blockquote pre code"
    ).split()
)
VOID = {"br", "hr", "img"}
DROP = {"script", "style", "head", "iframe", "object", "form", "svg"}


class Layout(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tree = ["div", {}, []]
        self.stack = [self.tree]
        self.dropped = 0
        self.slots = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if self.dropped or tag in DROP:
            self.dropped += tag not in VOID
            return
        if tag not in TAGS:
            tag = "span"
        kept = {}
        quote_class = attributes.get("class") or ""
        if (
            any(
                c in quote_class.split()
                for c in {
                    "gmail_quote",
                    "yahoo_quoted",
                    "protonmail_quote",
                    "ntes-mailmaster-quote",
                }
            )
            or tag == "blockquote"
            and attributes.get("type") == "cite"
        ):
            kept["_quote"] = "true"
        for key, value in attributes.items():
            if key in {"rowspan", "colspan"} and (value or "").isdigit():
                kept[key] = str(min(100, max(1, int(value))))
            if key == "href" and re.match(r"^(https?://|mailto:|tel:)", value or "", re.I):
                kept[key] = value
            if tag == "img" and key in {"src", "alt", "width"}:
                kept[key] = value or ""
        node = [tag, kept, []]
        self.stack[-1][2].append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if self.dropped:
            self.dropped -= 1
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if not self.dropped:
            self.stack[-1][2].append(data)

    def texts(self, node=None):
        return "\n".join(self.leaves(node))

    def leaves(self, node=None):
        node = self.tree if node is None else node
        return [
            text
            for child in node[2]
            for text in ([child] if isinstance(child, str) else self.leaves(child))
        ]

    def without_history(self):
        def prune(node):
            node[2] = [
                child for child in node[2] if isinstance(child, str) or not child[1].get("_quote")
            ]
            for child in node[2]:
                if not isinstance(child, str):
                    prune(child)

        prune(self.tree)
        text = self.texts()
        cut = min((m.start() for p in SEPARATORS if (m := p.search(text))), default=len(text) + 1)
        offset = 0

        def truncate(node):
            nonlocal offset
            children = []
            for child in node[2]:
                if isinstance(child, str):
                    start, offset = offset, offset + len(child) + 1
                    if start < cut:
                        children.append(child[: cut - start])
                elif offset < cut:
                    truncate(child)
                    children.append(child)
            node[2] = children

        truncate(self.tree)

    def render(self, translations=None, node=None):
        node = self.tree if node is None else node
        tag, attrs, children = node
        content = ""
        for child in children:
            if isinstance(child, str):
                if translations is None:
                    content += escape(child)
                else:
                    content += escape(translations.pop(0)) if child.strip() else escape(child)
            else:
                content += self.render(translations, child)
        attributes = "".join(
            f' {key}="{escape(value, quote=True)}"'
            for key, value in attrs.items()
            if not key.startswith("_")
        )
        return f"<{tag}{attributes}>" + ("" if tag in VOID else content + f"</{tag}>")

    def segments(self, node=None):
        node = self.tree if node is None else node
        return [
            text
            for child in node[2]
            for text in (
                [child]
                if isinstance(child, str) and child.strip()
                else []
                if isinstance(child, str)
                else self.segments(child)
            )
        ]


def from_raw(raw, body, quoted):
    html = display_parts(raw).get("body_html") if raw else None
    if not html:
        return None
    layout = Layout(html)
    # Use the structure only when no history can be accidentally translated.
    # Unknown or malformed boundaries fall back to the independently parsed new text.
    if quoted.strip() or any(p.search(layout.texts()) for p in SEPARATORS):
        layout.without_history()
    segments = layout.segments()
    if not segments or len(segments) > 240 or sum(map(len, segments)) > 24000:
        return None
    # A truncated or materially different HTML alternative must not replace plain text.
    from aimail.tasks.translate_mail import _numbers

    if _numbers(layout.texts()) != _numbers(body):
        return None

    def normalize(value):
        return re.sub(r"[\s>*•-]+", "", value).casefold()

    if quoted.strip() and normalize(layout.texts()) != normalize(body):
        return None
    return layout


def cache_source(source, layout):
    return source if layout is None else json.dumps([source, layout.render()], ensure_ascii=False)
