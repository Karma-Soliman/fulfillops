#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck source=scripts/lib-gitops.sh
source scripts/lib-gitops.sh

require_clean_main
require_healthy_app
require_kind_nodeport
kubectl -n fulfillops rollout status deployment/fulfillops-api --timeout=60s
ready="$(kubectl -n fulfillops get deployment fulfillops-api -o jsonpath='{.status.readyReplicas}')"
desired="$(kubectl -n fulfillops get deployment fulfillops-api -o jsonpath='{.spec.replicas}')"
if [[ "$ready" != 2 || "$desired" != 2 ]]; then
  echo "Rolling-update drill requires 2/2 API pods Ready, got ${ready:-0}/${desired:-0}." >&2
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
evidence_dir="docs/evidence/rolling-update-$stamp"
mkdir -p "$evidence_dir"
known_good="$(kubectl -n argocd get application fulfillops -o jsonpath='{.status.sync.revision}')"
before_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
capture_state "$evidence_dir" before
kubectl -n fulfillops get replicasets -l app.kubernetes.io/component=api -o wide \
  >"$evidence_dir/before-replicasets.txt"

branch="drill/rolling-$stamp"
git switch -c "$branch" main
set_release_note infra/k8s/overlays/kind/release-patch.yaml "rolling-$stamp"
git add infra/k8s/overlays/kind/release-patch.yaml
git commit -m "drill: harmless API rolling update $stamp"
pr_url="$(open_pr "$branch" "Drill: harmless API rolling update" \
  "Change the release-note pod-template annotation to \`rolling-$stamp\` to exercise the normal API rolling update.")"
printf 'Rolling-update PR: %s\n' "$pr_url"
merge_sha="$(wait_for_merge "$pr_url")"
merged_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

probe_csv="$evidence_dir/rolling_update_probe.csv"
python3 scripts/fulfillops_rollout_probe.py \
  --base-url http://localhost:8080 \
  --path /health/ready \
  --duration 30 \
  --interval 0.25 \
  --output "$probe_csv" >"$evidence_dir/probe-output.txt" 2>&1 &
probe_pid=$!
probe_exit=0
cleanup_probe() {
  if kill -0 "$probe_pid" >/dev/null 2>&1; then
    kill "$probe_pid" >/dev/null 2>&1 || true
    wait "$probe_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup_probe EXIT INT TERM

argo_refresh_and_wait "$merge_sha" 30
if wait "$probe_pid"; then
  probe_exit=0
else
  probe_exit=$?
fi
trap - EXIT INT TERM
cat "$evidence_dir/probe-output.txt"
kubectl -n fulfillops rollout status deployment/fulfillops-api --timeout=240s
argo_wait_health Healthy 180
capture_state "$evidence_dir" after
kubectl -n fulfillops get replicasets -l app.kubernetes.io/component=api -o wide \
  >"$evidence_dir/after-replicasets.txt"

after_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
sample_count="$(awk 'END {print (NR > 0 ? NR - 1 : 0)}' "$probe_csv")"
failure_count="$(awk -F, 'NR > 1 && ($2 < 200 || $2 >= 300) {count++} END {print count+0}' "$probe_csv")"
after_revision="$(kubectl -n argocd get application fulfillops -o jsonpath='{.status.sync.revision}')"
rs_before="$(awk 'NR>1 {print $1}' "$evidence_dir/before-replicasets.txt" | tr '\n' ' ')"
rs_after="$(awk 'NR>1 {print $1}' "$evidence_dir/after-replicasets.txt" | tr '\n' ' ')"
cat >"$evidence_dir/summary.md" <<EOF
# Rolling update drill

- Started: $before_time
- PR merged: $merged_at ($merge_sha)
- Completed: $after_time
- Known-good revision before drill: $known_good
- Revision after rollout: $after_revision
- API ReplicaSets before: ${rs_before:-none}
- API ReplicaSets after: ${rs_after:-none}
- Probe samples: $sample_count
- Probe failures: $failure_count (expected 0)
- Probe exit code: $probe_exit (expected 0)
- Probe CSV: $probe_csv
EOF
cp "$probe_csv" docs/rolling_update_probe.csv
printf '%s\n' "Evidence: $evidence_dir/summary.md" "Probe CSV copied to docs/rolling_update_probe.csv"
cat "$evidence_dir/summary.md"
if [[ "$probe_exit" -ne 0 || "$failure_count" -ne 0 ]]; then
  echo "Rolling-update probe recorded failures." >&2
  exit 1
fi
advance_local_main
