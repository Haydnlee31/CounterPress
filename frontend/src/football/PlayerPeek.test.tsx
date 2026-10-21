import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it} from 'vitest'
import {peekPosition,usePlayerPeek} from './PlayerPeek'
const players=[{player_id:'eb09',name:'Rory Ellis',role:'FW' as const,number:9}]
afterEach(cleanup)
function Pitch({unknown=false,enabled=true,frame=0}:{unknown?:boolean;enabled?:boolean;frame?:number}){const peek=usePlayerPeek(players,enabled,frame);return <><svg><g data-testid="marker" tabIndex={0} {...peek.bind(unknown?'extra':'eb09',unknown?'Eastbridge substitute 1':'Rory Ellis')}><circle r="5"/></g></svg>{peek.card}</>}
it('uses registered details on keyboard focus and dismisses on Escape',()=>{
 render(<Pitch/>);const marker=screen.getByTestId('marker');fireEvent.focus(marker)
 expect(screen.getByRole('tooltip').textContent).toContain('Rory Ellis');expect(screen.getByRole('tooltip').textContent).toContain('Forward');expect(screen.getByRole('tooltip').textContent).toContain('#9')
 expect(marker.getAttribute('aria-describedby')).toBe(screen.getByRole('tooltip').id)
 expect(fireEvent(window,new KeyboardEvent('keydown',{key:'Escape',cancelable:true,bubbles:true}))).toBe(false);expect(screen.queryByRole('tooltip')).toBeNull()
})
it('never infers a substitute shirt or position from its alias',()=>{
 render(<Pitch unknown/>);fireEvent.focus(screen.getByTestId('marker'))
 expect(screen.getByText('Eastbridge substitute 1')).toBeTruthy();expect(screen.getByRole('tooltip').textContent).toContain('Position unavailable');expect(screen.getByRole('tooltip').textContent).toContain('Shirt unavailable')
})
it('dismisses on outside interaction and scrolling',()=>{
 render(<Pitch/>);fireEvent.focus(screen.getByTestId('marker'));fireEvent.pointerDown(document.body);expect(screen.queryByRole('tooltip')).toBeNull()
 fireEvent.focus(screen.getByTestId('marker'));fireEvent.scroll(document);expect(screen.queryByRole('tooltip')).toBeNull()
})
it('allows the pointer to enter the card without it disappearing',async()=>{
 render(<Pitch/>);fireEvent.focus(screen.getByTestId('marker'));fireEvent.pointerLeave(screen.getByTestId('marker'));fireEvent.pointerEnter(screen.getByRole('tooltip'))
 await new Promise(resolve=>setTimeout(resolve,180));expect(screen.getByRole('tooltip')).toBeTruthy()
 fireEvent.pointerLeave(screen.getByRole('tooltip'));await waitFor(()=>expect(screen.queryByRole('tooltip')).toBeNull())
})
it('flips above and left at viewport edges with a safe margin',()=>{
 expect(peekPosition(350,790,240,72,{width:360,height:800})).toEqual({left:94,top:702})
 expect(peekPosition(0,0,240,72,{width:360,height:800})).toEqual({left:16,top:16})
 const p=peekPosition(5,790,240,72,{width:360,height:800});expect(p.left).toBeGreaterThanOrEqual(12);expect(p.top+72).toBeLessThanOrEqual(788)
})

it('hides cards for a disabled surface and clears them on explicit context changes',()=>{
 const {rerender}=render(<Pitch enabled={false}/>);fireEvent.focus(screen.getByTestId('marker'));expect(screen.queryByRole('tooltip')).toBeNull()
 rerender(<Pitch/>);fireEvent.focus(screen.getByTestId('marker'));expect(screen.getByRole('tooltip')).toBeTruthy()
 rerender(<Pitch enabled={false}/>);expect(screen.queryByRole('tooltip')).toBeNull()
 rerender(<Pitch/>);fireEvent.focus(screen.getByTestId('marker'));expect(screen.getByRole('tooltip')).toBeTruthy()
 rerender(<Pitch frame={1}/>);expect(screen.queryByRole('tooltip')).toBeNull()
})
it('dismisses hover when animation moves the marker away from a stationary pointer',async()=>{
 const previous=document.elementFromPoint
 document.elementFromPoint=()=>document.body
 try{
  render(<Pitch/>);fireEvent.pointerEnter(screen.getByTestId('marker'),{clientX:20,clientY:20})
  expect(screen.getByRole('tooltip')).toBeTruthy()
  await waitFor(()=>expect(screen.queryByRole('tooltip')).toBeNull())
 }finally{document.elementFromPoint=previous}
})
