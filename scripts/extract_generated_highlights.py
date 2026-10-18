"""Extract three exact action sequences with explicit parent-event provenance."""
import json
from pathlib import Path
from counterpress.fixture import PossessionFixture
ROOT=Path(__file__).resolve().parents[1]
parent=json.loads((ROOT/'fixtures/gi/synthetic/events.json').read_text())
# Editorial selections: turnover equalizer, taking the lead, late equalizer.
selections=[('level-first','a00495','a00500'),('take-lead','a00999','a01004'),('level-late','a01042','a01047')]
manifest={'parent_match_id':parent['match_id'],'display_date':'2026-10-18','highlights':[]}
for slug,start,end in selections:
    records=[e for e in parent['events'] if start<=e['event_id']<=end]
    result={k:v for k,v in parent.items() if k not in ('events','initial_state')}
    result['match_id']=f'showcase-{slug}-v1'
    score={'eastbridge':0,'northport':0}
    for e in parent['events']:
        if e['event_id']>=start:break
        if e['action']['kind']=='shot' and e['action']['outcome']=='goal':score[e['actor']['team_id']]+=1
    result['initial_state']={'at':{'period':2,'elapsed_ms':180000},'score':score,'controlled_possession_team_id':records[0]['actor']['team_id']}
    # Preserve original intervals; only shift the clock into the existing replay window.
    offset=780000-records[-1]['occurred_at']['elapsed_ms']
    result['events']=[]
    links=[]
    for i,e in enumerate(records,1):
        changed={**e,'match_id':result['match_id'],'source_delivery_sequence':i,'occurrence_order':i,
                 'occurred_at':{'period':2,'elapsed_ms':e['occurred_at']['elapsed_ms']+offset},
                 'available_at':{'period':2,'elapsed_ms':e['occurred_at']['elapsed_ms']+offset}}
        result['events'].append(changed)
        links.append({'event_id':e['event_id'],'parent_time':e['occurred_at'],'revision':e['revision']})
    fixture=PossessionFixture.model_validate_json(json.dumps(result))
    (ROOT/f'fixtures/showcases/{slug}.json').write_text(fixture.model_dump_json(indent=2)+'\n')
    manifest['highlights'].append({'scenario_id':slug,'match_id':result['match_id'],'events':links})
(ROOT/'fixtures/showcases/generated_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Extracted three highlights; original actors, actions and geometry retained.')
