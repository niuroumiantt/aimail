"""Test the m5 launcher's trust gates with fake transfers, never a real model or SSH."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "review_spark_candidate_m5.sh"
COMMIT = "a" * 40
HELPER_HASH = "b" * 64
TASK_HASH = "c" * 64
DIGESTS = {
    "eval_prompt_candidate.py": HELPER_HASH,
    "summarize_7.py": TASK_HASH,
    "configure_cli_bridge.py": "2195656780c5ff6800568c12942e0d8bb032959c596a7e496f266ebcd31b40be",
    "baseline_5.json": "0f66cd6677c249b721eeaeae2402ced92debbddbef71bd50d092a1423ce740e8",
    "summarize_5.py": "b012cbf9f6d2bebf1ccf23ac886a19d37db895632bbc18adaf99e7db7b88bee3",
}


@pytest.fixture
def launcher(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    captures = tmp_path / "calls.jsonl"
    program = (
        f"#!{sys.executable}\n"
        + """import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
record = {"name": name, "args": args}
if name == "curl":
    dest = pathlib.Path(args[args.index("-o") + 1])
    dest.write_text("PUBLIC_" + dest.name)
elif name == "shasum":
    path = pathlib.Path(args[-1])
    digests = json.loads(os.environ["TEST_DIGESTS"])
    digest = digests[path.name]
    if path.name == os.environ.get("TEST_BAD_FILE"):
        digest = "0" * 64
    print(digest + "  " + str(path))
elif name == "ssh":
    if "cat" in args:
        record["kind"] = "report"
        print("SYNTHETIC_CURRENT_REPORT")
        status = int(os.environ.get("TEST_REPORT_STATUS", "0"))
    elif "python3" in args:
        record["kind"] = "configure"
        record["stdin"] = sys.stdin.read()
        print("Saved for next deployment; no restart")
        status = int(os.environ.get("TEST_CONFIGURE_STATUS", "0"))
    else:
        record["kind"] = "evaluate"
        record["stdin"] = sys.stdin.read()
        status = int(os.environ.get("TEST_EVAL_STATUS", "0"))
    with open(os.environ["TEST_CALLS"], "a") as output:
        output.write(json.dumps(record) + "\\n")
    sys.exit(status)
with open(os.environ["TEST_CALLS"], "a") as output:
    output.write(json.dumps(record) + "\\n")
