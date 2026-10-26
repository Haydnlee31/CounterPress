#!/usr/bin/env python3
"""Read-only, bounded hosted Phase4 verification. This program NEVER sends events.

URLs come from FOOTIE_PHASE4_TEST_URL and FOOTIE_PHASE4_PRODUCTION_URL; they are
never persisted. Azure isolation must separately be established by the private
resource checker. `prepare` writes a local envelope for the dedicated sender.
"""
import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from counterpress.personalization.contracts import Action
from counterpress.personalization.metrics import digest
from counterpress.personalization.store import DataStore
from counterpress.streaming.contracts import CareerDelivery, MAX_DELIVERY_BYTES

EXPECTED = json.loads((ROOT / 'fixtures/evaluation/fan_card_lifecycle.json').read_text())
CONFIG = {'mode':'isolated', 'app':'counterpress-phase4', 'cosmos_database':'counterpress',
          'cosmos_container':'histories-phase4', 'eventhub':'deliveries-phase4',
          'pubsub_hub':'counterpress_phase4', 'checkpoint_container':'eventhub-checkpoints-phase4',
          'quarantine_container':'rejected-deliveries-phase4', 'inference':False,
          'dataset':EXPECTED['dataset']}
STEPS = ('correction', 'retraction', 'duplicate', 'restoration', 'late')
GENERATIONS = {'baseline':0, 'correction':1, 'retraction':2, 'duplicate':2, 'restoration':3, 'late':4}
OFFSETS = {'baseline':0, 'correction':1, 'retraction':2, 'duplicate':2, 'restoration':4, 'late':5}
AVAILABLE = {'baseline':1050489, 'correction':1050800, 'retraction':1051000,
             'duplicate':1051000, 'restoration':1052000, 'late':1080021}
FAILURES = ('rejected','retries','publish_failures','checkpoint_failures','consumer_failures','export_failures')
PROOF_CHECKS = ('journal','stream','checkpoint','quarantine','pubsub','identities','roles')


class VerificationError(Exception):
    """Only fixed diagnostic codes may reach stdout."""


def require(condition, code):
    if not condition:
        raise VerificationError(code)


