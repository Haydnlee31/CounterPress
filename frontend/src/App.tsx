import { AppHeader } from './shell/AppHeader'
import { lazy, Suspense, useEffect, useState } from 'react'
import AnalysisApp from './AnalysisApp'
import { Matchday } from './matchday/Matchday'

const Tools = lazy(() => import('./tools/Tools'))
const GI = lazy(() => import('./gi/GI'))
const ExploreData = lazy(() => import('./explore/ExploreData'))
const Studio = lazy(() => import('./studio/Studio'))

/** Explicit deep link keeps the existing analysis workspace available. */
export default function App() {
  const [route, setRoute] = useState(
    () => window.location.hash,
  )
  useEffect(() => {
    const update = () => { setRoute(window.location.hash); if (['#matchday','#explore','#gi','#studio','#analysis','#tools'].includes(window.location.hash)) document.querySelector('.cp-shell')?.scrollIntoView?.({block:'start',behavior:'instant'}) }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  if (route === '#tools') return <Suspense fallback={<p>Opening Tools…</p>}><Tools /></Suspense>
  if (route === '#gi') return <Suspense fallback={<p>Opening Match Centre…</p>}><GI /></Suspense>
  if (route === '#explore') return <Suspense fallback={<p>Opening match analysis…</p>}><ExploreData /></Suspense>
  if (route === '#studio') return <Suspense fallback={<p>Opening Studio…</p>}><Studio /></Suspense>
  return route === '#analysis' ? (
    <>
      <AppHeader active="analysis"/>
      <AnalysisApp embedded />
    </>
  ) : (
    <Matchday />
  )
}
