"""Isolated Spark canary: no OA gateway mutation, no external-provider fallback."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from aimail.backends import _extract_json
from aimail.paths import pilot_data_directory
from aimail.pilot import read_env
from aimail.tasks.summarize import SYSTEM, TASK_VERSION, InquirySummary, compose_source
from aimail.verify.numbers import unverified_numbers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--endpoint", help="Explicit operator override for a verified internal host"
    )
    args = parser.parse_args()
    os.umask(0o077)
    cfg = read_env(args.config)
    if cfg.get("KEEL_AI_UPSTREAM_PROVIDER") not in {"ollama", "openapi"}:
        raise ValueError("Canary requires explicitly configured internal API")
    url = args.endpoint or cfg["KEEL_AI_UPSTREAM_URL"]
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Unsafe endpoint")
    # Read the established local pilot data directory until its owner migrates it explicitly.
    directory = pilot_data_directory()
    conn = sqlite3.connect(f"file:{directory / 'mailbox.sqlite3'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, subject, body_new, body_quoted FROM message "
        "ORDER BY sent_at DESC, id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row is None:
        print('{"status":"no_mail"}')
        return 1
    # This canary intentionally covers text only, not a claim of full attachment coverage.
    source = compose_source(row["subject"], row["body_new"], row["body_quoted"])
    if len(source) > 24000:
        print('{"status":"source_too_large"}')
        return 1
    event = {
        "task_version": TASK_VERSION,
        "source_id": row["id"],
        "started_at": datetime.now(UTC).isoformat(),
        "model": cfg["KEEL_AI_UPSTREAM_MODEL"],
        "usage": None,
        "cost": None,
        "cost_status": "unpriced_internal_compute",
        "coverage": "single_mail_text_only",
        "status": "failed",
    }
    start = time.monotonic()
    response = None
    try:
        headers = {}
        if cfg.get("KEEL_AI_UPSTREAM_TOKEN"):
            headers["Authorization"] = "Bearer " + cfg["KEEL_AI_UPSTREAM_TOKEN"]
        response = httpx.post(
            url,
            headers=headers,
            timeout=httpx.Timeout(180, connect=8),
            follow_redirects=False,
            json={
                "model": event["model"],
                "temperature": 0,
                "max_tokens": 3000,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": source},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "inquiry",
                        "schema": InquirySummary.model_json_schema(),
                    },
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        event["usage"] = {
            key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        event["actual_model"] = data.get("model")
        summary = InquirySummary.model_validate_json(
            _extract_json(data["choices"][0]["message"]["content"])
        )
        warnings = unverified_numbers(summary.quoted_numbers, source)
        event["status"] = "needs_review" if warnings else "validated_structure"
        result = {**event, "summary": summary.model_dump(), "unverified": list(warnings)}
        with (directory / "latest-reading.json").open("w") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
    except Exception as exc:
        event["error_type"] = type(exc).__name__
    finally:
        event["elapsed_seconds"] = round(time.monotonic() - start, 3)
        event["http_status"] = response.status_code if response is not None else None
        with (directory / "model-calls.jsonl").open("a") as output:
            output.write(json.dumps(event) + "\n")
            output.flush()
            os.fsync(output.fileno())
        print(json.dumps(event))
    return int(event["status"] == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
