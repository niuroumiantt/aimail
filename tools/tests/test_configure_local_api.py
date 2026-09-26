import stat
from unittest.mock import Mock

import pytest
from tools import configure_local_api


def test_legacy_gateway_config_is_copied_without_requesting_another_key(tmp_path, monkeypatch):
    monkeypatch.setattr(configure_local_api.Path, "home", lambda: tmp_path)
    legacy = tmp_path / ".config/mail2leads/local-api.env"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"KEEL_AI_UPSTREAM_TOKEN=secret-value\n")
    legacy.chmod(0o600)

    mock_client = Mock()
    monkeypatch.setattr(configure_local_api.httpx, "Client", mock_client)
    configure_local_api.main()

    canonical = tmp_path / ".config/aimail/local-api.env"
    assert canonical.read_bytes() == legacy.read_bytes()
    assert stat.S_IMODE(canonical.stat().st_mode) == 0o600
    assert legacy.exists()
    mock_client.assert_not_called()


def test_existing_canonical_gateway_config_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(configure_local_api.Path, "home", lambda: tmp_path)
    canonical = tmp_path / ".config/aimail/local-api.env"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("existing")

    with pytest.raises(SystemExit, match="Existing configuration preserved"):
        configure_local_api.main()

    assert canonical.read_text() == "existing"
