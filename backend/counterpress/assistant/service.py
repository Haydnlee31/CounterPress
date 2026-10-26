"""All displayed claims are calculated here, with subject/metric/scope bindings."""
from collections import Counter
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,re
from counterpress.personalization.analytics import PlayerAnalytics,DEFINITIONS,aggregate
from counterpress.personalization.contracts import Fixture
from counterpress.personalization.metrics import select_events
from counterpress.fan.presentation import LABELS as FAN_LABELS
from .contracts import Plan
from .observation import observation_question, observation_answer

METRICS={d[0]:d for d in DEFINITIONS}


def metric_label(metric, zh=False):
    if not zh:return METRICS[metric][1]
    aliases={'pass_accuracy':'pass_accuracy_pct','shot_accuracy':'shot_accuracy_pct',
             'duel_win_pct':'duel_win_pct'}
    key=aliases.get(metric,metric)
    if key in FAN_LABELS:return FAN_LABELS[key][1]
    translations={
        'starts':'首发','non_penalty_goals':'非点球进球','shots_off_target':'射偏','shots_blocked':'射门被封堵',
        'conversion':'射门转化率','non_penalty_xg':'非点球预期进球','xg_per_shot':'每次射门预期进球',
        'goals_above_xg':'进球超出预期值','shots_inside_box':'禁区内射门','shots_outside_box':'禁区外射门',
        'shot_distance':'平均射门距离','penalty_shots':'主罚点球','penalty_goals':'点球进球','penalty_conversion':'点球命中率',
        'headed_shots':'头球射门','headed_goals':'头球进球','woodwork':'击中门框','goal_involvements':'进球与助攻',
        'xa':'预期助攻','passes_incomplete':'未成功传球','expected_completions':'预期成功传球',
        'expected_pass_accuracy':'预期传球成功率','passing_above_expected':'传球成功率超出预期值',
        'mean_pass_speed':'估计传球速度','mean_shot_speed':'估计射门速度','progressive_passes':'向前推进传球尝试',
        'progressive_passes_completed':'成功向前推进传球','progressive_accuracy':'向前推进传球成功率',
        'final_third_entries':'传入进攻三区','box_entries':'传入禁区','long_passes':'长传尝试','long_passes_completed':'成功长传',
        'long_accuracy':'长传成功率','forward_passes':'向前传球','backward_passes':'回传','lateral_passes':'横传',
        'pass_distance':'平均传球距离','crosses':'传中尝试','crosses_completed':'成功传中','cross_accuracy':'传中成功率',
        'passes_received':'接球','actions':'有球活动','box_actions':'对方禁区内有球活动','carries':'带球',
        'carry_distance_m':'带球距离','progressive_carries':'向前推进带球','carry_box_entries':'带球进入禁区',
        'duels':'地面对抗','duels_lost':'地面对抗失利','duels_drawn':'地面对抗未分胜负',
        'high_recoveries':'进攻三区夺回球权','save_pct':'扑救成功率','clean_sheet_pct':'零封率'}
    return translations.get(metric,METRICS[metric][1])


UNSUPPORTED=re.compile(r'\b(salary|injur\w*|predict\w*|bet(?:s|ting)?|odds|sprint\w*|running distance|how far.*(?:run|ran)|fastest|(?:top |maximum |peak )?(?:running|sprinting|player|athlete) speed|top speed|weather|transfer fee|real life|system prompt|api key|endpoint|sql|delete|ignore.*instructions)\b|\b(?:kilomet(?:er|re)s?|km/h|m/s|tracking speed|off[- ]?ball|thinking|intentions?|forecast\w*)\b|\b(?:speed|distance)\b.{0,50}\b(?:animation|animated|tracking|ran|run|covered)\b|\b(?:will|going to)\b.{0,60}\b(?:win|score|lose)\b|\b(?:coach|manager)\b.{0,50}\b(?:thought|wanted|intended|decided)\b|伤病|薪水|预测|冲刺|跑动距离|想法|教练.*意图',re.I)
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


def asks_regain_interval(question):
    """Recognize questions about the possession's origin, not just a duration.

    The same evidence gap matters when a fan asks whether the timeline covers
    the whole move or only its finish. Do not infer a regain from that wording.
    """
    return bool(re.search(
        r'regain|recover|(?:win|winning|won|get|getting|got|gain|gained|establish|established)'
        r'.{0,50}\b(?:ball|possession|control)\b|'
        r'\b(?:possession|control)\b.{0,25}\b(?:won|gained|established|recovered)\b|'
        r'\b(?:start|beginning|origin|entire|whole|full)\b.{0,45}\b(?:move|attack|possession|buildup|build-up|sequence)\b|'
        r'\b(?:move|attack|possession|buildup|build-up|sequence)\b.{0,45}\b(?:start|begin|began|beginning)\b|'
        r'\b(?:only|just)\b.{0,25}\b(?:final|last|end)\b.{0,15}\b(?:part|phase|segment|seconds)\b|'
        r'夺回|抢回|取得控制|获得球权|进攻.*(?:起点|开始|完整|末段)|(?:完整|整段).*进攻', question, re.I))


SCORING_MOMENT = r'(?:goal|finish|equalizer|equaliser|winner)'
RELATION_HISTORY = re.compile(r'\b(?:career|season|historical|history|total|totals|rate|percentage)\b|\b(?:how many|last five|last 5|recent form|per\s*90)\b|/90|生涯|赛季|总共|成功率', re.I)


def scoring_contributor(question):
    """Resolve grammatical roles separately from the scorer named in the question.

    The return value is an untrusted name phrase, never a player ID. Historical
    aggregates deliberately stay outside this single-moment interpretation.
    """
    if not re.search(r'\b'+SCORING_MOMENT+r'\b', question, re.I):return None
    patterns = (
        r'\bhow (?:did|does|has)\s+(.+?)\s+(?:contribut\w*|help(?:ed)?)\b',
        r'\bwhat role (?:did|does|has)\s+(.+?)\s+(?:play|played)\b',
        r'\b(?:explain|describe|show(?: me)?|what (?:was|is))\s+(.+?)[’\']s\s+(?:role|contribution|involvement)\b',
        r'\b(?:role|contribution|involvement)\s+of\s+(.+?)\s+(?:in|to|for|during)\b',
    )
    for pattern in patterns:
        match = re.search(pattern, question, re.I)
        if match:return match.group(1).strip()
    return None


