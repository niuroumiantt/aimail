"""IMAP 连接必须校验证书和主机名。imaplib 默认不校验——这条用例守着我们没退回默认。"""

from __future__ import annotations

import ssl

from aimail.ingest.imap import make_ssl_context


def test_ssl_context_verifies_certificate_and_hostname():
    ctx = make_ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
