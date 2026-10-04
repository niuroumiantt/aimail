"""Pinned m5 startup gates and embedded deployment behavior, without SSH or models."""

from __future__ import annotations

import base64
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "start_cli_worker_m5.sh"
COMMIT = "a" * 40
PUBLIC_FILES = (
    "tools/run_cli_worker.py",
    "tools/configure_cli_bridge.py",
    "server/src/aimail/backends/cli.py",
    "server/src/aimail/backends/cli_bridge.py",
)


@pytest.fixture
def launch(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    public = tmp_path / "public"
    for relative in PUBLIC_FILES:
        path = public / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    captures = tmp_path / "calls.jsonl"
    program = (
        f"#!{sys.executable}\n"
        + """import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
record = {"name": name, "args": args}
status = 0
if name == "curl":
    url = next(arg for arg in args if arg.startswith("https://"))
    relative = url.split(os.environ["TEST_COMMIT"] + "/", 1)[1]
    record["relative"] = relative
    if relative == os.environ.get("TEST_DOWNLOAD_FAIL"):
        status = 22
    else:
        content = (pathlib.Path(os.environ["TEST_PUBLIC"]) / relative).read_bytes()
        if relative == os.environ.get("TEST_BAD_HASH"):
            content += b"\\nCORRUPTED_PUBLIC_INPUT\\n"
        pathlib.Path(args[args.index("-o") + 1]).write_bytes(content)
elif name == "ssh":
    previous = pathlib.Path(os.environ["TEST_CALLS"])
    records = [json.loads(line) for line in previous.read_text().splitlines()]
    sequence = 1 + sum(call["name"] == "ssh" for call in records)
    record["sequence"] = sequence
    record["stdin"] = sys.stdin.read()
    status = int(os.environ.get("TEST_SSH_STATUS_" + str(sequence), "0"))
    if status == 0:
        print("SAFE_REMOTE_SUCCESS_" + str(sequence))
elif name.startswith("python"):
    record["kind"] = "version" if args[0] == "-c" else "worker"
    if record["kind"] == "worker":
        print("SAFE_WORKER_STARTED")
with open(os.environ["TEST_CALLS"], "a") as output:
    output.write(json.dumps(record) + "\\n")
sys.exit(status)
"""
    )
    for name in ("curl", "ssh", "python3.14"):
        executable = commands / name
        executable.write_text(program)
        executable.chmod(0o700)
    worker_home = tmp_path / "operator-home"
    worker_home.mkdir()
    environment = {
        **os.environ,
        "HOME": str(worker_home),
        "PATH": f"{commands}:{os.environ['PATH']}",
        "TEST_COMMIT": COMMIT,
        "TEST_PUBLIC": str(public),
        "TEST_CALLS": str(captures),
    }

    def run(args=None, **overrides):
        result = subprocess.run(
            ["bash", str(SCRIPT), *(args if args is not None else [COMMIT])],
            env={**environment, **overrides},
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
        calls = (
            [json.loads(line) for line in captures.read_text().splitlines()]
            if captures.exists()
            else []
        )
        return result, calls, worker_home

    return run


def test_download_hash_constants_match_the_frozen_public_sources():
    digests = re.findall(r"'([a-f0-9]{64})'", SCRIPT.read_text())
    assert digests == [
        hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in PUBLIC_FILES
    ]


@pytest.mark.parametrize(
    "args",
    [
        [],
        [COMMIT, "extra"],
        [COMMIT, "--codex-only", "extra"],
        ["main"],
        ["a" * 39],
        ["A" * 40],
        ["$(id)"],
        [COMMIT, "--probe-only", "$(id)"],
        [COMMIT, "--arbitrary", "codex_cli"],
        [COMMIT, "--probe-only", "codex_cli", "extra"],
    ],
)
def test_invalid_commit_is_rejected_before_any_python_download_or_ssh(launch, args):
    result, calls, _ = launch(args)
    assert result.returncode == 2
    assert calls == []


@pytest.mark.parametrize("relative", PUBLIC_FILES)
def test_every_real_checksum_failure_prevents_remote_actions_and_worker(launch, relative):
    result, calls, _ = launch(TEST_BAD_HASH=relative)
    assert result.returncode != 0
    assert "SAFE_WORKER_STARTED" not in result.stdout
    assert all(call["name"] != "ssh" and call.get("kind") != "worker" for call in calls)


def test_download_failure_prevents_remote_actions_and_worker(launch):
    result, calls, _ = launch(TEST_DOWNLOAD_FAIL=PUBLIC_FILES[1])
    assert result.returncode == 22
    assert all(call["name"] != "ssh" and call.get("kind") != "worker" for call in calls)


@pytest.mark.parametrize("sequence", [1, 2])
@pytest.mark.parametrize("status", [1, 255])
def test_remote_failure_prevents_worker_and_preserves_failure_status(launch, sequence, status):
    result, calls, _ = launch(**{f"TEST_SSH_STATUS_{sequence}": str(status)})
    assert result.returncode == status
    assert len([call for call in calls if call["name"] == "ssh"]) == sequence
    assert all(call.get("kind") != "worker" for call in calls)
    assert "SAFE_WORKER_STARTED" not in result.stdout


def test_success_runs_two_fixed_ssh_operations_before_exact_worker_command(launch):
    result, calls, worker_home = launch()
    assert result.returncode == 0, result.stderr
    downloads = [call for call in calls if call["name"] == "curl"]
    assert [call["relative"] for call in downloads] == list(PUBLIC_FILES)
    assert all(
        f"https://raw.githubusercontent.com/niuroumiantt/aimail/{COMMIT}/{call['relative']}"
        in call["args"]
        for call in downloads
    )
    remote = [call for call in calls if call["name"] == "ssh"]
    assert len(remote) == 2
    prefix = [
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "aliyun",
        "sudo",
        "-n",
        "python3",
        "-",
    ]
    assert remote[0]["args"] == prefix
    assert remote[1]["args"][: len(prefix)] == prefix
    assert (
        base64.b64decode(remote[1]["args"][-1], validate=True)
        == (ROOT / PUBLIC_FILES[1]).read_bytes()
    )
    assert len(remote[1]["args"]) == len(prefix) + 1
    remote_arguments = remote[1]["args"][remote[1]["args"].index("aliyun") + 1 :]
    assert shlex.split(" ".join(remote_arguments)) == remote_arguments
    assert remote[0]["stdin"] == (ROOT / PUBLIC_FILES[1]).read_text()
    assert remote[1]["stdin"] == remote_code()
    assert calls[-1]["kind"] == "worker"
    assert calls[-1]["args"] == [
        str(worker_home / ".local/share/aimail/cli-worker" / COMMIT / PUBLIC_FILES[0]),
        "--ssh-host",
        "aliyun",
        "--ssh-sudo",
        "--container",
        "mainland-aimail-1",
        "--codex-from-config",
        "--claude-model",
        "sonnet",
    ]
    assert "SAFE_WORKER_STARTED" in result.stdout


@pytest.mark.parametrize("backend", ["codex_cli", "claude_code_cli"])
def test_single_probe_mode_downloads_verified_client_without_server_mutations(launch, backend):
    result, calls, worker_home = launch([COMMIT, "--probe-only", backend])
    assert result.returncode == 0, result.stderr
    assert [call["relative"] for call in calls if call["name"] == "curl"] == list(PUBLIC_FILES)
    assert not any(call["name"] == "ssh" for call in calls)
    assert calls[-1]["kind"] == "worker"
    assert calls[-1]["args"] == [
        str(worker_home / ".local/share/aimail/cli-worker" / COMMIT / PUBLIC_FILES[0]),
        "--ssh-host",
        "aliyun",
        "--ssh-sudo",
        "--container",
        "mainland-aimail-1",
        "--codex-from-config",
        "--claude-model",
        "sonnet",
        "--probe-only",
        "--backend",
        backend,
    ]


@pytest.mark.parametrize("relative", PUBLIC_FILES)
def test_single_probe_checksum_failure_prevents_model_and_ssh(launch, relative):
    result, calls, _ = launch([COMMIT, "--probe-only", "codex_cli"], TEST_BAD_HASH=relative)
    assert result.returncode != 0
    assert all(call["name"] != "ssh" and call.get("kind") != "worker" for call in calls)


def test_codex_only_connects_verified_client_without_reconfiguration_or_duplicate_probe(launch):
    result, calls, worker_home = launch([COMMIT, "--codex-only"])
    assert result.returncode == 0, result.stderr
    assert [call["relative"] for call in calls if call["name"] == "curl"] == list(PUBLIC_FILES)
    assert not any(call["name"] == "ssh" for call in calls)
    assert calls[-1]["kind"] == "worker"
    assert calls[-1]["args"] == [
        str(worker_home / ".local/share/aimail/cli-worker" / COMMIT / PUBLIC_FILES[0]),
        "--ssh-host",
        "aliyun",
        "--ssh-sudo",
        "--container",
        "mainland-aimail-1",
        "--codex-from-config",
        "--backend",
        "codex_cli",
    ]


@pytest.mark.parametrize("relative", PUBLIC_FILES)
def test_codex_only_checksum_failure_prevents_all_remote_and_model_calls(launch, relative):
    result, calls, _ = launch([COMMIT, "--codex-only"], TEST_BAD_HASH=relative)
    assert result.returncode != 0
    assert all(call["name"] != "ssh" and call.get("kind") != "worker" for call in calls)


def remote_code():
    matches = re.findall(r"<<'PY'\n(.*?)\nPY\n", SCRIPT.read_text(), re.DOTALL)
    assert len(matches) == 1
    return matches[0] + "\n"


class FakeDeploy:
    def __init__(
        self,
        *,
        flag="0",
        health=(True,),
        busy=False,
        state=None,
        final_flag="1",
        image=None,
        compose_error=False,
        verify_error=None,
    ):
        self.events = []
        self.flag = flag
        self.health = iter(health)
        self.busy = busy
        self.final_flag = final_flag
        self.recreated = 0
        self.compose_error = compose_error
        self.verify_error = verify_error
        self.verify_count = 0
        self.env_file = None
        self.state = (
            state
            if state is not None
            else {
                "source_sha": COMMIT,
                "tag": "aimail-" + COMMIT,
                "image_id": "sha256:" + "d" * 64,
            }
        )
        self.image = (
            image
            if image is not None
            else [
                {
                    "Id": "sha256:" + "d" * 64,
                    "Config": {"Labels": {"org.opencontainers.image.revision": COMMIT}},
                }
            ]
        )

    def acquire_lock(self):
        self.events.append(("acquire",))
        if self.busy:
            raise RuntimeError("busy")

    def release_lock(self):
        self.events.append(("release",))

    def state_data(self):
        self.events.append(("state",))
        return self.state

    def verify_runtime(self):
        self.events.append(("verify",))
        self.verify_count += 1
        if self.verify_count == self.verify_error:
            raise RuntimeError("runtime identity or health failed")

    def container_for_service(self, service):
        self.events.append(("container", service))
        return ["container-before", "container-after", "container-recovered"][
            min(self.recreated, 2)
        ]

    def command(self, args):
        self.events.append(("command", args.copy()))
        if "LLM_CLI_BRIDGE_ENABLED" in args[-1]:
            if self.recreated >= 2:
                return "0\n" if "LLM_CLI_BRIDGE_ENABLED=0\n" in self.env_file.read_text() else "1\n"
            return (self.final_flag if self.recreated else self.flag) + "\n"
        if args[:3] == ["docker", "image", "inspect"]:
            return json.dumps(self.image)
        if (
            args[-1]
            == "from aimail.backends import cli_bridge; print(type(cli_bridge.enabled()) is bool)"
        ):
            return "True\n"
        raise AssertionError("Unexpected remote command")

    def compose(self, *args):
        self.events.append(("compose", args))
        self.recreated += 1
        if self.compose_error and self.recreated == 1:
            raise RuntimeError("activation compose failed")

    def wait_healthy(self, state):
        self.events.append(("healthy", state))
        return next(self.health)


@pytest.fixture
def execute_remote(monkeypatch, tmp_path):
    def run(deployer, *, configuration_source=None):
        deployer.env_file = tmp_path / ".env.aimail"
        deployer.env_file.write_text("KEEP=retained\nLLM_CLI_BRIDGE_ENABLED=1\n")
        configuration_source = (
            configuration_source
            if configuration_source is not None
            else (ROOT / PUBLIC_FILES[1]).read_bytes()
        )
        monkeypatch.setattr(sys, "argv", ["-", base64.b64encode(configuration_source).decode()])

        class Loader:
            def create_module(self, spec):
                return None

            def exec_module(self, module):
                module.Deploy = lambda: deployer

        def load(name, path):
            assert path == Path("/srv/aimail-deploy/deploy.py")
            return importlib.machinery.ModuleSpec(name, Loader())

        monkeypatch.setattr(importlib.util, "spec_from_file_location", load)
        previous = sys.modules.get("_aimail_cli_runtime")
        try:
            code = remote_code().replace(
                'Path("/srv/aimail-deploy/.env.aimail")', f"Path({str(deployer.env_file)!r})"
            )
            exec(compile(code, str(SCRIPT), "exec"), {"__name__": "__main__"})
        finally:
            if previous is None:
                sys.modules.pop("_aimail_cli_runtime", None)
            else:
                sys.modules["_aimail_cli_runtime"] = previous

    return run


def test_busy_deployment_lock_does_not_touch_runtime_or_release_an_unheld_lock(
    execute_remote, capsys
):
    deployer = FakeDeploy(busy=True)
    with pytest.raises(SystemExit, match="Cannot acquire Aimail deployment lock"):
        execute_remote(deployer)
    assert deployer.events == [("acquire",)]
    assert "Aimail healthy" not in capsys.readouterr().out


def test_enabled_runtime_is_verified_without_restarting_or_pulling(execute_remote, capsys):
    deployer = FakeDeploy(flag="1")
    execute_remote(deployer)
    names = [event[0] for event in deployer.events]
    assert names.count("verify") == 2
    assert "compose" not in names and "healthy" not in names
    assert names[-1] == "release"
    commands = [event[1] for event in deployer.events if event[0] == "command"]
    assert len(commands) == 2
    assert all(
        command[:5] == ["docker", "exec", "container-before", "python", "-c"]
        for command in commands
    )
    assert "Aimail healthy; CLI bridge enabled; source=" + COMMIT in capsys.readouterr().out


def test_disabled_runtime_recreates_only_current_local_image_then_checks_health(
    execute_remote, capsys
):
    deployer = FakeDeploy()
    execute_remote(deployer)
    composed = [event[1] for event in deployer.events if event[0] == "compose"]
    assert composed == [
        (
            "aimail-" + COMMIT,
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "aimail",
        )
    ]
    names = [event[0] for event in deployer.events]
    final_verify = max(i for i, name in enumerate(names) if name == "verify")
    assert names.index("compose") < names.index("healthy") < final_verify
    assert names.count("verify") == 2 and names[-1] == "release"
    commands = [event[1] for event in deployer.events if event[0] == "command"]
    assert commands[1] == ["docker", "image", "inspect", "aimail:aimail-" + COMMIT]
    assert commands[2][:8] == [
        "docker",
        "exec",
        "container-before",
        "uv",
        "run",
        "--no-sync",
        "python",
        "-c",
    ]
    assert commands[-1][2] == "container-after"
    assert "Aimail healthy; CLI bridge enabled" in capsys.readouterr().out


@pytest.mark.parametrize(
    "options",
    [
        {"health": (False, True)},
        {"compose_error": True, "health": (True,)},
        {"final_flag": "0", "health": (True, True)},
        {"verify_error": 2, "health": (True, True)},
    ],
)
def test_activation_failure_restores_same_image_and_disabled_flag_before_exit(
    execute_remote, capsys, options
):
    deployer = FakeDeploy(**options)
    with pytest.raises(SystemExit, match="previous disabled runtime was restored"):
        execute_remote(deployer)
    composed = [event[1] for event in deployer.events if event[0] == "compose"]
    assert len(composed) == 2 and composed[0] == composed[1]
    assert composed[0] == (
        "aimail-" + COMMIT,
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "--force-recreate",
        "aimail",
    )
    assert deployer.env_file.read_text() == "KEEP=retained\nLLM_CLI_BRIDGE_ENABLED=0\n"
    commands = [event[1] for event in deployer.events if event[0] == "command"]
    assert commands[-1][2] == "container-recovered"
    assert deployer.events[-2] == ("verify",)
    assert deployer.events[-1] == ("release",)
    assert "Aimail healthy" not in capsys.readouterr().out


def test_failed_recovery_never_reports_activation_or_recovery_success(execute_remote, capsys):
    deployer = FakeDeploy(health=(False, False))
    with pytest.raises(SystemExit, match="activation and recovery failed"):
        execute_remote(deployer)
    assert deployer.events[-1] == ("release",)
    assert sum(event[0] == "compose" for event in deployer.events) == 2
    assert "Aimail healthy" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "image",
    [
        [],
        [
            {
                "Id": "sha256:wrong",
                "Config": {"Labels": {"org.opencontainers.image.revision": COMMIT}},
            }
        ],
        [
            {
                "Id": "sha256:" + "d" * 64,
                "Config": {"Labels": {"org.opencontainers.image.revision": "b" * 40}},
            }
        ],
    ],
)
def test_missing_or_drifted_local_image_cannot_recreate_any_service(execute_remote, image):
    deployer = FakeDeploy(image=image)
    with pytest.raises(SystemExit, match="CLI runtime verification failed"):
        execute_remote(deployer)
    assert all(event[0] != "compose" for event in deployer.events)
    assert deployer.events[-1] == ("release",)


def test_remote_configuration_payload_hash_is_checked_before_deployment(execute_remote):
    deployer = FakeDeploy()
    with pytest.raises(SystemExit, match="Configuration tool checksum failed"):
        execute_remote(deployer, configuration_source=b"raise RuntimeError('must never execute')")
    assert deployer.events == []


@pytest.mark.parametrize(
    "state",
    [{}, {"source_sha": "main", "tag": "aimail-main"}, {"source_sha": COMMIT, "tag": "latest"}],
)
def test_invalid_recorded_state_is_rejected_before_any_docker_command(execute_remote, state):
    deployer = FakeDeploy(state=state)
    with pytest.raises(SystemExit, match="CLI runtime verification failed"):
        execute_remote(deployer)
    assert deployer.events == [("acquire",), ("state",), ("release",)]
