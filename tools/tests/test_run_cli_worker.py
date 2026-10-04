"""Local pull-worker protocol, authentication probes and transport boundaries."""

import copy
import importlib
import json
import os
import shlex
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


@pytest.mark.parametrize("ssh_sudo", [False, True])
def test_main_checks_remote_then_probes_before_registration_and_keeps_mail_on_stdin(
    monkeypatch, capsys, ssh_sudo
):
    calls = []

    def complete(backend, system, user, schema, *, model, allow_bridge):
        calls.append(("model", backend, system, user, model, allow_bridge))
        return '{"ok":true}' if schema is worker.PROBE_SCHEMA else '{"private":"RESULT"}'

    configure_cli(monkeypatch, complete)

    def run(arguments, request, timeout, cancel):
        action = arguments[-1]
        if action == "-":
            assert request == worker.REMOTE_CHECK_SCRIPT
            calls.append(("preflight", copy.deepcopy(arguments)))
            return b'{"enabled":true}'
        payload = json.loads(request)
        calls.append(("ssh", action, copy.deepcopy(arguments), payload))
        if action == "heartbeat":
            return b'{"ok":true}'
        if action == "claim":
            return json.dumps({"job": JOB}).encode()
        return b'{"accepted":true}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert (
        worker.main(
            ["--once", "--ssh-host", "operator-alias", "--container", "mail-app"]
            + (["--ssh-sudo"] if ssh_sudo else [])
        )
        == 0
    )
    assert calls[0][0] == "preflight"
    assert calls[1][0] == "model"
    assert calls[1][-1] is False
    remote = [entry for entry in calls if entry[0] == "ssh"]
    assert [entry[1] for entry in remote] == ["heartbeat", "claim", "finish"]
    assert remote[0][2] == [
        "ssh",
        "-T",
        "-oBatchMode=yes",
        "-oConnectTimeout=8",
        "operator-alias",
        *(["sudo", "-n"] if ssh_sudo else []),
        "docker",
        "exec",
        "-i",
        "mail-app",
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "aimail.cli_worker",
        "heartbeat",
    ]
    assert calls[0][1] == remote[0][2][:-3] + ["-"]
    worker_ids = [entry[3]["worker_id"] for entry in remote]
    assert len(set(worker_ids)) == 1
    assert remote[0][3]["capabilities"] == CAPABILITIES
    assert remote[0][3]["lease_seconds"] == 120
    assert remote[2][3]["output"] == '{"private":"RESULT"}'
    for entry in remote:
        assert "PRIVATE_MAIL" not in " ".join(entry[2])
        assert "RESULT" not in " ".join(entry[2])
        remote_arguments = entry[2][entry[2].index("operator-alias") + 1 :]
        assert shlex.split(" ".join(remote_arguments)) == remote_arguments
    log = capsys.readouterr()
    assert "PRIVATE_MAIL" not in log.out + log.err
    assert "PRIVATE_TASK" not in log.out + log.err
    assert "RESULT" not in log.out + log.err
    assert "abc123" not in log.out + log.err


@pytest.mark.parametrize(
    "answer", ['{"ok":false}', '{"ok":1}', '{"ok":true,"secret":"x"}', "not json"]
)
def test_failed_probe_never_registers_a_capability(monkeypatch, answer):
    configure_cli(monkeypatch, lambda *args, **kwargs: answer)
    contacted = []

    def run(arguments, request, timeout, cancel):
        contacted.append(arguments[-1])
        return b'{"enabled":true}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert worker.main(["--once"]) == 2
    assert contacted == ["-"]


def test_probe_cannot_bridge_or_print_private_cli_error(monkeypatch, capsys):
    def complete(*args, **kwargs):
        assert kwargs["allow_bridge"] is False
        raise worker.cli.CLIError("PRIVATE_MAIL credential-value")

    configure_cli(monkeypatch, complete)
    assert worker.probe_capabilities() == []
    logs = capsys.readouterr()
    assert "PRIVATE_MAIL" not in logs.out + logs.err
    assert "credential-value" not in logs.out + logs.err


