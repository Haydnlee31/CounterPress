from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Response
from counterpress.gi.service import MATCHES, Match, read_match


def install_gi(app, fixture_root: Path):
    @lru_cache(maxsize=2)
    def match(match_id: str):
        return read_match(fixture_root / 'gi', match_id)

    @app.get('/api/gi/matches/{match_id}', response_model=Match, tags=['GI'])
    def full_match(match_id: str, response: Response):
        if match_id not in MATCHES:
            raise HTTPException(404, 'Match not found')
        try:
            result = match(match_id)
        except (OSError, ValueError, KeyError):
            raise HTTPException(503, 'Match data is temporarily unavailable') from None
        response.headers['Cache-Control'] = 'public, max-age=300'
        return result
