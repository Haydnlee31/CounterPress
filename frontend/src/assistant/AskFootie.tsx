import {lazy,Suspense,useEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import type {FootieContext} from './context'
import {FootieMascot} from './FootieMascot'
import './ask-footie.css'
const Footie=lazy(()=>import('./Footie'))

export function AskFootie({context,onOpen,variant='default'}:{context:FootieContext;onOpen?:()=>void;variant?:'default'|'pitch'}){
  const [frozen,setFrozen]=useState<FootieContext|null>(null)
  const [opening,setOpening]=useState(false),[error,setError]=useState(false)
  const abort=useRef<AbortController|null>(null)
  useEffect(()=>()=>abort.current?.abort(),[])
  async function open(){
    onOpen?.();const snapshot=structuredClone(context)
    if(!snapshot.resolveSource){setFrozen(snapshot);return}
    abort.current?.abort();const controller=new AbortController();abort.current=controller
    setOpening(true);setError(false)
    try{
      const params=new URLSearchParams({match_id:snapshot.matchId!,event_id:snapshot.eventId!,revision:String(snapshot.eventRevision),resolved:String(!!snapshot.resolved)})
      const response=await fetch(`/api/fan/assistant/moment?${params}`,{signal:controller.signal,credentials:'omit',cache:'no-store'})
      if(!response.ok)throw Error()
      const source=await response.json()
      if(!controller.signal.aborted)setFrozen({...snapshot,cutoff:source.cutoff})
    }catch{if(!controller.signal.aborted)setError(true)}
    finally{if(!controller.signal.aborted)setOpening(false)}
  }
  return <><button type="button" className={variant==='pitch'?'ask-footie-pitch':'ask-footie'} aria-haspopup="dialog" disabled={opening} onClick={()=>void open()}>
    {variant==='pitch'?<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 4V6a2 2 0 0 1 2-2Z"/><path d="M7 9h10M7 13h6"/></svg>:<FootieMascot size={32}/>} {opening?'Opening Footie…':'Ask Footie'} {variant==='default'&&<span aria-hidden="true">↗</span>}
  </button>{error&&<small role="alert">Couldn’t open this moment. Try Ask Footie again.</small>}{frozen&&createPortal(<FootieDialog context={frozen} compact={variant==='pitch'} close={()=>setFrozen(null)}/>,document.body)}</>
}

function FootieDialog({context,close,compact}:{context:FootieContext;close:()=>void;compact:boolean}){
  const dialog=useRef<HTMLDialogElement>(null)
  useEffect(()=>{
    const el=dialog.current!,previous=document.activeElement as HTMLElement|null
    const overflow=document.body.style.overflow
    el.showModal();document.body.style.overflow='hidden'
    return()=>{el.close();document.body.style.overflow=overflow;previous?.focus()}
  },[])
  return <dialog className={`footie-dialog${compact?' footie-drawer':''}`} ref={dialog} aria-label="Ask Footie" onCancel={e=>{e.preventDefault();close()}} onClick={e=>{
    if(e.target===e.currentTarget)close()
    const link=e.target instanceof Element?e.target.closest('a'):null
    if(link?.getAttribute('href')?.startsWith('#football/'))close()
  }}>
    <div className="footie-dialog-top">{compact?<div className="footie-drawer-identity"><FootieMascot size={44}/><div><strong>Footie</strong><small>Alongside the action</small></div></div>:<span>{context.matchId?'Paused at this moment':'From Clubhouse'}</span>}<button type="button" onClick={close} aria-label="Close Footie">×</button></div>
    <Suspense fallback={<p role="status">Opening Footie…</p>}><Footie context={context} compact={compact}/></Suspense>
  </dialog>
}
