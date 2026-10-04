/**
 * StewardList — column 2 of the stewards surface.
 *
 * What is asserted, and what deliberately is not: the roster is queried by STEWARD
 * NAME (data the test supplies) and by test id, never by rendered English. The
 * `apps.issueRadar.views.stewards.*` catalog keys are populated in a separate change,
 * so an assertion on copy here would be an assertion about the state of the
 * translation files rather than about this component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Steward } from '../apps/issue-radar/api'

const ctx = { value: {} as Record<string, unknown> }
vi.mock('../apps/issue-radar/context', () => ({
  useIssueRadar: () => ctx.value,
}))

const StewardList = (await import('../apps/issue-radar/components/StewardList')).default

const setStewardView = vi.fn()
const setStewardFilter = vi.fn()
const onCreate = vi.fn()

/** A steward record with only the fields this list reads; `status` is the field the
 * stewards ROUTE adds on top of the store record (see `_steward_status` in
 * `steward_routes.py`), which is why it is cast rather than declared. */
const steward = (over: Partial<Steward> & { status?: string }): Steward => ({
  schema: 1,
  id: 'c1',
  name: 'Andromeda',
  avatar_seed: 'Andromeda',
  avatar_variant: null,
  agent: 'junction',
  model: '',
  extra_prompt: '',
  labels: [],
  auto_resolve_conflicts: false,
  auto_merge: false,
  unattended: false,
  max_open: 3,
  worktree_root: '',
  slot_key: '',
  enabled: true,
  paused_reason: '',
  created_at: '2026-08-01T00:00:00Z',
  retired_at: null,
  ...over,
} as Steward)

const ROSTER = [
  steward({ id: 'c1', name: 'Andromeda', status: 'working', labels: ['area: dashboard'] }),
  steward({ id: 'c2', name: 'Whirlpool', status: 'idle' }),
  steward({ id: 'c3', name: 'Triangulum', status: 'paused', enabled: false, paused_reason: 'Paused by you' }),
]

beforeEach(() => {
  vi.clearAllMocks()
  ctx.value = {
    stewards: ROSTER,
    stewardsLoading: false,
    stewardsError: null,
    stewardView: { kind: 'steward', id: 'c1' },
    setStewardView,
    // Selecting a row also drills into the detail on a narrow viewport, so the
    // fake context has to carry the pane state the real one hosts.
    listDetail: { isMobile: false, showList: true, showDetail: true, openDetail: vi.fn(), closeDetail: vi.fn() },
    stewardFilter: 'all',
    setStewardFilter,
    // The sort controls live in the rail; this column only applies the result.
    stewardSortKey: 'status',
    stewardSortDir: 'asc',
  }
})

