from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from fastapi import HTTPException, Response
from counterpress.fixture import PossessionFixture, load_fixture

MATCH_ID = 'synthetic-32fe41c5d304ce68d7d9'


def install_live(app, root: Path):
    @lru_cache(maxsize=1)
    def feed():
        folder = root / 'gi' / 'synthetic'
        path = folder / 'events.json'
        manifest = json.loads((folder / 'manifest.json').read_text())
        if sha256(path.read_bytes()).hexdigest() != manifest['fixture_sha256']:
            raise ValueError('Source checksum mismatch')
        result = load_fixture(path)
        if result.match_id != MATCH_ID:
            raise ValueError('Match mismatch')
        return result

    @app.get('/api/live/matches/{match_id}', response_model=PossessionFixture, tags=['Matchday'])
    def full_match(match_id: str, response: Response):
        if match_id != MATCH_ID:
            raise HTTPException(404, 'Full-match playback is not available for this match')
        try:
            result = feed()
        except (OSError, ValueError, KeyError):
            raise HTTPException(503, 'Match is temporarily unavailable') from None
        response.headers['Cache-Control'] = 'public, max-age=300'
        return result
