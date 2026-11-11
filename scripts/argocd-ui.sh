#!/usr/bin/env bash
set -euo pipefail

# Prints the generated initial password to this terminal only; it is never written to a file.
echo "Initial Argo CD admin password (keep it private):"
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' \
  | python3 -c 'import base64,sys; print(base64.b64decode(sys.stdin.read()).decode())'

# Uses localhost-only port forwarding for the UI and keeps this process attached to the terminal.
echo "Open https://localhost:8443 while this port-forward is running."
exec kubectl -n argocd port-forward svc/argocd-server 8443:443
