"""Run with: uv run uvicorn counterpress.api.main:app --reload."""

from typing import Literal
from contextlib import asynccontextmanager
from time import monotonic
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from counterpress.domain.models import Contract
from counterpress.domain.contributions import PlayerContributionEvidence
from counterpress.audience import PreferenceError, ViewingPreferences
from counterpress.api.snapshots import SCENARIOS, PlaybackRangeError, Scenario, ScreenSnapshot, SnapshotService, horizon
from counterpress.history import EvidenceBundle, HistoryStore, HistoryStorageError
from counterpress.storage import configured_store
from counterpress.pressure_publications import PressureChange
from counterpress.contribution_publications import ContributionChange


class HealthResponse(Contract):
    status: Literal["ok"] = "ok"
    service: Literal["counterpress"] = "counterpress"


def create_app(fixture_dir: Path | None = None, db_path: str | Path = ":memory:",
               static_dir: Path | None = None, store: HistoryStore | None = None,
               revision_publisher=None) -> FastAPI:
    root = fixture_dir or Path(os.environ.get("COUNTERPRESS_FIXTURE_DIR", Path(__file__).resolve().parents[3] / "fixtures"))
    service = SnapshotService(root, store if store is not None else configured_store(db_path))
    @asynccontextmanager
    async def lifespan(application):
        runtime = None
        try:
            if os.environ.get('COUNTERPRESS_STREAMING', 'off') == 'azure':
                from counterpress.streaming.azure import StreamingRuntime
                runtime = StreamingRuntime(service)
                await runtime.start()
                application.state.revision_publisher = runtime.publisher
            yield
        finally:
            if runtime:
                await runtime.close()

    application = FastAPI(title="CounterPress", version="0.1.0", lifespan=lifespan)
    application.state.snapshots = service
    application.state.revision_publisher = revision_publisher
    negotiations: list[float] = []

    @application.get('/api/revisions/negotiate')
    async def negotiate(response: Response, scenario_id: str):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if scenario_id not in SCENARIOS:
            raise HTTPException(status_code=404, detail='Unknown scenario')
        publisher = application.state.revision_publisher
        if publisher is None:
            return {'enabled': False}
        now = monotonic()
        negotiations[:] = [at for at in negotiations if now - at < 60]
        # One process / one replica demo limit. No identity or token is logged.
        if len(negotiations) >= 30:
            raise HTTPException(status_code=429, detail='Live updates are busy; polling remains available.',
                                headers={'Retry-After': '60'})
        negotiations.append(now)
        try:
            return await publisher.negotiate(scenario_id)
        except Exception:
            raise HTTPException(status_code=503, detail='Live updates unavailable; polling remains available.') from None

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Process liveness only; no external dependencies."""
        return HealthResponse()

    @application.get("/ready", response_model=HealthResponse, tags=["health"])
    def ready(response: Response) -> HealthResponse:
        """Check replay/storage availability without contacting a model."""
        response.headers["Cache-Control"] = "no-store"
        try:
            service.snapshot("increase", 180000)
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError) as exc:
            raise HTTPException(status_code=503, detail="Replay is not ready.") from exc
        return HealthResponse()

    @application.get("/api/scenarios", response_model=tuple[Scenario, ...])
    def scenarios() -> tuple[Scenario, ...]:
        try:
            return tuple(Scenario(scenario_id=key, label=value[1],
                                  **({"end": horizon(history)} if (history := service.store.read(key)) else {}))
                         for key, value in SCENARIOS.items())
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError) as exc:
            raise HTTPException(status_code=503, detail="Replay history could not be loaded or validated.") from exc

    @application.get("/api/scenarios/{scenario_id}/snapshot", response_model=ScreenSnapshot)
    def snapshot(scenario_id: str, response: Response, at_ms: int = Query(180000, ge=180000),
                 scope_id: str = Query("default", pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$"),
                 language: Literal["en", "zh-Hans"] = "en", depth: Literal["analyst", "casual"] = "analyst",
                 club_id: str | None = Query(None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$"),
                 player_id: str | None = Query(None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$"),
                 metric_focus: Literal["balanced", "high_recoveries", "passing", "pressure_exposure", "pressured_escape", "possession_without_progression", "player_high_recovery_share"] = "balanced",
                 card_budget: int = Query(1, ge=0, le=1)) -> ScreenSnapshot:
        response.headers["Cache-Control"] = "no-store"
        try:
            return service.snapshot(scenario_id, at_ms, scope_id, ViewingPreferences(
                language=language, depth=depth, club_id=club_id, player_id=player_id,
                metric_focus=metric_focus, card_budget=card_budget))
        except PreferenceError as exc:
            raise HTTPException(status_code=422, detail="Unknown club or player preference.") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown scenario") from exc
        except PlaybackRangeError as exc:
            raise HTTPException(status_code=422, detail="Position is outside the available replay.") from exc
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError) as exc:
            raise HTTPException(status_code=503, detail="Replay history could not be loaded or validated.") from exc

    @application.get("/api/scenarios/{scenario_id}/players/{player_id}/contribution", response_model=PlayerContributionEvidence)
    def contribution(scenario_id: str, player_id: str, response: Response,
                     at_ms: int = Query(..., ge=180000), team_id: str = "eastbridge") -> PlayerContributionEvidence:
        response.headers["Cache-Control"] = "no-store"
        try:
            return service.contribution(scenario_id, team_id, player_id, at_ms)
        except PreferenceError as exc:
            raise HTTPException(status_code=422, detail="Player must belong to the subject team.") from exc
        except PlaybackRangeError as exc:
            raise HTTPException(status_code=422, detail="Comparison requires completed windows within the available replay.") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown scenario") from exc
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError) as exc:
            raise HTTPException(status_code=503, detail="Replay history could not be loaded or validated.") from exc

    @application.get("/api/scenarios/{scenario_id}/evidence/{version}", response_model=EvidenceBundle)
    def evidence(scenario_id: str, version: int, response: Response, at_ms: int = Query(..., ge=180000)) -> EvidenceBundle:
        response.headers["Cache-Control"] = "no-store"
        try:
            return service.evidence(scenario_id, version, at_ms)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Evidence is not available at this cutoff.") from exc
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError) as exc:
            raise HTTPException(status_code=503, detail="Replay history could not be loaded or validated.") from exc

    @application.get("/api/scenarios/{scenario_id}/pressure/{insight_id}/evidence/{version}", response_model=PressureChange)
    def pressure_evidence(scenario_id: str, insight_id: str, version: int, response: Response,
                          at_ms: int = Query(..., ge=180000)) -> PressureChange:
        response.headers["Cache-Control"] = "no-store"
        try:
            return service.pressure_evidence(scenario_id, insight_id, version, at_ms)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Pressure evidence is not available at this cutoff.") from exc
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError) as exc:
            raise HTTPException(status_code=503, detail="Replay history could not be loaded or validated.") from exc

    @application.get("/api/scenarios/{scenario_id}/contributions/{insight_id}/evidence/{version}", response_model=ContributionChange)
    def contribution_evidence(scenario_id: str, insight_id: str, version: int, response: Response,
                             at_ms: int = Query(..., ge=180000)) -> ContributionChange:
        response.headers["Cache-Control"] = "no-store"
        try:
            return service.contribution_evidence(scenario_id, insight_id, version, at_ms)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Player evidence is not available at this cutoff.") from exc
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError) as exc:
            raise HTTPException(status_code=503, detail="Replay history could not be loaded or validated.") from exc

    if static_dir is not None:
        static_dir = static_dir.resolve()
        if not (static_dir / "index.html").is_file() or not (static_dir / "assets").is_dir():
            raise ValueError("Static frontend requires index.html and an assets directory.")

        @application.get("/", include_in_schema=False)
        def frontend() -> FileResponse:
            return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-store"})

        # Only expose compiled assets. No catch-all, source files or repository root.
        application.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    return application


app = create_app(
    db_path=os.environ.get("COUNTERPRESS_DB_PATH", str(Path(__file__).resolve().parents[3] / "var/counterpress.sqlite3")),
    static_dir=Path(os.environ["COUNTERPRESS_STATIC_DIR"]) if os.environ.get("COUNTERPRESS_STATIC_DIR") else None,
)
