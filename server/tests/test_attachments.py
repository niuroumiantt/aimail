"""攻击 M7:附件文字是确定性代码读出来的派生物——带署名落库、原字节不动、读不出来显形而不留白,
模型从附件里引用的数字要能回到原文。"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime

import openpyxl
from fastapi.testclient import TestClient

from aimail import backends
from aimail.api.app import create_app
from aimail.ingest import attachments
from aimail.ingest.run import ingest_once, store_raw
from aimail.store import repo
from aimail.tasks import draft as draft_mod
from aimail.tasks.read import read_message
from conftest import make_raw

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def pdf_with_text(text: str) -> bytes:
    """一页 Helvetica 的最小 PDF;text 为空就是"扫描件"(没有文字层)。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1") if text else b""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def xlsx_with_rows(rows: list[list[object]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def docx_with_paragraphs(paragraphs: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


# ── 读取器本身 ──


def test_pdf_text_layer_is_read():
    got = attachments.extract(
        "spec.pdf", "application/pdf", pdf_with_text("BOM: 48 x DDR5 64GB 4800")
    )
    assert got.status == "ok" and "DDR5 64GB 4800" in got.text
    assert got.extractor.startswith("pypdf ")


def test_scanned_pdf_is_failed_with_a_visible_reason():
    got = attachments.extract("scan.pdf", "application/octet-stream", pdf_with_text(""))
    assert got.status == "failed" and "vision" in got.reason and got.text == ""


def test_xlsx_rows_become_tab_separated_lines():
    got = attachments.extract(
        "bom.xlsx",
        "application/octet-stream",
        xlsx_with_rows([["Part", "Qty"], ["DDR5 64GB 4800", 200]]),
    )
    assert (
        got.status == "ok"
        and "DDR5 64GB 4800\t200" in got.text
        and got.extractor.startswith("openpyxl")
    )


def test_docx_paragraphs_are_read():
    got = attachments.extract("spec.docx", "", docx_with_paragraphs(["Spec:", "3 x RTX 6000 Ada"]))
    assert got.status == "ok" and got.text == "Spec:\n3 x RTX 6000 Ada"


def test_image_unknown_and_broken_files_fail_with_reasons_not_blanks():
    assert "vision" in attachments.extract("list.jpg", "image/jpeg", b"\xff\xd8junk").reason
    assert "不认识" in attachments.extract("stuff.bin", "application/octet-stream", b"junk").reason
    assert ".xlsx" in attachments.extract("old.xls", "application/vnd.ms-excel", b"junk").reason
    broken = attachments.extract("spec.pdf", "application/pdf", b"%PDF-1.4 not really")
    assert broken.status == "failed" and broken.reason
    assert attachments.extract("empty.txt", "text/plain", b"   ").status == "failed"


def test_oversized_attachment_is_refused_before_parsing():
    got = attachments.extract("huge.pdf", "application/pdf", b"0" * (attachments.MAX_BYTES + 1))
    assert got.status == "failed" and "太大" in got.reason


def test_text_files_decode_utf8_then_gb18030():
    assert attachments.extract(
        "a.csv", "text/csv", "型号,数量\nR740,20\n".encode()
    ).text.startswith("型号")
    assert "型号" in attachments.extract("b.txt", "", "型号 R740".encode("gb18030")).text


# ── 落库 ──


def test_ingest_stores_attachment_text_with_attribution_and_keeps_the_blob(conn, mailbox):
    pdf = pdf_with_text("BOM: 48 x DDR5 64GB 4800")
    raw = make_raw(message_id="<a@x>", attachments=[("spec.pdf", pdf, "application/pdf")])

    class Src:
        def uid_validity(self):
            return 1

        def new_uids(self, since):
            return [1] if since < 1 else []

        def fetch_raw(self, uid):
            return raw

    report = ingest_once(conn, mailbox, Src(), "INBOX", "in", NOW)
    assert report.stored == 1
    row = conn.execute("SELECT * FROM attachment_text").fetchone()
    assert row["status"] == "ok" and row["task_version"] == "attachment_text@1"
    assert row["model"].startswith("pypdf ") and row["produced_at"] == NOW.isoformat()
    assert bytes(conn.execute("SELECT content FROM attachment").fetchone()[0]) == pdf
    pk = int(conn.execute("SELECT id FROM message").fetchone()[0])
    assert attachments.extract_for_message(conn, pk) == 0  # 幂等:不重复读
    assert conn.execute("SELECT COUNT(*) FROM attachment_text").fetchone()[0] == 1


