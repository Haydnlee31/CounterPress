"""Prepare six source-bound highlight summaries with Azure OpenAI writing and factual review.

Default is an offline freshness check. --generate makes two bounded
model calls per changed highlight (writer and fact-checker); does not provision or modify Azure infrastructure.
"""
import argparse
import asyncio
import hashlib
import json
from math import hypot
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'frontend/src/highlights/preloaded-summaries.json'
SOURCES = {'last-gasp': 'last_gasp', 'one-touch': 'one_touch', 'breakaway': 'breakaway',
           'level-first': 'level-first', 'take-lead': 'take-lead', 'level-late': 'level-late'}
NAMES = dict(re.findall(r"\b((?:eb|np)\d{2}): '([^']+)'", (ROOT / 'frontend/src/matchday/identity.ts').read_text()))


def source_rows(events):
    rows = []
    from counterpress.domain.models import Event
    for raw in events:
        e = Event.model_validate(raw).model_dump(mode='json')
        a = e['action']
        rows.append([e['match_id'], e['event_id'], e['revision'], e['occurred_at'], e['available_at'],
                     e['actor'], e['position'], a['kind'], a.get('outcome'), a.get('recipient'),
                     a.get('end_position'), a.get('goalkeeper'), a.get('situation'), a.get('technique'),
                     a.get('from_team_id'), a.get('control')])
    return rows


def final_score(data):
    score = dict(data['initial_state']['score'])
    for e in data['events']:
        if e['action'].get('outcome') == 'goal':
            score[e['actor']['team_id']] += 1
    return score


def evidence_for(data):
    return {'context':{'score_before':data['initial_state']['score'], 'score_after':final_score(data),
                      'players':NAMES,'clubs':{t['team_id']:t['name'] for t in data['teams']},
                      'pitch':'105 by 68 metres; acting team attacks positive x. Left/right flank names are not supplied; say wide if appropriate.',
                      'scope':'Complete highlight only. Match outcome is not known. Timestamps are rebased; use intervals, not match minutes.'},
            'events':data['events']}


async def generate():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from run_footie_local import local_model_settings
    from counterpress.adaptation.azure import load_config
    from counterpress.assistant.highlight_summary import write_verified_summary,SummaryRejected,enrich_evidence
    local_model_settings(ROOT / '.env')
    config = load_config()
    if not config:
        raise SystemExit('Existing Azure configuration is required.')
    result = json.loads(DEST.read_text()) if DEST.exists() else {}
    for story, filename in SOURCES.items():
        path = ROOT / 'fixtures/showcases' / (filename+'.json')
        data = json.loads(path.read_text())
        old=result.get(story,{})
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if old.get('mode')=='azure_generated_verified' and old.get('fixture_sha256')==digest:
            continue
        try:
            verified=await write_verified_summary(config,enrich_evidence(evidence_for(data)))
        except SummaryRejected as rejected:
            print(f'{story}: correcting unsupported claims: {rejected.issues}')
            verified=await write_verified_summary(config,enrich_evidence(evidence_for(data)),feedback={'draft':rejected.draft,'issues':rejected.issues})
        result[story] = {**verified,'fixture_sha256':digest,'source':source_rows(data['events']), 'score':final_score(data)}
        print(f'{story}: model-written summary passed independent factual review')
        DEST.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    DEST.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')


def check():
    from counterpress.assistant.highlight_summary import Draft,enrich_evidence,check_goal_ordinals
    result = json.loads(DEST.read_text())
    assert set(result) == set(SOURCES)
    for story, filename in SOURCES.items():
        path = ROOT / 'fixtures/showcases' / (filename+'.json')
        data = json.loads(path.read_text())
        asset = result[story]
        assert asset['fixture_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest(), story
        assert asset['source'] == source_rows(data['events']), story
        assert asset['score'] == final_score(data), story
        assert asset['mode'] == 'azure_generated_verified' and 1 <= len(asset['text']) <= 3
        assert asset['review']=={'supported':True,'issues':[]}
        assert asset['text']==[p['text'] for p in asset['paragraphs']]
        check_goal_ordinals(Draft.model_validate({'paragraphs':asset['paragraphs']}),enrich_evidence(evidence_for(data)))
        allowed={e['event_id'] for e in data['events']}|{'context'}
        assert all(p['evidence_ids'] and set(p['evidence_ids'])<=allowed for p in asset['paragraphs'])
    print('6/6 preloaded summaries match their fixtures and passed factual review.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate', action='store_true')
    args = parser.parse_args()
    if args.generate:
        asyncio.run(generate())
    check()
