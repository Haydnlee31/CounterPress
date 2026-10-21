"""Production routing and readiness boundaries, without Docker or cloud access."""
import sqlite3
import asyncio
import gzip

from httpx import ASGITransport, AsyncClient

import pytest

from counterpress.api.main import create_app
from test_snapshot_api import request


def test_same_origin_frontend_preserves_api_and_file_boundaries(tmp_path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text('<html><script src="/assets/app.js"></script></html>')
    (static / "auth.html").write_text("<html>Sign-in callback</html>")
    (static / "assets/app.js").write_text('console.log("synthetic")')
    (static / ".env").write_text("PRIVATE_CANARY=not-for-http")
    (tmp_path / "outside.txt").write_text("outside-canary")
    (static / "assets/escape.txt").symlink_to(tmp_path / "outside.txt")
    app = create_app(static_dir=static)
    assert request(app, "/").headers["cache-control"] == "no-store"
    assert request(app, "/assets/app.js").text == 'console.log("synthetic")'
    assert request(app, "/auth.html").headers["referrer-policy"] == "no-referrer"
    assert request(app, "/api/studio/config").json() == {"enabled": False}
    snapshot = request(app, "/api/scenarios/increase/snapshot?at_ms=780000")
    assert snapshot.json()["insight"]["facts"]["current_count"] == 4
    assert snapshot.headers["cache-control"] == "no-store"
    for path in ("/.env", "/assets/escape.txt", "/assets/%2e%2e/.env", "/api/missing", "/missing", "/assets/missing.js"):
        response = request(app, path)
        assert response.status_code == 404
        assert "PRIVATE_CANARY" not in response.text and "outside-canary" not in response.text
        assert "<html>" not in response.text


def test_static_build_must_exist_but_api_only_development_still_works(tmp_path):
    with pytest.raises(ValueError, match="Static frontend requires"):
        create_app(static_dir=tmp_path)
    assert request(create_app(), "/").status_code == 404


def test_readiness_checks_local_replay_and_sanitizes_failures(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "history.sqlite3")
    assert request(app, "/ready").json() == {"status": "ok", "service": "counterpress"}
    assert request(app, "/ready").headers["cache-control"] == "no-store"

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("private-path-canary")

    monkeypatch.setattr(app.state.snapshots, "snapshot", fail)
    assert request(app, "/health").status_code == 200
    failed = request(app, "/ready")
    assert failed.status_code == 503
    assert failed.json() == {"detail": "Replay is not ready."}
    assert request(create_app(fixture_dir=tmp_path), "/ready").status_code == 503


def test_compression_preserves_match_data_and_cache_policy():
    app = create_app()

    async def check():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            path = '/api/gi/matches/wyscout-2058017'
            plain = await client.get(path, headers={'Accept-Encoding': 'identity'})
            async with client.stream('GET', path, headers={'Accept-Encoding': 'gzip'}) as compressed:
                wire = b''.join([part async for part in compressed.aiter_raw()])
                assert compressed.headers['content-encoding'] == 'gzip'
                assert 'Accept-Encoding' in compressed.headers['vary']
                assert compressed.headers['cache-control'] == plain.headers['cache-control']
                assert gzip.decompress(wire) == plain.content
                assert len(wire) < len(plain.content) / 4
            snapshot = await client.get('/api/scenarios/increase/snapshot?at_ms=780000')
            assert snapshot.headers['cache-control'] == 'no-store'
            assert snapshot.json()['insight']['facts']['current_count'] == 4
            assert 'content-encoding' not in (await client.get('/health')).headers

    asyncio.run(check())


def test_only_successful_hashed_assets_are_immutable_and_images_are_not_recompressed(tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<html>Footie</html>')
    (tmp_path / 'assets/main-AbCd1234.js').write_text('const data="football";\n' * 200)
    (tmp_path / 'assets/player-AbCd1234.webp').write_bytes(b'RIFF0000WEBP' + b'x' * 2000)
    (tmp_path / 'assets/plain.js').write_text('export const ready=true')
    app = create_app(static_dir=tmp_path)

    async def check():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/assets/main-AbCd1234.js')
            assert response.headers['cache-control'] == 'public, max-age=31536000, immutable'
            assert response.headers['content-encoding'] == 'gzip'
            cached = await client.get('/assets/main-AbCd1234.js', headers={'If-None-Match': response.headers['etag']})
            assert cached.status_code == 304
            assert cached.headers['cache-control'] == response.headers['cache-control']
            image = await client.get('/assets/player-AbCd1234.webp')
            assert 'content-encoding' not in image.headers
            assert len(image.content) == 2012
            for path in ('/', '/assets/plain.js', '/assets/missing-AbCd1234.js'):
                assert 'immutable' not in (await client.get(path)).headers.get('cache-control', '')

    asyncio.run(check())
