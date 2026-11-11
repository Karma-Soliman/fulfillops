#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Create the Argo CD system namespace declaratively so this script is safe to repeat.
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -

# Server-side apply avoids client-side annotation limits on Argo CD's large CRD definitions.
kubectl apply -k infra/argocd/install --server-side --force-conflicts

# Wait until Argo CD's repository cache and web/API server deployments are available.
kubectl -n argocd rollout status deployment/argocd-repo-server --timeout=600s
kubectl -n argocd rollout status deployment/argocd-server --timeout=600s

# The application controller is a StatefulSet in the pinned v3.6.1 install manifest.
if kubectl -n argocd get statefulset argocd-application-controller >/dev/null 2>&1; then
  kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=600s
elif kubectl -n argocd get deployment argocd-application-controller >/dev/null 2>&1; then
  kubectl -n argocd rollout status deployment/argocd-application-controller --timeout=600s
else
  echo "Argo CD application controller was not found as a Deployment or StatefulSet." >&2
  kubectl -n argocd get deploy,sts >&2
  exit 1
fi

# Show the complete Argo CD workload state after all required controllers are ready.
kubectl -n argocd get deploy,sts,pods -o wide