@pytest.mark.parametrize("backend", worker.BACKENDS)
def test_probe_only_targets_one_backend_without_registering_or_claiming(
    monkeypatch, capsys, backend
):
    checked = []
    configured = []
    inferred = []
    monkeypatch.setattr(worker.SSHTransport, "check", lambda self: checked.append(True))
    monkeypatch.setattr(
        worker.SSHTransport, "call", lambda *args, **kwargs: pytest.fail("Queue mutation")
    )

    def configuration(selected, *, model):
        configured.append((selected, model))
        return SimpleNamespace(model=model)

    def complete(selected, *args, **kwargs):
        inferred.append((selected, kwargs))
        return '{"ok":true}'

    monkeypatch.setattr(worker.cli, "configuration", configuration)
    monkeypatch.setattr(worker.cli, "complete", complete)
    assert (
        worker.main(
            [
                "--probe-only",
                "--backend",
                backend,
                "--codex-model",
                "codex-model",
                "--claude-model",
                "claude-model",
            ]
        )
        == 0
    )
    model = "codex-model" if backend == "codex_cli" else "claude-model"
    assert checked == [True]
    assert configured == [(backend, model)]
    assert inferred == [(backend, {"model": model, "allow_bridge": False})]
    assert "no capability registered or mail job claimed" in capsys.readouterr().out


def test_selected_worker_registers_only_verified_selected_backend(monkeypatch):
    configure_cli(monkeypatch, lambda *args, **kwargs: '{"ok":true}')
    registered = []
    monkeypatch.setattr(worker.SSHTransport, "check", lambda self: None)
    monkeypatch.setattr(
        worker.Worker, "serve", lambda self, **kwargs: registered.append(self.capabilities)
    )
    assert worker.main(["--backend", "codex_cli", "--once"]) == 0
    assert registered == [CAPABILITIES]


def test_duplicate_backend_does_not_repeat_paid_probe(monkeypatch):
    inferred = []
    configure_cli(monkeypatch, lambda *args, **kwargs: inferred.append(args) or '{"ok":true}')
    assert worker.probe_capabilities(backends=("codex_cli", "codex_cli")) == CAPABILITIES
    assert len(inferred) == 1


@pytest.mark.parametrize("backends", [(), ("private-backend",)])
def test_invalid_backend_selection_fails_before_model_call(monkeypatch, backends):
    monkeypatch.setattr(worker.cli, "complete", lambda *args, **kwargs: pytest.fail("Model call"))
    with pytest.raises(ValueError, match="supported local CLI"):
        worker.probe_capabilities(backends=backends)


@pytest.mark.parametrize(
    ("reason", "exit_code", "expected"),
    [
        ("timeout", None, "reason=timeout"),
        ("nonzero_exit", 1, "reason=nonzero_exit; exit_code=1"),
        ("nonzero_exit", "PRIVATE_MAIL", "reason=nonzero_exit"),
        ("nonzero_exit", True, "reason=nonzero_exit"),
        ("nonzero_exit", 1000000, "reason=nonzero_exit"),
        ("PRIVATE_MAIL credential-value", 1, "reason=unexpected_local_failure"),
    ],
)
def test_probe_failure_logs_only_closed_reason_and_integer_exit_code(
    monkeypatch, capsys, reason, exit_code, expected
):
    def complete(*args, **kwargs):
        error = worker.cli.CLIError("PRIVATE_MAIL credential-value")
        error.reason_code = reason
        error.exit_code = exit_code
        raise error

    configure_cli(monkeypatch, complete)
    assert worker.probe_capabilities(backends=("codex_cli",)) == []
    logs = capsys.readouterr()
    assert expected in logs.out
    assert "PRIVATE_MAIL" not in logs.out + logs.err
    assert "credential-value" not in logs.out + logs.err
    if type(exit_code) is not int or not -255 <= exit_code <= 255:
        assert "exit_code=" not in logs.out


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ('{"ok":1}', "probe_schema_mismatch"),
        ('{"ok":true,"secret":"PRIVATE_MAIL"}', "probe_schema_mismatch"),
        ('"PRIVATE_MAIL"', "probe_schema_mismatch"),
        ("PRIVATE_MAIL", "probe_invalid_json"),
    ],
)
def test_probe_contract_failure_reports_reason_without_output(monkeypatch, capsys, answer, reason):
    configure_cli(monkeypatch, lambda *args, **kwargs: answer)
    assert worker.probe_capabilities(backends=("codex_cli",)) == []
    logs = capsys.readouterr()
    assert f"reason={reason}" in logs.out
    assert "PRIVATE_MAIL" not in logs.out + logs.err


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
    monkeypatch.setattr(worker, "probe_capabilities", lambda **kwargs: pytest.fail("Model probe"))
    calls = []

    def run(arguments, request, timeout, cancel):
        calls.append(arguments[-1])
        return b'{"enabled":false}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert worker.main(["--once"]) == 2
    assert calls == ["-"]
    assert "phase=check; reason=bridge_disabled" in capsys.readouterr().out


