#!/usr/bin/env python3
"""Read a pinned candidate prompt as data; evaluate in this process only.

Usage: uv run python tools/eval_prompt_candidate.py RAW_COMMIT_URL SOURCE_FILE_SHA256
The tool can also be passed via stdin to an already running container. No downloaded Python
is imported, compiled or executed. Existing production files and the DB stay untouched.
Reports identify the configured backend/model route. The adapter does not expose
the resolved upstream model ID, so a route match does not prove its weights are unchanged.
Use --source-base64 to transfer public candidate source through argv when the
container cannot access GitHub. Offline data has the same URL, hash and AST checks.
The candidate defaults to the next installed version. --candidate-version can
explicitly select a later numbered version while retaining the same checks.
"""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import hashlib
import json
import os
import re
import runpy
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_BYTES = 128 * 1024
MAX_BASE64_BYTES = 96 * 1024
FIELDS = ("is_inquiry", "mail_type", "is_trade", "trade_role")


def stop(reason: str) -> None:
    print(f"STOP before model calls: {reason}", file=sys.stderr, flush=True)
    raise SystemExit(2)


def checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parsed_module(payload: bytes, label: str) -> ast.Module:
    try:
        return ast.parse(payload.decode("utf-8"), filename=label)
    except (UnicodeError, SyntaxError):
        stop(f"{label}: invalid UTF-8/Python source")


def prompt_constants(tree: ast.Module, expected_version: str) -> tuple[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            hits = [
                target.id
                for target in node.targets
                if isinstance(target, ast.Name) and target.id in {"SYSTEM", "TASK_VERSION"}
            ]
            if not hits:
                continue
            if len(node.targets) != 1 or len(hits) != 1:
                stop("SYSTEM/TASK_VERSION must be separate top-level literal assignments")
            name = hits[0]
            if name in constants or not isinstance(node.value, ast.Constant):
                stop("SYSTEM/TASK_VERSION must each have one string literal assignment")
            if not isinstance(node.value.value, str):
                stop("SYSTEM/TASK_VERSION must each be a string literal")
            constants[name] = node.value.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in {"SYSTEM", "TASK_VERSION"}:
                stop("annotated SYSTEM/TASK_VERSION assignments are not allowed")
    if constants.keys() != {"SYSTEM", "TASK_VERSION"}:
        stop("candidate is missing SYSTEM or TASK_VERSION")
    if constants["TASK_VERSION"] != expected_version or not constants["SYSTEM"].strip():
        stop(f"candidate must declare a nonempty SYSTEM and {expected_version}")
    return constants["SYSTEM"], constants["TASK_VERSION"]


def contract_ast(tree: ast.Module) -> str:
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "InquirySummary"
    ]
    if len(nodes) != 1:
        stop("source must have exactly one InquirySummary contract")
    return ast.dump(nodes[0], include_attributes=False)


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect rejected", headers, fp)


def source_reference(url: str, expected_hash: str) -> str:
    parts = urllib.parse.urlsplit(url)
    allowed_path = re.fullmatch(
        r"/niuroumiantt/aimail/([0-9a-f]{40})/server/src/aimail/tasks/summarize\.py",
        parts.path,
    )
    if (
        parts.scheme != "https"
        or parts.netloc != "raw.githubusercontent.com"
        or parts.query
        or parts.fragment
        or not allowed_path
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
    ):
        stop("use the immutable aimail raw commit URL and its 64-character SHA256")
    return allowed_path.group(1)


def verify_source(data: bytes, expected_hash: str) -> bytes:
    if len(data) > MAX_BYTES or checksum(data) != expected_hash:
        stop("candidate is over 128 KiB or its SHA256 does not match")
    return data


def offline_source(url: str, expected_hash: str, encoded: str) -> tuple[bytes, str]:
    source_sha = source_reference(url, expected_hash)
    if not encoded or len(encoded) > MAX_BASE64_BYTES:
        stop("offline source must be nonempty Base64 and at most 96 KiB encoded")
    try:
        data = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeError, ValueError, binascii.Error):
        stop("offline source must be valid ASCII Base64 without whitespace")
    return verify_source(data, expected_hash), source_sha


