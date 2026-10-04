#!/usr/bin/env python3
"""Operator-only opt-in for the next deployment; never prints application settings.

Run through the existing trusted SSH connection. No provider is selected, no CLI
login is copied and the running service is not restarted by this helper.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

KEY = "LLM_CLI_BRIDGE_ENABLED"
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?LLM_CLI_BRIDGE_ENABLED\s*=")


def configure(path: Path, *, enabled: bool) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected an existing regular configuration file")
    original = path.stat()
    content = path.read_text("utf-8")
    lines = [line for line in content.splitlines(keepends=True) if not ASSIGNMENT.match(line)]
    preserved = "".join(lines)
    replacement = preserved + ("\n" if preserved and not preserved.endswith("\n") else "")
    replacement += f"{KEY}={'1' if enabled else '0'}\n"
    fd, temporary = tempfile.mkstemp(prefix=".aimail-cli-config-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            os.fchmod(target.fileno(), 0o600)
            current = os.fstat(target.fileno())
            if (current.st_uid, current.st_gid) != (original.st_uid, original.st_gid):
                os.fchown(target.fileno(), original.st_uid, original.st_gid)
            target.write(replacement)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path("/srv/aimail-deploy/.env.aimail"))
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    try:
        configure(args.env_file, enabled=not args.disable)
    except (OSError, ValueError):
        print("Configuration was not updated; check the existing file and operator permissions.")
        return 2
    print("CLI bridge setting saved for the next Aimail redeployment; no mail was analyzed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
