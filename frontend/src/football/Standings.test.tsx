import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Standings} from './Standings'
import type {World} from './data'
const world={throughDate:'2026-10-19',catalog:{clubs:[{club_id:'redhaven',name:'Redhaven',short_name:'RH',featured:true,primary_color:'#b23d2d'}],seasons:['2026-27','2025-26']}} as World
const row={rank:1,club_id:'redhaven',played:8,wins:6,draws:1,losses:1,goals_for:20,goals_against:9,points:19}
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('shows recorded standings and refetches a different season without retaining the old table',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify({competition:'CounterPress League',season:url.endsWith('2025-26')?'2025-26':'2026-27',items:[{...row,points:url.endsWith('2025-26')?42:19}],match_ids:[]}))))
 render(<Standings world={world}/>);await screen.findByText('19 points · 8 played')
 expect(screen.getByRole('table')).toBeTruthy();expect(screen.getByText('+11')).toBeTruthy()
 fireEvent.change(screen.getByLabelText('Standings season'),{target:{value:'2025-26'}})
 await screen.findByText('42 points · 8 played');expect(screen.queryByText('19 points · 8 played')).toBeNull()
 await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2))
})
