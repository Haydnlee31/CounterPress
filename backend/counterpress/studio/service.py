"""Review the latest factual presentation inside the source-history transaction."""
from hashlib import sha256
from html import escape
import json
from time import time
from uuid import uuid4
from typing import Literal

from pydantic import Field
from counterpress.api.snapshots import BASELINE, CURRENT, horizon
from counterpress.audience import ViewingPreferences
from counterpress.domain.models import Contract, Event
from counterpress.recaps import SegmentRecap, build_recap
from counterpress.replay import display_time
from counterpress.studio.contracts import ReviewDecision


class ReviewRequest(Contract):
    preferences: ViewingPreferences = Field(default_factory=ViewingPreferences)


class DecisionRequest(ReviewRequest):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')


class SupportingEvidence(Contract):
    evidence_id: str
    revision: int
    definition: str
    records: tuple[Event, ...]


class ReviewView(Contract):
    fingerprint: str
    source_version: int
    recap: SegmentRecap
    status: Literal['unreviewed', 'approved', 'revoked', 'changed', 'unavailable']
    evidence: tuple[SupportingEvidence, ...]
    approval_id: str | None = None
    approved_at_unix_ms: int | None = None


class ReviewConflict(Exception):
    pass


def review_view(history, preferences):
    # This slice deliberately uses deterministic wording; no model invocation or
    # expiring model presentation can silently change an approved artifact.
    recap = build_recap(history, horizon(history), (BASELINE, CURRENT), preferences)
    evidence = []
    for statement in recap.statements:
        citation = statement.citation
        stream = {'recovery': history.changes, 'pressure': history.pressure_changes,
                  'contribution': history.contribution_changes}[citation.kind]
        publication = next(c for c in stream if c.insight_id == citation.insight_id and c.revision == citation.revision)
        bundle = publication.evidence
        definition = bundle.metric_definition if citation.kind == 'recovery' else bundle.disclosure
        evidence.append(SupportingEvidence(evidence_id=citation.evidence_id, revision=citation.revision,
                                          definition=definition, records=bundle.records))
    payload = {'version': 'studio-factual-v1', 'recap': recap.model_dump(mode='json'),
               'sources': [r.model_dump(mode='json') for r in history.records],
               'evidence': [e.model_dump(mode='json') for e in evidence]}
    fingerprint = sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    decision = next((d for d in reversed(history.studio_decisions) if d.fingerprint == fingerprint), None)
    status = ('unavailable' if recap.state != 'ready' else
              'approved' if decision and decision.decision == 'approve' else
              'revoked' if decision else 'changed' if history.studio_decisions else 'unreviewed')
    approved = decision if status == 'approved' else None
    return ReviewView(fingerprint=fingerprint, source_version=len(history.records), recap=recap, status=status, evidence=tuple(evidence),
                      approval_id=approved.decision_id if approved else None,
                      approved_at_unix_ms=approved.at_unix_ms if approved else None)


class StudioService:
    def __init__(self, snapshots, now=lambda: int(time() * 1000)):
        self.snapshots, self.now = snapshots, now

    def review(self, scenario, request):
        return review_view(self.snapshots.history(scenario), request.preferences)

    def decide(self, scenario, request, actor, decision):
        self.snapshots.history(scenario)  # validate/seed before transaction
        record = ReviewDecision(decision_id=f'review-{uuid4().hex}', fingerprint=request.fingerprint,
                                actor=actor, decision=decision, at_unix_ms=self.now())

        def commit(history):
            view = review_view(history, request.preferences)
            if view.fingerprint != request.fingerprint or view.recap.state != 'ready':
                raise ReviewConflict('Evidence or perspective changed. Review the latest version.')
            # Repeat clicks/retries are idempotent, including after restart.
            if view.status == ('approved' if decision == 'approve' else 'revoked'):
                return history
            if decision == 'revoke' and view.status != 'approved':
                raise ReviewConflict('There is no current approval to revoke.')
            return history.model_copy(update={'studio_decisions': (*history.studio_decisions, record)})

        result = self.snapshots.store.transact(scenario, commit)
        return review_view(result, request.preferences)

    def export(self, scenario, request):
        # Fresh canonical read; never trust a client-side approved flag or prose.
        view = self.review(scenario, request)
        if view.fingerprint != request.fingerprint or view.status != 'approved':
            raise ReviewConflict('Approval is no longer current. Review the latest version.')
        return render_export(view)


def render_export(view):
    """Self-contained, script-free, escaped and explicitly point-in-time artifact."""
    recap = view.recap
    cards = ''.join(f'<article><h2>{escape(s.narrative.title)}</h2><p>{escape(s.narrative.explanation)}</p>'
        f'<p>{escape(s.narrative.qualification)}</p><small>Evidence: {escape(s.citation.evidence_id)} · '
        f'revision {s.citation.revision}</small></article>' for s in recap.statements)
    windows = ' → '.join(f'({display_time(w.start)}, {display_time(w.end)}]' for w in recap.windows)
    return f'''<!doctype html><html lang="{recap.preferences.language}"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>CounterPress · Producer snapshot</title><style>body{{font:18px/1.6 system-ui;max-width:960px;margin:40px auto;padding:24px;color:#14332e;background:#f4f4eb}}article{{padding:24px;border:1px solid #9baaa5;margin:24px 0}}small,footer{{overflow-wrap:anywhere}}h1,h2{{line-height:1.15}}</style>
<header><p>COUNTERPRESS / STUDIO</p><h1>Producer snapshot</h1><p>Synthetic football · Fictional teams and players</p>
<p>Facts through {display_time(recap.cutoff)} · Windows {windows} · Start excluded, end included.</p></header>
{cards}<footer><p>Approved snapshot, not a live broadcast. Later corrections or revocations cannot recall this downloaded file. Recheck Studio before use.</p>
<p>Approval: {escape(view.approval_id)} · Source version {view.source_version}<br>Fingerprint: {view.fingerprint}</p></footer></html>'''
