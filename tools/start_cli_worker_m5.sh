#!/bin/bash
# Run on m5: use its existing CLI logins and trusted aliyun SSH alias.
set -euo pipefail
umask 077

if [ "$#" -ne 1 ] && [ "$#" -ne 2 ] && [ "$#" -ne 3 ]; then
  echo "Usage: bash start_cli_worker_m5.sh PINNED_COMMIT40 [--check-only | --codex-only | --probe-only codex_cli|claude_code_cli]" >&2
  exit 2
fi
if ! [[ "$1" =~ ^[0-9a-f]{40}$ ]] ||
   { [ "$#" -eq 2 ] && [ "$2" != "--codex-only" ] && [ "$2" != "--check-only" ]; } ||
   { [ "$#" -eq 3 ] && { [ "$2" != "--probe-only" ] ||
      { [ "$3" != "codex_cli" ] && [ "$3" != "claude_code_cli" ]; }; }; }; then
  echo "Invalid pinned commit or worker mode; no model was called." >&2
  exit 2
fi
worker_commit="$1"
worker_python=""
for candidate_python in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate_python" >/dev/null 2>&1 &&
     "$candidate_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    worker_python="$candidate_python"
    break
  fi
done
if [ -z "$worker_python" ]; then
  echo "Python 3.10 or newer is required on m5; no model was called." >&2
  exit 2
fi

worker_dir="$HOME/.local/share/aimail/cli-worker/$worker_commit"
repository="https://raw.githubusercontent.com/niuroumiantt/aimail/$worker_commit"
mkdir -p "$worker_dir/tools" "$worker_dir/server/src/aimail/backends"
for relative_file in tools/run_cli_worker.py tools/configure_cli_bridge.py \
    server/src/aimail/backends/cli.py server/src/aimail/backends/cli_bridge.py; do
  curl -fLsS --connect-timeout 15 --max-time 30 "$repository/$relative_file" \
    -o "$worker_dir/$relative_file"
done
printf '%s  %s\n' \
  '3baa24d19b685ced6d8870b8770618fb54006ee9deb7fa9dd7d1c88cf47ab2dd' "$worker_dir/tools/run_cli_worker.py" \
  '2195656780c5ff6800568c12942e0d8bb032959c596a7e496f266ebcd31b40be' "$worker_dir/tools/configure_cli_bridge.py" \
  '6bd80c63cb82a6c119053fd94974079b62b8cdb7c740734eeb027cd3ead196f5' "$worker_dir/server/src/aimail/backends/cli.py" \
  '10e14a8e4661a922f6b009d0673a66cb4e40cdedb5269a0b47d1446df2985cc8' "$worker_dir/server/src/aimail/backends/cli_bridge.py" |
  shasum -a 256 -c -

if [ "$#" -eq 2 ] && [ "$2" = "--check-only" ]; then
  # Only verify the existing bridge through SSH, without reading CLI configuration,
  # calling a model, registering a workstation or changing the server runtime.
  exec "$worker_python" "$worker_dir/tools/run_cli_worker.py" \
    --ssh-host aliyun --ssh-sudo --container mainland-aimail-1 \
    --check-only --ssh-check-timeout 60
fi

if [ "$#" -eq 3 ]; then
  # The bridge is already enabled: diagnose one local CLI without rewriting server
  # configuration, recreating its container, registering or claiming a mail job.
  exec "$worker_python" "$worker_dir/tools/run_cli_worker.py" \
    --ssh-host aliyun --ssh-sudo --container mainland-aimail-1 \
    --ssh-check-timeout 60 --codex-from-config --claude-model sonnet --probe-only --backend "$3"
fi

if [ "$#" -eq 2 ]; then
  # The existing bridge is enabled. One successful Codex probe continues directly
  # to registration and serving, without server configuration or container changes.
  exec "$worker_python" "$worker_dir/tools/run_cli_worker.py" \
    --ssh-host aliyun --ssh-sudo --container mainland-aimail-1 \
    --ssh-check-timeout 60 --codex-from-config --backend codex_cli
fi

ssh -T -o BatchMode=yes -o ConnectTimeout=8 aliyun sudo -n python3 - \
  < "$worker_dir/tools/configure_cli_bridge.py"

