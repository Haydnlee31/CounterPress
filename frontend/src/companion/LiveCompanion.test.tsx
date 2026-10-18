import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { Event } from '../types'
import { answer, completedEvents, cue } from './evidence'
import { LiveCompanion } from './LiveCompanion'

const pass:Event={schema_version:'1.0',match_id:'test',event_id:'pass',revision:1,source_delivery_sequence:1,occurrence_order:1,
  occurred_at:{period:2,elapsed_ms:1000},available_at:{period:2,elapsed_ms:1000},actor:{team_id:'eastbridge',player_id:'eb08'},position:{x:72,y:12},
  action:{kind:'pass',outcome:'completed',end_position:{x:90,y:34},recipient:{team_id:'eastbridge',player_id:'eb09'}}}
const goal:Event={...pass,event_id:'goal',occurrence_order:2,occurred_at:{period:2,elapsed_ms:4000},available_at:{period:2,elapsed_ms:4000},
  actor:{team_id:'eastbridge',player_id:'eb09'},action:{kind:'shot',outcome:'goal',end_position:{x:105,y:34}}}
afterEach(()=>{cleanup();vi.unstubAllGlobals()})

test('pending actions never announce their outcome or recipient',()=>{
  expect(cue(pass,false,false)).not.toContain('Rory')
  expect(cue(goal,false,false)).not.toContain('home')
  expect(completedEvents([pass,goal],1,false)).toEqual([pass])
  expect(answer('numbers',completedEvents([pass,goal],1,false),false).text).toContain('0 shots')
  expect(answer('happened',[],false).evidence).toEqual([])
})
test('evidence respects availability, revisions and match isolation',()=>{
  const correction={...pass,revision:2,available_at:{period:2 as const,elapsed_ms:5000},action:{...pass.action,outcome:'incomplete'}}
  expect(completedEvents([pass,correction,goal],2,true)).toEqual([pass,goal])
  const after={...goal,event_id:'after',occurrence_order:3,occurred_at:{period:2 as const,elapsed_ms:6000},available_at:{period:2 as const,elapsed_ms:6000}}
  expect(completedEvents([pass,correction,goal,after],3,true)[0]).toEqual(correction)
  expect(completedEvents([{...pass,match_id:'other'},goal],1,true)).toEqual([goal])
})
test('build-up stops at the last recovery and at half/time boundaries',()=>{
  const recovery={...pass,event_id:'recovery',action:{kind:'recovery'}}
  expect(answer('buildup',[pass,recovery,goal],false).evidence).toEqual([recovery,goal])
  expect(answer('buildup',[{...pass,occurred_at:{period:1,elapsed_ms:1000}},goal],false).evidence).toEqual([goal])
  expect(answer('buildup',[pass,{...goal,occurred_at:{period:2,elapsed_ms:40000}}],false).evidence).toHaveLength(1)
})
test('answers disappear when seeking backwards or revising the source',()=>{
  const props={events:[pass,goal],index:1,resolved:true,playing:false,finished:false,language:'en'}
  const ui=render(<LiveCompanion {...props}/>)
  fireEvent.click(screen.getByRole('button',{name:/Follow the play/}))
  fireEvent.click(screen.getByRole('button',{name:'What just happened?'}))
  expect(screen.getByText(/Actions behind this answer/)).toBeTruthy()
  ui.rerender(<LiveCompanion {...props} index={0} resolved={false}/>)
  expect(screen.queryByText(/Actions behind this answer/)).toBeNull()
  expect(screen.queryByText(/fires it home/)).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'What just happened?'}))
  expect(screen.getByText(/still unfolding/)).toBeTruthy()
  ui.rerender(<LiveCompanion {...props} events={[{...pass,revision:2},goal]}/>)
  expect(screen.queryByText(/still unfolding/)).toBeNull()
})
function mockSpeech(){
  const synth={speak:vi.fn(),cancel:vi.fn(),getVoices:()=>[]}
  vi.stubGlobal('speechSynthesis',synth)
  vi.stubGlobal('SpeechSynthesisUtterance',class {text:string;constructor(text:string){this.text=text}})
  return synth
}
test('speech is opt-in, replaces queued action, cancels on pause and unmount',()=>{
  const synth=mockSpeech()
  const props={events:[pass,goal],index:0,resolved:true,playing:true,finished:false,language:'en'}
  const ui=render(<LiveCompanion {...props}/>)
  expect(synth.speak).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:/Listen/}))
  expect(synth.speak).toHaveBeenCalledTimes(1)
  ui.rerender(<LiveCompanion {...props} index={1} resolved={false}/>)
  expect(synth.speak).toHaveBeenCalledTimes(1)
  ui.rerender(<LiveCompanion {...props} index={1}/>)
  expect(synth.speak.mock.calls.at(-1)![0].text).toContain('fires it home')
  const cancels=synth.cancel.mock.calls.length
  ui.rerender(<LiveCompanion {...props} index={1} playing={false}/>)
  expect(synth.cancel.mock.calls.length).toBeGreaterThan(cancels)
  ui.unmount()
  expect(synth.cancel.mock.calls.length).toBeGreaterThan(cancels+1)
})
test('a natural ending finishes its last cue, but seeking cancels it',()=>{
  const synth=mockSpeech()
  const props={events:[pass,goal],index:1,resolved:true,playing:true,finished:false,language:'en'}
  const ui=render(<LiveCompanion {...props}/>)
  fireEvent.click(screen.getByRole('button',{name:/Listen/}))
  const cancels=synth.cancel.mock.calls.length
  ui.rerender(<LiveCompanion {...props} playing={false} finished/>)
  expect(synth.cancel).toHaveBeenCalledTimes(cancels)
  ui.rerender(<LiveCompanion {...props} playing={false} index={0} resolved={false}/>)
  expect(synth.cancel.mock.calls.length).toBeGreaterThan(cancels)
})
test('speech failure leaves text and questions usable',()=>{
  const synth=mockSpeech()
  render(<LiveCompanion events={[pass]} index={0} resolved playing finished={false} language="en"/>)
  fireEvent.click(screen.getByRole('button',{name:/Listen/}))
  fireEvent.click(screen.getByRole('button',{name:/Follow the play/}))
  fireEvent.click(screen.getByRole('button',{name:'Show me the numbers'}))
  expect(screen.getByText(/1 of 1 passes completed/)).toBeTruthy()
  act(()=>synth.speak.mock.calls[0][0].onerror({error:'synthesis-failed'}))
  expect(screen.getByText(/Voice is unavailable/)).toBeTruthy()
  expect(screen.getByText(/1 of 1 passes completed/)).toBeTruthy()
  expect(screen.getByRole('button',{name:/Listen/}).getAttribute('aria-pressed')).toBe('false')
})
