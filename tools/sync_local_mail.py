#!/usr/bin/env python3
"""M5 personal mail mirror. Immutable originals, attachments and attributed translations.

Config and data stay outside Git. This reader cannot delete or send cloud mail.
SSH transport keeps the export API private; each device also needs a scoped token.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import re
import shlex
import socket
import sqlite3
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from datetime import UTC, datetime
from email import policy
from pathlib import Path


def write_private(path, content):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    with temporary.open("wb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def transport(config):
    if not config.get("ssh"):
        yield config["endpoint"]
        return
    command = config["ssh"]
    container = config["container"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", container):
        raise ValueError("invalid container")
    address = subprocess.check_output(
        command
        + [
            shlex.join(
                [
                    "sudo",
                    "-n",
                    "docker",
                    "inspect",
                    "--format",
                    "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                    container,
                ]
            )
        ],
        text=True,
    ).split()[0]
    socket.inet_aton(address)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    forward = subprocess.Popen(
        command[:-1]
        + ["-N", "-o", "ExitOnForwardFailure=yes", "-L", f"127.0.0.1:{port}:{address}:8900"]
        + command[-1:],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if forward.poll() is not None:
                raise RuntimeError("secure transport unavailable")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("secure transport timeout")
        yield f"http://127.0.0.1:{port}"
    finally:
        forward.terminate()
        try:
            forward.wait(timeout=5)
        except subprocess.TimeoutExpired:
            forward.kill()
            forward.wait()


def sync(config, root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    with sqlite3.connect(root / "mail.sqlite3") as db, transport(config) as endpoint:
        os.chmod(root / "mail.sqlite3", 0o600)
        db.executescript("""
        CREATE TABLE IF NOT EXISTS message(id INTEGER PRIMARY KEY, payload TEXT NOT NULL,
          raw_sha256 TEXT NOT NULL, file TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attachment(message_id INTEGER, part INTEGER, filename TEXT,
          sha256 TEXT, file TEXT, PRIMARY KEY(message_id,part));
        CREATE TABLE IF NOT EXISTS translation(id INTEGER PRIMARY KEY, source_id INTEGER,
          payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cursor(kind TEXT PRIMARY KEY, value INTEGER NOT NULL);
        """)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def get(path, binary=False):
            request = urllib.request.Request(
                endpoint + path, headers={"Authorization": "Bearer " + config["token"]}
            )
            with opener.open(request, timeout=60) as response:
                body = response.read()
                return body if binary else json.loads(body)

        for kind in ("messages", "translations"):
            row = db.execute("SELECT value FROM cursor WHERE kind=?", (kind,)).fetchone()
            after = row[0] if row else 0
            while True:
                result = get(f"/v1/local-mail/{kind}?after={after}&limit=50")
                expected = "local-mail@1" if kind == "messages" else "local-translations@1"
                if result["version"] != expected:
                    raise ValueError("unsupported export version")
                for item in result["items"]:
                    if item["id"] <= after:
                        raise ValueError("non-monotonic export")
                    if kind == "messages":
                        raw = get(f"/v1/local-mail/messages/{item['id']}/original", binary=True)
                        digest = hashlib.sha256(raw).hexdigest()
                        if digest != item["raw_sha256"]:
                            raise ValueError("original checksum mismatch")
                        filename = Path("originals") / digest[:2] / (digest + ".eml")
                        write_private(root / filename, raw)
                        parsed = email.message_from_bytes(raw, policy=policy.default)
                        for part, attachment in enumerate(parsed.walk()):
                            if attachment.is_multipart() or not (
                                attachment.get_filename()
                                or attachment.get_content_disposition() == "attachment"
                                or attachment.get("Content-ID")
                            ):
                                continue
                            content = attachment.get_payload(decode=True)
                            if content is None:
                                continue
                            sha = hashlib.sha256(content).hexdigest()
                            name = attachment.get_filename() or "inline-image"
                            safe = (
                                re.sub(r"[^\w.\- ]", "_", name).replace("..", "_")[:100].strip(". ")
                                or "attachment"
                            )
                            file = Path("attachments") / sha / safe
                            write_private(root / file, content)
                            db.execute(
                                "INSERT OR REPLACE INTO attachment VALUES(?,?,?,?,?)",
                                (item["id"], part, name, sha, str(file)),
                            )
                        db.execute(
                            "INSERT OR REPLACE INTO message VALUES(?,?,?,?)",
                            (
                                item["id"],
                                json.dumps(item, ensure_ascii=False),
                                digest,
                                str(filename),
                            ),
                        )
                    else:
                        if not db.execute(
                            "SELECT 1 FROM message WHERE id=?", (item["source_id"],)
                        ).fetchone():
                            raise ValueError("translation arrived before original")
                        db.execute(
                            "INSERT OR REPLACE INTO translation VALUES(?,?,?)",
                            (item["id"], item["source_id"], json.dumps(item, ensure_ascii=False)),
                        )
                    after = item["id"]
                if result["next_after"] != after:
                    raise ValueError("export cursor mismatch")
                db.execute("INSERT OR REPLACE INTO cursor VALUES(?,?)", (kind, after))
                db.commit()
                if not result["items"]:
                    break
        counts = {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("message", "attachment", "translation")
        }
        status = {"last_success": datetime.now(UTC).isoformat(), **counts}
        write_private(root / "sync-status.json", json.dumps(status).encode())
        return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(args.config.read_text())
    try:
        print(json.dumps(sync(config, args.data)))
    except Exception as error:
        # Credentials, mail subjects and request URLs never appear in service logs.
        print(json.dumps({"status": "retry", "error_type": type(error).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