def scoring_possessors(question):
    """Names owning a scoring moment; keep data-plane name matching strict."""
    phrases = re.finditer(r"([a-z]+(?:[ -][a-z]+){0,3})[’']s\s+"+SCORING_MOMENT+r'\b', question, re.I)
    fillers = {'to','in','of','for','the','this','that','before','behind','during','explain','describe','show','me',
               'contribute','contributed','help','with','create','created','make','made','what','how','did','does','has',
               'was','is','role','play','played','contribution','involvement','lead','led','buildup'}
    result=[]
    for match in phrases:
        words=match.group(1).split()
        boundaries=[i for i,word in enumerate(words) if word.lower() in {'to','in','of','for','before','behind','during','with'}]
        if boundaries:words=words[boundaries[-1]+1:]
        while words and words[0].lower() in fillers:words.pop(0)
        phrase=' '.join(words)
        if phrase:result.append(phrase)
    return result


def sequence_pass_count_intent(q):
    """True for one sequence count, False for aggregates, None for other questions."""
    # A count of the passes leading into one finish belongs to that observed
    # sequence, not the career pass-total tool or a generic match score query.
    sequence_pass_count = (
        re.search(r'\b(?:how many|number of|count(?: the)?)\s+(?:(?:completed|successful)\s+)?passes\b',q,re.I)
        and re.search(r'\bpasses\s+(?:that\s+)?(?:(?:led|leading)\s+(?:up\s+)?to|preceded)\s+.{0,80}\b'+SCORING_MOMENT+r'\b',q,re.I))
    if sequence_pass_count:
        history_or_rate=re.search(r'\b(?:career|season|seasons|matches|games|fixtures|history|historical|recent|average|percentage|accuracy|rate)\b|\b(?:last five|last 5|per\s*90|whole match|entire match)\b|/90',q,re.I)
        return not bool(history_or_rate)
    return None


def requested_analysis(request):
    """Recognize the three investigation intents without replacing career questions."""
    q=request.question
    if observation_question(request):return 'match_changes'
    count_intent=sequence_pass_count_intent(q)
    if count_intent is not None:return 'buildup' if count_intent else None
    if scoring_contributor(q):
        return None if RELATION_HISTORY.search(q) else 'buildup'
    if re.search(r'what (?:made|led to|created|set up) (?:that|this|the) goal|how (?:was|did).*(?:goal|buildup)|build[ -]?up|before (?:the |that |this )?(?:goal|finish)|进球.*(?:过程|形成)|如何.*进球',q,re.I):
        return 'buildup'
    if re.search(r'what(?: has|’s|\'s)? changed|how.*(?:game|match).*(?:changed|changing)|changes? in (?:the |this )?(?:game|match)|比赛.*变化',q,re.I):
        return 'match_changes'
    if (request.match_id and not re.search(r'career|recent|last five|season|生涯|最近|赛季',q,re.I)
            and re.search(r'how (?:is|has|are)|performance|involvement|表现|参与',q,re.I)
            and re.search(r'doing|playing|performed|performance|involvement|表现|参与',q,re.I)):
        return 'player_performance'
    return None


def analysis_options(request):
    """Strong intents bind; open match questions can be interpreted by the model.

    Counting/rate/history requests never become an unrequested investigation.
    Unknown wording is not itself evidence that a question is unsupported.
    """
    if UNSUPPORTED.search(request.question):return [None]
    explicit=requested_analysis(request)
    if explicit:return [explicit]
    if not request.match_id or not request.playback or UNSUPPORTED.search(request.question):return [None]
    if re.search(r'how many|how much|\b(total|count|scoreline|percentage|accuracy|completion|rate|career|season)\b|recent\s+(?:form|appearances)|last\s+(?:five|5)\s+(?:matches|appearances)|per\s*90|/90|what.*(?:score|scoreline)|多少|总共|生涯|赛季|最近|成功率',request.question,re.I):return [None]
    return [None,'buildup','player_performance','match_changes']


