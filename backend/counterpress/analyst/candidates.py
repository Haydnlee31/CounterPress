"""Typed, localized football interpretations; models may select, never rewrite.

Candidates require compound source evidence. Empty/weak spells abstain. No
tracking, elapsed possession, causal pressure or uncalibrated xG prose is inferred.
"""
from hashlib import sha256
import json
from .metrics import COMPLETE,CONTROLLED,turns

CANDIDATE_VERSION='analyst-candidates-v2'


def event_id(e):return f'{e.event_id}:r{e.revision}'


def in_box(e):return bool(e.start and e.start.x>=88.5 and 13.84<=e.start.y<=54.16)


def linked_transitions(events):
    """Every intermediary action must preserve an explicit actor/recipient chain."""
    output=[]
    for lost,recovery in turns(events):
        holder=recovery.player_id;chain=[lost,recovery]
        for e in events[events.index(recovery)+1:]:
            if e.period!=recovery.period or e.elapsed_ms-recovery.elapsed_ms>15000 or e.restart or e.club_id!=recovery.club_id or e.player_id!=holder:break
            chain.append(e)
            if len(chain)>8:break
            if e.kind=='shot':
                if e.outcome in {'goal','off_target','blocked','saved','on_target','woodwork'}:output.append(chain)
                break
            if e.kind=='pass' and e.outcome in COMPLETE and e.recipient_id:holder=e.recipient_id
            elif e.kind=='carry' and e.outcome in CONTROLLED:pass
            else:break
    return output


