#!/bin/sh
set -eu

role="${1:-api}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$role" in
  api)
    exec uvicorn api.main:app --host 0.0.0.0 --port 8080 --workers 1 --no-access-log "$@"
    ;;
  worker)
    exec python -m worker.main "$@"
    ;;
  migrate)
    exec alembic upgrade head "$@"
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
