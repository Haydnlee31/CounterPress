from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Response
from counterpress.gi.service import MATCH_ID, Match, read_match


def install_gi(app, fixture_root: Path):
    @lru_cache(maxsize=1)
    def match():
        return read_match(fixture_root / 'gi')

    @app.get('/api/gi/matches/{match_id}', response_model=Match, tags=['GI'])
    def full_match(match_id: str, response: Response):
        if match_id != MATCH_ID:
            raise HTTPException(404, 'Match not found')
        try:
            result = match()
        except (OSError, ValueError, KeyError):
            raise HTTPException(503, 'Match data is temporarily unavailable') from None
        response.headers['Cache-Control'] = 'public, max-age=300'
        return result
