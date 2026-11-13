#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck source=scripts/lib-gitops.sh
source scripts/lib-gitops.sh

usage() {
  echo 'Usage: scripts/release.sh --image <full-commit-sha> | scripts/release.sh --note "text"' >&2
  exit 2
}

mode=""
value=""
if [[ $# -eq 2 && "$1" == --image ]]; then
  mode=image
  value="$2"
elif [[ $# -eq 2 && "$1" == --note ]]; then
  mode=note
  value="$2"
else
  usage
fi

if [[ "$mode" == image && ! "$value" =~ ^[[:xdigit:]]{40}$ ]]; then
  echo "Image SHA must be a full 40-character hexadecimal commit SHA." >&2
  exit 2
fi
if [[ "$mode" == note && ( -z "$value" || "$value" == *$'\n'* ) ]]; then
  echo "Release note must be nonempty and fit on one line." >&2
  exit 2
fi

if [[ "$mode" == image ]]; then
  head_sha="$(git rev-parse HEAD)"
  if [[ "$head_sha" != "$value" ]]; then
    echo "Refusing to build image: requested SHA and current HEAD differ." >&2
    echo "Requested image SHA: $value" >&2
    echo "Current HEAD:        $head_sha" >&2
    exit 1
  fi
fi

require_clean_main
before_revision="$(kubectl -n argocd get application fulfillops \
  -o jsonpath='{.status.sync.revision}')"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
branch="release/$stamp"

if git show-ref --verify --quiet "refs/heads/$branch"; then
  echo "Release branch already exists locally: $branch" >&2
  exit 1
fi
remote_branch="$(git ls-remote --heads origin "refs/heads/$branch")"
if [[ -n "$remote_branch" ]]; then
  echo "Release branch already exists on origin: $branch" >&2
  exit 1
fi

if [[ "$mode" == image ]]; then
  image_context="$ROOT_DIR"
  image_tag="fulfillops:$value"
  architecture="$(docker info --format '{{.Architecture}}')"
  case "$architecture" in
    arm64|aarch64) platform=linux/arm64 ;;
    amd64|x86_64) platform=linux/amd64 ;;
    *) echo "Unsupported local Docker architecture: $architecture" >&2; exit 1 ;;
  esac
  docker build --platform "$platform" -t "$image_tag" "$image_context"
  kind load docker-image "$image_tag" --name fulfillops
fi

git switch -c "$branch" main
if [[ "$mode" == image ]]; then
  (cd infra/k8s/overlays/kind && kustomize edit set image "fulfillops=fulfillops:$value")
  title="release: deploy image $value"
  body="Deploy local image tag \`$image_tag\` to the kind overlay. The image was built from \`$image_context\` and loaded into the \`fulfillops\` kind cluster before the pull request was opened."
else
  set_release_note infra/k8s/overlays/kind/release-patch.yaml "$value"
  title="release: $value"
  body="Change only the API pod-template release-note annotation to \`$value\`, triggering a harmless rolling update."
fi

git add infra/k8s/overlays/kind/kustomization.yaml infra/k8s/overlays/kind/release-patch.yaml
git commit -m "$title"
printf 'Before Argo revision: %s\n' "$before_revision"
pr_url="$(open_pr "$branch" "$title" "$body")"
printf 'Release PR: %s\n' "$pr_url"
merge_sha="$(wait_for_merge "$pr_url")"
printf 'Merged revision: %s\n' "$merge_sha"
advance_local_main
argo_refresh_and_wait "$merge_sha" 180
argo_wait_health Healthy 180
kubectl -n fulfillops rollout status deployment/fulfillops-api --timeout=240s
printf 'Before revision: %s\nAfter revision: %s\n' "$before_revision" "$merge_sha"
