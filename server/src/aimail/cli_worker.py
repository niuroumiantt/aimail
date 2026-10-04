"""Fixed SSH operator protocol for the opt-in local CLI bridge (no network listener)."""

from __future__ import annotations

import argparse
import json
import sys

from aimail.backends import cli_bridge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("heartbeat", "claim", "finish"))
    args = parser.parse_args(argv)
    try:
        _, input_limit, output_limit = cli_bridge._limits()
        limit = 6 * max(input_limit, output_limit) + 65536
        raw = sys.stdin.buffer.read(limit + 1)
        if len(raw) > limit:
            raise cli_bridge.BridgeError("invalid_request")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise cli_bridge.BridgeError("invalid_request")
        if args.operation == "heartbeat":
            result = cli_bridge.heartbeat(
                payload.get("worker_id"),
                payload.get("capabilities"),
                payload.get("lease_seconds", cli_bridge.WORKER_TTL),
            )
        elif args.operation == "claim":
            result = cli_bridge.claim(payload.get("worker_id"))
        else:
            result = cli_bridge.finish(
                payload.get("worker_id"),
                payload.get("id"),
                payload.get("nonce"),
                payload.get("lease_token"),
                payload.get("output"),
                payload.get("error"),
            )
    except cli_bridge.BridgeError as exc:
        result = {"ok": False, "error": str(exc)}
    except (ValueError, TypeError, OSError):
        result = {"ok": False, "error": "invalid_request"}
    # Only this explicit SSH operator may see a claimed job's task text. All other
    # responses contain safe metadata/codes. No stderr logging or mailbox query.
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
