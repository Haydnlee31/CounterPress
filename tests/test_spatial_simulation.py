"""Spatial sampling changes probabilities before play, preserving event accounting."""
from copy import deepcopy
import json
import importlib.util
from hashlib import sha256
from pathlib import Path
from random import Random
import pytest

from counterpress.personalization.spatial import features, in_box, pass_target

ROOT=Path(__file__).resolve().parents[1]


def model():
    m=json.loads((ROOT/'fixtures/personalization/calibration.json').read_text())
    m['spatial']={'pass_tilts':{r:{} for r in ('GK','DF','MF','FW')}}
    return m


def test_progression_thresholds_and_box_boundaries():
    assert features((10,34),(40,34))['progression']
    assert not features((10,34),(39.99,34))['progression']
    assert features((45,34),(60,34))['progression']
    assert features((75,34),(85,34))['progression']
    assert not features((75,34),(70,65))['progression']
    assert in_box((88.5,13.84)) and not in_box((88.499,34))
    assert features((75,34),(90,34))['box_entry']
    assert not features((90,34),(95,34))['box_entry']


def test_tilt_changes_distribution_without_creating_out_of_pitch_targets():
    base=model();tilted=deepcopy(base)
    tilted['spatial']['pass_tilts']['MF']['progression']=-3
    sequences=[]
    for m in (base,tilted):
        rng=Random(818)
        samples=[pass_target(m,'MF',(60,34),rng) for _ in range(800)]
        assert all(1<=x<=104 and 1<=y<=67 for x,y in samples)
        sequences.append(samples)
    counts=[sum(features((60,34),p)['progression'] for p in s) for s in sequences]
    assert counts[1]<counts[0]*.35
    assert len(set(sequences[1]))>700  # not a repeated point or imposed quota
    rng=Random(818)
    assert [pass_target(tilted,'MF',(60,34),rng) for _ in range(800)]==sequences[1]


def test_role_preferences_do_not_leak_to_other_roles_and_keeper_remains_bounded():
    base=model();other=deepcopy(base)
    other['spatial']['pass_tilts']['FW']['box_entry']=4
    assert pass_target(base,'DF',(40,20),Random(5))==pass_target(other,'DF',(40,20),Random(5))
    rng=Random(500)
    assert all(pass_target(base,'GK',(10,34),rng)[0]<=70 for _ in range(100))


def test_app_rejects_spatial_model_without_expanded_review(tmp_path):
    from counterpress.personalization.store import DataStore
    raw=json.dumps({'spatial':{'version':'test'}}).encode()
    (tmp_path/'model.json').write_bytes(raw)
    (tmp_path/'manifest.json').write_text(json.dumps({'validation_status':'passed','files':{'model.json':sha256(raw).hexdigest()}}))
    with pytest.raises(ValueError,match='expanded position audit'):
        DataStore(tmp_path)


def test_staged_acceptance_binds_inputs_and_rejects_failed_or_stale_review(tmp_path):
    spec=importlib.util.spec_from_file_location('accept_spatial',ROOT/'scripts/accept_player_spatial.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    hashes={}
    for name in ('model.json','ledger.json.gz','registry.json','position-validation.json','analytics.gz'):
        raw=name.encode();(tmp_path/name).write_bytes(raw);hashes[name]=sha256(raw).hexdigest()
    manifest={'validation_status':'passed','files':hashes}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    report={'status':'passed_with_coverage_limits','input_sha256':hashes,
            'prior_position_report_sha256':hashes['position-validation.json'],'analytics_sha256':hashes['analytics.gz'],
            'independent_simulation_checks':{'pooled':{'test':{'passed':True}}},'core_position_checks':{'test':{'passed':True}}}
    path=tmp_path/'report.json';path.write_text(json.dumps(report))
    module.accept(tmp_path,path,tmp_path/'analytics.gz')
    bound=json.loads((tmp_path/'manifest.json').read_text())
    assert bound['files']['spatial-validation.json']==sha256(path.read_bytes()).hexdigest()
    flag={'share':.27,'passed':False,'source_supported_style':True,
          'source_style_reference':{'eligible':True,'central_80_range':[.14,.31]}}
    report['team_role_share_flags']=[flag];report['unresolved_team_role_share_flags']=[]
    path.write_text(json.dumps(report));module.accept(tmp_path,path,tmp_path/'analytics.gz')
    assert json.loads((tmp_path/'spatial-validation.json').read_text())['team_role_share_flags'][0]['passed'] is False
    flag['share']=.4;path.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='source support'):module.accept(tmp_path,path,tmp_path/'analytics.gz')
    report['team_role_share_flags']=[]
    report['population_flags']=['failure'];path.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='Unresolved'):module.accept(tmp_path,path,tmp_path/'analytics.gz')
    report['population_flags']=[];path.write_text(json.dumps(report))
    (tmp_path/'ledger.json.gz').write_bytes(b'changed')
    with pytest.raises(ValueError,match='input mismatch'):module.accept(tmp_path,path,tmp_path/'analytics.gz')


def test_bootstrap_ignores_unrelated_counts_without_changing_intervals():
    from counterpress.personalization.positions import summarize
    rows=[{'players':{'p':{'minutes':90,'passes':10+i*10,'passes_known':10+i*10,'passes_completed':5+i*5}},'roles':{'p':'DF'}} for i in range(4)]
    reference=summarize(rows,bootstrap=100)
    extra=deepcopy(rows)
    for row in extra:row['players']['p'].update({f'extra_{i}':999 for i in range(100)})
    assert reference['roles']['DF']['ci95']==summarize(extra,bootstrap=100)['roles']['DF']['ci95']


def test_squad_role_trait_scaling_does_not_inflate_role_volume():
    from counterpress.personalization.registry import build_registry
    from counterpress.personalization.simulation import simulate
    from counterpress.personalization.metrics import digest
    m=json.loads((ROOT/'fixtures/personalization/model.json').read_text())
    if 'spatial' not in m:
        m['spatial']={'pass_tilts':{r:{} for r in ('GK','DF','MF','FW')},
            'wide_involvement':{},'shot_inside_scale':dict.fromkeys(('GK','DF','MF','FW'),1),
            'shot_outside_scale':dict.fromkeys(('GK','DF','MF','FW'),1),
            'long_completion_offset':dict.fromkeys(('GK','DF','MF','FW'),0)}
    m['spatial']['center_role_traits']=True
    m['spatial']['role_centering_basis']='appearance_minutes'
    _,players=build_registry(m)
    changed=[p.model_copy(update={'shooting':p.shooting*.5}) if p.club_id=='northport' and p.role=='DF' else p for p in players]
    args=('eastbridge','northport','centering-test','2026-01-01T15:00:00Z','test',112233)
    original=simulate(m,players,*args)
    scaled=simulate(m,changed,*args)
    assert digest(original.events)==digest(scaled.events)
    # An unused reserve keeper must not alter the active keeper's role baseline.
    unused=[p.model_copy(update={'involvement':p.involvement*.5,'creating':p.creating*.5})
            if p.club_id=='northport' and p.number==15 else p for p in players]
    assert 'np15' not in {a.player_id for a in original.fixture.appearances}
    assert digest(original.events)==digest(simulate(m,unused,*args).events)
