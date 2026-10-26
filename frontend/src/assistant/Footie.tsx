import {useEffect,useId,useRef,useState} from 'react'
import {AppHeader} from '../shell/AppHeader'
import {defaults,readPreferences} from '../../../integrations/personalization/client'
import type {FanPreferences} from '../../../integrations/personalization/client'
import {getData,loadWorld,useResource} from '../football/data'
import type {Highlight,Match} from '../football/data'
import {HighlightPlayer} from '../football/HighlightPlayer'
import {FootieMascot} from './FootieMascot'
import type {FootieContext} from './context'
import '../football/football.css'
import './footie.css'
import {onCareerChange} from '../football/revisions'

type Plan={operation:string;player_ids:string[];club_id:string|null;match_id:string|null;metric:string;additional_metrics?:string[];per90:boolean;season:string|null;comparison_season:string|null;analysis?:string|null;investigate_player_id?:string|null}
type Fact={subject_name:string;label:string;value:number|null;unit:string;scope:{season?:string|null;matches?:number;window:string;time_label?:string|null;window_label?:string|null;cutoff?:{period:number;elapsed_ms:number}};coverage:{recorded_matches:number;total_matches:number}|null;evidence:{matches?:unknown[]};href:string}
type Clip={highlight_id:string;match_id:string;title:string;scorer_id:string;date:string}
type Visual={kind:string;label:string;cells?:{column:number;row:number;actions:number}[];items?:{label:string;value?:number|null;unit?:string;detail?:string;time_label?:string;event_id?:string;revision?:number}[];groups?:Visual[]}
type Answer={narrative?:{mode:string;blocks:{id:string;text:string;fact_indices:number[];evidence_id:string}[]};request_id:string;status:string;title:string;text:string[];facts:Fact[];actions:{label:string;href:string;highlight?:Clip}[];visual:Visual|null;plan:Plan;as_of:string;mode:string;suggestions:string[]}
type Turn={question:string;answer:Answer}
const initialQuestions=['How many goals does Mateo Cross have?','Who leads Redhaven in assists?','Compare Rory Ellis and Dario Voss in goals per 90']
const format=(v:number|null)=>v===null?'—':new Intl.NumberFormat('en',{maximumFractionDigits:2}).format(v)
function initialPreferences(){try{return readPreferences(window.localStorage).preferences}catch{return defaults()}}

export function AnswerVisual({visual}:{visual:Answer['visual']}){
  if(!visual)return null
  if(visual.kind==='groups')return <section className={`ft-visual-groups${visual.groups?.length===4?' ft-visual-pairs':''}`} aria-label={visual.label}>{visual.groups?.map(group=><AnswerVisual key={group.label} visual={group}/>)}</section>
  if(visual.kind==='timeline')return <details className="ft-sequence"><summary><span>{visual.label}</span><span className="ft-sequence-count">{visual.items?.length??0} actions</span></summary><ol aria-label={visual.label}>{visual.items?.map((item,i)=><li key={`${item.event_id??i}-${item.revision??0}`}><span className="ft-sequence-time">{item.time_label}</span><div><strong>{item.label}</strong>{item.detail&&<p>{item.detail}</p>}</div></li>)}</ol></details>
  if(visual.kind==='heatmap'){
    const max=Math.max(1,...(visual.cells??[]).map(c=>c.actions))
    return <figure className="ft-map"><figcaption>{visual.label}</figcaption><svg viewBox="-2 -2 109 72" role="img" aria-label="Action heatmap, attacking from left to right"><rect width="105" height="68" rx="1" fill="#173d32"/>{visual.cells?.map(c=><rect key={`${c.column}-${c.row}`} x={c.column*8.75} y={c.row*8.5} width="8.75" height="8.5" fill="#dcf1a0" opacity={.08+.85*c.actions/max}><title>{c.actions} recorded actions</title></rect>)}<g stroke="#fff" opacity=".5" strokeWidth=".5" fill="none"><rect width="105" height="68"/><path d="M52.5 0v68M0 13.84h16.5v40.32H0M105 13.84H88.5v40.32H105"/><circle cx="52.5" cy="34" r="9.15"/></g></svg><small>Recorded action locations · attacking →</small></figure>
  }
  const max=Math.max(1,...(visual.items??[]).map(i=>i.value??0))
  return <figure className="ft-bars"><figcaption>{visual.label}</figcaption>{visual.items?.map((item,i)=><div className="ft-bar" key={i}><div><span>{item.label}</span><strong>{format(item.value??null)}{item.value==null?'':item.unit==='percent'?'%':item.unit==='per90'?' /90':item.unit==='seconds'?' s':item.unit==='metres'?' m':''}</strong></div><div className="ft-track"><span style={{width:`${Math.max(0,(item.value??0)/max)*100}%`}}/></div></div>)}</figure>
}

