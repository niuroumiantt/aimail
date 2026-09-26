"""Canonical local Aimail paths with read-only legacy fallbacks."""

from pathlib import Path


def local_gateway_config() -> Path:
    canonical = Path.home() / ".config/aimail/local-api.env"
    legacy = Path.home() / ".config/mail2leads/local-api.env"
    return canonical if canonical.exists() or not legacy.exists() else legacy


def pilot_data_directory() -> Path:
    canonical = Path.home() / ".local/share/aimail/pilot"
    legacy = Path.home() / ".local/share/mail2leads/pilot"
    return canonical if canonical.exists() or not legacy.exists() else legacy
