#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Refresh the out-of-Git database credentials before any workload references them.
./scripts/bootstrap-secrets.sh

# Job pod templates are immutable, so remove a prior run before applying its replacement.
kubectl -n fulfillops delete job fulfillops-migrate --ignore-not-found=true --wait=true

# Apply the complete rendered stack, then require migrations and both deployments to finish.
kubectl apply -k infra/k8s/overlays/kind
kubectl -n fulfillops wait --for=condition=complete job/fulfillops-migrate --timeout=240s
kubectl -n fulfillops rollout status deployment/fulfillops-api --timeout=240s
kubectl -n fulfillops rollout status deployment/fulfillops-worker --timeout=240s
