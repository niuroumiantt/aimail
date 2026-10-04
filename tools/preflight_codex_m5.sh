#!/bin/bash
# Inspect the existing m5 CLI without inference, SSH or configuration changes.
set -eu

if [ "$#" -ne 0 ]; then
  echo '{"precheck":"unexpected_arguments"}'
  exit 2
fi
probe_python=""
for candidate_python in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate_python" >/dev/null 2>&1 &&
     "$candidate_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    probe_python="$candidate_python"
    break
  fi
done
[ -n "$probe_python" ] || { echo '{"precheck":"python_unavailable"}'; exit 2; }
exec "$probe_python" - <<'PY'
import dataclasses
import hashlib
import json
import os
import re
import runpy
import sys
import tempfile
from pathlib import Path

root = Path.home() / ".local/share/aimail/cli-worker/0dca357e5cd8867ba3f6262da722c210fea38748"
sources = {
    "tools/run_cli_worker.py": "f3ac0734141973ee7f25fa5e33513d7775b95f166eefc00e58c8db260b7a541d",
    "server/src/aimail/backends/cli.py": (
        "353775ac153d16a4570061d8a6beacf6214d60dbb42af81f40853e9a8a11ba0a"
    ),
    "server/src/aimail/backends/cli_bridge.py": (
        "10e14a8e4661a922f6b009d0673a66cb4e40cdedb5269a0b47d1446df2985cc8"
    ),
}
try:
    for relative, expected in sources.items():
        path = root / relative
        if (
            path.stat().st_size > 131072
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("source mismatch")
except Exception:
    print('{"precheck":"worker_source_unavailable_or_mismatched"}')
    raise SystemExit(2) from None

try:
    cli = runpy.run_path(str(root / "tools/run_cli_worker.py"))["cli"]
    cfg = dataclasses.replace(
        cli.configuration("codex_cli", model="gpt-5.4"), timeout=12, output_limit=65536
    )
except Exception:
    print('{"precheck":"worker_or_cli_configuration_unavailable"}')
    raise SystemExit(2) from None

report = {"scope": "METADATA_ONLY_NOT_INFERENCE_AUTH_VERIFICATION"}
reasons = {"start_failed", "nonzero_exit", "timeout", "output_limit", "invalid_encoding"}
# Native login status can write to stderr. Merge it only inside the bounded runner;
# neither stream, exception text nor credential content is ever printed.
driver = "import os,sys; os.dup2(1,2); os.execv(sys.argv[1],sys.argv[1:])"
try:
    with tempfile.TemporaryDirectory(prefix="aimail-model-") as cwd:

        def metadata(name, args):
            try:
                out = cli._run([sys.executable, "-c", driver, cfg.executable, *args], b"", cwd, cfg)
                report[name + "_exit"] = 0
                return out
            except Exception as exc:
                reason = getattr(exc, "reason_code", None)
                report[name + "_reason"] = (
                    reason if isinstance(reason, str) and reason in reasons else "UNAVAILABLE"
                )
                code = getattr(exc, "exit_code", None)
                report[name + "_exit"] = code if type(code) is int and -255 <= code <= 255 else None
                return ""

        version = metadata("version", ["--version"])
        match = re.search(
            r"(?m)^(?:codex-cli|Codex CLI|codex)\s+"
            r"(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?)\s*$",
            version,
        )
        report["version"] = match.group(1) if match else "UNKNOWN"
        help_text = metadata("help", ["exec", "--help"])
        report["flags"] = {
            flag: bool(
                re.search(r"(?m)^\s*(?:-[A-Za-z],\s*)?" + re.escape(flag) + r"\b", help_text)
            )
            for flag in (
                "--ignore-user-config",
                "--ignore-rules",
                "--ephemeral",
                "--output-schema",
                "--disable",
            )
        }
        auth = metadata("login", ["login", "status"])
        report["login_method"] = "UNKNOWN"
        if re.search(r"(?m)^Logged in using ChatGPT\s*$", auth):
            report["login_method"] = "CHATGPT"
        elif re.search(r"(?m)^Logged in using (?:an )?API key\b", auth):
            report["login_method"] = "API_KEY"
        elif re.search(r"(?m)^Not logged in\s*$", auth):
            report["login_method"] = "NOT_LOGGED_IN"
except Exception:
    print('{"precheck":"metadata_unavailable"}')
    raise SystemExit(2) from None

try:
    codex_dir = Path(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")).expanduser()
    report["auth_file_exists"] = (codex_dir / "auth.json").is_file()
except Exception:
    report["auth_file_exists"] = None

try:
    import tomllib

    path = codex_dir / "config.toml"
    try:
        with path.open("rb") as source:
            payload = source.read(131073)
        if len(payload) > 131072:
            raise ValueError("size limit")
        config = tomllib.loads(payload.decode("utf-8"))
        state = "TOP_LEVEL_AND_DEFAULT_PROFILE"
    except FileNotFoundError:
        config, state = {}, "NO_CONFIG_FILE"
    profile = config.get("profiles", {}).get(config.get("profile", ""), {})
    provider = profile.get("model_provider", config.get("model_provider", "openai"))
    settings = config.get("model_providers", {}).get(provider, {})
    mode = profile.get(
        "cli_auth_credentials_store", config.get("cli_auth_credentials_store", "file")
    )
    model = profile.get("model", config.get("model", ""))
    features = {**config.get("features", {}), **profile.get("features", {})}
    config_metadata = {
        "config_metadata": state,
        "auth_store_configured": "cli_auth_credentials_store" in config
        or "cli_auth_credentials_store" in profile,
        "auth_store": mode
        if isinstance(mode, str) and mode in ("file", "keyring", "auto", "ephemeral")
        else "UNKNOWN",
        "secret_auth_storage_configured": "secret_auth_storage" in features,
        "secret_auth_storage_true": features.get("secret_auth_storage") is True,
        "provider_default_bool": provider == "openai",
        "provider_base_url_configured": bool(settings.get("base_url")),
        "chatgpt_base_url_configured": bool(
            config.get("chatgpt_base_url") or profile.get("chatgpt_base_url")
        ),
        "provider_auth_configured": any(
            settings.get(k) for k in ("env_key", "http_headers", "env_http_headers")
        ),
        "model_matches_probe": model == "gpt-5.4" if model else None,
    }
    report.update(config_metadata)
except Exception:
    report["config_metadata"] = "UNAVAILABLE"
report["openai_base_url_env_set"] = bool(os.environ.get("OPENAI_BASE_URL"))
print(json.dumps(report, ensure_ascii=False))
PY