@pytest.mark.parametrize("response", [b"PRIVATE_MAIL", b'{"enabled":1}', b"{}"])
def test_invalid_remote_preflight_does_not_call_a_model_or_echo_private_output(
    monkeypatch, capsys, response
):
    monkeypatch.setattr(worker, "probe_capabilities", lambda **kwargs: pytest.fail("Model probe"))
    requests = []

    def run(arguments, request, timeout, cancel):
        requests.append((arguments, request))
        return response

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert worker.main(["--once", "--ssh-sudo"]) == 2
    assert len(requests) == 1
    assert requests[0][1] == worker.REMOTE_CHECK_SCRIPT
    log = capsys.readouterr()
    assert "PRIVATE_MAIL" not in log.out + log.err


def test_ssh_or_docker_permission_failure_prevents_paid_model_probes(monkeypatch, capsys):
    monkeypatch.setattr(worker, "probe_capabilities", lambda **kwargs: pytest.fail("Model probe"))

    def run(arguments, request, timeout, cancel):
        assert arguments[arguments.index("aliyun") + 1 :][:2] == ["sudo", "-n"]
        assert request == worker.REMOTE_CHECK_SCRIPT
        raise worker.RemoteError("SSH request failed", reason_code="ssh_nonzero_exit")

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert worker.main(["--once", "--ssh-sudo"]) == 2
    assert "phase=check; reason=ssh_nonzero_exit" in capsys.readouterr().out


@pytest.mark.parametrize("check_timeout", [None, "60", "0.05"])
def test_readiness_timeout_override_keeps_queue_requests_and_ssh_configuration_unchanged(
    monkeypatch, check_timeout
):
    calls = []
    configure_cli(monkeypatch, lambda *args, **kwargs: '{"ok":true}')

    def run(arguments, request, timeout, cancel):
        calls.append((arguments, timeout))
        if arguments[-1] == "-":
            assert request == worker.REMOTE_CHECK_SCRIPT
            return b'{"enabled":true}'
        if arguments[-1] == "heartbeat":
            return b'{"ok":true}'
        if arguments[-1] == "claim":
            return json.dumps({"job": JOB}).encode()
        return b'{"accepted":true}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    args = ["--once", "--backend", "codex_cli", "--ssh-sudo"]
    if check_timeout is not None:
        args += ["--ssh-check-timeout", check_timeout]
    assert worker.main(args) == 0
    assert [arguments[-1] for arguments, _ in calls] == ["-", "heartbeat", "claim", "finish"]
    assert [timeout for _, timeout in calls] == [
        float(check_timeout) if check_timeout is not None else 20,
        20,
        20,
        20,
    ]
    assert all(
        arguments[:5] == ["ssh", "-T", "-oBatchMode=yes", "-oConnectTimeout=8", "aliyun"]
        for arguments, _ in calls
    )


