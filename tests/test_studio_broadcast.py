"""Broadcast artifacts must retain approved claims, caveats and authorization."""
from html import escape

import pytest

from counterpress.studio.service import BroadcastRequest, ReviewRequest, ReviewConflict
from counterpress.studio.broadcast import render_broadcast
from test_studio import services, decision, ACTOR
from test_studio_editorial import draft, request
from test_history import updates


def selection(view, format='presenter-cue', **changes):
    return BroadcastRequest(**(request(view).model_dump() | {
        'insight_id': view.recap.statements[0].citation.insight_id, 'format': format} | changes))


@pytest.mark.parametrize('format', ['presenter-cue', 'lower-third'])
def test_broadcast_requires_current_approval_and_keeps_entire_selected_statement(services, format):
    service = services()
    view = service.review('increase', ReviewRequest())
    req = selection(view, format)
    with pytest.raises(ReviewConflict): service.broadcast('increase', req)
    approved = service.decide('increase', decision(view), ACTOR, 'approve')
    body = services().broadcast('increase', req)
    first = view.recap.statements[0]
    for text in (first.narrative.title, first.narrative.explanation, first.narrative.qualification,
                 first.citation.evidence_id, approved.approval_id, view.fingerprint, view.recap.match_id):
        assert escape(text) in body
    for other in view.recap.statements[1:]:
        assert escape(other.citation.evidence_id) not in body
    assert 'Synthetic football' in body and 'cannot recall' in body and 'UTC' in body
    assert 'Start excluded, end included' in body and '<script' not in body
    with pytest.raises(ReviewConflict): service.broadcast('increase', selection(view, insight_id='unapproved-story'))
    with pytest.raises(ReviewConflict): service.broadcast('pressure-increase', req)
    service.decide('increase', decision(view), ACTOR, 'revoke')
    with pytest.raises(ReviewConflict): services().broadcast('increase', req)


def test_corrections_and_withdrawals_block_both_formats(services):
    service = services()
    view = service.review('increase', ReviewRequest())
    service.decide('increase', decision(view), ACTOR, 'approve')
    for event in updates():
        service.snapshots.ingest('increase', (event,))
        for format in ('presenter-cue', 'lower-third', 'presenter-text'):
            with pytest.raises(ReviewConflict): service.broadcast('increase', selection(view, format))


@pytest.mark.parametrize('race', ['correction', 'revoke', 'expiry'])
@pytest.mark.parametrize('format', ['presenter-cue', 'presenter-text'])
def test_change_during_render_fails_closed(services, monkeypatch, race, format):
    service = services()
    attempt = draft(service) if race == 'expiry' else None
    view = service.review('increase', ReviewRequest(attempt_id=attempt.attempt_id if attempt else None))
    service.decide('increase', request(view), ACTOR, 'approve')
    def render(*args):
        body = render_broadcast(*args)
        if race == 'correction': service.snapshots.ingest('increase', (updates()[0],))
        elif race == 'revoke': service.decide('increase', request(view), ACTOR, 'revoke')
        else: service.now = lambda: attempt.expires_at_unix_ms
        return body
    monkeypatch.setattr('counterpress.studio.service.render_broadcast', render)
    with pytest.raises(ReviewConflict): service.broadcast('increase', selection(view, format))


def test_broadcast_escapes_copy_and_keeps_unicode(services):
    service = services()
    from counterpress.audience import ViewingPreferences
    view = service.review('increase', ReviewRequest(preferences=ViewingPreferences(language='zh-Hans')))
    view = service.decide('increase', decision(view), ACTOR, 'approve')
    statement = view.recap.statements[0]
    hostile = statement.model_copy(update={'narrative': statement.narrative.model_copy(update={
        'title': '<script>alert(1)</script>', 'qualification': '限制 <img src=x onerror=alert(1)>'})})
    for format in ('presenter-cue', 'lower-third'):
        body = render_broadcast(view, hostile, format, 1000)
        assert '<script>' not in body and '<img' not in body
        assert '&lt;script&gt;' in body and '限制' in body and 'lang="zh-Hans"' in body


def test_plain_text_copy_preserves_wording_and_rechecks_approval(services):
    service = services()
    view = service.review('increase', ReviewRequest())
    req = selection(view, 'presenter-text')
    with pytest.raises(ReviewConflict):
        service.broadcast('increase', req)
    service.decide('increase', decision(view), ACTOR, 'approve')
    body = service.broadcast('increase', req)
    statement = view.recap.statements[0]
    assert body.startswith('\n\n'.join((statement.narrative.title, statement.narrative.explanation, statement.narrative.qualification)))
    assert statement.citation.evidence_id in body and view.fingerprint in body
    assert '<html' not in body
    service.snapshots.ingest('increase', (updates()[0],))
    with pytest.raises(ReviewConflict):
        service.broadcast('increase', req)