# Reuse the host's existing deployer and lock. Reload only the recorded local
# Aimail image when needed; do not download an image or touch another service.
configuration_source=$(base64 < "$worker_dir/tools/configure_cli_bridge.py" | tr -d '\r\n')
ssh -T -o BatchMode=yes -o ConnectTimeout=8 aliyun sudo -n python3 - "$configuration_source" <<'PY'
import base64
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

configuration_source = base64.b64decode(sys.argv[1], validate=True)
if hashlib.sha256(configuration_source).hexdigest() != (
    "2195656780c5ff6800568c12942e0d8bb032959c596a7e496f266ebcd31b40be"
):
    raise SystemExit("Configuration tool checksum failed; no local model was called.")
configuration = {"__name__": "_verified_aimail_configuration"}
exec(compile(configuration_source, "<verified Aimail configuration>", "exec"), configuration)

spec = importlib.util.spec_from_file_location(
    "_aimail_cli_runtime", Path("/srv/aimail-deploy/deploy.py")
)
if spec is None or spec.loader is None:
    raise SystemExit("Aimail deployer is unavailable; no local model was called.")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
deployer = module.Deploy()
recreated = False
compose_arguments = (
    "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "aimail"
)
try:
    deployer.acquire_lock()
except (RuntimeError, OSError):
    raise SystemExit(
        "Cannot acquire Aimail deployment lock. Bridge setting is saved; rerun after deployment finishes."
    )

try:
    state = deployer.state_data()
    if not state or not re.fullmatch(r"[0-9a-f]{40}", state.get("source_sha", "")):
        raise RuntimeError("invalid runtime")
    if state.get("tag") != "aimail-" + state["source_sha"]:
        raise RuntimeError("invalid runtime")
    deployer.verify_runtime()
    container = deployer.container_for_service("aimail")
    flag_command = [
        "docker", "exec", container, "python", "-c",
        'import os; print("1" if os.environ.get("LLM_CLI_BRIDGE_ENABLED") == "1" else "0")',
    ]
    if deployer.command(flag_command).strip() != "1":
        local_image = json.loads(deployer.command(["docker", "image", "inspect", "aimail:" + state["tag"]]))
        if len(local_image) != 1 or local_image[0].get("Id") != state.get("image_id"):
            raise RuntimeError("recorded image unavailable")
        labels = local_image[0].get("Config", {}).get("Labels") or {}
        if labels.get("org.opencontainers.image.revision") != state["source_sha"]:
            raise RuntimeError("recorded image source differs")
        # Prove this recorded image has the bridge before recreating its container.
        deployer.command([
            "docker", "exec", container, "uv", "run", "--no-sync", "python", "-c",
            "from aimail.backends import cli_bridge; print(type(cli_bridge.enabled()) is bool)",
        ])
        print("Reloading CLI setting in the recorded Aimail image...", flush=True)
        recreated = True
        deployer.compose(state["tag"], *compose_arguments)
        if not deployer.wait_healthy(state):
            raise RuntimeError("health check failed")
        container = deployer.container_for_service("aimail")
        flag_command[2] = container
    if deployer.command(flag_command).strip() != "1":
        raise RuntimeError("runtime flag did not reload")
    deployer.verify_runtime()
    print("Aimail healthy; CLI bridge enabled; source=" + state["source_sha"], flush=True)
except Exception:
    if recreated:
        try:
            configuration["configure"](Path("/srv/aimail-deploy/.env.aimail"), enabled=False)
            deployer.compose(state["tag"], *compose_arguments)
            if not deployer.wait_healthy(state):
                raise RuntimeError("recovery health failed")
            flag_command[2] = deployer.container_for_service("aimail")
            if deployer.command(flag_command).strip() != "0":
                raise RuntimeError("recovery flag differs")
            deployer.verify_runtime()
        except Exception:
            raise SystemExit("CLI activation and recovery failed; check Aimail health. No local model was called.")
        raise SystemExit("CLI activation failed; the previous disabled runtime was restored. No local model was called.")
    raise SystemExit("CLI runtime verification failed; no local model was called. Check Aimail health.")
finally:
    deployer.release_lock()
PY

exec "$worker_python" "$worker_dir/tools/run_cli_worker.py" \
  --ssh-host aliyun --ssh-sudo --container mainland-aimail-1 \
  --ssh-check-timeout 60 --codex-from-config --claude-model sonnet
