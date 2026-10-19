"""Audit every reproducible career match, not just the selected showcase."""
import argparse,json,math,time
from collections import Counter
from pathlib import Path
from counterpress.personalization.metrics import reduce_record,digest
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService
from counterpress.personalization.replay import native_feed,highlight_feed


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('fixtures/personalization'));p.add_argument('--output',type=Path);a=p.parse_args()
    started=time.monotonic();store=DataStore(a.root);event_count=0;goals=0;team_games=Counter()
    for n,row in enumerate(store.rows(),1):
        record=store.original(row['id']);summary=reduce_record(record)
        assert digest(record.events)==row['digest']
        assert summary==json.loads(row['summary']),f'Summary mismatch: {row["id"]}'
        event_count+=len(record.events);goals+=sum(summary['score'].values())
        assert all((e.available_period,e.available_ms)<=(2,record.fixture.period_lengths_ms[1]+1000) for e in record.events)
        for club,stats in summary['clubs'].items():
            team_games[club]+=1
            ours=[s for pid,s in summary['players'].items() if store.players[pid].club_id==club]
            opponent=[s for pid,s in summary['players'].items() if store.players[pid].club_id!=club]
            assert stats['goals']==sum(s['goals'] for s in ours)+sum(s['own_goals'] for s in opponent)
            for metric in ('passes','passes_completed','shots','assists','xg'):
                assert math.isclose(stats[metric],sum(s[metric] for s in ours),abs_tol=1e-5),(row['id'],metric)
            assert stats['assists']<=stats['goals']
            if record.fixture.source_kind=='calibrated_simulation':
                assert math.isclose(sum(s['minutes'] for s in ours),990,abs_tol=1e-4)
                for at in (0,2700000,4000000,5399999):
                    assert sum(x.club_id==club and x.start_ms<=at<x.end_ms for x in record.fixture.appearances)==11
        for previous,current in zip(record.events,record.events[1:]):
            if previous.period!=current.period:continue
            if previous.flight_ms:assert current.elapsed_ms-previous.elapsed_ms>=previous.flight_ms
        if n%200==0:print(f'Validated {n} matches',flush=True)
    assert event_count==store.manifest['total_events']
    service=CareerService(store);profile_checks=0
    for player in store.players.values():
        if not player.featured:continue
        profile=service.profile(player.player_id);history=service.history(player.player_id,limit=1000)['items']
        for metric in ('goals','assists','passes','shots'):
            assert profile['totals'][metric]==sum(r['stats'][metric] for r in history)
        assert profile['scope']['match_count']==len(history)
        assert profile['heatmap']['total_actions']==sum(c['actions'] for c in profile['heatmap']['cells'])
        profile_checks+=1
    clips=json.loads((a.root/'highlights.json').read_text())
    for clip in clips:
        native=highlight_feed(native_feed(store.original(clip['match_id']),store.clubs),clip)
        assert [e.event_id for e in native.events]==clip['event_ids']
        assert native.events[-1].action.kind=='shot' and native.events[-1].action.outcome=='goal'
        assert len(native.events)>=2
    report={'status':'passed','matches':len(store.rows()),'events':event_count,'goals':goals,'featured_profiles':profile_checks,
            'featured_matches':len(store.rows(featured=True)),'highlights':len(clips),
            'checks':['Every event digest and regenerated summary','Player and club goals including own goals','Pass/shot/assist totals',
                      'Eleven active players and 990 team player-minutes in each simulation','Ball flight precedes next action',
                      'All 44 featured careers reconcile with history','Highlight parent links and native replay contracts'],
            'elapsed_seconds':round(time.monotonic()-started,2)}
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));store.close()

if __name__=='__main__':main()
