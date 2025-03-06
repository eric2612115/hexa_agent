#!/bin/bash
set -e

source /app/.venv/bin/activate
exec "$UVICORN_PATH" main:app --host 0.0.0.0 --port 7788