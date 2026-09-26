from aimail.paths import local_gateway_config, pilot_data_directory


def test_local_paths_default_to_aimail(tmp_path, monkeypatch):
    monkeypatch.setattr("aimail.paths.Path.home", lambda: tmp_path)
    assert local_gateway_config() == tmp_path / ".config/aimail/local-api.env"
    assert pilot_data_directory() == tmp_path / ".local/share/aimail/pilot"


def test_local_paths_keep_existing_legacy_data_until_migrated(tmp_path, monkeypatch):
    monkeypatch.setattr("aimail.paths.Path.home", lambda: tmp_path)
    legacy_config = tmp_path / ".config/mail2leads/local-api.env"
    legacy_data = tmp_path / ".local/share/mail2leads/pilot"
    legacy_config.parent.mkdir(parents=True)
    legacy_config.write_text("private")
    legacy_data.mkdir(parents=True)

    assert local_gateway_config() == legacy_config
    assert pilot_data_directory() == legacy_data


def test_canonical_paths_win_when_both_names_exist(tmp_path, monkeypatch):
    monkeypatch.setattr("aimail.paths.Path.home", lambda: tmp_path)
    canonical_config = tmp_path / ".config/aimail/local-api.env"
    canonical_data = tmp_path / ".local/share/aimail/pilot"
    canonical_config.parent.mkdir(parents=True)
    canonical_config.write_text("private")
    canonical_data.mkdir(parents=True)
    (tmp_path / ".config/mail2leads").mkdir(parents=True)
    (tmp_path / ".config/mail2leads/local-api.env").write_text("legacy")
    (tmp_path / ".local/share/mail2leads/pilot").mkdir(parents=True)

    assert local_gateway_config() == canonical_config
    assert pilot_data_directory() == canonical_data
