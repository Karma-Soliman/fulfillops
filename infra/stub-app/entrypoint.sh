#!/bin/sh
set -eu
case "${1:-api}" in
  api) exec uvicorn app.api:app --host 0.0.0.0 --port 8080 --workers 1 ;;
  worker) exec python -m app.worker ;;
  migrate) exec python -m app.migrate ;;
  id) exec id ;;
  *) exec "$@" ;;
esac
