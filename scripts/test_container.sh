#!/usr/bin/env bash
set -euo pipefail
image="${1:-counterpress:smoke}"
container_id="$(docker run -d --platform linux/amd64 --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /data:uid=10001,gid=10001,mode=0700 --tmpfs /tmp:mode=1777 \
  --memory 1g --cpus 0.5 -p 127.0.0.1::8000 "$image")"
trap 'docker rm -f "$container_id" >/dev/null' EXIT
binding="$(docker port "$container_id" 8000/tcp)"
base="http://$binding"
ready=false
for attempt in {1..60}; do
  if curl --fail --silent --max-time 5 "$base/ready" >/dev/null; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo 'FAIL: container did not become ready within startup budget' >&2
  exit 1
fi
python3 scripts/container_smoke.py "$base"
docker exec "$container_id" python -c '
import os
from pathlib import Path
assert os.getuid() == 10001
assert not any(name.startswith("AZURE_") for name in os.environ)
for path in ("/app/.env", "/app/.git", "/app/backend", "/app/uv.lock", "/app/static/.env"):
    assert not Path(path).exists(), path
assert Path("/data/counterpress.sqlite3").is_file()
print("PASS: non-root runtime, writable ephemeral database, no Azure environment or source credentials")
'
