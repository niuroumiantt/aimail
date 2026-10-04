"""Run bounded native metadata against a fake CLI, without inference or SSH."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/preflight_codex_m5.sh"
COMMIT = "0dca357e5cd8867ba3f6262da722c210fea38748"
FILES = (
    "tools/run_cli_worker.py",
    "server/src/aimail/backends/cli.py",
    "server/src/aimail/backends/cli_bridge.py",
)


@pytest.fixture
def preflight(tmp_path):
    home = tmp_path / "operator"
    cache = home / ".local/share/aimail/cli-worker" / COMMIT
    # These three reviewed sources still match the frozen client. Updating them
    # requires reviewing this operator tool's pinned client and hashes together.
    # Avoid git history: Actions' default shallow checkout contains only HEAD.
    for relative in FILES:
        path = cache / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    auth_home = home / "codex-auth"
    auth_home.mkdir()
    (auth_home / "auth.json").write_text("PRIVATE_AUTH_FILE_TOKEN")
    captures = tmp_path / "calls.jsonl"
    executable = tmp_path / "actual codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        + """import json, os, pathlib, sys
args = sys.argv[1:]
allowed = [["--version"], ["exec", "--help"], ["login", "status"]]
assert args in allowed, "inference forbidden"
assert sys.stdin.read() == ""
with open(os.environ["TEST_CALLS"], "a") as output:
    output.write(json.dumps({"args": args, "cwd": os.getcwd(), "executable": sys.argv[0],
                             "auth_home": os.environ["CODEX_HOME"]}) + "\\n")
sys.stderr.write("PRIVATE_STDERR_TOKEN\\n")
if args == ["--version"]:
    print("codex-cli 0.160.0")
elif args == ["exec", "--help"]:
    print("--ignore-user-config\\n--ignore-rules\\n--ephemeral\\n--output-schema\\n--disable")
    print("PRIVATE_HELP_TOKEN")
elif os.environ.get("TEST_LOGIN_FAIL"):
    sys.stderr.write("Not logged in PRIVATE_ACCOUNT_TOKEN")
    sys.exit(1)
else:
    sys.stderr.write("Logged in using " + os.environ.get("TEST_AUTH_METHOD", "ChatGPT") + "\\n")
"""
    )
    executable.chmod(0o700)
    alias = tmp_path / "codex-alias"
    alias.symlink_to(executable)
    environment = {
        **os.environ,
        "HOME": str(home),
        "CODEX_HOME": str(auth_home),
        "CODEX_CLI_COMMAND": str(alias),
        "LLM_CLI_BRIDGE_ENABLED": "1",
        "TEST_CALLS": str(captures),
    }
    body = re.search(r"<<'PY'\n(.*?)\nPY\n", SCRIPT.read_text(), re.DOTALL).group(1)

    def run(config=None, corrupt=None, **overrides):
        if config is not None:
            (auth_home / "config.toml").write_text(config)
        if corrupt is not None:
            with (cache / corrupt).open("ab") as output:
                output.write(b"\nraise RuntimeError('PRIVATE_CORRUPT_SOURCE')\n")
        result = subprocess.run(
            [sys.executable, "-"],
            input=body,
            env={**environment, **overrides},
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
        assert "PRIVATE" not in result.stdout + result.stderr
        calls = (
            [json.loads(line) for line in captures.read_text().splitlines()]
            if captures.exists()
            else []
        )
        return result, json.loads(result.stdout), calls

    return run, executable, auth_home


def test_preflight_manifest_matches_the_frozen_public_client_sources():
    assert re.findall(r'"([a-f0-9]{64})"', SCRIPT.read_text()) == [
        hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in FILES
    ]


def test_preflight_only_runs_three_metadata_commands_from_actual_resolved_cli(preflight):
    run, executable, auth_home = preflight
    result, report, calls = run()
    assert result.returncode == 0 and result.stderr == ""
    assert [call["args"] for call in calls] == [
        ["--version"],
        ["exec", "--help"],
        ["login", "status"],
    ]
    assert all(call["executable"] == str(executable) for call in calls)
    assert all(call["auth_home"] == str(auth_home) for call in calls)
    assert len({call["cwd"] for call in calls}) == 1
    cwd = Path(calls[0]["cwd"])
    assert cwd.name.startswith("aimail-model-") and not cwd.exists()
    assert report["version"] == "0.160.0"
    assert all(report["flags"].values())
    assert report["login_method"] == "CHATGPT" and report["login_exit"] == 0
    assert report["auth_file_exists"] is True
    assert report["scope"] == "METADATA_ONLY_NOT_INFERENCE_AUTH_VERIFICATION"


def test_keyring_and_profile_route_metadata_do_not_expose_config_or_login_credentials(preflight):
    run, _, _ = preflight
    result, report, _ = run(
        'profile="selected"\ncli_auth_credentials_store="keyring"\n'
        'chatgpt_base_url="https://PRIVATE_CHATGPT_URL"\n'
        "[features]\nsecret_auth_storage=true\n"
        '[profiles.selected]\nmodel_provider="private-provider"\nmodel="gpt-5.4"\n'
        '[model_providers.private-provider]\nbase_url="https://PRIVATE_URL"\n'
        'env_key="PRIVATE_KEY_NAME"\nhttp_headers={Authorization="PRIVATE_TOKEN"}\n',
        TEST_AUTH_METHOD="an API key - PRIVATE_API_TOKEN",
    )
    assert result.returncode == 0
    assert report["auth_store"] == "keyring" and report["auth_store_configured"] is True
    assert report["secret_auth_storage_configured"] is True
    assert report["secret_auth_storage_true"] is True
    assert report["provider_default_bool"] is False
    assert report["provider_base_url_configured"] is True
    assert report["chatgpt_base_url_configured"] is True
    assert report["provider_auth_configured"] is True
    assert report["model_matches_probe"] is True
    assert report["login_method"] == "API_KEY"


@pytest.mark.parametrize("relative", FILES)
def test_corrupted_cached_source_stops_before_loading_or_starting_cli(preflight, relative):
    run, _, _ = preflight
    result, report, calls = run(corrupt=relative)
    assert result.returncode == 2 and calls == []
    assert report == {"precheck": "worker_source_unavailable_or_mismatched"}


def test_login_failure_does_not_claim_authenticated_or_expose_native_error(preflight):
    run, _, _ = preflight
    result, report, calls = run(TEST_LOGIN_FAIL="1")
    assert result.returncode == 0 and len(calls) == 3
    assert report["login_exit"] == 1 and report["login_reason"] == "nonzero_exit"
    assert report["login_method"] == "UNKNOWN"


def test_invalid_config_is_unavailable_without_partial_metadata_or_parser_message(preflight):
    run, _, _ = preflight
    result, report, _ = run('cli_auth_credentials_store="PRIVATE_BROKEN\n')
    assert result.returncode == 0 and report["config_metadata"] == "UNAVAILABLE"
    assert "auth_store" not in report and "provider_default_bool" not in report


def test_default_file_storage_is_not_inference_authentication_evidence(preflight):
    run, _, _ = preflight
    _, report, _ = run()
    assert report["config_metadata"] == "NO_CONFIG_FILE"
    assert report["auth_store"] == "file" and report["auth_store_configured"] is False
    assert report["secret_auth_storage_configured"] is False
    assert report["model_matches_probe"] is None


def test_shell_rejects_arguments_before_inspecting_environment():
    result = subprocess.run(
        ["bash", str(SCRIPT), "unexpected"], text=True, capture_output=True, check=False
    )
    assert result.returncode == 2 and json.loads(result.stdout) == {
        "precheck": "unexpected_arguments"
    }
