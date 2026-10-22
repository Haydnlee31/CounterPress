"""Authored-intent evaluation. A correct fallback never counts as successful AI routing.

The oracle uses the reviewed query label and existing deterministic reducers. This
checks interpretation and evidence consistency, not an independent arithmetic audit.
"""
from collections import Counter
import json
import math
import sqlite3
import time
from threading import RLock
from pathlib import Path

from .contracts import AskRequest, Plan
from .service import blank, METRICS
from .narrative import build_claims, default_story


def load_cases(path, store):
    data = json.loads(Path(path).read_text())
    if data['ledger_sha256'] != store.manifest['files']['ledger.json.gz']:
        raise ValueError('Benchmark dataset changed; review labels and temporal anchors first')
    ids = [c['id'] for c in data['cases']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate benchmark IDs')
    for case in data['cases']:
        AskRequest.model_validate(case['request'])
        Plan.model_validate(case['expected_plan'])
    return data


def intent(plan):
    """Ignore only fields that the operation never reads; keep all subject/scope fields."""
    p = Plan.model_validate(plan).model_dump()
    if p['operation'] in ('clarify', 'unsupported'):
        return {'operation': p['operation']}
    if p['operation'] != 'seasons':
        p['comparison_season'] = None
    if p['operation'] == 'recent':
        p['per90'] = True  # recent always calculates per-90 for both windows
    metrics=sorted([p['metric'],*p['additional_metrics']])
    p['metric'],p['additional_metrics']=metrics[0],metrics[1:]
    if p['operation'] == 'compare':
        p['player_ids'] = sorted(p['player_ids'])
    return p


def reference(service, case):
    expected = Plan.model_validate(case['expected_plan'])
    request = AskRequest.model_validate(case['request'])
    # The independent label defines intent, not the same regex/model under test.
    # Feed canonical subject/measure labels from the authored plan, not a parsed
    # copy of the test question. This satisfies the explicit-measure read contract.
    names = [service.store.players[p].name for p in expected.player_ids]
    if expected.club_id:
        names.append(service.store.clubs[expected.club_id].name)
    if expected.operation not in ('clarify','unsupported'):
        names.extend(METRICS[m][1] for m in [expected.metric,*expected.additional_metrics])
    query = request.model_copy(update={'question': ' '.join(names) or 'Reference', 'season': expected.season})
    with service.store.lock:
        return service.answer(expected, query)


def lookup(service, case):
    request = AskRequest.model_validate(case['request'])
    started = time.monotonic()
    planned = service.local_plan(request)
    effective = planned
    with service.store.lock:
        try:
            answer = service.answer(planned, request)
        except (ValueError, KeyError):
            effective = blank('clarify')
            answer = service.answer(effective, request)
    claims = build_claims(answer, effective, request)
    answer.update(plan=effective.model_dump(), mode='lookup', narrative={
        'mode': 'calculated', 'blocks': default_story(claims, request.preferences.depth)})
    return answer, planned.model_dump(), round((time.monotonic()-started)*1000)


def canonical_answer(answer):
    # Order is presentation; subject/metric/period/value/coverage/evidence must agree.
    facts = sorted(answer['facts'], key=lambda f: json.dumps(f, sort_keys=True))
    actions = sorted(answer['actions'], key=lambda a: json.dumps(a, sort_keys=True))
    visual = answer.get('visual')
    def canonical_visual(v):
        if not v:return v
        if v['kind']=='groups':return {**v,'groups':sorted([canonical_visual(g) for g in v['groups']],key=lambda g:g['label'])}
        if v['kind']=='bars':return {**v,'items':sorted(v['items'],key=lambda item:json.dumps(item,sort_keys=True))}
        return v
    visual=canonical_visual(visual)
    return {'status': answer['status'], 'facts': facts, 'actions': actions, 'visual': visual}


def score(service, case, answer, raw_plan, duration_ms, *, attempted=False, stage_usage=None):
    expected = reference(service, case)
    request = AskRequest.model_validate(case['request'])
    plan = Plan.model_validate(answer['plan'])
    raw_correct = raw_plan is not None and intent(raw_plan) == intent(case['expected_plan'])
    effective_correct = intent(plan) == intent(case['expected_plan'])
    evidence_correct = canonical_answer(answer) == canonical_answer(expected)
    allowed = {c['id']: c for c in build_claims(answer, plan, request)}
    blocks = answer.get('narrative', {}).get('blocks', [])
    story_valid = (len(blocks) <= (3 if request.preferences.depth == 'analyst' else 2)
                   and len({b.get('id') for b in blocks}) == len(blocks)
                   and all(b == allowed.get(b.get('id')) for b in blocks))
    checks = case.get('checks', {})
    facts = answer['facts']
    anchors = []
    if 'status' in checks: anchors.append(answer['status'] == checks['status'])
    if 'null_metric' in checks:
        found = [f for f in facts if f['metric'] == checks['null_metric']]
        anchors.append(bool(found) and all(f['value'] is None for f in found))
    if 'forbidden_metric' in checks: anchors.append(all(f['metric'] != checks['forbidden_metric'] for f in facts))
    if 'milestone' in checks: anchors.append(any(f['metric'] == 'career_goals' and f['value'] == checks['milestone'] for f in facts))
    if 'goal_total' in checks: anchors.append(any(f['subject_id'] == 'rh09' and f['metric'] == 'goals' and f['value'] == checks['goal_total'] for f in facts))
    if 'goal_event' in checks: anchors.append(any(f['evidence'].get('event_id') == checks['goal_event'] for f in facts))
    if checks.get('no_highlight'): anchors.append(not any('highlight' in a for a in answer['actions']))
    return {'id': case['id'], 'category': case['category'], 'raw_intent_correct': raw_correct,
            'effective_intent_correct': effective_correct, 'answer_evidence_correct': evidence_correct,
            'narrative_bound': story_valid, 'anchors_correct': all(anchors),
            'passed': effective_correct and evidence_correct and story_valid and all(anchors),
            'model_attempted': attempted, 'mode': answer.get('mode'),
            'fallback': answer.get('fallback_reason'), 'narrative_fallback': answer.get('narrative', {}).get('fallback_reason'),
            'duration_ms': duration_ms, 'usage': stage_usage or {},
            'expected_intent': intent(case['expected_plan']),
            'actual_intent': intent(plan), 'raw_intent': intent(raw_plan) if raw_plan else None}


def percentile(values, fraction):
    if not values: return None
    return sorted(values)[max(0, math.ceil(len(values)*fraction)-1)]


def summarize(rows):
    n = len(rows)
    metrics = ['raw_intent_correct', 'effective_intent_correct', 'answer_evidence_correct', 'narrative_bound', 'anchors_correct', 'passed']
    return {'cases': n, 'metrics': {k: {'passed': sum(r[k] for r in rows), 'total': n} for k in metrics},
            'model_routing': {'passed': sum(r['raw_intent_correct'] for r in rows if r['model_attempted']),
                              'total': sum(r['model_attempted'] for r in rows)},
            'categories': {cat: {'passed': sum(r['passed'] for r in rows if r['category'] == cat),
                                'total': sum(r['category'] == cat for r in rows)} for cat in sorted({r['category'] for r in rows})},
            'latency_ms': {'p50': percentile([r['duration_ms'] for r in rows], .5), 'p95': percentile([r['duration_ms'] for r in rows], .95)},
            'fallbacks': dict(Counter(r['fallback'] for r in rows if r['fallback'])),
            'failed_ids': [r['id'] for r in rows if not r['passed']]}


def release_gate(rows, expected_model_cases, *, azure=False, agent=False):
    """Keep factual fallback success separate from completion of the paid workflow."""
    attempted=[r for r in rows if r['model_attempted']]
    interrupted={'model_allowance_exhausted','hourly_limit','evaluation_budget','exhausted'}
    complete=not azure or (len(attempted)==expected_model_cases and
        not any(r.get('fallback') in interrupted or r.get('narrative_fallback') in interrupted for r in rows))
    routing_ok=not azure or not expected_model_cases or sum(r['raw_intent_correct'] for r in attempted)/expected_model_cases>=.9
    agent_ok=not agent or all(r['mode']=='azure_agent' and not r.get('narrative_fallback') for r in attempted)
    return 'incomplete' if not complete else 'passed' if all(r['passed'] for r in rows) and routing_ok and agent_ok else 'failed'


class AttemptBudget:
    """Persist before sending. CLI restarts cannot reset the 20-attempt hourly limit."""
    def __init__(self, path, limit=20):
        if not 1 <= limit <= 20: raise ValueError('Use 1–20 model attempts')
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS attempts(at REAL NOT NULL)')
        self.limit, self.used = limit, 0
        self.lock = RLock()

    def reserve(self):
        with self.lock, self.db:
            self.db.execute('BEGIN IMMEDIATE')
            count = self.db.execute('SELECT COUNT(*) FROM attempts WHERE at > ?', (time.time()-3600,)).fetchone()[0]
            if count >= 20 or self.used >= self.limit: return False
            self.db.execute('INSERT INTO attempts VALUES(?)', (time.time(),))
            self.used += 1
        return True

    def close(self): self.db.close()
