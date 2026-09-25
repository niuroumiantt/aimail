"""Explicit personal sending identities, selected by authenticated employee email."""

import json
import os
import re
from dataclasses import dataclass

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
