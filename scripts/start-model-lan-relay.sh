#!/usr/bin/env bash

set -u

cd /Users/mac/项目/kodagent
exec python3 scripts/model_lan_relay.py \
  --listen-host "${OA_AGENT_MODEL_RELAY_LISTEN_HOST:-127.0.0.1}" \
  --listen-port "${OA_AGENT_MODEL_RELAY_LISTEN_PORT:-18081}" \
  --target-host "${OA_AGENT_MODEL_RELAY_TARGET_HOST:-192.168.1.103}" \
  --target-port "${OA_AGENT_MODEL_RELAY_TARGET_PORT:-8000}"
