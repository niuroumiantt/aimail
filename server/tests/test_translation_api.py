"""Translation is explicit, mailbox-scoped and reusable across provider changes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

from fastapi.testclient import TestClient

from aimail import backends, translation_store
from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import model_selection, repo
from aimail.store.db import connect
from aimail.tasks.translate_mail import Translation
from conftest import make_raw

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def seed(conn, mailbox, message_id="<translation@x>", body="Need 500 pcs SATA SSD."):
    return store_raw(
        conn,
        mailbox,
        make_raw(message_id=message_id, body=body),
        "in",
        NOW,
    )[0]


def test_translation_reads_and_mail_open_never_invoke_a_model(conn, mailbox, monkeypatch):
    pk = seed(conn, mailbox)
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    monkeypatch.setattr(backends, "ready", lambda: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(
        backends, "complete", lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError())
    )
    client = TestClient(create_app(conn, mailbox))
    assert client.get(f"/api/messages/{pk}/translation").json() is None
    assert client.get(f"/api/threads/{tid}").status_code == 200
    assert client.get("/api/threads").status_code == 200
    assert conn.execute("SELECT COUNT(*) FROM message_translation").fetchone()[0] == 0


def test_translation_checks_identity_and_selected_mailbox_before_model_or_cache(
    conn, mailbox, monkeypatch
):
    private = repo.ensure_mailbox(conn, "private@example.test")
    own = seed(conn, mailbox)
    other = seed(conn, private, "<private@x>")
    monkeypatch.setattr(backends, "ready", lambda: (_ for _ in ()).throw(AssertionError()))
    client = TestClient(
        create_app(
            conn,
            mailbox,
            require_oa_auth=True,
            mailbox_access={"owner@example.test": ("sales@example.test", "private@example.test")},
        )
    )
    owner = {"X-OA-Email": "owner@example.test", "X-OA-User": "Owner"}
    for method in (client.get, client.post):
        assert method(f"/api/messages/{own}/translation").status_code == 401
        assert method(f"/api/messages/{other}/translation", headers=owner).status_code == 404
        assert (
            method(
                f"/api/messages/{own}/translation",
                headers={**owner, "X-Mailbox-Address": "private@example.test"},
            ).status_code
            == 404
        )
        assert (
            method(
                f"/api/messages/{other}/translation",
                headers={
                    "X-OA-Email": "sales@example.test",
                    "X-Mailbox-Address": "private@example.test",
                },
            ).status_code
            == 403
        )
        assert method("/api/messages/9999/translation", headers=owner).status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM message_translation").fetchone()[0] == 0


def test_selected_provider_translation_preserves_original_and_cache_survives_switch(
    conn, mailbox, monkeypatch
):
    pk = seed(conn, mailbox)
    original = dict(conn.execute("SELECT * FROM message WHERE id=?", (pk,)).fetchone())
    model_selection.choose(conn, mailbox, "codex_cli", "Operator")
    calls = []

    def complete(_system, source, schema, **kwargs):
        calls.append((backends.backend(), source))
        assert schema is Translation
        return Translation(text_zh="需要 500 pcs SATA SSD。")

    monkeypatch.setattr(backends, "ready", lambda: (True, "configured"))
    monkeypatch.setattr(backends, "complete", complete)
    client = TestClient(create_app(conn, mailbox))
    first = client.post(f"/api/messages/{pk}/translation")
    assert first.status_code == 200
    result = first.json()
    assert result["status"] == "ok"
    assert result["model"].startswith("Codex CLI ·")
    assert calls == [("codex_cli", "Need 500 pcs SATA SSD.")]
    model_selection.choose(conn, mailbox, "claude_code_cli", "Operator")
    # Even an unavailable newly selected provider must not discard a valid cache.
    monkeypatch.setattr(backends, "ready", lambda: (_ for _ in ()).throw(AssertionError()))
    assert client.get(f"/api/messages/{pk}/translation").json() == result
    assert client.post(f"/api/messages/{pk}/translation").json() == result
    assert len(calls) == 1
    assert conn.execute("SELECT COUNT(*) FROM message_translation").fetchone()[0] == 1
    assert dict(conn.execute("SELECT * FROM message WHERE id=?", (pk,)).fetchone()) == original


def test_translation_failure_hides_private_exceptions_and_retry_is_explicit(
    conn, mailbox, monkeypatch, caplog
):
    pk = seed(conn, mailbox)
    monkeypatch.setenv("LOCAL_MODEL", "fast")
    monkeypatch.setattr(backends, "ready", lambda: (True, "configured"))
    calls = []

    def fail(*_args, **_kwargs):
        calls.append(True)
        raise RuntimeError("https://private-host/token=private-secret private-mail-body")

    monkeypatch.setattr(backends, "complete", fail)
    client = TestClient(create_app(conn, mailbox))
    failure = client.post(f"/api/messages/{pk}/translation")
    assert failure.status_code == 200
    assert failure.json()["status"] == "failed"
    assert failure.json()["text_zh"] == ""
    assert client.get(f"/api/messages/{pk}/translation").json() == failure.json()
    assert len(calls) == 1
    stored = conn.execute("SELECT reason,payload FROM message_translation").fetchone()
    for secret in ("private-host", "private-secret", "private-mail-body"):
        assert secret not in failure.text
        assert secret not in stored["reason"] + stored["payload"]
        assert secret not in caplog.text
    monkeypatch.setattr(
        backends, "complete", lambda *_a, **_kw: Translation(text_zh="需要 500 pcs SATA SSD。")
    )
    assert client.post(f"/api/messages/{pk}/translation").json()["status"] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM message_translation").fetchone()[0] == 2


def test_unavailable_provider_is_closed_and_does_not_cache_placeholder(conn, mailbox, monkeypatch):
    pk = seed(conn, mailbox)
    monkeypatch.setattr(backends, "ready", lambda: (False, "private-host private-secret"))
    client = TestClient(create_app(conn, mailbox))
    response = client.post(f"/api/messages/{pk}/translation")
    assert response.status_code == 503
    assert "private-" not in response.text
    assert client.get(f"/api/messages/{pk}/translation").json() is None


def test_translation_rejects_added_figures_even_when_original_identifiers_remain(
    conn, mailbox, monkeypatch
):
    pk = seed(conn, mailbox)
    monkeypatch.setenv("LOCAL_MODEL", "fast")
    monkeypatch.setattr(backends, "ready", lambda: (True, "configured"))
    monkeypatch.setattr(
        backends,
        "complete",
        lambda *_a, **_kw: Translation(text_zh="需要 500 pcs SATA SSD。价格 USD 999。"),
    )
    client = TestClient(create_app(conn, mailbox))
    result = client.post(f"/api/messages/{pk}/translation").json()
    assert result["status"] == "failed"
    assert result["text_zh"] == ""
    assert "999" not in result["reason"]
    assert "999" not in conn.execute("SELECT payload FROM message_translation").fetchone()[0]


def test_translation_refuses_a_blank_success_and_keeps_the_original(conn, mailbox, monkeypatch):
    pk = seed(conn, mailbox, body="Hello team.")
    monkeypatch.setenv("LOCAL_MODEL", "fast")
    monkeypatch.setattr(backends, "ready", lambda: (True, "configured"))
    monkeypatch.setattr(backends, "complete", lambda *_a, **_kw: Translation(text_zh="   \n "))
    client = TestClient(create_app(conn, mailbox))
    result = client.post(f"/api/messages/{pk}/translation").json()
    assert result["status"] == "failed"
    assert result["text_zh"] == ""
    assert client.get(f"/api/messages/{pk}/translation").json() == result
    assert (
        conn.execute("SELECT body_new FROM message WHERE id=?", (pk,)).fetchone()[0]
        == "Hello team."
    )


def test_cached_reads_do_not_wait_for_translation_and_parallel_posts_share_cache(
    tmp_path, monkeypatch
):
    conn = connect(tmp_path / "mail.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    pk = seed(conn, mailbox)
    started, finish = Event(), Event()
    calls = []
    monkeypatch.setenv("LOCAL_MODEL", "fast")
    monkeypatch.setattr(backends, "ready", lambda: (True, "configured"))

    def translate(source):
        calls.append(source)
        started.set()
        assert finish.wait(5)
        return Translation(text_zh="需要 500 pcs SATA SSD。")

    monkeypatch.setattr(translation_store.task, "translate", translate)
    client = TestClient(create_app(conn, mailbox))
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(client.post, f"/api/messages/{pk}/translation")
        assert started.wait(3)
        second = pool.submit(client.post, f"/api/messages/{pk}/translation")
        try:
            response = pool.submit(client.get, f"/api/messages/{pk}/translation").result(timeout=2)
            assert response.status_code == 200
            assert response.json() is None
        finally:
            finish.set()
        assert first.result(timeout=3).json() == second.result(timeout=3).json()
    assert len(calls) == 1
    conn.close()


def test_all_quoted_new_body_remains_translatable_without_mutating_mail(conn, mailbox, monkeypatch):
    pk = seed(conn, mailbox, body="> Need 1250 units.\n> Please quote.")
    before = dict(conn.execute("SELECT * FROM message WHERE id=?", (pk,)).fetchone())
    assert before["body_new"] == ""
    monkeypatch.setattr(backends, "ready", lambda: (True, "configured"))
    calls = []

    def complete(_system, source, _schema, **_kwargs):
        calls.append(source)
        return Translation(text_zh="需要 1250 units。请报价。")

    monkeypatch.setattr(backends, "complete", complete)
    client = TestClient(create_app(conn, mailbox))
    displayed = client.get(f"/api/threads/{before['thread_id']}").json()["messages"][0]
    assert displayed["body"] == before["body_quoted"]
    assert displayed["quoted"] is None
    assert client.post(f"/api/messages/{pk}/translation").json()["status"] == "ok"
    assert calls == [before["body_quoted"]]
    assert dict(conn.execute("SELECT * FROM message WHERE id=?", (pk,)).fetchone()) == before


def test_history_only_body_is_not_recovered_as_new_text(conn, mailbox, monkeypatch):
    pk = seed(conn, mailbox, body="On Friday, Buyer wrote:\n> Old 1250 unit quote.")
    monkeypatch.setattr(backends, "ready", lambda: (_ for _ in ()).throw(AssertionError()))
    client = TestClient(create_app(conn, mailbox))
    assert client.get(f"/api/messages/{pk}/translation").json() is None
    assert client.post(f"/api/messages/{pk}/translation").status_code == 422


def test_valid_legacy_cache_is_read_without_model_and_force_is_explicit(conn, mailbox, monkeypatch):
    import json
    from hashlib import sha256

    pk = seed(conn, mailbox)
    client = TestClient(create_app(conn, mailbox))
    conn.execute(
        "INSERT INTO message_translation(source_id,model,task_version,produced_at,"
        "status,payload,source_hash) "
        "VALUES(?,?,'translate_mail@1',?,'ok',?,?)",
        (
            pk,
            "Codex CLI · legacy",
            NOW.isoformat(),
            json.dumps({"text_zh": "旧译文 500 pcs SATA SSD"}),
            sha256(b"Need 500 pcs SATA SSD.").hexdigest(),
        ),
    )
    calls = []
    monkeypatch.setattr(backends, "ready", lambda: (True, "configured"))
    monkeypatch.setattr(
        backends,
        "complete",
        lambda *_a, **_kw: calls.append(True) or Translation(text_zh="需要 500 pcs SATA SSD。"),
    )
    saved = client.get(f"/api/messages/{pk}/translation").json()
    assert saved["task_version"] == "translate_mail@1" and saved["layout_notice"]
    assert client.post(f"/api/messages/{pk}/translation").json() == saved
    assert not calls
    updated = client.post(f"/api/messages/{pk}/translation?force=true").json()
    assert updated["task_version"] == "translate_mail@2" and len(calls) == 1
    assert client.get(f"/api/messages/{pk}/translation").json() == updated
    monkeypatch.setattr(
        backends, "complete", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError())
    )
    assert client.post(f"/api/messages/{pk}/translation?force=true").json()["status"] == "failed"
    assert client.get(f"/api/messages/{pk}/translation").json() == updated
