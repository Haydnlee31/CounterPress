"""Footie 34-question multi-agent benchmark; offline baseline unless explicitly selected.

--mock executes the real framework with authored provider replies, never a model.
--azure runs a bounded sample against the configured model in an isolated local app.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from pathlib import Path
import time

from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.evaluation import AttemptBudget, lookup
from counterpress.assistant.multiagent_evaluation import load_multiagent_cases, score_multiagent, summarize_multiagent
from counterpress.assistant.service import AssistantService
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore
from evaluate_footie import apply_mutation

ROOT = Path(__file__).resolve().parents[1]
LIVE_SAMPLE = {'multi_comparison', 'multi_save_percentage', 'multi_followup_metric', 'multi_neutral_keeper',
               'multi_goal_after', 'multi_match_career', 'multi_match_season', 'multi_tracking'}


class ObservedMultiAgent:
    max_requests = 4
    deadline_seconds = 24
    workflow = 'multiagent'

    def __init__(self, config, budget=None, transport_factory=None):
        self.config, self.budget, self.transport_factory = config, budget, transport_factory
        self.execution = {'requests': 0, 'roles': [], 'plans': [], 'usage': {}, 'partial_failures': [], 'completed_result': False}

    async def research(self, service, request, reserve):
        from counterpress.assistant.multiagent import MultiAgentResearch
        from counterpress.assistant.research import ResearchFailure
        self.execution = {'requests': 0, 'roles': [], 'plans': [], 'usage': {}, 'partial_failures': [], 'completed_result': False}
        def observed_reserve():
            if not reserve() or (self.budget and not self.budget.reserve()): return False
            self.execution['requests'] += 1
            return True
        def observe(kind, value):
            if kind == 'route': self.execution['roles'] = [task['role'] for task in value['tasks']]
            elif kind == 'task_plan': self.execution['plans'].append(value['plan'])
            elif kind == 'selection_proposal':
                # Preserve typed ID/length mistakes for diagnosis, never arbitrary model prose.
                def bounded_id(item):
                    return item if isinstance(item, str) and re.fullmatch(r'c[0-9]{1,4}|', item) else '[invalid ID]'
                if 'bundle_id' in value:
                    identifier = value['bundle_id']
                    self.execution['selection_proposal'] = {'bundle_id': identifier if isinstance(identifier, str)
                        and re.fullmatch(r'b[0-9]{1,4}', identifier) else '[invalid bundle]'}
                else:
                    self.execution['selection_proposal'] = {'lead': bounded_id(value.get('lead')),
                        'supporting': [bounded_id(item) for item in value.get('supporting', [])[:8]]
                        if isinstance(value.get('supporting'), list) else '[invalid array]'}
            elif kind == 'query_proposal':
                # Typed authored evaluation arguments only; unknown prose is withheld.
                raw = value.get('plan', value.get('query', value))
                if isinstance(raw, dict):
                    from counterpress.assistant.contracts import Plan
                    allowed = set(Plan.model_fields)
                    safe = {}
                    for key, item in raw.items():
                        if key not in allowed: continue
                        def atom(v):
                            return v if v is None or isinstance(v, bool) or isinstance(v, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', v) else '[invalid value]'
                        safe[key] = [atom(v) for v in item[:8]] if isinstance(item, list) else atom(item)
                    self.execution.setdefault('query_proposals', []).append(safe)
            elif kind == 'planning_failure':
                diagnostic = {key: str(item)[:80] for key, item in value.items()
                              if key in ('role', 'type', 'reason') and re.fullmatch(r'[a-zA-Z0-9_:-]{1,80}', str(item))}
                if isinstance(value.get('codes'), list):
                    diagnostic['codes'] = [code for code in value['codes'][:8]
                                           if isinstance(code, str) and re.fullmatch(r'[a-z_]{1,80}', code)]
                self.execution.setdefault('planning_failures', []).append(diagnostic)
        try:
            result = await MultiAgentResearch(self.config, self.transport_factory, observe).research(service, request, observed_reserve)
        except ResearchFailure as exc:
            self.execution.update(requests=exc.requests, usage=exc.usage,
                                  unreported_usage_attempts=exc.requests-exc.reported_requests)
            raise
        self.execution.update(roles=[task.role for task in result.tasks], plans=[plan.model_dump() for plan in result.plans],
            requests=result.requests, tools=result.tools, usage=result.usage,
            partial_failures=list(result.partial_failures), completed_result=True,
            unreported_usage_attempts=result.requests-result.reported_requests)
        return result


def authored_transport(case):
    """Provider contract fixture. Expected plans are authored, not inferred locally."""
    import httpx2
    calls = []
    tasks = case['tasks'] or [{'role': case['expected_roles'][0] if case['expected_roles'] else 'career',
                              'start': 0, 'end': len(case['request']['question']), 'scope': 'selected',
                              'expected_plan': case['expected_plan']}]
    def handler(request):
        body = json.loads(request.content)
        calls.append(body['response_format']['json_schema']['name'])
        messages = [m for m in body['messages'] if m['role'] == 'user']
        content = messages[-1]['content']
        if isinstance(content, list): content = ''.join(item.get('text', '') for item in content)
        data = json.loads(content)
        if calls[-1] == 'footie_route':
            result = {'tasks': [{'role': task['role'], 'scope': task['scope'],
                'question': case['request']['question'][task['start']:task['end']]} for task in tasks]}
        elif calls[-1] == 'footie_query':
            candidates = [t for t in tasks if case['request']['question'][t['start']:t['end']].strip() == data['question']]
            if len(candidates) != 1: raise AssertionError('Runtime rewrote an authored task')
            from counterpress.assistant.contracts import Plan
            result = Plan.model_validate(candidates[0]['expected_plan']).model_dump()
        else:
            assert calls[-1] == 'footie_story', 'Unexpected model stage'
            schema = body['response_format']['json_schema']['schema']
            if 'bundle_id' in schema['properties']:
                result = {'bundle_id': schema['properties']['bundle_id']['enum'][0]}
            else:
                claims = data['sentences']
                result = {'lead': claims[0]['id'] if claims else '',
                          'supporting': [claims[-1]['id']] if len(claims) > 1 else []}
        return httpx2.Response(200, json={'id': 'authored', 'object': 'chat.completion', 'created': 1, 'model': 'fixture',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(result)}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})
    return lambda: httpx2.MockTransport(handler), calls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--mock', action='store_true')
    mode.add_argument('--azure', action='store_true')
    split = parser.add_mutually_exclusive_group()
    split.add_argument('--heldout', action='store_true')
    split.add_argument('--fresh-heldout', action='store_true', help='Separately authored post-baseline questions; do not tune prompts against them')
    parser.add_argument('--all', action='store_true', help='Run all 34 regression cases instead of the preselected Azure sample')
    parser.add_argument('--case', action='append', dest='case_ids')
    parser.add_argument('--max-attempts', type=int, default=20)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Choose a new report path; preserve earlier results')
    if not 1 <= args.max_attempts <= 120: parser.error('--max-attempts must be 1–120')
    root = ROOT/'fixtures/personalization'
    path = ROOT/'fixtures/assistant'/('multiagent_fresh_holdout.json' if args.fresh_heldout else
                                    'multiagent_heldout.json' if args.heldout else 'multiagent_questions.json')
    sources = [path, Path(__file__), *sorted((ROOT/'backend/counterpress/assistant').glob('*.py'))]
    source_hashes = {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sources}
    store = DataStore(root)
    corpus = load_multiagent_cases(path, store)
    cases = corpus['cases']
    if args.case_ids:
        if set(args.case_ids)-{c['id'] for c in cases}: parser.error('Unknown case ID')
        cases = [c for c in cases if c['id'] in args.case_ids]
    elif args.azure and not args.heldout and not args.fresh_heldout and not args.all:
        cases = [c for c in cases if c['id'] in LIVE_SAMPLE]
    budget = None
    if args.azure:
        from counterpress.adaptation.azure import load_config
        from run_footie_local import local_model_settings
        local_model_settings(ROOT/'.env')
        try: config = load_config()
        except ValueError: raise SystemExit('Invalid Azure configuration; values withheld') from None
        if config is None: raise SystemExit('Missing Azure configuration')
        budget = AttemptBudget(ROOT/'var/footie-evaluation-budget.sqlite3', args.max_attempts,
                               hourly_limit=240, daily_limit=400)
    elif args.mock:
        from counterpress.adaptation.azure import AzureConfig
        from pydantic import SecretStr
        config = AzureConfig(endpoint='https://example.openai.azure.com', deployment='fixture', api_key=SecretStr('fake'))
    rows = []
    try:
        for case in cases:
            isolated = DataStore(root) if case.get('mutation') else None
            current = AssistantService(CareerService(isolated or store))
            try:
                apply_mutation(current.store, case)
                if args.azure or args.mock:
                    from fastapi import FastAPI
                    from fastapi.testclient import TestClient
                    from counterpress.assistant.api import install_assistant
                    factory, calls = authored_transport(case) if args.mock else (None, [])
                    observer = ObservedMultiAgent(config, budget, factory)
                    app = FastAPI()
                    install_assistant(app, lambda: current.career, researcher=observer)
                    started = time.monotonic()
                    with TestClient(app) as client:
                        response = client.post('/api/fan/assistant/ask', json=case['request'])
                    if response.status_code != 200:
                        raise RuntimeError(f'Benchmark API failed with HTTP {response.status_code}; response withheld')
                    answer = response.json()
                    duration = round((time.monotonic()-started)*1000)
                    execution = observer.execution
                else:
                    answer, _, duration = lookup(current, case)
                    execution = None
                row = score_multiagent(current, case, answer, duration, execution=execution)
                rows.append(row)
                print(f'{"PASS" if row["passed"] else "FAIL"} {case["id"]}: facts={row["facts_passed"]}, route={row["routing_correct"]}, complete={row["workflow_completed"]}', flush=True)
            finally:
                if isolated: isolated.close()
    finally:
        attempts = budget.used if budget else 0
        budget_exhausted = budget.denied if budget else False
        if budget: budget.close()
        store.close()
    summary = summarize_multiagent(rows, paid=args.azure, mocked=args.mock)
    incomplete = budget_exhausted or any(r.get('fallback') in ('model_allowance_exhausted', 'hourly_limit', 'evaluation_budget') or
                     (args.azure and r['expected_roles'] and not r['execution'].get('requests')) for r in rows)
    changed_sources = [str(p.relative_to(ROOT)) for p in sources
                       if source_hashes[str(p.relative_to(ROOT))] != sha256(p.read_bytes()).hexdigest()]
    status = 'incomplete' if incomplete or changed_sources else 'passed' if all(r['passed'] for r in rows) else 'failed'
    report = {'evaluation_status': status, 'mode': 'azure_multiagent' if args.azure else 'mock_multiagent' if args.mock else 'single_agent_lookup_baseline',
        'split': 'fresh_holdout' if args.fresh_heldout else 'heldout' if args.heldout else 'regression', 'created_at': datetime.now(timezone.utc).isoformat(),
        'corpus_cases': len(corpus['cases']), 'dataset_sha256': corpus['ledger_sha256'],
        'source_sha256': source_hashes, 'sources_changed_during_run': changed_sources,
        'model_attempts': attempts, 'summary': summary, 'results': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    print(f'Evaluation status: {status}. Paid model attempts: {attempts}. Report: {args.output}')
    return 0 if status == 'passed' else 2 if status == 'incomplete' else 1


if __name__ == '__main__': raise SystemExit(main())
