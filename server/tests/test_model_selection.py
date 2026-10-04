"""Mailbox choice is routing, never a request to re-read historical mail."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aimail import backends
from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import customer_workspace as workspace
from aimail.store import model_selection, repo
from aimail.store.db import connect
from aimail.tasks import ask_mailbox
from aimail.tasks.read import read_message
from conftest import make_raw


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "local-fixture")
    monkeypatch.setenv("CODEX_CLI_COMMAND", sys.executable)
    monkeypatch.setenv("CODEX_CLI_MODEL", "codex-fixture")
    monkeypatch.setenv("CLAUDE_CODE_CLI_COMMAND", sys.executable)
    monkeypatch.setenv("CLAUDE_CODE_CLI_MODEL", "claude-fixture")


def incoming(conn, mailbox, identity, *, subject="GPU", body="Need 2 units.", thread=None):
    pk, _ = store_raw(
        conn,
        mailbox,
        make_raw(
            message_id=f"<{identity}@selection.test>",
            subject=subject,
            body=body,
            date=datetime.now(UTC),
        ),
        "in",
        datetime.now(UTC),
        target_thread_id=thread,
    )
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    return int(pk), int(tid)


def summary(shape, *, inquiry=False):
    return shape.model_validate(
        {
            "is_inquiry": inquiry,
            "is_trade": inquiry,
            "trade_role": "buyer" if inquiry else "none",
            "mail_type": "inquiry" if inquiry else "other",
            "detected_language": "en",
            "summary_zh": "需求为 2 件。",
            "summary_en": "Need 2 units.",
            "facts": ["2 units"],
            "quoted_numbers": ["2"],
        }
    )


def test_choice_persists_without_calls_and_unavailable_provider_does_not_save(
    tmp_path, monkeypatch
):
    path = tmp_path / "mail.sqlite3"
    conn = connect(path)
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    _, thread = incoming(conn, mailbox, "one")
    monkeypatch.setattr(backends, "complete", lambda *a, **kw: pytest.fail("choice called model"))
    environment = dict(os.environ)
    with TestClient(create_app(conn, mailbox)) as client:
        initial = client.get("/api/model-selection").json()
        assert initial["selected"] == "local"
        assert {item["id"] for item in initial["options"]} == model_selection.SELECTABLE
        result = client.put(
            "/api/model-selection", json={"selected": "codex_cli"}, headers={"X-User": "operator"}
        )
        assert result.status_code == 200 and result.json()["selected"] == "codex_cli"
        assert result.json()["model"] == "Codex CLI · codex-fixture"
        assert client.get(f"/api/threads/{thread}").json()["reading"] is None
        monkeypatch.setenv("CLAUDE_CODE_CLI_COMMAND", "/missing/claude-code")
        failed = client.put(
            "/api/model-selection",
            json={"selected": "claude_code_cli"},
            headers={"X-User": "operator"},
        )
        assert failed.status_code == 503
        assert client.get("/api/model-selection").json()["selected"] == "codex_cli"
        monkeypatch.setenv("CLAUDE_CODE_CLI_COMMAND", environment["CLAUDE_CODE_CLI_COMMAND"])
        assert os.environ == environment
        assert conn.execute("SELECT count(*) FROM message_reading").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM customer_summary").fetchone()[0] == 0
    conn.close()
    restarted = connect(path)
    assert model_selection.selected(restarted, mailbox) == "codex_cli"
    restarted.close()


def test_selection_api_requires_person_and_authorized_mailbox(conn, mailbox):
    other = repo.ensure_mailbox(conn, "private@example.test")
    app = create_app(
        conn,
        mailbox,
        require_oa_auth=True,
        mailbox_access={"owner@example.test": ("sales@example.test",)},
    )
    with TestClient(app) as client:
        assert client.get("/api/model-selection").status_code == 401
        headers = {"X-OA-Email": "owner@example.test", "X-OA-User": "owner"}
        assert client.put("/api/model-selection", json={"selected": "codex_cli"}).status_code == 401
        forbidden = {**headers, "X-Mailbox-Address": "private@example.test"}
        assert client.get("/api/model-selection", headers=forbidden).status_code == 403
        assert (
            client.put(
                "/api/model-selection", json={"selected": "codex_cli"}, headers=forbidden
            ).status_code
            == 403
        )
        assert (
            client.put(
                "/api/model-selection", json={"selected": "codex_cli"}, headers=headers
            ).status_code
            == 200
        )
        assert model_selection.selected(conn, mailbox) == "codex_cli"
        assert model_selection.selected(conn, other) == "local"


def test_new_reading_captures_original_mailbox_route_and_failure_is_visible(
    conn, mailbox, monkeypatch
):
    other = repo.ensure_mailbox(conn, "other@example.test")
    first, _ = incoming(conn, mailbox, "first")
    second, _ = incoming(conn, other, "second")
    failed, thread = incoming(conn, mailbox, "failed", subject="FAILED")
    model_selection.choose(conn, mailbox, "codex_cli", "operator")
    model_selection.choose(conn, other, "claude_code_cli", "operator")
    calls = []

    def complete(system, source, shape, **kwargs):
        provider = backends.backend()
        calls.append(provider)
        if source.startswith("Subject: FAILED"):
            raise backends.LLMError("synthetic task failure")
        # Selection can change while inference is waiting. The in-flight task
        # must retain its provider and attribution through the full operation.
        if provider == "codex_cli":
            model_selection.choose(conn, mailbox, "local", "operator")
        return summary(shape)

    monkeypatch.setattr(backends, "complete", complete)
    assert read_message(conn, first, tasks=frozenset({"read"})) == "ok"
    assert repo.latest_reading(conn, first)["model"] == "Codex CLI · codex-fixture"
    assert read_message(conn, second, tasks=frozenset({"read"})) == "ok"
    assert repo.latest_reading(conn, second)["model"] == "Claude Code CLI · claude-fixture"
    assert backends.backend() == "local"
    model_selection.choose(conn, mailbox, "codex_cli", "operator")
    assert read_message(conn, failed, tasks=frozenset({"read"})) == "failed"
    assert repo.latest_reading(conn, failed)["model"] == "Codex CLI · codex-fixture"
    result = TestClient(create_app(conn, mailbox)).get(f"/api/threads/{thread}").json()
    assert result["reading"]["status"] == "failed" and result["reading"]["reason"]
    assert calls == ["codex_cli", "claude_code_cli", "codex_cli"]
    assert backends.backend() == "local"


def test_legacy_success_cache_survives_selection_and_only_changed_topic_uses_new_route(
    conn, mailbox, monkeypatch
):
    message, thread = incoming(conn, mailbox, "legacy")
    _, independent = incoming(conn, mailbox, "storage", subject="STORAGE", body="12 nodes.")
    original = conn.execute("SELECT raw_sha256 FROM message WHERE id=?", (message,)).fetchone()
    thread_row = repo.get_thread(conn, thread)
    # Recreate the deployed @1 fingerprint independently of the new helper.
    legacy_identity = [
        mailbox,
        thread,
        thread_row["contact_email"].strip().casefold(),
        [(message, original["raw_sha256"], [])],
        "Spark · local-fixture",
        ask_mailbox.TASK_VERSION,
        "customer_workspace@1",
        workspace.QUESTION,
        workspace.SOURCE_BUDGET,
    ]
    legacy_hash = hashlib.sha256(
        json.dumps(legacy_identity, ensure_ascii=False).encode()
    ).hexdigest()
    payload = {
        "findings": [],
        "scope": {"total": 1, "included": 1, "truncated": 0, "unread_attachments": 0},
    }
    conn.execute(
        "INSERT INTO customer_summary(mailbox_id,source_id,input_hash,model,task_version,"
        "produced_at,status,payload,reason) VALUES(?,?,?,?,?,?,'ok',?,'')",
        (
            mailbox,
            thread,
            legacy_hash,
            "Spark · local-fixture",
            ask_mailbox.TASK_VERSION,
            datetime.now(UTC).isoformat(),
            json.dumps(payload),
        ),
    )
    storage_job = next(
        job
        for job in workspace.claim(conn, mailbox, thread_row["contact_email"])
        if job["id"] == independent
    )
    workspace.finish(conn, storage_job, payload)
    model_selection.choose(conn, mailbox, "codex_cli", "operator")
    calls = []

    def complete(system, source, shape, **kwargs):
        calls.append(backends.backend())
        return shape.model_validate({"findings": []})

    monkeypatch.setattr(backends, "complete", complete)
    before = workspace.context(conn, mailbox, thread_row["contact_email"])
    current = next(project for project in before["projects"] if project["id"] == str(thread))
    assert current["state"] == "ok" and not current["stale"]
    assert current["summary"]["model"] == "Spark · local-fixture"
    assert workspace.claim(conn, mailbox, thread_row["contact_email"], retry=True) == []
    assert calls == []
    incoming(conn, mailbox, "new", body="Need 3 units.", thread=thread)
    jobs = workspace.claim(conn, mailbox, thread_row["contact_email"])
    assert len(jobs) == 1 and jobs[0]["id"] == thread
    assert jobs[0]["backend"] == "codex_cli"
    model_selection.choose(conn, mailbox, "local", "operator")
    workspace.finish(conn, jobs[0], workspace.generate(jobs[0]))
    assert calls == ["codex_cli"]
    after = workspace.context(conn, mailbox, thread_row["contact_email"])
    updated = next(project for project in after["projects"] if project["id"] == str(thread))
    assert updated["summary"]["model"] == "Codex CLI · codex-fixture"
    assert next(
        project for project in after["projects"] if project["id"] == str(independent)
    ) == next(project for project in before["projects"] if project["id"] == str(independent))


def test_customer_workers_are_scoped_to_job_not_current_selection(conn, mailbox, monkeypatch):
    other = repo.ensure_mailbox(conn, "other@example.test")
    _, thread = incoming(conn, mailbox, "one")
    _, other_thread = incoming(conn, other, "two")
    model_selection.choose(conn, mailbox, "codex_cli", "operator")
    model_selection.choose(conn, other, "claude_code_cli", "operator")
    jobs = workspace.claim(conn, mailbox, "mikko@aurora.test")
    other_jobs = workspace.claim(conn, other, "mikko@aurora.test")
    # Change both preferences after queueing but before the workers start.
    model_selection.choose(conn, mailbox, "local", "operator")
    model_selection.choose(conn, other, "local", "operator")
    assert jobs[0]["raw_model"] == "codex-fixture"
    assert other_jobs[0]["raw_model"] == "claude-fixture"
    monkeypatch.setenv("CODEX_CLI_MODEL", "different-codex-after-queue")
    monkeypatch.setenv("CLAUDE_CODE_CLI_MODEL", "different-claude-after-queue")
    seen, lock = [], threading.Lock()

    def complete(system, source, shape, **kwargs):
        with lock:
            seen.append((backends.backend(), backends.model_name()))
        return shape.model_validate({"findings": []})

    monkeypatch.setattr(backends, "complete", complete)
    outputs = {}

    def work(job):
        outputs[job["id"]] = workspace.generate(job)

    threads = [threading.Thread(target=work, args=(job,)) for job in jobs + other_jobs]
    for worker in threads:
        worker.start()
    for worker in threads:
        worker.join(2)
    assert sorted(seen) == [
        ("claude_code_cli", "claude-fixture"),
        ("codex_cli", "codex-fixture"),
    ]
    for job in jobs + other_jobs:
        workspace.finish(conn, job, outputs[job["id"]])
    assert (
        conn.execute("SELECT model FROM customer_summary WHERE source_id=?", (thread,)).fetchone()[
            0
        ]
        == "Codex CLI · codex-fixture"
    )
    assert (
        conn.execute(
            "SELECT model FROM customer_summary WHERE source_id=?", (other_thread,)
        ).fetchone()[0]
        == "Claude Code CLI · claude-fixture"
    )
    assert backends.backend() == "local"


def test_api_draft_assistant_and_explicit_analyze_use_selected_mailbox(conn, mailbox, monkeypatch):
    _, thread = incoming(conn, mailbox, "one")
    model_selection.choose(conn, mailbox, "codex_cli", "operator")
    seen = []

    def complete(system, source, shape, **kwargs):
        seen.append((shape.__name__, backends.backend()))
        if shape.__name__ == "InquirySummary":
            return summary(shape)
        if shape.__name__ == "ReplyDraft":
            return shape.model_validate(
                {
                    "language": "en",
                    "subject": "Re: GPU",
                    "body": "Thanks.",
                    "open_questions": [],
                    "quoted_numbers": [],
                }
            )
        return shape.model_validate({"findings": []})

    monkeypatch.setattr(backends, "complete", complete)
    with TestClient(create_app(conn, mailbox)) as client:
        headers = {"X-User": "operator"}
        assert (
            client.post(f"/api/threads/{thread}/draft", headers=headers).json()["draft"]["model"]
            == "Codex CLI · codex-fixture"
        )
        assert (
            client.post(
                "/api/assistant", headers=headers, json={"question": "Summarize."}
            ).status_code
            == 200
        )
        assert (
            client.get("/api/assistant").json()["turns"][0]["model"] == "Codex CLI · codex-fixture"
        )
        assert client.post(f"/api/threads/{thread}/analyze", headers=headers).status_code == 200
        assert client.post(f"/api/threads/{thread}/analyze", headers=headers).status_code == 200
        assert conn.execute("SELECT count(*) FROM message_reading").fetchone()[0] == 2
    assert seen == [
        ("ReplyDraft", "codex_cli"),
        ("Answer", "codex_cli"),
        ("InquirySummary", "codex_cli"),
        ("InquirySummary", "codex_cli"),
    ]
    assert backends.backend() == "local"
