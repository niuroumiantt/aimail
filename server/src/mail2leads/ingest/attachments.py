"""附件 → 文字。确定性代码,不是模型:
PDF 文字层(pypdf)、xlsx(openpyxl)、docx(zip 里的 XML)、csv / txt。

没有文字层的扫描件和图片记为 failed,reason 写明要走 vision 路由——那一步推迟到手里有真实扫描件时再接;
界面把它显形而不是留白(宪法第六条)。读出的文字是派生物,带署名落 attachment_text 表(第三条);
原附件的字节一个不动。
"""

from __future__ import annotations

import io
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from xml.etree import ElementTree

VERSION = "attachment_text@1"
MAX_BYTES = 15 * 1024 * 1024
MAX_CHARS = 20_000
MAX_PAGES = 60
VISION_DEFERRED = "要走 vision 路由,还没接"
TEXT_EXT = {".txt", ".csv", ".tsv", ".md"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp", ".heic"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class Extracted:
    status: str  # ok / failed
    text: str = ""
    reason: str = ""
    extractor: str = "stdlib"  # 署名:谁读的


def _kind(filename: str, content_type: str) -> str:
    ext = PurePosixPath(filename.lower()).suffix
    ct = content_type.lower()
    if ext == ".pdf" or ct == "application/pdf":
        return "pdf"
    if ext in {".xlsx", ".xlsm"} or "spreadsheetml" in ct:
        return "xlsx"
    if ext == ".xls":
        return "xls"
    if ext == ".docx" or "wordprocessingml" in ct:
        return "docx"
    if ext in TEXT_EXT or ct.startswith("text/"):
        return "text"
    if ext in IMAGE_EXT or ct.startswith("image/"):
        return "image"
    return "other"


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n…(截断)"


def _pdf(content: bytes) -> Extracted:
    import pypdf

    who = f"pypdf {pypdf.__version__}"
    reader = pypdf.PdfReader(io.BytesIO(content), strict=False)
    if reader.is_encrypted and not reader.decrypt(""):
        return Extracted("failed", reason="PDF 加密了,读不了", extractor=who)
    parts: list[str] = []
    for n, page in enumerate(reader.pages):
        if n >= MAX_PAGES:
            break
        parts.append((page.extract_text() or "").strip())
    text = "\n\n".join(p for p in parts if p)
    if not text:
        return Extracted(
            "failed", reason=f"PDF 没有文字层(扫描件),{VISION_DEFERRED}", extractor=who
        )
    return Extracted("ok", _clip(text), extractor=who)


def _xlsx(content: bytes) -> Extracted:
    import openpyxl

    who = f"openpyxl {openpyxl.__version__}"
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    lines: list[str] = []
    try:
        for ws in wb.worksheets:
            lines.append(f"## {ws.title}")
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else str(v).strip() for v in row]
                if any(cells):
                    lines.append("\t".join(cells).rstrip())
                if len(lines) > 3000:
                    break
    finally:
        wb.close()
    if not any(line and not line.startswith("## ") for line in lines):
        return Extracted("failed", reason="表格是空的", extractor=who)
    return Extracted("ok", _clip("\n".join(lines)), extractor=who)


def _docx(content: bytes) -> Extracted:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    paragraphs = [
        "".join(t.text or "" for t in p.iter(W + "t")).strip() for p in root.iter(W + "p")
    ]
    text = "\n".join(p for p in paragraphs if p)
    if not text:
        return Extracted("failed", reason="Word 文档里没有文字")
    return Extracted("ok", _clip(text))


def _text(content: bytes) -> Extracted:
    text = ""
    for enc in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text.strip():
        return Extracted("failed", reason="文件是空的")
    return Extracted("ok", _clip(text))