def test_check_only_uses_one_readonly_request_without_model_configuration_or_registration(
    monkeypatch, capsys
):
    requests = []

    def run(arguments, request, timeout, cancel):
        requests.append((arguments, request, timeout))
        return b'{"enabled":true}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    monkeypatch.setattr(worker, "_codex_config_model", lambda: pytest.fail("Model config read"))
    monkeypatch.setattr(worker, "probe_capabilities", lambda **kwargs: pytest.fail("Model probe"))
    monkeypatch.setattr(
        worker.cli, "configuration", lambda *args, **kwargs: pytest.fail("CLI config")
    )
    monkeypatch.setattr(worker.cli, "complete", lambda *args, **kwargs: pytest.fail("Inference"))
    monkeypatch.setattr(worker, "Worker", lambda *args, **kwargs: pytest.fail("Registration"))
    assert worker.main(["--check-only", "--ssh-check-timeout", "60", "--codex-from-config"]) == 0
    assert len(requests) == 1
    assert requests[0][0][-1] == "-"
    assert requests[0][1] == worker.REMOTE_CHECK_SCRIPT
    assert requests[0][2] == 60
    logs = capsys.readouterr()
    assert "no model called or capability registered" in logs.out
    assert "Checking local CLI connections" not in logs.out


def test_check_only_timeout_reports_readiness_stage_without_model_probes(monkeypatch, capsys):
    def run(*args):
        raise worker.RemoteError("SSH request interrupted or timed out", reason_code="ssh_timeout")

    monkeypatch.setattr(worker, "_run_ssh", run)
    monkeypatch.setattr(worker, "probe_capabilities", lambda **kwargs: pytest.fail("Model probe"))
    monkeypatch.setattr(worker, "Worker", lambda *args, **kwargs: pytest.fail("Registration"))
    assert worker.main(["--check-only", "--ssh-check-timeout", "60"]) == 2
    logs = capsys.readouterr()
    assert "Checking remote CLI bridge (up to 60s); no model call yet" in logs.out
    assert "phase=check; reason=ssh_timeout" in logs.out
    assert "Read-only connection check complete" not in logs.out


@pytest.mark.parametrize("timeout", ["0", "-1", "0.049", "60.001", "nan", "inf", "-inf"])
def test_bad_readiness_timeout_is_rejected_before_ssh_or_models(monkeypatch, timeout):
    monkeypatch.setattr(worker, "_run_ssh", lambda *args: pytest.fail("SSH request"))
    monkeypatch.setattr(worker, "probe_capabilities", lambda **kwargs: pytest.fail("Model probe"))
    assert worker.main(["--check-only", "--ssh-check-timeout=" + timeout]) == 2


@pytest.mark.parametrize(
    "modes",
    [
        ["--check-only", "--probe-only"],
        ["--check-only", "--once"],
        ["--probe-only", "--once"],
    ],
)
def test_conflicting_worker_modes_fail_before_any_request(monkeypatch, modes):
    monkeypatch.setattr(worker, "_run_ssh", lambda *args: pytest.fail("SSH request"))
    with pytest.raises(SystemExit) as failure:
        worker.main(modes)
    assert failure.value.code == 2


@pytest.mark.parametrize("enabled", ["0", "1"])
def test_preflight_script_only_checks_opt_in_without_creating_any_database(tmp_path, enabled):
    environment = {
        **os.environ,
        "PYTHONPATH": str(worker.Path(worker.__file__).resolve().parents[1] / "server" / "src"),
        "LLM_CLI_BRIDGE_ENABLED": enabled,
        "DB_PATH": str(tmp_path / "mail.sqlite3"),
        "LLM_CLI_BRIDGE_DB": str(tmp_path / "bridge.sqlite3"),
    }
    result = subprocess.run(
        [sys.executable, "-"],
        input=worker.REMOTE_CHECK_SCRIPT,
        env=environment,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {"enabled": enabled == "1"}
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("code", "message", "retryable"),
    [
        ("model_mismatch", "Local CLI model does not match the server configuration", False),
        ("worker_conflict", "Another CLI worker is active; waiting for its lease", True),
        ("invalid_request", "CLI worker protocol or configuration is invalid", False),
        ("queue_unavailable", "Remote CLI queue is unavailable", True),
        ("invalid_configuration", "Remote CLI bridge configuration is invalid", True),
    ],
)
def test_known_remote_errors_have_clear_fixed_messages(monkeypatch, code, message, retryable):
    response = json.dumps({"error": code, "detail": "PRIVATE_MAIL"}).encode()
    monkeypatch.setattr(worker, "_run_ssh", lambda *args: response)
    with pytest.raises(worker.RemoteError) as failure:
        worker.SSHTransport().call("heartbeat", {})
    assert str(failure.value) == message
    assert failure.value.retryable is retryable
    assert failure.value.reason_code == code
    assert "PRIVATE_MAIL" not in str(failure.value)


