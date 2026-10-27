import {FootieLoader} from './shell/FootieLoader'
import { AppHeader } from './shell/AppHeader'
import { lazy, Suspense, useEffect, useState } from 'react'
import AnalysisApp from './AnalysisApp'
import './shell/theme.css'
import {watchCareerRevisions} from './football/revisions'

const Highlights = lazy(() => import('./highlights/Highlights'))
const Matchday = lazy(() => import('./matchday/Matchday').then(module=>({default:module.Matchday})))
const AnalystMode = lazy(() => import('./analyst/AnalystMode'))
const FullMatch = lazy(() => import('./live/FullMatch'))
const Tools = lazy(() => import('./tools/Tools'))
const GI = lazy(() => import('./gi/GI'))
const Studio = lazy(() => import('./studio/Studio'))
const Footie = lazy(() => import('./assistant/Footie'))
const FootballHub = lazy(() => import('./football/FootballHub'))

/** Explicit deep link keeps the existing analysis workspace available. */
export default function App() {
  useEffect(watchCareerRevisions,[])
  const [route, setRoute] = useState(
    () => window.location.hash,
  )
  useEffect(() => {
    const update = () => { setRoute(window.location.hash); if (window.location.hash.startsWith('#highlights') || ['#live','#matchday','#matchday/breakdown','#explore','#gi','#studio','#analysis','#tools'].includes(window.location.hash)) document.querySelector('.cp-shell')?.scrollIntoView?.({block:'start',behavior:'instant'}) }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  if (route === '#analyst') return <Suspense fallback={<FootieLoader page label="Opening Analyst Mode…"/>}><AnalystMode /></Suspense>
  if (route === '#assistant') return <Suspense fallback={<FootieLoader page label="Opening Footie…"/>}><Footie /></Suspense>
  if (route.startsWith('#football')) return <Suspense fallback={<FootieLoader page label="Opening Clubhouse…"/>}><FootballHub /></Suspense>
  if (route === '#live') return <Suspense fallback={<FootieLoader page label="Opening the match…"/>}><FullMatch /></Suspense>
  if (route === '#tools') return <Suspense fallback={<FootieLoader page label="Opening Tools…"/>}><Tools /></Suspense>
  if (!route || route === '#gi') return <Suspense fallback={<FootieLoader page label="Opening Match Centre…"/>}><GI /></Suspense>
  if (route === '#highlights' || (route.startsWith('#highlights/') && route !== '#highlights/preloaded')) {
    let selectedId:string|undefined
    try {selectedId=route.startsWith('#highlights/')?decodeURIComponent(route.slice('#highlights/'.length)):undefined}catch {selectedId='invalid'}
    return <Suspense fallback={<FootieLoader page label="Opening Highlights…"/>}><Highlights selectedId={selectedId}/></Suspense>
  }
  if (route === '#studio') return <Suspense fallback={<FootieLoader page label="Opening Studio…"/>}><Studio /></Suspense>
  return route === '#analysis' ? (
    <>
      <AppHeader active="analysis"/>
      <AnalysisApp embedded />
    </>
  ) : (
    <Suspense fallback={<FootieLoader page label="Opening the highlight…"/>}><Matchday breakdown={route === '#matchday/breakdown' || route === '#explore'} /></Suspense>
  )
}
