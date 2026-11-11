#!/usr/bin/env bash
set -euo pipefail

# Forces a hard refresh so Argo CD rereads Git immediately instead of waiting for its polling interval.
kubectl -n argocd annotate application/fulfillops \
  argocd.argoproj.io/refresh=hard --overwrite