"""
    )
    for name in ("curl", "shasum", "ssh"):
        executable = commands / name
        executable.write_text(program)
        executable.chmod(0o700)
    environment = {
        **os.environ,
        "PATH": f"{commands}:{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "TEST_CALLS": str(captures),
        "TEST_DIGESTS": json.dumps(DIGESTS),
    }

    def run(args=None, **overrides):
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                *(args if args is not None else [COMMIT, HELPER_HASH, TASK_HASH]),
            ],
            env={**environment, **overrides},
            text=True,
            capture_output=True,
            timeout=5,
        )
        calls = (
            [json.loads(line) for line in captures.read_text().splitlines()]
            if captures.exists()
            else []
        )
        assert not list(tmp_path.glob("aimail-spark-review.*")), (
            "known temporary inputs are removed"
        )
        return result, calls

    return run


@pytest.mark.parametrize(
    "args",
    [
        [],
        [COMMIT],
        [COMMIT, HELPER_HASH, TASK_HASH, "extra"],
        ["main", HELPER_HASH, TASK_HASH],
        [COMMIT, "x" * 64, TASK_HASH],
        [COMMIT, HELPER_HASH, "$(touch /tmp/unsafe)"],
    ],
)
def test_invalid_pins_are_rejected_before_any_transfer_or_ssh(launcher, args):
    result, calls = launcher(args)
    assert result.returncode == 2 and calls == []


@pytest.mark.parametrize("bad_file", list(DIGESTS))
def test_every_checksum_gates_all_ssh_operations(launcher, bad_file):
    result, calls = launcher(TEST_BAD_FILE=bad_file)
    assert result.returncode == 2
    assert "checksum failed" in result.stderr
    assert all(call["name"] != "ssh" for call in calls)


@pytest.mark.parametrize("status", [2, 255])
def test_evaluation_error_never_prints_stale_report_or_enables_bridge(launcher, status):
    result, calls = launcher(TEST_EVAL_STATUS=str(status))
    assert result.returncode == status
    assert [call["kind"] for call in calls if call["name"] == "ssh"] == ["evaluate"]
    assert "SYNTHETIC_CURRENT_REPORT" not in result.stdout


def test_score_regression_prints_only_this_candidate_report_and_does_not_enable(launcher):
    result, calls = launcher(TEST_EVAL_STATUS="1")
    assert result.returncode == 1
    remote = [call for call in calls if call["name"] == "ssh"]
    assert [call["kind"] for call in remote] == ["evaluate", "report"]
    assert remote[1]["args"][-2:] == [
        f"/tmp/aimail-trade-eval-7-{COMMIT[:12]}.json",
        f"/tmp/aimail-trade-eval-7-{COMMIT[:12]}.tsv",
    ]
    assert "SYNTHETIC_CURRENT_REPORT" in result.stdout


def test_pass_verifies_five_inputs_before_evaluation_report_then_configuration(launcher):
    result, calls = launcher()
    assert result.returncode == 0
    first_ssh = next(i for i, call in enumerate(calls) if call["name"] == "ssh")
    assert [call["name"] for call in calls[:first_ssh]] == ["curl"] * 5 + ["shasum"] * 5
    remote = [call for call in calls if call["name"] == "ssh"]
    assert [call["kind"] for call in remote] == ["evaluate", "report", "configure"]
    evaluation = remote[0]
    args = evaluation["args"]
    assert "aliyun" in args and "mainland-aimail-1" in args
    remote_args = args[args.index("aliyun") + 1 :]
    assert remote_args[:11] == [
        "sudo",
        "docker",
        "exec",
        "-i",
        "mainland-aimail-1",
        "uv",
        "run",
        "--no-sync",
        "python",
        "-u",
        "-",
    ]
    assert "--project" not in remote_args
    assert shlex.split(" ".join(remote_args)) == remote_args
    report_args = remote[1]["args"]
    assert report_args[report_args.index("aliyun") + 1 :][:5] == [
        "sudo",
        "docker",
        "exec",
        "mainland-aimail-1",
        "cat",
    ]
    assert args[args.index("--candidate-version") + 1] == "summarize_inquiry@7"
    assert args[args.index("--baseline") + 1] == "/tmp/aimail-trade-eval.json"
    assert args[args.index("--baseline-base64") + 1] == "UFVCTElDX2Jhc2VsaW5lXzUuanNvbg=="
    assert args[args.index("--baseline-source-url") + 1].endswith(
        "/dc81766c22d8a2c3547bd14aa0e3b7d1a42ed2c6/server/src/aimail/tasks/summarize.py"
    )
    assert evaluation["stdin"] == "PUBLIC_eval_prompt_candidate.py"
    assert remote[2]["args"][-3:] == ["sudo", "python3", "-"]
    assert remote[2]["stdin"] == "PUBLIC_configure_cli_bridge.py"
    assert all("restart" not in call["args"] for call in remote)


def test_report_failure_prevents_configuration_and_is_nonzero(launcher):
    result, calls = launcher(TEST_REPORT_STATUS="3")
    assert result.returncode == 3
    assert [call["kind"] for call in calls if call["name"] == "ssh"] == ["evaluate", "report"]


def test_configuration_failure_is_not_reported_as_success(launcher):
    result, calls = launcher(TEST_CONFIGURE_STATUS="4")
    assert result.returncode == 4
    assert [call["kind"] for call in calls if call["name"] == "ssh"] == [
        "evaluate",
        "report",
        "configure",
    ]