describe('StewardList', () => {
  it('marks the selected steward as current, not merely styled', () => {
    // aria-current is what a screen reader announces; a background colour alone
    // leaves the selection invisible to one.
    ctx.value = { ...ctx.value, stewardView: { kind: 'steward', id: 'c2' } }
    render(<StewardList onCreate={onCreate} />)
    expect(screen.getByTestId('steward-row-c2').getAttribute('aria-current')).toBe('page')
    expect(screen.getByTestId('steward-row-c1').getAttribute('aria-current')).toBeNull()
  })

  it('selecting a row addresses that steward by id', async () => {
    render(<StewardList onCreate={onCreate} />)
    await userEvent.click(screen.getByText('Whirlpool'))
    expect(setStewardView).toHaveBeenCalledWith({ kind: 'steward', id: 'c2' })
  })

  it('offers the create control above the roster, and only reports the intent', async () => {
    // This column owns the ONE way to create a steward; the dialog itself lives in
    // Workspace, so the button must not try to open anything itself.
    render(<StewardList onCreate={onCreate} />)
    const create = screen.getByTestId('steward-create')
    const first = screen.getByTestId('steward-row-c1')
    // DOCUMENT_POSITION_FOLLOWING — the first steward comes after the control.
    expect(create.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await userEvent.click(create)
    expect(onCreate).toHaveBeenCalledTimes(1)
    expect(setStewardView).not.toHaveBeenCalled()
  })

  it('keeps the create control reachable under a filter that hides every row', () => {
    // Hiring is how an empty or fully-filtered roster is recovered from, so it
    // cannot be filtered away with the rows.
    ctx.value = { ...ctx.value, stewards: [ROSTER[0]], stewardFilter: 'paused' }
    const { unmount } = render(<StewardList onCreate={onCreate} />)
    expect(screen.queryByTestId('steward-row-c1')).toBeNull()
    expect(screen.getByTestId('steward-create')).toBeTruthy()
    unmount()

    // And on a repo with no stewards at all, where it is the only thing to do.
    ctx.value = { ...ctx.value, stewards: [], stewardFilter: 'all' }
    render(<StewardList onCreate={onCreate} />)
    expect(screen.getByTestId('steward-create')).toBeTruthy()
  })

  it('orders the roster by the active sort and flips with its direction', () => {
    // The CONTROLS moved to the rail, but applying the order is still this
    // column's job. Ascending `status` is the activity order — a steward with work in
    // flight leads, and a paused one sinks.
    ctx.value = { ...ctx.value, stewardSortKey: 'status', stewardSortDir: 'asc' }
    const { unmount } = render(<StewardList onCreate={onCreate} />)
    const idsOf = () => screen.getAllByTestId(/^steward-row-c/).map((n) => n.getAttribute('data-testid'))
    const asc = idsOf()
    unmount()

    ctx.value = { ...ctx.value, stewardSortDir: 'desc' }
    render(<StewardList onCreate={onCreate} />)
    expect(idsOf()).toEqual([...asc].reverse())
  })

  it('the Paused filter reads the steward record, so its rows match its count', () => {
    // `paused` is derived from enabled/retired_at — the backend's own flag — rather
    // than from the single-valued `status`, which is what keeps the chip's tally and
    // the rows it shows in agreement.
    ctx.value = { ...ctx.value, stewardFilter: 'paused' }
    render(<StewardList onCreate={onCreate} />)
    expect(screen.getByTestId('steward-row-c3')).toBeTruthy()
    expect(screen.queryByTestId('steward-row-c1')).toBeNull()
    expect(screen.queryByTestId('steward-row-c2')).toBeNull()
  })

  it('a paused steward shows its reason rather than a generic label', () => {
    render(<StewardList onCreate={onCreate} />)
    expect(screen.getByText('Paused by you')).toBeTruthy()
  })

  it('empties to the roster empty state, and to a filtered one when rows are hidden', () => {
    const { unmount } = render(<StewardList onCreate={onCreate} />)
    expect(screen.queryByTestId('steward-list-empty')).toBeNull()
    unmount()

    // Nothing matches the filter, but the repo does have stewards.
    ctx.value = { ...ctx.value, stewards: [ROSTER[0]], stewardFilter: 'paused' }
    const filtered = render(<StewardList onCreate={onCreate} />)
    expect(screen.getByTestId('steward-list-empty')).toBeTruthy()
    const filteredTitle = screen.getByTestId('steward-list-empty-title').textContent
    filtered.unmount()

    // No stewards at all — a different message, since there is nothing to unfilter.
    ctx.value = { ...ctx.value, stewards: [], stewardFilter: 'all' }
    render(<StewardList onCreate={onCreate} />)
    expect(screen.getByTestId('steward-list-empty-title').textContent).not.toBe(filteredTitle)
  })

  it('surfaces a load failure instead of rendering an empty roster', () => {
    ctx.value = { ...ctx.value, stewards: [], stewardsError: new Error('steward store unreadable') }
    render(<StewardList onCreate={onCreate} />)
    expect(screen.getByText('steward store unreadable')).toBeTruthy()
    // An error is not an empty roster: offering the "you have no stewards yet"
    // pitch here would invite creating one when the store simply could not be read.
    expect(screen.queryByTestId('steward-list-empty')).toBeNull()
  })
})
