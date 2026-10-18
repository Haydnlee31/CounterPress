import { lazy, Suspense, useEffect, useState } from 'react'
import AnalysisApp from './AnalysisApp'
import { Matchday } from './matchday/Matchday'

const ExploreData = lazy(() => import('./explore/ExploreData'))
const Studio = lazy(() => import('./studio/Studio'))

/** Explicit deep link keeps the existing analysis workspace available. */
export default function App() {
  const [route, setRoute] = useState(
    () => window.location.hash,
  )
  useEffect(() => {
    const update = () => setRoute(window.location.hash)
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  if (route === '#explore') return <Suspense fallback={<p>Opening match analysis…</p>}><ExploreData /></Suspense>
  if (route === '#studio') return <Suspense fallback={<p>Opening Studio…</p>}><Studio /></Suspense>
  return route === '#analysis' ? (
    <>
      <nav className="workspace-return" aria-label="Workspace">
        <a href="#matchday">← Matchday / 比赛故事</a>
        <a href="#studio">Producer Studio ↗</a>
      </nav>
      <AnalysisApp />
    </>
  ) : (
    <Matchday />
  )
}