def test_default_command_targets_verified_production_container(monkeypatch):
    configure_cli(monkeypatch, lambda *args, **kwargs: '{"ok":true}')
    commands = []

    def run(arguments, request, timeout, cancel):
        commands.append(arguments)
        if arguments[-1] == "-":
            return b'{"enabled":true}'
        if arguments[-1] == "heartbeat":
            return b'{"ok":true}'
        return b'{"job":null}'

    monkeypatch.setattr(worker, "_run_ssh", run)
    assert worker.main(["--once"]) == 0
    assert worker.SSHTransport().container == "mainland-aimail-1"
    assert len(commands) == 3
    assert all(command[command.index("-i") + 1] == "mainland-aimail-1" for command in commands)
    assert all("sudo" not in command for command in commands)


def test_sudo_option_is_boolean_and_cannot_become_an_arbitrary_command():
    with pytest.raises(ValueError, match="explicit boolean"):
        worker.SSHTransport(ssh_sudo="sudo -S")


@pytest.mark.parametrize("name", ["-bad", "host;touch", "a b", "a\n", "$(bad)", "a@b", "a/b"])
def test_shell_fragments_cannot_be_used_as_ssh_alias_or_container(name):
    with pytest.raises(ValueError):
        worker.SSHTransport(host=name)
    with pytest.raises(ValueError):
        worker.SSHTransport(container=name)


@pytest.mark.parametrize(
    "reason", ["ssh_timeout", "queue_unavailable", "unknown", "PRIVATE_MAIL", None, [], {}, True]
)
def test_remote_reason_metadata_is_closed_even_if_exception_attributes_change(reason):
    failure = worker.RemoteError("PRIVATE_MAIL", reason_code=reason)
    expected = (
        reason if isinstance(reason, str) and reason in worker.REMOTE_REASON_CODES else "unknown"
    )
    assert failure.reason_code == expected
    failure.reason_code = {"PRIVATE_MAIL": "credential"}
    assert worker._remote_failure_details("claim", failure) == "phase=claim; reason=unknown"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (b"PRIVATE_MAIL", "invalid_json"),
        (b'["PRIVATE_MAIL"]', "invalid_response"),
        (b'{"error":"PRIVATE_MAIL","detail":"credential"}', "remote_operation_failed"),
        (b'{"error":["PRIVATE_MAIL"]}', "remote_operation_failed"),
        (b'{"error":"queue_unavailable","detail":"PRIVATE_MAIL"}', "queue_unavailable"),
        (b'{"error":"invalid_configuration"}', "invalid_configuration"),
    ],
)
def test_transport_response_failures_have_closed_metadata(monkeypatch, response, reason):
    monkeypatch.setattr(worker, "_run_ssh", lambda *args: response)
    with pytest.raises(worker.RemoteError) as failure:
        worker.SSHTransport().call("claim", {})
    assert failure.value.reason_code == reason
    assert "PRIVATE_MAIL" not in worker._remote_failure_details("claim", failure.value)
    assert "credential" not in worker._remote_failure_details("claim", failure.value)


class UnprintableRemoteError(worker.RemoteError):
    def __str__(self):
        raise AssertionError("Exception message must never be formatted into logs")


