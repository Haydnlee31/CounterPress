"""Production routing and readiness boundaries, without Docker or cloud access."""
import sqlite3

import pytest

from counterpress.api.main import create_app
from test_snapshot_api import request


def test_same_origin_frontend_preserves_api_and_file_boundaries(tmp_path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text('<html><script src="/assets/app.js"></script></html>')
    (static / "assets/app.js").write_text('console.log("synthetic")')
    (static / ".env").write_text("PRIVATE_CANARY=not-for-http")
    (tmp_path / "outside.txt").write_text("outside-canary")
    (static / "assets/escape.txt").symlink_to(tmp_path / "outside.txt")
    app = create_app(static_dir=static)
    assert request(app, "/").headers["cache-control"] == "no-store"
    assert request(app, "/assets/app.js").text == 'console.log("synthetic")'
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
