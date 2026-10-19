"""Read-only catalog unifying existing short replays and career-linked excerpts.

Full matches never enter this catalog. Legacy showcase IDs remain stable for the
existing player; parent references never create additional career appearances.
"""
import json
from counterpress.fixture import load_fixture
from .presentation import action, fingerprint, words


TITLES = {
    'last-gasp': ('Last-second turnaround', '最后一刻的逆转'),
    'one-touch': ('Pass, move, finish', '传球、跑位、射门'),
    'breakaway': ('From halfway to goal', '从中场直奔球门'),
    'level-first': ('Cole brings it level', 'Cole扳平比分'),
    'take-lead': ('Hayes puts Eastbridge ahead', 'Hayes帮助Eastbridge领先'),
    'level-late': ('Fletcher answers back', 'Fletcher还以颜色'),
}


def completed_at(career, row, cutoff):
    if row['kickoff'] >= cutoff:
        return None
    at = career.historical_cutoff(row, cutoff)
    return None if at is False else at


def highlight_cards(service, p, cutoff, season):
    store = service.store; root = store.root.parent
    result = []
    # Only completed parent fixtures enter the home feed. Live milestone cards
    # use /fan/matches at the explicit playhead instead.
    metadata = json.loads((root / 'showcases/generated_manifest.json').read_text())
    old_clips = {c['scenario_id']: c for c in metadata['highlights']}
    for sid, title in TITLES.items():
        fixture = load_fixture(root / 'showcases' / (sid.replace('-', '_') + '.json' if sid in ('last-gasp', 'one-touch') else sid + '.json'))
        if service.snapshots:
            history = service.snapshots.store.read(sid)
            # Authored titles are only valid against their reviewed source.
            if history and history.records != fixture.events:
                continue
        parent = metadata['parent_match_id'] if sid in old_clips else None
        date = None; evidence = {'source_match_id': fixture.match_id,
            'events': [{'event_id': e.event_id, 'revision': e.revision} for e in fixture.events]}
        if parent:
            row = store.row(parent); at = completed_at(service.career, row, cutoff)
            if at is None or season and row['season'] != season:
                continue
            if store.evidence_digest(parent, at) != row['digest']:
                continue
            date = row['kickoff'][:10]
            evidence.update(parent_match_id=parent, event_digest=row['digest'])
        elif season:
            # Preloaded standalone reconstructions do not claim a league season.
            continue
        participants = set()
        for e in fixture.events:
            participants.add(e.actor.player_id)
            for name in ('recipient', 'opponent', 'goalkeeper'):
                actor = getattr(e.action, name, None)
                if actor:
                    participants.add(actor.player_id)
        clubs = [t.team_id for t in fixture.teams]
        result.append({'highlight_id': sid, 'match_id': parent, 'tag': 'match' if parent else 'preloaded',
            'date': date, 'title': words(p, *title), 'player_ids': sorted(participants), 'club_ids': clubs,
            'relevance': service.relevance(participants, clubs, p), 'evidence': evidence,
            'content_version': fingerprint(evidence), 'sort_order': 1 if sid == 'last-gasp' else 2,
            'action': action('highlight', sid, words(p, 'Watch highlight', '观看集锦'), scenario_id=sid)})
    for clip in json.loads((store.root / 'highlights.json').read_text()):
        mid = clip['match_id']; row = store.row(mid)
        at = completed_at(service.career, row, cutoff)
        if at is None or season and row['season'] != season or store.evidence_digest(mid, at) != row['digest']:
            continue
        record = store.original(mid)
        events = [e for e in record.events if e.event_id in clip['event_ids']]
        participants = sorted({pid for e in events for pid in (e.player_id, e.recipient_id, e.opponent_id, e.goalkeeper_id) if pid})
        scorer = store.players[clip['scorer_id']].name
        live = service.career.live(mid, clip['end']['period'], clip['end']['elapsed_ms'])
        milestone = next((m for m in live['milestones'] if m['event_id'] == clip['goal_event_id']), None)
        if milestone:
            en, zh = f'{scorer} reaches {milestone["career_goals"]} career goals', f'{scorer}达成生涯{milestone["career_goals"]}球'
        elif len(set(live['score'].values())) == 1:
            en, zh = f'{scorer} brings the teams level', f'{scorer}扳平比分'
        else:
            club = store.players[clip['scorer_id']].club_id
            opponent = row['away'] if club == row['home'] else row['home']
            if live['score'][club] > live['score'][opponent]:
                en, zh = f'{scorer} puts {store.clubs[club].name} ahead', f'{scorer}帮助{store.clubs[club].name}领先'
            else:
                en, zh = f'{scorer} scores for {store.clubs[club].name}', f'{scorer}为{store.clubs[club].name}进球'
        evidence = {'parent_match_id': mid, 'event_digest': row['digest'], 'baseline_id': live['baseline']['id'],
                    'events': [{'event_id': e.event_id, 'revision': e.revision} for e in events]}
        clubs = [row['home'], row['away']]
        result.append({'highlight_id': clip['highlight_id'], 'match_id': mid, 'tag': 'match',
            'date': clip['date'], 'title': words(p, en, zh), 'player_ids': participants, 'club_ids': clubs,
            'relevance': service.relevance(participants, clubs, p), 'evidence': evidence,
            'content_version': fingerprint(evidence), 'sort_order': 0,
            'action': action('highlight', clip['highlight_id'], words(p, 'Watch highlight', '观看集锦'),
                             replay_url=f'/api/data/highlights/{clip["highlight_id"]}/replay')})
    return result
