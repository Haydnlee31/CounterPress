import {useRef,useState} from 'react'
import type {PointerEvent} from 'react'
import type {Stroke} from './collection'

/** Coordinates live in the pitch's 105 × 68 space, including on a rotated phone pitch. */
export function pitchPoint(matrix:DOMMatrix,clientX:number,clientY:number){
  const p=new DOMPoint(clientX,clientY).matrixTransform(matrix.inverse())
  return {x:Math.round(Math.max(0,Math.min(105,p.x))*100)/100,y:Math.round(Math.max(0,Math.min(68,p.y))*100)/100}
}
export function PitchInk({strokes,at,enabled,playing,onStroke}:{strokes:Stroke[];at:number;enabled:boolean;playing:boolean;onStroke:(stroke:Stroke)=>void}){
  const group=useRef<SVGGElement>(null),pointer=useRef<number|null>(null),draft=useRef<Stroke|null>(null)
  const [points,setPoints]=useState<Stroke['points']>([])
  function point(e:PointerEvent<SVGRectElement>){const matrix=group.current?.getScreenCTM();return matrix?pitchPoint(matrix,e.clientX,e.clientY):null}
  function end(e:PointerEvent<SVGRectElement>,save:boolean){
    if(pointer.current!==e.pointerId)return
    if(save&&draft.current&&draft.current.points.length>1)onStroke(draft.current)
    pointer.current=null;draft.current=null;setPoints([])
    if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId)
  }
  const visible=playing?[]:strokes.filter(s=>Math.abs(s.at-at)<.002)
  return <g ref={group} data-pitch-ink="true">
    {[...visible,...(points.length?[{at,points}]:[])].map((s,i)=><polyline key={i} points={s.points.map(p=>`${p.x},${p.y}`).join(' ')} fill="none" stroke="#ff6262" strokeWidth=".65" strokeLinecap="round" strokeLinejoin="round" pointerEvents="none"/>)}
    {enabled&&<rect width="105" height="68" fill="transparent" style={{touchAction:'none',cursor:'crosshair'}} aria-label="Draw on the paused pitch" onPointerDown={e=>{
      if(pointer.current!==null||e.button!==0||strokes.length>=30)return
      const p=point(e);if(!p)return
      e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);pointer.current=e.pointerId;draft.current={at,points:[p]};setPoints([p])
    }} onPointerMove={e=>{
      if(pointer.current!==e.pointerId||!draft.current)return
      const p=point(e),last=draft.current.points.at(-1)!
      if(p&&Math.hypot(p.x-last.x,p.y-last.y)>.35){if(draft.current.points.length>=250)draft.current.points=draft.current.points.filter((_,i)=>i%2===0);draft.current.points.push(p);setPoints([...draft.current.points])}
    }} onPointerUp={e=>end(e,true)} onPointerCancel={e=>end(e,false)} onLostPointerCapture={e=>end(e,false)}/>}
  </g>
}
