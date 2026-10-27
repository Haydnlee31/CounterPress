import {FootieLoader} from '../shell/FootieLoader'
import {ImportMoment} from '../highlights/ImportMoment'
import { currentMatchId, matchDate } from './catalog'
import {sequenceEvents} from './replay'
import { PlaySequence } from './PlaySequence'
import { readGIWorkspace, saveGIWorkspace } from './session'
import { readPreferences } from '../matchday/preferences'
import { AppHeader } from '../shell/AppHeader'
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { alias, filters, matchClock, outcomeText, selectEvents } from './data'
import type { Filter, GIMatch, GIEvent } from './data'
import { ClubCrest } from '../matchday/ClubCrest'
import { clubs } from '../matchday/identity'
import '../matchday/matchday.css'
import './gi.css'

function ActionPitch({event,name,shots,onSelect,names,zh}:{event:GIEvent;name:string;shots?:GIEvent[];onSelect:(id:string)=>void;names:Map<string,string>;zh:boolean}) {
  const t=(en:string,cn:string)=>zh?cn:en
  return <svg className="gi-pitch" viewBox="-5 -5 115 78" role={shots?"group":"img"} aria-label={shots?t("Shot locations. Both clubs attack from left to right.","射门位置。双方俱乐部均从左向右进攻。"):zh?`${outcomeText(event)}，${name}。从左向右进攻。`:`${outcomeText(event)} by ${name}. Attacking from left to right.`}>
    <defs><marker id="gi-arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0 0L5 2.5L0 5" fill={event.team_id===4418?"#e7c771":"#a9d5f7"}/></marker></defs>
    <rect x="-5" y="-5" width="115" height="78" rx="3" fill="#153e35"/>
    {[0,1,2,3,4,5,6].map(i=><rect key={i} x={i*15} y="0" width="15" height="68" fill={i%2?'#ffffff08':'#ffffff00'}/>)}
    <g fill="none" stroke="#ffffff65" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
    <text x="52.5" y="-1.5" fill="#c5d5cf" fontSize="2.1" textAnchor="middle">{t('ATTACKING DIRECTION →','进攻方向 →')}</text>
    {shots?.map(shot=>shot.start && <g key={shot.event_id} role="button" tabIndex={0} aria-label={`${matchClock(shot)} ${outcomeText(shot)}, ${names.get(shot.player_id)}`} onClick={()=>onSelect(shot.event_id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(shot.event_id)}}} className="gi-shot-pin">
      <circle cx={shot.start.x} cy={shot.start.y} r={shot.outcome==='goal'?2.3:1.6} fill={shot.team_id===4418?'#e7c771':'#a9d5f7'} stroke={shot.event_id===event.event_id?'#fff':'#163c32'} strokeWidth={shot.event_id===event.event_id?'.8':'.4'}/><title>{names.get(shot.player_id)} · {outcomeText(shot)}</title>
    </g>)}
    {!shots && event.start && <>{event.end && event.kind==='Pass' && <line x1={event.start.x} y1={event.start.y} x2={event.end.x} y2={event.end.y} stroke={event.team_id===4418?"#e7c771":"#a9d5f7"} strokeWidth=".7" strokeDasharray={event.outcome==='incomplete'?'2 1':undefined} markerEnd="url(#gi-arrow)"/>}
      <circle cx={event.start.x} cy={event.start.y} r="3.5" fill={event.team_id===4418?"#e7c771":"#a9d5f7"} stroke="#fff" strokeWidth=".4"/><text x={event.start.x} y={event.start.y+1} textAnchor="middle" fontWeight="700" fontSize="2.5" fill="#153e35">{name.split(' ').map(n=>n[0]).slice(0,2).join('')}</text><title>{name}</title></>}
  </svg>
}

