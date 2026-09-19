"""入口:python -m mail2leads serve | ingest | read

serve  = 起 API(含前端)+ 后台每 POLL_SECONDS 秒收一次信,来信立刻读数
ingest = 收一次信就退出,接线时用
read   = 给还没有读数的来信补读,换模型或改合同后用
"""

from __future__ import annotations

import logging
import sys
import threading
import time

from mail2leads import backends
from mail2leads.config import Config
from mail2leads.ingest.imap import ImapSource
from mail2leads.ingest.run import ingest_once
from mail2leads.store import repo
from mail2leads.store.db import connect
from mail2leads.tasks.read import read_message, unread_incoming

log = logging.getLogger("mail2leads")


def _ingest_all(config: Config, mailbox_id: int) -> None:
    conn = connect(config.db_path)
    for folder, direction in ((config.imap_inbox, "in"), (config.imap_sent, "out")):
        if not folder:
            continue
        source = ImapSource(
            config.imap_host, config.imap_port, config.imap_user, config.imap_password, folder
        )
        try:
            report = ingest_once(conn, mailbox_id, source, folder, direction, reader=_reader())
            log.info(
                "%s:拉 %d 存 %d 跳过 %d 解析失败 %d",
                folder,
                report.fetched,
                report.stored,
                report.skipped,
                report.unparsable,
            )
        finally:
            source.close()
    conn.close()


def _reader():
    """后端配好了就边收边读;没配好就只收不读,STATUS 会显示「还没有读数」。"""
    ok, why = backends.ready()
    if not ok:
        log.warning("模型后端没配好(%s),只收信不读数", why)
        return None
    return read_message


def _read_pending(config: Config, mailbox_id: int) -> None:
    conn = connect(config.db_path)
    pending = unread_incoming(conn, mailbox_id)
    log.info("待读 %d 封,后端 %s", len(pending), backends.describe())
    for pk in pending:
        status = read_message(conn, pk)
        log.info("message %s → %s", pk, status)
    conn.close()


def _poll_forever(config: Config, mailbox_id: int) -> None:
    while True:
        try:
            _ingest_all(config, mailbox_id)
        except Exception:  # noqa: BLE001 —— 收信失败只记日志,下一轮再来;服务本身不能死
            log.exception("收信失败,%d 秒后重试", config.poll_seconds)
        time.sleep(config.poll_seconds)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    command = argv[1] if len(argv) > 1 else "serve"
    config = Config.from_env()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(config.db_path)
    mailbox_id = repo.ensure_mailbox(conn, config.mailbox)

    if command == "ingest":
        conn.close()
        _ingest_all(config, mailbox_id)
        return 0
    if command == "read":
        conn.close()
        ok, why = backends.ready()
        if not ok:
            print(f"跑不了:{why}", file=sys.stderr)
            return 2
        _read_pending(config, mailbox_id)
        return 0
    if command != "serve":
        print(f"不认识的命令 {command!r};可用:serve / ingest / read", file=sys.stderr)
        return 2

    import uvicorn

    from mail2leads.api.app import create_app

    threading.Thread(
        target=_poll_forever, args=(config, mailbox_id), daemon=True, name="ingest"
    ).start()
    uvicorn.run(
        create_app(conn, mailbox_id, config.web_dist), host="0.0.0.0", port=8900, log_level="info"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
