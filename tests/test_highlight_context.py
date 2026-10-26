"""Independent read-boundary oracles, including non-clip score corrections."""
from types import SimpleNamespace
import pytest
from counterpress.personalization.contracts import Action
from counterpress.personalization.highlight_context import highlight_context


@pytest.fixture
def setup():
    def event(eid, seq, period, at):
        return Action(match_id='test-match', event_id=eid, revision=1,
                      delivery_sequence=seq, occurrence_order=seq,
                      period=period, elapsed_ms=at, available_period=period,
                      available_ms=at, club_id='home', player_id='h1',
                      kind='shot', outcome='goal', goal_for='home', source_reference='test:'+eid)
    events = [event('earlier', 1, 1, 100), event('lead-in', 2, 2, 1000),
              event('goal', 3, 2, 2000), event('later', 4, 2, 3000)]
    appearances = [SimpleNamespace(player_id='h1', club_id='home', start_ms=0, end_ms=5400000),
                   SimpleNamespace(player_id='a1', club_id='away', start_ms=0, end_ms=5400000)]
    fixture = SimpleNamespace(period_lengths_ms=(2700000,2700000), appearances=appearances,
                              home_id='home', away_id='away')
    overlays = []
    store = SimpleNamespace(dataset='a'*64,
        clubs={c:SimpleNamespace(name=c.title()) for c in ('home','away')},
        original=lambda _:SimpleNamespace(fixture=fixture,events=events),
        events=lambda _:[*events,*overlays], row=lambda _:{'digest':'original'},
        evidence_digest=lambda _:'changed' if overlays else 'original')
    clip={'highlight_id':'clip','match_id':'test-match','event_ids':['lead-in','goal'],
          'goal_event_id':'goal','end':{'period':2,'elapsed_ms':2000}}
    return store,clip,events,overlays


def test_initial_boundary_is_not_full_time(setup):
    store,clip,_,_=setup
    result=highlight_context(store,clip)
    assert result['initial_cutoff']=={'period':2,'elapsed_ms':999}
    assert result['original_cutoff']==result['latest_cutoff']=={'period':2,'elapsed_ms':2000}
    assert result['original_sequence']==result['latest_sequence']==4
    assert result['active_player_ids']==['h1','a1']
    assert result['replay_available'] is True


def test_earlier_score_change_advances_review_but_future_play_does_not(setup):
    store,clip,events,overlays=setup
    overlays.append(events[-1].model_copy(update={'revision':2,'delivery_sequence':5,'available_ms':3500}))
    future=highlight_context(store,clip)
    assert future['replay_available'] is False
    assert future['latest_cutoff']==clip['end'] and future['latest_sequence']==4
    overlays.append(events[0].model_copy(update={'revision':2,'delivery_sequence':6,
                                                'available_period':2,'available_ms':2500,'retracted':True}))
    relevant=highlight_context(store,clip)
    assert relevant['latest_cutoff']=={'period':2,'elapsed_ms':2500}
    assert relevant['latest_sequence']==6
    assert relevant['content_version']!=future['content_version']


def test_equal_clock_revision_requires_new_sequence_and_restoration_does_not_restore_animation(setup):
    store,clip,events,overlays=setup
    initial=highlight_context(store,clip)
    overlays.append(events[2].model_copy(update={'revision':2,'delivery_sequence':5,'retracted':True}))
    withdrawn=highlight_context(store,clip)
    assert withdrawn['latest_cutoff']==initial['latest_cutoff']
    assert withdrawn['latest_sequence']==5 and withdrawn['goal']['retracted']
    overlays.append(events[2].model_copy(update={'revision':3,'delivery_sequence':6}))
    restored=highlight_context(store,clip)
    assert restored['goal']['revision']==3 and not restored['goal']['retracted']
    assert restored['replay_available'] is False
    assert len({initial['content_version'],withdrawn['content_version'],restored['content_version']})==3


def test_correction_moving_original_goal_past_clip_end_still_offers_review(setup):
    store,clip,events,overlays=setup
    overlays.append(events[2].model_copy(update={'revision':2,'delivery_sequence':5,
                                                'elapsed_ms':2600,'available_ms':2800}))
    result=highlight_context(store,clip)
    assert result['latest_cutoff']=={'period':2,'elapsed_ms':2800}
    assert result['latest_sequence']==5


def test_bad_clip_references_are_rejected(setup):
    store,clip,_,_=setup
    with pytest.raises(ValueError,match='Invalid highlight references'):
        highlight_context(store,{**clip,'event_ids':['absent']})


def test_post_match_update_is_not_silently_clamped_to_a_supported_clock(setup):
    store,clip,events,overlays=setup
    overlays.append(events[2].model_copy(update={'revision':2,'delivery_sequence':5,'available_ms':3000000}))
    result=highlight_context(store,clip)
    assert result['latest_cutoff']=={'period':2,'elapsed_ms':3000000}
    assert result['review_available'] is False
