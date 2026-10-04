/**
 * StewardPageView — the assertions that protect the page's meaning rather than its
 * markup.
 *
 * One of them exists because the number alone is misleading: "3 / 3" does not say
 * the steward has STOPPED taking issues, so the at-limit note must appear exactly at
 * the boundary and never below it.
 *
 * The others protect the 24h boundary (a row must not sit on the wrong side of the
 * Earlier divider), `next` being rendered in FULL (the column is a resumable
 * intent, useless truncated), the open-items table matching the ratio beside it,
 * and the pause payload.
 *
 * ## Why no assertion matches English text
 *
 * This view's catalog keys are handed off as a manifest and are not in `en.json`
 * yet, so `t()` currently returns the dotted key. Every copy assertion here
 * compares against `i18next.t(<same key>)`, which is correct BOTH before the
 * catalog lands (both sides are the key) and after (both sides are the English
 * string) — where a hardcoded "at its limit …" would pass in exactly one of those
 * two states.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { renderWithProviders } from './helpers'
import { i18next } from '../i18n'

const api = {
  steward: vi.fn(),
  setStewardPaused: vi.fn(),
}

// Only `issueRadarApi` is stubbed: `TERMINAL_PHASES` / `EDITING_PHASES` /
// `countsTowardOpen` are the REAL exports, because the view's whole contract is
// that it classifies phases through them. Re-declaring them in the mock would let
// the test agree with a view that had drifted from `steward_store.py`.
vi.mock('../apps/issue-radar/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../apps/issue-radar/api')>()),
  issueRadarApi: api,
}))

const ctx = { value: {} as Record<string, unknown> }
vi.mock('../apps/issue-radar/context', () => ({
  useIssueRadar: () => ctx.value,
}))

const StewardPageView = (await import('../apps/issue-radar/views/StewardPageView')).default

/** The instant every fixture stamp is measured from. Frozen so the 24h boundary
 *  is a fact of the test, not of the clock it ran on. */
const NOW = new Date('2026-08-09T12:00:00Z')
const HOUR = 3_600_000

/** An ISO stamp `hours` before NOW. */
function ago(hours: number): string {
  return new Date(NOW.getTime() - hours * HOUR).toISOString()
}

const KEY = 'apps.issueRadar.views.stewards.page'
/** The rendered form of a key — the key itself until the manifest lands in the
 *  catalogs, the English string after. Either way it is what the view renders. */
function copy(leaf: string, vars?: Record<string, unknown>): string {
  return i18next.t(`${KEY}.${leaf}`, vars ?? {}) as string
}

function steward(over: Record<string, unknown> = {}) {
  return {
    schema: 1,
    id: 'steward-andromeda',
    name: 'Andromeda',
    avatar_seed: 'steward-andromeda',
    avatar_variant: 2,
    agent: 'junction',
    model: 'claude-opus-5',
    extra_prompt: 'Prefer the smallest reversible fix.',
    labels: ['area: dashboard'],
    auto_resolve_conflicts: false,
    auto_merge: false,
    unattended: false,
    max_open: 3,
    worktree_root: '/tmp/stewards',
    slot_key: 'chat-andromeda',
    enabled: true,
    paused_reason: '',
    created_at: ago(72),
    retired_at: null,
    ...over,
  }
}

const LONG_NEXT =
  'Add the Windows branch to _safe_chmod — the regression test already fails, so '
  + 'implement the guard and re-run only that test before touching CI again.'

function item(number: number, phase: string, over: Record<string, unknown> = {}) {
  return {
    schema: 1,
    steward_id: 'steward-andromeda',
    owner: 'o',
    repo: 'r',
    number,
    phase,
    outcome: null,
    decision: '',
    why: '',
    next: LONG_NEXT,
    tried: [],
    worktree: '',
    branch: '',
    base_sha: '',
    pr_number: null,
    ci_state: {},
    claim_comment_id: null,
    labels_applied: [],
    claimed_at: ago(30),
    last_progress_at: ago(1),
    finished_at: null,
    ...over,
  }
}

function event(id: string, hoursAgo: number, over: Record<string, unknown> = {}) {
  return {
    id,
    ts: ago(hoursAgo),
    steward_id: 'steward-andromeda',
    number: 2251,
    kind: 'ci',
    text: `CI round 3 — 41/47 green (${id})`,
    ...over,
  }
}

