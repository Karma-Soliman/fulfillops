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
evidence_failures=()
record_evidence_failure() {
  local step="$1" detail="$2"
  echo "Evidence step failed: $step ($detail). Continuing to write the summary." >&2
  evidence_failures+=("$step ($detail)")
}
run_evidence_step() {
  local step="$1" detail="$2" rc
  shift 2
  if "$@"; then
    return 0
  else
    rc=$?
    record_evidence_failure "$step" "exit $rc; $detail"
    return 0
  fi
}
capture_after_state() {
  capture_state "$evidence_dir" after || return $?
  kubectl -n fulfillops get replicasets -l app.kubernetes.io/component=api -o wide \
    >"$evidence_dir/after-replicasets.txt"
}
if [[ -r "$evidence_dir/probe-output.txt" ]]; then
  if ! cat "$evidence_dir/probe-output.txt"; then
    record_evidence_failure "display probe output" "could not read $evidence_dir/probe-output.txt"
  fi
else
  record_evidence_failure "probe output" "missing or unreadable $evidence_dir/probe-output.txt"
fi
run_evidence_step "Kubernetes rollout wait" "Deployment did not report completion" \
  kubectl -n fulfillops rollout status deployment/fulfillops-api --timeout=240s
run_evidence_step "Argo health wait" "expected Healthy after rollout" \
  argo_wait_health Healthy 180
run_evidence_step "after-rollout snapshots" "see command output above" capture_after_state
after_time="unavailable"
after_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || {
  record_evidence_failure "completion timestamp" "date could not provide a UTC timestamp"
  after_time="unavailable"
}

sample_count="unavailable"
if [[ -r "$probe_csv" ]]; then
  sample_count="$(awk 'END {print (NR > 0 ? NR - 1 : 0)}' "$probe_csv")" || {
    record_evidence_failure "probe sample count" "awk could not read $probe_csv"
    sample_count="unavailable"
  }
else
  record_evidence_failure "probe sample count" "missing or unreadable $probe_csv"
fi
failure_count="unavailable"
if [[ -r "$probe_csv" ]]; then
  failure_count="$(awk -F, 'NR > 1 && ($2 < 200 || $2 >= 300) {count++} END {print count+0}' "$probe_csv")" || {
    record_evidence_failure "probe failure count" "awk could not read $probe_csv"
    failure_count="unavailable"
  }
else
  record_evidence_failure "probe failure count" "missing or unreadable $probe_csv"
fi
after_revision="unavailable"
after_revision="$(kubectl -n argocd get application fulfillops \
  -o jsonpath='{.status.sync.revision}')" || {
  record_evidence_failure "Argo revision capture" "kubectl could not read the Application revision"
  after_revision="unavailable"
}
rs_before="unavailable"
if [[ -r "$evidence_dir/before-replicasets.txt" ]]; then
  rs_before="$(awk 'NR>1 {print $1}' "$evidence_dir/before-replicasets.txt" | tr '\n' ' ')" || {
    record_evidence_failure "before ReplicaSet summary" "could not parse before-replicasets.txt"
    rs_before="unavailable"
  }
else
  record_evidence_failure "before ReplicaSet summary" "missing before-replicasets.txt"
fi
rs_after="unavailable"
if [[ -r "$evidence_dir/after-replicasets.txt" ]]; then
  rs_after="$(awk 'NR>1 {print $1}' "$evidence_dir/after-replicasets.txt" | tr '\n' ' ')" || {
    record_evidence_failure "after ReplicaSet summary" "could not parse after-replicasets.txt"
    rs_after="unavailable"
  }
else
  record_evidence_failure "after ReplicaSet summary" "missing after-replicasets.txt"
fi
csv_copy_status="not copied"
if cp "$probe_csv" docs/rolling_update_probe.csv; then
  csv_copy_status="copied to docs/rolling_update_probe.csv"
else
  record_evidence_failure "CSV copy" "could not copy $probe_csv to docs/rolling_update_probe.csv"
fi
if ! cat >"$evidence_dir/summary.md" <<EOF
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
- Probe CSV copy: $csv_copy_status
- Evidence step failures: ${evidence_failures[*]:-none}
EOF
then
  echo "Failed to write rolling-update summary: $evidence_dir/summary.md" >&2
  exit 1
fi
printf '%s\n' "Evidence: $evidence_dir/summary.md" "Probe CSV $csv_copy_status"
if ! cat "$evidence_dir/summary.md"; then
  echo "Failed to display rolling-update summary: $evidence_dir/summary.md" >&2
  exit 1
fi
if [[ "$probe_exit" -ne 0 || "$failure_count" != 0 || ${#evidence_failures[@]} -gt 0 ]]; then
  echo "Rolling-update probe recorded failures." >&2
  exit 1
fi
advance_local_main
