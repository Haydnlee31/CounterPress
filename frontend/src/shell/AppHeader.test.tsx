import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { AppHeader } from './AppHeader'
afterEach(cleanup)
it('keeps highlight identity in every workspace link and identifies the active route',()=>{
 render(<AppHeader active="explore" story="breakaway"/>)
 expect(screen.getByRole('link',{name:'Highlights'}).getAttribute('href')).toBe('?story=breakaway#highlights')
 expect(screen.getByRole('link',{name:'Highlights'}).getAttribute('aria-current')).toBe('page')
 expect(screen.getByRole('link',{name:'Match Centre'}).getAttribute('href')).toBe('?story=breakaway#gi')
 expect(screen.queryByRole('link',{name:'Explore data'})).toBeNull()
})
it('keeps the match library focused on full matches and closes with Escape',()=>{
 const {container}=render(<AppHeader active="gi"/>)
 const library=container.querySelector('.cp-library') as HTMLDetailsElement
 library.open=true
 expect(screen.getByText('Full-match archive')).toBeTruthy()
 expect(screen.queryByText('Last-second turnaround')).toBeNull()
 expect(screen.getByRole('link',{name:/Watch the full match/}).getAttribute('href')).toContain('&view=watch#gi')
 expect(screen.getAllByRole('link').filter(link=>link.closest('nav')).map(link=>link.textContent)).toEqual(['Match Centre','Highlights','Clubhouse','Footie'])
 expect(screen.getByRole('link',{name:/Eastbridge 4 – 2 Northport/}).getAttribute('href')).toContain('#gi')
 fireEvent.keyDown(library,{key:'Escape'})
 expect(library.open).toBe(false)
 expect(document.activeElement).toBe(library.querySelector('summary'))
})
it('rejects an unknown highlight when composing navigation links',()=>{
 render(<AppHeader active="matchday" story="not-a-story"/>)
 expect(screen.getByRole('link',{name:'Highlights'}).getAttribute('href')).toBe('?story=last-gasp#highlights')
})
it('avoids repeating a match library above the Matchday highlight gallery',()=>{
 render(<AppHeader active="matchday"/>)
 expect(screen.queryByText('Full-match archive')).toBeNull()
 expect(screen.queryByText('Watch the full match')).toBeNull()
 expect(screen.queryByText('Match library')).toBeNull()
})
