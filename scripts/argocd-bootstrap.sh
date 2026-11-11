#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# This one-time manual bootstrap solves the bootstrap problem: Argo CD cannot create its own first Application.
kubectl apply -f infra/argocd/project.yaml
kubectl apply -f infra/argocd/application.yaml

# Poll sync and health every ten seconds for up to five minutes.
for elapsed in $(seq 0 10 290); do
  status="$(kubectl -n argocd get application fulfillops \
    -o jsonpath='{.status.sync.status} {.status.health.status}')"
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "$timestamp ${status:-Pending}"
  if [[ "$status" == "Synced Healthy" ]]; then
    exit 0
  fi
  sleep 10
done

# Preserve the controller's reported conditions to make a failed bootstrap diagnosable.
echo "Timed out waiting for Application fulfillops to become Synced and Healthy." >&2
kubectl -n argocd get application fulfillops \
  -o jsonpath='status.conditions={.status.conditions}{"\n"}' >&2 || true
exit 1
