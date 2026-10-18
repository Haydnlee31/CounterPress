import { afterEach, expect, it, vi } from 'vitest'
import { giSessionKey, readGIWorkspace, saveGIWorkspace } from './session'
afterEach(()=>{sessionStorage.clear();vi.restoreAllMocks()})
it('restores the independent full-match workspace',()=>{
 const value={filter:'shots' as const,team:'9598',player:'wyscout-player-123',period:'2',selected:'wyscout-456',map:true}
 saveGIWorkspace(value);expect(readGIWorkspace()).toEqual(value)
})
it('sanitizes invalid or stale navigation fields',()=>{
 sessionStorage.setItem(giSessionKey,JSON.stringify({filter:'random',team:'bad',period:5,player:'eb04',selected:'x',map:'true'}))
 expect(readGIWorkspace()).toEqual({filter:'key',team:'',player:'',period:'',selected:null,map:false})
})
it('continues when browser storage is unavailable',()=>{
 vi.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw Error()})
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw Error()})
 expect(()=>saveGIWorkspace(readGIWorkspace())).not.toThrow()
})

it('isolates the saved selection for each full match',()=>{
 const saved=readGIWorkspace()
 saveGIWorkspace({...saved,selected:'wyscout-123'},'wyscout-2058007')
 expect(readGIWorkspace('wyscout-2058007').selected).toBe('wyscout-123')
 expect(readGIWorkspace().selected).not.toBe('wyscout-123')
})
it('restores native synthetic IDs only in a synthetic workspace',()=>{
 const id='synthetic-32fe41c5d304ce68d7d9'
 saveGIWorkspace({filter:'key',team:'',player:'eb04',period:'2',selected:'a00005',map:false},id)
 expect(readGIWorkspace(id).player).toBe('eb04')
 expect(readGIWorkspace(id).selected).toBe('a00005')
})
