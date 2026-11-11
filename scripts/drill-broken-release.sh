#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck source=scripts/lib-gitops.sh
source scripts/lib-gitops.sh

require_clean_main
require_healthy_app
kubectl -n fulfillops rollout status deployment/fulfillops-api --timeout=60s
ready="$(kubectl -n fulfillops get deployment fulfillops-api -o jsonpath='{.status.readyReplicas}')"
desired="$(kubectl -n fulfillops get deployment fulfillops-api -o jsonpath='{.spec.replicas}')"
if [[ "$ready" != 2 || "$desired" != 2 ]]; then
  echo "Broken-release drill requires 2/2 API pods Ready, got ${ready:-0}/${desired:-0}." >&2
  exit 1
fi
curl --fail --silent --show-error --max-time 3 http://localhost:8080/health/ready >/dev/null

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
evidence_dir="docs/evidence/broken-release-$stamp"
mkdir -p "$evidence_dir"
known_good="$(kubectl -n argocd get application fulfillops -o jsonpath='{.status.sync.revision}')"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
capture_state "$evidence_dir" before
# These single-quoted commands are evaluated inside the postgres pod so its secret-backed
# POSTGRES_USER and POSTGRES_DB environment variables are used without printing credentials.
# shellcheck disable=SC2016
orders_before="$(kubectl -n fulfillops exec postgres-0 -- sh -ec \
  'relation=$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT to_regclass('\''public.orders'\'')"); if [ -z "$relation" ]; then printf SKIP; else psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT count(*) FROM public.orders"; fi')"
printf 'orders count before: %s\n' "$orders_before" >"$evidence_dir/orders-count.txt"

availability_log="$evidence_dir/availability.log"
: >"$availability_log"
availability_loop() {
  while true; do
    local now code
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
      --max-time 2 http://localhost:8080/health/ready)"; then
      :
    else
      code=000
    fi
    printf '%s %s\n' "$now" "$code" >>"$availability_log"
    sleep 1
  done
}
availability_loop &
availability_pid=$!
stop_availability() {
  if kill -0 "$availability_pid" >/dev/null 2>&1; then
    kill "$availability_pid" >/dev/null 2>&1 || true
    wait "$availability_pid" >/dev/null 2>&1 || true
  fi
}
trap stop_availability EXIT INT TERM

bad_branch="drill/broken-$stamp"
git switch -c "$bad_branch" main
set_release_note infra/k8s/overlays/kind/release-patch.yaml "broken-$stamp"
set_readiness_path infra/k8s/overlays/kind/release-patch.yaml /health/broken
git add infra/k8s/overlays/kind/release-patch.yaml
git commit -m "drill: introduce broken API readiness probe $stamp"
bad_pr="$(open_pr "$bad_branch" "Drill: broken API readiness probe" \
  "Deliberately set the API readiness path to /health/broken to prove Kubernetes halts an unavailable rolling update. This is a temporary drill revision and will be reverted through a second pull request.")"
printf 'Broken-release PR: %s\n' "$bad_pr"
bad_merge="$(wait_for_merge "$bad_pr")"
bad_merged_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
argo_refresh_and_wait "$bad_merge" 90

halted=false
for elapsed in $(seq 0 10 240); do
  reason="$(kubectl -n fulfillops get deployment fulfillops-api \
    -o jsonpath='{range .status.conditions[?(@.type=="Progressing")]}{.reason}{end}')"
  argo_health="$(kubectl -n argocd get application fulfillops \
    -o jsonpath='{.status.health.status}')"
  printf '%s elapsed=%ss progressing=%s argo_health=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$elapsed" "${reason:-Unknown}" "${argo_health:-Unknown}"
  if [[ "$reason" == ProgressDeadlineExceeded && "$argo_health" == Degraded ]]; then
    halted=true
    break
  fi
  if [[ "$elapsed" != 240 ]]; then sleep 10; fi
done
if [[ "$halted" != true ]]; then
  capture_state "$evidence_dir" halted-timeout
  echo "Deployment did not reach ProgressDeadlineExceeded with Argo Degraded within 4 minutes." >&2
  exit 1
