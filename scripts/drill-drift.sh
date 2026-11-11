#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Store evidence under a UTC timestamp without ever recording credentials.
mkdir -p docs/evidence
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE="docs/evidence/drift-$STAMP.txt"
touch "$EVIDENCE"
echo "Drift correction evidence: $EVIDENCE"

# Records the Git revision and the Application/Deployment state before introducing drift.
{
  echo "Git origin/main: $(git rev-parse origin/main)"
  echo "Initial Application status: $(kubectl -n argocd get application fulfillops -o jsonpath='{.status.sync.status} {.status.health.status}')"
  echo "Initial desired API replicas: $(kubectl -n fulfillops get deployment fulfillops-api -o jsonpath='{.spec.replicas}')"
  echo "Initial ready API replicas: $(kubectl -n fulfillops get deployment fulfillops-api -o jsonpath='{.status.readyReplicas}')"
} | tee -a "$EVIDENCE"

# Deliberately changes only the live scale so Argo CD self-heal can restore Git's replica count.
kubectl -n fulfillops scale deployment/fulfillops-api --replicas=1 | tee -a "$EVIDENCE"

# Requests an immediate Git refresh rather than waiting for Argo CD's normal polling interval.
./scripts/argocd-refresh.sh 2>&1 | tee -a "$EVIDENCE"

# Poll every two seconds for at most sixty seconds, recording sync, health, and ready replica state.
RESTORED=false
for elapsed in $(seq 0 2 60); do
  app_status="$(kubectl -n argocd get application fulfillops \
    -o jsonpath='{.status.sync.status} {.status.health.status}')"
  desired="$(kubectl -n fulfillops get deployment fulfillops-api -o jsonpath='{.spec.replicas}')"
  ready="$(kubectl -n fulfillops get deployment fulfillops-api -o jsonpath='{.status.readyReplicas}')"
  desired="${desired:-0}"
  ready="${ready:-0}"
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  line="$timestamp elapsed=${elapsed}s app=${app_status:-Pending} api_ready=$ready/$desired"
  echo "$line" | tee -a "$EVIDENCE"
  if [[ "$app_status" == "Synced Healthy" && "$desired" == "2" && "$ready" == "2" ]]; then
    RESTORED=true
    break
  fi
  if [[ "$elapsed" != "60" ]]; then
    sleep 2
  fi
done

# Appends the controller's recent operation history and the namespace events for diagnosis.
{
  echo
  echo "Application history and operation state:"
  kubectl -n argocd get application fulfillops \
    -o jsonpath='history={.status.history}{"\n"}operationState={.status.operationState}{"\n"}'
  echo
  echo "Namespace fulfillops events:"
  kubectl -n fulfillops get events --sort-by=.lastTimestamp
} 2>&1 | tee -a "$EVIDENCE"

if [[ "$RESTORED" != true ]]; then
  echo "Argo CD did not restore two ready API replicas within 60 seconds." | tee -a "$EVIDENCE" >&2
  exit 1
fi

echo "Drift was corrected: API replicas are back at 2 and the Application is Synced and Healthy." | tee -a "$EVIDENCE"