export default function Footie({context,compact=false}:{context?:FootieContext;compact?:boolean}){
  const questionId=useId()
  const world=useResource('footie-world',loadWorld,false)
  const matches=useResource('footie-matches',signal=>getData<{items:Match[]}>('/api/data/matches?featured=true',signal))
  const config=useResource('footie-config',signal=>getData<{natural_language:boolean}>('/api/fan/assistant/config',signal))
  const [prefs,setPrefs]=useState<FanPreferences>(initialPreferences),[question,setQuestion]=useState(context?.question??''),[turns,setTurns]=useState<Turn[]>([])
  const [player,setPlayer]=useState(context?.playerId??''),[club,setClub]=useState(context?.clubId??''),[match,setMatch]=useState(context?.matchId??''),[season,setSeason]=useState(context?.season??'')
  const [typing,setTyping]=useState(false)
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[lastQuestion,setLastQuestion]=useState(''),[highlight,setHighlight]=useState<Highlight|null>(null)
  const controller=useRef<AbortController|null>(null),serial=useRef(0),answerRef=useRef<HTMLDivElement>(null),input=useRef<HTMLTextAreaElement>(null)
  useEffect(()=>()=>{controller.current?.abort();serial.current++},[])
  useEffect(()=>{if(!world.data)return;try{const checked=readPreferences(window.localStorage,{playerIds:new Set(world.data.players.map(p=>p.player_id)),clubIds:new Set(world.data.catalog.clubs.map(c=>c.club_id))}).preferences;setPrefs(checked);if(!context&&checked.favorite_player_ids.length===1)setPlayer(checked.favorite_player_ids[0])}catch{setPrefs(defaults())}},[world.data])
  const [recordsChanged,setRecordsChanged]=useState(false)
  useEffect(()=>onCareerChange(()=>{
    // The open highlight owns its historical cutoff and explicit update review.
    // Clear outdated assistant answers without closing that independent view.
    controller.current?.abort();serial.current++;setBusy(false);setTurns([]);setError('');setRecordsChanged(true)
  }),[])
  const cancel=()=>{controller.current?.abort();serial.current++;setBusy(false)}
  const reset=()=>{cancel();setTurns([]);setError('');setQuestion('');input.current?.focus()}
  const changeScope=(change:()=>void)=>{cancel();change();setTurns([]);setError('')}
  async function ask(text:string){
    if(!world.data||!text.trim())return
    const completedPeriod=matches.data?.items.find(item=>item.match_id===match)?.period_lengths_ms?.[1]
    if(match&&!context?.cutoff&&completedPeriod===undefined){setLastQuestion(text);setError('Match details are still loading. Please try again.');return}
    controller.current?.abort();const token=++serial.current,abort=new AbortController();controller.current=abort
    setBusy(true);setRecordsChanged(false);setError('');setLastQuestion(text);setQuestion('')
    const payload={question:text,preferences:prefs,as_of:context?.asOf??world.data.asOf,player_id:player||null,club_id:club||null,match_id:match||null,
      season:season||null,cutoff:context?.cutoff??(match?{period:2,elapsed_ms:completedPeriod!}:null),event_id:context?.eventId??null,event_revision:context?.eventRevision??null,through_sequence:context?.throughSequence,previous_plan:turns.at(-1)?.answer.plan??null}
    try{
      const response=await fetch('/api/fan/assistant/ask',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'omit',cache:'no-store',body:JSON.stringify(payload),signal:abort.signal})
      if(!response.ok)throw new Error(response.status===409?'The match records changed. Return to the moment and review the update before asking again.':response.status===429?'Please wait a moment before asking again.':'Footie couldn’t reach the match records. Please try again.')
      const answer=await response.json() as Answer
      if(token!==serial.current)return
      setTurns(old=>[...old,{question:text,answer}].slice(-8))
      requestAnimationFrame(()=>answerRef.current?.scrollIntoView?.({block:'start',behavior:'smooth'}))
    }catch(e){if(token===serial.current&&!abort.signal.aborted)setError(e instanceof Error?e.message:'Please try again.')}
    finally{if(token===serial.current)setBusy(false)}
  }
  const openClip=(clip:Clip)=>setHighlight({highlight_id:clip.highlight_id,match_id:clip.match_id,title:clip.title,date:clip.date,tag:'match',player_ids:[clip.scorer_id],club_ids:[],relevance:{reason:'',score:0},action:{kind:'replay',subject_id:clip.match_id,label:'Watch goal',replay_url:`/api/data/highlights/${encodeURIComponent(clip.highlight_id)}/replay`}})
  const suggestions=turns.at(-1)?.answer.suggestions??initialQuestions
  return <div className={`ft-page ${!context?'ft-standalone':''}`}>{!context&&<AppHeader active="assistant"/>}
    <main className="ft-main"><header className="ft-heading"><div hidden={compact}><p className="ft-eyebrow"><span/> YOUR FOOTBALL COMPANION</p><h1>Ask Footie<span>↗</span></h1><p>Player stats, comparisons and match insights.</p></div><button className="ft-reset" onClick={reset} disabled={!turns.length&&!busy}>New conversation ＋</button></header>
      {world.error||matches.error||config.error?<section className="ft-empty" role="alert"><h2>The records couldn’t be opened.</h2><button onClick={()=>{world.retry();matches.retry();config.retry()}}>Try again</button></section>:!world.data?<p role="status">Opening the match records…</p>:<>
      <section className="ft-context" aria-label="Question context" hidden={!!context}><span>Talk about</span><label>Player<select aria-label="Player context" value={player} onChange={e=>changeScope(()=>{setPlayer(e.target.value);setClub('');setMatch('')})}><option value="">Any player</option>{world.data.players.filter(p=>p.featured).map(p=><option key={p.player_id} value={p.player_id}>{prefs.favorite_player_ids.includes(p.player_id)?'♥ ':''}{p.name}</option>)}</select></label><label>Club<select aria-label="Club context" value={club} onChange={e=>changeScope(()=>{setClub(e.target.value);setPlayer('');setMatch('')})}><option value="">Any club</option>{world.data.catalog.clubs.filter(c=>c.featured).map(c=><option key={c.club_id} value={c.club_id}>{c.name}</option>)}</select></label><label>Period<select aria-label="Assistant period" value={season} disabled={!!match} onChange={e=>changeScope(()=>setSeason(e.target.value))}><option value="">Career</option>{world.data.catalog.seasons.map(s=><option key={s}>{s}</option>)}</select></label><details><summary>A match</summary><label>Completed match<select aria-label="Match context" value={match} onChange={e=>changeScope(()=>{setMatch(e.target.value);setPlayer('');setClub('');setSeason('')})}><option value="">Choose a match</option>{matches.data?.items.map(m=><option key={m.match_id} value={m.match_id}>{world.data!.catalog.clubs.find(c=>c.club_id===m.home_id)?.name} × {world.data!.catalog.clubs.find(c=>c.club_id===m.away_id)?.name} · {m.kickoff.slice(0,10)}</option>)}</select></label>{match&&<button onClick={()=>ask('Why did the latest goal matter in this match?')}>Explain the latest goal ↗</button>}</details></section>
      {context&&<div className="ft-source-context"><strong>{context.label}</strong><small>{context.cutoff?`Through ${context.cutoff.period===2?'2nd':'1st'} half · ${Math.floor(context.cutoff.elapsed_ms/60000)}:${String(Math.floor(context.cutoff.elapsed_ms/1000)%60).padStart(2,'0')} in this half`:(context.season||'Career')}{context.matchId?' · Match-time answers':''}</small></div>}
      {!turns.length&&!busy&&<section className="ft-start"><div className="ft-welcome-mascot" hidden={compact}><FootieMascot mood={typing?'listening':'greeting'} size={176} trackPointer/></div><h2>{compact?"Let’s look at this play.":"What caught your eye?"}</h2><p>{compact?"The replay is paused. Ask about the action, then pick up where you left off.":"Start with a name, compare two players, or find the story behind a goal."}</p><div className="ft-starters" hidden={compact}>{(context?[context.question]:player?[`How is ${world.data.players.find(p=>p.player_id===player)?.name} doing recently?`,`How many assists does ${world.data.players.find(p=>p.player_id===player)?.name} have?`]:club?[`Who leads ${world.data.catalog.clubs.find(c=>c.club_id===club)?.name} in goals?`]:match?['What made that goal happen?','What has changed in this match?','Why did the latest goal matter in this match?']:initialQuestions).map((q,i)=><button key={q} onClick={()=>ask(q)}><span>0{i+1}</span>{q}<b>↗</b></button>)}</div></section>}
      {recordsChanged&&<p className="ft-status" role="status">{context?.throughSequence!==undefined?'The match records have changed. Return to the moment to review the update.':'The match records have changed. Ask again for the latest figures.'}</p>}
      <div className="ft-conversation" aria-label="Conversation">{turns.map((turn,i)=><section className="ft-turn" key={turn.answer.request_id} ref={i===turns.length-1?answerRef:undefined}><p className="ft-question">{turn.question}</p><article className="ft-answer"><div className="ft-answer-mark"><FootieMascot size={42} mood={i===turns.length-1&&turn.answer.actions.some(a=>a.highlight)?'celebrating':'idle'}/><span>Footie</span></div><h2>{turn.answer.title}</h2>{turn.answer.narrative?.blocks.length?<><div className="ft-story">{turn.answer.narrative.blocks.map(block=><p key={block.id}>{block.text}</p>)}</div><details className="ft-breakdown"><summary>Figures and context</summary>{turn.answer.text.map((p,j)=><p key={j}>{p}</p>)}</details></>:turn.answer.text.map((p,j)=><p key={j}>{p}</p>)}<AnswerVisual visual={turn.answer.visual}/><div className="ft-actions">{turn.answer.actions.map((a,j)=>a.highlight?<button key={j} onClick={()=>openClip(a.highlight!)}>▶ {a.label}</button>:<a key={j} href={a.href}>{a.label} ↗</a>)}</div>{turn.answer.facts.length>0&&<details className="ft-evidence"><summary>Check the numbers · {turn.answer.facts.length} {turn.answer.facts.length===1?'figure':'figures'}</summary>{turn.answer.facts.map((f,j)=><div key={j}><a href={f.href}>{f.subject_name}</a><span>{f.label}{f.unit==='per90'?' /90':''}</span><strong>{format(f.value)}{f.unit==='percent'?'%':f.unit==='metres'?' m':f.unit==='seconds'?' s':f.unit==='minutes'?' min':''}</strong><small>{f.scope.window_label??(f.scope.window==='completed_appearances_before_kickoff'?`Previous ${f.scope.matches??''} appearances · before kickoff`:f.scope.time_label?`Through ${f.scope.time_label}`:f.scope.cutoff?`Period ${f.scope.cutoff.period} · ${Math.floor(f.scope.cutoff.elapsed_ms/60000)}′`:f.scope.season??'Career')}{f.coverage?` · ${f.coverage.recorded_matches}/${f.coverage.total_matches} recorded appearances`:''}</small></div>)}</details>}{turn.answer.mode==='lookup_fallback'&&<small className="ft-status">Answered with a direct statistics lookup.</small>}</article></section>)}</div>
      {busy&&<div className="ft-thinking" role="status"><FootieMascot mood="thinking" size={64}/> Reading the match records… <button onClick={cancel}>Cancel</button></div>}
      {error&&<div className="ft-error" role="alert">{error}<button onClick={()=>ask(lastQuestion)}>Try again</button></div>}
      <div className="ft-composer"><div className="ft-followups">{!!turns.length&&!busy&&suggestions.slice(0,context?.matchId?2:3).map(q=><button key={q} onClick={()=>ask(q)}>{q} ↗</button>)}</div><form onSubmit={e=>{e.preventDefault();void ask(question)}}><label htmlFor={questionId} className="sr-only">Ask a football question</label><textarea onFocus={()=>setTyping(true)} onBlur={()=>setTyping(false)} ref={input} id={questionId} placeholder="Ask about a player, club or match…" value={question} maxLength={600} rows={2} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(!busy)void ask(question)}}}/><button type="submit" disabled={busy||!question.trim()} aria-label="Send question">↑</button></form><p>{compact?'Close Footie to return to the replay.':<>Match records through {world.data.throughDate} · {config.data?.natural_language?'Natural-language questions':'Quick statistics lookups'} · Conversation stays in this tab</>}</p></div>
      </>}
    </main>{highlight&&world.data&&<HighlightPlayer highlight={highlight} world={world.data} prefs={prefs} update={setPrefs} close={()=>setHighlight(null)}/>}</div>
}