def test_readiness_failure_logs_only_phase_and_reason_before_any_model(monkeypatch, capsys):
    def failed(*args):
        raise UnprintableRemoteError("PRIVATE_MAIL", reason_code="ssh_timeout")

    monkeypatch.setattr(worker, "_run_ssh", failed)
    monkeypatch.setattr(worker, "probe_capabilities", lambda **kwargs: pytest.fail("Paid probe"))
    assert worker.main(["--check-only"]) == 2
    output = capsys.readouterr()
    assert "phase=check; reason=ssh_timeout" in output.out
    assert "PRIVATE_MAIL" not in output.out + output.err


@pytest.mark.parametrize("phase", ["heartbeat", "claim", "finish"])
def test_worker_error_logs_preserve_retries_without_exposing_exception_or_repeating_model(
    monkeypatch, capsys, phase
):
    calls = []
    inferred = []

    def call(action, payload, *, cancel=None):
        calls.append((action, copy.deepcopy(payload)))
        count = sum(name == action for name, _ in calls)
        if action == phase and count == 1:
            raise UnprintableRemoteError("PRIVATE_MAIL credential", reason_code="queue_unavailable")
        if action == "heartbeat":
            return {"ok": True}
        if action == "claim":
            if phase == "finish":
                return {"job": copy.deepcopy(JOB)}
            instance._stop.set()
            return {"job": None}
        instance._stop.set()
        return {"accepted": True}

    instance = worker.Worker(
        SimpleNamespace(call=call), CAPABILITIES, heartbeat_seconds=100, retry_seconds=0
    )
    monkeypatch.setattr(
        worker.cli, "complete", lambda *args, **kwargs: inferred.append(args) or '{"result":42}'
    )
    monkeypatch.setattr(worker, "probe_capabilities", lambda **kwargs: pytest.fail("Paid probe"))
    instance.serve()
    assert sum(action == phase for action, _ in calls) == 2
    assert len(inferred) == (1 if phase == "finish" else 0)
    finishes = [payload for action, payload in calls if action == "finish"]
    if finishes:
        assert finishes[0] == finishes[1]
    output = capsys.readouterr()
    assert f"phase={phase}; reason=queue_unavailable" in output.out
    assert "PRIVATE_MAIL" not in output.out + output.err
    assert "credential" not in output.out + output.err
    assert "abc123" not in output.out + output.err


def test_background_heartbeat_logs_do_not_format_exception_messages(capsys):
    calls = []

    def call(action, payload, *, cancel=None):
        calls.append(action)
        if len(calls) == 1:
            raise UnprintableRemoteError("PRIVATE_MAIL", reason_code="ssh_timeout")
        instance._stop.set()
        return {"ok": True}

    instance = worker.Worker(SimpleNamespace(call=call), CAPABILITIES, heartbeat_seconds=0.001)
    instance._pulse()
    assert calls == ["heartbeat", "heartbeat"]
    output = capsys.readouterr()
    assert "phase=heartbeat; reason=ssh_timeout" in output.out
    assert "PRIVATE_MAIL" not in output.out + output.err


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


def test_actual_nonzero_process_is_distinct_from_timeout_and_hides_private_output(monkeypatch):
    _local_process(
        monkeypatch,
        "import sys; sys.stdin.read(); sys.stdout.write('PRIVATE_MAIL'); "
        "sys.stderr.write('credential'); sys.exit(23)",
    )
    with pytest.raises(worker.RemoteError) as failure:
        worker.SSHTransport().call("claim", {})
    assert failure.value.reason_code == "ssh_nonzero_exit"
    assert str(failure.value) == "SSH request failed"


def test_ssh_launch_failure_does_not_expose_os_error(monkeypatch):
    def launch(*args, **kwargs):
        raise OSError("PRIVATE_MAIL credential")

    monkeypatch.setattr(worker.subprocess, "Popen", launch)
    with pytest.raises(worker.RemoteError) as failure:
        worker.SSHTransport().call("claim", {})
    assert failure.value.reason_code == "ssh_unavailable"
    assert str(failure.value) == "SSH unavailable"


