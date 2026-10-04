"""Bounded, opt-in re-reading of legacy inbox classifications.

Run ``python -m aimail.reclassify --mailbox sales@example.test`` to inspect.
Add ``--apply`` only when ready to spend the displayed topic budget.
Nothing in the normal server startup invokes this module.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from aimail import backends
from aimail.config import default_database_path
from aimail.store.db import connect
from aimail.tasks.read import read_message
from aimail.tasks.summarize import TASK_VERSION

MAX_LIMIT = 100


class BackendUnavailable(RuntimeError):
    """Raised before the first task attempt when no backend is configured."""


def candidates(
    conn: sqlite3.Connection, mailbox_id: int, *, retry_failed: bool = False
) -> list[sqlite3.Row]:
    """Only each visible thread's latest incoming original, in this mailbox.

    A current failed reading also counts as attempted; retrying it needs an
    explicit flag. Earlier originals, outgoing mail and delegated mailbox
    fragments are deliberately outside this bounded migration.
    """
    rows = conn.execute(
        "SELECT m.id,t.id AS thread_id,r.task_version,r.status FROM thread t "
        "JOIN message m ON m.id=(SELECT latest.id FROM message latest "
        "WHERE latest.thread_id=t.id AND latest.direction='in' "
        "ORDER BY latest.sent_at DESC,latest.id DESC LIMIT 1) "
        "LEFT JOIN message_reading r ON r.id=(SELECT id FROM message_reading "
        "WHERE source_id=m.id ORDER BY produced_at DESC,id DESC LIMIT 1) "
        "WHERE t.mailbox_id=? AND m.mailbox_id=? AND NOT EXISTS "
        "(SELECT 1 FROM thread_mail_state state WHERE state.thread_id=t.id "
        "AND state.deleted_at<>'') ORDER BY m.sent_at DESC,m.id DESC",
        (mailbox_id, mailbox_id),
    ).fetchall()
    return [
        row
        for row in rows
        if row["task_version"] != TASK_VERSION or (retry_failed and row["status"] == "failed")
    ]


def run_batch(
    conn: sqlite3.Connection,
    mailbox_id: int,
    *,
    limit: int = 20,
    apply: bool = False,
    retry_failed: bool = False,
) -> dict:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit 必须在 1 到 {MAX_LIMIT} 之间")
    pending = candidates(conn, mailbox_id, retry_failed=retry_failed)
    selected = pending[:limit]
    report = {
        "task_version": TASK_VERSION,
        "model": backends.describe(),
        "mode": "apply" if apply else "dry_run",
        "eligible": len(pending),
        "budget": limit,
        "max_task_attempts": 2 * len(selected),  # complete() allows at most one JSON repair.
        "selected": [{"source_id": row["id"], "thread_id": row["thread_id"]} for row in selected],
        "processed": 0,
        "ok": 0,
        "failed": 0,
    }
    if not apply:
        return report
    ready, reason = backends.ready()
    if not ready:
        raise BackendUnavailable(f"AI 尚未配置：{reason}")
    for row in selected:
        # A normal inbox re-read may have finished after the initial inspection.
        latest = conn.execute(
            "SELECT task_version,status FROM message_reading WHERE source_id=? "
            "ORDER BY produced_at DESC,id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        if latest and latest["task_version"] == TASK_VERSION:
            if not (retry_failed and latest["status"] == "failed"):
                continue
        status = read_message(conn, int(row["id"]), tasks=frozenset({"read"}))
        report["processed"] += 1
        report[status] += 1
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mailbox", required=True, help="精确邮箱地址，不扩展到其它邮箱")
    parser.add_argument("--db", type=Path, default=default_database_path())
    parser.add_argument("--limit", type=int, default=20, help="每次最多 100，默认 20 个话题")
    parser.add_argument("--apply", action="store_true", help="明确执行；默认只检查，不调用模型")
    parser.add_argument("--retry-failed", action="store_true", help="明确重试当前版本失败读数")
    args = parser.parse_args(argv)
    if not args.db.is_file() or not 1 <= args.limit <= MAX_LIMIT:
        parser.error("数据库必须已存在，limit 必须在 1 到 100 之间")

    # Even the inspection must not create/migrate a database.
    conn = sqlite3.connect(f"file:{quote(str(args.db.resolve()))}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id,address FROM mailbox WHERE lower(address)=?", (args.mailbox.strip().lower(),)
    ).fetchone()
    if row is None:
        conn.close()
        parser.error("没有这个精确邮箱")
    mailbox_id, address = int(row["id"]), row["address"]
    if not args.apply:
        try:
            report = run_batch(conn, mailbox_id, limit=args.limit, retry_failed=args.retry_failed)
        finally:
            conn.close()
    else:
        conn.close()
        # This lock coordinates operator batches; no SQL transaction is held
        # while the model runs, so inbox reads remain responsive.
        with args.db.with_suffix(args.db.suffix + ".reclassify.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(
                    json.dumps(
                        {"error": "已有重分类批次运行；本次没有调用模型"}, ensure_ascii=False
                    )
                )
                return 2
            worker = connect(args.db)
            try:
                report = run_batch(
                    worker, mailbox_id, limit=args.limit, apply=True, retry_failed=args.retry_failed
                )
            except BackendUnavailable:
                print(json.dumps({"error": "AI 尚未配置；本次没有调用模型"}, ensure_ascii=False))
                return 2
            finally:
                worker.close()
    print(json.dumps({"mailbox": address, **report}, ensure_ascii=False, indent=2))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
