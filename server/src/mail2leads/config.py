"""环境变量。缺必填项就在启动时炸,不要等第一封邮件进来才发现。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    mailbox: str
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_inbox: str
    imap_sent: str
    db_path: Path
    poll_seconds: int
    web_dist: Path | None

    @classmethod
    def from_env(cls) -> Config:
        def required(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise RuntimeError(f"缺少环境变量 {name}")
            return value

        dist = os.environ.get("WEB_DIST", "").strip()
        return cls(
            mailbox=required("MAILBOX"),
            imap_host=required("IMAP_HOST"),
            imap_port=int(os.environ.get("IMAP_PORT", "993")),
            imap_user=required("IMAP_USER"),
            imap_password=required("IMAP_PASSWORD"),
            imap_inbox=os.environ.get("IMAP_INBOX", "INBOX"),
            imap_sent=os.environ.get("IMAP_SENT", ""),
            db_path=Path(os.environ.get("DB_PATH", "data/mail2leads.sqlite3")),
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            web_dist=Path(dist) if dist else None,
        )
