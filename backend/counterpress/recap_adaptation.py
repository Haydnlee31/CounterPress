"""Approved recap presentation and revision-bound cache keys, without model calls."""

from hashlib import sha256
import json

from counterpress.recaps import SegmentRecap, build_recap
from counterpress.workflow.recap_contracts import RecapDraft, RecapWorkflowView, StoryIdentity


def identities(recap: SegmentRecap) -> tuple[StoryIdentity, ...]:
    return tuple(StoryIdentity.model_validate(s.citation.model_dump(exclude={'available_at'})) for s in recap.statements)


def fingerprint(recap: SegmentRecap, score: dict, source_version: int) -> str:
    frozen = {'template_version': 'recap-presentation-v1', 'recap': recap.model_dump(mode='json'),
              'score': score, 'source_version': source_version}
    return sha256(json.dumps(frozen, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_draft(draft: RecapDraft, key: str, language: str, selected: tuple[StoryIdentity, ...]):
    actual = tuple(StoryIdentity.model_validate(s.model_dump(exclude={'template'})) for s in draft.stories)
    if draft.fingerprint != key or draft.language != language or actual != selected or not 1 <= len(actual) <= 4:
        raise ValueError('producer must preserve reviewed identities, order, fingerprint and language')


def present_recap(history, recap: SegmentRecap, score, now: int):
    """A changed source, cutoff, viewpoint or expired attempt uses factual fallback."""
    attempt = next((a for a in reversed(history.recap_workflows)
                    if a.preferences == recap.preferences and a.match_id == recap.match_id
                    and a.requested_at.key() <= recap.cutoff.key()
                    and a.available_at.key() <= recap.cutoff.key()), None)
    if attempt is None or recap.state != 'ready':
        return recap, None
    status = attempt.status
    if attempt.fingerprint != fingerprint(recap, score, len(history.records)):
        status = 'stale'
    elif not attempt.started_at_unix_ms <= now < attempt.expires_at_unix_ms:
        status = 'expired'
    applied = status in ('accepted', 'narrowed') and attempt.draft is not None
    view = RecapWorkflowView(attempt_id=attempt.attempt_id, status=status, actions=attempt.actions,
                            applied=applied, heading=attempt.draft.heading if applied else None,
                            expires_at_unix_ms=attempt.expires_at_unix_ms)
    if not applied:
        return recap, view
    draft = attempt.draft
    allowed = identities(recap)
    selected = tuple(StoryIdentity.model_validate(s.model_dump(exclude={'template'})) for s in draft.stories)
    if len(set(s.insight_id for s in selected)) != len(selected) or any(s not in allowed for s in selected):
        raise ValueError('stored recap plan no longer matches the factual recap')
    validate_draft(draft, attempt.fingerprint, recap.preferences.language, selected)
    brief = build_recap(history, recap.cutoff, recap.windows, recap.preferences.model_copy(update={'depth': 'casual'}))
    by_id = {s.citation.insight_id: s for s in recap.statements}
    short = {s.citation.insight_id: s for s in brief.statements}
    rendered = []
    for choice in draft.stories:
        statement = by_id[choice.insight_id]
        if choice.template == 'brief':
            # Only code-rendered wording changes; names, fractions, windows and
            # qualifications still come from the same frozen evidence.
            statement = statement.model_copy(update={'narrative': statement.narrative.model_copy(update={
                'explanation': short[choice.insight_id].narrative.explanation})})
        rendered.append(statement)
    return recap.model_copy(update={'statements': tuple(rendered),
                                   'omitted_count': recap.omitted_count + len(recap.statements)-len(rendered)}), view
