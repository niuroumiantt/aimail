"""Local pull-worker protocol, authentication probes and transport boundaries."""

import copy
import importlib
import json
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest
from tools import run_cli_worker as worker

CAPABILITIES = [{"backend": "codex_cli", "model": "exact-model", "verified": True}]
JOB = {
    "id": 7,
    "nonce": "abc123",
    "lease_token": "def456",
    "backend": "codex_cli",
    "model": "exact-model",
    "system": "PRIVATE_TASK",
    "user": "PRIVATE_MAIL $(touch /tmp/should-not-exist)",
    "schema": {"type": "object"},
}


class FakeTransport:
    def __init__(self, *, finish_failures=0, job=None):
        self.calls = []
        self.finish_failures = finish_failures
        self.job = copy.deepcopy(JOB if job is None else job)
        self.beat = threading.Event()

    def call(self, action, payload, *, cancel=None):
        self.calls.append((action, copy.deepcopy(payload)))
        if action == "heartbeat":
            if sum(name == "heartbeat" for name, _ in self.calls) > 1:
                self.beat.set()
            return {"ok": True}
        if action == "claim":
            return {"job": self.job}
        if self.finish_failures:
            self.finish_failures -= 1
            raise worker.RemoteError("SSH request failed")
        return {"accepted": True}


def configure_cli(monkeypatch, complete):
    def configuration(backend, *, model):
        if backend != "codex_cli":
            raise worker.cli.CLIError("Not installed")
        assert model == "exact-model"
        return SimpleNamespace(model=model)

    monkeypatch.setenv("CODEX_CLI_MODEL", "exact-model")
    monkeypatch.setattr(worker.cli, "configuration", configuration)
    monkeypatch.setattr(worker.cli, "complete", complete)


def test_main_probes_actual_answer_before_registration_and_keeps_mail_on_stdin(monkeypatch, capsys):
    calls = []

    def complete(backend, system, user, schema, *, model, allow_bridge):
        calls.append(("model", backend, system, user, model, allow_bridge))
        return '{"ok":true}' if schema is worker.PROBE_SCHEMA else '{"private":"RESULT"}'

    configure_cli(monkeypatch, complete)

    def run(arguments, request, timeout, cancel):
        action = arguments[-1]
        payload = json.loads(request)
        calls.append(("ssh", action, copy.deepcopy(arguments), payload))
        if action == "heartbeat":
            return b'{"ok":true}'
        if action == "claim":
            return json.dumps({"job": JOB}).encode()
        return b'{"accepted":true}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert worker.main(["--once", "--ssh-host", "operator-alias", "--container", "mail-app"]) == 0
    assert calls[0][0] == "model"
    assert calls[0][-1] is False
    remote = [entry for entry in calls if entry[0] == "ssh"]
    assert [entry[1] for entry in remote] == ["heartbeat", "claim", "finish"]
    assert remote[0][2] == [
        "ssh",
        "-T",
        "-oBatchMode=yes",
        "-oConnectTimeout=8",
        "operator-alias",
        "docker",
        "exec",
        "-i",
        "mail-app",
        "python",
        "-m",
        "aimail.cli_worker",
        "heartbeat",
    ]
    worker_ids = [entry[3]["worker_id"] for entry in remote]
    assert len(set(worker_ids)) == 1
    assert remote[0][3]["capabilities"] == CAPABILITIES
    assert remote[0][3]["lease_seconds"] == 120
    assert remote[2][3]["output"] == '{"private":"RESULT"}'
    for entry in remote:
        assert "PRIVATE_MAIL" not in " ".join(entry[2])
        assert "RESULT" not in " ".join(entry[2])
    log = capsys.readouterr()
    assert "PRIVATE_MAIL" not in log.out + log.err
    assert "PRIVATE_TASK" not in log.out + log.err
    assert "RESULT" not in log.out + log.err
    assert "abc123" not in log.out + log.err


@pytest.mark.parametrize("answer", ['{"ok":1}', '{"ok":true,"secret":"x"}', "not json"])
def test_failed_probe_never_registers_a_capability(monkeypatch, answer):
    configure_cli(monkeypatch, lambda *args, **kwargs: answer)
    contacted = []
    monkeypatch.setattr(worker, "_run_ssh", lambda *args: contacted.append(args))
    assert worker.main(["--once"]) == 2
    assert not contacted


