#!/bin/sh
set -eu

if [ "$(uname -s)" != "Darwin" ]; then
    echo "run_mac_agent.sh is only for macOS." >&2
    exit 1
fi

env_file="${FOWOCO_MAC_ENV_FILE:-.env.mac}"
python_bin="${FOWOCO_MAC_PYTHON:-.venv/bin/python}"
port="${FOWOCO_MAC_PORT:-8000}"

if [ ! -r "$env_file" ]; then
    echo "Missing $env_file. Copy .env.mac.example and replace placeholders." >&2
    exit 1
fi
if [ ! -x "$python_bin" ]; then
    echo "Missing $python_bin. Create the Mac native virtual environment first." >&2
    exit 1
fi

export PYTHONUNBUFFERED=1
export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false

# Loopback binding is intentional: Cloudflare Tunnel is the only public ingress.
# One uvicorn worker guarantees one process-local BERT/A.X model instance.
exec caffeinate -dimsu "$python_bin" -m uvicorn app.main:app \
    --host 127.0.0.1 \
    --port "$port" \
    --workers 1 \
    --env-file "$env_file"
