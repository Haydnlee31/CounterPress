from counterpress.personalization.coverage import metric_coverage,covered_rates
from counterpress.personalization.metrics import empty
from counterpress.fan.presentation import metric_tiles
from counterpress.fan.contracts import FanPreferences


def test_partial_assists_keep_counts_and_use_only_covered_minutes():
    # Independent example: 2 assists in 90 covered minutes, plus an unknown 30.
    known={**empty(),'appearances':1,'minutes':90,'assists':2}
    # A known award in an otherwise incomplete match can contribute to the
    # recorded count, but cannot be mixed into a rate over different minutes.
    unknown={**empty(),'appearances':1,'minutes':30,'assists':1}
    c=metric_coverage([({'source_kind':'calibrated_simulation'},known),({'source_kind':'adapted_archive','assist_basis':'unavailable'},unknown)])
    total={**known,'appearances':2,'minutes':120,'assists':3}
    rates=covered_rates(total,c)
    assert rates['assists_per90']==2
    assert rates['goal_involvements_per90'] is None
    tiles={t['metric']:t for t in metric_tiles(total,rates,{'metrics':c,'assists_unavailable_matches':1},FanPreferences(depth='analyst'))}
    assert tiles['assists']['value']==3
    assert tiles['assists']['coverage']=='partial'
    assert tiles['assists']['coverage_label']=='1 of 2 matches'
    assert tiles['assists_per90']['denominator']==90


def test_unknown_zero_is_not_a_recorded_zero():
    stats={**empty(),'appearances':1,'minutes':90}
    coverage=metric_coverage([({'source_kind':'adapted_archive','assist_basis':'unavailable'},stats)])
    tiles={t['metric']:t for t in metric_tiles(stats,covered_rates(stats,coverage),{'metrics':coverage,'assists_unavailable_matches':1},FanPreferences(depth='analyst'))}
    assert tiles['assists']['value'] is None
    coverage=metric_coverage([({'source_kind':'adapted_archive','assist_basis':'provider_tags'},stats)])
    tiles={t['metric']:t for t in metric_tiles(stats,covered_rates(stats,coverage),{'metrics':coverage},FanPreferences(depth='analyst'))}
    assert tiles['assists']['value']==0
    assert tiles['assists']['coverage']=='available'
