import {useEffect,useState} from 'react'

/** Shares the existing Analyst phone breakpoint; data remains owned by its parent. */
export function useMobileLayout(){
  const [mobile,setMobile]=useState(()=>typeof matchMedia==='function'&&matchMedia('(max-width: 700px)').matches)
  useEffect(()=>{
    if(typeof matchMedia!=='function')return
    const query=matchMedia('(max-width: 700px)'),update=()=>setMobile(query.matches)
    update();query.addEventListener('change',update)
    return()=>query.removeEventListener('change',update)
  },[])
  return mobile
}
