"""Bind a passing independent audit to its staged dataset. Does not deploy/copy it."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


def accept(root,report_path,analytics):
    report=json.loads(report_path.read_text());manifest=json.loads((root/'manifest.json').read_text())
    if manifest['validation_status']!='passed' or report['status']!='passed_with_coverage_limits':
        raise ValueError('Both original and expanded audit gates must pass')
    for group in ('population_flags','individual_flags','arithmetic_errors','team_reconciliation_errors','independent_simulation_flags'):
        if report.get(group):raise ValueError('Unresolved audit findings: '+group)
    if report.get('unresolved_team_role_share_flags',report.get('team_role_share_flags')):
        raise ValueError('Unresolved club share findings')
    for flag in report.get('team_role_share_flags',[]):
        ref=flag.get('source_style_reference',{});lo,hi=ref.get('central_80_range',[None,None])
        if not flag.get('source_supported_style') or not ref.get('eligible') or lo is None or not lo<=flag['share']<=hi:
            raise ValueError('Club variation lacks source support')
    if not report.get('independent_simulation_checks') or not all(c['passed'] for g in report['independent_simulation_checks'].values() for c in g.values()):
        raise ValueError('Independent expanded simulation checks are missing or failed')
    if not report.get('core_position_checks') or not all(c['passed'] for c in report['core_position_checks'].values()):
        raise ValueError('Core position checks are missing or failed')
    for name in ('model.json','ledger.json.gz','registry.json'):
        actual=sha256((root/name).read_bytes()).hexdigest()
        if report['input_sha256'][name]!=actual or manifest['files'][name]!=actual:raise ValueError('Audit input mismatch: '+name)
    if report['prior_position_report_sha256']!=sha256((root/'position-validation.json').read_bytes()).hexdigest():raise ValueError('Position report mismatch')
    if report['analytics_sha256']!=sha256(analytics.read_bytes()).hexdigest():raise ValueError('Analytics artifact mismatch')
    raw=report_path.read_bytes();(root/'spatial-validation.json').write_bytes(raw)
    manifest['files']['spatial-validation.json']=sha256(raw).hexdigest()
    manifest['spatial_validation_status']=report['status']
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Expanded audit accepted and bound to this dataset. No app files copied.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);parser.add_argument('--analytics',type=Path,required=True)
    args=parser.parse_args();accept(args.fixtures,args.report,args.analytics)
