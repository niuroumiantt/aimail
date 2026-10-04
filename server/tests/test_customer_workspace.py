import json
import threading
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aimail import backends
from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import customer_workspace as workspace
from aimail.store import repo
from aimail.store.db import connect
from aimail.tasks.ask_mailbox import Answer
from conftest import make_raw


def add(conn, mailbox, key, body, *, subject="GPU", thread=None, direction="in", date=None):
    pk, _ = store_raw(
        conn,
        mailbox,
        make_raw(
            subject=subject,
            body=body,
            message_id=f"<{key}@example.test>",
            from_="Mikko <mikko@aurora.test>" if direction == "in" else "sales@example.test",
            to="sales@example.test" if direction == "in" else "mikko@aurora.test",
            date=date,
        ),
        direction,
        datetime.now(UTC),
        target_thread_id=thread,
    )
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()
    return pk, int(tid[0]) if tid else None


@pytest.fixture
def fake_model(monkeypatch):
    calls = []
    monkeypatch.setenv("LOCAL_MODEL", "fixture-model")

    def complete(system, user, shape, **kwargs):
        payload = json.loads(user)
        assert payload["history_untrusted"] == []
        assert "DERIVED_MARKER" not in user
        calls.append(payload["mail_evidence"])
        source = payload["mail_evidence"][-1]
        quote = source["text"].split("\n\n", 1)[1].strip()
        return Answer(findings=[{"source_id": source["id"], "quote": quote, "text": quote}])

    monkeypatch.setattr(backends, "complete", complete)
    return calls


def run_jobs(conn, mailbox):
    jobs = workspace.claim(conn, mailbox, "mikko@aurora.test")
    for job in jobs:
        workspace.finish(conn, job, workspace.generate(job))
    return jobs


def test_latest_demand_survives_old_mail_selection_and_refresh(conn, mailbox, fake_model):
    initial, thread = add(conn, mailbox, "old", "4 H200 units.")
    add(conn, mailbox, "quote", "Our quotation: 4 H200 units.", thread=thread, direction="out")
    add(
        conn,
        mailbox,
        "new",
        "Changed requirement: 2 H200 units.",
        thread=thread,
        date=datetime(2026, 10, 4, tzinfo=UTC),
    )
    _, storage = add(conn, mailbox, "storage", "12 storage nodes.", subject="STORAGE")
    assert len(run_jobs(conn, mailbox)) == 2
    assert len(fake_model) == 2
    assert run_jobs(conn, mailbox) == []
    context = workspace.context(conn, mailbox, "MIKKO@aurora.test")
    gpu = next(item for item in context["projects"] if item["id"] == str(thread))
    assert gpu["summary"]["findings"][0]["text"] == "Changed requirement: 2 H200 units."
    assert gpu["scope"]["total"] == 3
    assert any(message["direction"] == "out" for message in gpu["messages"])
    assert gpu["messages"][0]["id"] == str(initial)
    saved_storage = next(item for item in context["projects"] if item["id"] == str(storage))
    assert saved_storage["summary"]["findings"][0]["text"] == "12 storage nodes."
    add(
        conn,
        mailbox,
        "latest",
        "Final requirement: 3 H200 units.",
        thread=thread,
        date=datetime(2026, 10, 5, tzinfo=UTC),
    )
    assert len(run_jobs(conn, mailbox)) == 1
    updated = workspace.context(conn, mailbox, "mikko@aurora.test")
    assert next(item for item in updated["projects"] if item["id"] == str(storage)) == saved_storage
    assert len(fake_model) == 3


