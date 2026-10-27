import {act,cleanup,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {FootieLoader} from './FootieLoader'
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})
it('keeps the actual pending operation readable without initiating requests',()=>{
 const fetch=vi.fn();vi.stubGlobal('fetch',fetch)
 const {container}=render(<FootieLoader label="Opening Match Centre…"/>)
 expect(screen.getByRole('status').textContent).toContain('Opening Match Centre…')
 expect(container.querySelector('.footie-mascot')?.getAttribute('aria-hidden')).toBe('true')
 expect(fetch).not.toHaveBeenCalled()
})
it('pauses offscreen and background motion and disconnects its observer on unmount',()=>{
 let notify:(entries:{isIntersecting:boolean}[])=>void=()=>{}
 const disconnect=vi.fn()
 vi.stubGlobal('IntersectionObserver',class {constructor(callback:typeof notify){notify=callback}observe(){}disconnect=disconnect})
 const hidden=vi.spyOn(document,'hidden','get').mockReturnValue(false)
 const {unmount}=render(<FootieLoader compact label="Opening statistics…"/>)
 const loader=screen.getByRole('status')
 act(()=>notify([{isIntersecting:false}]))
 expect(loader.getAttribute('data-paused')).toBe('true')
 act(()=>notify([{isIntersecting:true}]))
 expect(loader.getAttribute('data-paused')).toBe('false')
 hidden.mockReturnValue(true);act(()=>document.dispatchEvent(new Event('visibilitychange')))
 expect(loader.getAttribute('data-paused')).toBe('true')
 unmount();expect(disconnect).toHaveBeenCalledTimes(1)
})
