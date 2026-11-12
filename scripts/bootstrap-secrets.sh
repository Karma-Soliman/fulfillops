#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Read the ignored local environment file without printing any values.
if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and set local database values." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

# Fail before kubectl if a required database setting is absent.
for key in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB; do
  if [[ -z "${!key:-}" ]]; then
    echo "Missing required .env key: $key" >&2
    exit 1
  fi
done

# Encode credentials so punctuation in passwords remains valid in the PostgreSQL URL.
DATABASE_URL="$(python3 - <<'PY'
import os
from urllib.parse import quote

user = quote(os.environ["POSTGRES_USER"], safe="")
password = quote(os.environ["POSTGRES_PASSWORD"], safe="")
database = quote(os.environ["POSTGRES_DB"], safe="")
print(f"postgresql+psycopg://{user}:{password}@postgres:5432/{database}")
PY
)"
export DATABASE_URL

# Apply the namespace declaratively before applying the credentials Secret.
kubectl apply -f infra/k8s/base/namespace.yaml >/dev/null

# Apply the local credentials from stdin; kubectl output contains only object metadata.
kubectl create secret generic fulfillops-db \
  --namespace fulfillops \
  --from-literal="POSTGRES_USER=$POSTGRES_USER" \
  --from-literal="POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
  --from-literal="POSTGRES_DB=$POSTGRES_DB" \
  --from-literal="DATABASE_URL=$DATABASE_URL" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

# Print the Secret's key names only, never its values.
echo "Created or updated Secret fulfillops-db with keys: POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL"
