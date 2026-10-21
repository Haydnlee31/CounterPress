import {useState} from 'react'
export const replaySpeeds=[.5,1,1.5,2] as const
const key='footie.replay.speed.v1'
export function useReplaySpeed(){
  const [speed,setSpeed]=useState(()=>{try{const n=Number(sessionStorage.getItem(key));return replaySpeeds.some(v=>v===n)?n:1}catch{return 1}})
  return [speed,(n:number)=>{if(!replaySpeeds.some(v=>v===n))return;setSpeed(n);try{sessionStorage.setItem(key,String(n))}catch{/* Session choice only. */}}] as const
}
