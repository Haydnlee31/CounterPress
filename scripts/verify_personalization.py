"""Audit every reproducible career match, not just the selected showcase."""
import argparse,json,math,time
from hashlib import sha256
from collections import Counter
from pathlib import Path
from counterpress.personalization.metrics import reduce_record,digest
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService
from counterpress.personalization.replay import native_feed,highlight_feed
from counterpress.personalization.positions import generated_row,summarize,position_checks


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('fixtures/personalization'));p.add_argument('--output',type=Path);a=p.parse_args()
    started=time.monotonic();store=DataStore(a.root);event_count=0;goals=0;team_games=Counter();position_rows=[]
    import counterpress.personalization.simulation as simulation_module
    for name,expected in store.manifest.get('simulation_sources',{}).items():
        assert sha256(Path(simulation_module.__file__).with_name(name).read_bytes()).hexdigest()==expected,f'Generation source changed: {name}'
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
            for metric in ('passes','passes_completed','passes_unknown','shots','shots_on_target','shots_off_target','shots_blocked',
                           'assists','duels','duels_won','duels_unknown','recoveries','saves','key_passes','xg'):
                assert math.isclose(stats[metric],sum(s[metric] for s in ours),abs_tol=1e-5),(row['id'],metric)
            assert stats['assists']<=stats['goals']
            if record.fixture.source_kind=='calibrated_simulation':
                assert math.isclose(sum(s['minutes'] for s in ours),990,abs_tol=1e-4)
                for at in (0,2700000,4000000,5399999):
                    assert sum(x.club_id==club and x.start_ms<=at<x.end_ms for x in record.fixture.appearances)==11
                assert stats['shots']==stats['shots_on_target']+stats['shots_off_target']+stats['shots_blocked']
                assert stats['passes_completed']+stats['passes_unknown']<=stats['passes']
                assert stats['duels_won']+stats['duels_unknown']<=stats['duels']
                assert stats['saves']==sum(e.kind=='shot' and e.outcome=='saved' and e.club_id!=club for e in record.events)
                assert stats['shots_on_target']==stats['goals']+sum(s['saves'] for s in opponent)
        if record.fixture.source_kind=='calibrated_simulation' and not record.fixture.featured:
            position_rows.append(generated_row(record,summary,list(store.players.values())))
        for previous,current in zip(record.events,record.events[1:]):
            if previous.period!=current.period:continue
            if previous.flight_ms:assert current.elapsed_ms-previous.elapsed_ms>=previous.flight_ms
        if n%200==0:print(f'Validated {n} matches',flush=True)
    assert event_count==store.manifest['total_events']
    service=CareerService(store);profile_checks=0
    for player in store.players.values():
        if not player.featured:continue
        profile=service.profile(player.player_id);history=service.history(player.player_id,limit=1000)['items']
        for metric in ('goals','assists','passes','passes_completed','shots','saves','duels','duels_won','clean_sheets','goals_conceded'):
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
    realism=store.manifest['population_validation']
    for group in ('historical_checks','validation_checks'):
        assert all(c['passed'] for c in realism[group].values()),f'Population realism check failed: {group}'
    positional=json.loads((a.root/'position-validation.json').read_text())
    actual=summarize(sorted(position_rows,key=lambda row:row['id']))
    position_gates=position_checks(actual,positional['source_holdout'],positional['source_training'])
    for role,row in actual['roles'].items():
        for metric,value in row['rates'].items():
            expected=positional['historical']['roles'][role]['rates'][metric]
            assert value is None and expected is None or value is not None and expected is not None and math.isclose(value,expected,abs_tol=1e-8)
    assert all(c['passed'] for c in position_gates.values()),'Historical position check failed'
    for batch in positional['validation_batches']:
        assert all(c['passed'] for c in position_checks(batch['observed'],positional['source_holdout'],positional['source_training']).values()),'Independent position check failed'
    assert all(c['passed'] for c in positional['pooled_checks'].values()),'Pooled position check failed'
    assert all(c['passed'] for c in positional['pooled_population_checks'].values()),'Pooled population check failed'
    report={'status':'passed','matches':len(store.rows()),'events':event_count,'goals':goals,'featured_profiles':profile_checks,
            'featured_matches':len(store.rows(featured=True)),'highlights':len(clips),
            'checks':['Every event digest and regenerated summary','Player and club goals including own goals','Pass/shot/assist totals',
                      'Eleven active players and 990 team player-minutes in each simulation','Ball flight precedes next action',
                      'All 44 featured careers reconcile with history','Highlight parent links and native replay contracts'],
            'population_checks':{g:len(realism[g]) for g in ('historical_checks','validation_checks')},
            'position_checks':len(position_gates)*(2+len(positional['validation_batches'])),
            'independent_simulation_matches':sum(b['observed']['matches'] for b in positional['validation_batches']),
            'validation_warnings':store.manifest.get('validation_warnings',[]),
            'elapsed_seconds':round(time.monotonic()-started,2)}
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));store.close()

if __name__=='__main__':main()
