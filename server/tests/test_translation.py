from datetime import UTC, datetime

from aimail import translation_store
from aimail.ingest.run import store_raw
from aimail.store import repo
from aimail.store.db import connect
from aimail.tasks.translate_mail import Translation, _numbers
from conftest import make_raw


def test_translation_keeps_identifiers_and_failure_is_visible(tmp_path, monkeypatch):
    conn = connect(tmp_path / "test.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    pk, _ = store_raw(
        conn,
        mailbox,
        make_raw(body="Need 500 pcs SATA SSD by 2026-10-01."),
        "in",
        datetime.now(UTC),
    )
    translation_store.prepare(conn)
    monkeypatch.setattr(
        translation_store.task,
        "translate",
        lambda source: Translation(text_zh="需要 500 pcs SATA SSD，交期 2026-10-01。"),
    )
    assert translation_store.translate(conn, pk) == "ok"
    assert "500" in translation_store.get(conn, pk)["text_zh"]

    monkeypatch.setattr(
        translation_store.task, "translate", lambda source: (_ for _ in ()).throw(ValueError())
    )
    assert translation_store.translate(conn, pk) == "failed"
    assert translation_store.get(conn, pk)["status"] == "failed"
    conn.close()


def test_numeric_contract_is_not_empty():
    assert _numbers("500 pcs on 2026-10-01") == {"500", "2026-10-01"}
