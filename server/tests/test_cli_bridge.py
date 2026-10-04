"""Attack the optional private SSH queue with real independent SQLite connections."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from pydantic import BaseModel

from aimail import backends
from aimail.backends import cli_bridge as bridge

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
CAPS = [{"backend": "codex_cli", "model": "dev-one", "verified": True}]


@pytest.fixture(autouse=True)
def bridge_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CLI_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "mailbox.sqlite3"))
    monkeypatch.setenv("LLM_CLI_BRIDGE_DB", str(tmp_path / "cli-bridge.sqlite3"))
    monkeypatch.setenv("LLM_CLI_TIMEOUT", "2")
    monkeypatch.setenv("LLM_CLI_MAX_OUTPUT_BYTES", "2097152")
    monkeypatch.setenv("LLM_CLI_BRIDGE_MAX_INPUT_BYTES", "1048576")
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "local-fast")
    monkeypatch.delenv("CODEX_CLI_MODEL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_CLI_MODEL", raising=False)
    monkeypatch.setenv("CODEX_CLI_COMMAND", "/missing/server/codex")


def register(worker="worker-one", caps=CAPS):
    assert bridge.heartbeat(worker, caps) == {"ok": True}


def submit():
    return bridge.submit("codex_cli", "dev-one", "fixed contract", "PRIVATE_MAIL", SCHEMA)


def finish(job, worker="worker-one", output='{"ok":true}', error=None):
    return bridge.finish(worker, job["id"], job["nonce"], job["lease_token"], output, error)


def test_bridge_is_explicitly_opt_in_and_does_not_touch_main_db(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_CLI_BRIDGE_ENABLED")
    assert bridge.ready("codex_cli")[0] is False
    with pytest.raises(bridge.BridgeError, match="bridge_disabled"):
        register()
    assert not (tmp_path / "cli-bridge.sqlite3").exists()
    assert not (tmp_path / "mailbox.sqlite3").exists()
    monkeypatch.setenv("LLM_CLI_BRIDGE_ENABLED", "1")
    register()
    assert not (tmp_path / "mailbox.sqlite3").exists()
    assert (tmp_path / "cli-bridge.sqlite3").stat().st_mode & 0o777 == 0o600
    monkeypatch.setenv("LLM_CLI_BRIDGE_DB", str(tmp_path / "mailbox.sqlite3"))
    with pytest.raises(bridge.BridgeError, match="invalid_configuration"):
        submit()


def test_verified_live_worker_drives_catalog_and_exact_model_attribution(monkeypatch):
    assert bridge.ready("codex_cli")[0] is False
    assert backends.provider_catalog()[0]["available"] is False
    register()
    choice = backends.provider_catalog()[0]
    assert choice["available"] and choice["model"] == "dev-one"
    assert "已连接" in choice["reason"]
    assert "missing/server" not in json.dumps(choice)
    monkeypatch.setenv("CODEX_CLI_MODEL", "another-model")
    assert bridge.ready("codex_cli")[0] is False
    with pytest.raises(bridge.BridgeError, match="model_mismatch"):
        register()


def test_unverified_capability_and_active_second_worker_are_rejected():
    with pytest.raises(bridge.BridgeError, match="invalid_request"):
        register(caps=[{**CAPS[0], "verified": False}])
    register()
    with pytest.raises(bridge.BridgeError, match="worker_conflict"):
        register(worker="second-worker")


def test_atomic_claim_nonce_lease_and_idempotent_finish():
    register()
    job_id, nonce = submit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: bridge.claim("worker-one"), range(2)))
    jobs = [claim["job"] for claim in claims if claim["job"] is not None]
    assert len(jobs) == 1
    job = jobs[0]
    assert job["id"] == job_id and job["nonce"] == nonce and job["user"] == "PRIVATE_MAIL"
    assert finish({**job, "nonce": "wrong"}) == {"accepted": False}
    assert finish({**job, "lease_token": "wrong"}) == {"accepted": False}
    assert finish(job, worker="other-worker") == {"accepted": False}
    assert finish(job) == {"accepted": True}
    assert finish(job) == {"accepted": True}, "identical completion retry only acknowledges"
    assert finish(job, output='{"ok":false}') == {"accepted": False}
    assert bridge.result(job_id, nonce) == ("ok", '{"ok":true}')
    assert bridge.claim("worker-one") == {"job": None}


def test_heartbeat_renews_running_lease_and_model_cannot_change_while_active(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(bridge.time, "time", lambda: clock[0])
    monkeypatch.setenv("LLM_CLI_TIMEOUT", "300")
    register()
    job_id, nonce = submit()
    job = bridge.claim("worker-one")["job"]
    clock[0] += 100
    register()
    with pytest.raises(bridge.BridgeError, match="worker_conflict"):
        register(caps=[{**CAPS[0], "model": "dev-two"}])
    clock[0] += 100
    assert finish(job) == {"accepted": True}, "renewed lease remains valid after original TTL"
    assert bridge.result(job_id, nonce)[0] == "ok"


def test_timeout_and_worker_loss_reject_late_results_without_reexecution(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(bridge.time, "time", lambda: clock[0])
    monkeypatch.setenv("LLM_CLI_TIMEOUT", "300")
    register()
    job_id, nonce = submit()
    job = bridge.claim("worker-one")["job"]
    clock[0] += 121
    assert bridge.result(job_id, nonce) == ("failed", "worker_disconnected")
    assert finish(job) == {"accepted": False}
    assert bridge.ready("codex_cli")[0] is False
    register(worker="new-worker")
    assert bridge.claim("new-worker") == {"job": None}
    next_id, next_nonce = submit()
    clock[0] += 301
    assert bridge.result(next_id, next_nonce) == ("failed", "request_timeout")


def test_queue_bounds_input_output_and_scrubs_worker_errors(monkeypatch):
    register()
    monkeypatch.setenv("LLM_CLI_BRIDGE_MAX_INPUT_BYTES", "1024")
    with pytest.raises(bridge.BridgeError, match="input_too_large"):
        bridge.submit("codex_cli", "dev-one", "sys", "PRIVATE_MAIL" * 1000, SCHEMA)
    job_id, nonce = submit()
    job = bridge.claim("worker-one")["job"]
    monkeypatch.setenv("LLM_CLI_MAX_OUTPUT_BYTES", "1024")
    with pytest.raises(bridge.BridgeError, match="output_too_large"):
        finish(job, output="PRIVATE_TOKEN" * 1000)
    assert finish(job, error="PRIVATE_TOKEN echoed stderr") == {"accepted": True}
    assert bridge.result(job_id, nonce) == ("failed", "worker_call_failed")
    with bridge._database() as connection:
        row = dict(connection.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone())
    assert row["output"] is None and "PRIVATE_TOKEN" not in json.dumps(row)


def test_server_complete_uses_remote_output_then_deletes_duplicate_source():
    class Result(BaseModel):
        ok: bool

    register()

    def model_request():
        with backends.use_backend("codex_cli"):
            assert backends.describe() == "Codex CLI · dev-one"
            return backends.complete("fixed contract", "PRIVATE_MAIL", Result)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(model_request)
        deadline, job = time.monotonic() + 2, None
        while time.monotonic() < deadline and job is None:
            job = bridge.claim("worker-one")["job"]
            if job is None:
                time.sleep(0.01)
        assert job is not None
        assert finish(job) == {"accepted": True}
        assert pending.result(timeout=2).ok is True
    with bridge._database() as connection:
        assert connection.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0
    assert finish(job) == {"accepted": False}


def test_disconnected_bridge_fails_loudly_without_local_fallback():
    class Result(BaseModel):
        ok: bool

    with pytest.raises(backends.LLMError, match="未连接"):
        with backends.use_backend("codex_cli", model="dev-one"):
            backends.complete("task", "mail", Result)


def test_registered_model_change_preserves_outer_snapshot_and_catalog_is_independent():
    register()
    with backends.use_backend("codex_cli"):
        assert backends.model_name() == "dev-one"
        register(caps=[{**CAPS[0], "model": "dev-two"}])
        with backends.use_backend("codex_cli"):
            assert backends.model_name() == "dev-one"
            assert backends.ready()[0] is False
        assert backends.provider_catalog()[0]["model"] == "dev-two"
        assert backends.model_name() == "dev-one"
        with backends.use_backend("local"):
            assert backends.model_name() == "local-fast"
        assert backends.describe() == "Codex CLI · dev-one"
    assert backends.model_name() == "local-fast"


def test_real_concurrent_registration_change_never_executes_new_model_as_old():
    class Result(BaseModel):
        ok: bool

    register()
    captured = threading.Event()
    changed = threading.Event()

    def task():
        with backends.use_backend("codex_cli"):
            captured.set()
            assert changed.wait(timeout=2)
            with backends.use_backend("codex_cli"):
                assert backends.describe() == "Codex CLI · dev-one"
                with pytest.raises(backends.LLMError, match="未连接"):
                    backends.complete("task", "mail", Result)
            return backends.describe()

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(task)
        assert captured.wait(timeout=2)
        register(caps=[{**CAPS[0], "model": "dev-two"}])
        changed.set()
        assert running.result(timeout=2) == "Codex CLI · dev-one"
    with bridge._database() as connection:
        assert connection.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0


def test_retention_removes_abandoned_scope_payloads(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(bridge.time, "time", lambda: clock[0])
    register()
    job_id, nonce = submit()
    clock[0] += 3
    assert bridge.result(job_id, nonce)[0] == "failed"
    clock[0] += bridge.RETENTION + 1
    with pytest.raises(bridge.BridgeError, match="job_expired"):
        bridge.result(job_id, nonce)


def test_legacy_default_mailbox_cannot_be_used_as_bridge_database(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DB_PATH")
    legacy = tmp_path / "data" / "mail2leads.sqlite3"
    legacy.parent.mkdir()
    legacy.write_bytes(b"IMMUTABLE_LEGACY_DATABASE")
    monkeypatch.setenv("LLM_CLI_BRIDGE_DB", "data/mail2leads.sqlite3")
    with pytest.raises(bridge.BridgeError, match="invalid_configuration"):
        submit()
    assert legacy.read_bytes() == b"IMMUTABLE_LEGACY_DATABASE"


def test_database_lock_wait_cannot_accept_a_result_after_deadline(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(bridge.time, "time", lambda: clock[0])
    register()
    job_id, nonce = submit()
    job = bridge.claim("worker-one")["job"]
    entered = threading.Event()
    original = bridge._database

    @contextmanager
    def tracked_database():
        entered.set()
        with original() as connection:
            yield connection

    lock = sqlite3.connect(bridge.database_path(), isolation_level=None)
    lock.execute("BEGIN IMMEDIATE")
    monkeypatch.setattr(bridge, "_database", tracked_database)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(finish, job)
            assert entered.wait(timeout=1)
            clock[0] += 3
            lock.rollback()
            assert pending.result(timeout=2) == {"accepted": False}
    finally:
        lock.close()
    assert bridge.result(job_id, nonce) == ("failed", "request_timeout")
