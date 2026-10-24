"""Existing-app, zero-production-traffic review and explicit cleanup. No promotion."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import time

from deploy_azure import DeploymentError, require_ci, run, validate_app

API = '2025-07-01'
APP = 'counterpress'
LABEL = 'footie-review'
REVISION = re.compile(r'^counterpress--[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
CANDIDATE = re.compile(r'^counterpress--stage-([0-9]+)-([0-9]+)$')


def require(condition, message):
    if not condition:raise DeploymentError(message)


def template_value(template):
    value = copy.deepcopy(template)
    value.pop('revisionSuffix', None)
    for container in value.get('containers', []):
        container['env'] = sorted(container.get('env', []), key=lambda e:e['name'])
    return value


def application_value(app):
    """All app-scoped values except our two explicit routing controls."""
    p = app['properties']; config = copy.deepcopy(p['configuration'])
    config.pop('activeRevisionsMode', None)
    config.get('ingress', {}).pop('traffic', None)
    return {'configuration':config, 'identity':app.get('identity'),
            'environment':p.get('environmentId'), 'workload':p.get('workloadProfileName')}


def pinned(app, production, candidate=None):
    traffic = app['properties']['configuration']['ingress'].get('traffic') or []
    expected = {production:100}
    if candidate:expected[candidate] = 0
    return (len(traffic) == len(expected)
            and all(not t.get('latestRevision') and t.get('revisionName') in expected
                    and t.get('weight') == expected[t['revisionName']]
                    and t.get('label') == (LABEL if t['revisionName'] == candidate else None)
                    for t in traffic)
            and len({t['revisionName'] for t in traffic}) == len(expected))


def routing(production, candidate=None, mode='Multiple'):
    weights = [{'revisionName':production, 'weight':100}]
    if candidate:weights.append({'revisionName':candidate, 'weight':0, 'label':LABEL})
    # API 2025-07-01 uses JSON Merge Patch: do not round-trip secrets/configuration.
    return {'configuration':{'activeRevisionsMode':mode,'ingress':{'traffic':weights}}}


def staging_template(original, image, suffix):
    template = copy.deepcopy(original)
    require(len(template.get('containers', [])) == 1 and not template.get('initContainers'),
            'Staging requires one application container without init containers')
    require(re.fullmatch(r'[a-zA-Z0-9]+\.azurecr\.io/counterpress@sha256:[a-f0-9]{64}', image),
            'A pinned application image is required')
    require(original['containers'][0]['image'].split('/')[0] == image.split('/')[0],
            'The image must use the existing registry')
    container = template['containers'][0]; container['image'] = image
    env = container.get('env', [])
    require(len({e['name'] for e in env}) == len(env), 'Duplicate runtime settings')
    replacements = {'COUNTERPRESS_STREAMING':'off'}
    if any(e['name'] == 'COUNTERPRESS_CAREER_STREAMING' for e in env):
        replacements['COUNTERPRESS_CAREER_STREAMING'] = 'off'
    container['env'] = [e for e in env if e['name'] not in replacements] + [
        {'name':name,'value':value} for name,value in replacements.items()]
    scale = template['scale']
    require(scale.get('minReplicas') == 0 and scale.get('maxReplicas') == 1,
            'Staging requires the existing zero-to-one replica bound')
    rules = scale.get('rules') or []
    require(all('http' in r or r.get('custom', {}).get('type') == 'azure-eventhub' for r in rules),
            'Unexpected scaler; staging stopped')
    scale['rules'] = [r for r in rules if 'http' in r]
    require(len(scale['rules']) == 1, 'One HTTP scaler is required')
    template['revisionSuffix'] = suffix
    return template


def validate_production(app):
    validate_app(app)
    p = app['properties']; name = p.get('latestRevisionName', '')
    require(REVISION.fullmatch(name), 'Invalid production revision')
    require(p.get('latestReadyRevisionName') == name and p.get('provisioningState') == 'Succeeded',
            'Production must be ready before staging')
    traffic = p['configuration']['ingress'].get('traffic') or []
    require(len(traffic) == 1 and traffic[0].get('weight') == 100 and not traffic[0].get('label')
            and (traffic[0].get('revisionName') == name or traffic[0].get('latestRevision') is True),
            'Production traffic is not an unambiguous single revision')
    return name


def revision_ready(revision):
    p = revision['properties']
    return (p.get('active') is True and p.get('provisioningState') in ('Provisioned','Succeeded')
            and p.get('healthState') == 'Healthy')


class Azure:
    def __init__(self, target):
        require(target.get('resource_group') == 'counterpress-dev', 'Unexpected resource group')
        require(re.fullmatch(r'[a-zA-Z0-9]+', target.get('registry_name', '')), 'Invalid registry')
        self.group = target['resource_group']; self.registry = target['registry_name']
        self.common = ['-g', self.group, '-n', APP, '--only-show-errors', '-o', 'json']

    def app(self):return run(['az','containerapp','show',*self.common], parse=True)

    def revisions(self):return run(['az','containerapp','revision','list',*self.common], parse=True)

    def revision(self, name):
        require(REVISION.fullmatch(name), 'Invalid revision name')
        return run(['az','containerapp','revision','show','--revision',name,*self.common], parse=True)

    def patch(self, properties):
        require(set(properties) <= {'configuration','template'}, 'Unexpected staging update')
        config = properties.get('configuration', {})
        require(set(config) <= {'activeRevisionsMode','ingress'}
                and set(config.get('ingress', {})) <= {'traffic'}, 'Unexpected app-scoped update')
        app = self.app()
        # This is a merge PATCH, never a PUT or a full app configuration copy.
        fd, name = tempfile.mkstemp(prefix='footie-stage-', suffix='.json', dir=os.environ.get('RUNNER_TEMP'))
        try:
            with os.fdopen(fd, 'w') as f:json.dump({'properties':properties}, f)
            run(['az','rest','--method','patch','--url',app['id']+'?api-version='+API,
                 '--body','@'+name,'--only-show-errors','-o','json'], timeout=300)
        finally:Path(name).unlink(missing_ok=True)

    def deactivate(self, name):
        require(CANDIDATE.fullmatch(name), 'Only the named staging revision may be deactivated')
        run(['az','containerapp','revision','deactivate','--revision',name,*self.common])

    def wait(self, predicate, message):
        for _ in range(36):
            if predicate():return
            time.sleep(5)
        raise DeploymentError(message)

    def wait_revision(self, name, template, production, baseline):
        def ready():
            app = self.app()
            require(application_value(app) == baseline, 'Unreviewed app-scoped change; stopped')
            require(app['properties']['configuration']['activeRevisionsMode'] == 'Multiple'
                    and pinned(app, production), 'Production routing mode or traffic changed; stopped')
            if name not in {r['name'] for r in self.revisions()}:return False
            revision = self.revision(name)
            require(template_value(revision['properties']['template']) == template_value(template),
                    'Revision template differs from the reviewed template')
            return revision_ready(revision) and app['properties'].get('provisioningState') == 'Succeeded'
        self.wait(ready, 'The requested revision did not become healthy; keep production pinned and run cleanup')

    def push(self):
        sha = os.environ['GITHUB_SHA']
        host = run(['az','acr','show','-n',self.registry,'--query','loginServer','-o','tsv','--only-show-errors'])
        require(host == self.registry+'.azurecr.io', 'Unexpected registry host')
        run(['az','acr','login','-n',self.registry,'--only-show-errors'])
        tag = host+'/counterpress:'+sha
        run(['docker','tag','counterpress:stage',tag]);run(['docker','push',tag],timeout=600)
        digest = run(['az','acr','repository','show','-n',self.registry,'--image','counterpress:'+sha,
                      '--query','digest','-o','tsv','--only-show-errors'])
        require(re.fullmatch(r'sha256:[a-f0-9]{64}',digest), 'Invalid registry digest')
        return host+'/counterpress@'+digest


def stage(azure, image, suffix):
    require(re.fullmatch(r'stage-[0-9]+-[0-9]+', suffix), 'Invalid staging suffix')
    before = azure.app(); production = validate_production(before); candidate = APP+'--'+suffix
    revisions = azure.revisions()  # Permission/readiness preflight before any app mutation.
    require(all(not r['properties'].get('active') or r['name'] == production for r in revisions),
            'Unexpected active revision; staging stopped')
    require(all(r['name'] != candidate for r in revisions), 'Staging revision already exists; clean up first')
    original = azure.revision(production)
    require(revision_ready(original), 'Production revision is not healthy')
    require(template_value(original['properties']['template']) == template_value(before['properties']['template']),
            'Production template changed; staging stopped')
    template = staging_template(original['properties']['template'], image, suffix)
    baseline = application_value(before)
    # Print recoverable, non-secret identities BEFORE the first app mutation.
    print('Production revision: '+production, flush=True)
    print('Candidate revision: '+candidate, flush=True)
    print('Cleanup: python3 scripts/stage_azure.py cleanup --production '+production+' --candidate '+candidate, flush=True)
    azure.patch(routing(production))  # Atomically pin the old revision AND enable Multiple.
    azure.wait(lambda:pinned(azure.app(),production)
               and azure.app()['properties']['configuration']['activeRevisionsMode'] == 'Multiple',
               'Production pin was not confirmed; no candidate was deployed')
    current = azure.app()
    require(application_value(current) == baseline
            and current['properties'].get('latestRevisionName') == production
            and current['properties']['configuration']['activeRevisionsMode'] == 'Multiple'
            and template_value(current['properties']['template']) == template_value(before['properties']['template']),
            'Unreviewed change while pinning production; stopped')
    azure.patch({'template':template})
    azure.wait_revision(candidate, template, production, baseline)
    require(azure.app()['properties'].get('latestRevisionName') == candidate,
            'An unexpected revision was created during staging; stopped')
    azure.patch(routing(production, candidate))
    azure.wait(lambda:pinned(azure.app(),production,candidate), 'Review label was not confirmed; run cleanup')
    current = azure.app()
    require(application_value(current) == baseline
            and current['properties']['configuration']['activeRevisionsMode'] == 'Multiple'
            and current['properties'].get('latestRevisionName') == candidate,
            'Unreviewed app-scoped change; stopped')
    require(revision_ready(azure.revision(candidate)), 'Candidate is no longer healthy')
    print('PASS: original production stays at 100%; candidate is 0% with public label '+LABEL, flush=True)
    print('Open Container Apps > Revisions and replicas > candidate > label URL. The label is public, not an access control.', flush=True)
    print('No live AI check was run. Complete the bounded candidate review, then cleanup before normal deployment.', flush=True)
    return production, candidate


def cleanup(azure, production, candidate):
    require(REVISION.fullmatch(production) and CANDIDATE.fullmatch(candidate)
            and production != candidate, 'Invalid cleanup revision identities')
    restored = candidate.replace('--stage-', '--restore-', 1)
    current = azure.app(); revisions = {r['name']:r for r in azure.revisions()}
    require(all(not r['properties'].get('active') or name in (production,candidate,restored)
                for name,r in revisions.items()), 'Unexpected active revision; cleanup stopped')
    require(production in revisions, 'Original production revision is unavailable; manual reviewed recovery required')
    original = azure.revision(production)['properties']['template']
    # Validate the original production settings, not the deliberately isolated staging template.
    check = copy.deepcopy(current);check['properties']['template'] = original
    check['properties']['configuration']['activeRevisionsMode'] = 'Single'
    validate_app(check)
    require(not original.get('initContainers'), 'Unexpected original template')
    baseline = application_value(current)
    if candidate in revisions:
        c = azure.revision(candidate)['properties']['template']
        expected = staging_template(original,c['containers'][0]['image'],candidate.split('--',1)[1])
        require(template_value(c) == template_value(expected), 'Candidate is not the reviewed isolated template')
    # Idempotent after a completed cleanup, while the old immutable revision still exists.
    restore_template = copy.deepcopy(original);restore_template['revisionSuffix'] = restored.split('--',1)[1]
    if restored in revisions:
        r = azure.revision(restored)
        require(template_value(r['properties']['template']) == template_value(original),
                'Restoration revision does not match original production')
    mode = current['properties']['configuration']['activeRevisionsMode']
    require(mode in ('Single','Multiple'), 'Unexpected revision mode')
    latest = current['properties'].get('latestRevisionName')
    require(latest in (production,candidate,restored), 'Unexpected latest revision; cleanup stopped')
    if mode == 'Single':
        require(latest in (production,restored) and
                template_value(current['properties']['template']) == template_value(original),
                'Single mode points at an unexpected template; cleanup stopped')
        traffic = current['properties']['configuration']['ingress'].get('traffic') or []
        require(pinned(current,latest) or (len(traffic) == 1 and traffic[0].get('latestRevision') is True
                and traffic[0].get('weight') == 100 and not traffic[0].get('label')),
                'Single mode traffic is ambiguous; cleanup stopped')
        require(revision_ready(azure.revision(latest)), 'Production is not healthy')
        require(candidate not in revisions or not revisions[candidate]['properties'].get('active'),
                'Unexpected active candidate in Single mode')
        print('PASS: original production configuration is already restored in Single mode', flush=True)
        return
    active_production = restored if pinned(current,restored) else production
    require(pinned(current,active_production) or pinned(current,production,candidate),
            'Traffic is not pinned to original production; cleanup stopped')
    # Remove the public review label first; this does not stop existing in-flight requests.
    azure.patch(routing(active_production))
    azure.wait(lambda:pinned(azure.app(),active_production), 'Production pin was not confirmed; cleanup stopped')
    if latest == production and candidate not in revisions:
        # Failure before candidate creation: no restoration revision is necessary.
        target = production
    else:
        target = restored
        if restored not in revisions:
            azure.patch({'template':restore_template})
        azure.wait_revision(restored,restore_template,active_production,baseline)
        require(azure.app()['properties'].get('latestRevisionName') == restored,
                'Restoration must be the latest revision before Single mode')
        azure.patch(routing(restored))
        azure.wait(lambda:pinned(azure.app(),restored), 'Restoration traffic was not confirmed')
    if candidate in revisions and azure.revision(candidate)['properties'].get('active'):
        azure.deactivate(candidate)
        azure.wait(lambda:not azure.revision(candidate)['properties'].get('active'),
                   'Candidate did not deactivate; keep production pinned and retry cleanup')
    before_single = azure.app()
    require(application_value(before_single) == baseline and pinned(before_single,target)
            and before_single['properties'].get('latestRevisionName') == target
            and revision_ready(azure.revision(target)), 'Single-mode safety check failed')
    azure.patch(routing(target,mode='Single'))
    def finished():
        app = azure.app()
        return (app['properties']['configuration']['activeRevisionsMode'] == 'Single'
                and app['properties'].get('latestReadyRevisionName') == target
                and app['properties'].get('provisioningState') == 'Succeeded'
                and pinned(app,target) and revision_ready(azure.revision(target)))
    azure.wait(finished, 'Single-mode restoration was not confirmed; inspect before any deployment')
    after = azure.app()
    require(application_value(after) == baseline and
            template_value(after['properties']['template']) == template_value(original),
            'Restored configuration differs from production')
    print('PASS: original production image/settings restored; candidate inactive; Single mode restored', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action',required=True)
    sub.add_parser('stage')
    clean = sub.add_parser('cleanup');clean.add_argument('--production',required=True);clean.add_argument('--candidate',required=True)
    args = parser.parse_args()
    azure = Azure(json.loads(os.environ['CP_AZURE_TARGET']))
    if args.action == 'stage':
        require_ci()
        suffix = 'stage-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
        # Validate current production before uploading; stage rechecks after the push.
        validate_production(azure.app())
        stage(azure,azure.push(),suffix)
    else:cleanup(azure,args.production,args.candidate)


if __name__ == '__main__':
    try:main()
    except DeploymentError as exc:
        print('Staging stopped: '+str(exc),flush=True)
        raise SystemExit(1) from None
    except Exception:
        print('Staging stopped: configuration, Azure operation or verification failed. Use the printed cleanup identities; do not switch traffic to latest.',flush=True)
        raise SystemExit(1) from None
