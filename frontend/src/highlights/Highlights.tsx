import {FootieLoader} from '../shell/FootieLoader'
import {useState,useSyncExternalStore} from 'react'
import {AppHeader} from '../shell/AppHeader'
import {PlaySequence} from '../gi/PlaySequence'
import {alias} from '../gi/data'
import type {GIMatch} from '../gi/data'
import {matchDate} from '../gi/catalog'
import {getData,useResource} from '../football/data'
import {replayGallery} from '../matchday/replayGallery'
import {FootieMascot} from '../assistant/FootieMascot'
import {highlightLink,removeHighlight,sourceKey,updateHighlight,useCollection} from './collection'
import type {SavedHighlight} from './collection'
import {generateSummary,subscribeSummaries,summaryState,summaryVersion} from './summary'
import '../matchday/matchday.css'
import '../gi/gi.css'
import './highlights.css'

function SavedReplay({item}:{item:SavedHighlight}){
  const result=useResource(`saved-highlight:${item.matchId}`,signal=>getData<GIMatch>(`/api/gi/matches/${encodeURIComponent(item.matchId)}`,signal),item.matchId)
  useSyncExternalStore(subscribeSummaries,summaryVersion)
  const [error,setError]=useState(''),[note,setNote]=useState(item.note)
  const match=result.data,event=match?.events.find(e=>e.event_id===item.eventId)
  const stale=!!match&&!!event&&(event.revision!==item.revision||sourceKey(match,event)!==item.source)
  const state=summaryState(item.id)
  function change(update:(value:SavedHighlight)=>SavedHighlight){try{updateHighlight(item.id,update);setError('')}catch(e){setError((e as Error).message)}}
  return <article className="hl-selected" aria-label="Saved highlight">
    <header className="hl-selected-heading"><div><p className="fan-kicker">{item.clock} · {item.player}</p><h2>{item.title}</h2><p>Eastbridge × Northport · {matchDate(item.date)}</p></div><a href={`?match=${encodeURIComponent(item.matchId)}&moment=${encodeURIComponent(item.eventId)}#gi`}>Back to this match ↗</a></header>
    {result.error?<div role="alert"><p>The replay couldn’t load. Your notes are still saved.</p><button onClick={result.retry}>Try again</button></div>:!match?<FootieLoader label="Opening your highlight…"/>:!event?<p role="alert">This moment is no longer in the match records. Your notes are still saved.</p>:stale?<div className="hl-update" role="status"><h3>This play has been updated</h3><p>Review the latest version in Match Centre. Updating this highlight will clear its old pitch markings and summary; your written note stays.</p><button onClick={()=>{const updated={...item,revision:event.revision,source:sourceKey(match,event),strokes:[],summary:undefined};try{updateHighlight(item.id,()=>updated);void generateSummary(updated);setError('')}catch(e){setError((e as Error).message)}}}>Use updated play</button></div>:<section className="gi-detail hl-pitch" aria-label="Highlight replay"><PlaySequence key={item.source} matchId={match.match_id} events={match.events} event={event} names={new Map(match.players.map(p=>[p.player_id,alias(p)]))} players={match.players} hideObservation annotations={{strokes:item.strokes,change:strokes=>change(value=>({...value,strokes}))}}/></section>}
    <section className="hl-summary" aria-label="Moment summary"><div className="hl-summary-heading"><FootieMascot size={46}/><div><p className="fan-kicker">FOOTIE’S TAKE</p><h3>Footie's Summary</h3></div></div>
      {stale||!event?<p>Analysis will be available after the current play is loaded and verified.</p>:state.busy?<p role="status">Footie is reviewing the recorded play… You can keep watching and add your notes.</p>:item.summary&&item.summary.source===item.source?<>{item.summary.text.map((text,i)=><p key={i}>{text}</p>)}<button onClick={()=>void generateSummary(item)}>Refresh summary</button>{!item.summary.ai&&<p className="hl-summary-status">Statistics summary · AI analysis is currently unavailable. <button onClick={()=>void generateSummary(item)}>Try AI analysis</button></p>}</>:<><p>{state.error||'Your replay is saved. Generate Footie’s take on the play.'}</p><button onClick={()=>void generateSummary(item)}>Generate AI summary</button></>}
      {state.error&&item.summary&&!state.busy&&<p role="alert">{state.error}</p>}
    </section>
    <section className="hl-notes"><label htmlFor="highlight-note">Your coaching notes</label><p>What would you repeat, or change next time?</p><textarea id="highlight-note" value={note} maxLength={2000} rows={3} placeholder="A run to watch, a passing option, a different position…" onChange={e=>setNote(e.target.value)}/><div><small>{note.length}/2000</small><button disabled={note===item.note} onClick={()=>change(value=>({...value,note}))}>{note===item.note?'Notes saved':'Save notes'}</button></div></section>
    {error&&<p role="alert">{error}</p>}
  </article>
}

