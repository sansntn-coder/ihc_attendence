#!/bin/zsh

cd "$(dirname "$0")"
BIND_HOST="${BIND_HOST:-0.0.0.0}" PORT="${PORT:-8000}" python3 server.py
