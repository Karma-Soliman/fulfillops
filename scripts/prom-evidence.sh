#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Save every query result with a UTC filename and print the same evidence to the terminal.
mkdir -p docs/evidence
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE="docs/evidence/prometheus-$STAMP.txt"
: > "$EVIDENCE"
echo "Prometheus evidence: $EVIDENCE"

# Forward only for this command; the process is always stopped when the script exits.
PORT_FORWARD_LOG="$(mktemp)"
kubectl -n fulfillops port-forward svc/prometheus 9090:9090 >"$PORT_FORWARD_LOG" 2>&1 &
PORT_FORWARD_PID=$!
cleanup() {
  kill "$PORT_FORWARD_PID" >/dev/null 2>&1 || true
  wait "$PORT_FORWARD_PID" >/dev/null 2>&1 || true
  rm -f "$PORT_FORWARD_LOG"
}
trap cleanup EXIT

# Wait up to thirty seconds for Prometheus readiness through the temporary forward.
READY=false
for _ in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:9090/-/ready >/dev/null 2>&1; then
    READY=true
    break
  fi
  sleep 1
done
if [[ "$READY" != true ]]; then
  echo "Prometheus did not answer /-/ready through port-forward." >&2
  cat "$PORT_FORWARD_LOG" >&2
  exit 1
fi

log() {
  printf '%s\n' "$*" | tee -a "$EVIDENCE"
}
log "UTC timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "Generating 250 catalog requests through the kind NodePort..."
for _ in $(seq 1 250); do
  curl --fail --silent --show-error http://localhost:8080/api/v1/catalog >/dev/null
done
log "Generated 250 successful catalog requests."
log "Waiting 15 seconds for scrape samples..."
sleep 15

# Query all required series and print labels plus values without an extra JSON dependency.
python3 - <<'PY' | tee -a "$EVIDENCE"
import json
from urllib.parse import urlencode
from urllib.request import urlopen

queries = [
    ("up by job and instance", "up"),
    ("sum by (job) (up)", "sum by (job) (up)"),
    (
        "request rate",
        "sum(rate(fulfillops_http_requests_total[1m]))",
    ),
    (
        "p95 HTTP latency",
        "histogram_quantile(0.95, sum by (le) (rate(fulfillops_http_request_duration_seconds_bucket[1m])))",
    ),
    (
        "worker heartbeat rate",
        "sum(rate(fulfillops_worker_heartbeats_total[1m]))",
    ),
]

for title, query in queries:
    url = "http://127.0.0.1:9090/api/v1/query?" + urlencode({"query": query})
    with urlopen(url, timeout=10) as response:
        payload = json.load(response)
    if payload.get("status") != "success":
        raise SystemExit(f"Prometheus query failed: {title}: {payload}")
    print(f"\n{title}: {query}")
    results = payload["data"]["result"]
    if not results:
        print("  (no series)")
    for result in results:
        labels = result.get("metric", {})
        label_text = ", ".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
        print(f"  {{{label_text}}} = {result['value'][1]}")
PY

log "Evidence saved to $EVIDENCE"
