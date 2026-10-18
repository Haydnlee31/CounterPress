"""Deterministic layouts of one approved statement; no new copy or model calls."""
from datetime import datetime, timezone
from html import escape

from counterpress.replay import display_time


def utc_label(unix_ms):
    return datetime.fromtimestamp(unix_ms / 1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def render_broadcast(view, statement, format, generated_at):
    n, c = statement.narrative, statement.citation
    if format == 'presenter-text':
        return ('\n\n'.join((n.title, n.explanation, n.qualification))
                + f'\n\n—\n{n.subject_name} · Facts through {display_time(view.recap.cutoff)}'
                + f'\nEvidence {c.evidence_id} · Revision {c.revision}'
                + f'\nMatch {view.recap.match_id} · Fingerprint {view.fingerprint}'
                + f'\nApproval {view.approval_id} · Prepared {utc_label(generated_at)}'
                + (f'\nAI wording approval expires {utc_label(view.workflow.expires_at_unix_ms)}.' if view.workflow and view.workflow.applied else '')
                + '\nSynthetic football · Fictional teams and players.'
                + '\nStatic approved copy. Recheck Studio before use; later changes cannot recall copied text.')
    label = 'Presenter cue' if format == 'presenter-cue' else 'Lower-third preview'
    windows = ' → '.join(f'({display_time(w.start)}, {display_time(w.end)}]' for w in view.recap.windows)
    expiry = (f'AI-assisted selection · Attempt {escape(view.attempt_id)} · '
              f'AI wording approval expires {utc_label(view.workflow.expires_at_unix_ms)}.'
              if view.workflow and view.workflow.applied else 'Factual wording · No AI draft selected.')
    # The full qualification travels with both formats; no truncation or free editing.
    return f'''<!doctype html><html lang="{n.language}"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>CounterPress · {label}</title>
<style>body{{font:18px/1.6 system-ui;margin:0;background:#f4f3eb;color:#173d34;padding:32px}}main{{max-width:1080px;margin:auto}}h1,h2{{line-height:1.2}}h2{{font-size:clamp(24px,4vw,38px)}}article{{padding:28px;border-left:6px solid #d9a65e;background:#fffef8;overflow-wrap:anywhere}}.stage.lower-third{{min-height:400px;display:flex;align-items:end;background:linear-gradient(135deg,#16372f,#285c4c);padding:32px}}.lower-third article{{width:100%;background:#173d34;color:#fff7df}}.qualification{{border-top:1px solid #80988b;padding-top:12px}}footer{{font-size:14px;overflow-wrap:anywhere;border-top:1px solid #8d9c92;margin-top:28px}}@media(max-width:600px){{body{{padding:18px}}.stage.lower-third{{padding:16px}}article{{padding:18px}}}}</style>
<main><header><p>COUNTERPRESS / STUDIO</p><h1>{label}</h1>
<p>Synthetic football · Fictional teams and players · Preview only</p>
<p>Read the full qualification with the claim. Rehearse timing before use; text is not shortened to fit a duration.</p></header>
<section class="stage {format}"><article><p>{escape(n.subject_name)} · Synthetic football</p>
<h2>{escape(n.title)}</h2><p>{escape(n.explanation)}</p><p class="qualification">{escape(n.qualification)}</p>
<small>Facts through {display_time(view.recap.cutoff)} · Evidence revision {c.revision}</small></article></section>
<footer><p>Windows {windows} · Start excluded, end included.</p>
<p>Evidence: {escape(c.evidence_id)} · Insight: {escape(c.insight_id)} · Revision {c.revision}<br>
Match: {escape(view.recap.match_id)} · Source version {view.source_version}</p>
<p>Approval: {escape(view.approval_id)} · Approved {utc_label(view.approved_at_unix_ms)}<br>
Prepared {utc_label(generated_at)} · {expiry}<br>Fingerprint: {view.fingerprint}</p>
<p>Static approved snapshot, not live broadcast playout. Later corrections or revocations cannot recall this downloaded file. Recheck Studio before use. Both layouts reproduce one complete approved statement; editing its wording requires a fresh review.</p></footer></main></html>'''
