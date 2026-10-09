import sqlite3
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


def test_local_translation_model_does_not_override_a_selected_cli(monkeypatch):
    from aimail import backends
    from aimail.tasks.translate_mail import routed_model

    monkeypatch.setenv("MAIL_TRANSLATION_MODEL", "brain")
    with backends.use_backend("local"):
        assert routed_model() == "brain"
    for provider in ("codex_cli", "claude_code_cli", "claude"):
        with backends.use_backend(provider):
            assert routed_model() is None


def test_cache_checks_body_and_task_version_without_using_provider(monkeypatch):
    # A minimal mutable source exercises input replacement without weakening the
    # immutable RFC822 tables or triggers in the application schema.
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE message(id INTEGER PRIMARY KEY,body_new TEXT NOT NULL,"
        "body_quoted TEXT NOT NULL DEFAULT '')"
    )
    conn.execute("INSERT INTO message(id,body_new) VALUES(1,'Need 500 pcs SATA SSD.')")
    translation_store.prepare(conn)
    calls = []

    def translate(source):
        calls.append(source)
        return Translation(text_zh=source.replace("Need", "需要"))

    monkeypatch.setattr(translation_store.task, "translate", translate)
    first = translation_store.translate_cached(conn, 1)
    assert translation_store.translate_cached(conn, 1) == first
    conn.execute("UPDATE message SET body_new='Need 600 pcs SATA SSD.' WHERE id=1")
    assert translation_store.get_current(conn, 1) is None
    assert "600" in translation_store.translate_cached(conn, 1)["text_zh"]
    monkeypatch.setattr(translation_store.task, "TASK_VERSION", "translate_mail@next")
    assert translation_store.get_current(conn, 1) is None
    assert translation_store.translate_cached(conn, 1)["task_version"] == "translate_mail@next"
    assert calls == ["Need 500 pcs SATA SSD.", "Need 600 pcs SATA SSD.", "Need 600 pcs SATA SSD."]
    assert conn.execute("SELECT COUNT(*) FROM message_translation").fetchone()[0] == 3
    conn.close()


def test_existing_prototype_translation_migrates_without_model_call(conn, mailbox, monkeypatch):
    conn.execute("DROP TABLE message_translation")
    conn.execute(
        "CREATE TABLE message_translation(id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,"
        "model TEXT NOT NULL,task_version TEXT NOT NULL,produced_at TEXT NOT NULL,"
        "status TEXT NOT NULL,payload TEXT NOT NULL DEFAULT '{}',reason TEXT NOT NULL DEFAULT '')"
    )
    pk, _ = store_raw(conn, mailbox, make_raw(), "in", datetime.now(UTC))
    conn.execute(
        "INSERT INTO message_translation VALUES(1,?,'Historical model','translate_mail@1',"
        "'2026-10-01','ok','{\"text_zh\":\"历史译文\"}','')",
        (pk,),
    )
    monkeypatch.setattr(
        translation_store.task, "translate", lambda _s: (_ for _ in ()).throw(AssertionError())
    )
    translation_store.prepare(conn)
    translation_store.prepare(conn)
    assert translation_store.get(conn, pk)["text_zh"] == "历史译文"
    assert translation_store.get_current(conn, pk) is None
    assert conn.execute("SELECT source_hash FROM message_translation").fetchone()[0] == ""


def test_legacy_history_translation_is_invalidated_without_deleting_original_or_calling_model(
    monkeypatch,
):
    from hashlib import sha256

    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE message(id INTEGER PRIMARY KEY,body_new TEXT,body_quoted TEXT)")
    original = "Need 12 units.\n\n---- 回复的原邮件 ----\nEarlier offer: 10 units."
    conn.execute("INSERT INTO message VALUES(1,?,'')", (original,))
    translation_store.prepare(conn)
    conn.execute(
        "INSERT INTO message_translation(source_id,model,task_version,produced_at,status,"
        "payload,source_hash) VALUES(1,'Old model',?,'2026-10-09','ok','{}',?)",
        (translation_store.task.TASK_VERSION, sha256(original.encode()).hexdigest()),
    )
    monkeypatch.setattr(
        translation_store.task, "translate", lambda _: (_ for _ in ()).throw(AssertionError())
    )
    assert translation_store.get_current(conn, 1) is None
    assert translation_store._source(conn, 1) == "Need 12 units."
    assert conn.execute("SELECT body_new FROM message").fetchone()[0] == original
    assert conn.execute("SELECT COUNT(*) FROM message_translation").fetchone()[0] == 1
    conn.close()
