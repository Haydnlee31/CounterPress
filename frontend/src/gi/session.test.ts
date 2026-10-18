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
