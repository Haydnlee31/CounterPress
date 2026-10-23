"""All displayed claims are calculated here, with subject/metric/scope bindings."""
from collections import Counter
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,re
from counterpress.personalization.analytics import PlayerAnalytics,DEFINITIONS,aggregate
from counterpress.personalization.contracts import Fixture
from counterpress.personalization.metrics import select_events
from .contracts import Plan

METRICS={d[0]:d for d in DEFINITIONS}
UNSUPPORTED=re.compile(r'\b(salary|injur\w*|predict\w*|bet(?:s|ting)?|odds|sprint\w*|running distance|how far.*(?:run|ran)|fastest|top speed|weather|transfer fee|real life|system prompt|api key|endpoint|sql|delete|ignore.*instructions)\b|伤病|薪水|预测|冲刺|跑动距离',re.I)
ALIASES={
 'goals':r'\b(goal(?:s)?|scor\w*|found the net|find the net)\b|进球',
 'assists':r'\bassist(?:s)?\b|助攻',
 'key_passes':r'\b(?:chances? (?:created|creation)|chances?|key passes?|shot assists?)\b',
 'xa':r'\b(?:xa|expected assists?)\b',
 'xg':r'\b(?:xg|expected goals?)\b',
 'pass_accuracy':r'\b(pass(?:ing)? (?:accuracy|completion)|accurate pass\w*)\b|传球成功率',
 'passes':r'\b(pass(?:es|ing)?)\b|传球',
 'saves':r'\bsave\w*\b|扑救', 'clean_sheets':r'clean sheet|零封',
 'shots':r'\bshot\w*\b|射门', 'duels_won':r'challenge|duel|对抗',
 'save_pct':r'\b(?:fraction|percentage|proportion|share|percent) of (?:the )?shots(?: on target)?\b(?:(?!\b(?:and|or|plus)\b)[a-z -]){0,70}\bfaced\b(?:(?!\b(?:and|or|plus)\b)[a-z -]){0,70}\b(?:save|saved|stop|stopped)\b|扑救成功率|扑救率',
}


def requested_metrics(question):
    """Specific phrases own their spans; 'save percentage' is not a save count.

    Multiple non-overlapping measures must all be represented in the plan,
    never silently discarded. These are supported synonyms, not tactical inference.
    """
    matches=[]
    for key, pattern in ALIASES.items():
        matches.extend((m.start(),m.end(),key) for m in re.finditer(pattern,question,re.I))
    for key, definition in METRICS.items():
        pattern=r'(?<![a-zA-Z0-9_])'+re.escape(definition[1])+r'(?![a-zA-Z0-9_])'
        matches.extend((m.start(),m.end(),key) for m in re.finditer(pattern,question,re.I))
    return {key for start,end,key in matches if not any(
        a<=start and b>=end and (b-a)>(end-start) for a,b,_ in matches)}


def unresolved_percentage(question):
    """An unrecognized ratio must not quietly become its numerator counts."""
    asks_ratio=re.search(r'\b(?:percentage|fraction|proportion|percent)\b|\bshare of\b|百分比|比例',question,re.I)
    return bool(asks_ratio and not any(METRICS[m][5]=='percent' for m in requested_metrics(question)))


def player_superlative(question):
    return bool(re.search(r'\b(?:highest|greatest|largest|maximum)\b|最高|最多',question,re.I)
        and re.search(r'\b(?:players?|squad|teammates?|footballers?|who)\b|球员|谁',question,re.I))


def fingerprint(value):return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def blank(operation='clarify',**kwargs):return Plan(operation=operation,player_ids=[],club_id=None,match_id=None,metric='goals',per90=False,season=None,comparison_season=None).model_copy(update=kwargs)


def constrained_metrics(request):
    explicit=requested_metrics(request.question)
    if explicit:return explicit
    if request.previous_plan and (period_followup_operation(request) or re.search(r'^(and|what about|how about|their|his|her|那|他)|\b(last season|per 90|instead)\b',request.question,re.I)):
        return {request.previous_plan.metric,*request.previous_plan.additional_metrics}
    return set()