def hashed(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def private_write(path, value, *, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.pending') if replace else path
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    if replace:
        os.replace(temporary,path)


def proof_check(proof, now=None):
    require(proof.get('isolated') is True and proof.get('inference') is False
            and proof.get('production_unchanged') is True, 'isolation_proof_failed')
    require(proof.get('dataset') == EXPECTED['dataset'], 'isolation_dataset_mismatch')
    require(isinstance(proof.get('image_digest'),str) and re.fullmatch(r'sha256:[a-f0-9]{64}',proof['image_digest']), 'isolation_image_invalid')
    require(isinstance(proof.get('origin_sha256'),str) and re.fullmatch(r'[a-f0-9]{64}',proof['origin_sha256']), 'isolation_origin_missing')
    checks = proof.get('isolation_checks',{})
    require(all(checks.get(key) is True for key in PROOF_CHECKS), 'isolation_checks_missing')
    try:
        at = datetime.fromisoformat(proof['checked_at'].replace('Z','+00:00'))
        age = ((now or datetime.now(timezone.utc))-at).total_seconds()
    except (KeyError,ValueError,TypeError):
        raise VerificationError('isolation_time_invalid') from None
    require(-300 <= age <= 7200, 'isolation_proof_expired')
    return hashed(proof)


class Reader:
    def __init__(self, base_url):
        import httpx
        parsed = urlsplit(base_url)
        require(parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
                and not parsed.password and not parsed.query and not parsed.fragment
                and parsed.path in ('','/'), 'invalid_reader_origin')
        port = parsed.port
        self.origin = 'https://' + parsed.hostname.lower() + ((':'+str(port)) if port and port!=443 else '')
        self.client = httpx.Client(base_url=self.origin,timeout=10,follow_redirects=False,trust_env=False)
    def close(self):
        self.client.close()
    def request(self, method, path, body=None, params=None):
        # No assistant, ingestion, management, or arbitrary caller-provided paths.
        require(path.startswith('/api/data/') or path.startswith('/api/phase4/')
                or path.startswith('/api/fan/matches/') or path == '/api/fan/home', 'reader_path_forbidden')
        require(method == 'GET' or method == 'POST' and path.startswith('/api/fan/'), 'reader_method_forbidden')
        try:
            response = self.client.request(method,path,json=body,params=params,headers={'Cache-Control':'no-store'})
            require(response.status_code == 200, 'reader_http_failed')
            require(len(response.content) <= 8_000_000, 'reader_response_too_large')
            return response.json()
        except VerificationError:
            raise
        except Exception:
            raise VerificationError('reader_transport_failed') from None
    def get(self,path,params=None):return self.request('GET',path,params=params)
    def post(self,path,body):return self.request('POST',path,body=body)


def revision(reader):
    state = reader.get('/api/data/revisions')
    require(state.get('dataset') == EXPECTED['dataset'] and state.get('enabled') is True,
            'revision_dataset_or_storage_invalid')
    require(type(state.get('generation')) is int and state['generation'] >= 0, 'revision_generation_invalid')
    return state


def counters(reader):
    value = reader.get('/api/phase4/telemetry')
    require(value.get('schema') == 'phase4_counters_v1', 'telemetry_schema_invalid')
    require(all(type(value.get(k)) is int and value[k] >= 0 for k in ('processed',*FAILURES)), 'telemetry_counts_invalid')
    require(type(value.get('pending')) is bool, 'telemetry_pending_invalid')
    require(type(value.get('observed_backlog')) is int and value['observed_backlog']>=0, 'telemetry_backlog_invalid')
    return {k:value[k] for k in ('processed',*FAILURES,'pending','observed_backlog')}


def isolation(reader):
    actual = reader.get('/api/phase4/config')
    require(all(actual.get(k) == v and type(actual.get(k)) is type(v) for k,v in CONFIG.items()),
            'isolated_app_config_mismatch')
    return hashed({k:actual[k] for k in CONFIG})


def production_snapshot(reader):
    before = revision(reader)
    matches = reader.get('/api/data/matches', {'featured':'true','limit':20})
    require(len(matches['items']) == matches['total'] and 1 <= matches['total'] <= 12,
            'production_match_inventory_unbounded')
    fingerprints = {}
    for match in matches['items']:
        mid = match['match_id']
        require(isinstance(mid,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',mid), 'production_match_identity_invalid')
        lengths = match['period_lengths_ms']
        response = reader.post('/api/fan/matches/'+mid, {'cutoff':{'period':2,'elapsed_ms':lengths[1]+60000},
            'preferences':{}, 'card_budget':0})
        fingerprints[mid] = response['evidence']['event_digest']
    home = reader.post('/api/fan/home', {'as_of':'2026-10-20T00:00:00Z','preferences':{},'limit':12})
    after = revision(reader)
    require(before == after, 'production_changed_during_read')
    return {'revision':before, 'event_digests_at_end':fingerprints,
            'highlights':sorted((h['highlight_id'],h['content_version']) for h in home['highlights']),
            'highlight_total':home['highlight_total']}


def unchanged_production(reader, state):
    current = production_snapshot(reader)
    require(hashed(current) == state['production_hash'], 'production_state_changed')
    return hashed(current)


def context(reader):
    return reader.get('/api/data/highlights/'+EXPECTED['highlight_id']+'/context')


def fan(reader, depth, cutoff, sequence):
    result = reader.post('/api/fan/matches/'+EXPECTED['match_id'], {
        'cutoff':cutoff, 'through_sequence':sequence, 'card_budget':5,
        'preferences':{'favorite_player_ids':['rh04'],'depth':depth,'metric_focus':'balanced'}})
    cards = [c for c in result['cards'] if c['id'] == EXPECTED['match_id']+':e01019:buildup']
    require(len(cards) <= 1, 'duplicate_card')
    return result, cards[0] if cards else None


def card_check(card, depth, kind, revision_number):
    expected = EXPECTED[kind]
    require(card is not None and card['text'] == expected[depth], 'card_audience_text_mismatch')
    evidence = card['evidence']
    require(evidence['event_revision'] == revision_number and card['ask_footie']['event_revision'] == revision_number,
            'card_source_revision_mismatch')
    require(evidence['occurred_at'] == EXPECTED['occurred_at'] and evidence['expires_at'] == EXPECTED['expires_at'],
            'card_occurrence_or_expiry_changed')
    require([e['event_id'] for e in evidence['events']] == expected['events'], 'card_event_chain_mismatch')
    values = {f['metric']:f for f in card['facts']}
    require(values['buildup_completed_passes']['value'] == expected.get('favorite_passes',expected.get('completed_passes'))
            and values['buildup_completed_passes']['subject_id'] == ('rh04' if kind=='baseline' else 'redhaven'),
            'card_contribution_mismatch')
    if depth == 'analyst':
        require(values['observed_buildup_seconds']['value'] == expected['observed_seconds']
                and values['buildup_participants']['value'] == expected['participants'], 'card_analyst_facts_mismatch')
    return {'card_hash':hashed(card),'content_version':card['content_version'],
            'evidence_fingerprint':evidence['evidence_fingerprint'],'event_revision':revision_number}


def bound_proof(test, proof):
    value = proof_check(proof)
    require(sha256(test.origin.encode()).hexdigest()==proof['origin_sha256'], 'isolated_origin_mismatch')
    return value


def baseline(test, production, proof):
    proof_hash = bound_proof(test,proof)
    config_hash = isolation(test)
    prod = production_snapshot(production)
    public_clips={h[0] for h in prod['highlights']}
    required_clips={c['highlight_id'] for c in json.loads((ROOT/'fixtures/personalization/highlights.json').read_text())
                    if c['match_id']==EXPECTED['match_id']}
    require(required_clips.issubset(public_clips), 'production_showcase_highlights_missing')
    initial = revision(test)
    require(initial['generation'] == 0 and initial.get('matches') == {}, 'test_journal_not_fresh')
    telemetry = counters(test)
    require(telemetry['processed'] == 0 and all(telemetry[k] == 0 for k in FAILURES)
            and not telemetry['pending'], 'test_consumer_not_fresh')
    ctx = context(test)
    require(ctx['replay_available'] is True and ctx['goal']['revision'] == 1
            and ctx['original_cutoff'] == ctx['latest_cutoff'] == EXPECTED['original_cutoff'], 'initial_context_mismatch')
    # Full bounded source comparison derives the unused sequence from actual
    # hosted events, not only a copied local payload or a display clock.
    remote = []
    for offset in range(0,4000,500):
        page = test.get('/api/data/matches/'+EXPECTED['match_id']+'/events',{'offset':offset,'limit':500})
        require(page['total'] <= 4000, 'test_source_too_large')
        remote.extend(Action.model_validate({k:v for k,v in row.items() if k != 'metrics'}) for row in page['items'])
        if len(remote) == page['total']:break
    require(len(remote) == page['total'], 'test_source_incomplete')
    store = DataStore(ROOT/'fixtures/personalization')
    try:
        require(store.dataset == EXPECTED['dataset'], 'local_dataset_changed')
        require(digest(remote) == store.row(EXPECTED['match_id'])['digest'], 'hosted_source_not_canonical')
    finally:store.close()
    sequence = max(e.delivery_sequence for e in remote)
    require(ctx['original_sequence'] == ctx['latest_sequence'] == sequence, 'initial_sequence_mismatch')
    cards = {}
    for depth in ('casual','analyst'):
        _,card = fan(test,depth,EXPECTED['original_cutoff'],sequence)
        cards[depth] = card_check(card,depth,'baseline',1)
    require(cards['casual']['evidence_fingerprint'] == cards['analyst']['evidence_fingerprint']
            and cards['casual']['content_version'] != cards['analyst']['content_version'], 'audiences_not_distinct')
    require(revision(test) == initial, 'test_changed_during_baseline')
    state = {'schema':'phase4_hosted_check_v1','stage':'baseline','dataset':EXPECTED['dataset'],
        'sequence':sequence,'generation':0,'processed':0,'config_hash':config_hash,'proof_hash':proof_hash,
        'image_digest':proof['image_digest'],'harness_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'production_hash':hashed(prod),'production_baseline':prod,'original_cards':cards,'checks':[]}
    unchanged_production(production,state)
    return state


def next_stage(state, step):
    index = STEPS.index(step)
    require(state['stage'] == ('baseline' if index==0 else STEPS[index-1]), 'step_out_of_order')


def payload_for(state, step):
    next_stage(state,step)
    store = DataStore(ROOT/'fixtures/personalization')
    try:
        require(state['dataset'] == EXPECTED['dataset'] == store.dataset, 'payload_dataset_mismatch')
        record = store.original(EXPECTED['match_id'])
        require(state['sequence'] == max(e.delivery_sequence for e in record.events), 'payload_sequence_not_canonical')
        goal = next(e for e in record.events if e.event_id == 'e01019')
        passing = next(e for e in record.events if e.event_id == 'e01016')
        seq = state['sequence']
        correction = passing.model_copy(update={'revision':2,'delivery_sequence':seq+1,'available_ms':1050800,'recipient_id':'rh13'})
        retract = goal.model_copy(update={'revision':2,'delivery_sequence':seq+2,'available_ms':1051000,'retracted':True})
        restore = goal.model_copy(update={'revision':3,'delivery_sequence':seq+3,'available_ms':1052000})
        restore_pass = passing.model_copy(update={'revision':3,'delivery_sequence':seq+4,'available_ms':1052000})
        late = goal.model_copy(update={'revision':4,'delivery_sequence':seq+5,'available_ms':1080021})
        batches = {'correction':[correction], 'retraction':[retract], 'duplicate':[retract],
                   'restoration':[restore,restore_pass], 'late':[late]}
        # Validate chronology and actors against the entire reviewed local chain.
        for stage in STEPS[:STEPS.index(step)+1]:store.ingest(EXPECTED['match_id'],batches[stage])
        delivery = CareerDelivery(dataset=state['dataset'],delivery_id='phase4-'+('retraction' if step=='duplicate' else step),
                                  match_id=EXPECTED['match_id'],events=tuple(batches[step]))
        require(len(delivery.model_dump_json().encode()) <= MAX_DELIVERY_BYTES, 'payload_too_large')
        return delivery.model_dump(mode='json')
    finally:store.close()


def prepare(test, production, state, proof, step):
    bound_proof(test,proof)
    require(proof['image_digest']==state['image_digest'], 'isolated_image_changed')
    require(isolation(test) == state['config_hash'], 'isolated_config_changed')
    unchanged_production(production,state)
    require(revision(test)['generation'] == state['generation'], 'test_generation_not_previous_step')
    require(counters(test)['processed'] == state['processed'], 'unreviewed_test_delivery')
    return payload_for(state,step)


def check_step(test, production, state, proof, step, *, attempts=10, sleep=time.sleep):
    next_stage(state,step)
    bound_proof(test,proof)
    require(proof['image_digest']==state['image_digest'], 'isolated_image_changed')
    require(isolation(test) == state['config_hash'], 'isolated_config_changed')
    unchanged_production(production,state)
    expected_generation = GENERATIONS[step]
    for attempt in range(attempts):
        current, telemetry = revision(test), counters(test)
        require(current['generation'] <= expected_generation, 'unexpected_test_generation')
        require(all(telemetry[k] == 0 for k in FAILURES), 'test_consumer_failure')
        if current['generation'] == expected_generation and telemetry['processed'] > state['processed'] and not telemetry['pending']:break
        if attempt+1 < attempts:sleep(1)
    else:raise VerificationError('delivery_not_confirmed_within_bound')
    ctx = context(test)
    seq = state['sequence'] + OFFSETS[step]
    goal_revision = 2 if step in ('retraction','duplicate') else 3 if step=='restoration' else 4 if step=='late' else 1
    require(ctx['original_sequence'] == state['sequence'] and ctx['latest_sequence'] == seq
            and ctx['original_cutoff'] == EXPECTED['original_cutoff']
            and ctx['latest_cutoff'] == {'period':2,'elapsed_ms':AVAILABLE[step]}, 'step_context_boundary_mismatch')
    require(ctx['replay_available'] is False and ctx['goal']['revision'] == goal_revision
            and ctx['goal']['retracted'] is (step in ('retraction','duplicate')), 'step_goal_or_replay_mismatch')
    cards = {}
    for depth in ('casual','analyst'):
        _,historical = fan(test,depth,EXPECTED['original_cutoff'],state['sequence'])
        require(hashed(historical) == state['original_cards'][depth]['card_hash'], 'historical_card_changed')
        cutoff = {'period':2,'elapsed_ms':1080021} if step=='late' else EXPECTED['updated_cutoff']
        response,card = fan(test,depth,cutoff,seq)
        score = {'southbank':2,'redhaven':1 if step in ('retraction','duplicate') else 2}
        require(response['facts']['score'] == score, 'updated_score_mismatch')
        if step in ('retraction','duplicate','late'):
            require(card is None, 'withdrawn_or_expired_card_returned')
        else:
            cards[depth] = card_check(card,depth,'corrected' if step=='correction' else 'baseline',goal_revision)
            require(cards[depth]['evidence_fingerprint'] != state['original_cards'][depth]['evidence_fingerprint'],
                    'changed_source_reused_original_evidence')
        if step in ('restoration','late'):
            _,before = fan(test,depth,{'period':2,'elapsed_ms':1080019},seq)
            _,expired = fan(test,depth,EXPECTED['expires_at'],seq)
            require(before is not None and expired is None, 'fixed_expiry_boundary_failed')
    require(revision(test) == current, 'test_changed_during_step_read')
    unchanged_production(production,state)
    result = {'step':step,'generation':expected_generation,'processed':telemetry['processed'],
              'processed_delta':telemetry['processed']-state['processed'],'cards':cards,
              'original_cards_preserved':True,'production_unchanged':True,'replay_withdrawn':True,
              'delivery_evidence':'processed_counter_delta_in_isolated_stream',
              'socket_transport_checked':False,'physical_checkpoint_checked':False}
    return {**state,'stage':step,'generation':expected_generation,'processed':telemetry['processed'],
            'checks':[*state['checks'],result]}, result


def valid_hint(message, generation):
    if not isinstance(message,str) or len(message)>4096:return False
    try:value=json.loads(message)
    except (ValueError,TypeError):return False
    return (isinstance(value,dict) and value.get('type')=='career.changed'
            and type(value.get('schema_version')) is int and value.get('schema_version')==1
            and value.get('dataset')==EXPECTED['dataset'] and type(value.get('generation')) is int
            and value['generation']==generation and value.get('match_id')==EXPECTED['match_id'])


async def watch(test, generation, seconds=55):
    import aiohttp
    require(1<=seconds<=55,'watch_duration_invalid')
    def negotiate():
        config=test.get('/api/data/revisions/negotiate')
        value=urlsplit(config.get('url',''))
        require(config.get('enabled') is True and value.scheme=='wss' and value.hostname
                and value.hostname.endswith('.webpubsub.azure.com') and not value.username and not value.password,
                'socket_negotiation_invalid')
        return config['url']
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=seconds+10),trust_env=False) as session:
        deadline=time.monotonic()+seconds
        async with session.ws_connect(negotiate(),max_msg_size=4096,receive_timeout=seconds) as socket:
            print(json.dumps({'status':'watching','expected_generation':generation}),flush=True)
            found=False
            while time.monotonic()<deadline:
                try:
                    message=await asyncio.wait_for(socket.receive(),timeout=max(.01,deadline-time.monotonic()))
                except (TimeoutError,asyncio.TimeoutError):
                    raise VerificationError('expected_revision_hint_not_received') from None
                if message.type==aiohttp.WSMsgType.TEXT and valid_hint(message.data,generation):found=True;break
                if message.type in (aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.ERROR):break
            require(found,'expected_revision_hint_not_received')
        # A new receive-only connection and authoritative read demonstrate recovery;
        # no token, URL, message body or connection identifier leaves this scope.
        async with session.ws_connect(negotiate(),max_msg_size=4096) as reopened:
            require(not reopened.closed,'socket_reconnect_failed')
            current=revision(test)
            require(current['generation']==generation,'socket_hint_not_authoritative')
    return {'status':'passed','hint_generation':generation,'reconnected':True,
            'authoritative_generation':current['generation'],'model_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('baseline','prepare','check','watch'))
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--proof',type=Path,required=True)
    parser.add_argument('--step',choices=STEPS)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--generation',type=int)
    parser.add_argument('--test-url-env',default='FOOTIE_PHASE4_TEST_URL')
    parser.add_argument('--production-url-env',default='FOOTIE_PHASE4_PRODUCTION_URL')
    args=parser.parse_args()
    test=production=None
    try:
        proof=json.loads(args.proof.read_text());proof_check(proof)
        test=Reader(os.environ[args.test_url_env]);production=Reader(os.environ[args.production_url_env])
        require(test.origin!=production.origin,'test_and_production_origins_identical')
        bound_proof(test,proof)
        require(not args.output.exists(),'output_already_exists')
        if args.command=='baseline':
            require(not args.state.exists(),'state_already_exists')
            state=baseline(test,production,proof);private_write(args.state,state)
            report={'status':'passed','step':'baseline','production_hash':state['production_hash'],
                    'dataset':state['dataset'],'generation':0,'original_cards':state['original_cards']}
        else:
            state=json.loads(args.state.read_text())
            require(state['schema']=='phase4_hosted_check_v1','state_schema_invalid')
            require(state['harness_sha256']==sha256(Path(__file__).read_bytes()).hexdigest(), 'harness_changed_since_baseline')
            require(proof['image_digest']==state['image_digest'], 'isolated_image_changed')
            if args.command=='prepare':
                require(args.step is not None,'step_required')
                payload=prepare(test,production,state,proof,args.step)
                private_write(args.output,payload)
                print(json.dumps({'status':'prepared','step':args.step,'payload_sha256':hashed(payload),
                                  'sent':False,'model_calls':0}),flush=True)
                return 0
            if args.command=='watch':
                require(type(args.generation) is int and 0<=args.generation<=4,'watch_generation_invalid')
                require(isolation(test)==state['config_hash'],'isolated_config_changed')
                unchanged_production(production,state)
                report=asyncio.run(watch(test,args.generation))
                unchanged_production(production,state)
            else:
                require(args.step is not None,'step_required')
                state,result=check_step(test,production,state,proof,args.step)
                private_write(args.state,state,replace=True)
                report={'status':'passed',**result,'model_calls':0}
        private_write(args.output,report)
        print(json.dumps(report,indent=2),flush=True)
        return 0
    except VerificationError as exc:
        print(json.dumps({'status':'failed','reason':str(exc),'model_calls':0}),flush=True)
        return 1
    except Exception:
        print(json.dumps({'status':'failed','reason':'verification_unavailable','model_calls':0}),flush=True)
        return 2
    finally:
        if test:test.close()
        if production:production.close()


if __name__=='__main__':raise SystemExit(main())
