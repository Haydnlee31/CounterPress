import {cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {AnalystConversation} from './AnalystRoom'
import type {Analysis} from './data'
afterEach(cleanup)
const round:Analysis={snapshot_id:'saved',cutoff:{period:1,elapsed_ms:600000},mode:'discussion',status:'complete',readings:[],summary:null,messages:[{id:'one',role:'control',text:'The recovery created space behind the midfield.',reply_to:null,relation:'observation',metric_ids:[],evidence_ids:[]}]}
const props={rounds:[],pending:false,failed:false,available:true,playing:true,analysis:null,refresh:vi.fn()}
it('replaces watching with failure and lets the viewer retry without hiding an existing contribution',()=>{
 const refresh=vi.fn()
 const {rerender}=render(<AnalystConversation {...props} failed refresh={refresh}/> )
 expect(screen.queryByText('The analysts are watching.')).toBeNull()
 expect(screen.getByText('Discussion unavailable')).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'Try again'}));expect(refresh).toHaveBeenCalledOnce()
 rerender(<AnalystConversation {...props} failed rounds={[round]} refresh={refresh}/> )
 expect(screen.getByRole('log').textContent).toContain(round.messages![0].text)
 expect(screen.queryByText('Following the match')).toBeNull()
 rerender(<AnalystConversation {...props} failed pending analysis={{...round,status:'unavailable'}}/> )
 expect(screen.getByText('Analysts discussing')).toBeTruthy()
 expect(screen.queryByText('Discussion unavailable')).toBeNull()
 expect(screen.queryByRole('button',{name:'Try again'})).toBeNull()
})
it.each(['unavailable','hourly_limit','daily_limit','budget_limit','disabled'])('does not claim to be watching after a %s response',status=>{
 render(<AnalystConversation {...props} analysis={{...round,status,messages:[]}}/> )
 expect(screen.queryByText('The analysts are watching.')).toBeNull()
 expect(screen.queryByText('Following the match')).toBeNull()
})
it('does not ask someone already playing to start the replay',()=>{
 render(<AnalystConversation {...props}/> )
 expect(screen.queryByText(/^Start the replay/)).toBeNull()
})

it.each(['hourly_limit','daily_limit','budget_limit','disabled'])('keeps the %s status visible after the snapshot expires',discussionStatus=>{
 render(<AnalystConversation {...props} discussionStatus={discussionStatus}/> )
 expect(screen.queryByText('The analysts are watching.')).toBeNull()
 expect(screen.queryByText('Following the match')).toBeNull()
})