fi
halted_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
capture_state "$evidence_dir" halted

revert_branch="drill/revert-$stamp"
git fetch --quiet origin main
git switch -c "$revert_branch" "$bad_merge"
parent_line="$(git rev-list --parents -n 1 "$bad_merge")"
parent_count="$(wc -w <<< "$parent_line" | tr -d ' ')"
if [[ "$parent_count" -gt 2 ]]; then
  git revert --no-edit -m 1 "$bad_merge"
else
  git revert --no-edit "$bad_merge"
fi
revert_pr="$(open_pr "$revert_branch" "Recovery: revert broken readiness drill" \
  "Revert the deliberately broken readiness-probe revision. The last known-good configuration is restored; no schema migration was involved.")"
printf 'Recovery PR: %s\n' "$revert_pr"
recovery_sha="$(wait_for_merge "$revert_pr")"
revert_merged_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
argo_refresh_and_wait "$recovery_sha" 180
argo_wait_health Healthy 180
kubectl -n fulfillops rollout status deployment/fulfillops-api --timeout=240s
capture_state "$evidence_dir" recovered
healthy_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# shellcheck disable=SC2016
orders_after="$(kubectl -n fulfillops exec postgres-0 -- sh -ec \
  'relation=$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT to_regclass('\''public.orders'\'')"); if [ -z "$relation" ]; then printf SKIP; else psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT count(*) FROM public.orders"; fi')"
printf 'orders count after: %s\n' "$orders_after" >>"$evidence_dir/orders-count.txt"
stop_availability
trap - EXIT INT TERM

availability_total="$(wc -l < "$availability_log" | tr -d ' ')"
availability_failures="$(awk '$2 !~ /^2[0-9][0-9]$/ {count++} END {print count+0}' "$availability_log")"
advance_local_main
git diff "$known_good" HEAD -- infra/k8s >"$evidence_dir/known-good-manifest-diff.txt"
if [[ -s "$evidence_dir/known-good-manifest-diff.txt" ]]; then
  echo "Final infra/k8s differs from known-good revision $known_good:" >&2
  cat "$evidence_dir/known-good-manifest-diff.txt" >&2
  exit 1
fi

cat >"$evidence_dir/summary.md" <<EOF
# Broken release and Git revert drill

- Drill started: $started_at
- Bad revision merged: $bad_merged_at ($bad_merge)
- Halt detected: $halted_at
- Revert merged: $revert_merged_at ($recovery_sha)
- Argo Healthy again: $healthy_at
- Known-good revision: $known_good
- Bad revision: $bad_merge
- Recovery revision: $recovery_sha
- Deployment halted because the API readiness probe failed at /health/broken. With maxUnavailable 0, the old ready replicas stayed available; ProgressDeadlineExceeded stopped the rollout.
- Availability samples: $availability_total
- Availability failures: $availability_failures (expected 0)
- Orders count before/after: $orders_before / $orders_after (SKIP means the stub has no orders table)
- Manifest diff against known-good: empty; see known-good-manifest-diff.txt.

## Rollback versus fix-forward

The Git revert was chosen because a known-good revision exists, the correct fix is not yet known, and this drill made no schema migration. Reverting restores the reviewed manifest state through the normal PR and Argo CD path.
EOF
printf 'Recovery commit manifests match known-good (empty diff):\n'
git diff "$known_good" HEAD -- infra/k8s
echo '(empty)'
printf 'Availability samples=%s failures=%s\n' "$availability_total" "$availability_failures"
printf 'Evidence: %s\n' "$evidence_dir/summary.md"
cat "$evidence_dir/summary.md"
if [[ "$availability_failures" -ne 0 ]]; then
  echo "Availability probe recorded failures." >&2
  exit 1
fi
if [[ "$orders_before" != SKIP && "$orders_before" != "$orders_after" ]]; then
  echo "Committed orders count changed during the broken-release drill." >&2
  exit 1
fi
