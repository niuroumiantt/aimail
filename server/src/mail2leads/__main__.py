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
from mail2leads.send import SmtpTransport
from mail2leads.store import outbox, repo
from mail2leads.store.db import connect
from mail2leads.tasks.read import read_message, unread_incoming

log = logging.getLogger("mail2leads")
ingest_lock = threading.Lock()


def _ingest_all(config: Config, mailbox_id: int) -> None:
    # 定时任务和人工点击共用锁，避免同一个邮箱同时跑两次 IMAP 同步。
    with ingest_lock:
        conn = connect(config.db_path)
        try:
            for folder, direction in ((config.imap_inbox, "in"), (config.imap_sent, "out")):
                if not folder:
                    continue
                source = ImapSource(
                    config.imap_host, config.imap_port, config.imap_user, config.imap_password, folder
                )
                try:
                    report = ingest_once(
                        conn, mailbox_id, source, folder, direction, reader=_reader(config)
                    )
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
        finally:
            conn.close()


def _reader(config: Config):
    """后端配好了就边收边读;没配好就只收不读,STATUS 会显示「还没有读数」。"""
    ok, why = backends.ready()
    if not ok:
        log.warning("模型后端没配好(%s),只收信不读数", why)
        return None
    return lambda conn, pk: read_message(conn, pk, tasks=config.tasks)


def _read_pending(config: Config, mailbox_id: int) -> None:
    conn = connect(config.db_path)
    pending = unread_incoming(conn, mailbox_id)
    log.info("待读 %d 封,后端 %s", len(pending), backends.describe())
    for pk in pending:
        status = read_message(conn, pk, tasks=config.tasks)
        log.info("message %s → %s", pk, status)
    conn.close()


def _deliver_once(config: Config, mailbox_id: int) -> tuple[int, int]:
    conn = connect(config.db_path)
    try:
        result = outbox.deliver_pending(
            conn, mailbox_id, outbox.HttpPoster(config.webhook_url), config.webhook_secret
        )
    finally:
        conn.close()
    return result


def _deliver_forever(config: Config, mailbox_id: int) -> None:
    """推送线索事件到 WEBHOOK_URL。失败按退避重试,永不丢;送没送到 /api/outbox 看得见。"""
    while True:
        try:
            sent, failed = _deliver_once(config, mailbox_id)
            if sent or failed:
                log.info("推送:送到 %d,失败 %d", sent, failed)
        except Exception:  # noqa: BLE001 —— 推送失败只记日志,服务本身不能死
            log.exception("推送失败")
        time.sleep(30)


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
    if command == "deliver":
        conn.close()
        if not config.webhook_url:
            print("没配 WEBHOOK_URL,没有可推的地方", file=sys.stderr)
            return 2
        sent, failed = _deliver_once(config, mailbox_id)
        print(f"送到 {sent},失败 {failed}")
        return 0 if not failed else 1
    if command != "serve":
        print(f"不认识的命令 {command!r};可用:serve / ingest / read / deliver", file=sys.stderr)
        return 2

    import uvicorn

    from mail2leads.api.app import create_app

    threading.Thread(
        target=_poll_forever, args=(config, mailbox_id), daemon=True, name="ingest"
    ).start()
    if config.webhook_url:
        threading.Thread(
            target=_deliver_forever, args=(config, mailbox_id), daemon=True, name="deliver"
        ).start()
    # 发信的口只在这里接上:后台线程没有请求,拿不到令牌,也就发不了(宪法第二条)
    transport = SmtpTransport(
        config.smtp_host, config.smtp_port, config.smtp_user, config.smtp_password
    )
    app = create_app(
        conn,
        mailbox_id,
        config.web_dist,
        sender=config.mailbox,
        sender_name=config.sender_name,
        transport=transport,
        api_tokens=config.api_tokens,
        webhook_configured=bool(config.webhook_url),
        tasks=config.tasks,
        display_name=config.sender_name,
        sync_mailbox=lambda: _ingest_all(config, mailbox_id),
        require_oa_auth=config.require_oa_auth,
    )
    uvicorn.run(app, host=config.listen_host, port=config.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
