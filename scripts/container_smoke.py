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
showcase = data("/api/scenarios/last-gasp/snapshot?at_ms=780000")
assert showcase["state"]["score"] == {"eastbridge": 3, "northport": 1}
assert [e["action"]["outcome"] for e in showcase["pitch_events"] if e["action"]["kind"] == "shot"] == ["saved", "saved", "goal"]
assert not showcase["recap"]["statements"]
assert data("/api/scenarios/last-gasp/snapshot?at_ms=779999")["state"]["score"] == {"eastbridge": 2, "northport": 1}
for scenario, final in (("one-touch",3),("breakaway",2)):
    show = data(f"/api/scenarios/{scenario}/snapshot?at_ms=780000")
    assert show["state"]["score"] == {"eastbridge":final,"northport":0}
    assert len(show["pitch_events"]) == 5 and not show["recap"]["statements"]
    assert data(f"/api/scenarios/{scenario}/snapshot?at_ms=779999")["state"]["score"]["eastbridge"] == final-1
gi = json.loads(get('/api/gi/matches/wyscout-2058017')[0])
assert len(gi['events']) == 1462 and len(gi['players']) == 27
assert [team['score'] for team in gi['teams']] == [4, 2]
assert gi['source']['license'] == 'CC BY 4.0'
assert gi['video_alignment'] == 'unverified'
comeback = json.loads(get('/api/gi/matches/wyscout-2058007')[0])
assert len(comeback['events']) == 1682 and len(comeback['players']) == 26
assert [team['score'] for team in comeback['teams']] == [3, 2]
assert [e['goal_for'] for e in comeback['events'] if e['goal_for']] == [9598, 9598, 4418, 4418, 4418]
assert comeback['source']['license'] == 'CC BY 4.0'
catalog = json.loads(get('/api/data/catalog')[0])
assert catalog['counts']['featured_players'] == 44 and catalog['counts']['historical_matches'] == 840
assert json.loads(get('/api/data/matches')[0])['total'] == 4
assert json.loads(get('/api/data/players')[0])['total'] == 44
career = json.loads(get('/api/data/players/sb09')[0])
assert career['totals']['goals'] > 0 and career['coverage']['tracking_distance_m'] is None
new_match = 'career-showcase-southbank-redhaven'
milestone = data(f'/api/data/matches/{new_match}/live?period=2&elapsed_ms=2700000')['milestones'][0]
at = milestone['available_at']['elapsed_ms']
assert not data(f'/api/data/matches/{new_match}/live?period=2&elapsed_ms={at-1}')['milestones']
assert data(f'/api/data/matches/{new_match}/live?period=2&elapsed_ms={at}')['milestones'][0]['career_goals'] == 20
assert len(json.loads(get('/api/data/highlights')[0])) == 3
assert {t['team_id'] for t in json.loads(get(f'/api/data/matches/{new_match}/replay')[0])['teams']} == {'southbank','redhaven'}

def personalized(path, payload):
    request = Request(base + '/api/fan/' + path, data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=20) as response:
        assert response.headers.get('Cache-Control') == 'private, no-store'
        assert response.headers.get('Set-Cookie') is None
        return json.load(response)

preferences = {'favorite_club_ids': ['redhaven'], 'favorite_player_ids': ['rh08'], 'primary_club_id': 'redhaven'}
home = personalized('home', {'preferences': preferences, 'as_of': '2026-10-20T00:00:00Z'})
assert len(home['highlights']) == 9 and len(home['matches']) == 4
assert home['matches'][0]['match_id'] == new_match
assert home['following']['players'][0]['player']['name'] == 'Enzo Clarke'
before = personalized('matches/' + new_match, {'preferences': preferences, 'cutoff': {'period': 2, 'elapsed_ms': at-1}})
after = personalized('matches/' + new_match, {'preferences': preferences, 'cutoff': {'period': 2, 'elapsed_ms': at}})
assert not any(c['kind'] == 'career_goal_milestone' for c in before['cards'])
assert after['cards'][0]['facts'][0]['value'] == 20 and len(after['focus']['active_player_ids']) == 22
analyst = personalized('matches/' + new_match, {'preferences': {**preferences, 'depth': 'analyst'}, 'cutoff': {'period': 2, 'elapsed_ms': at}})
assert after['facts'] == analyst['facts'] and after['cards'][0]['text'] != analyst['cards'][0]['text']
assert personalized('home', {'as_of': '2026-10-20T00:00:00Z'})['following'] == {'players': [], 'clubs': []}
for path in ("/.env", "/.git/config", "/fixtures/recovery_increase.json", "/api/missing", "/assets/missing.js"):
    try:
        get(path)
        raise AssertionError(f"Unexpected public file: {path}")
    except HTTPError as error:
        assert error.code == 404
print("PASS: health, readiness, frontend/assets, Studio access, evidence/recaps, replay goals, GI attribution, 44 career profiles, four featured matches, nine personalized highlights, causal milestone, 22-player focus, audience fact parity, preference isolation, private-path 404s")
