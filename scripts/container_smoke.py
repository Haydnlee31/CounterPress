"""Exercise the built image through its real HTTP port; no cloud credentials."""
import json
import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def get(path):
    with urlopen(base + path, timeout=20) as response:
        return response.read(), response.headers


def data(path):
    body, headers = get(path)
    assert headers.get("Cache-Control") == "no-store"
    return json.loads(body)


assert json.loads(get("/health")[0]) == {"status": "ok", "service": "counterpress"}
assert data("/ready")["status"] == "ok"
html, headers = get("/")
assert headers.get_content_type() == "text/html"
assert headers.get("Cache-Control") == "no-store"
assets = re.findall(rb'(?:src|href)="(/assets/[^\"]+)"', html)
assert len(assets) >= 2
for asset in assets:
    assert len(get(asset.decode())[0]) > 100
callback, callback_headers = get("/auth.html")
assert callback_headers.get("Cache-Control") == "no-store"
assert callback_headers.get("Referrer-Policy") == "no-referrer"
assert b"/assets/" in callback
studio = data("/api/studio/config")
if '--studio-enabled' in sys.argv:
    assert studio['enabled'] is True and set(studio) == {'enabled', 'client_id', 'authority', 'scope'}
    for action in ('review', 'approve', 'revoke', 'export', 'draft', 'broadcast'):
        payload = {} if action == 'review' else {'fingerprint': 'a'*64}
        if action == 'broadcast': payload.update(insight_id='test-story', format='lower-third')
        request = Request(base+'/api/studio/increase/'+action, data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            urlopen(request, timeout=20)
            raise AssertionError('Studio accepted an anonymous request')
        except HTTPError as error:
            assert error.code == 401 and error.headers.get('Cache-Control') == 'no-store'
else:
    assert studio == {"enabled": False}
positive = data("/api/scenarios/increase/snapshot?at_ms=780000")
assert positive["insight"]["facts"]["baseline_count"] == 1
assert positive["insight"]["facts"]["current_count"] == 4
assert len(positive["evidence"]["records"]) == 5
control = data("/api/scenarios/control/snapshot?at_ms=780000")
assert control["insight"] is None
pressure = data("/api/scenarios/pressure-increase/snapshot?at_ms=780000")
assert len(pressure["recap"]["statements"]) == 2
assert pressure["adapted_recap"] is None
chinese = data("/api/scenarios/pressure-increase/snapshot?at_ms=780000&language=zh-Hans")
assert chinese["recap"]["preferences"]["language"] == "zh-Hans"
for path in ("/.env", "/.git/config", "/fixtures/recovery_increase.json", "/api/missing", "/assets/missing.js"):
    try:
        get(path)
        raise AssertionError(f"Unexpected public file: {path}")
    except HTTPError as error:
        assert error.code == 404
print("PASS: health, readiness, frontend/assets, Studio callback/access boundary, 1-to-4 evidence, control, bilingual recap, private-path 404s")
