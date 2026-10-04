#!/bin/bash
# Run on m5. Download and verify public pinned inputs before any trusted SSH action.
# Compatible with macOS Bash 3.2; no mail scan or login-file access.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: bash review_spark_candidate_m5.sh COMMIT40 HELPER_SHA256 TASK_SHA256" >&2
  exit 2
fi
if ! [[ "$1" =~ ^[0-9a-f]{40}$ ]] ||
   ! [[ "$2" =~ ^[0-9a-f]{64}$ ]] ||
   ! [[ "$3" =~ ^[0-9a-f]{64}$ ]]; then
  echo "Expected a pinned 40-character commit and two lowercase SHA-256 digests." >&2
  exit 2
fi

candidate_commit="$1"
helper_digest="$2"
candidate_digest="$3"
repository="https://raw.githubusercontent.com/niuroumiantt/aimail"
candidate_root="$repository/$candidate_commit"
baseline_commit="dc81766c22d8a2c3547bd14aa0e3b7d1a42ed2c6"
configure_digest="2195656780c5ff6800568c12942e0d8bb032959c596a7e496f266ebcd31b40be"
baseline_digest="0f66cd6677c249b721eeaeae2402ced92debbddbef71bd50d092a1423ce740e8"
baseline_source_digest="b012cbf9f6d2bebf1ccf23ac886a19d37db895632bbc18adaf99e7db7b88bee3"
candidate_url="$candidate_root/server/src/aimail/tasks/summarize.py"
baseline_source_url="$repository/$baseline_commit/server/src/aimail/tasks/summarize.py"
review_dir="$(mktemp -d "${TMPDIR:-/tmp}/aimail-spark-review.XXXXXX")"

cleanup() {
  rm -f "$review_dir/eval_prompt_candidate.py" "$review_dir/summarize_7.py" \
    "$review_dir/configure_cli_bridge.py" "$review_dir/baseline_5.json" \
    "$review_dir/summarize_5.py"
  rmdir "$review_dir" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

download() {
  curl -fLsS --connect-timeout 15 --max-time 30 "$1" -o "$2"
}
verify() {
  local actual
  actual="$(shasum -a 256 "$1")"
  actual="${actual%% *}"
  if [ "$actual" != "$2" ]; then
    echo "Public input checksum failed; no SSH action was performed." >&2
    exit 2
  fi
}
encode() {
  base64 < "$1" | tr -d '\r\n'
}

download "$candidate_root/tools/eval_prompt_candidate.py" "$review_dir/eval_prompt_candidate.py"
download "$candidate_url" "$review_dir/summarize_7.py"
download "$candidate_root/tools/configure_cli_bridge.py" "$review_dir/configure_cli_bridge.py"
download "$candidate_root/evals/summarize_inquiry/results/2026-10-04-spark-fast-5.json" \
  "$review_dir/baseline_5.json"
download "$baseline_source_url" "$review_dir/summarize_5.py"
verify "$review_dir/eval_prompt_candidate.py" "$helper_digest"
verify "$review_dir/summarize_7.py" "$candidate_digest"
verify "$review_dir/configure_cli_bridge.py" "$configure_digest"
verify "$review_dir/baseline_5.json" "$baseline_digest"
verify "$review_dir/summarize_5.py" "$baseline_source_digest"

candidate_base64="$(encode "$review_dir/summarize_7.py")"
baseline_base64="$(encode "$review_dir/baseline_5.json")"
baseline_source_base64="$(encode "$review_dir/summarize_5.py")"
report_prefix="/tmp/aimail-trade-eval-7-${candidate_commit:0:12}"

echo "Verified five public inputs; evaluating summarize_inquiry@7 on Spark against archived @5."
set +e
ssh -T -o BatchMode=yes -o ConnectTimeout=8 aliyun \
  sudo docker exec -i mainland-aimail-1 uv run --no-sync python -u - \
  "$candidate_url" "$candidate_digest" --source-base64 "$candidate_base64" \
  --candidate-version summarize_inquiry@7 --root /app \
  --baseline /tmp/aimail-trade-eval.json \
  --baseline-base64 "$baseline_base64" --baseline-sha256 "$baseline_digest" \
  --baseline-source-url "$baseline_source_url" \
  --baseline-source-sha256 "$baseline_source_digest" \
  --baseline-source-base64 "$baseline_source_base64" \
  --out "$report_prefix.tsv" --report-json "$report_prefix.json" \
  < "$review_dir/eval_prompt_candidate.py"
evaluation_status=$?
set -e

if [ "$evaluation_status" -eq 0 ] || [ "$evaluation_status" -eq 1 ]; then
  ssh -T -o BatchMode=yes -o ConnectTimeout=8 aliyun \
    sudo docker exec mainland-aimail-1 cat "$report_prefix.json" "$report_prefix.tsv"
else
  echo "Evaluation did not produce an accepted result; no configuration was changed." >&2
  exit "$evaluation_status"
fi
if [ "$evaluation_status" -eq 0 ]; then
  ssh -T -o BatchMode=yes -o ConnectTimeout=8 aliyun sudo python3 - \
    < "$review_dir/configure_cli_bridge.py"
else
  echo "Candidate did not pass; CLI bridge configuration was not changed." >&2
fi
exit "$evaluation_status"