/** The default page payload: 3 open items against max_open 3, plus one finished
 *  item that must stay out of the open table and its ratio. */
function payload(over: Record<string, unknown> = {}) {
  return {
    steward: steward(),
    items: [
      item(2251, 'implementing', { last_progress_at: ago(0.2) }),
      item(2264, 'awaiting-reply', { last_progress_at: ago(5) }),
      item(2247, 'awaiting-merge', { last_progress_at: ago(2) }),
      item(2259, 'skipped', { last_progress_at: ago(9), finished_at: ago(9) }),
    ],
    events: [event('e-recent', 1)],
    counts: { open: 3 },
    ...over,
  }
}

function renderPage() {
  return renderWithProviders(<StewardPageView stewardId="steward-andromeda" />)
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(NOW)
  vi.clearAllMocks()
  ctx.value = {
    active: { owner: 'o', repo: 'r' },
    refreshPrefs: { listPollMs: 60_000, detailPollMs: 15_000, staleTimeMs: 30_000, pollInBackground: false, prefetchPulls: false },
  }
  api.steward.mockResolvedValue(payload())
  api.setStewardPaused.mockImplementation((_ref: unknown, _id: string, paused: boolean) =>
    Promise.resolve({ steward: steward({ enabled: !paused, paused_reason: paused ? '' : '' }) }))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('StewardPageView — phases and event kinds are translated, not machine tokens', () => {
  it('renders a phase through the catalog and never as its raw token', async () => {
    // REGRESSION: the badge rendered `{item.phase}` directly, so a reader saw the
    // kebab-case store vocabulary (`awaiting-merge`) and every non-English locale
    // saw that same English. The untranslated-literal gate cannot catch it — the
    // value is dynamic, not a literal — so the guarantee has to live in a test.
    api.steward.mockResolvedValue(payload({ items: [item(7, 'awaiting-merge')] }))
    renderPage()

    // Scoped to the work-items table: the header badge legitimately shows the
    // SAME label (this item is the newest live one), so an unscoped query is
    // ambiguous rather than wrong.
    const labelled = await screen.findAllByText(copy('phase_awaiting_merge'))
    expect(labelled.length).toBeGreaterThan(0)
    // The raw token must appear NOWHERE: asserting only the label would still
    // pass if the code rendered both.
    expect(screen.queryByText('awaiting-merge')).not.toBeInTheDocument()
    // Translated prose needs the app font: `--mono` has no coverage for
    // zh-CN/ja/ko/hi/bn (see index.css), so a mono badge renders those as tofu.
    expect(labelled[0].className).toContain('font-body')
  })

  it('renders a ledger line\u2019s kind through the catalog too', async () => {
    api.steward.mockResolvedValue(payload({
      events: [{ ts: new Date().toISOString(), number: 7, kind: 'handback', text: 'over to you' }],
    }))
    renderPage()

    expect(await screen.findByText(copy('kind_handback'))).toBeInTheDocument()
    expect(screen.queryByText('handback')).not.toBeInTheDocument()
  })

  it('states the steward is idle rather than echoing a phase token in the header', async () => {
    // The header used `newestLive?.phase` verbatim while its paused/idle siblings
    // used catalog keys — one branch of the same label speaking a different
    // language from the other two.
    api.steward.mockResolvedValue(payload({ items: [item(7, 'investigating')] }))
    renderPage()

    const state = await screen.findByTestId('steward-state')
    expect(state).toHaveTextContent(copy('phase_investigating'))
    expect(state).not.toHaveTextContent('investigating')
  })
})

describe('StewardPageView — slot accounting', () => {
  it('shows the at-limit note only once open work items reach max_open', async () => {
    api.steward.mockResolvedValue(payload({ counts: { open: 3 } }))
    renderPage()

    const note = await screen.findByTestId('stat-open-items-note')
    expect(note).toHaveTextContent(copy('at_its_limit'))
    // The value still reports the ratio, so "at its limit" is attributable.
    expect(screen.getByTestId('stat-open-items')).toHaveTextContent(
      copy('open_of_max', { open: '3', max: '3' }),
    )
  })

  it('does not claim the limit is reached while a slot is still free', async () => {
    api.steward.mockResolvedValue(payload({ counts: { open: 2 } }))
    renderPage()

    const note = await screen.findByTestId('stat-open-items-note')
    expect(note).not.toHaveTextContent(copy('at_its_limit'))
    expect(note).toHaveTextContent(copy('slots_free', { count: 1 }))
  })
})

describe('StewardPageView — work log 24h boundary', () => {
  it('puts only events inside the rolling 24h window above the Earlier divider', async () => {
    api.steward.mockResolvedValue(payload({
      events: [
        event('e-1h', 1),
        event('e-23h', 23),
        event('e-2359', 23.983),   // 23h 59m — inside
        event('e-2401', 24.017),   // 24h 01m — outside
        event('e-3d', 72),
      ],
    }))
    renderPage()

    const table = await screen.findByTestId('work-log-table')
    const rows = within(table).getAllByRole('row').slice(1) // drop the header row
    const ids = rows.map((r) => r.getAttribute('data-testid'))
    const divider = ids.indexOf('work-log-earlier')

    // Newest first, with the divider exactly at the boundary crossing.
    expect(ids).toEqual([
      'work-log-row-e-1h',
      'work-log-row-e-23h',
      'work-log-row-e-2359',
      'work-log-earlier',
      'work-log-row-e-2401',
      'work-log-row-e-3d',
    ])
    // And the highlight follows the same split — the accent border marks recency,
    // so it must not be applied to a row that sits below the divider.
    ids.slice(0, divider).forEach((id) => {
      expect(screen.getByTestId(id!)).toHaveAttribute('data-recent', 'true')
    })
    ids.slice(divider + 1).forEach((id) => {
      expect(screen.getByTestId(id!)).toHaveAttribute('data-recent', 'false')
    })
    expect(within(screen.getByTestId('work-log-row-e-1h')).getAllByRole('cell')[0].className)
      .toContain('border-l-accent')
    expect(within(screen.getByTestId('work-log-row-e-2401')).getAllByRole('cell')[0].className)
      .toContain('border-l-transparent')
  })

  it('omits the Earlier divider when every event is inside the window', async () => {
    api.steward.mockResolvedValue(payload({ events: [event('e-1h', 1), event('e-5h', 5)] }))
    renderPage()

    await screen.findByTestId('work-log-row-e-1h')
    expect(screen.queryByTestId('work-log-earlier')).not.toBeInTheDocument()
  })
})

describe('StewardPageView — the next column', () => {
  it('renders the resumable intent in full, not truncated', async () => {
    renderPage()

    const cell = await screen.findByTestId('work-item-next-2251')
    // The whole sentence, character for character: this column is the only place
    // a human (or the steward's next turn) can read what happens next.
    expect(cell).toHaveTextContent(LONG_NEXT)
    expect(cell.textContent).toBe(LONG_NEXT)
    expect(cell.className).not.toMatch(/truncate|line-clamp/)
  })

  it('lists exactly the slot-consuming items, so the table matches the ratio', async () => {
    renderPage()

    await screen.findByTestId('work-items-table')
    expect(screen.getByTestId('work-item-2251')).toBeInTheDocument()
    expect(screen.getByTestId('work-item-2264')).toBeInTheDocument()
    expect(screen.getByTestId('work-item-2247')).toBeInTheDocument()
    // A finished item is NOT slot-consuming (`countsTowardOpen`), so it must not
    // appear in a table whose count is the "3 / 3" stat.
    expect(screen.queryByTestId('work-item-2259')).not.toBeInTheDocument()
  })
})

describe('StewardPageView — pause', () => {
  it('posts paused=true for this steward and this repo', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderPage()

    await user.click(await screen.findByTestId('steward-pause-toggle'))

    await waitFor(() => {
      expect(api.setStewardPaused).toHaveBeenCalledTimes(1)
    })
    expect(api.setStewardPaused).toHaveBeenCalledWith({ owner: 'o', repo: 'r' }, 'steward-andromeda', true)
  })

  it('posts paused=false from a paused steward', async () => {
    api.steward.mockResolvedValue(payload({
      steward: steward({ enabled: false, paused_reason: 'stopped by you' }),
    }))
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderPage()

    // The paused state is visible before the action, so the button's verb is
    // attributable to the record rather than to a local toggle.
    expect(await screen.findByTestId('steward-state')).toHaveTextContent(copy('state_paused'))
    await user.click(screen.getByTestId('steward-pause-toggle'))

    await waitFor(() => {
      expect(api.setStewardPaused).toHaveBeenCalledWith({ owner: 'o', repo: 'r' }, 'steward-andromeda', false)
    })
  })
})
