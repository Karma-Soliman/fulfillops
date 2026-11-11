#!/usr/bin/env bash

# Requires callers to enable strict mode and run from somewhere inside the repository.
GITOPS_ROOT="$(git rev-parse --show-toplevel)"

require_clean_main() {
  local branch local_sha remote_sha entry entry_status entry_path dirty=0
  branch="$(git -C "$GITOPS_ROOT" branch --show-current)"
  if [[ "$branch" != main ]]; then
    echo "Expected branch main, currently on '$branch'." >&2
    return 1
  fi

  # Drill evidence is expected to remain untracked between the two drills; all source changes
  # and untracked files outside these generated evidence paths still block the operation.
  while IFS= read -r entry; do
    entry_status="${entry:0:2}"
    entry_path="${entry:3}"
    if [[ "$entry_status" == '??' && ( "$entry_path" == docs/evidence/* || "$entry_path" == docs/rolling_update_probe.csv ) ]]; then
      continue
    fi
    printf 'Dirty worktree entry: %s\n' "$entry" >&2
    dirty=1
  done < <(git -C "$GITOPS_ROOT" status --porcelain --untracked-files=all)
  if [[ "$dirty" -ne 0 ]]; then
    echo "Commit or stash source changes before running a release drill." >&2
    return 1
  fi

  git -C "$GITOPS_ROOT" fetch --quiet origin main
  local_sha="$(git -C "$GITOPS_ROOT" rev-parse HEAD)"
  remote_sha="$(git -C "$GITOPS_ROOT" rev-parse origin/main)"
  if [[ "$local_sha" != "$remote_sha" ]]; then
    echo "Local main ($local_sha) is not up to date with origin/main ($remote_sha)." >&2
    echo "Run: git pull --ff-only origin main" >&2
    return 1
  fi
}

open_pr() {
  local branch="$1" title="$2" body="$3"
  git -C "$GITOPS_ROOT" push --set-upstream origin "$branch" >&2
  gh pr create --base main --head "$branch" --title "$title" --body "$body"
}

wait_for_merge() {
  local pr_url="$1" result state merge_sha
  while true; do
    result="$(gh pr view "$pr_url" --json state,mergeCommit \
      --jq '[.state, (.mergeCommit.oid // "")] | @tsv')"
    IFS=$'\t' read -r state merge_sha <<< "$result"
    case "$state" in
      MERGED)
        if [[ -z "$merge_sha" ]]; then
          echo "PR is merged but GitHub did not return its merge commit: $pr_url" >&2
          return 1
        fi
        printf '%s\n' "$merge_sha"
        return 0
        ;;
      CLOSED)
        echo "PR was closed without merging: $pr_url" >&2
        return 1
        ;;
      OPEN)
        echo "waiting for merge: $pr_url" >&2
        sleep 10
        ;;
      *)
        echo "Unexpected PR state '$state' for $pr_url" >&2
        return 1
        ;;
    esac
  done
}

argo_refresh_and_wait() {
  local expected_sha="$1" timeout_seconds="$2" elapsed=0 status sync health revision
  kubectl -n argocd annotate application/fulfillops \
    argocd.argoproj.io/refresh=hard --overwrite
  while (( elapsed <= timeout_seconds )); do
    status="$(kubectl -n argocd get application fulfillops \
      -o jsonpath='{.status.sync.status}{" "}{.status.health.status}{" "}{.status.sync.revision}')"
    read -r sync health revision <<< "$status"
    printf '%s sync=%s health=%s revision=%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${sync:-Unknown}" \
      "${health:-Unknown}" "${revision:-Unknown}"
    if [[ "$revision" == "$expected_sha" && "$sync" == Synced ]]; then
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  echo "Argo CD did not sync expected revision $expected_sha within ${timeout_seconds}s." >&2
  return 1
}

argo_wait_health() {
  local wanted_health="$1" timeout_seconds="$2" elapsed=0 sync health revision
  while (( elapsed <= timeout_seconds )); do
    read -r sync health revision < <(kubectl -n argocd get application fulfillops \
      -o jsonpath='{.status.sync.status}{" "}{.status.health.status}{" "}{.status.sync.revision}')
    printf '%s sync=%s health=%s revision=%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${sync:-Unknown}" \
      "${health:-Unknown}" "${revision:-Unknown}"
    if [[ "$health" == "$wanted_health" ]]; then
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  echo "Argo CD health did not become $wanted_health within ${timeout_seconds}s." >&2
  return 1
}

capture_state() {
  local dir="$1" label="$2"
  mkdir -p "$dir"
  kubectl -n fulfillops get deployment,replicaset,pods -o wide \
    >"$dir/$label-workloads.txt" 2>&1
  kubectl -n fulfillops get endpoints fulfillops-api -o wide \
    >"$dir/$label-api-endpoints.txt" 2>&1
  kubectl -n fulfillops rollout history deployment/fulfillops-api \
    >"$dir/$label-rollout-history.txt" 2>&1
  kubectl -n fulfillops get deployment fulfillops-api \
    -o jsonpath='{range .status.conditions[*]}{.type}{" status="}{.status}{" reason="}{.reason}{" message="}{.message}{"\n"}{end}' \
    >"$dir/$label-deployment-conditions.txt" 2>&1
  kubectl -n fulfillops get events --sort-by=.lastTimestamp \
    >"$dir/$label-recent-events.txt" 2>&1
  kubectl -n argocd get application fulfillops -o yaml \
    >"$dir/$label-argocd-status-history.yaml" 2>&1
}

set_release_note() {
  local patch_file="$1" note="$2"
  python3 - "$patch_file" "$note" <<'PY'
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
note = sys.argv[2]
text = path.read_text(encoding="utf-8")
pattern = re.compile(r"(?m)^([ \t]*fulfillops\.io/release-note:[ \t]*).*$")
updated, count = pattern.subn(lambda match: match.group(1) + json.dumps(note), text)
if count != 1:
    raise SystemExit(f"Expected one release-note annotation in {path}, found {count}")
path.write_text(updated, encoding="utf-8")
PY
}

set_readiness_path() {
  local patch_file="$1" probe_path="$2"
  python3 - "$patch_file" "$probe_path" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
probe_path = sys.argv[2]
text = path.read_text(encoding="utf-8")
pattern = re.compile(r"(?m)^([ \t]*path: )[\"']?/health/(?:ready|broken)[\"']?[ \t]*$")
updated, count = pattern.subn(lambda match: match.group(1) + probe_path, text)
if count != 1:
    raise SystemExit(f"Expected one API readiness path in {path}, found {count}")
path.write_text(updated, encoding="utf-8")
PY
}

advance_local_main() {
  git -C "$GITOPS_ROOT" fetch --quiet origin main
  git -C "$GITOPS_ROOT" switch main
  git -C "$GITOPS_ROOT" merge --ff-only origin/main
}

require_healthy_app() {
  local status
  status="$(kubectl -n argocd get application fulfillops \
    -o jsonpath='{.status.sync.status}{" "}{.status.health.status}{" "}{.status.sync.revision}')"
  if [[ "$status" != "Synced Healthy "* ]]; then
    echo "Expected Argo CD Synced Healthy, got: ${status:-empty}" >&2
    return 1
  fi
}