def test_probe_cannot_bridge_or_print_private_cli_error(monkeypatch, capsys):
    def complete(*args, **kwargs):
        assert kwargs["allow_bridge"] is False
        raise worker.cli.CLIError("PRIVATE_MAIL credential-value")

    configure_cli(monkeypatch, complete)
    assert worker.probe_capabilities() == []
    logs = capsys.readouterr()
    assert "PRIVATE_MAIL" not in logs.out + logs.err
    assert "credential-value" not in logs.out + logs.err


def test_lost_finish_ack_reuses_same_result_and_lease_without_rerunning_cli(monkeypatch):
    transport = FakeTransport(finish_failures=2)
    invoked = []

    def complete(*args, **kwargs):
        invoked.append((args, kwargs))
        return '{"result":42}'

    monkeypatch.setattr(worker.cli, "complete", complete)
    instance = worker.Worker(transport, CAPABILITIES, worker_id="stable-id", retry_seconds=0.001)
    instance.serve(once=True)
    assert len(invoked) == 1
    assert invoked[0][1] == {"model": "exact-model", "allow_bridge": False}
    finishes = [payload for action, payload in transport.calls if action == "finish"]
    assert len(finishes) == 3
    assert all(payload == finishes[0] for payload in finishes)
    assert finishes[0] == {
        "worker_id": "stable-id",
        "id": 7,
        "nonce": "abc123",
        "lease_token": "def456",
        "output": '{"result":42}',
    }


def test_heartbeats_continue_during_blocking_inference_and_stop_on_completion(monkeypatch):
    transport = FakeTransport()

    def complete(*args, **kwargs):
        assert transport.beat.wait(timeout=2), "No heartbeat during inference"
        return '{"result":42}'

    monkeypatch.setattr(worker.cli, "complete", complete)
    instance = worker.Worker(transport, CAPABILITIES, heartbeat_seconds=0.01)
    instance.serve(once=True)
    assert sum(action == "heartbeat" for action, _ in transport.calls) >= 2
    assert instance._stop.is_set()
    assert not any(thread.name == "aimail-worker-heartbeat" for thread in threading.enumerate())


def test_remote_model_must_match_verified_exact_model(monkeypatch):
    job = {**JOB, "model": "different-model"}
    transport = FakeTransport(job=job)
    invoked = []
    monkeypatch.setattr(worker.cli, "complete", lambda *args, **kwargs: invoked.append(args))
    worker.Worker(transport, CAPABILITIES).serve(once=True)
    assert not invoked
    finish = [payload for action, payload in transport.calls if action == "finish"]
    assert len(finish) == 1
    assert "error" in finish[0] and "output" not in finish[0]


def test_inference_error_is_generic_and_cannot_echo_private_input(monkeypatch, capsys):
    transport = FakeTransport()

    def complete(*args, **kwargs):
        raise RuntimeError("PRIVATE_MAIL secret output")

    monkeypatch.setattr(worker.cli, "complete", complete)
    worker.Worker(transport, CAPABILITIES).serve(once=True)
    finish = [payload for action, payload in transport.calls if action == "finish"][0]
    assert finish["error"] == "Local CLI inference failed; check login and model access"
    logs = capsys.readouterr()
    assert "PRIVATE_MAIL" not in logs.out + logs.err
    assert "secret output" not in logs.out + logs.err


def test_bridge_disabled_is_reported_safely_without_claiming(monkeypatch, capsys):
    configure_cli(monkeypatch, lambda *args, **kwargs: '{"ok":true}')
    calls = []

    def run(arguments, request, timeout, cancel):
        calls.append(arguments[-1])
        return b'{"error":"bridge_disabled"}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert worker.main(["--once"]) == 2
    assert calls == ["heartbeat"]
    assert "Remote CLI bridge is disabled" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("code", "message", "retryable"),
    [
        ("model_mismatch", "Local CLI model does not match the server configuration", False),
        ("worker_conflict", "Another CLI worker is active; waiting for its lease", True),
        ("invalid_request", "CLI worker protocol or configuration is invalid", False),
    ],
)
def test_known_remote_errors_have_clear_fixed_messages(monkeypatch, code, message, retryable):
    response = json.dumps({"error": code, "detail": "PRIVATE_MAIL"}).encode()
    monkeypatch.setattr(worker, "_run_ssh", lambda *args: response)
    with pytest.raises(worker.RemoteError) as failure:
        worker.SSHTransport().call("heartbeat", {})
    assert str(failure.value) == message
    assert failure.value.retryable is retryable
    assert "PRIVATE_MAIL" not in str(failure.value)


