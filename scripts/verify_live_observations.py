"""Read-only, offline cross-fixture audit of the rolling observation boundary.

Runs the public fan service against every featured match, with two audiences,
and independently recounts the events cited by each emitted observation. This
checks accounting/causality, not whether a statistical change has a tactical cause.
"""
from collections import Counter
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from counterpress.fan.contracts import FanPreferences, MatchRequest
from counterpress.fan.service import FanService
from counterpress.personalization.contracts import Fixture
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore


def recount(events, cutoff, ceiling, observation):
    # Independent of the production snapshot/window helpers.
    latest = {}
    for e in events:
        if e.delivery_sequence > ceiling or (e.available_period, e.available_ms) > cutoff:
            continue
        if e.event_id not in latest or latest[e.event_id].revision < e.revision:
            latest[e.event_id] = e
    visible = [e for e in latest.values() if not e.retracted and (e.period, e.elapsed_ms) <= cutoff]
    windows = observation['windows']
    assert len(windows) == 2 and windows[0]['end_ms'] == windows[1]['start_ms']
    assert windows[1]['end_ms'] == cutoff[1]
    assert all(w['period'] == cutoff[0] and w['end_ms'] - w['start_ms'] == 180000
               and w['boundary'] == '(start,end]' for w in windows)
    groups = [[e for e in visible if e.period == w['period']
               and w['start_ms'] < e.elapsed_ms <= w['end_ms']
               and e.club_id == observation['club_id'] and e.kind in {'pass', 'carry', 'shot', 'recovery'}]
              for w in windows]
    expected_refs = {(e.event_id, e.revision, e.delivery_sequence) for g in groups for e in g}
    actual_refs = {(e['event_id'], e['revision'], e['delivery_sequence']) for e in observation['evidence']}
    assert expected_refs == actual_refs
    metrics = observation['metrics']
    assert metrics['sample_sizes'] == list(map(len, groups))
    if observation['kind'] == 'shots_increase':
        values = [sum(e.kind == 'shot' and e.outcome != 'own_goal' for e in g) for g in groups]
    elif observation['kind'] == 'passing_decline':
        passes = [[e for e in g if e.kind == 'pass'] for g in groups]
        assert all(e.outcome in {'complete', 'completed', 'incomplete'} for g in passes for e in g)
        numerators = [sum(e.outcome in {'complete', 'completed'} for e in g) for g in passes]
        denominators = list(map(len, passes))
        assert metrics['completed'] == numerators and metrics['attempted'] == denominators
        values = [round(100 * n / d, 3) for n, d in zip(numerators, denominators)]
    else:
        assert observation['kind'] == 'player_involvement'
        values = [sum(e.player_id == observation['player_id'] for e in g) for g in groups]
    assert values == [metrics['before'], metrics['after']]
    interpretation = observation['interpretation']
    assert interpretation['text'] == observation['text'] and observation['summary'] != observation['text']
    assert interpretation['facts'] and interpretation['evidence']
    by_id = {e.event_id: e for e in visible}
    for ref in interpretation['evidence']:
        event = by_id[ref['event_id']]
        assert event.revision == ref['revision'] and event.delivery_sequence == ref['delivery_sequence']
        assert all(event.model_dump(mode='json')[key] == value for key, value in ref.items())
    score = Counter(e.goal_for for e in visible if e.goal_for)
    assert interpretation['context']['score_for'] == score[observation['club_id']]


def main():
    root = Path(__file__).resolve().parents[1]
    store = DataStore(root / 'fixtures/personalization')
    fan = FanService(CareerService(store))
    checked = 0
    times = []
    counts = Counter()
    diagnostics = Counter()
    examples = {}
    diagnostic_examples = {}
    matches = {}
    with store.snapshot():
        for row in store.rows(featured=True):
            fixture = Fixture.model_validate_json(row['fixture'])
            events = store.events(fixture.match_id)
            favorites = sorted({a.player_id for a in fixture.appearances if a.club_id == fixture.home_id})[:12]
            audiences = [FanPreferences(), FanPreferences(favorite_club_ids=[fixture.home_id],
                         primary_club_id=fixture.home_id, favorite_player_ids=favorites, depth='analyst')]
            emitted = 0
            for period, length in enumerate(fixture.period_lengths_ms, 1):
                for end in sorted({*range(360000, length + 1, 60000), length}):
                    for prefs in audiences:
                        request = MatchRequest(preferences=prefs, cutoff={'period': period, 'elapsed_ms': end}, card_budget=5)
                        start = perf_counter()
                        result = fan.observations(fixture.match_id, request)
                        times.append((perf_counter() - start) * 1000)
                        assert result['cutoff'] == request.cutoff.model_dump()
                        for item in result['observations']:
                            recount(events, (period, end), result['through_sequence'], item)
                            counts[item['kind']] += 1
                            diagnostics[item['interpretation']['kind']] += 1
                            emitted += 1
                            examples.setdefault(item['kind'], {'match_id': fixture.match_id,
                                'cutoff': result['cutoff'], 'text': item['text'], 'metrics': item['metrics']})
                            diagnostic_examples.setdefault(item['interpretation']['kind'], {'match_id': fixture.match_id,
                                'cutoff': result['cutoff'], 'title': item['title'], 'text': item['text']})
                        checked += 1
            matches[fixture.match_id] = {'observations_checked': emitted}
    assert set(counts) == {'shots_increase', 'passing_decline', 'player_involvement'}
    report = {'status': 'passed', 'snapshots_checked': checked, 'observations_checked': sum(counts.values()),
              'by_kind': dict(counts), 'diagnostics': dict(diagnostics), 'matches': matches, 'examples': examples,
              'diagnostic_examples': diagnostic_examples,
              'local_service_latency_ms': {'median': round(median(times), 2),
                  'p95': round(sorted(times)[int(.95 * (len(times) - 1))], 2)},
              'model_calls': 0, 'cloud_calls': 0}
    destination = root / 'var/live-observations-audit.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
