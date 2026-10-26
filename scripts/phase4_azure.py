"""Explicit isolated Phase4 plan/deploy/verify/cleanup. Never sends career events.

Shared production resources are read-only references. Private Azure metadata is
captured in memory; stdout contains only fixed labels, digests and booleans.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID, uuid5

from deploy_azure import DeploymentError, require_ci
from stage_azure import patch_state, validate_production

ROOT = Path(__file__).resolve().parents[1]
APP = 'counterpress-phase4'
GROUP = 'counterpress-dev'
DEPLOYMENT = 'counterpress-phase4-isolated'
DIGEST = re.compile(r'sha256:[a-f0-9]{64}')
ROLE_IDS = {'receiver':'a638d3c7-ab3a-418d-83e6-5f17a39d4fde',
            'sender':'2b629674-e913-4c01-ae53-ef4638d8f975',
            'blob':'ba92f5b4-2d11-453d-a403-e96b0029c9fe',
            'pubsub':'12cf5a90-567b-43ae-8102-96cf46c7d9b4'}
FIXED_ENV = {
    'PHASE4_MODE':'isolated', 'CONTAINER_APP_NAME':APP,
    'COUNTERPRESS_STORAGE':'cosmos', 'COUNTERPRESS_STREAMING':'azure',
    'COUNTERPRESS_CAREER_STREAMING':'on', 'COUNTERPRESS_PROFILE_DB_PATH':':memory:',
    'COUNTERPRESS_COSMOS_DATABASE':'counterpress', 'COUNTERPRESS_COSMOS_AUTH':'managed-identity', 'COUNTERPRESS_COSMOS_CONTAINER':'histories-phase4',
    'COUNTERPRESS_EVENTHUB_NAME':'deliveries-phase4', 'COUNTERPRESS_FEED_AUTH':'managed-identity',
    'COUNTERPRESS_CHECKPOINT_CONTAINER':'eventhub-checkpoints-phase4',
    'COUNTERPRESS_QUARANTINE_CONTAINER':'rejected-deliveries-phase4',
    'COUNTERPRESS_PUBSUB_HUB':'counterpress_phase4',
    'COUNTERPRESS_ASSISTANT_MODEL':'off', 'COUNTERPRESS_EDITORIAL':'off',
    'COUNTERPRESS_STUDIO':'off', 'COUNTERPRESS_AGENT_TRACING':'off', 'COUNTERPRESS_TELEMETRY':'off',
}
COMMAND = ['uvicorn']
ARGS = ['counterpress.api.phase4:create_app','--factory','--host','0.0.0.0','--port','8000','--workers','1','--no-access-log']


def require(condition, message):
    if not condition:raise DeploymentError(message)


def missing_resource_error(stderr):
    # Azure CLI exposes the authoritative service code in its first error line.
    # Never infer absence from a word in an authorization or transport message.
    match=re.match(r'^\s*ERROR:\s*\(([A-Za-z][A-Za-z0-9]+)\)',stderr)
    if not match or match[1] not in {'ResourceNotFound','NotFound','RoleAssignmentNotFound','DeploymentNotFound','EntityNotFound','ContainerNotFound'}:
        return False
    code=re.search(r'^Code:\s*([A-Za-z][A-Za-z0-9]+)\s*$',stderr,re.MULTILINE)
    return code is None or code[1]==match[1]


def az(*args, missing=False, parse=True):
    p=subprocess.run(['az',*args,'--only-show-errors','-o','json'],capture_output=True,text=True,timeout=600)
    if p.returncode:
        if missing and missing_resource_error(p.stderr):return None
        raise DeploymentError('Phase4 Azure operation failed; private diagnostics suppressed')
    return (json.loads(p.stdout) if p.stdout.strip() else None) if parse else p.stdout.strip()


def fingerprint(app):
    return hashlib.sha256(json.dumps(patch_state(app),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def private_file(path, value):
    path=Path(path)
    require(path.resolve().is_relative_to(Path('/private/tmp')), 'Evidence must stay in /private/tmp')
    require(not path.is_symlink(), 'Evidence symlinks are not accepted')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2);f.write('\n')


def target_bundle(production):
    p=production['properties'];env={e['name']:e.get('value') for e in p['template']['containers'][0]['env']}
    base=production['id'].split('/providers/Microsoft.App/')[0]
    require(base.lower().endswith('/resourcegroups/'+GROUP), 'Unexpected resource group')
    cosmos=urlsplit(env['COUNTERPRESS_COSMOS_ENDPOINT']).hostname.split('.')[0]
    storage=urlsplit(env['COUNTERPRESS_CHECKPOINT_ENDPOINT']).hostname.split('.')[0]
    pubsub=urlsplit(env['COUNTERPRESS_PUBSUB_ENDPOINT']).hostname.split('.')[0]
    namespace=env['COUNTERPRESS_EVENTHUB_NAMESPACE'].split('.')[0]
    for name in (cosmos,storage,pubsub,namespace):require(re.fullmatch(r'[a-z0-9-]+',name), 'Invalid resource metadata')
    out={'base':base,'app':base+'/providers/Microsoft.App/containerApps/'+APP,
        'identity':base+'/providers/Microsoft.ManagedIdentity/userAssignedIdentities/'+APP,
        'cosmos':base+'/providers/Microsoft.DocumentDB/databaseAccounts/'+cosmos,
        'hub':base+'/providers/Microsoft.EventHub/namespaces/'+namespace+'/eventhubs/deliveries-phase4',
        'pubsub':base+'/providers/Microsoft.SignalRService/webPubSub/'+pubsub,
        'environment':p['environmentId'],'registry':p['configuration']['registries'][0]['server'],
        'pull':next(i for i in production['identity']['userAssignedIdentities'] if i.endswith('/counterpress-pull')),
        'endpoints':{k:env[k] for k in ('COUNTERPRESS_COSMOS_ENDPOINT','COUNTERPRESS_EVENTHUB_NAMESPACE','COUNTERPRESS_CHECKPOINT_ENDPOINT','COUNTERPRESS_PUBSUB_ENDPOINT')}}
    out['journal']=out['cosmos']+'/sqlDatabases/counterpress/containers/histories-phase4'
    out['cosmos_scope']=out['cosmos']+'/dbs/counterpress/colls/histories-phase4'
    for key,name in (('checkpoint','eventhub-checkpoints-phase4'),('quarantine','rejected-deliveries-phase4')):
        out[key]=base+'/providers/Microsoft.Storage/storageAccounts/'+storage+'/blobServices/default/containers/'+name
    return out


def arm_guid(*parts):
    # ARM guid() uses documented UUID-v5 namespace and hyphen-joined arguments.
    return str(uuid5(UUID('11fb06fb-712d-4ddd-98c7-e71bbd588830'),'-'.join(parts)))


def cleanup_manifest(bundle):
    identity=bundle['identity']
    def assignment(scope,suffix):return scope+'/providers/Microsoft.Authorization/roleAssignments/'+arm_guid(scope,identity,suffix)
    return [bundle['app'],bundle['cosmos']+'/sqlRoleAssignments/'+arm_guid(bundle['cosmos'],identity,'phase4-history-access'),
        assignment(bundle['hub'],'phase4-receiver'),assignment(bundle['hub'],'phase4-sender'),
        assignment(bundle['checkpoint'],'phase4-blob'),assignment(bundle['quarantine'],'phase4-blob'),
        assignment(bundle['pubsub'],'phase4-pubsub'),bundle['hub'],bundle['checkpoint'],bundle['quarantine'],bundle['journal'],identity]


def allowed_target(resource_id, bundle):
    return resource_id in cleanup_manifest(bundle)


def resource_version(resource_id,bundle):
    return ('2025-07-01' if resource_id==bundle['app'] else '2023-01-31' if resource_id==bundle['identity']
        else '2024-11-15' if '/Microsoft.DocumentDB/' in resource_id else '2022-04-01' if '/roleAssignments/' in resource_id
        else '2024-01-01' if '/Microsoft.EventHub/' in resource_id else '2023-05-01')


def read_target(resource_id,bundle):
    require(allowed_target(resource_id,bundle),'Unapproved resource read')
    return az('resource','show','--ids',resource_id,'--api-version',resource_version(resource_id,bundle),missing=True)


def require_fresh_targets(bundle):
    require(all(read_target(resource_id,bundle) is None for resource_id in cleanup_manifest(bundle)),
            'A verification target already exists; do not adopt it. Use the original receipt for reviewed cleanup')


def template_digest():
    return hashlib.sha256((ROOT/'infra/phase4.bicep').read_bytes()).hexdigest()


def check_what_if(result,bundle):
    changes=result.get('changes',result.get('properties',{}).get('changes',[]))
    require(isinstance(changes,list) and bool(changes), 'Empty deployment preview')
    counts={}
    for change in changes:
        kind=change['changeType'];counts[kind]=counts.get(kind,0)+1
        if kind in ('Ignore','NoChange'):continue
        require(kind=='Create' and allowed_target(change['resourceId'],bundle),
                'Deployment preview changes an unapproved resource')
        if '/roleAssignments/' in change['resourceId'] or '/sqlRoleAssignments/' in change['resourceId']:
            require(kind=='Create', 'Existing access assignment would change; review manually')
            properties=(change.get('after') or {}).get('properties',{})
            definition=properties.get('roleDefinitionId')
            ids=cleanup_manifest(bundle)
            expected={ids[2]:ROLE_IDS['receiver'],ids[3]:ROLE_IDS['sender'],ids[4]:ROLE_IDS['blob'],ids[5]:ROLE_IDS['blob'],ids[6]:ROLE_IDS['pubsub']}
            if definition and change['resourceId'] in expected:
                require(definition.split('/')[-1]==expected[change['resourceId']], 'Unexpected role definition in preview')
            if change['resourceId']==ids[1] and properties.get('scope'):
                require(properties['scope']==bundle['cosmos_scope'], 'Unexpected Cosmos scope in preview')
    return counts


def validate_test_app(app,bundle,identity,image):
    require(app['id']==bundle['app'] and app.get('tags',{}).get('purpose')=='footie-phase4', 'Not the owned verification app')
    p=app['properties'];config=p['configuration'];template=p['template']
    require(p['environmentId']==bundle['environment'] and p.get('workloadProfileName')=='Consumption', 'Shared environment drift')
    require(config['activeRevisionsMode']=='Single' and not config.get('secrets'), 'Verification must be secret-free and Single revision')
    require(config['ingress']['external'] is True and config['ingress']['allowInsecure'] is False and config['ingress']['targetPort']==8000, 'Unexpected ingress')
    registries=config.get('registries',[])
    require(len(registries)==1 and registries[0].get('server')==bundle['registry'] and registries[0].get('identity')==bundle['pull']
        and all(k in ('server','identity') or (k in ('username','passwordSecretRef') and v in (None,'')) for k,v in registries[0].items()), 'Unexpected registry authentication')
    require(set(app['identity']['userAssignedIdentities'])=={bundle['identity'],bundle['pull']}, 'Unexpected attached identity')
    require(identity['id']==bundle['identity'] and identity.get('tags',{}).get('purpose')=='footie-phase4', 'Wrong test identity')
    require(len(template['containers'])==1 and not template.get('initContainers'), 'Unexpected containers')
    c=template['containers'][0]
    require(c['name']==APP and c['image']==bundle['registry']+'/counterpress@'+image, 'Unexpected verification image')
    require(c.get('command')==COMMAND and c.get('args')==ARGS, 'Wrong API entry point')
    require(c['resources']['cpu']==0.5 and c['resources']['memory']=='1Gi', 'Unexpected compute allocation')
    entries=c.get('env',[]);env={e['name']:e.get('value') for e in entries}
    expected={**FIXED_ENV,**bundle['endpoints'],**{k:identity['properties']['clientId'] for k in
        ('COUNTERPRESS_COSMOS_CLIENT_ID','COUNTERPRESS_STREAM_CLIENT_ID','COUNTERPRESS_FEED_CLIENT_ID')}}
    require(len(entries)==len(expected) and env==expected and all(set(e)<={'name','value','secretRef'} and e.get('secretRef') in (None,'') for e in entries), 'Incomplete or mixed production/test settings')
    scale=template['scale'];require(scale['minReplicas']==0 and scale['maxReplicas']==1, 'Unexpected scale')
    rules=scale.get('rules',[]);require(len(rules)==2 and {r['name'] for r in rules}=={'http','eventhub-phase4'}, 'Unexpected scale rules')
    event=next(r['custom'] for r in rules if r['name']=='eventhub-phase4')
    require(event['type']=='azure-eventhub' and event['identity']==bundle['identity'] and event['metadata']=={
        'eventHubNamespace':bundle['endpoints']['COUNTERPRESS_EVENTHUB_NAMESPACE'].split('.')[0],
        'eventHubName':'deliveries-phase4','consumerGroup':'$Default',
        'storageAccountName':urlsplit(bundle['endpoints']['COUNTERPRESS_CHECKPOINT_ENDPOINT']).hostname.split('.')[0],
        'blobContainer':'eventhub-checkpoints-phase4','checkpointStrategy':'blobMetadata',
        'unprocessedEventThreshold':'1','activationUnprocessedEventThreshold':'0'}, 'Event consumer isolation drift')
    return True


def verify_access(bundle,identity):
    principal=identity['properties']['principalId']
    roles=az('role','assignment','list','--all','--include-inherited')
    own=[r for r in roles if r['principalId']==principal]
    wanted={(bundle['hub'],ROLE_IDS['receiver']),(bundle['hub'],ROLE_IDS['sender']),
        (bundle['checkpoint'],ROLE_IDS['blob']),(bundle['quarantine'],ROLE_IDS['blob']),
        (bundle['pubsub'],ROLE_IDS['pubsub'])}
    actual={(r['scope'],r['roleDefinitionId'].split('/')[-1]) for r in own}
    require(actual==wanted and not any(r.get('condition') for r in own), 'Test identity access differs from reviewed scopes')
    assignments=az('rest','--method','get','--url',bundle['cosmos']+'/sqlRoleAssignments?api-version=2024-11-15')['value']
    assigned=[r for r in assignments if r['properties']['principalId']==principal]
    require(len(assigned)==1 and assigned[0]['properties']['scope']==bundle['cosmos_scope'], 'Test journal identity has unexpected scope')
    role=az('rest','--method','get','--url',assigned[0]['properties']['roleDefinitionId']+'?api-version=2024-11-15')
    actions={a for p in role['properties']['permissions'] for a in p['dataActions']}
    require(actions=={'Microsoft.DocumentDB/databaseAccounts/readMetadata',*[f'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/items/{x}' for x in ('read','create','replace')]}, 'Unexpected Cosmos data permissions')
    return [r['id'] for r in own]+[assigned[0]['id']]


def production():
    app=az('containerapp','show','-g',GROUP,'-n','counterpress')
    validate_production(app)
    return app


def ensure_production(state):
    require(fingerprint(production())==state['production_fingerprint'], 'Production changed; stop and review')


def preview(args,state,bundle):
    result=az('deployment','group','what-if','-g',GROUP,'--template-file',str(ROOT/'infra/phase4.bicep'),
        '--parameters','imageDigest='+state['image_digest'],'expiresOn='+state['expires_on'],'location='+state['location'],
        '--result-format','FullResourcePayloads')
    counts=check_what_if(result,bundle)
    changes=result.get('changes',result.get('properties',{}).get('changes',[]))
    require({c['resourceId'] for c in changes if c['changeType']=='Create'}==set(cleanup_manifest(bundle)),
            'Preview must create exactly the twelve isolated resources/assignments')
    ensure_production(state)
    return counts


def publish_image():
    # This path uses only existing registry push privileges. It never deploys.
    require_ci()
    app=production();bundle=target_bundle(app);sha=os.environ['GITHUB_SHA']
    registry=bundle['registry'].split('.')[0]
    az('acr','login','--name',registry,parse=False)
    tag=bundle['registry']+'/counterpress:phase4-'+sha
    for command in (['docker','tag','counterpress:phase4',tag],['docker','push',tag]):
        result=subprocess.run(command,capture_output=True,text=True,timeout=600)
        require(result.returncode==0,'Verification image publication failed; private diagnostics suppressed')
    result=az('acr','repository','show','--name',registry,'--image','counterpress:phase4-'+sha)
    digest=result['digest'];require(DIGEST.fullmatch(digest),'Invalid registry digest')
    require(fingerprint(production())==fingerprint(app),'Production changed during image publication')
    print(json.dumps({'status':'IMAGE_PUBLISHED','commit':sha,'image_digest':digest,'deployment_performed':False}))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('## Isolated Phase4 image\n\nCommit: `'+sha+'`\n\nImage digest: `'+digest+'`\n\nNo application deployment performed.\n')


def require_terminal_deployment(state):
    deployment=az('deployment','group','show','-g',GROUP,'-n',DEPLOYMENT,missing=True)
    require(deployment is not None,'Deployment record unavailable; inspect before cleanup')
    properties=deployment['properties']
    require(properties.get('provisioningState') in ('Succeeded','Failed','Canceled'),
            'Deployment is still active; wait for completion before cleanup')
    parameters=properties.get('parameters',{})
    require(all(parameters.get(k,{}).get('value')==value for k,value in
        {'imageDigest':state['image_digest'],'expiresOn':state['expires_on'],'location':state['location']}.items()),
        'Deployment does not match the reviewed cleanup receipt')


def cleanup(state,bundle,args):
    require(args.apply and args.discard_test_data,'Cleanup requires --apply --discard-test-data after evidence is saved and producer stopped')
    require_terminal_deployment(state)
    ids=cleanup_manifest(bundle)
    require(state.get('cleanup_ids')==ids and state.get('absent_targets')==ids and state.get('deploy_attempted') is True,
            'Missing initial absence proof or unsafe cleanup manifest')
    identity=read_target(bundle['identity'],bundle)
    if identity:
        require(identity.get('tags',{}).get('purpose')=='footie-phase4' and identity['tags'].get('expiresOn')==state['expires_on'], 'Identity ownership changed')
        principal=identity['properties']['principalId']
        require(state.get('identity_principal_id',principal)==principal,'Identity principal changed during cleanup')
        state['identity_principal_id']=principal
    principal=state.get('identity_principal_id')
    if not state.get('cleanup_started'):
        app=read_target(bundle['app'],bundle)
        if app:
            require(app.get('tags',{}).get('purpose')=='footie-phase4' and app['tags'].get('expiresOn')==state['expires_on'],'App ownership changed')
            if app.get('properties',{}).get('provisioningState')=='Succeeded':
                require(identity is not None,'Ready app has no owned identity')
                validate_test_app(app,bundle,identity,state['image_digest'])
        state['cleanup_started']=True;state['cleanup_pending']=list(ids);private_file(args.state,state)
    require(isinstance(state.get('cleanup_pending'),list) and state['cleanup_pending']==[i for i in ids if i in state['cleanup_pending']],'Invalid remaining cleanup manifest')
    for resource_id in list(state['cleanup_pending']):
        ensure_production(state)
        existing=read_target(resource_id,bundle)
        if existing:
            if '/roleAssignments/' in resource_id or '/sqlRoleAssignments/' in resource_id:
                require(principal and existing['properties']['principalId']==principal,'Role ownership changed; cleanup stopped')
            if resource_id in (bundle['app'],bundle['identity']):
                require(existing.get('tags',{}).get('purpose')=='footie-phase4' and existing['tags'].get('expiresOn')==state['expires_on'],'Resource ownership changed; cleanup stopped')
            az('rest','--method','delete','--url',resource_id+'?api-version='+resource_version(resource_id,bundle),missing=True)
            if resource_id==bundle['app']:
                for _ in range(60):
                    if read_target(resource_id,bundle) is None:break
                    time.sleep(2)
                else:raise DeploymentError('Verification app deletion is still pending; resume cleanup later')
        state['cleanup_pending'].remove(resource_id);private_file(args.state,state)
    ensure_production(state)
    print(json.dumps({'status':'CLEANED','production_unchanged':True,'deleted_test_resources':len(ids)}))


def main(args):
    if args.operation=='publish':return publish_image()
    require(args.state,'Specify a private receipt under /private/tmp')
    before=production();bundle=target_bundle(before)
    if args.operation=='plan':
        require(args.image_digest and DIGEST.fullmatch(args.image_digest), 'An immutable image digest is required')
        require(args.commit and re.fullmatch(r'[a-f0-9]{40}',args.commit),'Specify the reviewed build workflow commit')
        # Prove the reviewed image exists in the existing registry; no build/push here.
        found=az('acr','repository','show','--name',bundle['registry'].split('.')[0],
            '--image','counterpress:phase4-'+args.commit)
        require(found['digest']==args.image_digest, 'Registry digest mismatch')
        state={'schema':'footie-phase4.v1','production_fingerprint':fingerprint(before),
            'image_digest':args.image_digest,'location':before['location'],'build_commit':args.commit,'template_sha256':template_digest(),
            'cleanup_ids':cleanup_manifest(bundle),'absent_targets':cleanup_manifest(bundle),'expires_on':(datetime.now(timezone.utc)+timedelta(hours=4)).isoformat()}
        require_fresh_targets(bundle)
        state['preview_counts']=preview(args,state,bundle)
        private_file(args.state,state)
        print(json.dumps({'status':'PLANNED','preview_counts':state['preview_counts'],'production_unchanged':True}))
        return
    state=json.loads(Path(args.state).read_text())
    require(state.get('schema')=='footie-phase4.v1' and DIGEST.fullmatch(state['image_digest']), 'Invalid verification receipt')
    ensure_production(state)
    if args.operation=='deploy':
        require(args.apply, 'Cloud deployment requires explicit --apply')
        require(datetime.fromisoformat(state['expires_on'])>datetime.now(timezone.utc), 'Plan expired; prepare a new reviewed plan')
        require(state.get('template_sha256')==template_digest(),'Reviewed template changed; prepare a new plan')
        require_fresh_targets(bundle)
        preview(args,state,bundle)
        state['deploy_attempted']=True;private_file(args.state,state)
        result=az('deployment','group','create','-g',GROUP,'-n',DEPLOYMENT,
            '--template-file',str(ROOT/'infra/phase4.bicep'),'--parameters',
            'imageDigest='+state['image_digest'],'expiresOn='+state['expires_on'],'location='+state['location'])
        ids=result['properties']['outputs']['cleanupIds']['value']
        require(ids==cleanup_manifest(bundle), 'Unexpected cleanup manifest')
        state['cleanup_ids']=ids;private_file(args.state,state);ensure_production(state)
        print(json.dumps({'status':'DEPLOYED','production_unchanged':True,'inference':False}))
        return
    if args.operation=='cleanup':return cleanup(state,bundle,args)
    app=az('resource','show','--ids',bundle['app'],'--api-version','2025-07-01')
    identity=az('resource','show','--ids',bundle['identity'],'--api-version','2023-01-31')
    validate_test_app(app,bundle,identity,state['image_digest'])
    role_ids=verify_access(bundle,identity)
    if args.operation=='verify':
        p=app['properties']
        require(p.get('latestReadyRevisionName')==p.get('latestRevisionName') and p.get('provisioningState')=='Succeeded','Verification revision is not ready')
        url='https://'+p['configuration']['ingress']['fqdn']
        with urlopen(url+'/api/data/revisions',timeout=45) as response:revision=json.load(response)
        require(re.fullmatch(r'[a-f0-9]{64}',revision['dataset']), 'Invalid dataset digest')
        with urlopen(url+'/api/phase4/config',timeout=45) as response:config=json.load(response)
        require(config.get('mode')=='isolated' and config.get('app')==APP and config.get('inference') is False and config.get('dataset')==revision['dataset']
            and config.get('cosmos_container')=='histories-phase4' and config.get('eventhub')=='deliveries-phase4'
            and config.get('pubsub_hub')=='counterpress_phase4' and config.get('checkpoint_container')=='eventhub-checkpoints-phase4'
            and config.get('quarantine_container')=='rejected-deliveries-phase4', 'Public isolation checks failed')
        ensure_production(state)
        proof={'isolated':True,'dataset':revision['dataset'],'inference':False,'production_unchanged':True,
            'checked_at':datetime.now(timezone.utc).isoformat(),'image_digest':state['image_digest'],
            'origin_sha256':hashlib.sha256(url.encode()).hexdigest(),
            'isolation_checks':dict.fromkeys(('journal','stream','checkpoint','quarantine','pubsub','identities','roles'),True)}
        require(args.proof, 'Specify an external private proof path');private_file(args.proof,proof)
        print(json.dumps({'status':'VERIFIED',**proof}))
        return



if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('publish','plan','deploy','verify','cleanup'))
    parser.add_argument('--state',help='Private receipt under /private/tmp')
    parser.add_argument('--image-digest')
    parser.add_argument('--source-commit','--commit',dest='commit',help='Main commit from the successful isolated image build workflow')
    parser.add_argument('--proof',help='Sanitized isolation proof under /private/tmp')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--discard-test-data',action='store_true')
    try:main(parser.parse_args())
    except DeploymentError as error:parser.exit(2,str(error)+'\n')
    except Exception:parser.exit(2,'Phase4 operation stopped; private diagnostics suppressed.\n')
