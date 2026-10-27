import {cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {AskFootie} from './AskFootie'
vi.mock('./Footie',()=>({default:()=> <p>Ready to ask</p>}))
let reduced=false
const cancel=vi.fn(),animate=vi.fn(()=>({cancel}))
beforeEach(()=>{
 reduced=false;animate.mockClear();cancel.mockClear()
 vi.stubGlobal('matchMedia',(query:string)=>({matches:query==='(prefers-reduced-motion: no-preference)'&&!reduced}))
 vi.stubGlobal('fetch',vi.fn())
 Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.open=true}})
 Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(this:HTMLDialogElement){this.open=false}})
 Object.defineProperty(HTMLDialogElement.prototype,'animate',{configurable:true,value:animate})
})
afterEach(()=>{cleanup();delete (HTMLDialogElement.prototype as any).animate;vi.unstubAllGlobals();vi.restoreAllMocks()})
it('animates a pointer-opened drawer without requesting an answer, and restores focus on close',async()=>{
 render(<AskFootie drawer context={{label:'Clubhouse',question:'Who leads the club?'}}/>)
 const opener=screen.getByRole('button',{name:/Ask Footie/});opener.focus();fireEvent.click(opener,{detail:1})
 await screen.findByText('Ready to ask')
 expect(animate).toHaveBeenCalledWith(expect.any(Array),expect.objectContaining({duration:200}))
 expect(fetch).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'Close Footie'}))
 expect(document.activeElement).toBe(opener);expect(cancel).toHaveBeenCalled()
})
it.each([['keyboard',false,0],['reduced motion',true,1]] as const)('opens immediately for %s',async(_label,reduce,detail)=>{
 reduced=reduce;render(<AskFootie drawer context={{label:'Clubhouse',question:'Who leads the club?'}}/>)
 fireEvent.click(screen.getByRole('button',{name:/Ask Footie/}),{detail});await screen.findByText('Ready to ask')
 expect(animate).not.toHaveBeenCalled()
})
