import {cleanup,render,screen} from '@testing-library/react'
import {afterEach,expect,it} from 'vitest'
import {Badge} from './visuals'
import {ClubCrest} from '../matchday/ClubCrest'
afterEach(cleanup)
it.each(['eastbridge','northport','southbank','redhaven'])('uses the Clubhouse sizing contract for %s, independent of lazy matchday CSS',club_id=>{
 render(<Badge club={{club_id,name:club_id,short_name:'FC',featured:true,primary_color:'#173e33'}}/>)
 const crest=screen.getByRole('img')
 expect(crest.getAttribute('class')).toBe('fh-badge')
 expect(crest.getAttribute('viewBox')).toBe('0 0 80 90')
})
it('keeps existing match scoreboards on their own crest sizing contract',()=>{
 render(<ClubCrest club="eastbridge"/> )
 expect(screen.getByRole('img').getAttribute('class')).toBe('fan-crest')
})
