import {cleanup,render,screen} from '@testing-library/react'
import {expect,test} from 'vitest'
import {AppHeader} from '../shell/AppHeader'
import {FULL_MATCH} from './playback'
test('a direct full-match link keeps navigation attached to the playing match',()=>{
 const previous=window.location.href
 try{
  window.history.replaceState({},'', '/#live')
  render(<AppHeader active="matchday" fullMatch/>)
  expect(screen.getByRole('link',{name:'Match Centre',exact:true}).getAttribute('href')).toContain(`match=${FULL_MATCH}#gi`)
 }finally{cleanup();window.history.replaceState({},'',previous)}
})