def extract(filename: str, content_type: str, content: bytes) -> Extracted:
    """一份附件 → 文字。永不抛:坏文件、不认识的类型都是带原因的 failed。"""
    if len(content) > MAX_BYTES:
        return Extracted("failed", reason=f"太大({len(content) // (1024 * 1024)} MB),不读")
    kind = _kind(filename, content_type)
    try:
        if kind == "pdf":
            return _pdf(content)
        if kind == "xlsx":
            return _xlsx(content)
        if kind == "docx":
            return _docx(content)
        if kind == "text":
            return _text(content)
    except Exception as exc:  # noqa: BLE001 —— 附件是外来的,坏文件只记原因,不炸收信
        return Extracted("failed", reason=f"解析失败:{type(exc).__name__}: {str(exc)[:200]}")
    if kind == "image":
        return Extracted("failed", reason=f"图片{VISION_DEFERRED}")
    if kind == "xls":
        return Extracted("failed", reason="旧版 .xls 不读,请客户另存为 .xlsx")
    return Extracted("failed", reason=f"不认识的类型 {content_type or filename}")


# ── 落库与取用 ──


def extract_for_message(
    conn: sqlite3.Connection, message_pk: int, now: datetime | None = None
) -> int:
    """给这封信还没读过的附件读文字,落 attachment_text。幂等;返回这次新读的份数。"""
    produced_at = (now or datetime.now(UTC)).replace(microsecond=0).isoformat()
    rows = conn.execute(
        "SELECT a.id, a.filename, a.content_type, a.content FROM attachment a "
        "WHERE a.message_id = ? "
        "AND NOT EXISTS (SELECT 1 FROM attachment_text t WHERE t.source_id = a.id) ORDER BY a.id",
        (message_pk,),
    ).fetchall()
    for r in rows:
        result = extract(str(r["filename"]), str(r["content_type"]), bytes(r["content"]))
        conn.execute(
            "INSERT INTO attachment_text "
            "(source_id, model, task_version, produced_at, status, text, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                int(r["id"]),
                result.extractor,
                VERSION,
                produced_at,
                result.status,
                result.text,
                result.reason,
            ),
        )
    return len(rows)


@dataclass(frozen=True)
class AttachmentText:
    attachment_id: int
    filename: str
    size: int
    status: str  # ok / failed / none(还没读)
    text: str
    reason: str


_SELECT = (
    "SELECT a.id, a.filename, a.size, t.status, t.text, t.reason FROM attachment a "
    "LEFT JOIN attachment_text t ON t.id = (SELECT id FROM attachment_text "
    "WHERE source_id = a.id ORDER BY produced_at DESC, id DESC LIMIT 1) "
)


def _row(r: sqlite3.Row) -> AttachmentText:
    return AttachmentText(
        attachment_id=int(r["id"]),
        filename=str(r["filename"]),
        size=int(r["size"]),
        status=str(r["status"] or "none"),
        text=str(r["text"] or ""),
        reason=str(r["reason"] or ""),
    )


def texts_for_message(conn: sqlite3.Connection, message_pk: int) -> list[AttachmentText]:
    rows = conn.execute(_SELECT + "WHERE a.message_id = ? ORDER BY a.id", (message_pk,)).fetchall()
    return [_row(r) for r in rows]


def get_text(
    conn: sqlite3.Connection, mailbox_id: int, attachment_id: int
) -> AttachmentText | None:
    """按附件 id 取;只认本邮箱的(别的邮箱的附件当不存在)。"""
    row = conn.execute(
        _SELECT + "JOIN message m ON m.id = a.message_id WHERE a.id = ? AND m.mailbox_id = ?",
        (attachment_id, mailbox_id),
    ).fetchone()
    return _row(row) if row else None


def source_text(conn: sqlite3.Connection, message_pk: int, per_file: int = 4000) -> str:
    """模型输入里的附件段:读出来的原样放,读不出来的写明原因。没有附件就是空串。"""
    items = texts_for_message(conn, message_pk)
    if not items:
        return ""
    lines = ["——附件——"]
    for it in items:
        if it.status == "ok":
            body = it.text if len(it.text) <= per_file else it.text[:per_file] + "\n…(截断)"
            lines.append(f"[{it.filename}]\n{body}")
        else:
            lines.append(f"[{it.filename}] 没读出来:{it.reason or '还没读'}")
    return "\n\n".join(lines)
