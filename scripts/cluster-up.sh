#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop, then retry make cluster-up." >&2
  exit 1
fi

# An existing kind cluster already owns host port 8080 through its port mapping.
if kind get clusters | grep -Fxq fulfillops; then
  echo "Cluster fulfillops already exists."
  kubectl config use-context kind-fulfillops
  exit 0
fi

if lsof -nP -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Host port 8080 is already in use. Stop the local Compose stack with 'make down' or stop the process using that port." >&2
  lsof -nP -iTCP:8080 -sTCP:LISTEN >&2 || true
  exit 1
fi

kind create cluster --config infra/kind/cluster.yaml \
  --image kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5 \
  --wait 120s
kubectl config use-context kind-fulfillops
kubectl get nodes -o wide
