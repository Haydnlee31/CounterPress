"""Isolated career-stream verification factory; no inference or write HTTP routes.

Run explicitly with uvicorn counterpress.api.phase4:create_app --factory.
The regular application does not import this module or enable this mode.
"""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from time import monotonic

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from counterpress.personalization.api import install_personalization
from counterpress.fan.api import install_fan
from counterpress.streaming.telemetry import COUNTERS


ISOLATION = {
    'PHASE4_MODE': 'isolated',
    'CONTAINER_APP_NAME': 'counterpress-phase4',
    'COUNTERPRESS_STORAGE': 'cosmos',
    'COUNTERPRESS_COSMOS_DATABASE': 'counterpress',
    'COUNTERPRESS_COSMOS_CONTAINER': 'histories-phase4',
    'COUNTERPRESS_COSMOS_AUTH': 'managed-identity',
    'COUNTERPRESS_STREAMING': 'azure',
    'COUNTERPRESS_CAREER_STREAMING': 'on',
    'COUNTERPRESS_EVENTHUB_NAME': 'deliveries-phase4',
    'COUNTERPRESS_PUBSUB_HUB': 'counterpress_phase4',
    'COUNTERPRESS_CHECKPOINT_CONTAINER': 'eventhub-checkpoints-phase4',
    'COUNTERPRESS_QUARANTINE_CONTAINER': 'rejected-deliveries-phase4',
    'COUNTERPRESS_PROFILE_DB_PATH': ':memory:',
    'COUNTERPRESS_TELEMETRY': 'off',
    'COUNTERPRESS_AGENT_TRACING': 'off',
}


def validate_environment():
    if any(os.environ.get(key) != value for key, value in ISOLATION.items()):
        raise ValueError('Phase 4 requires the complete isolated runtime configuration')


class CareerOnly:
    def history(self, *_):
        # Quarantine ordinary scenario envelopes sent to this career-only hub.
        raise ValueError('This verifier accepts career deliveries only')


def create_app(*, fixture_dir=None, static_dir=None, journal=None, runtime_factory=None):
    validate_environment()
    root = Path(fixture_dir or os.environ.get('COUNTERPRESS_FIXTURE_DIR',
                                            Path(__file__).resolve().parents[3] / 'fixtures'))
    if journal is None:
        from counterpress.storage import configured_store
        from counterpress.personalization.journal import CosmosCareerJournal
        journal = CosmosCareerJournal(configured_store(':memory:').container)
    if runtime_factory is None:
        from counterpress.streaming.azure import StreamingRuntime
        runtime_factory = StreamingRuntime

    @asynccontextmanager
    async def lifespan(app):
        runtime = runtime_factory(CareerOnly(), career)
        app.state.runtime = runtime
        try:
            await runtime.start()
            app.state.publisher = runtime.publisher
            yield
        finally:
            app.state.publisher = None
            await runtime.close()
            career().store.close()

    app = FastAPI(title='Footie isolated revision verification', lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    app.state.publisher = None
    career = install_personalization(app, root, journal)
    install_fan(app, career)
    negotiations = []

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'counterpress'}

    @app.get('/ready')
    def ready(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        try:
            career().store.revision_state()
        except Exception:
            raise HTTPException(503, 'Isolated career storage unavailable') from None
        return health()

    @app.get('/api/phase4/config')
    def config(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        return {'mode': 'isolated', 'app': 'counterpress-phase4',
                'cosmos_database': 'counterpress', 'cosmos_container': 'histories-phase4',
                'eventhub': 'deliveries-phase4', 'pubsub_hub': 'counterpress_phase4',
                'checkpoint_container': 'eventhub-checkpoints-phase4',
                'quarantine_container': 'rejected-deliveries-phase4',
                'inference': False, 'dataset': career().store.dataset}

    @app.get('/api/phase4/telemetry')
    def telemetry(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        telemetry = app.state.runtime.telemetry
        # A read never resets counters, advances checkpoints or exports content.
        return {'schema': 'phase4_counters_v1',
                **{name: telemetry.counts[name] for name in COUNTERS},
                'observed_backlog': telemetry.backlog,
                'pending': telemetry.pending_since is not None}

    @app.get('/api/data/revisions/negotiate')
    async def negotiate(response: Response):
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        if app.state.publisher is None:
            raise HTTPException(503, 'Revision delivery unavailable')
        now = monotonic()
        negotiations[:] = [at for at in negotiations if now - at < 60]
        if len(negotiations) >= 30:
            raise HTTPException(429, 'Revision delivery busy', headers={'Retry-After': '60'})
        negotiations.append(now)
        try:
            state = await run_in_threadpool(lambda: career().store.revision_state())
            return await app.state.publisher.negotiate_career(state['dataset'])
        except Exception:
            raise HTTPException(503, 'Revision delivery unavailable') from None

    directory = static_dir or os.environ.get('COUNTERPRESS_STATIC_DIR')
    if directory:
        directory = Path(directory).resolve()
        if not (directory / 'index.html').is_file() or not (directory / 'assets').is_dir():
            raise ValueError('Compiled frontend required')

        @app.get('/', include_in_schema=False)
        def frontend():
            return FileResponse(directory / 'index.html', headers={'Cache-Control': 'no-store'})

        app.mount('/assets', StaticFiles(directory=directory / 'assets'))
    return app