def test_broken_attachment_does_not_block_ingest(conn, mailbox):
    raw = make_raw(message_id="<b@x>", attachments=[("x.pdf", b"garbage", "application/pdf")])
    pk, _ = store_raw(conn, mailbox, raw, "in", NOW)
    assert pk is not None
    attachments.extract_for_message(conn, pk, NOW)
    [item] = attachments.texts_for_message(conn, pk)
    assert item.status == "failed" and item.reason and item.filename == "x.pdf"
    assert "没读出来" in attachments.source_text(conn, pk)


def test_reader_sees_attachment_text_and_its_numbers_verify(conn, mailbox, monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "fast")
    seen: list[str] = []

    def fake(system: str, user: str, hint: str) -> str:
        seen.append(user)
        return json.dumps(
            {
                "is_inquiry": True,
                "detected_language": "en",
                "summary_zh": "要 48 条 DDR5",
                "summary_en": "48 DDR5",
                "facts": ["48 条 DDR5 64GB(来自附件)"],
                "quoted_numbers": ["48", "DDR5", "64GB"],
            }
        )

    monkeypatch.setattr(backends, "_call_local", fake)
    raw = make_raw(
        message_id="<c@x>",
        body="Please quote, spec attached.",
        attachments=[("spec.pdf", pdf_with_text("BOM: 48 x DDR5 64GB 4800"), "application/pdf")],
    )
    pk, _ = store_raw(conn, mailbox, raw, "in", NOW)
    assert read_message(conn, int(pk)) == "ok"
    assert "——附件——" in seen[0] and "DDR5 64GB 4800" in seen[0]
    assert json.loads(repo.latest_reading(conn, int(pk))["payload"])["unverified"] == []


def test_draft_source_carries_attachment_text(conn, mailbox):
    raw = make_raw(
        message_id="<d@x>",
        body="See attached BOM.",
        attachments=[
            ("bom.xlsx", xlsx_with_rows([["DDR5 64GB", 200]]), "application/octet-stream")
        ],
    )
    pk, _ = store_raw(conn, mailbox, raw, "in", NOW)
    tid = int(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])
    _, text = draft_mod.thread_source(conn, tid)
    assert "[bom.xlsx]" in text and "DDR5 64GB\t200" in text


# ── API ──


def test_api_exposes_attachment_state_and_text_only_within_the_mailbox(conn, mailbox):
    raw = make_raw(
        message_id="<e@x>",
        attachments=[
            ("spec.pdf", pdf_with_text("BOM: 48 x DDR5"), "application/pdf"),
            ("scan.pdf", pdf_with_text(""), "application/pdf"),
        ],
    )
    pk, _ = store_raw(conn, mailbox, raw, "in", NOW)
    attachments.extract_for_message(conn, pk, NOW)
    tid = int(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])
    client = TestClient(create_app(conn, mailbox))
    atts = client.get(f"/api/threads/{tid}").json()["messages"][0]["attachments"]
    assert [(a["name"], a["read"]) for a in atts] == [("spec.pdf", "ok"), ("scan.pdf", "failed")]
    assert "vision" in atts[1]["reason"] and "text" not in atts[0]  # 正文按需取,不随线程下发
    got = client.get(f"/api/attachments/{atts[0]['id']}/text").json()
    assert got["status"] == "ok" and "DDR5" in got["text"]
    assert client.get("/api/attachments/999/text").status_code == 404
    other = repo.ensure_mailbox(conn, "other@example.test", "Other")
    assert (
        TestClient(create_app(conn, other))
        .get(f"/api/attachments/{atts[0]['id']}/text")
        .status_code
        == 404
    )
