#!/usr/bin/env bash
set -e
cd /root/sprechen1
if [ -d "venv" ]; then
    source venv/bin/activate
fi
exec uvicorn app.main:app --host 127.0.0.1 --port 8085