def test_ssh_stdout_limit_kills_oversized_response_before_it_is_parsed(monkeypatch):
    monkeypatch.setattr(worker, "MAX_RESPONSE_BYTES", 1024)
    _local_process(
        monkeypatch,
        "import sys,time; sys.stdout.write('x'*4096); sys.stdout.flush(); time.sleep(5)",
    )
    with pytest.raises(worker.RemoteError, match="exceeded limit") as failure:
        worker.SSHTransport(timeout=1).call("claim", {"worker_id": "test"})
    assert failure.value.reason_code == "response_limit"


def test_ssh_timeout_and_cancellation_stop_without_private_output(monkeypatch):
    _local_process(monkeypatch, "import time; time.sleep(5)")
    with pytest.raises(worker.RemoteError, match="timed out") as failure:
        worker.SSHTransport(timeout=0.05).call("claim", {"worker_id": "test"})
    assert failure.value.reason_code == "ssh_timeout"
    cancel = threading.Event()
    timer = threading.Timer(0.02, cancel.set)
    timer.start()
    try:
        with pytest.raises(worker.RemoteError, match="interrupted") as failure:
            worker.SSHTransport(timeout=1).call("heartbeat", {}, cancel=cancel)
        assert failure.value.reason_code == "ssh_cancelled"
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
    assert b"--ssh-sudo" in result.stdout


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


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ('model = "gpt-6.1-sol"\n', "gpt-6.1-sol"),
        ('model = "o3"\n', "o3"),
        (
            'model = "gpt-5.4"\nprofile = "daily"\n[profiles.daily]\nmodel = "gpt-6.1-sol"\n',
            "gpt-6.1-sol",
        ),
        ('model = "gpt-6.1-sol"\nprofile = "daily"\n[profiles.daily]\n', "gpt-6.1-sol"),
    ],
)
def test_codex_config_choice_is_bound_to_one_probe_and_registration_without_loading_settings(
    monkeypatch, tmp_path, capsys, config, expected
):
    directory = tmp_path / "codex"
    directory.mkdir()
    (directory / "config.toml").write_text(
        config + '\n[mcp_servers.private]\ncommand = "PRIVATE_COMMAND"\n'
    )
    monkeypatch.setenv("CODEX_HOME", str(directory))
    monkeypatch.setenv("CODEX_CLI_MODEL", "gpt-environment-choice")
    monkeypatch.setattr(worker.SSHTransport, "check", lambda self: None)
    configs, inferred, registered = [], [], []

    def configuration(backend, *, model):
        configs.append((backend, model))
        return SimpleNamespace(model=model)

    def complete(*args, **kwargs):
        inferred.append((args, kwargs))
        return '{"ok":true}'

    monkeypatch.setattr(worker.cli, "configuration", configuration)
    monkeypatch.setattr(worker.cli, "complete", complete)
    monkeypatch.setattr(
        worker.Worker, "serve", lambda self, **kwargs: registered.append(self.capabilities)
    )
    assert worker.main(["--codex-from-config", "--backend", "codex_cli"]) == 0
    assert configs == [("codex_cli", expected)]
    assert len(inferred) == 1
    assert inferred[0][1] == {"model": expected, "allow_bridge": False}
    assert inferred[0][0][3]["properties"]["ok"] == {"type": "boolean"}
    assert registered == [[{"backend": "codex_cli", "model": expected, "verified": True}]]
    assert worker.os.environ["CODEX_CLI_MODEL"] == "gpt-environment-choice"
    assert (directory / "config.toml").read_text().startswith(config)
    logs = capsys.readouterr()
    assert "PRIVATE_COMMAND" not in logs.out + logs.err


def test_codex_config_defaults_to_operator_home(monkeypatch, tmp_path):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".codex"
    directory.mkdir()
    (directory / "config.toml").write_text('model = "gpt-6.1-sol"\n')
    assert worker._codex_config_model() == "gpt-6.1-sol"


