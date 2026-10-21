import {cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it} from 'vitest'
import {PitchIdentity,PitchFaceToggle,usePitchFaces} from './PitchIdentity'
afterEach(()=>{cleanup();localStorage.clear()})
it('uses a stable portrait, unique clipping IDs and readable initials on failure',()=>{
 const {container}=render(<svg><PitchIdentity playerId="eb09" name="Rory Ellis" color="gold"/><PitchIdentity playerId="eb09" name="Rory Ellis" color="gold"/></svg>)
 expect(container.querySelectorAll('image')).toHaveLength(2)
 const ids=[...container.querySelectorAll('clipPath')].map(e=>e.id);expect(new Set(ids).size).toBe(2)
 fireEvent.error(container.querySelector('image')!)
 expect(screen.getByText('RE')).toBeTruthy()
})
it('shares the faces preference between mounted pitches without hiding players',()=>{
 function Pitch(){const [faces,setFaces]=usePitchFaces();return <><PitchFaceToggle faces={faces} change={setFaces}/><svg><PitchIdentity playerId="eb09" name="Rory Ellis" color="gold" faces={faces}/></svg></>}
 const {container}=render(<><Pitch/><Pitch/></>)
 fireEvent.change(screen.getAllByLabelText('Pitch player display')[0],{target:{value:'initials'}})
 expect(container.querySelectorAll('image')).toHaveLength(0);expect(screen.getAllByText('RE')).toHaveLength(2)
 expect(localStorage.getItem('footie.pitch.faces.v1')).toBe('off')
})
