"""IMAP 来源。真连接只在这里;测试用 FakeSource 走同一个协议。

imaplib.IMAP4_SSL 默认**不校验证书**。这里显式用 ssl.create_default_context(),
校验证书也校验主机名——邮箱密码走的就是这条连接,不能裸奔。
"""

from __future__ import annotations

import imaplib
import ssl
from typing import Protocol


class Source(Protocol):
    def uid_validity(self) -> int: ...
    def new_uids(self, since_uid: int) -> list[int]: ...
    def fetch_raw(self, uid: int) -> bytes: ...


def make_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


class ImapSource:
    def __init__(self, host: str, port: int, user: str, password: str, folder: str) -> None:
        self.conn = imaplib.IMAP4_SSL(host, port, ssl_context=make_ssl_context(), timeout=30)
        self.conn.login(user, password)
        status, _ = self.conn.select(self._quote(folder), readonly=True)
        if status != "OK":
            raise RuntimeError(f"选不中 IMAP 文件夹 {folder!r}")

    @staticmethod
    def _quote(folder: str) -> str:
        return '"' + folder.replace('"', '\\"') + '"'

    def uid_validity(self) -> int:
        values = self.conn.response("UIDVALIDITY")[1]
        return int(values[0]) if values and values[0] else 0

    def new_uids(self, since_uid: int) -> list[int]:
        # IMAP 的 n:* 在 n 超过最大 UID 时会返回最大那一封,所以拿回来再按 > since 过滤
        status, data = self.conn.uid("SEARCH", None, f"UID {since_uid + 1}:*")
        if status != "OK" or not data or not data[0]:
            return []
        return [u for u in (int(x) for x in data[0].split()) if u > since_uid]

    def fetch_raw(self, uid: int) -> bytes:
        status, data = self.conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if status != "OK" or not data:
            raise RuntimeError(f"拉不到 UID {uid}")
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                return item[1]
        raise RuntimeError(f"UID {uid} 的回包里没有正文")

    def close(self) -> None:
        try:
            self.conn.logout()
        except (OSError, imaplib.IMAP4.error):
            pass
