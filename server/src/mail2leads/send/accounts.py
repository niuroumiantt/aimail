"""Explicit personal sending identities, selected by authenticated employee email."""

import json
import os
import re
from dataclasses import dataclass, replace

from mail2leads.config import Config
from mail2leads.send import SmtpTransport, Transport, validate_sender


@dataclass(frozen=True)
class SendingAccount:
    address: str
    display_name: str
    transport: Transport


def from_env(environ=None) -> dict[str, SendingAccount]:
    """SENDING_ACCOUNTS contains metadata and password env names, never passwords."""
    env = os.environ if environ is None else environ
    try:
        entries = json.loads(env.get("SENDING_ACCOUNTS", "[]"))
        if not isinstance(entries, list):
            raise ValueError
        accounts = {}
        for entry in entries:
            address = entry["address"].strip().lower()
            if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", address):
                raise ValueError
            validate_sender(address)
            if address in accounts:
                raise ValueError
            reference = entry["password_env"]
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", reference):
                raise ValueError
            password = env.get(reference, "")
            if not password or not entry["host"]:
                raise ValueError
            port = int(entry.get("port", 465))
            if not 1 <= port <= 65535:
                raise ValueError
            accounts[address] = SendingAccount(
                address,
                entry.get("display_name", ""),
                SmtpTransport(entry["host"], port, address, password),
            )
        return accounts
    except (ValueError, KeyError, TypeError, AttributeError, PermissionError):
        raise ValueError("个人发件账号配置无效：检查地址、服务器及密码环境变量引用") from None


def receiving_configs(base: Config, environ=None) -> tuple[Config, ...]:
    """Only explicitly configured personal inboxes can participate in scheduled sends."""
    env = os.environ if environ is None else environ
    accounts = from_env(env)
    try:
        result = []
        for entry in json.loads(env.get("SENDING_ACCOUNTS", "[]")):
            address = entry["address"].strip().lower()
            if not entry.get("imap_host"):
                continue  # Reply-only identity; no automatic sequence scheduler.
            if address == base.mailbox or address not in base.followup_members:
                raise ValueError
            reference = entry["imap_password_env"]
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", reference) or not env.get(reference):
                raise ValueError
            inbox = entry.get("imap_inbox", "INBOX").strip()
            port = int(entry.get("imap_port", 993))
            if not inbox or not 1 <= port <= 65535:
                raise ValueError
            account = accounts[address]
            smtp = account.transport
            result.append(
                replace(
                    base,
                    mailbox=address,
                    imap_user=address,
                    imap_host=entry["imap_host"],
                    imap_password=env[reference],
                    imap_port=port,
                    imap_inbox=inbox,
                    imap_sent=entry.get("imap_sent", ""),
                    sender_name=account.display_name,
                    smtp_host=smtp.host,
                    smtp_port=smtp.port,
                    smtp_user=address,
                    smtp_password=smtp.password,
                )
            )
        return tuple(result)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("个人收信配置无效：检查登记员工、IMAP 服务器和密码环境变量引用") from None
