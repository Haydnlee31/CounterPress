import {act,cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {PlaySequence} from './PlaySequence'
import type {GIEvent,GIPlayer} from './data'
const first:GIEvent={event_id:'a',provider_event_id:null,revision:1,source_order:1,occurrence_order:1,period:1,elapsed_ms:1000,team_id:4418,player_id:'eb09',kind:'Shot',detail:'Shot',outcome:'goal',start:{x:90,y:34},end:{x:105,y:34},goal_for:4418,review:false,tags:[]}
const second={...first,event_id:'b',player_id:'np09',team_id:9598,goal_for:9598,period:2 as const}
const players:GIPlayer[]=[{player_id:'eb09',alias_id:'eb09',team_id:4418,provider_player_id:null},{player_id:'np09',alias_id:'np09',team_id:9598,provider_player_id:null}]
const names=new Map([['eb09','Rory Ellis'],['np09','Henry Blake']])
let tick:FrameRequestCallback|undefined,now=0
beforeEach(()=>{sessionStorage.clear();localStorage.clear();now=0;tick=undefined;vi.spyOn(performance,'now').mockImplementation(()=>now);vi.stubGlobal('requestAnimationFrame',vi.fn(cb=>{tick=cb;return 1}));vi.stubGlobal('cancelAnimationFrame',vi.fn())})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})
const step=()=>act(()=>{now+=100;tick?.(now)})
it('advances exactly once only after an actively playing sequence has finished',()=>{
 const complete=vi.fn();render(<PlaySequence events={[first]} event={first} players={players} names={names} autoAdvance onComplete={complete}/>)
 for(let i=0;i<10;i++)step()
 expect(complete).not.toHaveBeenCalled()
 for(let i=0;i<20;i++)step()
 expect(complete).toHaveBeenCalledTimes(1)
 for(let i=0;i<10;i++)step()
 expect(complete).toHaveBeenCalledTimes(1)
})
it('seeking to the end pauses without unexpectedly auto-advancing',()=>{
 const complete=vi.fn();render(<PlaySequence events={[first]} event={first} players={players} names={names} autoAdvance onComplete={complete}/>)
 fireEvent.change(screen.getByLabelText('Play sequence progress'),{target:{value:'1'}})
 expect(screen.getByRole('button',{name:'Replay sequence'})).toBeTruthy();expect(complete).not.toHaveBeenCalled()
})
it('plays the full match across halves, keeps future goals hidden and supports 2x',()=>{
 render(<PlaySequence events={[first,second]} event={first} players={players} names={names} fullMatch/>)
 expect(screen.getByText('0 – 0')).toBeTruthy()
 fireEvent.change(screen.getByLabelText('Sequence playback speed'),{target:{value:'2'}})
 fireEvent.click(screen.getByRole('button',{name:'Play match'}))
 for(let i=0;i<10;i++)step()
 expect(screen.getByText('1 – 0')).toBeTruthy()
 fireEvent.change(screen.getByLabelText('Full match progress'),{target:{value:'1'}})
 expect(screen.getByText('1 – 1')).toBeTruthy();expect(screen.getByRole('button',{name:'Replay match'})).toBeTruthy()
 expect(sessionStorage.getItem('footie.replay.speed.v1')).toBe('2')
})
it('removes sent-off players at the correct point without revealing a future card',()=>{
 const red={...first,event_id:'red',kind:'Foul',detail:'Foul',outcome:'unknown',goal_for:null,tags:[1701],elapsed_ms:2000,end:null}
 const {container}=render(<PlaySequence events={[first,red,second]} event={first} players={players} names={names} fullMatch/>)
 expect(container.querySelectorAll('.gi-replay-player')).toHaveLength(2)
 fireEvent.change(screen.getByLabelText('Full match progress'),{target:{value:'1'}})
 expect(container.querySelectorAll('.gi-replay-player')).toHaveLength(1)
 expect(screen.getByText('Rory Ellis · Sent off')).toBeTruthy()
})

it('emits completed source clocks, not render frames or future revision availability',()=>{
 const changed=vi.fn(),late={...first,available_ms:4000}
 render(<PlaySequence events={[late,second]} event={late} players={players} names={names} fullMatch hideObservation onPlaybackChange={changed}/>)
 expect(changed).toHaveBeenLastCalledWith({cutoff:{period:1,elapsed_ms:0},playing:false})
 fireEvent.click(screen.getByRole('button',{name:'Play match'}))
 const before=changed.mock.calls.length
 for(let i=0;i<3;i++)step()
 expect(changed.mock.calls.length).toBe(before)
 for(let i=0;i<20;i++)step()
 expect(changed.mock.calls.some(([v])=>v.cutoff.elapsed_ms===4000)).toBe(false)
 fireEvent.change(screen.getByLabelText('Full match progress'),{target:{value:'1'}})
 expect(changed).toHaveBeenLastCalledWith({cutoff:{period:2,elapsed_ms:1000},playing:false})
 fireEvent.change(screen.getByLabelText('Full match progress'),{target:{value:'0'}})
 expect(changed).toHaveBeenLastCalledWith({cutoff:{period:1,elapsed_ms:0},playing:false})
})
