"""Operator opt-in preserves private settings and cannot replace a symlink target."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "configure_cli_bridge", Path(__file__).parents[1] / "configure_cli_bridge.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_flag_update_preserves_other_settings_and_does_not_print_them(tmp_path, capsys):
    path = tmp_path / "app.env"
    private = 'MAIL_PASSWORD="example-secret#with-specials"\nOTHER_KEY="a=b"\n'
    path.write_text(private + "LLM_CLI_BRIDGE_ENABLED=0\nLLM_CLI_BRIDGE_ENABLED=0")
    module.configure(path, enabled=True)
    assert path.read_text() == private + "LLM_CLI_BRIDGE_ENABLED=1\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert capsys.readouterr().out == ""
    module.configure(path, enabled=False)
    assert path.read_text() == private + "LLM_CLI_BRIDGE_ENABLED=0\n"


def test_missing_or_symlink_configuration_is_never_replaced(tmp_path):
    target = tmp_path / "target.env"
    target.write_text("ORIGINAL=value")
    link = tmp_path / "link.env"
    link.symlink_to(target)
    for path in (link, tmp_path / "missing.env"):
        with pytest.raises(ValueError):
            module.configure(path, enabled=True)
    assert link.is_symlink()
    assert target.read_text() == "ORIGINAL=value"
