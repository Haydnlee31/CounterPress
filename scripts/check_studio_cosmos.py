"""Live Studio durability checks in isolated verification partitions, never match data.

Run seed and verify in separate processes using the existing Cosmos managed
identity. No model configuration, app settings or identity roles are modified.
"""
import argparse
import json
import os
from pathlib import Path
import re
from pydantic import TypeAdapter

from counterpress.api.snapshots import SnapshotService
from counterpress.cosmos_check import ScopedStore
from counterpress.domain.models import Event
from counterpress.storage import configured_store
from counterpress.studio.service import StudioService, ReviewRequest, DecisionRequest, ReviewConflict

ACTOR = '0' * 64  # Explicit probe actor, never represented as a human approval.


def request(view):
    return DecisionRequest(preferences=view.recap.preferences, fingerprint=view.fingerprint)


def denied_export(service, view):
    try:
        service.export('increase', request(view))
    except ReviewConflict:
        return True
    raise AssertionError('An invalid approval was exported')


def check(phase, scope, store, fixtures):
    scoped = ScopedStore(store, 'studio-'+scope)
    service = StudioService(SnapshotService(fixtures if phase == 'seed' else Path('/missing-studio-fixtures'), scoped))
    if phase == 'seed':
        if scoped.read('increase') is not None:
            raise ValueError('Verification scope already exists; never reset its history')
        view = service.review('increase', ReviewRequest())
        approved = service.decide('increase', request(view), ACTOR, 'approve')
        assert approved.status == 'approved' and approved.fingerprint in service.export('increase', request(view))
        assert service.decide('increase', request(view), ACTOR, 'approve') == approved
        revoked = service.decide('increase', request(view), ACTOR, 'revoke')
        assert revoked.status == 'revoked' and denied_export(service, view)
        service.decide('increase', request(view), ACTOR, 'approve')
        revisions = TypeAdapter(tuple[Event, ...]).validate_json((fixtures/'faults/recovery_corrections.json').read_text())
        for revision in revisions:
            service.snapshots.ingest('increase', (revision,))
            assert denied_export(service, view)
            assert service.review('increase', ReviewRequest()).status in ('changed', 'unavailable')
        current = service.review('increase', ReviewRequest())
        approved = service.decide('increase', request(current), ACTOR, 'approve')
        assert approved.status == 'approved' and approved.fingerprint != view.fingerprint
    current = service.review('increase', ReviewRequest())
    assert current.status == 'approved' and current.approval_id
    assert current.fingerprint in service.export('increase', request(current))
    history = service.snapshots.history('increase')
    assert len(history.records) == 93
    assert [d.decision for d in history.studio_decisions] == ['approve', 'revoke', 'approve', 'approve']
    old = DecisionRequest(fingerprint=history.studio_decisions[0].fingerprint)
    try:
        service.export('increase', old)
    except ReviewConflict:
        pass
    else:
        raise AssertionError('Old approval survived the correction')
    return {'phase':phase, 'isolated_partition':True, 'durable_decisions':4, 'source_records':93,
            'current_approval_export':True, 'old_approval_rejected':True,
            'fixture_free_restore':phase=='verify', 'synthetic_probe_actor':True, 'model_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('seed','verify'))
    parser.add_argument('--scope',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]{1,32}',args.scope):parser.error('Invalid verification scope')
    if os.environ.get('COUNTERPRESS_STORAGE')!='cosmos':parser.error('Explicit Cosmos storage required')
    try:
        report=check(args.phase,args.scope,configured_store(':memory:'),Path(os.environ.get('COUNTERPRESS_FIXTURE_DIR','fixtures')))
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        print('PASS: isolated Studio approval, revocation, correction and durability checks; zero model calls.',flush=True)
    except Exception:
        parser.exit(1,'FAIL: Studio Cosmos verification failed; private diagnostics omitted.\n')


if __name__=='__main__':main()
