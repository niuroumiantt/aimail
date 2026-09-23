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
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    sender_name: str
    api_tokens: dict[str, str]
    tasks: frozenset[str]
    port: int
    listen_host: str
    webhook_url: str
    webhook_secret: str
    db_path: Path
    poll_seconds: int
    web_dist: Path | None
    require_oa_auth: bool
    outreach_import_token: str = ""
    outreach_enabled: bool = False
    outreach_daily_cap: int = 20
    outreach_approval_proxy_key: str = ""

    @classmethod
    def from_env(cls) -> Config:
        def required(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise RuntimeError(f"缺少环境变量 {name}")
            return value

        dist = os.environ.get("WEB_DIST", "").strip()
        webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
        webhook_secret = os.environ.get("WEBHOOK_SECRET", "").strip()
        if webhook_url and not webhook_secret:
            raise RuntimeError("配了 WEBHOOK_URL 就必须配 WEBHOOK_SECRET:不签名的推送下游没法信")
        return cls(
            mailbox=required("MAILBOX"),
            imap_host=required("IMAP_HOST"),
            imap_port=int(os.environ.get("IMAP_PORT", "993")),
            imap_user=required("IMAP_USER"),
            imap_password=required("IMAP_PASSWORD"),
            imap_inbox=os.environ.get("IMAP_INBOX", "INBOX"),
            imap_sent=os.environ.get("IMAP_SENT", ""),
            smtp_host=os.environ.get("SMTP_HOST", "").strip()
            or required("IMAP_HOST").replace("imap.", "smtp.", 1),
            smtp_port=int(os.environ.get("SMTP_PORT", "465")),
            smtp_user=os.environ.get("SMTP_USER", "").strip() or required("IMAP_USER"),
            smtp_password=os.environ.get("SMTP_PASSWORD", "").strip() or required("IMAP_PASSWORD"),
            sender_name=os.environ.get("SENDER_NAME", "").strip(),
            api_tokens=parse_tokens(os.environ.get("API_TOKENS", "")),
            tasks=parse_tasks(os.environ.get("TASKS", "")),
            port=int(os.environ.get("PORT", "8900")),
            listen_host=os.environ.get("LISTEN_HOST", "127.0.0.1").strip() or "127.0.0.1",
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            db_path=Path(os.environ.get("DB_PATH", "data/mail2leads.sqlite3")),
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            web_dist=Path(dist) if dist else None,
            require_oa_auth=os.environ.get("REQUIRE_OA_AUTH", "") == "1",
            outreach_import_token=os.environ.get("OUTREACH_IMPORT_TOKEN", ""),
            outreach_enabled=os.environ.get("OUTREACH_ENABLED", "") == "1",
            outreach_daily_cap=int(os.environ.get("OUTREACH_DAILY_CAP", "20")),
            outreach_approval_proxy_key=os.environ.get("OUTREACH_APPROVAL_PROXY_KEY", ""),
        )


def parse_tokens(raw: str) -> dict[str, str]:
    """API_TOKENS="oa:长随机串,po:另一串" → {"oa": ..., "po": ...}。名字进日志,串永不进日志。"""
    tokens: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise RuntimeError(f"API_TOKENS 里的 {item[:8]}… 缺名字,格式是 名字:令牌")
        name, value = item.split(":", 1)
        if len(value) < 16:
            raise RuntimeError(f"API 令牌 {name} 太短,至少 16 个字符(openssl rand -hex 32)")
        tokens[name.strip()] = value.strip()
    return tokens


# 一个邮箱开哪些任务:read 读数(必开)、leads 提线索建议、draft 起草回信。个人邮箱通常只开 read
ALL_TASKS = frozenset({"read", "leads", "draft"})
DEFAULT_TASKS = ALL_TASKS


def parse_tasks(raw: str) -> frozenset[str]:
    """TASKS="read,leads" → {"read", "leads"}。空 = 全开;不认识的名字启动即炸。"""
    names = frozenset(n.strip() for n in raw.split(",") if n.strip())
    if not names:
        return DEFAULT_TASKS
    unknown = names - ALL_TASKS
    if unknown:
        raise RuntimeError(f"TASKS 里不认识 {sorted(unknown)};可用:{sorted(ALL_TASKS)}")
    return names | {"read"}
