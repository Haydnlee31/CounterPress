import {cleanup,render,screen} from '@testing-library/react'
import {afterEach,expect,it} from 'vitest'
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
it('keeps multiple reviewed live turns visible rather than replacing the conversation',()=>{
 const rounds=[1,2,3].map(i=>({snapshot_id:`s${i}`,mode:'discussion',status:'complete',readings:[],summary:null,cutoff:{period:1,elapsed_ms:i*60000},messages:[{id:'control',role:'control',text:`Reading ${i}`,metric_ids:[],evidence_ids:[],reply_to:null,relation:'observation'}]})) as Analysis[]
 render(<AnalystConversation rounds={rounds} pending={false} available playing live analysis={rounds[2]} refresh={()=>{}}/>)
 const log=screen.getByRole('log')
 for(const i of [1,2,3])expect(log.textContent).toContain(`Reading ${i}`)
 expect(screen.queryByText('Earlier discussion')).toBeNull()
})
