#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Require a clean source tree so the SHA tag identifies exactly the committed app source.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty; commit or remove all changes before building a SHA-tagged image." >&2
  exit 1
fi

# Use the selected context for local architecture; the default is the real application at repo root.
IMAGE_CONTEXT="${IMAGE_CONTEXT:-.}"
IMAGE_SHA="$(git rev-parse HEAD)"
IMAGE_REF="fulfillops:$IMAGE_SHA"

# Build and load the same local-architecture image into every node in the kind cluster.
docker build --tag "$IMAGE_REF" "$IMAGE_CONTEXT"
kind load docker-image "$IMAGE_REF" --name fulfillops

# Point the kind overlay at the immutable commit-specific tag.
(
  cd infra/k8s/overlays/kind
  kustomize edit set image "fulfillops=$IMAGE_REF"
)
echo "Built and loaded $IMAGE_REF from $IMAGE_CONTEXT"
