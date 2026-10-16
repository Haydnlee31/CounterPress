"""Frozen development pilot: templates vs one editor vs Analyst/Producer.

Offline by default. --live explicitly permits bounded paid calls using local
configuration. Every variant gets a fresh private SQLite history; no cloud writes.
"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
import logging
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter

import httpx2
from agent_framework import EvalItem, LocalEvaluator, Message, evaluator

from counterpress.adaptation.azure import load_config
from counterpress.api.snapshots import SCENARIOS, SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.domain.models import Event
from counterpress.history import SQLiteHistoryStore
from counterpress.recaps import build_recap
from counterpress.workflow.recap_service import RecapWorkflowService
from counterpress.workflow.single_editor import SingleEditorService
from counterpress.evaluation.meter import Meter, MeteredTransport

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / 'fixtures/evaluation/editorial_cases.json'
LOCK = ROOT / 'fixtures/evaluation/editorial_lock.json'


def locked_files():
    return [MANIFEST, *(ROOT/'fixtures'/name for name, _ in SCENARIOS.values()),
            ROOT/'fixtures/faults/recovery_corrections.json',
            ROOT/'uv.lock', *(ROOT/'backend/counterpress').rglob('*.py')]


def source_hashes():
    return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(set(locked_files()))}


def verified_cases():
    lock = json.loads(LOCK.read_text())
    if lock['files'] != source_hashes():
        raise ValueError('Frozen cases or prompts changed; version and review the pilot before running again')
    return json.loads(MANIFEST.read_text()), sha256(LOCK.read_bytes()).hexdigest()


def prepare(case):
    app = SnapshotService(ROOT/'fixtures', SQLiteHistoryStore(':memory:'))
    app.history(case['scenario'])
    if 'corrections_through' in case:
        records = [Event.model_validate(r) for r in json.loads(
            (ROOT/'fixtures/faults/recovery_corrections.json').read_text())
            if r['available_at']['elapsed_ms'] <= case['corrections_through']]
        app.ingest(case['scenario'], records)
        if case.get('duplicate_reversed'):
            app.ingest(case['scenario'], tuple(reversed(records)) + tuple(records))
    prefs = ViewingPreferences(**case['preferences'])
    snapshot = app.snapshot(case['scenario'], case['at_ms'], preferences=prefs)
    check_oracle(case, snapshot)
    return app, prefs, snapshot


def check_oracle(case, snapshot):
    """Hand-written scenario expectations, not generated model expectations."""
    recap = snapshot.recap
    assert recap.state == case['expected_state'], case['id']
    assert not any(s.citation.kind == case.get('forbidden_kind') for s in recap.statements), case['id']
    expected = case.get('required_fact')
    if not expected:
        return
    found = False
    for statement in recap.statements:
        c = statement.citation
        if c.kind == 'recovery':
            packet = snapshot.lifecycle.evidence.packet
            actual = {'metric': packet.metric, 'team': packet.subject_team_id,
                      'before': [packet.baseline.value], 'after': [packet.current.value]}
        elif c.kind == 'pressure':
            pub = next(p for p in snapshot.pressure_lifecycle if p.insight_id == c.insight_id and p.revision == c.revision)
            d = pub.decision
            actual = {'metric': d.metric, 'team': pub.evidence.subject_team_id,
                      'before': [d.baseline_numerator, d.baseline_denominator],
                      'after': [d.current_numerator, d.current_denominator]}
        else:
            pub = next(p for p in snapshot.contribution_lifecycle if p.insight_id == c.insight_id and p.revision == c.revision)
            e = pub.evidence
            actual = {'metric': e.metric, 'team': e.subject_team_id,
                      'before': [e.baseline.player_count, e.baseline.team_count],
                      'after': [e.current.player_count, e.current.team_count]}
        found |= actual == expected
    assert found, f"Independent fact expectation failed: {case['id']}"


def validate_presentation(source, displayed, brief):
    """Allow only a ranked subset of exact citations and code-owned variants."""
    by_id = {s.citation.insight_id: s for s in source.statements}
    short = {s.citation.insight_id: s for s in brief.statements}
    selected = [s.citation.insight_id for s in displayed.statements]
    if (len(set(selected)) != len(selected) or any(i not in by_id for i in selected)
            or selected != [s.citation.insight_id for s in source.statements if s.citation.insight_id in selected]
            or displayed.match_id != source.match_id or displayed.cutoff != source.cutoff
            or displayed.windows != source.windows or displayed.preferences != source.preferences
            or displayed.state != source.state
            or displayed.omitted_count != source.omitted_count + len(source.statements) - len(selected)):
        return False
    for statement in displayed.statements:
        original = by_id[statement.citation.insight_id]
        allowed_short = original.model_copy(update={'narrative': original.narrative.model_copy(update={
            'explanation': short[statement.citation.insight_id].narrative.explanation})})
        if statement not in (original, allowed_short):
            return False
    return not source.statements or bool(selected)


@evaluator
def supported_presentation(response: str) -> bool:
    return json.loads(response)['supported_presentation'] is True


@evaluator
def ineligible_requests_are_free(response: str) -> bool:
    row = json.loads(response)
    return row['model_eligible'] or row['dispatched_requests'] == 0


def summarize(rows):
    report = {}
    for variant in sorted(set(r['variant'] for r in rows)):
        group = [r for r in rows if r['variant'] == variant]
        eligible = [r for r in group if r['model_eligible']]
        durations = sorted(r['duration_ms'] for r in eligible)
        costs = [r['observed_estimated_usd'] for r in group]
        accepted = sum(r['status'] in ('accepted', 'narrowed') for r in eligible)
        missing = sum(r['usage_missing_requests'] for r in group)
        report[variant] = {
            'samples': len(group), 'eligible_samples': len(eligible),
            'statuses': dict(Counter(r['status'] for r in group)),
            'accepted': accepted,
            'fallbacks_on_eligible': sum(r['fallback'] for r in eligible),
            'latency_ms_p50': median(durations) if durations else None,
            # Small pilots should not advertise a production P95.
            'latency_ms_p95': durations[ceil(.95*len(durations))-1] if len(durations) >= 20 else None,
            'latency_ms_max': max(durations, default=None),
            'dispatched_requests': sum(r['dispatched_requests'] for r in group),
            'input_tokens_observed': sum(r['input_tokens_observed'] for r in group),
            'output_tokens_observed': sum(r['output_tokens_observed'] for r in group),
            'usage_missing_requests': missing,
            'observed_estimated_usd': round(sum(costs), 8),
            'estimated_usd_per_accepted_including_failures': round(sum(costs)/accepted, 8) if accepted and not missing else None,
            'supported_presentations': sum(r['supported_presentation'] for r in group),
        }
    return report


async def evaluate_suite(*, live=False, repetitions=1, config=None, transport_factory=None):
    manifest, lock_hash = verified_cases()
    if not 1 <= repetitions <= 2:
        raise ValueError('pilot supports one or two repetitions')
    if live and config is None:
        raise ValueError('live evaluation requires complete local Azure configuration')
    meter = Meter()
    rows = []
    variants = ['template', 'single_editor', 'analyst_producer'] if live else ['template']
    for repetition in range(repetitions):
        for index, case in enumerate(manifest['cases']):
            # Rotate execution order to reduce a fixed warmup/order advantage.
            rotation = (index + repetition) % len(variants)
            for variant in variants[rotation:] + variants[:rotation]:
                started = perf_counter()
                app, prefs, before = prepare(case)
                start_receipt = len(meter.receipts)
                attempt = None
                if variant != 'template':
                    implementation = SingleEditorService if variant == 'single_editor' else RecapWorkflowService
                    inner = transport_factory or (lambda: httpx2.AsyncHTTPTransport(retries=0))
                    service = implementation(app, config,
                        transport_factory=lambda: MeteredTransport(meter, inner()))
                    attempt = await service.run(case['scenario'], case['at_ms'], prefs)
                after = app.snapshot(case['scenario'], case['at_ms'], preferences=prefs)
                displayed = after.adapted_recap or after.recap
                brief = build_recap(app.history(case['scenario']), before.recap.cutoff,
                                    before.recap.windows, prefs.model_copy(update={'depth': 'casual'}))
                receipts = meter.receipts[start_receipt:]
                supported = (before.recap == after.recap
                             and validate_presentation(before.recap, displayed, brief))
                rows.append({
                    'case_id': case['id'], 'repetition': repetition + 1, 'variant': variant,
                    'model_eligible': case['model_eligible'],
                    'status': attempt.status if attempt else 'template',
                    'reason': attempt.reason if attempt else 'deterministic_baseline',
                    'duration_ms': round((perf_counter()-started)*1000),
                    'workflow_duration_ms': attempt.duration_ms if attempt else 0,
                    'fallback': variant != 'template' and after.adapted_recap is None,
                    'supported_presentation': supported,
                    'source_stories': len(before.recap.statements), 'displayed_stories': len(displayed.statements),
                    'changed_presentation': displayed != before.recap,
                    'dispatched_requests': len(receipts),
                    'tool_invocations': attempt.tool_invocations if attempt else 0,
                    'input_tokens_observed': sum(r['input_tokens'] or 0 for r in receipts),
                    'output_tokens_observed': sum(r['output_tokens'] or 0 for r in receipts),
                    'usage_missing_requests': sum(r['estimated_usd'] is None for r in receipts),
                    'observed_estimated_usd': sum(r['estimated_usd'] or 0 for r in receipts),
                    'admission_estimate_usd': sum(r['admission_estimate_usd'] for r in receipts),
                    # Only validated, application-rendered text; never provider prose.
                    'presentation': displayed.model_dump(mode='json'),
                })
    items = [EvalItem(conversation=[Message('user', [r['case_id']]),
                                   Message('assistant', [json.dumps(r)])]) for r in rows]
    scores = await LocalEvaluator(supported_presentation, ineligible_requests_are_free).evaluate(
        items, eval_name=manifest['version'])
    return {
        'suite': manifest['version'], 'split': manifest['split'], 'lock_sha256': lock_hash,
        'packages': {p: version(p) for p in ('agent-framework-core', 'agent-framework-openai', 'openai')},
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'mode': 'live' if live else 'offline_templates_only', 'repetitions': repetitions,
        'evaluator': 'Microsoft Agent Framework LocalEvaluator; deterministic checks, no paid judge',
        'checks': scores.result_counts, 'per_check': scores.per_evaluator,
        'human_usefulness_ratings': None,
        'cost': {'currency': 'USD', 'input_rate_per_million': str(meter.input_usd_per_million),
                 'output_rate_per_million': str(meter.output_usd_per_million),
                 'admission_allowance_usd': str(meter.allowance_usd),
                 'reserved_estimate_usd': str(meter.reserved_usd), 'max_requests': meter.max_requests,
                 'note': 'Conservative uncached regional tariff estimate, not invoiced cost. Missing usage is unknown; cached-input discounts omitted.'},
        'summary': summarize(rows), 'rows': rows,
        'limitations': ['Development pilot; fixtures are previously used and not a held-out evaluation',
                       'P95 omitted for fewer than 20 eligible samples per variant',
                       'Structural validity is not proof of fan usefulness',
                       'Fallbacks count as valid presentations but not successful AI adaptations',
                       'No hosted AI activation, Cosmos writes, new service or automated user study'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--repetitions', type=int, choices=[1, 2], default=1)
    parser.add_argument('--output', type=Path, default=Path('var/editorial-evaluation.json'))
    args = parser.parse_args()
    for name in ('agent_framework', 'openai', 'httpx', 'httpx2', 'httpcore'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        result = asyncio.run(evaluate_suite(live=args.live, repetitions=args.repetitions,
                                            config=load_config() if args.live else None))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({k: result[k] for k in ('mode', 'checks', 'summary')}, indent=2))
        raise SystemExit(0 if result['checks']['failed'] == 0 and result['checks']['errored'] == 0 else 2)
    except (OSError, ValueError, AssertionError):
        parser.error('Evaluation could not complete; check the frozen suite and local configuration. No provider diagnostics are printed.')


if __name__ == '__main__':
    main()
