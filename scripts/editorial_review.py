"""Create a blind, printable review packet from validated pilot presentations.

Run locally. The answer key is separate; do not give it to reviewers before scoring.
This creates empty score sheets, never participant ratings or model-generated judges.
"""
import argparse
from collections import defaultdict
from html import escape
import json
from pathlib import Path
import random
import re

# Presentation-only aliases matching the Matchday identity register.
NAMES = {"eb04": "Alex Rowan", "eb06": "Jamie Vale", "eb08": "Kai Mercer",
         "eb09": "Rory Ellis", "np04": "Noah Arden", "np06": "Sam Linden", "np08": "Leo Marlow"}


def display(value):
    return escape(re.sub(r"\b(?:eb|np)\d{2}\b", lambda m: NAMES.get(m[0], m[0]), value))


def render(report, language):
    if report.get('mode') != 'live' or report['checks']['failed'] or report['checks']['errored']:
        raise ValueError('A completed, passing live report is required')
    groups = defaultdict(list)
    for row in report['rows']:
        if (row['repetition'] == 1 and row['model_eligible']
                and row['presentation']['preferences']['language'] == language):
            groups[row['case_id']].append(row)
    rng = random.Random(20261017)
    sections, key = [], {}
    for number, (case, rows) in enumerate(sorted(groups.items()), 1):
        if {r['variant'] for r in rows} != {'template', 'single_editor', 'analyst_producer'} or len(rows) != 3:
            raise ValueError('Every comparison must contain three variants')
        rng.shuffle(rows)
        candidates = []
        key[str(number)] = {'case_id': case, 'candidates': {}}
        for label, row in zip('ABC', rows):
            key[str(number)]['candidates'][label] = {'variant': row['variant'], 'status': row['status']}
            recap = row['presentation']
            statements = []
            for statement in recap['statements']:
                n = statement['narrative']
                statements.append('<article><h3>'+display(n['title'])+'</h3><p>'+display(n['explanation'])
                                  +'</p><p class="qualification">'+display(n['qualification'])+'</p></article>')
            candidates.append('<div class="candidate"><h2>'+label+'</h2>'+''.join(statements)
                              +'<p>Clarity / 清晰度: ___ &nbsp; Relevance / 相关性: ___</p>'
                               '<p>Completeness / 完整性: ___ &nbsp; Usefulness / 实用性: ___</p></div>')
        sections.append('<section><h1>Comparison / 比较 '+str(number)+'</h1><div class="cards">'
                        +''.join(candidates)+'</div><p>Preferred option or tie / 首选或并列: ____</p>'
                        '<p>Why? What was missing or misleading? / 原因、遗漏或误导之处: ____________________</p></section>')
    if not sections:
        raise ValueError('No comparable presentations for this language')
    html = '''<!doctype html><html lang="'''+language+'''"> <meta charset="utf-8">
<title>CounterPress anonymous editorial review</title>
<style>body{font:16px system-ui;color:#17372a;margin:32px;line-height:1.5}section{break-after:page;margin:40px 0}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.candidate{border:1px solid #8ca28e;padding:18px}h3{font-size:19px}.qualification{font-size:14px}article{border-bottom:1px solid #ddd;padding-bottom:12px}@media(max-width:760px){.cards{grid-template-columns:1fr}}</style>
<h1>CounterPress editorial review / 编辑呈现评估</h1>
<p>Anonymous participant ID / 匿名编号: ____ &nbsp; Date / 日期: ____</p>
<p>Fictional match simulation. These are alternative presentations of the same recorded comparisons.
Rate each dimension from 1 (poor) to 5 (excellent), then explain your preference. Ties are allowed.
Do not guess which option used AI. This sheet contains no pre-filled ratings.</p>
<p>虚构比赛模拟。各选项基于相同的记录比较。每项按 1（差）至 5（好）评分，说明偏好原因；允许并列。无需猜测哪个选项使用了 AI。</p>
'''+''.join(sections)+'</html>'
    return html, key


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('report', type=Path)
    p.add_argument('--language', choices=['en', 'zh-Hans'], default='en')
    p.add_argument('--output-dir', type=Path, default=Path('var'))
    args = p.parse_args()
    try:
        html, key = render(json.loads(args.report.read_text()), args.language)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stem = 'editorial-review-'+args.language
        (args.output_dir/(stem+'.html')).write_text(html)
        (args.output_dir/(stem+'-key.json')).write_text(json.dumps(key,indent=2)+'\n')
        print('Created blank blind review packet and separate answer key; no ratings collected.')
    except (OSError, ValueError, KeyError, TypeError):
        p.error('Could not build review packet from the supplied report')


if __name__ == '__main__':
    main()
