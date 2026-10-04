#!/usr/bin/env python3
"""Run locally logged-in inference CLIs for a remote Aimail installation over SSH.

The remote side owns the queue; this client claims one job at a time. Mail text travels
only over SSH stdin/stdout, never in command arguments or logs. It does not install,
log in to, configure or expose either CLI as a network service.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_local_cli() -> ModuleType:
    """Load only the stdlib adapter, without importing the server dependency graph."""
    root = Path(__file__).resolve().parents[1] / "server" / "src"
    namespace = "_aimail_pull_backends"
    package = ModuleType(namespace)
    package.__path__ = [str(root / "aimail" / "backends")]
    sys.modules[namespace] = package
    spec = importlib.util.spec_from_file_location(
        f"{namespace}.cli", root / "aimail" / "backends" / "cli.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = _load_local_cli()

BACKENDS = ("codex_cli", "claude_code_cli")
PROBE_FAILURE_CODES = frozenset(
    {
        "config_invalid",
        "config_missing",
        "start_failed",
        "nonzero_exit",
        "timeout",
        "output_limit",
        "invalid_encoding",
        "invalid_envelope",
        "request_failed",
        "tool_operation",
        "incomplete_result",
        "local_busy",
        "probe_invalid_json",
        "probe_schema_mismatch",
    }
)
PROBE_FAILURE_KINDS = frozenset(
    {
        "schema_rejected",
        "model_unavailable",
        "auth_401",
        "access_403",
        "rate_429",
        "server_error",
        "network_error",
        "tls_error",
        "unknown",
    }
)
MODEL_VARIABLES = {"codex_cli": "CODEX_CLI_MODEL", "claude_code_cli": "CLAUDE_CODE_CLI_MODEL"}
DEFAULT_CONTAINER = "mainland-aimail-1"
LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 30
RETRY_SECONDS = 2
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024
PROBE_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_CODEX_MODEL_ID = re.compile(
    r"(?:gpt-[A-Za-z0-9][A-Za-z0-9._-]{0,95}|o[1-9][A-Za-z0-9._-]{0,95})\Z"
)
REMOTE_CHECK_SCRIPT = (
    b"import json\n"
    b"from aimail.backends import cli_bridge\n"
    b'print(json.dumps({"enabled": cli_bridge.enabled()}))\n'
)
REMOTE_REASON_CODES = frozenset(
    {
        "unknown",
        "request_unavailable",
        "ssh_unavailable",
        "ssh_timeout",
        "ssh_cancelled",
        "ssh_nonzero_exit",
        "ssh_io_error",
        "response_limit",
        "invalid_json",
        "invalid_response",
        "bridge_disabled",
        "model_mismatch",
        "worker_conflict",
        "invalid_request",
        "queue_unavailable",
        "invalid_configuration",
        "remote_operation_failed",
    }
)


class RemoteError(RuntimeError):
    """A fixed safe transport failure, without remote output or source content."""

    def __init__(
        self, message: str, *, retryable: bool = True, reason_code: str = "unknown"
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.reason_code = (
            reason_code
            if isinstance(reason_code, str) and reason_code in REMOTE_REASON_CODES
            else "unknown"
        )


def _remote_failure_details(phase: str, error: RemoteError) -> str:
    """Format closed metadata only, even if an exception's attributes were changed."""
    safe_phase = (
        phase
        if isinstance(phase, str) and phase in {"check", "heartbeat", "claim", "finish", "worker"}
        else "unknown"
    )
    reason = getattr(error, "reason_code", None)
    safe_reason = reason if isinstance(reason, str) and reason in REMOTE_REASON_CODES else "unknown"
    return f"phase={safe_phase}; reason={safe_reason}"


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _run_ssh(
    arguments: list[str],
    request: bytes,
    timeout: float,
    cancel: threading.Event | None = None,
) -> bytes:
    """Bound stdout while it is read, discard stderr and stop the process group."""
    if len(request) > MAX_REQUEST_BYTES or (cancel is not None and cancel.is_set()):
        raise RemoteError(
            "Remote request unavailable",
            reason_code="ssh_cancelled"
            if cancel is not None and cancel.is_set()
            else "request_unavailable",
        )
    try:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            shell=False,
        )
    except OSError as exc:
        raise RemoteError("SSH unavailable", reason_code="ssh_unavailable") from exc
    assert process.stdin is not None and process.stdout is not None
    output = bytearray()
    offset = 0
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdin, process.stdout):
                os.set_blocking(stream.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0 or (cancel is not None and cancel.is_set()):
                    raise RemoteError(
                        "SSH request interrupted or timed out",
                        reason_code="ssh_cancelled"
                        if cancel is not None and cancel.is_set()
                        else "ssh_timeout",
                    )
                for key, _ in selector.select(min(remaining, 0.1)):
                    if key.data == "stdin":
                        try:
                            offset += os.write(key.fd, request[offset : offset + 65536])
                        except BrokenPipeError:
                            offset = len(request)
                        if offset >= len(request):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        output.extend(chunk)
                        if len(output) > MAX_RESPONSE_BYTES:
                            raise RemoteError(
                                "SSH response exceeded limit", reason_code="response_limit"
                            )
            remaining = deadline - time.monotonic()
            if remaining <= 0 or (cancel is not None and cancel.is_set()):
                raise RemoteError(
                    "SSH request interrupted or timed out",
                    reason_code="ssh_cancelled"
                    if cancel is not None and cancel.is_set()
                    else "ssh_timeout",
                )
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or (cancel is not None and cancel.is_set()):
                    raise RemoteError(
                        "SSH request interrupted or timed out",
                        reason_code="ssh_cancelled"
                        if cancel is not None and cancel.is_set()
                        else "ssh_timeout",
                    )
                try:
                    code = process.wait(timeout=min(remaining, 0.1))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if code:
                raise RemoteError("SSH request failed", reason_code="ssh_nonzero_exit")
    except OSError as exc:
        raise RemoteError("SSH request failed", reason_code="ssh_io_error") from exc
    finally:
        _stop_process(process)
        for stream in (process.stdin, process.stdout):
            if not stream.closed:
                stream.close()
    return bytes(output)


@dataclass(frozen=True)
class SSHTransport:
    host: str = "aliyun"
    container: str = DEFAULT_CONTAINER
    timeout: float = 20
    ssh_sudo: bool = False

    def __post_init__(self) -> None:
        if not _SAFE_NAME.fullmatch(self.host) or not _SAFE_NAME.fullmatch(self.container):
            raise ValueError("SSH alias and container must contain only letters, digits, ._- ")
        if not 0.05 <= self.timeout <= 60:
            raise ValueError("SSH timeout must be between 0.05 and 60 seconds")
        if type(self.ssh_sudo) is not bool:
            raise ValueError("SSH sudo must be an explicit boolean")

    def _arguments(self, *python_arguments: str) -> list[str]:
        return [
            "ssh",
            "-T",
            "-oBatchMode=yes",
            "-oConnectTimeout=8",
            self.host,
            *(["sudo", "-n"] if self.ssh_sudo else []),
            "docker",
            "exec",
            "-i",
            self.container,
            "uv",
            "run",
            "--no-sync",
            "python",
            *python_arguments,
        ]

    def check(self) -> None:
        """Check remote import/access and opt-in before spending a model probe."""
        response = self._request(self._arguments("-"), REMOTE_CHECK_SCRIPT)
        if response.get("enabled") is False:
            raise RemoteError(
                "Remote CLI bridge is disabled", retryable=False, reason_code="bridge_disabled"
            )
        if response.get("enabled") is not True:
            raise RemoteError(
                "Remote CLI bridge readiness unavailable",
                retryable=False,
                reason_code="invalid_response",
            )

    def call(
        self,
        action: str,
        payload: dict[str, Any],
        *,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        if action not in {"heartbeat", "claim", "finish"}:
            raise ValueError("Unknown worker operation")
        request = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return self._request(
            self._arguments("-m", "aimail.cli_worker", action), request, cancel=cancel
        )

    def _request(
        self,
        arguments: list[str],
        request: bytes,
        *,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        output = _run_ssh(arguments, request, self.timeout, cancel)
        try:
            response = json.loads(output)
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise RemoteError("SSH response was not JSON", reason_code="invalid_json") from exc
        if not isinstance(response, dict):
            raise RemoteError("SSH response was not an object", reason_code="invalid_response")
        if "error" in response:
            # Even a compromised/misconfigured remote must not make us log its
            # arbitrary error strings, which could contain mail text or secrets.
            safe_errors = {
                "bridge_disabled": ("Remote CLI bridge is disabled", False),
                "model_mismatch": (
                    "Local CLI model does not match the server configuration",
                    False,
                ),
                "worker_conflict": ("Another CLI worker is active; waiting for its lease", True),
                "invalid_request": ("CLI worker protocol or configuration is invalid", False),
                "queue_unavailable": ("Remote CLI queue is unavailable", True),
                "invalid_configuration": ("Remote CLI bridge configuration is invalid", True),
            }
            code = response["error"]
            if isinstance(code, str) and code in safe_errors:
                message, retryable = safe_errors[code]
                raise RemoteError(message, retryable=retryable, reason_code=code)
            raise RemoteError(
                "Remote worker operation unavailable", reason_code="remote_operation_failed"
            )
        return response


def _codex_config_model() -> str:
    """Read only the operator's model choice; never pass user settings to inference."""
    try:
        import tomllib

        directory = Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser()
        with (directory / "config.toml").open("rb") as source:
            payload = source.read(131073)
        if len(payload) > 131072:
            raise ValueError("config size limit")
        settings = tomllib.loads(payload.decode("utf-8"))
        model = settings.get("model")
        if "profile" in settings:
            profile_name = settings["profile"]
            profiles = settings.get("profiles", {})
            if not isinstance(profile_name, str) or not isinstance(profiles, dict):
                raise ValueError("invalid profile")
            profile = profiles.get(profile_name)
            if not isinstance(profile, dict):
                raise ValueError("missing profile")
            model = profile.get("model", model)
    except FileNotFoundError:
        raise cli.CLIError(
            "Codex model configuration is missing", reason_code="config_missing"
        ) from None
    except Exception:
        raise cli.CLIError(
            "Codex model configuration is unavailable", reason_code="config_invalid"
        ) from None
    if model is None:
        raise cli.CLIError("Codex model configuration is missing", reason_code="config_missing")
    if not isinstance(model, str) or not _CODEX_MODEL_ID.fullmatch(model):
        raise cli.CLIError("Codex model ID is invalid", reason_code="config_invalid")
    return model


def _report_probe_failure(
    backend: str, reason: Any, exit_code: Any = None, failure_kind: Any = "unknown"
) -> None:
    # Never stringify exception messages, arbitrary attributes or process output.
    code = (
        reason
        if isinstance(reason, str) and reason in PROBE_FAILURE_CODES
        else "unexpected_local_failure"
    )
    suffix = (
        f"; exit_code={exit_code}"
        if code == "nonzero_exit" and type(exit_code) is int and -255 <= exit_code <= 255
        else ""
    )
    kind = (
        failure_kind
        if isinstance(failure_kind, str) and failure_kind in PROBE_FAILURE_KINDS
        else "unknown"
    )
    print(
        f"{backend}: connection probe failed; reason={code}{suffix}; "
        f"failure_kind={kind}; capability not registered",
        flush=True,
    )


def probe_capabilities(
    *,
    codex_model: str | None = None,
    codex_from_config: bool = False,
    claude_model: str | None = None,
    backends: tuple[str, ...] = BACKENDS,
) -> list[dict[str, Any]]:
    """Advertise only executable/model pairs that returned a real synthetic answer."""
    capabilities = []
    overrides = {"codex_cli": codex_model, "claude_code_cli": claude_model}
    if not backends or any(backend not in BACKENDS for backend in backends):
        raise ValueError("Select a supported local CLI backend")
    if codex_from_config and codex_model is not None:
        raise ValueError("Choose an explicit Codex model or its configured model")
    for backend in dict.fromkeys(backends):
        try:
            # configuration performs the local executable/model readiness checks.
            # Passing the model explicitly also bypasses remote model discovery,
            # even when the operator's shell inherits the server bridge flag.
            model = overrides[backend]
            if backend == "codex_cli" and codex_from_config:
                model = _codex_config_model()
            if model is None:
                model = os.environ.get(MODEL_VARIABLES[backend], "")
            config = cli.configuration(backend, model=model)
            answer = cli.complete(
                backend,
                'Return exactly the JSON object {"ok":true}. No tools or other content.',
                "Synthetic connection check; no email or customer data.",
                PROBE_SCHEMA,
                model=config.model,
                allow_bridge=False,
            )
            try:
                decoded = json.loads(answer)
            except (ValueError, TypeError):
                _report_probe_failure(backend, "probe_invalid_json")
                continue
            # Python compares 1 == True; insist on the schema's exact JSON boolean.
            if (
                not isinstance(decoded, dict)
                or decoded != {"ok": True}
                or type(decoded.get("ok")) is not bool
            ):
                _report_probe_failure(backend, "probe_schema_mismatch")
                continue
            capabilities.append({"backend": backend, "model": config.model, "verified": True})
        except cli.CLIError as exc:
            _report_probe_failure(
                backend,
                getattr(exc, "reason_code", None),
                getattr(exc, "exit_code", None),
                getattr(exc, "failure_kind", None),
            )
        except Exception:
            # CLI error text is not a connection certificate and must not be logged.
            _report_probe_failure(backend, "unexpected_local_failure")
    return capabilities


class Worker:
    def __init__(
        self,
        transport: SSHTransport,
        capabilities: list[dict[str, Any]],
        *,
        worker_id: str | None = None,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
        retry_seconds: float = RETRY_SECONDS,
    ) -> None:
        self.transport = transport
        self.capabilities = capabilities
        self.worker_id = worker_id or uuid.uuid4().hex
        self.heartbeat_seconds = heartbeat_seconds
        self.retry_seconds = retry_seconds
        self._stop = threading.Event()

    def heartbeat(self, *, cancel: threading.Event | None = None) -> None:
        result = self.transport.call(
            "heartbeat",
            {
                "worker_id": self.worker_id,
                "capabilities": self.capabilities,
                "lease_seconds": LEASE_SECONDS,
            },
            cancel=cancel,
        )
        if result.get("ok") is not True:
            raise RemoteError("Remote heartbeat was not accepted", reason_code="invalid_response")

    def _pulse(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                self.heartbeat(cancel=self._stop)
            except RemoteError as exc:
                if not self._stop.is_set():
                    print(
                        "Remote heartbeat unavailable; "
                        f"{_remote_failure_details('heartbeat', exc)}; reconnecting",
                        flush=True,
                    )

    def _job_payload(self, job: Any) -> dict[str, Any]:
        if not isinstance(job, dict):
            raise RemoteError("Invalid remote job", reason_code="invalid_response")
        job_id = job.get("id")
        if type(job_id) is not int or job_id <= 0:
            raise RemoteError("Invalid remote job", reason_code="invalid_response")
        for field in ("nonce", "lease_token"):
            value = job.get(field)
            if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{1,256}", value):
                raise RemoteError("Invalid remote job", reason_code="invalid_response")
        return {
            "worker_id": self.worker_id,
            "id": job_id,
            "nonce": job["nonce"],
            "lease_token": job["lease_token"],
        }

    def _execute(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = self._job_payload(job)
        matches = any(
            capability["backend"] == job.get("backend")
            and capability["model"] == job.get("model")
            and capability.get("verified") is True
            for capability in self.capabilities
        )
        if (
            not matches
            or not isinstance(job.get("system"), str)
            or not isinstance(job.get("user"), str)
            or not isinstance(job.get("schema"), dict)
        ):
            return {**payload, "error": "Local CLI job configuration is unavailable"}
        print(f"Running job {job['id']} with {job['backend']}", flush=True)
        try:
            output = cli.complete(
                job["backend"],
                job["system"],
                job["user"],
                job["schema"],
                model=job["model"],
                allow_bridge=False,
            )
            if (
                not isinstance(output, str)
                or not output.strip()
                or len(output.encode("utf-8")) > MAX_RESULT_BYTES
            ):
                raise cli.CLIError("Local CLI returned no result")
            return {**payload, "output": output}
        except Exception:
            return {**payload, "error": "Local CLI inference failed; check login and model access"}

    def _finish(self, payload: dict[str, Any]) -> None:
        # The retained payload is immutable while reconnecting. Never rerun inference
        # after a lost completion acknowledgement; the remote CAS is idempotent.
        while not self._stop.is_set():
            try:
                result = self.transport.call("finish", payload)
                if type(result.get("accepted")) is not bool:
                    raise RemoteError(
                        "Remote completion acknowledgement unavailable",
                        reason_code="invalid_response",
                    )
                outcome = "accepted" if result["accepted"] else "expired or rejected"
                print(f"Job {payload['id']}: {outcome}", flush=True)
                return
            except RemoteError as exc:
                print(
                    "Completion acknowledgement unavailable; retaining result for retry; "
                    f"{_remote_failure_details('finish', exc)}",
                    flush=True,
                )
                if self._stop.wait(self.retry_seconds):
                    return

    def serve(self, *, once: bool = False) -> None:
        # The first heartbeat follows capability probing and must succeed before a
        # job is claimed. Keep subsequent heartbeats separate from blocking inference.
        while True:
            try:
                self.heartbeat()
                print("CLI workstation registered; waiting for mail tasks", flush=True)
                break
            except RemoteError as exc:
                if once or not exc.retryable:
                    raise
                print(
                    f"Remote heartbeat unavailable; {_remote_failure_details('heartbeat', exc)}; "
                    "reconnecting",
                    flush=True,
                )
                if self._stop.wait(self.retry_seconds):
                    return
        pulse = threading.Thread(target=self._pulse, name="aimail-worker-heartbeat", daemon=True)
        pulse.start()
        try:
            while not self._stop.is_set():
                try:
                    response = self.transport.call("claim", {"worker_id": self.worker_id})
                    if "job" not in response:
                        raise RemoteError(
                            "Remote claim response unavailable", reason_code="invalid_response"
                        )
                    job = response["job"]
                    if job is not None:
                        self._finish(self._execute(job))
                    if once:
                        return
                except RemoteError as exc:
                    print(
                        f"Remote queue unavailable; {_remote_failure_details('claim', exc)}; "
                        "reconnecting",
                        flush=True,
                    )
                    if once:
                        raise
                if self._stop.wait(self.retry_seconds):
                    return
        finally:
            self._stop.set()
            pulse.join(timeout=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-host", default="aliyun", help="Existing trusted SSH config alias")
    parser.add_argument(
        "--container", default=DEFAULT_CONTAINER, help="Remote Aimail container name"
    )
    parser.add_argument(
        "--ssh-sudo",
        action="store_true",
        help="Use fixed sudo -n for remote Docker; requires existing passwordless permission",
    )
    parser.add_argument(
        "--ssh-check-timeout",
        type=float,
        default=20,
        help="Initial read-only SSH check budget in seconds (0.05–60); queue requests remain 20s",
    )
    codex_source = parser.add_mutually_exclusive_group()
    codex_source.add_argument(
        "--codex-model", help="Exact model available to the locally logged-in CLI"
    )
    codex_source.add_argument(
        "--codex-from-config",
        action="store_true",
        help="Read only the model ID from Codex config.toml and its default profile",
    )
    parser.add_argument("--claude-model", help="Exact model available to the locally logged-in CLI")
    parser.add_argument(
        "--backend",
        choices=BACKENDS,
        action="append",
        help="Check and serve only this CLI; repeat to select both (default: both)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-only",
        action="store_true",
        help="Check remote bridge access then exit without local models, registration or mail jobs",
    )
    mode.add_argument(
        "--probe-only",
        action="store_true",
        help="Run synthetic connection checks then exit without registration or mail jobs",
    )
    mode.add_argument("--once", action="store_true", help="Register and claim at most one job")
    args = parser.parse_args(argv)
    phase = "check"
    try:
        transport = SSHTransport(args.ssh_host, args.container, ssh_sudo=args.ssh_sudo)
        readiness_transport = replace(transport, timeout=args.ssh_check_timeout)
    except ValueError:
        print(
            "Invalid SSH settings; use a trusted alias, a valid container and a check timeout "
            "between 0.05 and 60 seconds",
            flush=True,
        )
        return 2
    try:
        print(
            f"Checking remote CLI bridge (up to {args.ssh_check_timeout:g}s); no model call yet",
            flush=True,
        )
        check_started = time.monotonic()
        readiness_transport.check()
        print(
            f"Remote CLI bridge enabled; readiness took {time.monotonic() - check_started:.2f}s",
            flush=True,
        )
        if args.check_only:
            print(
                "Read-only connection check complete; no model called or capability registered.",
                flush=True,
            )
            return 0
        print("Checking local CLI connections", flush=True)
        capabilities = probe_capabilities(
            codex_model=args.codex_model,
            codex_from_config=args.codex_from_config,
            claude_model=args.claude_model,
            backends=tuple(args.backend) if args.backend else BACKENDS,
        )
        if not capabilities:
            print("No verified local CLI. Check installation, login and exact model configuration.")
            return 2
        for capability in capabilities:
            print(f"Verified: {capability['backend']} / {capability['model']}", flush=True)
        if args.probe_only:
            print(
                "Connection check complete; no capability registered or mail job claimed.",
                flush=True,
            )
            return 0
        worker = Worker(transport, capabilities)
        print(f"Worker {worker.worker_id}: starting SSH pull connection", flush=True)
        phase = "worker"
        worker.serve(once=args.once)
        return 0
    except RemoteError as exc:
        print(f"Remote request unavailable; {_remote_failure_details(phase, exc)}", flush=True)
        return 2
    except KeyboardInterrupt:
        print("Worker stopped", flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
