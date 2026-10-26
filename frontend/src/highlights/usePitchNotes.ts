import {useEffect,useState} from 'react'
import type {Event} from '../types'
import type {Stroke} from './collection'

export function usePitchNotes(events:Event[]){
 const source=JSON.stringify(events),key=`footie.pitch-notes.v1:${events[0]?.match_id??'empty'}`
 const [state,setState]=useState<{source:string;strokes:Stroke[]}>({source:'',strokes:[]}),[error,setError]=useState('')
 useEffect(()=>{try{const saved=JSON.parse(localStorage.getItem(key)??'null');const strokes=saved?.source===source&&Array.isArray(saved.strokes)?saved.strokes:[]
   if(strokes.length>30||!strokes.every((s:Stroke)=>Number.isFinite(s.at)&&s.at>=0&&s.at<=1&&Array.isArray(s.points)&&s.points.length<=250&&s.points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&p.x>=0&&p.x<=105&&p.y>=0&&p.y<=68)))throw Error()
   setState({source,strokes});setError('')
 }catch{setState({source,strokes:[]});setError('Saved drawings could not be loaded. New drawings will last for this visit.')}},[source,key])
 function change(strokes:Stroke[]){setState({source,strokes});try{localStorage.setItem(key,JSON.stringify({source,strokes}));setError('')}catch{setError('Drawing kept for this visit. Browser storage is unavailable.')}}
 return {strokes:state.source===source?state.strokes:[],change,error}
}