def test_default_command_targets_verified_production_container(monkeypatch):
    configure_cli(monkeypatch, lambda *args, **kwargs: '{"ok":true}')
    commands = []

    def run(arguments, request, timeout, cancel):
        commands.append(arguments)
        if arguments[-1] == "heartbeat":
            return b'{"ok":true}'
        return b'{"job":null}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert worker.main(["--once"]) == 0
    assert worker.SSHTransport().container == "mainland-aimail-1"
    assert len(commands) == 2
    assert all(command[command.index("-i") + 1] == "mainland-aimail-1" for command in commands)


@pytest.mark.parametrize("name", ["-bad", "host;touch", "a b", "a\n", "$(bad)", "a@b", "a/b"])
def test_shell_fragments_cannot_be_used_as_ssh_alias_or_container(name):
    with pytest.raises(ValueError):
        worker.SSHTransport(host=name)
    with pytest.raises(ValueError):
        worker.SSHTransport(container=name)


def _local_process(monkeypatch, program):
    original = subprocess.Popen
    calls = []

    def launch(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return original([sys.executable, "-c", program], **kwargs)

    monkeypatch.setattr(worker.subprocess, "Popen", launch)
    return calls


def test_ssh_process_receives_only_json_stdin_and_discards_private_stderr(monkeypatch, capsys):
    calls = _local_process(
        monkeypatch,
        "import json,sys; data=json.load(sys.stdin); "
        "sys.stderr.write('PRIVATE_ERROR'); "
        "print(json.dumps({'received':data['user']}))",
    )
    result = worker.SSHTransport().call("finish", {"user": "PRIVATE_MAIL"})
    assert result == {"received": "PRIVATE_MAIL"}
    assert calls[0][1]["stderr"] is subprocess.DEVNULL
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["start_new_session"] is True
    assert "PRIVATE_MAIL" not in " ".join(calls[0][0])
    assert capsys.readouterr().err == ""


def test_ssh_stdout_limit_kills_oversized_response_before_it_is_parsed(monkeypatch):
    monkeypatch.setattr(worker, "MAX_RESPONSE_BYTES", 1024)
    _local_process(
        monkeypatch,
        "import sys,time; sys.stdout.write('x'*4096); sys.stdout.flush(); time.sleep(5)",
    )
    with pytest.raises(worker.RemoteError, match="exceeded limit"):
        worker.SSHTransport(timeout=1).call("claim", {"worker_id": "test"})


def test_ssh_timeout_and_cancellation_stop_without_private_output(monkeypatch):
    _local_process(monkeypatch, "import time; time.sleep(5)")
    with pytest.raises(worker.RemoteError, match="timed out"):
        worker.SSHTransport(timeout=0.05).call("claim", {"worker_id": "test"})
    cancel = threading.Event()
    timer = threading.Timer(0.02, cancel.set)
    timer.start()
    try:
        with pytest.raises(worker.RemoteError, match="interrupted"):
            worker.SSHTransport(timeout=1).call("heartbeat", {}, cancel=cancel)
    finally:
        timer.join()


def test_remote_errors_and_non_json_never_echo_response(monkeypatch):
    for response in (b'{"error":"PRIVATE_MAIL"}', b"PRIVATE_MAIL", b'"PRIVATE_MAIL"'):
        monkeypatch.setattr(worker, "_run_ssh", lambda *args, value=response: value)
        with pytest.raises(worker.RemoteError) as failure:
            worker.SSHTransport().call("claim", {"worker_id": "test"})
        assert "PRIVATE_MAIL" not in str(failure.value)


def test_worker_help_runs_without_product_or_third_party_python_dependencies():
    result = subprocess.run(
        [sys.executable, "-S", str(worker.Path(worker.__file__).resolve()), "--help"],
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"--codex-model" in result.stdout
    assert b"--claude-model" in result.stdout


def test_explicit_probe_model_does_not_change_environment_or_consult_remote_bridge(monkeypatch):
    monkeypatch.setenv("LLM_CLI_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("CODEX_CLI_MODEL", "environment-model")
    configs = []
    probes = []

    def configuration(backend, *, model):
        if backend != "codex_cli":
            raise worker.cli.CLIError("Unavailable")
        configs.append((backend, model))
        return SimpleNamespace(model=model)

    def complete(*args, **kwargs):
        probes.append(kwargs)
        return '{"ok":true}'

    monkeypatch.setattr(worker.cli, "configuration", configuration)
    monkeypatch.setattr(worker.cli, "complete", complete)
    monkeypatch.setattr(
        worker.cli, "ready", lambda *args, **kwargs: pytest.fail("Remote readiness")
    )
    assert worker.probe_capabilities(codex_model="argument-model") == [
        {"backend": "codex_cli", "model": "argument-model", "verified": True}
    ]
    assert configs == [("codex_cli", "argument-model")]
    assert probes == [{"model": "argument-model", "allow_bridge": False}]
    assert worker.os.environ["CODEX_CLI_MODEL"] == "environment-model"
    assert worker.os.environ["LLM_CLI_BRIDGE_ENABLED"] == "1"


def test_result_larger_than_bridge_default_is_reported_as_failure(monkeypatch):
    monkeypatch.setattr(worker, "MAX_RESULT_BYTES", 10)
    monkeypatch.setattr(worker.cli, "complete", lambda *args, **kwargs: "PRIVATE_TOO_LONG")
    transport = FakeTransport()
    worker.Worker(transport, CAPABILITIES).serve(once=True)
    finish = [payload for action, payload in transport.calls if action == "finish"][0]
    assert "output" not in finish
    assert "PRIVATE_TOO_LONG" not in finish["error"]


def test_normal_registration_reconnects_before_claiming_without_repeating_inference(monkeypatch):
    transport = FakeTransport()
    original = transport.call
    registration = 0

    def call(action, payload, **kwargs):
        nonlocal registration
        if action == "heartbeat":
            registration += 1
            if registration == 1:
                raise worker.RemoteError("SSH request failed")
        result = original(action, payload, **kwargs)
        if action == "finish":
            instance._stop.set()
        return result

    transport.call = call
    invoked = []

    def complete(*args, **kwargs):
        invoked.append(args)
        return '{"ok":true}'

    monkeypatch.setattr(worker.cli, "complete", complete)
    instance = worker.Worker(transport, CAPABILITIES, retry_seconds=0.001)
    instance.serve()
    assert registration == 2
    assert len(invoked) == 1


def test_wire_protocol_matches_real_broker_and_never_recurses_into_bridge(tmp_path, monkeypatch):
    bridge = importlib.import_module("_aimail_pull_backends.cli_bridge")
    monkeypatch.setenv("LLM_CLI_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("LLM_CLI_BRIDGE_DB", str(tmp_path / "bridge.sqlite3"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "mail.sqlite3"))
    monkeypatch.setenv("CODEX_CLI_MODEL", "exact-model")

    def run(arguments, request, timeout, cancel):
        payload = json.loads(request)
        action = arguments[-1]
        if action == "heartbeat":
            result = bridge.heartbeat(**payload)
        elif action == "claim":
            result = bridge.claim(**payload)
        else:
            result = bridge.finish(
                payload["worker_id"],
                payload["id"],
                payload["nonce"],
                payload["lease_token"],
                payload.get("output"),
                payload.get("error"),
            )
        return json.dumps(result).encode()

    invoked = []

    def complete(*args, **kwargs):
        assert kwargs["allow_bridge"] is False
        invoked.append(args)
        return '{"answer":"synthetic"}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    monkeypatch.setattr(worker.cli, "complete", complete)
    instance = worker.Worker(worker.SSHTransport(), CAPABILITIES, worker_id="stable-worker")
    instance.heartbeat()
    job_id, nonce = bridge.submit(
        "codex_cli", "exact-model", "Synthetic system", "Synthetic source", {"type": "object"}
    )
    instance.serve(once=True)
    assert bridge.result(job_id, nonce) == ("ok", '{"answer":"synthetic"}')
    assert len(invoked) == 1
