"""Provision a project-scoped local gateway key; never print credentials."""

import os
import shutil
import tempfile
from pathlib import Path

import httpx


def main():
    os.umask(0o077)
    destination = Path.home() / ".config/aimail/local-api.env"
    legacy = Path.home() / ".config/mail2leads/local-api.env"
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination.parent, 0o700)
    if destination.exists():
        raise SystemExit("Existing configuration preserved")
    if legacy.exists():
        fd, temporary = tempfile.mkstemp(prefix=".local-api.", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as output, legacy.open("rb") as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o600)
            os.link(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        print("Legacy private configuration copied to Aimail path; source preserved")
        return
    with httpx.Client(base_url="http://127.0.0.1:8800", timeout=10) as client:
        response = client.post(
            "/admin/keys",
            json={
                "kind": "tokens",
                "tokens": 100000,
                "label": "aimail",
                "models": ["qwen3.8:27b-mxfp8"],
            },
        )
        response.raise_for_status()
        issued = response.json()
        try:
            with destination.open("x") as output:
                output.write(
                    "KEEL_AI_UPSTREAM_PROVIDER=openapi\n"
                    "KEEL_AI_UPSTREAM_URL=http://127.0.0.1:8800/v1/chat/completions\n"
                    "KEEL_AI_UPSTREAM_MODEL=qwen3.8:27b-mxfp8\n"
                    "KEEL_AI_UPSTREAM_TOKEN=" + issued["key"] + "\n"
                )
        except Exception:
            client.delete(f"/admin/keys/{issued['id']}")
            raise
        print(f"Private configuration created; gateway key id={issued['id']}")


if __name__ == "__main__":
    main()
