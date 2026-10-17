import {readFileSync} from 'node:fs'
import {act,cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import type {Event} from '../types'
import {sequenceScene,scoreAtPlayhead} from './pitchScene'
import {replayShapes} from './replayGallery'
import {MatchPitch} from './MatchPitch'
const load=(name:string)=>JSON.parse(readFileSync(`../fixtures/showcases/${name}.json`,'utf8')) as {events:Event[]}
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})
for(const name of ['last_gasp','one_touch','breakaway']) test(`${name}: all identities persist, boundaries join, touches meet ball and nothing leaves pitch`,()=>{
 const {events}=load(name), original=JSON.stringify(events)
 for(let i=0;i<events.length;i++){
  for(const progress of [0,.2,.5,.8,1]){
   const scene=sequenceScene(events,i,progress)
   expect(scene.players).toHaveLength(22)
   expect(new Set(scene.players.map(p=>p.player_id)).size).toBe(22)
   expect(scene.players.every(p=>Number.isFinite(p.x)&&p.x>=0&&p.x<=105&&p.y>=0&&p.y<=68)).toBe(true)
   if(progress===0 || events[i].action.kind==='carry') expect(scene.players.find(p=>p.player_id===events[i].actor.player_id)).toMatchObject(scene.ball)
  }
  if(i+1<events.length){
   const before=sequenceScene(events,i,1),after=sequenceScene(events,i+1,0)
   expect(before.ball).toEqual(after.ball)
   for(const p of before.players){const next=after.players.find(v=>v.player_id===p.player_id)!;expect(Math.hypot(p.x-next.x,p.y-next.y)).toBeLessThan(.0001)}
  }
 }
 expect(JSON.stringify(events)).toBe(original)
})
test('authored off-ball maps contain two bounded positions for every player on each side',()=>{
 for(const map of Object.values(replayShapes)) for(const team of Object.values(map)){
  expect(team).toHaveLength(2)
  for(const frame of team){expect(frame).toHaveLength(11);for(const [x,y] of frame){expect(x>=0&&x<=105&&y>=0&&y<=68).toBe(true)}}
 }
})
test('scrubbing and restart keep score and goal announcement in step with the shot',()=>{
 const {events}=load('one_touch'),head=vi.fn()
 const ui=render(<MatchPitch events={events} fromStart onPlayhead={head}/>)
 const slider=screen.getByRole('slider',{name:'Replay position'})
 fireEvent.change(slider,{target:{value:'450'}})
 expect(ui.container.querySelector('.fan-goal-banner')).toBeNull()
 expect(ui.container.querySelector('.fan-commentary')!.textContent).not.toContain('fires it home')
 expect(scoreAtPlayhead({eastbridge:3,northport:0},events,4,false).eastbridge).toBe(2)
 fireEvent.change(slider,{target:{value:'480'}})
 expect(ui.container.querySelector('.fan-goal-banner')).toBeTruthy()
 expect(head).toHaveBeenLastCalledWith({index:4,resolved:true})
 fireEvent.click(screen.getByRole('button',{name:/Restart/}))
 expect((slider as HTMLInputElement).value).toBe('0')
 expect(head).toHaveBeenLastCalledWith({index:0,resolved:false})
})
test('pausing the last shot resumes it instead of restarting the sequence',()=>{
 let callback:FrameRequestCallback=()=>{}
 vi.stubGlobal('requestAnimationFrame',vi.fn((f:FrameRequestCallback)=>{callback=f;return 1}));vi.stubGlobal('cancelAnimationFrame',vi.fn())
 vi.spyOn(performance,'now').mockReturnValue(0)
 const {events}=load('one_touch');render(<MatchPitch events={events} fromStart/>)
 fireEvent.change(screen.getByRole('slider',{name:'Replay position'}),{target:{value:'420'}})
 fireEvent.click(screen.getByRole('button',{name:/Play highlight/}));act(()=>callback(100))
 fireEvent.click(screen.getByRole('button',{name:/Pause play/}))
 const paused=(screen.getByRole('slider',{name:'Replay position'}) as HTMLInputElement).value
 fireEvent.click(screen.getByRole('button',{name:/Play highlight/}))
 expect((screen.getByRole('slider',{name:'Replay position'}) as HTMLInputElement).value).toBe(paused)
 expect(screen.getByText('5 / 5')).toBeTruthy()
})
test('reconstructed player trajectories stay below 12 m/s at normal playback speed',()=>{
 for(const name of ['last_gasp','one_touch','breakaway']){
  const {events}=load(name)
  for(let i=0;i<events.length;i++){
   const seconds=Math.max(1000,Math.min(10000,(events[i+1]?.occurred_at.elapsed_ms ?? events[i].occurred_at.elapsed_ms+2500)-events[i].occurred_at.elapsed_ms))/1000
   let previous=sequenceScene(events,i,0)
   for(let step=1;step<=20;step++){
    const next=sequenceScene(events,i,step/20)
    for(const p of previous.players){const q=next.players.find(v=>v.player_id===p.player_id)!;expect(Math.hypot(p.x-q.x,p.y-q.y)/(seconds/20),`${name}: ${p.player_id} action ${i}`).toBeLessThan(12)}
    previous=next
   }
  }
 }
})

test('turnaround attackers start outside the penalty area and run upfield instead of waiting at their future touch',()=>{
 const {events}=load('last_gasp'), first=sequenceScene(events,0,0)
 for(const p of first.players.filter(p=>p.number!==1&&p.player_id!=='np08')) expect(p.x).toBeGreaterThanOrEqual(21)
 for(const id of ['eb06','eb07','eb09']) expect(first.players.find(p=>p.player_id===id)!.x).toBeLessThan(40)
 expect(sequenceScene(events,events.length-1,0).players.find(p=>p.player_id==='eb09')).toMatchObject({x:92,y:34})
})