def period_followup_operation(request):
    """A period-only edit cannot invent a different kind of analysis."""
    previous = request.previous_plan
    if not previous or previous.operation not in ('stats', 'compare', 'recent', 'club_leaders'):
        return None
    if re.fullmatch(r'\s*(?:(?:and|what about|how about)\s+|那)?'
                    r'(?:last season|this season|career|20\d{2}-\d{2}|上赛季|本赛季|生涯)'
                    r'\s*[?？.!。]*\s*', request.question, re.I):
        return previous.operation
    return None


class AssistantService:
    def __init__(self,career):self.career,self.store=career,career.store;self.analytics=PlayerAnalytics(career)

    def scope(self,request):
        rows=self.store.rows()
        latest=max(r['kickoff'] for r in rows)
        cutoff=request.as_of or (datetime.fromisoformat(latest.replace('Z','+00:00')).replace(hour=0,minute=0,second=0)+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        seasons=sorted({r['season'] for r in rows if r['kickoff']<cutoff},reverse=True)
        return cutoff,seasons

    def context(self,request):
        cutoff,seasons=self.scope(request)
        local=self.local_plan(request)
        return {'players':[{'id':p.player_id,'name':p.name,'club':p.club_id} for p in self.store.players.values() if p.featured],
            'clubs':[{'id':c.club_id,'name':c.name} for c in self.store.clubs.values()],
            'matches':[{'id':r['id'],'home':r['home'],'away':r['away'],'date':r['kickoff']} for r in self.store.rows(featured=True) if r['kickoff']<cutoff],
            'metrics':{k:d[1] for k,d in METRICS.items()},'requested_metrics':sorted(constrained_metrics(request)),
            'period_followup_operation':period_followup_operation(request),
            'requested_operation':self.operation_constraint(request),
            'requested_per90':local.per90,
            'resolved_subjects':{'player_ids':local.player_ids,'club_id':local.club_id,'match_id':request.match_id},
            'as_of':cutoff,'seasons':seasons,'current_season':seasons[0] if seasons else None,
            'selected':{'player_id':request.player_id,'club_id':request.club_id,'match_id':request.match_id,'season':request.season,'cutoff':request.playback.model_dump() if request.playback else None,'event_id':request.event_id},
            'favorites':{'players':request.preferences.favorite_player_ids,'club':request.preferences.primary_club_id},
            'previous_plan':request.previous_plan.model_dump() if request.previous_plan else None}

    def names(self,text,registry,id_attr):
        # Never resolve a surname shared by multiple players to the first match.
        full=[getattr(p,id_attr) for p in registry.values() if re.search(r'(?<![a-zA-Z0-9_])'+re.escape(p.name)+r'(?![a-zA-Z0-9_])',text,re.I)]
        if full:return full
        candidates=[getattr(p,id_attr) for p in registry.values() if any(re.search(r'(?<!\w)'+re.escape(part)+r'(?!\w)',text,re.I) for part in p.name.split()[-1:] if len(part)>2)]
        return candidates if len(candidates)==1 else []

    def operation_constraint(self,request):
        """Bind explicit user intent, while leaving unrecognized phrasing to the model."""
        q=request.question
        if unresolved_percentage(q):return 'clarify'
        if re.search(r'\b(?:lowest|fewest|least|minimum)\b|最少|最低',q,re.I):return 'clarify'
        if re.search(r'\b(best|better|worst|creative|naturally superior)\b',q,re.I) and not constrained_metrics(request):
            return 'clarify'
        local=self.local_plan(request)
        if local.operation in ('unsupported','clarify'):return None
        if local.operation=='match' and (local.metric!='goals' or local.additional_metrics or local.per90):
            return 'clarify'
        explicit=bool(constrained_metrics(request) or period_followup_operation(request)
            or re.search(r'\b(recent|form|last five|last 5|compare|versus|vs|season|moment|this play|what happened|match|milestone)\b|最近|状态|对比|比较|赛季|比赛|里程碑',q,re.I))
        if not explicit:return None
        if local.operation=='stats' and len(local.player_ids)>1:return 'compare'
        return local.operation

    def local_plan(self,request):
        q=request.question.lower();_,seasons=self.scope(request)
        if UNSUPPORTED.search(q) or re.search(r'\b\d+(?:st|nd|rd|th)? minute\b|\b20\d\d-\d\d-\d\d\b',q):return blank('unsupported')
        if unresolved_percentage(q) or re.search(r'\b(?:lowest|fewest|least|minimum)\b|最少|最低',q,re.I):return blank('clarify')
        players=self.names(q,self.store.players,'player_id');clubs=self.names(q,self.store.clubs,'club_id')
        explicit=bool(players or clubs)
        previous=request.previous_plan
        follow=bool(period_followup_operation(request) or re.search(r'^(and|what about|how about|their|his|her|那|他)|\b(last season|per 90|instead)\b',q))
        if not players and not clubs:
            players=[request.player_id] if request.player_id else previous.player_ids if previous and follow else []
            clubs=[request.club_id] if request.club_id else [previous.club_id] if previous and follow and previous.club_id else []
        if not players and not clubs and re.search(r'my favou?rite player|我的最爱球员',q) and len(request.preferences.favorite_player_ids)==1:players=list(request.preferences.favorite_player_ids)
        if not players and not clubs and re.search(r'my club|my team|我的球队',q) and request.preferences.primary_club_id:clubs=[request.preferences.primary_club_id]
        season=request.season if request.season is not None else previous.season if previous and follow and not explicit else None
        match_season=re.search(r'20\d{2}-\d{2}(?!\d)',q)
        if match_season:season=match_season.group()
        if 'last season' in q or '上赛季' in q:season=seasons[1] if len(seasons)>1 else 'unavailable'
        elif 'this season' in q or '本赛季' in q:season=seasons[0] if seasons else 'unavailable'
        measures=requested_metrics(q)
        if len(measures)>3:return blank('clarify')
        if re.search(r'\bcareer\b|生涯',q) and not match_season and 'season' not in q and '赛季' not in q:season=None
        ordered=[key for key in METRICS if key in measures]
        metric=ordered[0] if ordered else previous.metric if previous and follow else 'goals'
        additional=ordered[1:] if ordered else list(previous.additional_metrics) if previous and follow else []
        per90=bool(re.search(r'per\s*90|/90|每90',q)) or bool(previous and follow and previous.per90)
        if re.search(r'\b(total|count)\b',q):per90=False
        op='stats';mid=request.match_id
        if re.search(r'why|milestone|what happened|moment|this play|match|scoreline|比赛|里程碑|为什么',q) and mid:op='match'
        elif re.search(r'compare|versus|\bvs\b|side by side|对比|比较',q):op='seasons' if len(players)==1 and ('season' in q or '赛季' in q or len(re.findall(r'20\d{2}-\d{2}(?!\d)',q))==2) else 'compare'
        elif re.search(r'recent|form|last five|last 5|最近|状态',q):op='recent'
        elif clubs and (re.search(r'who|lead|most|top|contribut|谁|最多|贡献',q) or player_superlative(q)):op='club_leaders'
        elif previous and follow and not explicit:op=previous.operation
        if not players and not clubs and op!='match':op='clarify'
        if re.search(r'\b(best|better|worst|creative)\b',q) and not measures:op='clarify'
        # Unknown questions must not silently turn into a goals answer.
        supported=re.search(r'goal|assist|pass|save|shot|sheet|duel|xg|stat|form|recent|season|compare|why|milestone|moment|this play|what happened|match|contribut|scor|how many|进球|助攻|传球|状态|赛季|对比|比赛|扑救|数据|里程碑',q)
        if op!='clarify' and not supported and not follow and not measures:op='unsupported'
        if op=='seasons' and ('this season' in q or '本赛季' in q):season=seasons[0] if seasons else None
        if op=='seasons' and match_season:
            named_seasons=re.findall(r'20\d{2}-\d{2}(?!\d)',q)
            comparison=named_seasons[1] if len(named_seasons)>1 else seasons[1] if len(seasons)>1 else None
        else:comparison=seasons[1] if len(seasons)>1 else None
        if op in ('match','clarify','unsupported') and additional:return blank('clarify')
        return blank(op,additional_metrics=additional,player_ids=players,club_id=clubs[0] if len(clubs)==1 else None,match_id=mid,metric=metric,per90=per90,season=season,comparison_season=comparison)

    def validate(self,plan,request):
        _,seasons=self.scope(request)
        if plan.operation in ('unsupported','clarify'):return plan
        if request.event_id and (not request.match_id or not request.playback or request.event_revision is None):
            raise ValueError('A moment requires its match, playback time and revision')
        if request.playback and plan.operation!='match':raise ValueError('Choose a career scope or a match-time question')
        q=request.question.lower()
        inherited_operation = period_followup_operation(request)
        if inherited_operation and plan.operation != inherited_operation:
            raise ValueError('A period-only follow-up must retain its operation')
        expected_operation=self.operation_constraint(request)
        if expected_operation and plan.operation!=expected_operation:
            raise ValueError('Requested operation mismatch')
        if re.search(r'\b(total|count)\b',q) and (plan.per90 or plan.operation=='recent'):
            raise ValueError('Requested count cannot become a rate or recent-form window')
        if plan.operation not in ('match','recent') and plan.per90!=self.local_plan(request).per90:
            raise ValueError('Requested rate mismatch')
        if UNSUPPORTED.search(q) or re.search(r'\b\d+(?:st|nd|rd|th)? minute\b|\b20\d\d-\d\d-\d\d\b',q):
            raise ValueError('Unsupported question scope')
        if plan.operation!='match':
            named_seasons=re.findall(r'20\d{2}-\d{2}(?!\d)',q)
            if len(named_seasons)==2:
                if plan.operation!='seasons' or {plan.season,plan.comparison_season}!=set(named_seasons):
                    raise ValueError('Season comparison mismatch')
            elif len(named_seasons)==1 and plan.season!=named_seasons[0]:raise ValueError('Season mismatch')
            elif not named_seasons:
                this='this season' in q or '本赛季' in q
                last='last season' in q or '上赛季' in q
                if this and last:
                    if len(seasons)<2 or plan.operation!='seasons' or {plan.season,plan.comparison_season}!=set(seasons[:2]):
                        raise ValueError('Season comparison mismatch')
                elif last:
                    if len(seasons)<2 or plan.season!=seasons[1]:raise ValueError('Season mismatch')
                elif this:
                    if not seasons or plan.season!=seasons[0]:raise ValueError('Season mismatch')
                else:
                    previous=request.previous_plan
                    follow=bool(re.search(r'^(and|what about|how about|their|his|her|那|他)|\b(per 90|instead)\b',q))
                    explicit=bool(self.names(q,self.store.players,'player_id') or self.names(q,self.store.clubs,'club_id'))
                    expected_season=request.season if request.season is not None else previous.season if previous and follow and not explicit else None
                    if re.search(r'\bcareer\b|生涯',q):expected_season=None
                    if plan.operation=='seasons' and expected_season is None:
                        if plan.season not in (None,seasons[0] if seasons else None):raise ValueError('Default season mismatch')
                    elif plan.season!=expected_season:raise ValueError('Default scope mismatch')
            if re.search(r'per\s*90|/90|每90',q) and plan.operation!='recent' and not plan.per90:
                raise ValueError('Rate mismatch')
        chosen=[plan.metric,*plan.additional_metrics]
        if len(chosen)>3 or len(set(chosen))!=len(chosen) or any(m not in METRICS for m in chosen):raise ValueError('Unsupported metric')
        if any(p not in self.store.players for p in plan.player_ids):raise ValueError('Unknown player')
        if plan.club_id and plan.club_id not in self.store.clubs:raise ValueError('Unknown club')
        if any(s and s not in seasons for s in (plan.season,plan.comparison_season)):raise ValueError('Unavailable season')
        explicit_metrics=constrained_metrics(request)
        if explicit_metrics and set(chosen)!=explicit_metrics:raise ValueError('Metric mismatch')
        if not explicit_metrics and plan.additional_metrics:raise ValueError('Extra metrics need an explicit request')
        if plan.additional_metrics and plan.operation not in ('stats','compare','recent','seasons','club_leaders'):raise ValueError('Unsupported compound operation')
        named=self.names(request.question,self.store.players,'player_id')
        if named and set(named)!=set(plan.player_ids):raise ValueError('Subject mismatch')
        allowed=set(named or ([request.player_id] if request.player_id else request.previous_plan.player_ids if request.previous_plan else []))
        if re.search(r'my favou?rite player|我的最爱球员',request.question,re.I) and len(request.preferences.favorite_player_ids)==1:allowed.update(request.preferences.favorite_player_ids)
        if plan.player_ids and not set(plan.player_ids)<=allowed:raise ValueError('Unresolved subject')
        clubs=self.names(request.question,self.store.clubs,'club_id')
        if clubs and plan.club_id not in clubs:raise ValueError('Club mismatch')
        allowed_clubs=set(clubs or ([request.club_id] if request.club_id else [request.previous_plan.club_id] if request.previous_plan else []))
        if re.search(r'my club|my team|我的球队',request.question,re.I):allowed_clubs.add(request.preferences.primary_club_id)
        if plan.club_id and plan.club_id not in allowed_clubs:raise ValueError('Unresolved club')
        if request.match_id and plan.match_id and plan.match_id!=request.match_id:raise ValueError('Match mismatch')
        if plan.operation in ('stats','recent','seasons') and len(plan.player_ids)!=1 and not (plan.operation=='stats' and plan.club_id and not plan.player_ids):raise ValueError('Choose a subject')
        if plan.operation=='compare' and not 2<=len(plan.player_ids)<=4:raise ValueError('Choose two to four players')
        if plan.operation=='club_leaders' and not plan.club_id:raise ValueError('Choose a club')
        if plan.operation=='club_leaders' and plan.player_ids:raise ValueError('A club ranking cannot select a player subset')
        if plan.operation=='seasons' and (not plan.comparison_season or not seasons):raise ValueError('Choose two seasons')
        if plan.operation=='match':
            if plan.metric!='goals' or plan.additional_metrics or plan.per90:
                raise ValueError('Match aggregate supports score and recorded goal milestones only')
            if not plan.match_id or plan.match_id!=request.match_id:raise ValueError('Choose a match')
            if not request.playback:raise ValueError('Choose a playback time')
            row=self.store.row(plan.match_id)
            if not row['featured']:raise ValueError('Choose a featured match')
            if row['kickoff']>=self.scope(request)[0]:raise ValueError('Match unavailable at this date')
            f=json.loads(row['fixture'])
            elapsed=request.playback.elapsed_ms+(f['period_lengths_ms'][0]+900000 if request.playback.period==2 else 0)
            wall=(datetime.fromisoformat(row['kickoff'].replace('Z','+00:00'))+timedelta(milliseconds=elapsed)).strftime('%Y-%m-%dT%H:%M:%SZ')
            if wall>self.scope(request)[0]:raise ValueError('Playback exceeds availability date')
        return plan

    def measure(self,pid,metric,season,cutoff,per90,recent=False):
        from counterpress.personalization.analytics import derive
        from counterpress.personalization.contracts import MatchRecord
        entries=[];refs=[];heat=Counter()
        revised={r[0] for r in self.store.db.execute('SELECT DISTINCT match_id FROM career_revisions')}
        for row in self.store.rows(club=self.store.players[pid].club_id,season=season,before=cutoff):
            at=self.career.historical_cutoff(row,cutoff)
            if at is False:continue
            f=json.loads(row['fixture']);cached=self.analytics.artifact['matches'][row['id']]
            if cached['digest']!=row['digest']:raise ValueError('Analytics lineage mismatch')
            data=cached['players']
            if row['id'] in revised or at is not None and at<(2,f['period_lengths_ms'][1]+1000):
                record=MatchRecord(fixture=self.store.original(row['id']).fixture,events=tuple(select_events(self.store.events(row['id']),at)))
                data=derive(record,self.store.summary(row['id'],at,completed=True))
            if pid not in data or not data[pid]['stats']['appearances']:continue
            entries.append((f,data[pid]));heat.update(data[pid]['heat'])
            refs.append({'match_id':row['id'],'event_digest':self.store.evidence_digest(row['id'],at)})
            if recent and len(entries)==5:break
        metrics=aggregate(entries)
        if self.store.players[pid].role!='GK':metrics=[m for m in metrics if m['group']!='Goalkeeping']
        matches=[f['match_id'] for f,_ in entries]
        view={'heatmap':{'cells':[{'column':int(k.split(':')[0]),'row':int(k.split(':')[1]),'actions':v} for k,v in heat.items()]}}
        item=next((m for m in metrics if m['key']==metric),None)
        scope={'season':season,'as_of':cutoff,'window':'last_five_appearances' if recent else 'whole_period','matches':len(matches)}
        val=item['per90' if per90 else 'value'] if item else None
        fact={'subject_id':pid,'subject_kind':'player','subject_name':self.store.players[pid].name,'metric':metric,'label':METRICS[metric][1],
            'value':val,'unit':'per90' if per90 else item['unit'] if item else METRICS[metric][5],'scope':scope,
            'coverage':{'recorded_matches':item['covered_matches'] if item else 0,'total_matches':len(matches)},
            'evidence':{'reducer_version':'player-analytics-v1','baseline_id':fingerprint({'refs':refs,'scope':scope,'metric':metric,'per90':per90,'value':val}),
                'matches':refs,'ledger_sha256':self.store.manifest['files']['ledger.json.gz']},'href':f'#football/player/{pid}'}
        # Rates over tiny exposure should not imply comparable performance.
        if per90 and (not item or item['covered_minutes']<180):
            fact['value']=None
            fact['evidence']['baseline_id']=fingerprint({'refs':refs,'scope':scope,'metric':metric,'per90':per90,'value':None})
        return fact,view

    @staticmethod
    def display(fact):
        v=fact['value']
        if v is None:return '—'
        return f'{v:,.2f}'.rstrip('0').rstrip('.') if v!=int(v) else f'{int(v):,}'

    def answer(self,plan,request):
        self.validate(plan,request)
        if not plan.additional_metrics:
            return self._answer_single(plan,request)
        # One caller-held revision snapshot covers every measure. Never compare
        # different units on a shared bar axis or let a partial read look complete.
        parts=[self._answer_single(plan.model_copy(update={'metric':m,'additional_metrics':[]}),request)
               for m in [plan.metric,*plan.additional_metrics]]
        facts=[f for part in parts for f in part['facts']]
        actions={a['href']:a for part in parts for a in part['actions']}
        zh=request.preferences.language=='zh-Hans'
        return {'status':'answered','title':'一起看这些数据' if zh else 'The bigger picture',
                'text':[text for part in parts for text in part['text']], 'facts':facts,
                'actions':list(actions.values()),
                'visual':{'kind':'groups','label':'数据对比' if zh else 'Measures at a glance',
                    'groups':[{'kind':'bars','label':METRICS[m][1],
                        'items':[{'label':f['subject_name']+' · '+(f['scope']['season'] or ('Last five' if f['scope']['window']=='last_five_appearances' else 'Career')),
                                  'value':f['value'],'unit':f['unit']} for f in part['facts']]}
                        for m,part in zip([plan.metric,*plan.additional_metrics],parts)]}}

    def _answer_single(self,plan,request):
        cutoff,seasons=self.scope(request)
        zh=request.preferences.language=='zh-Hans';t=lambda a,b:b if zh else a
        facts=[];visual=None;actions=[];text=[];scope_label=plan.season or t('career','生涯')
        if plan.operation in ('unsupported','clarify'):
            return {'status':plan.operation,'title':t('Let’s narrow it down','请选择范围'),'text':[t('I can look up player or club statistics, compare players or seasons, review recent form, and explain recorded match milestones. Choose a subject and a measurable statistic.','我可以查询球员或俱乐部数据、对比球员或赛季、查看近期状态和解释已记录的比赛里程碑。请选择对象和指标。')],'facts':[],'actions':[],'visual':None}
        if plan.operation=='match':
            if request.event_id:
                from .moment import moment_answer
                return moment_answer(self,plan,request)
            return self.match_answer(plan,request)
        if plan.operation=='stats' and plan.club_id and not plan.player_ids:
            p=self.career.profile(plan.club_id,'club',plan.season,cutoff)
            key=plan.metric;coverage=p['coverage']['metrics'].get(key)
            value=p['totals'].get(key) if not plan.per90 else None
            if key=='pass_accuracy' and not plan.per90:value=p['rates']['pass_accuracy_pct']
            if coverage:value=coverage['covered_total'] if coverage['recorded_matches'] and not plan.per90 else None
            facts=[{'subject_id':plan.club_id,'subject_kind':'club','subject_name':p['subject']['name'],'metric':key,'label':METRICS[key][1],'value':value,'unit':METRICS[key][5],
                'scope':{'season':plan.season,'as_of':cutoff,'window':'whole_period','matches':p['scope']['match_count']},
                'coverage':{'recorded_matches':coverage['recorded_matches'] if coverage else p['scope']['match_count'],'total_matches':p['scope']['match_count']},
                'evidence':p['evidence'],'href':f'#football/club/{plan.club_id}'}]
        elif plan.operation=='club_leaders':
            # Compare only club players with recorded exposure, never all-time world rankings.
            for player in self.store.players.values():
                if player.club_id==plan.club_id:
                    f,_=self.measure(player.player_id,plan.metric,plan.season,cutoff,plan.per90)
                    if f['value'] is not None and f['scope']['matches']:facts.append(f)
            facts=sorted(facts,key=lambda f:(-f['value'],f['subject_id']))[:5]
            text.append(t('The leading players in this club’s recorded history for the selected metric. Ties share the same value.','以下是该俱乐部记录中所选指标领先的球员；相同数值表示并列。'))
        elif plan.operation=='seasons':
            for season in (plan.season or seasons[0],plan.comparison_season):
                f,_=self.measure(plan.player_ids[0],plan.metric,season,cutoff,plan.per90);facts.append(f)
        elif plan.operation=='recent':
            for recent in (True,False):
                f,_=self.measure(plan.player_ids[0],plan.metric,plan.season,cutoff,True,recent=recent);facts.append(f)
            text.append(t('Recent form compares the last five completed appearances with the selected period, using the same per-90 measure.','近期状态按每90分钟比较最近五次完整出场与所选时期。'))
        else:
            for pid in plan.player_ids:
                f,view=self.measure(pid,plan.metric,plan.season,cutoff,plan.per90);facts.append(f)
                if plan.operation=='stats':visual={'kind':'heatmap','label':t('Where the actions happened','场上活动位置'),'cells':view['heatmap']['cells']}
        for f in facts:
            label=f['scope']['season'] or scope_label
            if f['scope']['window']=='last_five_appearances':label=t('last five appearances','最近五次出场')
            suffix='%' if f['unit']=='percent' else t(' per 90',' /90分钟') if f['unit']=='per90' else ''
            text.append(f"{f['subject_name']} · {label}: {self.display(f)}{suffix if f['unit']!='per90' else ''} {f['label'].lower()}{suffix if f['unit']=='per90' else ''}.")
            if f['value'] is None:text.append(t('There is not enough recorded coverage for this measure in the selected scope.','所选范围内没有足够的记录支持此指标。'))
            elif f['coverage']['recorded_matches']<f['coverage']['total_matches']:text.append(t(f"This figure covers {f['coverage']['recorded_matches']} of {f['coverage']['total_matches']} appearances.",f"该数据覆盖{f['coverage']['total_matches']}次出场中的{f['coverage']['recorded_matches']}次。"))
            if not any(a['href']==f['href'] for a in actions):actions.append({'label':t('View ','查看 ')+f['subject_name'],'href':f['href']})
        if request.preferences.depth=='analyst' and facts:
            text.append(t('Each figure is restricted to the stated period and recorded coverage; the breakdown below shows its denominator.', '每项数据均限定在所选时期和记录范围内；下方可查看覆盖次数。'))
        if len(facts)>1:visual={'kind':'bars','label':METRICS[plan.metric][1],'items':[{'label':f['subject_name']+' · '+(f['scope']['season'] or ('Last five' if f['scope']['window']=='last_five_appearances' else 'Career')),'value':f['value'],'unit':f['unit']} for f in facts]}
        if len(facts)==2 and all(f['value'] is not None for f in facts):
            a,b=facts
            if a['value']==b['value']:text.insert(0,t('They are level on this measure.','这项指标相同。'))
            elif plan.operation in ('compare','recent','seasons'):
                higher=a if a['value']>b['value'] else b
                text.insert(0,t(f"The higher recorded {METRICS[plan.metric][1].lower()} figure is {higher['subject_name']} in {higher['scope']['season'] or ('the last five appearances' if higher['scope']['window']=='last_five_appearances' else 'the selected period')}.",'以下对比采用相同指标和记录范围。'))
        if not facts:text=[t('No recorded observations match this scope.','该范围没有记录。')]
        return {'status':'answered','title':t('From the match records','来自比赛记录'),'text':text,'facts':facts,'visual':visual,'actions':actions}

    def match_answer(self,plan,request):
        mid=plan.match_id;at=request.playback;zh=request.preferences.language=='zh-Hans';t=lambda a,b:b if zh else a
        live=self.career.live(mid,at.period,at.elapsed_ms)
        selected=select_events(self.store.events(mid),(at.period,at.elapsed_ms));goals=[e for e in selected if e.goal_for]
        row=self.store.row(mid);home=self.store.clubs[row['home']].name;away=self.store.clubs[row['away']].name
        text=[f"{home} {live['score'][row['home']]}–{live['score'][row['away']]} {away}"]
        evidence={'match_id':mid,'event_digest':self.store.evidence_digest(mid,(at.period,at.elapsed_ms)),'baseline_id':live['baseline']['id'],
                  'events':[{'event_id':e.event_id,'revision':e.revision} for e in goals]}
        scope={'match_id':mid,'cutoff':at.model_dump(),'as_of':self.scope(request)[0],'window':'match_at_cutoff'}
        facts=[{'subject_id':c,'subject_kind':'club','subject_name':self.store.clubs[c].name,'metric':'goals','label':'Goals','value':n,'unit':'count','scope':scope,'coverage':None,'evidence':evidence,'href':f'#football/club/{c}'} for c,n in live['score'].items()]
        if goals:
            goal=goals[-1];name=self.store.players[goal.player_id].name
            before=Counter(live['score']);before[goal.goal_for]-=1;other=row['away'] if goal.goal_for==row['home'] else row['home']
            after=live['score'];own=goal.goal_for
            impact=t('extended the lead','扩大领先') if after[own]>after[other]+1 else t('put the team ahead','帮助球队领先') if after[own]>after[other] else t('brought the teams level','扳平比分') if after[own]==after[other] else t('reduced the deficit','缩小分差')
            if goal.kind=='other':impact=t('changed the score through an own goal','通过乌龙球改变比分')
            text.append(t(f'{name} {impact}: {before[row["home"]]}–{before[row["away"]]} became {after[row["home"]]}–{after[row["away"]]}.',f'{name}{impact}，比分从{before[row["home"]]}–{before[row["away"]]}变为{after[row["home"]]}–{after[row["away"]]}。'))
            milestone=next((m for m in live['milestones'] if m['event_id']==goal.event_id),None)
            if milestone:
                text.append(t(f"That was {name}’s {milestone['career_goals']}th career goal in the recorded history.",f"这是{name}在记录中的生涯第{milestone['career_goals']}球。"))
                facts.append({'subject_id':goal.player_id,'subject_kind':'player','subject_name':name,'metric':'career_goals','label':'Career goals','value':milestone['career_goals'],'unit':'count','scope':scope,'coverage':None,'evidence':{**evidence,'event_id':goal.event_id,'revision':goal.revision},'href':f'#football/player/{goal.player_id}'})
        else:text.append(t('No goal has been recorded by this point.','截至此时尚未记录进球。'))
        actions=[{'label':t('Open player profile','查看球员资料'),'href':f'#football/player/{goals[-1].player_id}'}] if goals else []
        # Only offer a clip whose entire canonical source is already available and unchanged.
        clips=json.loads((self.store.root/'highlights.json').read_text())
        for clip in clips:
            if goals and clip['match_id']==mid and clip['goal_event_id']==goals[-1].event_id and self.store.evidence_digest(mid)==row['digest'] and (clip['end']['period'],clip['end']['elapsed_ms'])<=(at.period,at.elapsed_ms):
                actions.insert(0,{'label':t('Watch the goal','观看进球'),'href':f'#football/player/{clip["scorer_id"]}','highlight':clip})
        return {'status':'answered','title':t('Why the moment matters','这一刻为什么重要'),'text':text,'facts':facts,'visual':None,'actions':actions}
