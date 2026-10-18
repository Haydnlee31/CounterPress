import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { AppHeader } from './AppHeader'
afterEach(cleanup)
it('keeps highlight identity in every workspace link and identifies the active route',()=>{
 render(<AppHeader active="explore" story="breakaway"/>)
 expect(screen.getByRole('link',{name:'Matchday'}).getAttribute('href')).toBe('?story=breakaway#matchday')
 expect(screen.getByRole('link',{name:'Explore data'}).getAttribute('aria-current')).toBe('page')
 expect(screen.getByRole('link',{name:'Match Centre'}).getAttribute('href')).toBe('?story=breakaway#gi')
 expect(document.querySelector('.cp-context-label')?.textContent).toContain('From halfway to goal')
})
it('offers separate highlight and full-match collections and closes with Escape',()=>{
 const {container}=render(<AppHeader active="gi"/>)
 const library=container.querySelector('.cp-library') as HTMLDetailsElement
 library.open=true
 expect(screen.getByText('Full-match archive')).toBeTruthy()
 expect(screen.getByRole('link',{name:/Eastbridge 4 – 2 Northport/}).getAttribute('href')).toContain('#gi')
 fireEvent.keyDown(library,{key:'Escape'})
 expect(library.open).toBe(false)
 expect(document.activeElement).toBe(library.querySelector('summary'))
})
it('rejects an unknown highlight when composing navigation links',()=>{
 render(<AppHeader active="matchday" story="not-a-story"/>)
 expect(screen.getByRole('link',{name:'Explore data'}).getAttribute('href')).toBe('?story=last-gasp#explore')
})