def test_historical_insert_outbound_and_attachment_change_invalidate(conn, mailbox, fake_model):
    message, thread = add(conn, mailbox, "first", "2 H200 units.")
    run_jobs(conn, mailbox)
    assert add(conn, mailbox, "first", "2 H200 units.")[0] is None
    assert workspace.claim(conn, mailbox, "mikko@aurora.test") == []
    add(
        conn,
        mailbox,
        "earlier",
        "Initial requirement: 4 H200 units.",
        thread=thread,
        date=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert len(run_jobs(conn, mailbox)) == 1
    add(
        conn,
        mailbox,
        "sent",
        "We can deliver in 3 weeks.",
        thread=thread,
        direction="out",
        date=datetime(2026, 10, 6, tzinfo=UTC),
    )
    assert len(run_jobs(conn, mailbox)) == 1
    conn.execute(
        "INSERT INTO attachment(message_id,filename,content_type,size,sha256,content) "
        "VALUES(?, 'spec.txt','text/plain',4,'hash',?)",
        (message, b"spec"),
    )
    attachment = conn.execute("SELECT MAX(id) FROM attachment").fetchone()[0]
    assert len(run_jobs(conn, mailbox)) == 1
    conn.execute(
        "INSERT INTO attachment_text(source_id,model,task_version,produced_at,status,text,reason) "
        "VALUES(?,'text','extract@1',?,'ok','spec','')",
        (attachment, datetime.now(UTC).isoformat()),
    )
    assert len(run_jobs(conn, mailbox)) == 1
    assert len(fake_model) == 5


def test_cached_failure_is_explicit_and_retry_does_not_touch_other_projects(
    conn, mailbox, fake_model
):
    _, thread = add(conn, mailbox, "a", "2 H200 units.")
    run_jobs(conn, mailbox)
    add(conn, mailbox, "b", "3 H200 units.", thread=thread, date=datetime(2026, 10, 6, tzinfo=UTC))
    job = workspace.claim(conn, mailbox, "mikko@aurora.test")[0]
    workspace.finish(conn, job, None)
    project = workspace.context(conn, mailbox, "mikko@aurora.test")["projects"][0]
    assert project["state"] == "failed" and project["stale"]
    assert project["summary"]["findings"][0]["text"] == "2 H200 units."
    assert workspace.claim(conn, mailbox, "mikko@aurora.test") == []
    assert len(workspace.claim(conn, mailbox, "mikko@aurora.test", retry=True)) == 1
    assert workspace.claim(conn, mailbox, "mikko@aurora.test", retry=True) == []


def test_two_connections_claim_only_once_and_restart_reuses_result(tmp_path, fake_model):
    path = tmp_path / "mail.sqlite3"
    first = connect(path)
    mailbox = repo.ensure_mailbox(first, "sales@example.test")
    add(first, mailbox, "a", "2 units.")
    second = connect(path)
    jobs = workspace.claim(first, mailbox, "mikko@aurora.test")
    assert workspace.claim(second, mailbox, "mikko@aurora.test") == []
    workspace.finish(first, jobs[0], workspace.generate(jobs[0]))
    first.close()
    assert workspace.claim(second, mailbox, "mikko@aurora.test") == []
    assert workspace.context(second, mailbox, "mikko@aurora.test")["projects"][0]["state"] == "ok"
    second.close()


def test_customer_api_respects_mailbox_boundary_and_retains_lead_signal(conn, mailbox, fake_model):
    message, thread = add(conn, mailbox, "a", "2 units.")
    other = repo.ensure_mailbox(conn, "other@example.test")
    _, private = add(conn, other, "private", "PRIVATE 999 units.")
    app = create_app(
        conn,
        mailbox,
        require_oa_auth=True,
        mailbox_access={"viewer@example.test": ("sales@example.test",)},
    )
    with TestClient(app) as client:
        headers = {"X-OA-Email": "viewer@example.test"}
        assert client.get(f"/api/threads/{private}/customer", headers=headers).status_code == 404
        assert client.post(f"/api/threads/{private}/customer", headers=headers).status_code == 404
        assert (
            client.get(
                f"/api/threads/{thread}/customer",
                headers={**headers, "X-Mailbox-Address": "other@example.test"},
            ).status_code
            == 403
        )
        assert (
            client.get(f"/api/threads/{thread}/customer", headers=headers).json()["projects"][0][
                "state"
            ]
            == "none"
        )
        assert not fake_model  # Reads do not call a model.
        assert client.post(f"/api/threads/{thread}/customer", headers=headers).json()["queued"] == 1
        for _ in range(100):
            context = client.get(f"/api/threads/{thread}/customer", headers=headers).json()
            if context["projects"][0]["state"] == "ok":
                break
            time.sleep(0.01)
        assert context["projects"][0]["state"] == "ok"
        assert client.post(f"/api/threads/{thread}/customer", headers=headers).json()["queued"] == 0
        assert len(fake_model) == 1
        assert "PRIVATE" not in json.dumps(context)
        conn.execute(
            "INSERT INTO message_reading(source_id,model,task_version,produced_at,"
            "status,payload,reason) "
            "VALUES(?,'model','summarize_inquiry@4',?,'ok',?, '')",
            (message, datetime.now(UTC).isoformat(), json.dumps({"is_inquiry": True})),
        )
        add(
            conn, mailbox, "later", "Thanks.", thread=thread, date=datetime(2026, 10, 7, tzinfo=UTC)
        )
        assert client.get("/api/threads", headers=headers).json()[0]["has_trade"] is True


def test_customer_api_reads_and_analyzes_only_the_selected_topic(conn, mailbox, fake_model):
    _, gpu = add(conn, mailbox, "selected-gpu", "4 H200 units.")
    add(conn, mailbox, "gpu-reply", "Our quotation for 4 H200 units.", thread=gpu, direction="out")
    add(
        conn,
        mailbox,
        "gpu-latest",
        "Latest requirement: 2 H200 units.",
        thread=gpu,
        date=datetime(2026, 10, 5, tzinfo=UTC),
    )
    _, storage = add(conn, mailbox, "separate-storage", "12 storage nodes.", subject="STORAGE")
    with TestClient(create_app(conn, mailbox)) as client:
        before = client.get(f"/api/threads/{gpu}/customer").json()
        assert [project["id"] for project in before["projects"]] == [str(gpu)]
        assert fake_model == []
        assert client.post(f"/api/threads/{gpu}/customer").json()["queued"] == 1
        for _ in range(100):
            current = client.get(f"/api/threads/{gpu}/customer").json()["projects"][0]
            if current["state"] == "ok":
                break
            time.sleep(0.01)
        assert current["state"] == "ok"
        assert current["scope"]["total"] == 3
        assert current["summary"]["findings"][0]["text"] == "Latest requirement: 2 H200 units."
        assert len(fake_model) == 1
        assert any(
            source["text"].endswith("Our quotation for 4 H200 units.") for source in fake_model[0]
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM customer_summary WHERE source_id=?", (storage,)
            ).fetchone()[0]
            == 0
        )
        assert client.post(f"/api/threads/{gpu}/customer?retry=true").json()["queued"] == 0
        assert len(fake_model) == 1
        separate = client.get(f"/api/threads/{storage}/customer").json()["projects"]
        assert len(separate) == 1 and separate[0]["id"] == str(storage)
        assert separate[0]["state"] == "none"


def test_summary_wait_does_not_block_file_backed_inbox_reads(tmp_path, monkeypatch):
    path = tmp_path / "mail.sqlite3"
    conn = connect(path)
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    _, thread = add(conn, mailbox, "a", "2 units.")
    monkeypatch.setenv("LOCAL_MODEL", "fixture-model")
    entered, release = threading.Event(), threading.Event()

    def generate(job):
        entered.set()
        release.wait(3)
        return {"findings": [], "scope": job["scope"]}

    monkeypatch.setattr(workspace, "generate", generate)
    with TestClient(create_app(conn, mailbox)) as client:
        try:
            assert client.post(f"/api/threads/{thread}/customer").json()["queued"] == 1
            assert entered.wait(1)
            assert client.get("/api/threads").status_code == 200
            assert client.get(f"/api/threads/{thread}").status_code == 200
            assert client.post(f"/api/threads/{thread}/customer").json()["queued"] == 0
        finally:
            release.set()
        for _ in range(100):
            if client.get(f"/api/threads/{thread}/customer").json()["projects"][0]["state"] == "ok":
                break
            time.sleep(0.01)
    conn.close()