export default function GI() {
  const [requestedMoment]=useState(()=>new URLSearchParams(window.location.search).get('moment'))
  const [view,setView]=useState<'overview'|'moments'|'watch'>(()=>new URLSearchParams(window.location.search).get('view')==='watch'?'watch':requestedMoment?'moments':'overview')
  const [guide,setGuide]=useState(false),[autoAdvance,setAutoAdvance]=useState(false),[sequenceFloor,setSequenceFloor]=useState(0)
  const [matchId]=useState(currentMatchId)
  const [saved]=useState(()=>readGIWorkspace(matchId))
  const [preference]=useState(readPreferences)
  const zh=preference.language==='zh-Hans', t=(en:string,cn:string)=>zh?cn:en
  const theme=clubs[(preference.club_id??'eastbridge') as keyof typeof clubs]
  const [match,setMatch]=useState<GIMatch|null>(null),[error,setError]=useState(false),[attempt,setAttempt]=useState(0)
  const [filter,setFilter]=useState<Filter>(requestedMoment?'all':saved.filter),[team,setTeam]=useState(requestedMoment?'':saved.team),[player,setPlayer]=useState(requestedMoment?'':saved.player),[period,setPeriod]=useState(requestedMoment?'':saved.period)
  const [map,setMap]=useState(requestedMoment?false:saved.map)
  const [selected,setSelected]=useState<string|null>(requestedMoment??saved.selected),[limit,setLimit]=useState(40)
  useEffect(()=>{const controller=new AbortController();setError(false)
    fetch(`/api/gi/matches/${matchId}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(setMatch).catch(e=>{if(e.name!=='AbortError')setError(true)})
    return ()=>controller.abort()
  },[attempt,matchId])
  useEffect(()=>saveGIWorkspace({filter,team,player,period,selected,map},matchId),[filter,team,player,period,selected,map,matchId])
  useEffect(()=>{if(match&&player&&!match.players.some(p=>p.player_id===player&&(!team||String(p.team_id)===team)))setPlayer('')},[match,player,team])
  const names=useMemo(()=>new Map(match?.players.map(p=>[p.player_id,alias(p)])),[match])
  const records=useMemo(()=>selectEvents(match?.events??[],filter,team,player,period),[match,filter,team,player,period])
  const scope=useMemo(()=>selectEvents(match?.events??[],'all',team,player,period),[match,team,player,period])
  useEffect(()=>{setLimit(40);setSequenceFloor(0)},[filter,team,player,period])
  const current=records.find(e=>e.event_id===selected)??records[0]
  const currentIndex=current?match!.events.findIndex(e=>e.event_id===current.event_id):-1
  const context=current?match!.events.filter(e=>e.period===current.period).filter(e=>e.elapsed_ms>current.elapsed_ms-10000&&e.elapsed_ms<=current.elapsed_ms+10000):[]
  const teamName=(id:number)=>id===4418?'Eastbridge':id===9598?'Northport':''
  const clubId=(id:number)=>id===4418?'eastbridge':'northport'
  const goals=match?.events.filter(e=>e.goal_for!==null)??[]
  function advanceSequence(){
    if(!match||!current)return
    const played=sequenceEvents(match.events,current)
    const last=played.at(-1)??current
    const end=match.events.findIndex(e=>e.event_id===last.event_id)
    const next=records.find(e=>match.events.findIndex(x=>x.event_id===e.event_id)>end)
    if(next){setSequenceFloor(end+1);setSelected(next.event_id)}
    else setAutoAdvance(false)
  }
  function inspect(id:string) {setSequenceFloor(0);setSelected(id);document.getElementById('gi-detail')?.focus({preventScroll:true});if(window.matchMedia?.('(max-width: 800px)').matches)document.getElementById('gi-detail')?.scrollIntoView({block:'start'})}
  function jump(id:string) {setSequenceFloor(0);setView('moments');setFilter('all');setTeam('');setPlayer('');setPeriod('');setSelected(id);requestAnimationFrame(()=>{document.getElementById('gi-detail')?.focus({preventScroll:true});document.getElementById('gi-detail')?.scrollIntoView({block:'start'})})}
  const metricCards:[Filter,string,number][]=[['shots',t('Shots','射门'),scope.filter(e=>e.kind==='Shot').length],['off_target',t('Off target','偏出目标'),scope.filter(e=>e.kind==='Shot'&&e.outcome==='off_target').length],['passes',t('Passes','传球'),scope.filter(e=>e.kind==='Pass').length],['incomplete',t('Unsuccessful passes','失败传球'),scope.filter(e=>e.kind==='Pass'&&e.outcome==='incomplete').length]]
  return <div className="matchday gi" data-club={preference.club_id??'eastbridge'} style={{'--fan-accent':theme.accent,'--club-accent':theme.accent} as CSSProperties}>
    <a className="fan-skip" href="#gi-content" onClick={e=>{e.preventDefault();document.getElementById('gi-content')?.focus()}}>{t('Skip to match centre','跳至比赛中心')}</a>
    <AppHeader active="gi" language={preference.language}/>
    <main id="gi-content" tabIndex={-1}>
      {error?<section role="alert"><h1>{t('The match couldn\'t load','比赛数据加载失败')}</h1><button onClick={()=>setAttempt(n=>n+1)}>{t('Try again','重试')}</button></section>:!match?<FootieLoader label={t('Opening match centre…','正在打开比赛中心…')}/>:<>
        <section className="gi-match-header" aria-label={t('Match result','比赛结果')}>
          <div className="gi-match-label"><span className="gi-live-dot"/> {t('FULL TIME','完场')} <span>{t('MATCH CENTRE','比赛中心')}</span></div>
          <h1 aria-label={`Eastbridge ${match.teams[0].score} – ${match.teams[1].score} Northport`}><span className="gi-club"><ClubCrest club="eastbridge"/>Eastbridge</span><span className="gi-score">{match.teams[0].score}<i>:</i>{match.teams[1].score}</span><span className="gi-club">Northport<ClubCrest club="northport"/></span></h1>
          <p><time dateTime={match.display_date}>{matchDate(match.display_date)}</time></p>
          <p>{match.teams[0].score===match.teams[1].score?t('Full time · All square','完场 · 平局'):zh?`${match.teams[0].score>match.teams[1].score?'Eastbridge':'Northport'} 获胜`:`${match.teams[0].score>match.teams[1].score?'Eastbridge':'Northport'} win`} · {goals.length} {t('goals','球')}</p>
        </section>
        <div className="gi-view-switch" role="group" aria-label={t('Match centre view','比赛中心视图')}><button aria-pressed={view==='overview'} onClick={()=>setView('overview')}>{t('Overview','概览')}</button><button aria-pressed={view==='moments'} onClick={()=>setView('moments')}>{t('Moments','时刻')}</button><button aria-pressed={view==='watch'} onClick={()=>setView('watch')}>{t('Watch full match','观看全场')}</button><a className="gi-standings-link" href="#football/standings">{t('Season standings ↗','赛季积分榜 ↗')}</a><button onClick={()=>setGuide(!guide)} aria-expanded={guide}>{t('How to explore','探索指南')}</button></div>
        {guide&&<aside className="gi-guide" aria-label={t('Match centre guide','比赛中心指南')}><h2>{t('Your match, at a glance','比赛一览')}</h2><p>{t('Start with the score and team comparisons. Select a goal below to open its build-up. In Moments, watch the play unfold, or open Filters to follow a player or half. Save any moment to Highlights for Footie\'s summary, drawings and your own notes.','从比分和球队对比开始。选择下方的进球以查看其进攻过程。在时刻中观看比赛展开，或打开筛选跟踪球员或半场。将任意时刻保存到精彩片段，获取 Footie 的总结、绘图和您自己的笔记。')}</p><button onClick={()=>{setView('moments');setGuide(false)}}>{t('Take me to the moments →','带我去时刻 →')}</button><button onClick={()=>setGuide(false)}>{t('Close guide','关闭指南')}</button></aside>}
        {view==='overview'&&<section className="gi-overview" aria-label={t('Full match overview','全场比赛概览')}><div className="gi-editorial"><p className="fan-kicker">{t('THE MATCH IN NUMBERS','数据中的比赛')}</p><h2>{match.headline}</h2><p>{match.summary}</p><button onClick={()=>setView('moments')}>{t('Explore the key moments ↗','探索关键时刻 ↗')}</button></div><div className="gi-comparisons"><div className="gi-comparison-clubs"><strong>Eastbridge</strong><strong>Northport</strong></div>{([t('Shots','射门'),t('Passes completed','传球成功'),t('Passes unsuccessful','传球失败'),t('Shots off target','偏出目标的射门')] as const).map(label=>{const counts=[4418,9598].map(id=>match.events.filter(e=>e.team_id===id&&(label===t('Shots','射门')?e.kind==='Shot':label===t('Shots off target','偏出目标的射门')?e.kind==='Shot'&&e.outcome==='off_target':e.kind==='Pass'&&e.outcome===(label===t('Passes completed','传球成功')?'complete':'incomplete'))).length);return <div className="gi-comparison" key={label}><div><strong>{counts[0]}</strong><span>{label}</span><strong>{counts[1]}</strong></div><div className="gi-comparison-bar"><i style={{flex:counts[0]||.01}}/><i style={{flex:counts[1]||.01}}/></div></div>})}</div></section>}
        {view==='watch'&&<section className="gi-watch" aria-label={t('Full match replay','全场比赛回放')}><header><div><p className="fan-kicker">{t('FULL MATCH REPLAY','全场回放')}</p><h2>{t('From kick-off to the final whistle.','从开球到终场哨声。')}</h2></div><div className="gi-watch-actions"><button onClick={()=>setView('moments')}>{t('Explore individual moments','探索单个时刻')}</button><a className="gi-analyst-button" href={`?match=${encodeURIComponent(matchId)}#analyst`}>{t('Analyst Mode','分析模式')}</a></div></header><PlaySequence fullMatch key={match.match_id} matchId={match.match_id} events={match.events} event={match.events[0]} names={names} players={match.players}/></section>}
        <div hidden={view!=='moments'}>
        <details className="gi-filter-disclosure"><summary>{t('Filters · club, player & half','筛选 · 俱乐部、球员与半场')}</summary>
        <div className="gi-toolbar">
          <div className="gi-team-tabs" role="group" aria-label={t('Team','球队')}>{[['',t('Both clubs','双方俱乐部')],['4418','Eastbridge'],['9598','Northport']].map(([id,label])=><button key={id} aria-pressed={team===id} onClick={()=>{setTeam(id);setPlayer('')}}>{id&&<span className={`gi-team-dot ${id==='9598'?'away':''}`}/>}{label}</button>)}</div>
          <label className="gi-player-select"><span>{t('Follow a player','跟踪球员')}</span><select aria-label={t('Player','球员')} value={player} onChange={e=>setPlayer(e.target.value)}><option value="">{t('Everyone','全部')}</option>{match.players.filter(p=>!team||String(p.team_id)===team).map(p=><option key={p.player_id} value={p.player_id}>{alias(p)} · {teamName(p.team_id)}</option>)}</select></label>
          <div className="gi-period-tabs" role="group" aria-label={t('Period','时段')}>{[['',t('Full match','全场')],['1',t('1st half','上半场')],['2',t('2nd half','下半场')]].map(([id,label])=><button key={id} aria-pressed={period===id} onClick={()=>setPeriod(id)}>{label}</button>)}</div>
        </div>
        </details>
        <div className="gi-workspace">
          <section className="gi-detail" id="gi-detail" tabIndex={-1} aria-label={t('Selected action','选定动作')}>
            <div className="gi-canvas-toolbar"><span><span className="gi-live-dot"/> {t('ON THE PITCH','球场实况')}</span><div role="group" aria-label={t('Pitch view','球场视图')}><button aria-pressed={!map} onClick={()=>setMap(false)}>{t('Selected play','选定动作')}</button><button aria-pressed={map} onClick={()=>setMap(true)}>{t('Shot map','射门地图')} <span>{scope.filter(e=>e.kind==='Shot').length}</span></button></div></div>
            {current?<>
              <div className="gi-detail-heading"><p className="fan-kicker">{teamName(current.team_id)} <span> / </span> {matchClock(current)}</p><h2>{outcomeText(current)}</h2><p><span className="gi-player-avatar">{(names.get(current.player_id)??'').split(' ').map(n=>n[0]).slice(0,2).join('')}</span>{names.get(current.player_id)}</p></div>
              <>{!map?(view==='moments'&&<PlaySequence matchId={match.match_id} sequenceFloor={sequenceFloor} autoAdvance={autoAdvance} onAutoAdvanceChange={setAutoAdvance} onComplete={advanceSequence} key={current.event_id} events={match.events} event={current} names={names} players={match.players}/>):<ActionPitch event={current} name={names.get(current.player_id)??'Player'} shots={map?scope.filter(e=>e.kind==='Shot'):undefined} onSelect={id=>{setFilter('shots');inspect(id)}} names={names} zh={zh}/>}</>
              <ImportMoment match={match} event={current}/>
              {(map||!current.start)&&<div className="gi-canvas-caption"><span>{map?t('Select a shot to explore the play','选择一次射门以探索动作'):current.start?t('Follow the highlighted players','跟踪高亮球员'):t('Location unavailable for this action','此动作的位置不可用')}</span>{map&&<span className="gi-legend"><i/>Eastbridge <i/>Northport</span>}</div>}
              <div className="gi-scrubber"><time>{matchClock(current)}</time><input aria-label={t('Match timeline','比赛时间轴')} aria-valuetext={matchClock(current)} type="range" min={0} max={match.events.length-1} value={currentIndex} onChange={e=>jump(match.events[Number(e.target.value)].event_id)}/><span>{t('FT','完')}</span></div>
              <div className="gi-step"><button disabled={currentIndex<=0} onClick={()=>jump(match.events[currentIndex-1].event_id)}>{t('← Previous action','← 上一个动作')}</button><span>{current.period===1?t('FIRST HALF','上半场'):t('SECOND HALF','下半场')}</span><button disabled={currentIndex>=match.events.length-1} onClick={()=>jump(match.events[currentIndex+1].event_id)}>{t('Next action →','下一个动作 →')}</button></div>
            </>:<div className="gi-canvas-empty"><h2>{t('No plays in this view','此视图中暂无动作')}</h2><p>{t('Try another player or half to explore their match.','尝试选择其他球员或半场以探索比赛。')}</p><button onClick={()=>{setTeam('');setPlayer('');setPeriod('');setFilter('key')}}>{t('Show key moments','显示关键时刻')}</button></div>}
          </section>
          <section className="gi-actions" aria-label={t('Match actions','比赛动作')}><div className="gi-actions-heading"><span className="fan-kicker">{t('THE MATCH, UNPACKED','深度解析比赛')}</span><h2>{t('Find your moment','找到你的时刻')}<span>↘</span></h2></div>
            <label className="gi-action-filter"><span>{t('Show moments','显示时刻')}</span><select aria-label={t('Show moments','显示时刻')} value={filter} onChange={e=>setFilter(e.target.value as Filter)}>{filters.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
            <div className="gi-results"><span>{records.length} {t(records.length===1?'play':'plays',records.length===1?'个动作':'个动作')}{player?` · ${names.get(player)}`:''}</span><button onClick={()=>{setTeam('');setPlayer('');setPeriod('');setFilter('key')}}>{t('Reset filters','重置筛选')}</button></div>
            {!records.length?<p className="gi-empty">{t('No actions match these filters. Try another player or period.','没有符合筛选条件的动作。请尝试其他球员或时段。')}</p>:<ol className="gi-action-list">{records.slice(0,limit).map(e=><li key={e.event_id}><button aria-current={e.event_id===current?.event_id?'true':undefined} onClick={()=>inspect(e.event_id)}><time>{matchClock(e)}</time><span><strong>{outcomeText(e)}</strong><small><i className={`gi-team-dot ${e.team_id===9598?'away':''}`}/>{names.get(e.player_id)} · {teamName(e.team_id)}</small></span><span aria-hidden="true">↗</span></button></li>)}</ol>}
            {records.length>limit&&<button className="gi-more" onClick={()=>setLimit(n=>n+40)}>{t(`Show more actions (${records.length-limit} remaining)`,`显示更多动作（剩余 ${records.length-limit} 个）`)}</button>}
          </section>
        </div>
        </div>
        <section className="gi-goals" aria-label={t('Goal timeline','进球时间轴')}><div><span className="fan-kicker">{t('GOAL BY GOAL','逐球进展')}</span><h2>{t('The story in goals.','用进球讲述故事。')}</h2></div><div className="gi-goal-ribbon">{goals.map((e,i)=><button key={e.event_id} onClick={()=>jump(e.event_id)} aria-current={current?.event_id===e.event_id?'true':undefined}><time>{matchClock(e)}</time><span className="gi-goal-marker"><ClubCrest club={clubId(e.goal_for!)}/></span><strong>{goals.slice(0,i+1).filter(g=>g.goal_for===4418).length} – {goals.slice(0,i+1).filter(g=>g.goal_for===9598).length}</strong><span>{e.outcome==='own_goal'?t('Own goal','乌龙球'):names.get(e.player_id)}</span></button>)}</div></section>
        <div className="gi-below" hidden={view!=='moments'}>
          <section className="gi-stats" aria-label={t('Match statistics','比赛统计')}>
            <p className="fan-kicker">{t('LOOK A LITTLE CLOSER','深入了解')}</p>
            {zh?<h2>射门与传球。<br/>{' '}深入了解。</h2>:<h2>Shots &amp; passes.<br/>{' '}A closer look.</h2>}
            <p className="gi-scope-label">{team?teamName(Number(team)):t('Both clubs','双方俱乐部')} · {period?period==='1'?t('First half','上半场'):t('Second half','下半场'):t('Full match','全场')}{player?` · ${names.get(player)}`:''}</p>
            <div className="gi-stat-strip">{metricCards.map(([id,label,count])=><button key={id} aria-pressed={filter===id} onClick={()=>{setFilter(id);document.getElementById('gi-detail')?.scrollIntoView({block:'start',behavior:'instant'})}}><span>{label}</span><strong>{count}</strong><span aria-hidden="true">↗</span></button>)}</div>
          </section>
          <section className="gi-context" aria-label={t('Around this moment','此时刻前后')}>
            <p className="fan-kicker">{t('CONNECT THE PLAYS','连接动作')}</p>
            <h2>{t('Around this moment','此时刻前后')}</h2>
            <p className="gi-scope-label">{current?t(`Ten seconds either side of ${matchClock(current)}.`,`${matchClock(current)} 前后十秒。`):t('Select a play to follow the sequence.','选择一个动作以跟踪序列。')}</p>
            {current?<div className="gi-context-body">
              <ol>{context.map(e=><li key={e.event_id}><button aria-current={e.event_id===current.event_id?'true':undefined} onClick={()=>jump(e.event_id)}>
                <time>{matchClock(e)}</time><span>{names.get(e.player_id)??'Player'}<strong>{outcomeText(e)}</strong></span><span aria-hidden="true">↗</span>
              </button></li>)}</ol>
              {current.goal_for!==null&&<p className="gi-insight">{teamName(current.goal_for!)} {t('add a goal','进球')}{current.outcome==='own_goal'?t(' through an own goal','（乌龙球）'):''}.</p>}
              {current.review&&<p className="gi-insight">{t('A dangerous loss of the ball. Follow the surrounding plays to see what happened next.','危险失球。查看周围的动作，了解接下来发生了什么。')}</p>}
            </div>:<div/>}
          </section>
        </div>
        <footer className="fan-footer gi-footer">{match.video_url&&<a href={match.video_url} target="_blank" rel="noreferrer">Watch source match ↗</a>}{match.synthetic?<p>Original CounterPress match generated from aggregate football patterns. Calibration: 15 licensed Wyscout matches; fictional clubs and players.</p>:<p>Eastbridge, Northport and player names are display aliases. Actions and the result are adapted from {match.source_label}. Substitute labels identify additional participants.</p>}<p>{match.synthetic?'Calibration data:':'Event data:'} Luca Pappalardo & Emanuele Massucco / Wyscout · <a href={match.source.source} target="_blank" rel="noreferrer">Original dataset</a> · <a href={match.source.license_url} target="_blank" rel="noreferrer">CC BY 4.0</a>. {match.synthetic?'Generated actions and outcomes are new; source matches supply aggregate calibration only.':'Adapted with display aliases, scaled coordinates and outcome classifications.'}</p><details><summary>{t('Sources & how the numbers are counted','数据来源及计数方式')}</summary>{current&&<p>{current.provider_event_id===null?t('Generated event','生成事件')+` ${current.event_id}`:`Wyscout ${zh?'事件':'event'} ${current.provider_event_id}`} · {t('revision','修订')} {current.revision}. {current.period===1?t('First','上'):t('Second','下')} half, {(current.elapsed_ms/1000).toFixed(2)} seconds.</p>}<p>Pitch locations use a 105 × 68 metre display, with the acting team attacking right. The replay reconstructs the action with a full-team formation. Supporting positions and movement are illustrative, not continuous tracking. Video timing has not been verified; the source link opens the original replay.</p><p>{match.metric_policy} On-target shots without a goal are not automatically labelled saves. An unsuccessful pass is a recorded outcome, not a judgment of the player.</p></details></footer>
      </>}
    </main>
  </div>
}
