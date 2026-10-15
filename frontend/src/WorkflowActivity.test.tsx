import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import { WorkflowActivity } from './WorkflowActivity'

afterEach(cleanup)

test('shows concise actions for a narrowed story', () => {
  render(<WorkflowActivity workflow={{ attempt_id: 'one', status: 'narrowed', actions: [
    { label: 'Requested comparison', elapsed_ms: 100 },
    { label: 'Narrowed to recovery counts', elapsed_ms: 200 },
    { label: 'Prepared explanation', elapsed_ms: 300 },
  ] }}/>)
  expect(screen.getByRole('region', { name: 'Analysis activity' })).toBeTruthy()
  expect(screen.getAllByRole('listitem').map(item => item.textContent)).toEqual([
    'Requested comparison', 'Narrowed to recovery counts', 'Prepared explanation',
  ])
})

test('replaces prior activity with stale fallback and clears it on an earlier snapshot', () => {
  const view = render(<WorkflowActivity workflow={{ attempt_id: 'one', status: 'accepted', actions: [
    { label: 'Prepared explanation', elapsed_ms: 300 },
  ] }}/>)
  view.rerender(<WorkflowActivity workflow={{ attempt_id: 'two', status: 'stale', actions: [
    { label: 'Discarded stale result', elapsed_ms: 400 }, { label: 'Used factual fallback', elapsed_ms: 400 },
  ] }}/>)
  expect(screen.queryByText('Prepared explanation')).toBeNull()
  expect(screen.getByText('Discarded stale result')).toBeTruthy()
  view.rerender(<WorkflowActivity workflow={null}/>)
  expect(screen.queryByRole('region', { name: 'Analysis activity' })).toBeNull()
})