def constrained_metrics(request):
    if requested_analysis(request):return set()
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
        context={'players':[{'id':p.player_id,'name':p.name,'club':p.club_id} for p in self.store.players.values() if p.featured],
            'clubs':[{'id':c.club_id,'name':c.name} for c in self.store.clubs.values()],
            'matches':[{'id':r['id'],'home':r['home'],'away':r['away'],'date':r['kickoff']} for r in self.store.rows(featured=True) if r['kickoff']<cutoff],
            'metrics':{k:d[1] for k,d in METRICS.items()},'requested_metrics':[] if len(analysis_options(request))>1 else sorted(constrained_metrics(request)),
            'period_followup_operation':period_followup_operation(request),
            'requested_operation':self.operation_constraint(request),
            'requested_analysis':local.analysis,'analysis_options':analysis_options(request),
            'requested_per90':local.per90,
            'resolved_subjects':{'player_ids':local.player_ids,'club_id':local.club_id,'match_id':request.match_id},
            'as_of':cutoff,'seasons':seasons,'current_season':seasons[0] if seasons else None,
            'selected':{'player_id':request.player_id,'club_id':request.club_id,'match_id':request.match_id,'season':request.season,'cutoff':request.playback.model_dump() if request.playback else None,'event_id':request.event_id},
            'favorites':{'players':request.preferences.favorite_player_ids,'club':request.preferences.primary_club_id},
            'previous_plan':request.previous_plan.model_dump() if request.previous_plan else None}
        if observation_question(request):
            context['selected']['observation'] = {'id':request.observation_id,
                'comparison':'two adjacent three-minute windows ending at the selected cutoff',
                'question_scope':'the selected observation only; the tool resolves its metric and subject'}
        if request.playback:
            # Intent is resolved against server-validated IDs; the model does not
            # need the entire career catalogue to query one selected match.
            ids=set(local.player_ids)|set(request.preferences.favorite_player_ids)|set(self.names(request.question,self.store.players,'player_id'))
            if request.player_id:ids.add(request.player_id)
            context['players']=[p for p in context['players'] if p['id'] in ids]
            context['matches']=[m for m in context['matches'] if m['id']==request.match_id]
            match=next(iter(context['matches']),None)
            club_ids={match['home'],match['away']} if match else set()
            if local.club_id:club_ids.add(local.club_id)
            context['clubs']=[c for c in context['clubs'] if c['id'] in club_ids]
            context['metrics']={'goals':'Match analysis carrier'}
            context['seasons']=[];context['current_season']=None
        return context

    def names(self,text,registry,id_attr):
        # Never resolve a surname shared by multiple players to the first match.
        full=[getattr(p,id_attr) for p in registry.values() if re.search(r'(?<![a-zA-Z0-9_])'+re.escape(p.name)+r'(?![a-zA-Z0-9_])',text,re.I)]
        if full:return full
        candidates=[getattr(p,id_attr) for p in registry.values() if any(re.search(r'(?<!\w)'+re.escape(part)+r'(?!\w)',text,re.I) for part in p.name.split()[-1:] if len(part)>2)]
        return candidates if len(candidates)==1 else []

    def unresolved_analysis_subject(self,question,analysis):
        """An explicit unknown name must never inherit the open profile's subject."""
        if analysis=='buildup':
            contributor=scoring_contributor(question)
            if contributor and not RELATION_HISTORY.search(question):
                if not self.exact_player_subject(contributor):return True
            for subject in scoring_possessors(question) if contributor else []:
                if re.search(r'\b(?:goal|finish|move|play|sequence|attack)\s*$',subject,re.I):continue
                if re.search(r'\b(?:player|team|club)\b',subject,re.I) or self.names(subject,self.store.clubs,'club_id'):continue
                if not self.exact_player_subject(subject):return True
            match=re.search(r"([a-z]+(?: [a-z]+){0,3})[’']s (?:goal|finish|buildup)\b",question,re.I)
            if not match:return False
            subject=match.group(1)
            # A possessive event ('this goal’s buildup') does not name a player.
            if re.search(r'\b(?:goal|finish|move|play|sequence|attack)\s*$',subject,re.I):return False
            return not self.names(subject,self.store.players,'player_id') and not self.names(subject,self.store.clubs,'club_id') and not re.search(r'\b(?:player|team|club)\b',subject,re.I)
        if analysis=='player_performance':
            patterns=[r'how (?:is|are|has|have)\s+(.+?)\s+(?:doing|playing|performed|been doing|been playing)',
                      r'(?:performance|involvement) of\s+(.+?)(?:\s+in\b|\s+this\b|[?？]|$)']
            registry,id_attr=self.store.players,'player_id'
            pronouns={'he','she','they','him','her','them','my player','my favourite player','my favorite player','this player','the player','my selected player'}
        elif analysis=='match_changes':
            patterns=[r'(?:changed|changing|changes)\s+(?:for|at|with)\s+(.+?)(?:\s+in\b|\s+this\b|[?？]|$)',
                      r'how (?:has|have|is|are)\s+(.+?)\s+(?:changed|changing)']
            registry,id_attr=self.store.clubs,'club_id'
            pronouns={'my club','my team','this club','this team','the team','the club','the match','the game','this match','this game','they'}
        else:return False
        for pattern in patterns:
            match=re.search(pattern,question,re.I)
            if match:
                subject=match.group(1).strip()
                if subject.lower() not in pronouns and not self.names(subject,registry,id_attr):return True
        return False

    def exact_player_subject(self,phrase):
        """A multiword unknown name cannot inherit a known player's surname."""
        normalized=phrase.strip().casefold()
        exact=[getattr(p,'player_id',pid) for pid,p in self.store.players.items() if p.name.casefold()==normalized]
        if exact:return exact
        return self.names(phrase,self.store.players,'player_id') if len(phrase.split())==1 else []

    def operation_constraint(self,request):
        """Bind explicit user intent, while leaving unrecognized phrasing to the model."""
        q=request.question
        if requested_analysis(request):return 'match' if request.match_id else 'clarify'
        if unresolved_percentage(q):return 'clarify'
        if re.search(r'\b(?:lowest|fewest|least|minimum)\b|最少|最低',q,re.I):return 'clarify'
        if re.search(r'\b(best|better|worst|creative|naturally superior)\b',q,re.I) and not constrained_metrics(request):
            return 'clarify'
        local=self.local_plan(request)
        if local.operation in ('unsupported','clarify'):return None
        if len(analysis_options(request))>1:return 'match'
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
        analysis=requested_analysis(request)
        explicit_favorite=bool(re.search(r'my favou?rite player|我的最爱球员',q))
        if explicit_favorite and not self.names(q,self.store.players,'player_id'):
            if len(request.preferences.favorite_player_ids)!=1:return blank('clarify')
            players=list(request.preferences.favorite_player_ids);clubs=[]
        if analysis:
            if self.unresolved_analysis_subject(request.question,analysis):return blank('clarify')
            if not request.match_id or not request.playback:return blank('clarify')
            if analysis=='player_performance' and not players and re.search(r'my player|我的球员',q) and len(request.preferences.favorite_player_ids)==1:
                players=list(request.preferences.favorite_player_ids)
            if analysis=='player_performance' and len(players)!=1:return blank('clarify')
            return blank('match',analysis=analysis,player_ids=players if analysis=='player_performance' else [],
                         club_id=clubs[0] if len(clubs)==1 and analysis=='match_changes' else None,match_id=request.match_id)
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
        if plan.investigate_player_id and plan.analysis!='buildup':raise ValueError('Invalid follow-up scope')
        if plan.analysis and plan.operation!='match':raise ValueError('Analysis requires match scope')
        if plan.operation in ('unsupported','clarify'):return plan
        if request.event_id and (not request.match_id or not request.playback or request.event_revision is None):
            raise ValueError('A moment requires its match, playback time and revision')
        if request.playback and plan.operation!='match':raise ValueError('Choose a career scope or a match-time question')
        q=request.question.lower()
        if plan.analysis not in analysis_options(request):raise ValueError('Analysis intent mismatch')
        if plan.analysis and self.unresolved_analysis_subject(request.question,plan.analysis):raise ValueError('Unknown named subject')
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
        if explicit_metrics and not plan.analysis and set(chosen)!=explicit_metrics:raise ValueError('Metric mismatch')
        if not explicit_metrics and plan.additional_metrics:raise ValueError('Extra metrics need an explicit request')
        if plan.additional_metrics and plan.operation not in ('stats','compare','recent','seasons','club_leaders'):raise ValueError('Unsupported compound operation')
        named=self.names(request.question,self.store.players,'player_id')
        if named and plan.analysis not in ('buildup','match_changes') and set(named)!=set(plan.player_ids):raise ValueError('Subject mismatch')
        allowed=set(named or ([request.player_id] if request.player_id else request.previous_plan.player_ids if request.previous_plan else []))
        if re.search(r'my (?:favou?rite )?player|我的最爱球员|我的球员',request.question,re.I) and len(request.preferences.favorite_player_ids)==1:allowed.update(request.preferences.favorite_player_ids)
        if plan.player_ids and not set(plan.player_ids)<=allowed:raise ValueError('Unresolved subject')
        clubs=self.names(request.question,self.store.clubs,'club_id')
        if clubs and plan.analysis not in ('buildup','player_performance') and plan.club_id not in clubs:raise ValueError('Club mismatch')
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
            if plan.analysis=='player_performance' and len(plan.player_ids)!=1:raise ValueError('Choose one player')
            if plan.analysis in ('buildup','match_changes') and plan.player_ids:raise ValueError('Unexpected player subset')
            if plan.analysis and (plan.season or plan.comparison_season):raise ValueError('Analysis uses playback scope')
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
                    'groups':[{'kind':'bars','label':metric_label(m,zh),
                        'items':[{'label':f['subject_name']+' · '+(f['scope']['season'] or (('最近五次出场' if zh else 'Last five') if f['scope']['window']=='last_five_appearances' else ('生涯' if zh else 'Career'))),
                                  'value':f['value'],'unit':f['unit']} for f in part['facts']]}
                        for m,part in zip([plan.metric,*plan.additional_metrics],parts)]}}

    def _answer_single(self,plan,request):
        cutoff,seasons=self.scope(request)
        zh=request.preferences.language=='zh-Hans';t=lambda a,b:b if zh else a
        facts=[];visual=None;actions=[];text=[];scope_label=plan.season or t('career','生涯')
        if plan.operation in ('unsupported','clarify'):
            intent=requested_analysis(request)
            if plan.operation=='clarify' and intent:
                question=t('Which match or goal would you like me to look at? Open it, then ask Footie.','您想了解哪场比赛或哪个进球？打开后再询问 Footie。') if not request.match_id or not request.playback else t('Which player would you like me to look at? Name one player from this match.','您想了解哪位球员？请指定本场的一位球员。') if intent=='player_performance' else t('Which part should I check: this play, or a player’s history?','您想了解这次进攻还是球员历史？')
                return {'status':'clarify','title':t('A little more context','需要更多背景'),'text':[question],'facts':[],'actions':[],'visual':None}
            if plan.operation=='clarify':
                if not request.match_id and not request.player_id and not request.club_id and not self.names(request.question,self.store.players,'player_id') and not self.names(request.question,self.store.clubs,'club_id'):
                    question=t('Which match, player or club would you like to look at? Select one or include its name in your question.','您想了解哪场比赛、哪位球员或哪家俱乐部？请选择对象或在问题中提供名称。')
                elif request.match_id:
                    question=t('Which player or part of this match should I check? You can ask about a goal, a player’s performance, or how the game changed.','您想了解本场的哪位球员或哪个方面？可以询问进球过程、球员表现或比赛变化。')
                else:
                    question=t('Which statistic and period would you like to compare? For example, goals this season or assists over a career.','您想比较哪项数据和哪个时期？例如本赛季进球或生涯助攻。')
                return {'status':'clarify','title':t('A little more context','需要更多背景'),'text':[question],'facts':[],'actions':[],'visual':None}
            return {'status':plan.operation,'title':t('Let’s narrow it down','请选择范围'),'text':[t('I can look up player or club statistics, compare players or seasons, review recent form, and explain recorded match milestones. Choose a subject and a measurable statistic.','我可以查询球员或俱乐部数据、对比球员或赛季、查看近期状态和解释已记录的比赛里程碑。请选择对象和指标。')],'facts':[],'actions':[],'visual':None}
        if plan.operation=='match':
            if plan.analysis:return self.intelligence_answer(plan,request)
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
            f['label']=metric_label(f['metric'],zh)
            label=f['scope']['season'] or scope_label
            if f['scope']['window']=='last_five_appearances':label=t('last five appearances','最近五次出场')
            suffix='%' if f['unit']=='percent' else t(' per 90',' /90分钟') if f['unit']=='per90' else ''
            text.append(f"{f['subject_name']} · {label}：{f['label']} {self.display(f)}{suffix}。" if zh else
                f"{f['subject_name']} · {label}: {self.display(f)}{suffix if f['unit']!='per90' else ''} {f['label'].lower()}{suffix if f['unit']=='per90' else ''}.")
            if f['value'] is None:text.append(t('There is not enough recorded coverage for this measure in the selected scope.','所选范围内没有足够的记录支持此指标。'))
            elif f['coverage']['recorded_matches']<f['coverage']['total_matches']:text.append(t(f"This figure covers {f['coverage']['recorded_matches']} of {f['coverage']['total_matches']} appearances.",f"该数据覆盖{f['coverage']['total_matches']}次出场中的{f['coverage']['recorded_matches']}次。"))
            if not any(a['href']==f['href'] for a in actions):actions.append({'label':t('View ','查看 ')+f['subject_name'],'href':f['href']})
        if request.preferences.depth=='analyst' and facts:
            text.append(t('Each figure is restricted to the stated period and recorded coverage; the breakdown below shows its denominator.', '每项数据均限定在所选时期和记录范围内；下方可查看覆盖次数。'))
        if len(facts)>1:visual={'kind':'bars','label':metric_label(plan.metric,zh),'items':[{'label':f['subject_name']+' · '+(f['scope']['season'] or (t('Last five','最近五次出场') if f['scope']['window']=='last_five_appearances' else t('Career','生涯'))),'value':f['value'],'unit':f['unit']} for f in facts]}
        if len(facts)==2 and all(f['value'] is not None for f in facts):
            a,b=facts
            if a['value']==b['value']:text.insert(0,t('They are level on this measure.','这项指标相同。'))
            elif plan.operation in ('compare','recent','seasons'):
                higher=a if a['value']>b['value'] else b
                text.insert(0,t(f"The higher recorded {METRICS[plan.metric][1].lower()} figure is {higher['subject_name']} in {higher['scope']['season'] or ('the last five appearances' if higher['scope']['window']=='last_five_appearances' else 'the selected period')}.",'以下对比采用相同指标和记录范围。'))
        if not facts:text=[t('No recorded observations match this scope.','该范围没有记录。')]
        return {'status':'answered','title':t('From the match records','来自比赛记录'),'text':text,'facts':facts,'visual':visual,'actions':actions}

    def investigation_candidates(self,plan,request):
        """A bounded follow-up can inspect only observed, meaningful participants."""
        if plan.analysis!='buildup':return []
        from .intelligence import goal_buildup
        fixture=Fixture.model_validate_json(self.store.row(plan.match_id)['fixture'])
        at=(request.playback.period,request.playback.elapsed_ms)
        events=self.store.events(plan.match_id)
        selected=select_events(events,at)
        eid=request.event_id or next((e.event_id for e in reversed(selected) if e.goal_for),None)
        if not eid:return []
        event=next((e for e in selected if e.event_id==eid),None)
        if request.event_id:
            if not event or event.revision!=request.event_revision:return []
            at=(event.available_period,event.available_ms)
        result=goal_buildup(fixture,events,event_id=eid,cutoff=at,expected_revision=request.event_revision)
        if result['status']!='available':return []
        named=set(self.names(request.question,self.store.players,'player_id'))
        favorites=set(request.preferences.favorite_player_ids)
        candidates=[]
        for row in result['contributions']:
            meaningful=sum(row[k] for k in ('completed_passes','receptions','carries'))
            if meaningful<2 or named and row['player_id'] not in named:continue
            candidates.append({'player_id':row['player_id'],'name':self.store.players[row['player_id']].name,
                'completed_passes':row['completed_passes'],'receptions':row['receptions'],'carry_segments':row['carries'],
                'favorite':row['player_id'] in favorites,'observed_involvement':meaningful})
        return sorted(candidates,key=lambda c:(not c['favorite'],-c['observed_involvement'],c['player_id']))[:3]

    def intelligence_answer(self,plan,request):
        """Deterministic investigation; every sentence remains replay/revision bound."""
        from .intelligence import goal_buildup, involvement, compare_windows
        row=self.store.row(plan.match_id)
        fixture=Fixture.model_validate_json(row['fixture'])
        at=(request.playback.period,request.playback.elapsed_ms)
        events=self.store.events(plan.match_id)
        selected=select_events(events,at)
        zh=request.preferences.language=='zh-Hans';t=lambda en,cn:cn if zh else en
        def unavailable(en,cn):
            return {'status':'clarify','title':t('A little more context','需要更多背景'),'text':[t(en,cn)],'facts':[],'actions':[],'visual':None}
        if request.event_id:
            selected_event=next((e for e in selected if e.event_id==request.event_id),None)
            if not selected_event or selected_event.revision!=request.event_revision:
                return unavailable('This moment has changed or is still unfolding. Reopen the play when it finishes.','这一刻已更新或尚未结束，请在结束后重新打开。')
            at=(selected_event.available_period,selected_event.available_ms)
            selected=select_events(events,at)
        scope={'match_id':plan.match_id,'cutoff':{'period':at[0],'elapsed_ms':at[1]},'as_of':self.scope(request)[0],'window':plan.analysis}
        digest=self.store.evidence_digest(plan.match_id,at)
        def fact(tool,subject_id,metric,label,value,unit='count',*,subject_kind='club',extra_scope=None,extra_evidence=None):
            registry=self.store.players if subject_kind=='player' else self.store.clubs
            evidence={'match_id':plan.match_id,'event_digest':digest,'reducer_version':tool['rule_version'],
                      'source_kind':tool['source_kind'],'events':tool.get('evidence',[]),
                      'observation_coverage':tool.get('coverage',{}),**(extra_evidence or {})}
            return {'subject_id':subject_id,'subject_kind':subject_kind,'subject_name':registry[subject_id].name,
                    'metric':metric,'label':label,'value':value,'unit':unit,'scope':{**scope,**(extra_scope or {})},
                    'coverage':None,'evidence':evidence,'href':f'#football/{subject_kind}/{subject_id}'}
        def clock(period,ms):
            seconds=(ms+(fixture.period_lengths_ms[0] if period==2 else 0))//1000
            return f'{seconds//60}:{seconds%60:02d}'
        scope['time_label']=clock(at[0],at[1])
        if plan.analysis=='buildup':
            goal_id=request.event_id or next((e.event_id for e in reversed(selected) if e.goal_for),None)
            if not goal_id:return unavailable('Choose a goal that has finished playing to explore its buildup.','请选择已结束的进球片段来查看进球过程。')
            result=goal_buildup(fixture,events,event_id=goal_id,cutoff=at,expected_revision=request.event_revision)
            if result['status']!='available':
                return unavailable('Choose a completed goal scored by the attacking team to explore its buildup.','请选择进攻方已完成的进球来查看进球过程。')
            goal=result['goal'];metrics=result['metrics'];name=self.store.players[goal['player_id']].name
            contributor_phrase=scoring_contributor(request.question)
            explicit_contributors=self.exact_player_subject(contributor_phrase) if contributor_phrase else []
            if contributor_phrase and not explicit_contributors:
                return unavailable('I could not identify the contributing player. Name one player from this match.','无法识别所指的参与球员，请指定本场的一位球员。')
            for phrase in scoring_possessors(request.question) if contributor_phrase else []:
                if re.search(r'\b(?:goal|finish|move|play|sequence|attack)\s*$',phrase,re.I):continue
                if re.search(r'\b(?:player|team|club)\b',phrase,re.I) or self.names(phrase,self.store.clubs,'club_id'):continue
                scorers=self.exact_player_subject(phrase)
                if scorers != [goal['player_id']]:
                    return unavailable('That player did not score the selected goal, or the name is unresolved. Open the goal you mean.','该球员并非所选进球的射手，或姓名无法识别，请打开您想了解的进球。')
            named=self.names(request.question,self.store.players,'player_id')
            named_clubs=self.names(request.question,self.store.clubs,'club_id')
            if named_clubs and goal['club_id'] not in named_clubs:
                return unavailable('The selected goal was scored by a different club. Open the goal you mean.','所选进球属于另一俱乐部，请打开您想了解的进球。')
            if named and not set(named)<={c['player_id'] for c in result['contributions']}:
                return unavailable('The selected goal does not include that player in its recorded buildup. Open the goal you mean.','所选进球的进攻记录没有该球员，请打开您想了解的进球。')
            for pid in named:
                if re.search(re.escape(self.store.players[pid].name)+r"[’']s "+SCORING_MOMENT+r'\b',request.question,re.I) and pid!=goal['player_id']:
                    return unavailable('That player did not score the selected goal. Open their goal to explore it.','该球员并非所选进球的射手，请打开其进球片段。')

            definitions=[('completed_passes','Completed passes','成功传球','count'),('carry_count','Carry segments','带球片段','count'),
                         ('participant_count','Players involved','参与球员','count'),('observed_duration_seconds','Observed buildup','已记录进攻时长','seconds'),
                         ('regain_to_shot_seconds','Regain to shot','夺回球权至射门','seconds'),('net_progression_m','Net progress towards goal','向球门净推进','metres')]
            facts=[fact(result,goal['club_id'],key,t(en,cn),metrics[key],unit) for key,en,cn,unit in definitions]
            duration=metrics['observed_duration_seconds'];passes=metrics['completed_passes'];participants=metrics['participant_count']
            display_duration=round(duration,1) if duration>=.1 else duration
            display_regain=round(metrics['regain_to_shot_seconds'],1) if metrics['regain_to_shot_seconds'] is not None else None
            text=[t(f'{name} finished a sequence involving {participants} '+('player' if participants==1 else 'players')+f' and {passes} completed '+('pass' if passes==1 else 'passes')+f' over about {display_duration:g} seconds.',
                    f'{name}完成进球；这段进攻有{participants}名球员参与、{passes}次成功传球，持续约{display_duration:g}秒。')]
            goal_event=next(e for e in selected if e.event_id==goal_id)
            if goal_event.situation=='free_kick':
                text=[t(f'{name} scored from a free kick.' if not passes else f'{name} scored from a free-kick attack.',f'{name}在任意球进攻中取得进球。')]
            elif goal_event.penalty or goal_event.situation=='penalty':
                text=[t(f'{name} converted a penalty.',f'{name}罚入点球。')]
            elif goal_event.situation=='corner':
                text=[t(f'{name} scored from a corner-kick attack.',f'{name}在角球进攻中取得进球。')]
            if metrics['regain_to_shot_seconds'] is not None:
                text.insert(0,t(f'The team went from regaining possession to {name}’s scoring shot in about {display_regain:g} seconds.',
                              f'球队从夺回球权到完成进球射门用了约{display_regain:g}秒。'))
            elif not result['coverage']['complete_possession'] and goal_event.situation not in ('free_kick','penalty','corner'):
                text[-1]=t(f'The recorded buildup ends with {name} scoring: {passes} completed '+('pass' if passes==1 else 'passes')+f' involving {participants} '+('player' if participants==1 else 'players')+f' across about {display_duration:g} seconds.',
                          f'已记录的进攻以{name}进球结束：最后{duration:g}秒内有{participants}名球员参与、{passes}次成功传球。')
            # Describe the observed football action before enumerating absent
            # actions. A carry-only suffix is still an informative finish.
            if not passes and goal_event.situation == 'open_play':
                carried = next((c for c in result['contributions'] if c['player_id']==goal['player_id'] and c['carries']),None)
                if carried:
                    text[-1]=t(f'{name} carried the ball and finished with a goal. The recorded sequence covers about {display_duration:g} seconds.',
                                  f'{name}带球后射门得分；已记录的片段持续约{display_duration:g}秒。')
                elif not metrics['carry_count']:
                    text[-1]=t(f'The record shows {name}’s scoring shot, without an earlier buildup to describe.',
                                  f'记录展示了{name}的进球射门，没有此前的进攻过程可供分析。')
            if metrics['regain_to_shot_seconds'] is None and asks_regain_interval(request.question):
                text.insert(0,t('The record starts at a restart, not an observed regain of possession; a regain-to-shot interval is unavailable.' if result['coverage']['start_known'] else
                    'The record does not establish when the team first gained control. This timeline covers the observed finish of the move, not a confirmed full possession, so the regain-to-shot time is unavailable.',
                    '记录从重新开球开始，并未记录此前夺回球权的时刻，因此不能计算夺回球权至射门的时长。' if result['coverage']['start_known'] else
                    '记录无法确定球队最初取得球权的时间；时间线仅展示已记录的进攻末段，不能视为完整控球过程，也不能计算夺回球权至射门的时长。'))
            # Prefer the fan's player when they contributed, without changing sporting credit.
            favorites=set(request.preferences.favorite_player_ids)
            contributors=sorted(result['contributions'],key=lambda c:(c['player_id'] not in explicit_contributors,c['player_id'] not in favorites,
                -(c['completed_passes']+c['receptions']+c['carries']+c['recoveries']),c['player_id']))
            contributor=next((c for c in contributors if c['player_id'] in explicit_contributors or not explicit_contributors and c['player_id']!=goal['player_id']),None)
            if contributor:
                pid=contributor['player_id'];pname=self.store.players[pid].name
                details=[]
                measures=[('completed_passes','completed passes','次成功传球'),('receptions','received passes','次接球'),('carries','carry segments','段带球'),('recoveries','regains','次夺回球权')]
                if explicit_contributors:measures.append(('shots','shots','次射门'))
                for key,en,cn in measures:
                    if contributor[key]:
                        singular={'completed passes':'completed pass','received passes':'received pass','carry segments':'carry segment','regains':'regain','shots':'shot'}
                        details.append(t(f'{contributor[key]} '+(singular[en] if contributor[key]==1 else en),f'{contributor[key]}{cn}'))
                        facts.append(fact(result,pid,'buildup_'+key,t(en.title(),cn),contributor[key],subject_kind='player'))
                if details:text.insert(0 if explicit_contributors and not asks_regain_interval(request.question) else 1,
                    t(f'{pname} contributed '+', '.join(details)+' in the buildup.',f'{pname}在进攻过程中贡献了'+ '、'.join(details)+'。'))
            if goal_event.situation in ('free_kick','penalty','corner'):
                visible_goals=[e for e in selected if e.goal_for]
                if visible_goals and visible_goals[-1].event_id==goal_id:
                    from counterpress.fan.contracts import PlaybackCutoff
                    scoped=request.model_copy(update={'playback':PlaybackCutoff(period=at[0],elapsed_ms=at[1])})
                    impact=self.match_answer(plan,scoped)
                    facts.extend(impact['facts'])
                    text.extend(impact['text'][1:])
            verbs={'pass':t('Completed pass','成功传球'),'carry':t('Carried the ball','带球'),'recovery':t('Regained possession','夺回球权'),
                   'shot':t('Goal','进球'),'pressure':t('Applied pressure','施压')}
            timeline=[]
            for e in result['timeline']:
                recipient=e.get('recipient_id')
                verb=verbs.get(e['kind'],t('Recorded action','场上动作'))
                if e['kind']=='pass' and e['outcome'] not in ('complete','completed'):verb=t('Pass attempt','传球尝试')
                if e['kind']=='shot' and e['outcome']!='goal':verb=t('Shot','射门')
                timeline.append({'event_id':e['event_id'],'revision':e['revision'],'label':self.store.players[e['player_id']].name,
                    'detail':verb+(t(' to ','给 ')+self.store.players[recipient].name if recipient and e['kind']=='pass' else ''),
                    'period':e['period'],'elapsed_ms':e['elapsed_ms'],'time_label':clock(e['period'],e['elapsed_ms']),'kind':e['kind']})
            if plan.investigate_player_id:
                focus=next((c for c in result['contributions'] if c['player_id']==plan.investigate_player_id),None)
                allowed={c['player_id'] for c in self.investigation_candidates(plan,request)}
                if focus is None or focus['player_id'] not in allowed:raise ValueError('Follow-up participant is no longer eligible')
                detail=involvement(fixture,events,player_id=focus['player_id'],cutoff=at)
                if detail['status']=='available':
                    pname=self.store.players[focus['player_id']].name
                    # Choose a recorded action present in both this sequence and
                    # the match. A reception is not an authored sporting assist.
                    key=next((k for k in ('completed_passes','receptions','carries') if focus[k] and detail['metrics'][k] is not None and (k!='completed_passes' or detail['coverage']['pass_outcomes_complete'])),None)
                    if key and detail['metrics'][key]>=focus[key]:
                        count,total=focus[key],detail['metrics'][key]
                        label={'completed_passes':('completed passes','成功传球'),'receptions':('received passes','接球'),'carries':('carry segments','带球片段')}[key]
                        if not any(f['subject_id']==focus['player_id'] and f['metric']=='buildup_'+key for f in facts):
                            facts.append(fact(result,focus['player_id'],'buildup_'+key,t(label[0].title(),label[1]),count,subject_kind='player'))
                        facts.append(fact(detail,focus['player_id'],'match_'+key,t('Match '+label[0], '本场'+label[1]),total,subject_kind='player'))
                        share=round(count/total*100,1) if total else 0
                        text.insert(1,t(f'This buildup accounts for {count} of {pname}’s {total} {label[0]} by this goal ({share:g}%).',
                            f'这段进攻包含{pname}本场截至目前{total}次{label[1]}中的{count}次（{share:g}%），体现了其在这次进攻与整场比赛中的参与。'))
            if sequence_pass_count_intent(request.question) is True:
                position=1 if asks_regain_interval(request.question) and metrics['regain_to_shot_seconds'] is None else 0
                text.insert(position,t(f'The recorded buildup contains {passes} completed '+('pass.' if passes==1 else 'passes.'),
                                       f'已记录的进攻过程包含{passes}次成功传球。'))
            actions=[{'label':t('View ','查看 ')+name,'href':f'#football/player/{goal["player_id"]}'}]
            for clip in json.loads((self.store.root/'highlights.json').read_text()):
                if (clip['match_id']==plan.match_id and clip['goal_event_id']==goal_id and self.store.evidence_digest(plan.match_id)==row['digest']
                        and (clip['end']['period'],clip['end']['elapsed_ms'])<=at):
                    actions.insert(0,{'label':t('Watch the buildup','观看进攻过程'),'href':f'#football/player/{clip["scorer_id"]}','highlight':clip})
            return {'status':'answered','title':t('How the goal came together','进球是如何形成的'),'text':text,'facts':facts,'actions':actions,
                    'visual':{'kind':'timeline','label':t('The buildup','进球过程'),'items':timeline}}
        if plan.analysis=='player_performance':
            pid=plan.player_ids[0];player=self.store.players[pid]
            result=involvement(fixture,events,player_id=pid,cutoff=at)
            if result['status']!='available':return unavailable('This player has no appearance at the selected point in this match.','该球员在所选比赛时间尚无出场记录。')
            named_clubs=self.names(request.question,self.store.clubs,'club_id')
            if named_clubs and result['club_id'] not in named_clubs:
                return unavailable('This player represents a different club in this match. Please check the player or club.','该球员在本场代表另一俱乐部，请核实球员或俱乐部。')
            metrics=result['metrics'];minutes=metrics['minutes']
            priority={'GK':['passes','completed_passes'],'DF':['passes','recoveries'],'MF':['passes','receptions'],'FW':['shots','receptions']}[player.role]
            chosen=[m for m in priority if metrics[m] is not None]
            if len(chosen)<2:chosen+= [m for m in ('passes','shots') if m not in chosen][:2-len(chosen)]
            labels={'passes':('Pass attempts','传球尝试'),'completed_passes':('Completed passes','成功传球'),'recoveries':('Regains','夺回球权'),
                    'shots':('Shots','射门'),'receptions':('Received passes','接球')}
            if not result['coverage']['pass_outcomes_complete']:labels['completed_passes']=('Recorded completed passes','已记录成功传球')
            facts=[fact(result,pid,m,t(*labels[m]),metrics[m],subject_kind='player') for m in chosen]
            goals=sum(e.player_id==pid and e.kind=='shot' and e.outcome=='goal' and e.goal_for==result['club_id'] for e in selected)
            if goals:facts.insert(0,fact(result,pid,'goals',t('Goals','进球'),goals,subject_kind='player'))
            facts.append(fact(result,pid,'observed_minutes',t('Minutes played','出场分钟'),round(minutes,1),'minutes',subject_kind='player'))
            text=[t(f'{player.name} has '+', '.join(f'{metrics[m]} {labels[m][0].lower()}' for m in chosen)+f' in {minutes:.1f} minutes so far.',
                    f'{player.name}目前出场{minutes:.1f}分钟，'+ '、'.join(f'{metrics[m]}次{labels[m][1]}' for m in chosen)+'。')]
            if goals:
                text.insert(0,t(f'{player.name} has scored {goals} '+('goal' if goals==1 else 'goals')+' so far.',f'{player.name}截至目前已打入{goals}球。'))
            if player.role=='GK':
                from counterpress.personalization.contracts import MatchRecord
                from counterpress.personalization.metrics import reduce_record
                appearance=next(a for a in fixture.appearances if a.player_id==pid)
                def during_appearance(e):
                    elapsed=e.elapsed_ms+(fixture.period_lengths_ms[0] if e.period==2 else 0)
                    return appearance.start_ms<=elapsed<appearance.end_ms
                faced=[e for e in selected if e.kind=='shot' and e.club_id!=result['club_id'] and during_appearance(e)]
                keeper_events=[e for e in selected if during_appearance(e) and
                    (e in faced or e.kind=='shot' and e.goalkeeper_id==pid or e.goal_for and e.goal_for!=result['club_id'])]
                # Use the existing shared accounting, including own goals and
                # substitutions; conceded goals are not attributed as mistakes.
                summary=reduce_record(MatchRecord(fixture=fixture,events=tuple(selected)),at)
                keeper_stats=summary['players'][pid]
                save_complete=fixture.source_kind!='adapted_archive' and all(
                    e.outcome in ('goal','own_goal','saved','blocked','off_target','woodwork')
                    and (e.outcome!='saved' or e.goalkeeper_id is not None) for e in faced)
                keeper_tool={**result,'rule_version':summary['rule_version'],
                    'coverage':{'saves_complete':save_complete,'basis':'recorded_shot_outcomes','tracking':'unavailable'},
                    'evidence':[{k:getattr(e,k) for k in ('match_id','event_id','revision','period','elapsed_ms',
                        'available_period','available_ms','occurrence_order','kind','outcome','club_id','player_id',
                        'goalkeeper_id','goal_for','source_reference')} for e in keeper_events]}
                saves=keeper_stats['saves'] if save_complete else None
                conceded=keeper_stats['goals_conceded']
                facts.extend([fact(keeper_tool,pid,'saves',t('Saves','扑救'),saves,subject_kind='player'),
                    fact(keeper_tool,pid,'goals_conceded',t('Team goals conceded while on pitch','在场期间球队失球'),conceded,subject_kind='player')])
                keeper_line=t(f'{player.name} has made {saves} '+('save' if saves==1 else 'saves')+f'; the team has conceded {conceded} '+('goal' if conceded==1 else 'goals')+' during their time on the pitch.',
                    f'{player.name}已完成{saves}次扑救，在场期间球队失{conceded}球。') if save_complete else t(
                    f'{player.name}’s team has conceded {conceded} '+('goal' if conceded==1 else 'goals')+' during their time on the pitch; this match’s records do not identify saves reliably.',
                    f'{player.name}在场期间球队失{conceded}球；本场记录不足以可靠统计扑救次数。')
                text.insert(0,keeper_line)
            # Same reducer and source family for both sides; never mix archive
            # sparse observations with calibrated full-history event rates.
            historical=[];refs=[]
            for historic_row in self.store.rows(club=player.club_id,before=fixture.kickoff):
                historic_at=self.career.historical_cutoff(historic_row,fixture.kickoff)
                if historic_at is False:continue
                hf=Fixture.model_validate_json(historic_row['fixture'])
                if hf.source_kind!=fixture.source_kind or hf.minutes_basis!=fixture.minutes_basis:continue
                previous=involvement(hf,self.store.events(hf.match_id),player_id=pid,cutoff=historic_at)
                if previous['status']!='available':continue
                historical.append(previous)
                refs.append({'match_id':hf.match_id,'event_digest':self.store.evidence_digest(hf.match_id,historic_at)})
                if len(historical)==5:break
            historical_minutes=sum(h['metrics']['minutes'] for h in historical)
            groups=[]
            for metric in chosen:
                label=t(*labels[metric]);valid=len(historical)>=3 and historical_minutes>=180 and minutes>=10 and all(h['metrics'][metric] is not None for h in historical)
                if metric=='completed_passes':valid=valid and result['coverage']['pass_outcomes_complete'] and all(h['coverage']['pass_outcomes_complete'] for h in historical)
                current_rate=round(metrics[metric]*90/minutes,2) if minutes>=10 else None
                previous_rate=round(sum(h['metrics'][metric] for h in historical)*90/historical_minutes,2) if valid else None
                if valid:
                    base_evidence={'events':[],'matches':refs,'baseline_id':fingerprint({'refs':refs,'metric':metric,'minutes':historical_minutes}),
                                   'observation_coverage':{'matches':len(historical),'minutes':historical_minutes,'source_kind':fixture.source_kind}}
                    facts.append(fact(result,pid,metric+'_per90',label,current_rate,'per90',subject_kind='player'))
                    facts.append(fact(result,pid,metric+'_per90',label,previous_rate,'per90',subject_kind='player',
                        extra_scope={'window':'completed_appearances_before_kickoff','as_of':fixture.kickoff,'matches':len(historical),'cutoff':None,'time_label':None},extra_evidence=base_evidence))
                    direction=t('higher than','高于') if current_rate>previous_rate else t('lower than','低于') if current_rate<previous_rate else t('level with','与其相同')
                    text.append(t(f'At this point, {player.name}’s {labels[metric][0].lower()} rate is {current_rate:g} per 90 minutes, {direction} {previous_rate:g} across the previous {len(historical)} completed appearances.',
                        f'截至目前，{player.name}的{labels[metric][1]}为每90分钟{current_rate:g}次；之前{len(historical)}次完整出场为{previous_rate:g}次。'))
                    groups.append({'kind':'bars','label':label,'items':[{'label':t('This match so far','本场截至目前'),'value':current_rate,'unit':'per90'},
                        {'label':t(f'Previous {len(historical)} appearances',f'之前{len(historical)}次出场'),'value':previous_rate,'unit':'per90'}]})
            if not groups:
                text.append(t('There is not yet enough comparable playing time for a historical rate comparison.','尚无足够可比的出场时间来对比历史表现。'))
            return {'status':'answered','title':t(f'{player.name}, so far',f'{player.name}的本场表现'),'text':text,'facts':facts,
                    'actions':[{'label':t('Open player profile','查看球员资料'),'href':f'#football/player/{pid}'}],
                    'visual':{'kind':'groups','label':t('A like-for-like comparison','同口径对比'),'groups':groups} if groups else None}
        if plan.analysis=='match_changes':
            if observation_question(request):
                return observation_answer(self,request)
            window_ms=600000;end_ms=min(at[1],fixture.period_lengths_ms[at[0]-1])//window_ms*window_ms
            if end_ms<2*window_ms:return unavailable('Let two ten-minute stretches finish in this half so I can compare them fairly.','请等待本半场完成两个十分钟时段，以进行同口径对比。')
            start_ms=end_ms-2*window_ms;split_ms=end_ms-window_ms
            club_ids=[plan.club_id] if plan.club_id else [fixture.home_id,fixture.away_id]
            favorite=request.preferences.primary_club_id
            club_ids=sorted(club_ids,key=lambda cid:cid!=favorite)
            facts=[];text=[];groups=[]
            for cid in club_ids:
                result=compare_windows(fixture,events,club_id=cid,period=at[0],start_ms=start_ms,split_ms=split_ms,end_ms=end_ms,cutoff=at)
                if result['status']!='available':continue
                name=self.store.clubs[cid].name
                before_label=f'{clock(at[0],start_ms)}–{clock(at[0],split_ms)}';after_label=f'{clock(at[0],split_ms)}–{clock(at[0],end_ms)}'
                pass_label='Completed passes' if result['coverage']['pass_outcomes_complete'] else 'Recorded completed passes'
                pass_cn='成功传球' if result['coverage']['pass_outcomes_complete'] else '已记录成功传球'
                for metric,label,cn in [('shots','Shots','射门'),('completed_passes',pass_label,pass_cn)]:
                    previous=result['before'][metric];current=result['after'][metric]
                    for index,value in enumerate((previous,current)):
                        facts.append(fact(result,cid,metric,t(label,cn),value,extra_scope={'observation_window':result['windows'][index],'window_label':before_label if index==0 else after_label}))
                    groups.append({'kind':'bars','label':name+' · '+t(label,cn),'items':[{'label':before_label,'value':previous,'unit':'count'}, {'label':after_label,'value':current,'unit':'count'}]})
                a,b=result['before'],result['after']
                text.append(t(f'{name}: {b["shots"]} '+('shot' if b['shots']==1 else 'shots')+f' and {b["completed_passes"]} {pass_label.lower()} in {after_label}, compared with {a["shots"]} '+('shot' if a['shots']==1 else 'shots')+f' and {a["completed_passes"]} {pass_label.lower()} in {before_label}.',
                    f'{name}在{after_label}有{b["shots"]}次射门和{b["completed_passes"]}次{pass_cn}；此前{before_label}为{a["shots"]}次射门和{a["completed_passes"]}次{pass_cn}。'))
                if a['shots']==b['shots'] and a['completed_passes']==b['completed_passes']:
                    text.append(t(f'{name} is level across these two measures in the two ten-minute windows.',f'{name}在两个十分钟时段的这两项指标相同。'))
            if not facts:return unavailable('There are too few recorded actions in those stretches to make a useful comparison.','这些时段的场上动作记录太少，无法进行有效对比。')
            return {'status':'answered','title':t('What has changed','比赛发生了什么变化'),'text':text,'facts':facts,'actions':[],
                    'visual':{'kind':'groups','label':t('Two completed ten-minute stretches','两个已完成的十分钟时段'),'groups':groups}}
        raise ValueError('Unknown analysis')

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
