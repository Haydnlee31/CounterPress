import {cleanup,render,screen,fireEvent} from '@testing-library/react'
import {afterEach,expect,it} from 'vitest'
import {ContextualInsight} from './ContextualInsight'
import {MetricMap} from './MetricBoard'
import {PlayerOptions} from './PlayerOptions'
import {AnalystConversation} from './AnalystRoom'
import type {Snapshot,Metric,Analysis} from './data'
afterEach(cleanup)
it('draws a shot path only when both recorded endpoints exist',()=>{
 const metric={id:'shots',key:'shot_map',status:'available',window:'prefix',role:'chance',label:'Shots',unit:'locations',basis:'recorded_events',club_id:'a',value:{shots:[{event_id:'one',x:90,y:20,end:{x:105,y:34},outcome:'goal'},{event_id:'two',x:85,y:40,outcome:'saved'}]}} as Metric
 const {container}=render(<MetricMap metrics={[metric]} view="shot_map" clubId="a"/>)
 expect(container.querySelectorAll('.an-shot-path')).toHaveLength(1)
 expect(container.querySelector('.an-shot-path')?.getAttribute('d')).toBe('M90 20L105 34')
 expect(screen.getByRole('img').getAttribute('aria-label')).toContain('recorded trajectories')
})
it('groups every player once under their club',()=>{
 const s={clubs:[{club_id:'a',name:'Eastbridge'},{club_id:'b',name:'Northport'}],players:[{player_id:'b1',club_id:'b',name:'Bea',role:'MF'},{player_id:'a1',club_id:'a',name:'Ali',role:'FW'}]} as Snapshot
 const {container}=render(<select><PlayerOptions snapshot={s}/></select>)
 const groups=container.querySelectorAll('optgroup')
 expect([...groups].map(g=>g.label)).toEqual(['Eastbridge','Northport'])
 expect(groups[0].querySelector('option')?.value).toBe('a1')
 expect(groups[1].querySelector('option')?.value).toBe('b1')
})
it('shows the latest comment without scrolling and retains expandable history',()=>{
 const rounds=[1,2,3].map(i=>({snapshot_id:`s${i}`,mode:'discussion',status:'complete',readings:[],summary:null,cutoff:{period:1,elapsed_ms:i*60000},messages:[{id:'control',role:'control',text:`Reading ${i}`,metric_ids:[],evidence_ids:[],reply_to:null,relation:'observation'}]})) as Analysis[]
 const {rerender,container}=render(<AnalystConversation rounds={rounds.slice(0,2)} pending={false} available playing live analysis={rounds[1]} refresh={()=>{}}/>)
 expect(screen.getByRole('log').textContent).toContain('Reading 2')
 expect(screen.getByRole('log').textContent).not.toContain('Reading 1')
 const history=container.querySelector('details')!
 expect(history.open).toBe(false)
 fireEvent.click(history.querySelector('summary')!)
 rerender(<AnalystConversation rounds={rounds} pending={false} available playing live analysis={rounds[2]} refresh={()=>{}}/>)
 expect(screen.getByRole('log').textContent).toContain('Reading 3')
 expect(screen.getByRole('log').textContent).not.toContain('Reading 2')
 expect(history.open).toBe(true)
 expect(screen.getByRole('region',{name:'Earlier analyst comments'}).textContent).toContain('Reading 2')
 expect(screen.getByRole('region',{name:'Earlier analyst comments'}).textContent).toContain('Reading 1')
})


it('labels the club whose positive shot evidence triggered the contextual map',()=>{
 const metrics=[{id:'zero',key:'shots',club_id:'a',value:0},{id:'one',key:'shots',club_id:'b',value:1}] as Metric[]
 const snapshot={cutoff:{period:1,elapsed_ms:120000},clubs:[{club_id:'a',name:'Eastbridge'},{club_id:'b',name:'Northport'}],players:[],metrics:[]} as unknown as Snapshot
 const round={snapshot_id:'s',cutoff:{period:1,elapsed_ms:60000},metrics,messages:[{metric_ids:['zero','one'],visual:'none'}]} as unknown as Analysis
 const {rerender}=render(<ContextualInsight snapshot={snapshot} rounds={[round]} focusPlayerId={null}/>)
 expect(screen.getByText(/Northport · Match so far/)).toBeTruthy()
 rerender(<ContextualInsight snapshot={{...snapshot,cutoff:{period:1,elapsed_ms:30000}}} rounds={[round]} focusPlayerId={null}/>)
 expect(screen.queryByRole('region',{name:'Conversation visual'})).toBeNull()
})
