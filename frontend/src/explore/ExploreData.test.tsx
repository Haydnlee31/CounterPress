import {readFileSync} from 'node:fs'
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,beforeEach,expect,test,vi} from 'vitest'
import type {Snapshot} from '../types'
import * as api from '../api'
import ExploreData from './ExploreData'
import App from '../App'
vi.mock('../api',()=>({fetchSnapshot:vi.fn(),fetchScenarios:vi.fn()}))
vi.mock('../revisions',()=>({subscribeRevisions:vi.fn(()=>()=>{})}))
beforeEach(()=>{
 window.history.replaceState(null,'','/?story=last-gasp#explore')
 window.localStorage.clear()
 vi.mocked(api.fetchScenarios).mockResolvedValue([])
 vi.mocked(api.fetchSnapshot).mockImplementation(async(story,at,_signal,scope)=>{
  const fixture=JSON.parse(readFileSync(`../fixtures/showcases/${story.replaceAll('-','_')}.json`,'utf8'))
  return {scenario_id:story,scope_id:scope,history_version:1,state:{at:{period:2,elapsed_ms:at}},replay_end:{period:2,elapsed_ms:780000},pitch_events:fixture.events} as Snapshot
 })
})
afterEach(()=>{cleanup();vi.restoreAllMocks()})
test('supporting plays seek the pitch, player selections expose evidence and phase counts are comparable',async()=>{
 render(<ExploreData/>)
 const timeline=await screen.findByRole('region',{name:'Highlight timeline'})
 const pitch=screen.getByRole('region',{name:'Match pitch'})
 expect(within(pitch).getAllByRole('group').filter(e=>e.classList.contains('fan-pitch-player'))).toHaveLength(22)
 fireEvent.click(screen.getByRole('button',{name:/Find the finish/}))
 await waitFor(()=>expect(within(pitch).getByRole('slider').getAttribute('aria-valuenow') ?? (within(pitch).getByRole('slider') as HTMLInputElement).value).toBe('700'))
 fireEvent.click(within(timeline).getAllByRole('button')[0])
 await waitFor(()=>expect(screen.getByRole('button',{name:/Keep the chance alive/}).getAttribute('aria-pressed')).toBe('true'))
 fireEvent.click(screen.getByRole('button',{name:'Players'}))
 fireEvent.click(within(screen.getByRole('complementary',{name:'Highlight insights'})).getByRole('button',{name:/Theo Ashford/}))
 expect(screen.getByRole('heading',{name:'Theo Ashford'})).toBeTruthy()
 expect(screen.getByText('Involved in 2 recorded actions in this highlight.')).toBeTruthy()
 fireEvent.click(within(screen.getByRole('complementary',{name:'Highlight insights'})).getByRole('button',{name:/Rory Ellis/}))
 expect(within(pitch).getByRole('group',{name:'Rory Ellis, Eastbridge'}).classList.contains('selected')).toBe(true)
 fireEvent.click(within(pitch).getByRole('button',{name:'Back to play'}))
 expect(screen.getByRole('heading',{name:'How did the chance develop?'})).toBeTruthy()
 fireEvent.click(within(pitch).getByRole('group',{name:'Finn Brooks, Eastbridge'}))
 expect(screen.getByRole('heading',{name:'How did the chance develop?'})).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'Compare'}))
 expect(screen.getByRole('table').textContent).toContain('Saves')
 fireEvent.change(screen.getByLabelText('Second phase'),{target:{value:'2'}})
 fireEvent.click(screen.getByRole('button',{name:'Show second phase'}))
 await waitFor(()=>expect((within(pitch).getByRole('slider') as HTMLInputElement).value).toBe('700'))
})
test('switching highlights clears player/phase state and preserves the return link',async()=>{
 render(<ExploreData/>)
 await screen.findByRole('region',{name:'Highlight timeline'})
 fireEvent.click(screen.getByRole('button',{name:'Players'}))
 fireEvent.click(screen.getByRole('button',{name:/Pass, move, finish/}))
 await screen.findByRole('button',{name:/Bring the ball under control/})
 expect(screen.getByRole('heading',{level:1}).textContent).toBe('Pass, move, finish')
 expect(screen.getByRole('link',{name:'Watch'}).getAttribute('href')).toBe('#matchday')
 expect(window.location.search).toBe('?story=one-touch')
 expect(screen.queryByRole('heading',{name:'Who was involved?'})).toBeNull()
})
test('network failure offers recovery instead of stale explanations',async()=>{
 vi.mocked(api.fetchSnapshot).mockRejectedValueOnce(new Error('offline'))
 render(<ExploreData/>)
 await screen.findByRole('alert')
 expect(screen.queryByRole('region',{name:'Highlight timeline'})).toBeNull()
 fireEvent.click(screen.getByRole('button',{name:'Try again'}))
 await screen.findByRole('region',{name:'Highlight timeline'})
})

test('Watch, Breakdown and legacy links keep the mounted pitch, seek position and player selection',async()=>{
 render(<App/> )
 await screen.findByRole('region',{name:'Highlight timeline'})
 const pitch=screen.getByRole('region',{name:'Match pitch'})
 const slider=within(pitch).getByRole('slider') as HTMLInputElement
 fireEvent.change(slider,{target:{value:'432'}})
 fireEvent.click(screen.getByRole('button',{name:'Players'}))
 fireEvent.click(within(screen.getByRole('complementary',{name:'Highlight insights'})).getByRole('button',{name:/Rory Ellis/}))
 async function navigate(hash:string) {
  await act(async()=>{window.history.pushState(null,'',hash);window.dispatchEvent(new HashChangeEvent('hashchange'))})
 }
 await navigate('#matchday')
 expect(screen.queryByRole('region',{name:'Highlight timeline'})).toBeNull()
 expect(screen.getByRole('region',{name:'Match pitch'})).toBe(pitch)
 expect(slider.value).toBe('432')
 expect(within(pitch).getByRole('group',{name:'Rory Ellis, Eastbridge'}).classList.contains('selected')).toBe(true)
 await navigate('#matchday/breakdown')
 expect(screen.getByRole('region',{name:'Match pitch'})).toBe(pitch)
 expect(slider.value).toBe('432')
 expect(screen.getByRole('heading',{name:'Who was involved?'})).toBeTruthy()
 expect(screen.getByRole('link',{name:'Breakdown'}).getAttribute('aria-current')).toBe('page')
})
