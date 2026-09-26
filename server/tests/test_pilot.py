from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aimail.pilot import bounded_raw, read_env, recent_uids


def test_model_canary_records_usage_without_mail_content(tmp_path, monkeypatch):
    import json
    import sqlite3
    import sys

    from aimail.backends import pilot

    directory = tmp_path / ".local/share/aimail/pilot"
    directory.mkdir(parents=True)
    conn = sqlite3.connect(directory / "mailbox.sqlite3")
    conn.execute("CREATE TABLE message (id, subject, body_new, body_quoted, sent_at)")
    conn.execute("INSERT INTO message VALUES (1, 'private subject', '48 units', '', '2026')")
    conn.commit()
    conn.close()
    cfg = tmp_path / "config.env"
    cfg.write_text(
        "KEEL_AI_UPSTREAM_PROVIDER=ollama\nKEEL_AI_UPSTREAM_MODEL=test\n"
        "KEEL_AI_UPSTREAM_URL=http://127.0.0.1:11434/v1/chat/completions\n"
    )
    cfg.chmod(0o600)
    monkeypatch.setattr(pilot.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["pilot", "--config", str(cfg)])
    summary = {
        "is_inquiry": True,
        "detected_language": "en",
        "summary_zh": "48 units",
        "summary_en": "48 units",
        "facts": ["48 units"],
        "quoted_numbers": ["48"],
    }
    response = Mock(status_code=200)
    response.json.return_value = {
        "model": "test",
        "usage": {"prompt_tokens": 50},
        "choices": [{"message": {"content": json.dumps(summary)}}],
    }
    monkeypatch.setattr(pilot.httpx, "post", Mock(return_value=response))
    assert pilot.main() == 0
    event = json.loads((directory / "model-calls.jsonl").read_text())
    assert event["usage"]["completion_tokens"] is None
    assert event["cost"] is None
    assert event["status"] == "validated_structure"
    assert "private subject" not in json.dumps(event)
    assert json.loads((directory / "latest-reading.json").read_text())["source_id"] == 1


def test_pilot_selects_latest_bounded_uids():
    source = SimpleNamespace(conn=Mock())
    source.conn.uid.return_value = ("OK", [b"8 2 5 8 9"])
    assert recent_uids(source, 30, 2) == [8, 9]
    assert source.conn.uid.call_args.args[:3] == ("SEARCH", None, "SINCE")
    with pytest.raises(ValueError):
        recent_uids(source, 31, 2)


def test_pilot_refuses_large_mail_before_fetch():
    source = SimpleNamespace(conn=Mock(), fetch_raw=Mock())
    source.conn.uid.return_value = ("OK", [b"1 (RFC822.SIZE 3000000)"])
    assert bounded_raw(source, 1) is None
    source.fetch_raw.assert_not_called()


def test_pilot_parses_config_without_shell_execution(tmp_path):
    path = tmp_path / "private.env"
    path.write_text('KEY="$(touch forbidden)"\n')
    path.chmod(0o600)
    assert read_env(path)["KEY"] == "$(touch forbidden)"
    path.chmod(0o644)
    with pytest.raises(ValueError):
        read_env(path)