@pytest.mark.parametrize(
    "config",
    [
        None,
        "",
        'model = "PRIVATE_MODEL token-value"\n',
        'model = "$(touch PRIVATE_FILE)"\n',
        "model = false\n",
        'model = "gpt-6.1-sol"\nprofile = false\n',
        'model = "gpt-6.1-sol"\nprofile = "missing"\n',
        'model = "gpt-6.1-sol"\nprofile = "daily"\nprofiles = "PRIVATE_CONFIG"\n',
        'model = "gpt-6.1-sol"\n[PRIVATE_INVALID',
        "# PRIVATE_CONFIG\n" + "x" * 131072,
    ],
)
def test_missing_or_invalid_codex_config_stops_before_inference_and_registration(
    monkeypatch, tmp_path, capsys, config
):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    if config is not None:
        (tmp_path / "config.toml").write_text(config)
    monkeypatch.setattr(worker.SSHTransport, "check", lambda self: None)
    monkeypatch.setattr(
        worker.cli, "configuration", lambda *args, **kwargs: pytest.fail("CLI configuration")
    )
    monkeypatch.setattr(worker.cli, "complete", lambda *args, **kwargs: pytest.fail("Model call"))
    monkeypatch.setattr(worker.Worker, "serve", lambda *args, **kwargs: pytest.fail("Registration"))
    assert worker.main(["--codex-from-config", "--backend", "codex_cli"]) == 2
    logs = capsys.readouterr()
    assert "reason=config_" in logs.out
    assert "PRIVATE_" not in logs.out + logs.err
    assert "token-value" not in logs.out + logs.err
    assert "workstation registered" not in logs.out


def test_config_source_does_not_read_config_or_probe_codex_when_only_claude_is_selected(
    monkeypatch,
):
    monkeypatch.setattr(worker, "_codex_config_model", lambda: pytest.fail("Codex config read"))
    monkeypatch.setattr(
        worker.cli, "configuration", lambda backend, model: SimpleNamespace(model=model)
    )
    inferred = []
    monkeypatch.setattr(
        worker.cli, "complete", lambda *args, **kwargs: inferred.append(args[0]) or '{"ok":true}'
    )
    assert worker.probe_capabilities(
        codex_from_config=True, claude_model="sonnet", backends=("claude_code_cli",)
    ) == [{"backend": "claude_code_cli", "model": "sonnet", "verified": True}]
    assert inferred == ["claude_code_cli"]


def test_conflicting_codex_model_sources_fail_before_transport_or_models(monkeypatch):
    monkeypatch.setattr(worker.SSHTransport, "check", lambda self: pytest.fail("SSH call"))
    with pytest.raises(SystemExit) as failure:
        worker.main(["--codex-model", "gpt-6.1-sol", "--codex-from-config"])
    assert failure.value.code == 2
    with pytest.raises(ValueError, match="explicit Codex model"):
        worker.probe_capabilities(codex_model="gpt-6.1-sol", codex_from_config=True)


@pytest.mark.parametrize(
    "kind",
    ["model_unavailable", "auth_401", "PRIVATE_ERROR", {"PRIVATE_ERROR": "token-value"}, None],
)
def test_probe_failure_kind_is_closed_and_cannot_print_arbitrary_values(monkeypatch, capsys, kind):
    def complete(*args, **kwargs):
        error = worker.cli.CLIError(
            "PRIVATE_MESSAGE token-value", reason_code="nonzero_exit", exit_code=1
        )
        error.failure_kind = kind
        raise error

    configure_cli(monkeypatch, complete)
    assert worker.probe_capabilities(backends=("codex_cli",)) == []
    logs = capsys.readouterr()
    expected = kind if isinstance(kind, str) and kind in worker.PROBE_FAILURE_KINDS else "unknown"
    assert f"failure_kind={expected}" in logs.out
    assert "PRIVATE_" not in logs.out + logs.err
    assert "token-value" not in logs.out + logs.err


def test_registration_confirmation_requires_an_accepted_remote_heartbeat(monkeypatch, capsys):
    monkeypatch.setattr(worker.cli, "complete", lambda *args, **kwargs: pytest.fail("Model call"))
    transport = FakeTransport()
    transport.call = lambda *args, **kwargs: {"ok": False}
    with pytest.raises(worker.RemoteError, match="not accepted"):
        worker.Worker(transport, CAPABILITIES).serve(once=True)
    assert "workstation registered" not in capsys.readouterr().out


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