def download_source(url: str, expected_hash: str) -> tuple[bytes, str]:
    source_sha = source_reference(url, expected_hash)
    request = urllib.request.Request(url, headers={"User-Agent": "aimail-synthetic-eval/1"})
    try:
        with urllib.request.build_opener(NoRedirects).open(request, timeout=30) as response:
            data = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        stop(f"candidate download failed ({type(exc).__name__}); production is untouched")
    return verify_source(data, expected_hash), source_sha


def failed_samples(report: dict, rows: list[dict], label: str) -> None:
    indexed = {prediction["id"]: prediction for prediction in report["predictions"]}
    for row in rows:
        prediction = indexed[row["id"]]
        expected = tuple(row["reference"][field] for field in FIELDS)
        actual = tuple(prediction.get(field) for field in FIELDS)
        if prediction.get("status") != "ok" or actual != expected or prediction.get("unverified"):
            print(
                f"{label} {row['id']}: predicted={actual!r}; expected={expected!r}; "
                f"status={prediction.get('status')}; unverified={prediction.get('unverified', [])}",
                file=sys.stderr,
                flush=True,
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_url")
    parser.add_argument("source_sha256")
    parser.add_argument("--source-base64", help="public candidate source; disable network fetching")
    parser.add_argument(
        "--candidate-version",
        help="explicit numbered task version newer than the installed version",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "server" / "src"))
    from aimail import backends
    from aimail.tasks import summarize as task

    dataset = root / "evals" / "summarize_inquiry" / "dataset.sample.jsonl"
    runner = dataset.parent / "run.py"
    outputs = [args.out.resolve(), args.report_json.resolve()]
    protected = {args.baseline.resolve(), dataset.resolve(), runner.resolve(), Path(task.__file__)}
    if os.environ.get("DB_PATH"):
        protected.add(Path(os.environ["DB_PATH"]).resolve())
    if len(set(outputs)) != 2 or any(
        output in protected
        or any(output.is_relative_to(root / folder) for folder in ("server", "web", "tools"))
        for output in outputs
    ):
        stop("output paths must not replace the baseline, dataset, database or application source")
    try:
        rows = [
            json.loads(line) for line in dataset.read_text("utf-8").splitlines() if line.strip()
        ]
        baseline = json.loads(args.baseline.read_text("utf-8"))
    except (OSError, ValueError):
        stop("the installed dataset or baseline report is missing/invalid")
    dataset_hash = checksum(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode())
    expected_ids = [row["id"] for row in rows]
    installed_system_hash = checksum(task.SYSTEM.encode())
    schema_hash = checksum(
        json.dumps(
            task.InquirySummary.model_json_schema(), ensure_ascii=False, sort_keys=True
        ).encode()
    )
    try:
        valid_baseline = (
            bool(rows)
            and baseline["dataset_sha256"] == dataset_hash
            and baseline["model"] == backends.describe()
            and baseline["task_version"] == task.TASK_VERSION
            and baseline["sample_count"] == len(rows)
            and [prediction["id"] for prediction in baseline["predictions"]] == expected_ids
            and isinstance(baseline["metrics"], dict)
            and {"malformed", "unverified_numbers", "is_inquiry"} <= baseline["metrics"].keys()
            and baseline.get("system_sha256", installed_system_hash) == installed_system_hash
            and baseline.get("schema_sha256", schema_hash) == schema_hash
        )
    except (KeyError, TypeError):
        valid_baseline = False
    if not valid_baseline:
        stop("baseline task version, configured model route, dataset hash/IDs/count do not match")
    ready, _ = backends.ready()
    if backends.backend() != "local" or not ready:
        stop("this qualification requires the configured local model backend")

    version = re.fullmatch(r"summarize_inquiry@([1-9]\d*)", task.TASK_VERSION)
    if not version:
        stop("installed task must declare a numbered summarize_inquiry version")
    expected_version = f"summarize_inquiry@{int(version.group(1)) + 1}"
    if args.candidate_version is not None:
        selected_version = re.fullmatch(r"summarize_inquiry@([1-9]\d*)", args.candidate_version)
        if not selected_version or int(selected_version.group(1)) <= int(version.group(1)):
            stop(
                "explicit candidate version must be numbered summarize_inquiry newer than installed"
            )
        expected_version = args.candidate_version
    installed_bytes = Path(task.__file__).read_bytes()
    if args.source_base64 is not None:
        candidate_bytes, source_sha = offline_source(
            args.source_url, args.source_sha256, args.source_base64
        )
    else:
        candidate_bytes, source_sha = download_source(args.source_url, args.source_sha256)
    candidate_tree = parsed_module(candidate_bytes, "candidate")
    candidate_system, candidate_version = prompt_constants(candidate_tree, expected_version)
    if contract_ast(candidate_tree) != contract_ast(parsed_module(installed_bytes, "installed")):
        stop("InquirySummary changed; this driver permits a prompt/version experiment only")
    candidate_system_hash = checksum(candidate_system.encode())
    print(
        f"Baseline: route={baseline['model']}; task={baseline['task_version']}; "
        f"dataset_sha256={dataset_hash}; system_sha256={installed_system_hash}",
        file=sys.stderr,
        flush=True,
    )
    print(
        f"Candidate: route={backends.describe()}; task={candidate_version}; "
        f"source_sha={source_sha}; "
        f"source_file_sha256={args.source_sha256}; system_sha256={candidate_system_hash}; "
        f"schema_sha256={schema_hash}; samples={len(rows)}",
        file=sys.stderr,
        flush=True,
    )
    print(
        "Model identity is the configured route only; the current adapter does not expose "
        "the upstream's resolved model ID. No mailbox/database is read or written.",
        file=sys.stderr,
        flush=True,
    )
    print(f"Diagnostic tuple order: {FIELDS!r}", file=sys.stderr, flush=True)
    failed_samples(baseline, rows, "BASELINE")

    original_system, original_version, original_argv = task.SYSTEM, task.TASK_VERSION, sys.argv
    # Module assignments exist only in this docker-exec process. The running server
    # and worker have separate Python memory and their code/files are unchanged.
    task.SYSTEM, task.TASK_VERSION = candidate_system, candidate_version
    with tempfile.TemporaryDirectory(prefix="aimail-synthetic-candidate-", dir="/tmp") as temp:
        temp_tsv, temp_json = Path(temp) / "eval.tsv", Path(temp) / "eval.json"
        sys.argv = [
            str(runner),
            str(dataset),
            "--no-judge",
            "--out",
            str(temp_tsv),
            "--report-json",
            str(temp_json),
            "--baseline",
            str(args.baseline),
        ]
        try:
            runpy.run_path(str(runner), run_name="__main__")
            status = 0
        except SystemExit as exc:
            status = exc.code if isinstance(exc.code, int) else 1
        except Exception as exc:
            print(
                f"Evaluation stopped ({type(exc).__name__}); production is untouched",
                file=sys.stderr,
            )
            return 2
        finally:
            task.SYSTEM, task.TASK_VERSION, sys.argv = (
                original_system,
                original_version,
                original_argv,
            )
        if not temp_json.is_file():
            print("No candidate report was produced", file=sys.stderr)
            return status or 2
        candidate_report = json.loads(temp_json.read_text("utf-8"))
        candidate_report.update(
            {
                "candidate_source_sha": source_sha,
                "candidate_source_file_sha256": args.source_sha256,
                "candidate_transport": "offline_base64"
                if args.source_base64 is not None
                else "https",
                "system_sha256": candidate_system_hash,
                "schema_sha256": schema_hash,
                "baseline_task_version": baseline["task_version"],
                "baseline_system_sha256": installed_system_hash,
                "installed_task_file_sha256": checksum(installed_bytes),
                "model_identity": (
                    "configured_route_only; resolved upstream model ID is unavailable"
                ),
                "experiment": "prompt/version override in isolated synthetic evaluation process",
            }
        )
        temp_json.write_text(
            json.dumps(candidate_report, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        for source, destination in ((temp_tsv, args.out), (temp_json, args.report_json)):
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as staged:
                staged.write(source.read_bytes())
                staged_path = Path(staged.name)
            os.replace(staged_path, destination)
        failed_samples(candidate_report, rows, "CANDIDATE")
        print(
            f"Candidate report: {args.report_json}; comparison: {args.out}; exit_status={status}",
            file=sys.stderr,
            flush=True,
        )
        return status


if __name__ == "__main__":
    raise SystemExit(main())
