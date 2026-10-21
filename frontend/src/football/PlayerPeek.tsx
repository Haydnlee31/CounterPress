import {useEffect,useId,useLayoutEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import type {FocusEvent,PointerEvent} from 'react'
import type {Player} from './data'
import {playerPortraits} from './portraits'
import './playerPeek.css'

type Identity=Pick<Player,'player_id'|'name'|'role'|'number'>
type Anchor={id:string;name:string;x:number;y:number;root:Element;target:Element;mode:'hover'|'focus'|'touch'}
let catalog:Promise<Identity[]>|undefined
function identities(){
  if(!catalog)catalog=fetch('/api/data/players?featured=true&limit=100',{credentials:'omit'})
    .then(async r=>{if(!r.ok)throw Error('Player details unavailable');return (await r.json()).items as Identity[]})
    .catch(()=>{catalog=undefined;return []})
  return catalog
}
const roles:Record<string,string>={GK:'Goalkeeper',DF:'Defender',MF:'Midfielder',FW:'Forward'}
export function peekPosition(x:number,y:number,width:number,height:number,viewport:{width:number;height:number}){
  const gap=16,edge=12
  return {left:Math.max(edge,Math.min(x+gap+width>viewport.width-edge?x-width-gap:x+gap,viewport.width-width-edge)),top:Math.max(edge,Math.min(y+gap+height>viewport.height-edge?y-height-gap:y+gap,viewport.height-height-edge))}
}
/** One lightweight card per pitch. No model call or request on pointer movement. */
export function usePlayerPeek(known?:Identity[],enabled=true,frameKey?:string|number){
  const [players,setPlayers]=useState<Identity[]>(known??[]),[anchor,setAnchor]=useState<Anchor|null>(null)
  const id=useId(),timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined)
  const overCard=useRef(false)
  const cancel=()=>{clearTimeout(timer.current);timer.current=undefined}
  const close=()=>{cancel();overCard.current=false;setAnchor(null)}
  const leave=()=>{cancel();timer.current=setTimeout(()=>setAnchor(null),140)}
  useEffect(()=>{if(known){setPlayers(known);return}let alive=true;void identities().then(p=>{if(alive)setPlayers(p)});return()=>{alive=false}},[known])
  useEffect(()=>()=>clearTimeout(timer.current),[])
  useEffect(()=>{close()},[enabled,frameKey])
  useEffect(()=>{
    if(!anchor)return
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close()}}
    const outside=(e:globalThis.PointerEvent)=>{if(!(e.target instanceof Element)||!e.target.closest('[data-player-peek],.player-peek'))close()}
    window.addEventListener('keydown',key,true);window.addEventListener('resize',close);document.addEventListener('scroll',close,true);document.addEventListener('pointerdown',outside)
    return()=>{window.removeEventListener('keydown',key,true);window.removeEventListener('resize',close);document.removeEventListener('scroll',close,true);document.removeEventListener('pointerdown',outside)}
  },[!!anchor])
  function show(playerId:string,name:string,target:Element,x:number,y:number,mode:Anchor['mode']='hover'){if(!enabled)return;cancel();setAnchor({id:playerId,name,x,y,root:target.closest('dialog')??document.body,target,mode})}
  function bind(playerId:string,name:string){return {
    'data-player-peek':playerId,'data-inspectable':enabled,'aria-describedby':enabled&&anchor?.id===playerId?id:undefined,
    onPointerEnter:(e:PointerEvent<SVGGElement>)=>{if(e.pointerType!=='touch')show(playerId,name,e.currentTarget,e.clientX,e.clientY)},
    onPointerMove:(e:PointerEvent<SVGGElement>)=>{if(e.pointerType!=='touch')setAnchor(a=>a?.id===playerId?{...a,x:e.clientX,y:e.clientY}:a)},
    onPointerLeave:(e:PointerEvent<SVGGElement>)=>{if(e.pointerType!=='touch')leave()},
    onFocus:(e:FocusEvent<SVGGElement>)=>{const r=e.currentTarget.getBoundingClientRect();show(playerId,name,e.currentTarget,r.right,r.top+r.height/2,'focus')},
    onBlur:leave,
    onPointerDown:(e:PointerEvent<SVGGElement>)=>{if(e.pointerType!=='touch'){e.preventDefault();return}if(e.pointerType==='touch'){const r=e.currentTarget.getBoundingClientRect();show(playerId,name,e.currentTarget,r.right,r.top,'touch')}},
  }}
  // A moving SVG marker may leave a stationary pointer without a mousemove.
  // Dismiss that hover card; keyboard/touch cards follow their actual marker.
  useEffect(()=>{
    if(!anchor||!enabled)return
    let frame:number
    const tick=()=>{
      if(!anchor.target.isConnected){close();return}
      if(anchor.mode==='hover'&&!overCard.current){
        const under=document.elementFromPoint?.(anchor.x,anchor.y)
        if(under&&!anchor.target.contains(under)&&!under.closest('.player-peek')){if(!timer.current)leave()}
      }else if(anchor.mode!=='hover'){
        const box=anchor.target.getBoundingClientRect(),x=box.right,y=box.top+box.height/2
        setAnchor(a=>a&&a.id===anchor.id&&(Math.abs(a.x-x)>.5||Math.abs(a.y-y)>.5)?{...a,x,y}:a)
      }
      frame=requestAnimationFrame(tick)
    }
    frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)
  },[anchor?.id,anchor?.mode,anchor?.x,anchor?.y,enabled])
  const record=anchor?players.find(p=>p.player_id===anchor.id):undefined
  return {bind,card:enabled&&anchor?createPortal(<PlayerPeek key={anchor.id} id={id} anchor={anchor} player={record} enter={()=>{overCard.current=true;cancel()}} leave={()=>{overCard.current=false;leave()}}/>,anchor.root):null}
}
function PlayerPeek({id,anchor,player,enter,leave}:{id:string;anchor:Anchor;player?:Identity;enter:()=>void;leave:()=>void}){
  const ref=useRef<HTMLDivElement>(null),[position,setPosition]=useState({left:12,top:12}),[failed,setFailed]=useState(false)
  useLayoutEffect(()=>{const r=ref.current!.getBoundingClientRect();setPosition(peekPosition(anchor.x,anchor.y,r.width,r.height,{width:window.innerWidth,height:window.innerHeight}))},[anchor.x,anchor.y,player])
  const name=player?.name??anchor.name,portrait=playerPortraits[anchor.id]
  return <div ref={ref} id={id} role="tooltip" className="player-peek" style={position} onPointerEnter={enter} onPointerLeave={e=>{if(e.pointerType!=='touch')leave()}}>
    <div className="player-peek-avatar" aria-hidden="true">{portrait&&!failed?<img src={portrait} alt="" onError={()=>setFailed(true)}/>:<span>{name.split(' ').map(s=>s[0]).slice(0,2).join('')}</span>}</div>
    <div className="player-peek-copy"><strong>{name}</strong><span>{player?roles[player.role]??'Position unavailable':'Position unavailable'}<i aria-hidden="true">·</i>{player&&Number.isInteger(player.number)?`#${player.number}`:'Shirt unavailable'}</span></div>
  </div>
}
