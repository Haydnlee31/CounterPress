"""Authored multi-agent benchmark oracle; no inference or cloud writes here.

Question labels are independent of the router. Arithmetic is checked against the
existing canonical reducers, not claimed as an independent audit of those reducers.
"""
import json
from pathlib import Path

from .contracts import AskRequest, Plan
from .evaluation import canonical_answer, intent, percentile, reference
from .narrative import build_claims
from .service import fingerprint


def load_multiagent_cases(path, store):
    data = json.loads(Path(path).read_text())
    if data['ledger_sha256'] != store.manifest['files']['ledger.json.gz']:
        raise ValueError('Benchmark dataset changed; review expected scopes first')
    ids = [case['id'] for case in data['cases']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate benchmark IDs')
    for case in data['cases']:
        request = AskRequest.model_validate(case['request'])
        Plan.model_validate(case['expected_plan'])
        for task in case['tasks']:
            Plan.model_validate(task['expected_plan'])
            if not 0 <= task['start'] < task['end'] <= len(request.question):
                raise ValueError('Invalid authored question span')
        if case['tasks'] and [t['role'] for t in case['tasks']] != case['expected_roles']:
            raise ValueError('Authored route mismatch')
    return data


def expected_parts(service, case):
    """Resolve authored labels and explicit pre-match boundaries, never router output."""
    request = AskRequest.model_validate(case['request'])
    tasks = case['tasks'] or [{'role': 'match' if case['expected_plan']['operation'] == 'match' else 'career',
                              'start': 0, 'end': len(request.question),
                              'expected_plan': case['expected_plan']}]
    parts = []
    for task in tasks:
        body = request.model_copy(update={'question': request.question[task['start']:task['end']].strip()})
        if case['tasks'] and task['role'] == 'career' and request.playback:
            # The authored contract compares historical records BEFORE kickoff.
            # It must not expose end-of-match aggregates to someone mid-replay.
            kickoff = service.store.row(request.match_id)['kickoff']
            body = body.model_copy(update={'as_of': min(service.scope(request)[0], kickoff),
                                          'playback': None, 'event_id': None, 'event_revision': None})
        plan = Plan.model_validate(task['expected_plan'])
        answer = reference(service, {'expected_plan': plan.model_dump(),
                                     'request': body.model_dump(by_alias=True)})
        claims = build_claims(answer, plan, body)
        for claim in claims:
            claim['source_role'] = task['role']
            if case['tasks'] and task['role'] == 'career' and request.playback:
                claim['text'] = 'Before this match kicked off: ' + claim['text']
                claim['evidence_id'] = fingerprint({'text': claim['text'],
                    'facts': [answer['facts'][i] for i in claim['fact_indices']]})
        parts.append({'role': task['role'], 'plan': plan, 'request': body,
                      'answer': answer, 'claims': claims})
    return parts


def _sorted(values):
    return sorted(values, key=lambda value: json.dumps(value, sort_keys=True))


def _claim_identity(claim, facts):
    """IDs/indices may change in a merged answer, but their linked facts may not."""
    indices = claim.get('fact_indices', [])
    if not indices or any(type(i) is not int or i < 0 or i >= len(facts) for i in indices):
        return None
    return {'kind': claim.get('kind'), 'text': claim.get('text'),
            'evidence_id': claim.get('evidence_id'), 'facts': _sorted([facts[i] for i in indices])}


def score_multiagent(service, case, answer, duration_ms, *, execution=None):
    """Separate factual correctness from delegation/model completion and cost bounds."""
    parts = expected_parts(service, case)
    request = AskRequest.model_validate(case['request'])
    expected_facts = [fact for part in parts for fact in part['answer']['facts']]
    expected_actions = (parts[0]['answer']['actions'] if len(parts) == 1 else
                        list({a['href']: a for part in parts for a in part['answer']['actions']}.values()))
    expected_status = 'answered' if any(p['answer']['status'] == 'answered' for p in parts) else parts[0]['answer']['status']
    facts = answer.get('facts', [])
    facts_correct = _sorted(facts) == _sorted(expected_facts)
    actions_correct = _sorted(answer.get('actions', [])) == _sorted(expected_actions)
    status_correct = answer.get('status') == expected_status
    plans = (execution.get('plans') if execution and execution.get('completed_result', True) else None) or [answer['plan']]
    expected_plans = [p['plan'].model_dump() for p in parts]
    plans_correct = _sorted([intent(p) for p in plans]) == _sorted([intent(p) for p in expected_plans])
    roles = execution.get('roles', []) if execution else []
    route_correct = sorted(roles) == sorted(case['expected_roles'])
    allowed = [_claim_identity(c, p['answer']['facts']) for p in parts for c in p['claims']]
    blocks = answer.get('narrative', {}).get('blocks', [])
    identities = [_claim_identity(c, facts) for c in blocks]
    narrative_bound = (len(blocks) <= (3 if request.preferences.depth == 'analyst' else 2)
                       and len({c.get('id') for c in blocks}) == len(blocks)
                       and all(c is not None and c in allowed for c in identities)
                       and (not allowed or bool(blocks)))
    narrative_coverage = all(not part['claims'] or any(
        identity in [_claim_identity(claim, part['answer']['facts']) for claim in part['claims']]
        for identity in identities) for part in parts)
    role_bound = not execution or answer.get('mode') != 'azure_agent' or all(any(block.get('source_role') == part['role'] and
        identity in [_claim_identity(claim, part['answer']['facts']) for claim in part['claims']]
        for part in parts) for block, identity in zip(blocks, identities))
    # Exact visual checks for existing single-domain answers; cross-domain tests
    # separately prove every chart value is drawn from the expected fact bundle.
    if len(parts) == 1:
        visual_correct = canonical_answer(answer)['visual'] == canonical_answer(parts[0]['answer'])['visual']
    else:
        visual = answer.get('visual')
        chart_items = []
        chart_labels = []
        def visit(value, target):
            if not value: return
            if value.get('kind') == 'groups':
                for group in value['groups']: visit(group, target)
            elif value.get('kind') == 'bars': target.extend(value['items'])
        visit(visual, chart_items)
        allowed_items = [{'label': f['subject_name'], 'value': f['value'], 'unit': f['unit']} for f in expected_facts]
        for part in parts: visit(part['answer'].get('visual'), allowed_items)
        if visual and visual.get('kind') == 'groups':
            chart_labels = [group['label'] for group in visual['groups']]
        expected_prefixes = ['This match · ' if part['role'] == 'match' else
                             'Before kickoff · ' if request.playback else 'Player history · '
                             for part in parts if any(f['metric'] != 'selected_action' for f in part['answer']['facts'])]
        visual_correct = (bool(chart_items) and all(item in allowed_items for item in chart_items)
            and all(any(label.startswith(prefix) for label in chart_labels) for prefix in expected_prefixes)
            and all(any(label.startswith(prefix) for prefix in expected_prefixes) for label in chart_labels))
    checks = case.get('checks', {})
    anchors = []
    if 'null_metric' in checks:
        found = [f for f in facts if f['metric'] == checks['null_metric']]
        anchors.append(bool(found) and all(f['value'] is None for f in found))
    if 'forbidden_metric' in checks: anchors.append(all(f['metric'] != checks['forbidden_metric'] for f in facts))
    if 'milestone' in checks: anchors.append(any(f['metric'] == 'career_goals' and f['value'] == checks['milestone'] for f in facts))
    if 'goal_event' in checks: anchors.append(any(f['evidence'].get('event_id') == checks['goal_event'] for f in facts))
    if checks.get('no_highlight'): anchors.append(not any('highlight' in a for a in answer.get('actions', [])))
    text = ' '.join([*answer.get('text', []), *(b.get('text', '') for b in blocks)]).lower()
    framing_safe = not any(phrase.lower() in text for phrase in checks.get('forbidden_phrases', []))
    failures = (execution or {}).get('partial_failures', [])
    attempted = bool((execution or {}).get('requests', 0))
    calls_bounded = (execution or {}).get('requests', 0) <= (4 if case['tasks'] else 2)
    completed = (not case['expected_roles'] or (attempted and not failures and
        answer.get('mode') == 'azure_agent' and bool((execution or {}).get('plans')) and not answer.get('fallback_reason') and
        not answer.get('narrative', {}).get('fallback_reason')))
    checks_result = {'intent_correct': plans_correct, 'facts_correct': facts_correct,
        'actions_correct': actions_correct, 'status_correct': status_correct,
        'visual_correct': visual_correct, 'narrative_bound': narrative_bound, 'narrative_coverage': narrative_coverage,
        'narrative_role_bound': role_bound,
        'anchors_correct': all(anchors), 'framing_safe': framing_safe}
    return {'id': case['id'], 'category': case['category'], **checks_result,
        'facts_passed': all(checks_result.values()), 'routing_correct': route_correct,
        'workflow_completed': completed, 'calls_bounded': calls_bounded,
        'passed': all(checks_result.values()) and route_correct and completed and calls_bounded,
        'mode': answer.get('mode'), 'fallback': answer.get('fallback_reason'),
        'narrative_fallback': answer.get('narrative', {}).get('fallback_reason'),
        'partial_failures': failures, 'expected_roles': case['expected_roles'], 'actual_roles': roles,
        'expected_intents': [intent(p) for p in expected_plans], 'actual_intents': [intent(p) for p in plans],
        'duration_ms': duration_ms, 'execution': execution or {}}


def summarize_multiagent(rows, *, paid=False, mocked=False):
    checks = ['facts_passed', 'routing_correct', 'workflow_completed', 'calls_bounded', 'passed']
    return {'cases': len(rows), 'paid_model_calls': sum(r['execution'].get('requests', 0) for r in rows) if paid else 0,
        'mocked_provider_calls': sum(r['execution'].get('requests', 0) for r in rows) if mocked else 0,
        'metrics': {key: {'passed': sum(r[key] for r in rows), 'total': len(rows)} for key in checks},
        'latency_ms': {'p50': percentile([r['duration_ms'] for r in rows], .5),
                       'p95': percentile([r['duration_ms'] for r in rows], .95)},
        'failed_ids': [r['id'] for r in rows if not r['passed']],
        'limitations': ['Authored questions, not population accuracy.',
            'Numerical oracle uses existing canonical reducers; independent accounting audits remain necessary.',
            'Mock transport validates execution contracts, not model reasoning.' if mocked else
            'Single-run model results do not establish repeatability.' if paid else
            'Offline lookup baseline does not execute any agent.']}
