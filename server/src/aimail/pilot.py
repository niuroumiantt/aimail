"""Bounded, read-only mailbox canary. Never starts SMTP, polling or a web server."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aimail.ingest.imap import ImapSource
from aimail.ingest.run import store_raw
from aimail.paths import pilot_data_directory
from aimail.store import repo
from aimail.store.db import connect


def read_env(path: Path) -> dict[str, str]:
    """Parse values as data, never execute a sourced shell file."""
    if path.stat().st_mode & 0o077:
        raise ValueError("Configuration must have private permissions (0600)")
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError("Unsupported configuration syntax")
        words = shlex.split(value, comments=True)
        if len(words) > 1:
            raise ValueError("Unsupported configuration value")
        result[key] = words[0] if words else ""
    return result


def recent_uids(source: ImapSource, days: int, limit: int) -> list[int]:
    if not 1 <= days <= 30 or not 1 <= limit <= 100:
        raise ValueError("Pilot bounds: 1–30 days, 1–100 messages")
    since = datetime.now(UTC) - timedelta(days=days)
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    date = f"{since.day:02d}-{months[since.month - 1]}-{since.year}"
    status, data = source.conn.uid("SEARCH", None, "SINCE", date)
    if status != "OK":
        raise RuntimeError("Mailbox search failed")
    values = sorted({int(x) for x in data[0].split()}) if data and data[0] else []
    return values[-limit:]


def bounded_raw(source: ImapSource, uid: int, max_bytes: int = 2_000_000) -> bytes | None:
    status, data = source.conn.uid("FETCH", str(uid), "(RFC822.SIZE)")
    sizes = [
        int(n)
        for item in data or []
        if isinstance(item, bytes)
        for n in re.findall(rb"RFC822.SIZE (\d+)", item)
    ]
    if status != "OK" or not sizes:
        raise RuntimeError("Mailbox size check failed")
    if max(sizes) > max_bytes:
        return None
    raw = source.fetch_raw(uid)
    return raw if len(raw) <= max_bytes else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mail-config", required=True, type=Path)
    parser.add_argument("--mailbox", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.days <= 30 or not 1 <= args.limit <= 100:
        parser.error("days <= 30 and limit <= 100 required")
    os.umask(0o077)
    config = read_env(args.mail_config)
    if config.get("KEEL_CRM_MAILBOX_ADDRESS") != args.mailbox:
        raise ValueError("Mailbox does not match explicitly requested account")
    directory = pilot_data_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Dedicated pilot database; never updates the full-sync cursor or the OA database.
    conn = connect(directory / "mailbox.sqlite3")
    mailbox = repo.ensure_mailbox(conn, args.mailbox)
    source = None
    counts = {"selected": 0, "stored": 0, "duplicate": 0, "oversize": 0}
    try:
        source = ImapSource(
            config["KEEL_CRM_MAILBOX_IMAP_HOST"],
            993,
            args.mailbox,
            config["KEEL_CRM_MAILBOX_PASSWORD"],
            "INBOX",
        )
        uids = recent_uids(source, args.days, args.limit)
        counts["selected"] = len(uids)
        for uid in uids:
            raw = bounded_raw(source, uid)
            if raw is None:
                counts["oversize"] += 1
                continue
            pk, _ = store_raw(conn, mailbox, raw, "in", datetime.now(UTC))
            counts["stored" if pk is not None else "duplicate"] += 1
        print(
            json.dumps(
                {
                    "status": "ok",
                    "folder": "INBOX",
                    "days": args.days,
                    "limit": args.limit,
                    **counts,
                }
            )
        )
        return 0
    except Exception as exc:
        # Never expose an upstream exception containing authentication or mail content.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, **counts}))
        return 1
    finally:
        if source is not None:
            source.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