def build_candidates(*,fixture,events,request,rows,players,clubs,score,windows):
    """Append derived scalar facts to rows, return at most two readings per role."""
    if request.cutoff.elapsed_ms<300000:return []
    p,end=request.cutoff.period,request.cutoff.elapsed_ms
    current=[e for e in events if e.period==p and max(0,end-300000)<e.elapsed_ms<=end]
    previous=[e for e in events if e.period==p and max(0,end-600000)<e.elapsed_ms<=max(0,end-300000)]
    names={c['club_id']:c['name']for c in clubs};people={x['player_id']:x['name']for x in players}
    index={r['id']:r for r in rows};zh=request.language=='zh-Hans';analyst=request.depth=='analyst';ranked=[]
    def loc(en,cn):return cn if zh else en
    def mid(club,key,w='current'):return f'{w}:{club}:{key}'
    def value(club,key,w='current'):return index.get(mid(club,key,w),{}).get('value')
    def fact(club,key,label,v,role='chance',unit='count',window='current',subject=None):
        ident=mid(club,key,window)
        if ident not in index:
            row={'id':ident,'key':key,'window':window,'club_id':club,'label':label,'unit':unit,'value':v,'basis':'recorded_events','status':'available','role':role,'method':'compound_event_facts'}
            if key not in {'shots_inside_box','shots_blocked'}:row['presentation']='evidence_only'
            if subject:row['player_id']=subject
            rows.append(row);index[ident]=row
        return ident
    def add(family,role,proof,metrics,headline,explanation,alternative,watch,priority=.7):
        refs=list(dict.fromkeys(event_id(e)for e in proof))
        refs=refs[-8:];metrics=list(dict.fromkeys(metrics))
        if not refs or not metrics or len(metrics)>8 or any(m not in index or index[m]['value'] is None or index[m]['status']=='unavailable'for m in metrics):return
        reading={'role':role,'headline':headline,'explanation':explanation,'alternative':alternative,'watch_next':watch,'evidence_ids':refs,'metric_ids':metrics,'confidence':'medium'}
        if any(len(reading[k])>limit for k,limit in [('headline',100),('explanation',550),('alternative',240),('watch_next',240)]):raise ValueError('Candidate prose exceeded its contract')
        ident='cp2-'+family+'-'+sha256(json.dumps(reading,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()[:20]
        ranked.append((priority,{'id':ident,'role':role,'reading':reading}))
    for club in (fixture.home_id,fixture.away_id):
        other=fixture.away_id if club==fixture.home_id else fixture.home_id
        name,opponent=names[club],names[other]
        own=[e for e in current if e.club_id==club]
        shots=[e for e in own if e.kind=='shot' and e.outcome!='own_goal']
        before=[e for e in previous if e.club_id==club and e.kind=='shot' and e.outcome!='own_goal']
        box=[e for e in shots if in_box(e)];oldbox=[e for e in before if in_box(e)]
        box_id=fact(club,'shots_inside_box','Shots from inside the box',len(box))
        oldbox_id=fact(club,'shots_inside_box','Shots from inside the box',len(oldbox),window='previous')
        blocked=[e for e in shots if e.outcome=='blocked']
        blocked_id=fact(club,'shots_blocked','Blocked shots',len(blocked))
        if end>=600000 and len(shots)>=3 and len(shots)>=len(before)+2 and len(box)>=2:
            alternative=loc('All those shots were blocked, so closer positions have not yet produced an unblocked attempt.','这些射门都被封堵，靠近球门还没有换来未被封堵的射门。') if len(blocked)==len(shots) else loc('The window records attempts, not a guarantee that this threat will continue.','这段时间记录了射门机会，但不能保证这样的威胁会持续。')
            explanation=loc(f'{name} took {len(shots)} shots in the last 5 minutes, compared with {len(before)} before; {len(box)} came from inside the box. The higher shot count includes attempts from inside the box.',f'{name}过去5分钟射门{len(shots)}次，上个窗口为{len(before)}次，其中{len(box)}次在禁区内。射门总数增加，其中包括禁区内的起脚机会。') if analyst else loc(f'{name} are shooting more often, with attempts coming from inside the box. The higher volume includes attempts inside the penalty area.',f'{name}射门变多，也能够在禁区内起脚。射门数量增加，其中也包括禁区内的尝试。')
            if score[club]<score[other]:
                explanation+=loc(f' They still trail {score[club]}–{score[other]}.',f' 当前比分仍以{score[club]}比{score[other]}落后。')
            add('box-growth','chance',shots+before,[mid(club,'shots'),mid(club,'shots','previous'),box_id,blocked_id,mid(club,'goals','prefix'),mid(other,'goals','prefix')],(loc(f'{name} reach the box, but their shots are blocked.',f'{name}进入禁区，但射门都被封堵。')if len(blocked)==len(shots)else loc(f'{name} are creating more shooting opportunities.',f'{name}制造了更多射门机会。')),explanation,alternative,loc('Watch whether the next box entry produces an unblocked shot.','接下来留意进入禁区后，能否完成未被封堵的射门。'),.88)
        elif end>=600000 and shots and len(oldbox)>=2 and not box and all(e.start for e in shots) and len(shots)<=len(before):
            explanation=loc(f'{name} have {len(shots)} {"shot" if len(shots)==1 else "shots"} in this 5-minute window, all outside the box; the previous window included {len(oldbox)} inside it. Recent attempts have come from outside the penalty area.',f'{name}过去5分钟的{len(shots)}次射门都来自禁区外，上个窗口则有{len(oldbox)}次禁区内射门。最近的尝试来自禁区外。') if analyst else loc(f'{name} have moved from attempts inside the box to shots outside it. The next attack needs a closer look at where the shot is taken.',f'{name}此前能在禁区内射门，现在的尝试来自禁区外。接下来值得关注起脚位置能否再次靠近球门。')
            # No coach instruction: observational rather than "needs to change".
            explanation=explanation.replace('The next attack needs a closer look at where the shot is taken.','The location of the next attempt is worth watching.')
            add('farther-out','chance',shots+oldbox,[mid(club,'shots'),mid(club,'shots','previous'),box_id,oldbox_id],loc(f'{name}’s recent shots are outside the box.',f'{name}最近的射门来自禁区外。'),explanation,loc('This comparison covers a short spell and only the shots that were recorded.','这个比较只涉及短时间内已经发生的射门。'),loc('Watch whether the next shooting opportunity comes from inside the box.','接下来留意能否重新获得禁区内的射门机会。'),.73)
        own_actions=value(club,'on_ball_actions')or 0;other_actions=value(other,'on_ball_actions')or 0
        entries=value(club,'final_third_entries')
        if own_actions>=20 and own_actions>other_actions*1.8 and not shots and entries is not None and entries<=1:
            other_shots=value(other,'shots')or 0
            explanation=loc(f'{name} recorded {own_actions} on-ball actions against {opponent}’s {other_actions} in the last 5 minutes, but no shot and only {entries} completed {"pass" if entries==1 else "passes"} into the final third. More activity has not yet become a shooting chance.',f'{name}过去5分钟有{own_actions}次有球动作，{opponent}为{other_actions}次，但还没有射门，成功传入进攻三区只有{entries}次。更多有球参与还未转化为射门机会。') if analyst else loc(f'{name} have more recorded activity on the ball in the last 5 minutes, but no shot in that spell. Their completed passes have rarely crossed into the final third.',f'{name}过去5分钟的有球参与更多，但这段时间还没有射门，成功传入进攻三区的次数也很少。')
            alternative=loc(f'{opponent} have still taken {other_shots} {"shot" if other_shots==1 else "shots"} with fewer on-ball actions in this window.',f'{opponent}虽然有球动作更少，仍然完成了{other_shots}次射门。') if other_shots else loc('Neither club has taken a shot in this window.','这个窗口里双方都还没有射门。')
            add('activity-no-shot','control',own[-6:],[mid(club,'on_ball_actions'),mid(other,'on_ball_actions'),mid(club,'shots'),mid(club,'final_third_entries'),mid(other,'shots')],loc(f'{name}’s recent activity has not produced a shot.',f'{name}最近有球参与更多，却还没有射门。'),explanation,alternative,loc('Watch whether the next forward entry ends with a shot.','接下来留意向前推进后，能否真正完成射门。'),.86)
        a=value(club,'pass_accuracy');b=value(club,'pass_accuracy','previous');old_entries=value(club,'final_third_entries','previous')
        ac=index[mid(club,'pass_accuracy')].get('coverage',{});bc=index[mid(club,'pass_accuracy','previous')].get('coverage',{})
        if end>=600000 and a is not None and b is not None and a<=b-15 and entries is not None and old_entries is not None and entries<old_entries and ac.get('numerator',0)>=10 and bc.get('numerator',0)>=10 and ac.get('numerator')==ac.get('denominator') and bc.get('numerator')==bc.get('denominator'):
            explanation=loc(f'{name}’s pass completion fell from {b:.1f}% to {a:.1f}% across consecutive 5-minute windows, while completed final-third entries fell from {old_entries} to {entries}. Less reliable passing is coinciding with fewer forward entries.',f'{name}相邻5分钟窗口的传球成功率从{b:.1f}%降至{a:.1f}%，成功传入进攻三区从{old_entries}次降至{entries}次。传球成功率降低的同时，向前传入也减少了。')if analyst else loc(f'{name} are completing a smaller share of passes and making fewer entries into the final third. The recent spell is producing less reliable forward progression.',f'{name}的传球成功比例降低，成功传入进攻三区也减少了。最近这段进攻向前发展的稳定性有所下降。')
            add('passing-progress','control',[e for e in own if e.kind=='pass'][-6:],[mid(club,'pass_accuracy'),mid(club,'pass_accuracy','previous'),mid(club,'final_third_entries'),mid(club,'final_third_entries','previous')],loc(f'{name}’s passing is yielding fewer forward entries.',f'{name}的传递带来更少向前传入。'),explanation,loc('This comparison shows the two changes together; it does not identify why individual passes failed.','这个比较显示两种变化同时出现，但不能确定每次传球失败的原因。'),loc('Watch whether the next spell restores both pass completion and entries into the final third.','接下来留意传球成功率和传入进攻三区的次数能否同时回升。'),.83)
        # A regain trend is attributed to the recovering club, never its own losses.
        regains=value(club,'verified_turnovers');oldregains=value(club,'verified_turnovers','previous')
        entries_old=value(club,'final_third_entries','previous')
        if end>=600000 and regains is not None and oldregains is not None and regains>=3 and regains>=oldregains+2 and entries is not None and entries_old is not None and entries>=entries_old+2:
            proof=[e for pair in turns(current)if pair[1].club_id==club for e in pair]
            explanation=loc(f'{name} recovered {regains} opponent incomplete passes, up from {oldregains}; their completed final-third pass entries rose from {entries_old} to {entries}. More regained balls coincide with more forward entries.',f'{name}在对手传球失败后夺回球权{regains}次，上个窗口为{oldregains}次；成功传入进攻三区也从{entries_old}次增加到{entries}次。更多夺回球权与更多向前传入同时出现。')
            add('regains-forward','defence',proof,[mid(club,'verified_turnovers'),mid(club,'verified_turnovers','previous'),mid(club,'final_third_entries'),mid(club,'final_third_entries','previous')],loc(f'{name} are winning balls back and moving forward.',f'{name}夺回球权更多，也有更多向前传入。'),explanation,loc('These totals do not link every recovery to a forward entry.','这些总数并不意味着每次夺回球权都直接带来了向前传入。'),loc('Watch whether the next recovery starts an attack into the final third.','接下来留意夺回球权后，能否直接发起进入进攻三区的进攻。'),.7)
    if fixture.source_kind!='adapted_archive':
        for chain in linked_transitions(current):
            lost,recovery,shot=chain[0],chain[1],chain[-1]
            if end-shot.elapsed_ms>90000:continue
            club=recovery.club_id;name=names[club];opponent=names[lost.club_id]
            seconds=(shot.elapsed_ms-recovery.elapsed_ms)/1000
            duration=fact(club,'transition_seconds_'+shot.event_id,'Recovery-to-shot time',seconds,role='defence',unit='seconds')
            outcome=fact(club,'transition_goal_'+shot.event_id,'Goal from the linked transition',int(shot.goal_for==club),role='defence')
            shots_fact=mid(club,'shots')
            is_goal=shot.goal_for==club
            score_refs=[];effect=''
            if is_goal:
                at=lambda e:(e.period,e.elapsed_ms,e.occurrence_order)
                after={c:sum(e.goal_for==c for e in events if at(e)<=at(shot))for c in (fixture.home_id,fixture.away_id)}
                other=fixture.away_id if club==fixture.home_id else fixture.home_id
                for c in (club,other):
                    ref=fact(c,'score_after_'+shot.event_id,'Score immediately after this shot',after[c],role='defence');index[ref]['event_id']=shot.event_id;score_refs.append(ref)
                if after[club]==after[other]:effect=loc(f' It restored parity at {after[club]}–{after[other]}.',f' 这次进球把比分扳成{after[club]}比{after[other]}。')
                elif after[club]-1==after[other]:effect=loc(f' It put {name} ahead {after[club]}–{after[other]}.',f' 这次进球让{name}以{after[club]}比{after[other]}领先。')
                else:effect=loc(f' The score immediately became {after[club]}–{after[other]} from {name}’s perspective.',f' 进球后{name}视角的比分为{after[club]}比{after[other]}。')
            ending=loc('ended in a goal','以进球结束')if is_goal else loc('ended with a shot that did not score','形成射门，但未能进球')
            explanation=loc(f'{opponent}’s incomplete pass was recovered by {people[recovery.player_id]}; the linked move {ending} after {seconds:.3f} seconds. The chance came directly after the opponent lost the ball.',f'{opponent}传球失败后，{people[recovery.player_id]}夺回球权，衔接的进攻在{seconds:.3f}秒后{ending}。这次机会紧接着对手丢球出现。') if analyst else loc(f'{name} turned an opponent’s loose pass into a quick shooting chance. The recovery and linked attack {ending}.',f'{name}利用对手的失误传球迅速制造射门，夺回球权后的衔接进攻{ending}。')
            explanation+=effect
            alternative=loc('The sequence identifies the loose pass, but not whether it was forced by pressure.','这条衔接确认了对手传球失败，但无法说明失误是否由施压造成。') if is_goal else loc('The move reached a shot, but the finish did not turn that opportunity into a goal.','进攻虽然形成射门，但最后的处理没有把机会变成进球。')
            add('regain-shot','defence',chain,[duration,outcome,shots_fact,*score_refs],(loc(f'{name} turned a loose pass into an equalizer.',f'{name}利用失误传球扳平了比分。')if is_goal and after[club]==after[other]else loc(f'{name} turned a loose pass into a chance.',f'{name}利用失误传球制造了机会。')),explanation,alternative,loc('Watch whether the next recovered ball reaches a shot before the attack breaks down.','接下来留意夺回球权后，能否在进攻中断前再次形成射门。'),.95)
            participants={e.player_id for e in chain[1:]}|{e.recipient_id for e in chain[1:] if e.recipient_id}
            focus=request.focus_player_id
            if focus and focus not in participants:continue
            target=focus or shot.player_id;player=people[target]
            if target not in participants:continue
            involvement=fact(club,'transition_involved_'+target+'_'+shot.event_id,'Player involved in linked recovery-to-shot move',1,role='players',subject=target)
            description=loc('recovered the loose ball and finished the move','夺回球权并完成最后的射门')if target==recovery.player_id==shot.player_id else loc('was involved in the linked move that reached the shot','参与了这次最终形成射门的衔接')
            if target==shot.player_id and target!=recovery.player_id:description=loc('finished the move after a teammate’s recovery','在队友夺回球权后完成最后的射门')
            if target==recovery.player_id and target!=shot.player_id:description=loc('started the move with a recovery before a teammate shot','通过夺回球权发起这次进攻，随后队友完成射门')
            outcome_text={'goal':('scored','取得进球'),'off_target':('missed the target','射门偏出'),'blocked':('had the shot blocked','射门被封堵'),'saved':('had the shot saved','射门被扑出'),'woodwork':('hit the woodwork','射门击中门框')}.get(shot.outcome,('did not score','未能进球'))
            finish=loc(*outcome_text)
            explanation=loc(f'{player} {description}. The recovery-to-shot chain took {seconds:.3f} seconds; {people[shot.player_id]} {finish}. This ties the player’s involvement to a concrete shooting chance.',f'{player}{description}。从夺回球权到射门用了{seconds:.3f}秒，{people[shot.player_id]}{finish}。这说明该球员的参与确实衔接到了射门机会。') if analyst else loc(f'{player} {description}, linking involvement to a shooting chance. {people[shot.player_id]} {finish}.',f'{player}{description}，参与最终衔接到了射门机会；{people[shot.player_id]}{finish}。')
            explanation+=effect
            add('player-chain','players',chain,[duration,involvement,outcome,*score_refs],loc(f'{player} connects the recovery to the chance.',f'{player}把夺回球权衔接成了射门机会。'),explanation,loc('The finish and the contribution are different: a shot can follow good involvement without becoming a goal.','参与和终结是两回事：形成了射门，也不代表机会已经变成进球。')if not is_goal else loc('The goal followed an opponent’s loose pass; it does not establish a repeatable pressing pattern.','这次进球来自对手传球失误，还不足以证明这样的抢回进攻会持续出现。'),loc(f'Watch whether {player} is involved again when the next recovered ball becomes an attack.',f'接下来留意再次夺回球权发动进攻时，{player}是否继续参与衔接。'),1. if focus else .9)
    # Focus remains usable even without a verified transition, but no arbitrary
    # player is elevated from a basic cumulative total alone.
    focus=request.focus_player_id
    if focus and not any(c['role']=='players'for _,c in ranked):
        own=[e for e in current if e.player_id==focus];passes=[e for e in own if e.kind=='pass'];shots=[e for e in own if e.kind=='shot' and e.outcome!='own_goal']
        if len(passes)>=5 and shots and all(e.outcome in {'off_target','blocked','saved','woodwork','on_target'}for e in shots):
            club=next(x['club_id']for x in players if x['player_id']==focus);player=people[focus]
            passes_id=fact(club,'focus_passes_'+focus,'Player pass attempts in this window',len(passes),role='players',subject=focus)
            shot_id=fact(club,'focus_shots_'+focus,'Player shots in this window',len(shots),role='players',subject=focus)
            goals_id=fact(club,'focus_goals_'+focus,'Player goals in this window',0,role='players',subject=focus)
            explanation=loc(f'{player} attempted {len(passes)} passes and {len(shots)} {"shot" if len(shots)==1 else "shots"} in the last 5 minutes, without scoring. The player is involved in both circulation and finishing, but that involvement has not yet produced a goal.',f'{player}过去5分钟尝试了{len(passes)}次传球和{len(shots)}次射门，但没有进球。该球员同时参与传递和终结，不过参与还未换来进球。')if analyst else loc(f'{player} is involved in both passing and shooting during this spell, but has not scored. The next finish is a useful test of that involvement.',f'{player}这段时间既参与传球也尝试射门，但还没有进球。接下来的终结是观察这种参与能否转化为成果的机会。')
            add('player-involvement','players',own[-6:]+shots[-2:],[passes_id,shot_id,goals_id],loc(f'{player} is involved, without a finish yet.',f'{player}参与活跃，但还没有进球。'),explanation,loc('Pass and shot counts alone do not prove the passes created those chances.','传球和射门总数本身，并不能证明这些传球直接创造了射门。'),loc(f'Watch whether {player}’s next shooting involvement ends with a goal or another missed opportunity.',f'接下来留意{player}再次参与射门时，是取得进球还是错失机会。'),.85)
    result=[]
    for role in ('chance','defence','control','players'):
        result.extend(c for _,c in sorted((x for x in ranked if x[1]['role']==role),key=lambda x:(-x[0],x[1]['id']))[:2])
    return result
