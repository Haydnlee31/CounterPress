"""Evaluate Footie against authored intents; offline by default, bounded Azure opt-in."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time

from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.evaluation import AttemptBudget, load_cases, lookup, score, summarize
from counterpress.assistant.service import AssistantService, UNSUPPORTED
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT = Path(__file__).resolve().parents[1]
MID = 'career-showcase-southbank-redhaven'


class ObservedPlanner:
    def __init__(self, inner, budget): self.inner, self.budget = inner, budget; self.reset()
    def reset(self): self.raw = None; self.usage = {}; self.attempted = False
    async def plan(self, question, context):
        from counterpress.adaptation.azure import ProviderFailure
        if not self.budget.reserve(): raise ProviderFailure('evaluation_budget', 'exhausted')
        self.attempted = True
        plan, self.usage = await self.inner.plan(question, context)
        self.raw = plan.model_dump()
        return plan, self.usage


class ObservedNarrator:
    def __init__(self, inner, budget): self.inner, self.budget = inner, budget; self.usage = {}; self.attempted = False
    async def explain(self, question, claims, depth):
        from counterpress.adaptation.azure import ProviderFailure
        if not self.budget.reserve(): raise ProviderFailure('evaluation_budget', 'exhausted')
        self.attempted = True
        result, self.usage = await self.inner.explain(question, claims, depth)
        return result, self.usage


def apply_mutation(store, case):
    if not case.get('mutation'): return
    if case['mutation'] != 'retract_goal': raise ValueError('Unknown benchmark mutation')
    events = store.original(MID).events
    goal = next(e for e in events if e.event_id == 'e01178')
    store.ingest(MID, [goal.model_copy(update={'revision': 2, 'delivery_sequence': max(e.delivery_sequence for e in events)+1,
        'available_period': 2, 'available_ms': 2700100, 'retracted': True})])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--azure', action='store_true', help='Run the preselected 10-question live sample, at most 20 model attempts')
    parser.add_argument('--case', action='append', dest='case_ids', help='Run only these authored case IDs; record this as a targeted check')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-attempts', type=int, default=20)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Choose a new output path; preserve prior evaluation results')
    if not 1 <= args.max_attempts <= 20: parser.error('--max-attempts must be 1–20')
    root = ROOT/'fixtures/personalization'
    store = DataStore(root)
    service = AssistantService(CareerService(store))
    path = ROOT/'fixtures/assistant/questions.json'
    corpus = load_cases(path, store)
    cases = [c for c in corpus['cases'] if not args.azure or c['live_sample']]
    if args.case_ids:
        unknown=set(args.case_ids)-{c['id'] for c in cases}
        if unknown: parser.error('Case IDs must belong to the selected offline corpus or live sample')
        cases=[c for c in cases if c['id'] in args.case_ids]
    rows = []; budget = None; client = None; planner = None; narrator = None
    try:
        if args.azure:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from counterpress.assistant.api import install_assistant
            from counterpress.assistant.planner import AzurePlanner
            from counterpress.assistant.narrative import AzureNarrator
            from counterpress.fan.api import FanBodyLimit
            from counterpress.adaptation.azure import load_config
            from run_footie_local import local_model_settings
            local_model_settings(ROOT/'.env')
            try: config = load_config()
            except ValueError: raise SystemExit('Invalid Azure configuration; values withheld') from None
            if config is None: raise SystemExit('Missing Azure configuration')
            budget = AttemptBudget(ROOT/'var/footie-evaluation-budget.sqlite3', args.max_attempts)
            planner = ObservedPlanner(AzurePlanner(config), budget)
            narrator = ObservedNarrator(AzureNarrator(config), budget)
            app = FastAPI(); app.add_middleware(FanBodyLimit)
            install_assistant(app, lambda: service.career, planner, narrator)
            client = TestClient(app); client.__enter__()
        for case in cases:
            changed = DataStore(root) if case.get('mutation') else None
            current = AssistantService(CareerService(changed)) if changed else service
            try:
                apply_mutation(current.store, case)
                if args.azure:
                    planner.reset(); narrator.usage = {}; narrator.attempted = False
                    started = time.monotonic()
                    response = client.post('/api/fan/assistant/ask', json=case['request'])
                    if response.status_code != 200: raise RuntimeError('Evaluation HTTP request failed')
                    answer = response.json()
                    row = score(current, case, answer, planner.raw, round((time.monotonic()-started)*1000),
                        attempted=planner.attempted, stage_usage={'planner': planner.usage, 'narrator': narrator.usage})
                    row['unreported_usage_attempts'] = int(planner.attempted and not planner.usage)+int(narrator.attempted and not narrator.usage)
                else:
                    answer, raw, duration = lookup(current, case)
                    row = score(current, case, answer, raw, duration)
                rows.append(row)
                print(f"{'PASS' if row['passed'] else 'FAIL'} {case['id']}: intent={row['raw_intent_correct']}, answer={row['answer_evidence_correct']}", flush=True)
            finally:
                if changed: changed.close()
    finally:
        if client: client.__exit__(None, None, None)
        attempts = budget.used if budget else 0
        if budget: budget.close()
        store.close()
    sources = [path, Path(__file__), *sorted((ROOT/'backend/counterpress/assistant').glob('*.py'))]
    summary = summarize(rows)
    expected_model_cases = sum(not UNSUPPORTED.search(c['request']['question']) for c in cases) if args.azure else 0
    complete = not args.azure or summary['model_routing']['total'] == expected_model_cases
    routing_ok = not args.azure or not expected_model_cases or summary['model_routing']['passed'] / expected_model_cases >= .9
    status = 'incomplete' if not complete else 'passed' if all(r['passed'] for r in rows) and routing_ok else 'failed'
    reported_tokens = {}
    for row in rows:
        for usage in row['usage'].values():
            for key,value in usage.items():reported_tokens[key] = reported_tokens.get(key,0) + value
    report = {'evaluation_status': status, 'expected_model_cases': expected_model_cases, 'reported_tokens': reported_tokens,
        'version': corpus['version'], 'created_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'azure_targeted' if args.azure and args.case_ids else 'azure_sample' if args.azure else 'offline_lookup', 'corpus_cases': len(corpus['cases']),
        'dataset_sha256': corpus['ledger_sha256'],
        'source_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sources},
        'model_attempts': attempts, 'summary': summary, 'results': rows,
        'limits': ['Authored regression cases, not unseen fan traffic.',
                   'Oracle uses reviewed intent labels and existing reducers; independent reducer audits remain separate.',
                   'Azure sample is small and single-run; do not present it as population accuracy.',
                   'Token counts exclude unknown billed usage on failed requests; no dollar-cost claim.',
                   'No hosted endpoint, synthesis, streaming write or production data mutation.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['summary'], indent=2))
    print(f'Evaluation status: {status}. Model cases: {summary["model_routing"]["total"]}/{expected_model_cases}.')
    print(f'Model attempts: {attempts}. Report: {args.output}')
    return 0 if status == 'passed' else 2 if status == 'incomplete' else 1


if __name__ == '__main__': raise SystemExit(main())
