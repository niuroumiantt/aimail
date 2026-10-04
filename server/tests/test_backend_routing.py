"""Provider routing must not leak between mailboxes, threads, tasks or catalog reads."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import BaseModel

from aimail import backends


class Answer(BaseModel):
    provider: str
    model: str


@pytest.fixture(autouse=True)
def configured_backends(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "local-fast")
    monkeypatch.setenv("CODEX_CLI_MODEL", "codex-dev")
    monkeypatch.setenv("CLAUDE_CODE_CLI_MODEL", "claude-dev")
    # Existence is configuration validation, not a claim Python is an actual CLI.
    monkeypatch.setenv("CODEX_CLI_COMMAND", sys.executable)
    monkeypatch.setenv("CLAUDE_CODE_CLI_COMMAND", sys.executable)
    monkeypatch.setenv("MODEL", "claude-api-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key")
    monkeypatch.setenv("LLM_CLI_TIMEOUT", "3")
    monkeypatch.setenv("LLM_CLI_MAX_OUTPUT_BYTES", "2097152")


def test_scoped_local_selection_overrides_cli_env_without_mutating_env(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "codex_cli")
    environment = dict(os.environ)
    assert backends.backend() == "codex_cli"
    with backends.use_backend("local"):
        assert backends.backend() == "local"
        assert backends.model_name() == "local-fast"
        assert backends.describe() == "Spark · local-fast"
        assert backends.ready()[0]
    assert backends.backend() == "codex_cli"
    assert dict(os.environ) == environment


def test_nested_scope_and_exception_restore_previous_selection():
    with backends.use_backend("codex_cli"):
        assert backends.model_name() == "codex-dev"
        with pytest.raises(RuntimeError, match="cancelled"):
            with backends.use_backend("claude_code_cli"):
                assert backends.describe() == "Claude Code CLI · claude-dev"
                raise RuntimeError("cancelled")
        assert backends.backend() == "codex_cli"
    assert backends.backend() == "local"


@pytest.mark.parametrize("name", ["spark", "CODEX_CLI", " local ", "https://secret@host", None, {}])
def test_provider_id_is_an_enum_not_a_client_command_or_url(name):
    with pytest.raises(backends.LLMError) as error:
        with backends.use_backend(name):
            pytest.fail("unreachable")
    assert "secret" not in str(error.value)
    assert backends.backend() == "local"


def test_catalog_has_only_requested_choices_and_preserves_scope_without_inference(monkeypatch):
    def no_inference(*args, **kwargs):
        pytest.fail("catalog must not call a model")

    monkeypatch.setattr(backends, "complete", no_inference)
    with backends.use_backend("claude"):
        catalog = backends.provider_catalog()
        assert backends.backend() == "claude"
        assert backends.model_name() == "claude-api-model"
    assert [entry["id"] for entry in catalog] == ["codex_cli", "claude_code_cli", "local"]
    assert [entry["label"] for entry in catalog] == ["Codex CLI", "Claude Code CLI", "Spark"]
    assert all(entry["available"] for entry in catalog)
    assert all(set(entry) == {"id", "label", "available", "model", "reason"} for entry in catalog)
    assert "运行时核验" in catalog[0]["reason"]


def test_catalog_explains_unconfigured_cli_and_hides_addresses_and_secrets(monkeypatch):
    monkeypatch.setenv("LOCAL_BASE_URL", "https://secret:password@private-host/v1?token=secret")
    monkeypatch.setenv("LOCAL_API_KEY", "PRIVATE_GATEWAY_KEY")
    monkeypatch.setenv("CODEX_CLI_COMMAND", "/private/secret/missing-codex")
    monkeypatch.delenv("CLAUDE_CODE_CLI_MODEL")
    catalog = backends.provider_catalog()
    assert catalog[0]["available"] is False
    assert "未安装" in catalog[0]["reason"]
    assert catalog[1]["available"] is False and "指定模型" in catalog[1]["reason"]
    public = json.dumps(catalog)
    assert all(value not in public for value in ["secret", "private-host", "PRIVATE_GATEWAY_KEY"])
    monkeypatch.setenv("LOCAL_MODEL", "https://credential@accidental-url")
    local = backends.provider_catalog()[2]
    assert local["model"] == "" and local["available"] is False
    assert "credential" not in json.dumps(local)


def test_two_threads_call_and_sign_independent_selected_backends(monkeypatch):
    from aimail.backends import cli

    barrier = threading.Barrier(2)

    def local(system, user, shape, **options):
        barrier.wait(timeout=3)
        assert backends.backend() == "local"
        return json.dumps({"provider": backends.backend(), "model": backends.model_name()})

    def cli_call(backend, system, user, schema, **options):
        barrier.wait(timeout=3)
        assert backend == backends.backend() == "codex_cli"
        return json.dumps({"provider": backend, "model": backends.model_name()})

    monkeypatch.setattr(backends, "_call_local", local)
    monkeypatch.setattr(cli, "complete", cli_call)

    def run(name):
        with backends.use_backend(name):
            answer = backends.complete("task", "untrusted mail", Answer)
            return answer, backends.describe()

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(run, "local")
        two = pool.submit(run, "codex_cli")
        assert one.result() == (Answer(provider="local", model="local-fast"), "Spark · local-fast")
        assert two.result() == (
            Answer(provider="codex_cli", model="codex-dev"),
            "Codex CLI · codex-dev",
        )
    assert backends.backend() == "local"


def test_interleaved_async_requests_keep_their_selection():
    async def run():
        entered = 0
        ready = asyncio.Event()

        async def request(name):
            nonlocal entered
            with backends.use_backend(name):
                entered += 1
                if entered == 2:
                    ready.set()
                await ready.wait()
                await asyncio.sleep(0)
                return backends.backend(), backends.model_name(), backends.describe()

        return await asyncio.gather(request("local"), request("claude_code_cli"))

    assert asyncio.run(run()) == [
        ("local", "local-fast", "Spark · local-fast"),
        ("claude_code_cli", "claude-dev", "Claude Code CLI · claude-dev"),
    ]
    assert backends.backend() == "local"


def test_queued_worker_keeps_captured_selection_when_caller_changes():
    with backends.use_backend("codex_cli"):
        captured = backends.backend()

    def worker():
        assert backends.backend() == "local", "new threads do not inherit request context"
        with backends.use_backend(captured):
            return backends.describe()

    with backends.use_backend("claude_code_cli"), ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(worker).result() == "Codex CLI · codex-dev"
        assert backends.backend() == "claude_code_cli"
    assert backends.backend() == "local"


def test_repair_attempt_stays_on_selected_provider_and_restores_after_failure(monkeypatch):
    from aimail.backends import cli

    calls = []

    def invalid(backend, *args, **kwargs):
        calls.append((backend, backends.backend(), backends.describe()))
        return "invalid JSON"

    monkeypatch.setattr(cli, "complete", invalid)
    with pytest.raises(backends.LLMError, match="两次"):
        with backends.use_backend("claude_code_cli"):
            backends.complete("task", "mail", Answer)
    assert calls == [
        ("claude_code_cli", "claude_code_cli", "Claude Code CLI · claude-dev"),
        ("claude_code_cli", "claude_code_cli", "Claude Code CLI · claude-dev"),
    ]
    assert backends.backend() == "local"