export default function Highlights({selectedId}:{selectedId?:string}){
  const {items,error}=useCollection(),[failure,setFailure]=useState(''),[remove,setRemove]=useState<string|null>(null)
  const selected=selectedId?items.find(h=>h.id===selectedId):items[0]
  return <div className="matchday hl-page"><AppHeader active="matchday"/><main id="highlights-content">
    <header className="hl-heading"><div><p className="fan-kicker">YOUR COLLECTION</p><h1>Highlights<span>.</span></h1><p>Keep the play. Make it yours.</p></div><a className="hl-primary" href="#gi">Find a moment ＋</a></header>
    {error&&<p role="alert">{error}</p>}
    {selectedId&&!selected&&<p role="status">This highlight isn’t saved in this browser. <a href="#highlights">Open your collection</a></p>}
    {selected?<SavedReplay key={selected.id} item={selected}/>:!error&&<section className="hl-empty"><span aria-hidden="true">↗</span><h2>Your favourite plays, all here.</h2><p>Open Moments in Match Centre and save a play. Watch it again, read Footie’s analysis, and draw your ideas straight onto the pitch.</p><a href="#gi">Explore Match Centre →</a></section>}
    {!!items.length&&<section className="hl-collection" aria-label="Your saved highlights"><div className="hl-section-heading"><h2>Your highlights</h2><span>{items.length} saved</span></div><div className="hl-grid">{items.map(h=><article className="hl-card" key={h.id} data-selected={selected?.id===h.id}><a href={highlightLink(h.id)} aria-current={selected?.id===h.id?'true':undefined}><span className="fan-kicker">{matchDate(h.date)} · {h.clock}</span><h3>{h.title}</h3><p>{h.player}</p><small>Eastbridge × Northport {h.strokes.length>0?'· Annotated':''}</small><span className="hl-card-arrow" aria-hidden="true">↗</span></a>{remove===h.id?<div className="hl-remove"><span>Remove replay and notes?</span><button onClick={()=>{try{removeHighlight(h.id);setRemove(null);setFailure('');if(selected?.id===h.id)window.location.hash='highlights'}catch(e){setFailure((e as Error).message)}}}>Remove</button><button onClick={()=>setRemove(null)}>Keep</button></div>:<button className="hl-remove-link" aria-label={`Remove ${h.title} by ${h.player}`} onClick={()=>setRemove(h.id)}>Remove</button>}</article>)}</div></section>}
    {failure&&<p role="alert">{failure}</p>}
    <details className="hl-preloaded"><summary>Preloaded highlights</summary><div className="hl-grid">{Object.entries(replayGallery).map(([id,h])=><a className="hl-card" key={id} href={`?story=${encodeURIComponent(id)}#highlights/preloaded`}><span className="fan-kicker">{h.duration}</span><h3>{h.title[0]}</h3><span>Watch highlight ↗</span></a>)}</div></details>
    <footer className="hl-storage-note">Your collection, drawings and notes are saved in this browser. AI summaries use the recorded match events.</footer>
  </main></div>
}
