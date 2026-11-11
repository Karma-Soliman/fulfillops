#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME=fulfillops
ASSUME_YES=false

if [[ "${1:-}" == "--yes" ]]; then
  ASSUME_YES=true
  shift
fi
if [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--yes]" >&2
  exit 2
fi

if ! kind get clusters | grep -Fxq "$CLUSTER_NAME"; then
  echo "Cluster $CLUSTER_NAME does not exist."
  exit 0
fi

if [[ "$ASSUME_YES" != true ]]; then
  read -r -p "Delete cluster fulfillops? All data in it (including database volumes) is lost [y/N] " answer
  case "$answer" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Keeping cluster $CLUSTER_NAME."; exit 0 ;;
  esac
fi

kind delete cluster --name "$CLUSTER_NAME"
