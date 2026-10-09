/**
 * Agent roster (WardingAgentsPage) — card grid, compact table, editor dialog.
 *
 * The page used to be a StatCard row plus an HTML table, and its tests read the
 * DOM structurally (`table tr`, nth-child cells). Those assertions could not
 * survive the rewrite and, more importantly, never covered the behaviour that
 * actually matters: which card is the default, what the editor is pre-filled
 * with, the ordering of the promote-then-save writes, and the nested-dialog
 * keyboard case. Everything here is queried by accessible name or an explicit
 * test id so a restyle cannot turn a green suite red.
 *
 * The list view IS a table again, but the assertions go through roles
 * (`columnheader`, the row's own control) rather than cell positions, so
 * reordering a column does not break them.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { MemoryRouter } from 'react-router-dom'
import { configureStore } from '@reduxjs/toolkit'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import dashboardReducer from '../store/dashboardSlice'
import chatReducer from '../store/chatSlice'
import notificationsReducer from '../store/notificationsSlice'

/* Render framer-motion elements as plain DOM. The side sheet is an
   AnimatePresence child with a 240ms x-translate exit, so a real
   AnimatePresence keeps the closing sheet mounted for the duration of that
   transition — which would make every "Escape closes / Escape is ignored"
   assertion pass or fail on timing rather than on behaviour. */
vi.mock('framer-motion', async () => {
  const React = await import('react')
  const FRAMER_PROPS = new Set([
    'layout', 'layoutId', 'initial', 'animate', 'exit', 'transition',
    'variants', 'whileHover', 'whileTap', 'onAnimationComplete',
  ])
  const make = (tag: string) =>
    React.forwardRef((props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      const clean: Record<string, unknown> = {}
      for (const k of Object.keys(props)) {
        if (k === 'children' || FRAMER_PROPS.has(k)) continue
        clean[k] = props[k]
      }
      return React.createElement(tag, { ...clean, ref }, props.children as React.ReactNode)
    })
  // One component type per tag, cached: a proxy minting a fresh type per read
  // would hand React a new element type each render and remount the subtree.
  const cache = new Map<string, unknown>()
  return {
    motion: new Proxy({}, {
      get: (_t, tag: string) => {
        if (!cache.has(tag)) cache.set(tag, make(tag))
        return cache.get(tag)
      },
    }),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    useReducedMotion: () => false,
  }
})

/* ── Mock api client ── */
const mockApi = vi.hoisted(() => ({
  wardingAgents: vi.fn(),
  agentsInstalled: vi.fn(),
  workspaces: vi.fn(),
  wardingConfig: vi.fn(),
  createWorkspace: vi.fn(),
  createWardingAgent: vi.fn(),
  updateWardingAgent: vi.fn(),
  deleteWardingAgent: vi.fn(),
  agentResolvedModel: vi.fn(),
  setDefaultAgent: vi.fn(),
  createChatSlot: vi.fn(),
  models: vi.fn(),
}))

vi.mock('../api/client', () => ({ api: mockApi }))

import WardingAgentsPage from '../pages/WardingAgentsPage'
import AgentAvatar from '../components/AgentAvatar'

function createTestStore() {
  return configureStore({
    reducer: { dashboard: dashboardReducer, chat: chatReducer, notifications: notificationsReducer },
  })
}

function renderPage() {
  const store = createTestStore()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Provider store={store}>
        <MemoryRouter>
          <WardingAgentsPage />
        </MemoryRouter>
      </Provider>
    </QueryClientProvider>,
  )
}

/* The default agent deliberately does NOT point at a workspace or memory store
   called "default": otherwise the literal "default" appears three times inside
   its own card and the `default` badge could not be asserted by text. */
const DEFAULT_AGENT = {
  name: 'warding',
  kiro_agent: 'warding',
  workspace: 'core-ws',
  memory_store: 'core-mem',
}
const OTHER_AGENT = {
  name: 'oncall',
  kiro_agent: 'ops-agent',
  workspace: 'oncall',
  memory_store: 'oncall-mem',
  model: 'claude-opus-5',
}

const AGENTS_RESPONSE = { agents: [DEFAULT_AGENT, OTHER_AGENT], default_agent: 'warding' }
const WORKSPACES_RESPONSE = {
  workspaces: [{ name: 'default' }, { name: 'core-ws' }, { name: 'oncall' }],
}
const INSTALLED_RESPONSE = [{ name: 'warding' }, { name: 'ops-agent' }]
const CONFIG_RESPONSE = { memory_stores: { default: {}, 'core-mem': {}, 'oncall-mem': {} } }

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.wardingAgents.mockResolvedValue(AGENTS_RESPONSE)
  mockApi.agentsInstalled.mockResolvedValue(INSTALLED_RESPONSE)
  mockApi.workspaces.mockResolvedValue(WORKSPACES_RESPONSE)
  mockApi.wardingConfig.mockResolvedValue(CONFIG_RESPONSE)
  mockApi.agentResolvedModel.mockResolvedValue({ model: '', pinned: false, kiro_agent: 'warding' })
  mockApi.models.mockResolvedValue([{ model_name: 'claude-opus-5' }])
  // The mutation hooks read `.error` off the resolved body, so an undefined
  // resolution (a bare vi.fn()) would throw inside onSuccess.
  mockApi.createWardingAgent.mockResolvedValue({})
  mockApi.updateWardingAgent.mockResolvedValue({})
  mockApi.deleteWardingAgent.mockResolvedValue({})
  mockApi.setDefaultAgent.mockResolvedValue({})
  mockApi.createWorkspace.mockResolvedValue({ name: 'staging' })
})

/** Wait until the roster has rendered real data rather than the empty state. */
async function renderRoster(expectCards = 2) {
  const rendered = renderPage()
  await waitFor(() => expect(screen.getAllByTestId('agent-card')).toHaveLength(expectCards))
  await waitFor(() => expect(mockApi.workspaces).toHaveBeenCalled())
  await waitFor(() => expect(mockApi.wardingConfig).toHaveBeenCalled())
  return rendered
}

/** Escape, dispatched where Radix listens for it.
 *
 *  Radix's DismissableLayer binds `keydown` on `document`; the hand-rolled dialog
 *  this page used to render bound it on `window`. An event dispatched directly AT
 *  `window` never passes through `document`, so `fireEvent.keyDown(window, ...)`
 *  is invisible to Radix — it is not a faithful simulation either way, since a
 *  real keypress targets the focused element and bubbles up through both. */
function pressEscape() {
  fireEvent.keyDown(document, { key: 'Escape' })
}

/** A roster card, addressed by the accessible name the card exposes. */
function agentCard(name: string) {
  return screen.getByRole('button', { name: `Edit agent ${name}` })
}

/** Open the editor dialog on `name` and return the dialog element. */
async function openEditor(name: string): Promise<HTMLElement> {
  fireEvent.click(agentCard(name))
  return await screen.findByRole('dialog', { name: `Edit agent ${name}` })
}

/** Open the editor dialog in create mode and return the dialog element. */
async function openCreate(): Promise<HTMLElement> {
  fireEvent.click(screen.getByTestId('new-agent'))
  return await screen.findByRole('dialog', { name: 'Create a new agent' })
}

/**
 * Move the editor to one of its rail panes.
 *
 * The editor is a rail plus one pane, so a control is only mounted while its own
 * pane is showing. Tests that touch a binding, the routing field or the removal
 * step navigate there first — the same click a user makes.
 */
function gotoPane(sheet: HTMLElement, key: string) {
  fireEvent.click(within(sheet).getByTestId(`agent-rail-${key}`))
}

describe('agent roster — cards', () => {
  it('renders one card per agent and badges only the default one', async () => {
    await renderRoster()

    const cards = screen.getAllByTestId('agent-card')
    expect(cards).toHaveLength(2)

    const defaultCard = agentCard('warding')
    expect(within(defaultCard).getByText('default')).toBeInTheDocument()
    expect(within(defaultCard).getByText('Used for all new chats')).toBeInTheDocument()

    const otherCard = agentCard('oncall')
    expect(within(otherCard).queryByText('default')).not.toBeInTheDocument()

    // Bindings are on the card itself — that is the whole point of the grid.
    expect(within(otherCard).getByText('ops-agent')).toBeInTheDocument()
    expect(within(otherCard).getByText('oncall-mem')).toBeInTheDocument()
    expect(within(otherCard).getByText('claude-opus-5')).toBeInTheDocument()
    // No per-agent pin on the default agent → the model reads as inherited.
    expect(within(defaultCard).getByText('Inherited')).toBeInTheDocument()
    // Nothing collides in this fixture, so no store is flagged as shared.
    expect(within(otherCard).queryByText('shared')).not.toBeInTheDocument()
    expect(within(defaultCard).queryByText('shared')).not.toBeInTheDocument()
  })

  it('flags only the store that a second agent also points at', async () => {
    // Both agents on one memory store, distinct workspaces: the marker must land
    // on MEMORY STORE and nowhere else. A bare "Shared" badge in the header was
    // read by a first-run reviewer as "shared with my teammates", so the point
    // of this shape is that it names WHICH store is doubled up.
    mockApi.wardingAgents.mockResolvedValue({
      agents: [
        { ...DEFAULT_AGENT, memory_store: 'core-mem' },
        { ...OTHER_AGENT, workspace: 'oncall', memory_store: 'core-mem' },
      ],
      default_agent: 'warding',
    })
    await renderRoster()

    for (const name of ['warding', 'oncall']) {
      const card = agentCard(name)
      // One marker per card — the workspaces are distinct, so files are not shared.
      expect(within(card).getAllByText('shared')).toHaveLength(1)
    }
  })
})

describe('agent roster — isolation preview notice', () => {
  const NOTICE = /Isolated memory per agent is on the way/
  const TIP = /Isolated memory per agent is still being built/

  /* The view choice persists to localStorage, so a test here that switches to
     List would otherwise hand every later block a table instead of the cards
     they query. Cleared on both edges: before, so this block starts on cards
     whatever ran earlier; after, so it cannot leak forward. */
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('says the bindings are a preview, in both views', async () => {
    await renderRoster()
    // Page-level, so it is on screen before the user picks a view.
    expect(screen.getByText(NOTICE)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'List' }))
    await screen.findByRole('table')
    // Switching the layout must not take the caveat away with the cards.
    expect(screen.getByText(NOTICE)).toBeInTheDocument()
  })

  it('is not repeated on every card', async () => {
    await renderRoster()
    // The claim is about the whole surface. Two agents, one notice — a per-card
    // copy would put the same sentence on the page as many times as there are
    // agents, and the roster runs to dozens.
    expect(screen.getAllByText(NOTICE)).toHaveLength(1)
  })

  it('hangs the same caveat off the workspace and memory bindings', async () => {
    await renderRoster()
    const sheet = await openEditor('oncall')
    gotoPane(sheet, 'place')
    // Two tips, one per binding the notice is about. The editor is an overlay,
    // so the page-level notice is not readable from here — the tooltip is the
    // only place this caveat reaches a user who is mid-edit.
    expect(within(sheet).getAllByTitle(TIP)).toHaveLength(2)
  })

  it('marks the workspace and memory columns in the list view', async () => {
    await renderRoster()
    fireEvent.click(screen.getByRole('button', { name: 'List' }))
    const table = await screen.findByRole('table')
    expect(within(table).getAllByTitle(TIP)).toHaveLength(2)
    // Each tip is a named control rather than announcing as "question mark",
    // and the header above keeps its own short name regardless.
    expect(within(table).getAllByRole('button', { name: 'More information' })).toHaveLength(2)
  })
})

describe('agent roster — filtering', () => {
  it('narrows the visible cards', async () => {
    await renderRoster()
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter agents…' }), {
      target: { value: 'oncall' },
    })
    await waitFor(() => expect(screen.getAllByTestId('agent-card')).toHaveLength(1))
    expect(agentCard('oncall')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit agent warding' })).not.toBeInTheDocument()
  })

  it('shows the filter empty state when nothing matches', async () => {
    await renderRoster()
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter agents…' }), {
      target: { value: 'no-such-agent' },
    })
    await waitFor(() => expect(screen.queryAllByTestId('agent-card')).toHaveLength(0))
    expect(screen.getByTestId('empty-state-title')).toHaveTextContent('No agents match your filter')
  })

  it('shows the zero-agent empty state when there are no agents at all', async () => {
    mockApi.wardingAgents.mockResolvedValue({ agents: [], default_agent: '' })
    renderPage()
    await waitFor(() =>
      expect(screen.getByTestId('empty-state-title')).toHaveTextContent('No agents'),
    )
    // Distinct copy from the filter case — a first run is not a failed search.
    expect(screen.getByTestId('empty-state-title')).not.toHaveTextContent('match your filter')
    expect(screen.queryAllByTestId('agent-card')).toHaveLength(0)
  })

  it('does not flash the empty state while an invalidateQueries-driven refetch is in flight', async () => {
    // After retiring the refreshTrigger-in-queryKey pattern, the
    // roster query key is stable (`['warding-agents']`) and refetches are
    // triggered by `queryClient.invalidateQueries` from the WS handler.
    // `invalidateQueries` keeps the cached data visible during the refetch,
    // so the roster must never collapse to the empty state.
    let resolveSecond: (v: unknown) => void = () => {}
    mockApi.wardingAgents
      .mockResolvedValueOnce(AGENTS_RESPONSE)
      .mockImplementationOnce(() => new Promise(res => { resolveSecond = res }))

    const store = createTestStore()
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <Provider store={store}>
          <MemoryRouter>
            <WardingAgentsPage />
          </MemoryRouter>
        </Provider>
      </QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getAllByTestId('agent-card')).toHaveLength(2))

    // Simulate the WS handler: invalidate the query in-place (no key change).
    act(() => { qc.invalidateQueries({ queryKey: ['warding-agents'] }) })

    // The prior roster must remain on screen throughout the pending refetch —
    // no empty state, cards intact.
    await waitFor(() => expect(mockApi.wardingAgents).toHaveBeenCalledTimes(2))
    expect(screen.queryByTestId('empty-state-title')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('agent-card')).toHaveLength(2)

    // And once the refetch resolves the roster is still there (now from fresh
    // data), never having blanked in between.
    resolveSecond(AGENTS_RESPONSE)
    await waitFor(() => expect(screen.getAllByTestId('agent-card')).toHaveLength(2))
    expect(screen.queryByTestId('empty-state-title')).not.toBeInTheDocument()
  })
})

describe('agent roster — description', () => {
  it('clamps a long description to two lines and keeps the full text reachable', async () => {
    // The card used to `truncate` to ONE line, which cut nearly every real
    // description mid-word. Two lines plus the full text in the tooltip.
    const long =
      'Paged-alert triage agent — owns the runbooks, keeps the escalation ladder ' +
      'warm, and files the follow-up tickets after every page.'
    mockApi.wardingAgents.mockResolvedValue({
      agents: [DEFAULT_AGENT, { ...OTHER_AGENT, description: long }],
      default_agent: 'warding',
    })
    await renderRoster()

    const desc = within(agentCard('oncall')).getByText(long)
    expect(desc.className).toContain('line-clamp-2')
    // Height is pinned alongside the clamp: without it the clamp leaks a sliver
    // of a third line, and short-description cards sit shorter than their
    // neighbours so the binding grids stop lining up across the row.
    expect(desc.className).toContain('h-[34px]')
    expect(desc).toHaveAttribute('title', long)
  })

  it('does not put an empty title on an agent with no description', async () => {
    await renderRoster()
    // DEFAULT_AGENT has no description, so the card shows the default-agent line
    // instead — and must not advertise a tooltip that would render as blank.
    const filler = within(agentCard('warding')).getByText('Used for all new chats')
    expect(filler).not.toHaveAttribute('title')
  })

  it('falls back to the same text in the card and the row', async () => {
    // The two views drifted: an agent with no description was blank in the card
    // but italic "No description" in the row, so the same agent read differently
    // depending on which layout you were in.
    await renderRoster()
    // OTHER_AGENT is non-default with no description -> the placeholder.
    expect(within(agentCard('oncall')).getByText('No description')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'List' }))
    await screen.findByRole('table')
    const row = screen.getByRole('button', { name: 'Edit agent oncall' }).closest('tr')!
    expect(within(row).getByText('No description')).toBeInTheDocument()

    // And the default agent keeps its own hint in BOTH views, rather than one
    // view explaining why it matters and the other calling it undescribed.
    const defaultRow = screen.getByRole('button', { name: 'Edit agent warding' }).closest('tr')!
    expect(within(defaultRow).getByText('Used for all new chats')).toBeInTheDocument()
  })
})

describe('agent roster — view toggle', () => {
  beforeEach(() => localStorage.clear())

  it('defaults to cards and switches to a table on List', async () => {
    await renderRoster()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'List' }))

    const table = await screen.findByRole('table')
    expect(screen.getAllByTestId('agent-roster-row')).toHaveLength(2)
    // The cards are gone, not merely hidden underneath.
    expect(screen.queryAllByTestId('agent-card')).toHaveLength(0)
    // Bindings move into columns, so the header names them once instead of
    // repeating a label per card. Exact names: the workspace and memory headers
    // carry the preview InfoTip, and each `th` pins its own `aria-label` so the
    // tip's name is not concatenated into the column's.
    expect(within(table).getByRole('columnheader', { name: 'Workspace' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Memory Store' })).toBeInTheDocument()
  })

  it('carries each agent’s bindings into its row', async () => {
    await renderRoster()
    fireEvent.click(screen.getByRole('button', { name: 'List' }))
    await screen.findByRole('table')

    const row = screen.getByRole('button', { name: 'Edit agent oncall' }).closest('tr')!
    expect(within(row).getByText('ops-agent')).toBeInTheDocument()
    expect(within(row).getByText('oncall-mem')).toBeInTheDocument()
    expect(within(row).getByText('claude-opus-5')).toBeInTheDocument()
  })

  it('opens the editor from a row', async () => {
    await renderRoster()
    fireEvent.click(screen.getByRole('button', { name: 'List' }))
    await screen.findByRole('table')

    fireEvent.click(screen.getByRole('button', { name: 'Edit agent oncall' }))
    expect(await screen.findByRole('dialog', { name: 'Edit agent oncall' })).toBeInTheDocument()
  })

  it('opens the editor exactly once when the row itself is clicked', async () => {
    // The row is a click target for convenience AND contains a real control
    // with the same action. One gesture must not fire both.
    await renderRoster()
    fireEvent.click(screen.getByRole('button', { name: 'List' }))
    await screen.findByRole('table')

    const nameControl = screen.getByRole('button', { name: 'Edit agent oncall' })
    fireEvent.click(nameControl)
    await screen.findByRole('dialog', { name: 'Edit agent oncall' })
    // A second dialog would mean the row handler fired on top of the control's.
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
  })

  it('remembers the choice across mounts', async () => {
    const { unmount } = await renderRoster()
    fireEvent.click(screen.getByRole('button', { name: 'List' }))
    await screen.findByRole('table')
    expect(localStorage.getItem('mc-agents-view')).toBe('list')

    // A fresh mount reads the stored layout rather than snapping back to cards.
    unmount()
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('agent-roster-row')).toHaveLength(2))
  })

  it('flags a doubled-up store in the row, naming which one', async () => {
    mockApi.wardingAgents.mockResolvedValue({
      agents: [
        { ...DEFAULT_AGENT, memory_store: 'core-mem' },
        { ...OTHER_AGENT, workspace: 'oncall', memory_store: 'core-mem' },
      ],
      default_agent: 'warding',
    })
    await renderRoster()
    fireEvent.click(screen.getByRole('button', { name: 'List' }))
    await screen.findByRole('table')

    const row = screen.getByRole('button', { name: 'Edit agent oncall' }).closest('tr')!
    // Memory is doubled; the workspaces are distinct, so exactly one marker.
    expect(within(row).getAllByText('shared')).toHaveLength(1)
  })

  it('is not offered when there are no agents to lay out', async () => {
    mockApi.wardingAgents.mockResolvedValue({ agents: [], default_agent: '' })
    renderPage()
    await waitFor(() =>
      expect(screen.getByTestId('empty-state-title')).toHaveTextContent('No agents'),
    )
    expect(screen.queryByRole('button', { name: 'List' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cards' })).not.toBeInTheDocument()
  })
})

describe('agent editor — opening', () => {
  it('opens pre-filled with the clicked agent’s bindings', async () => {
    await renderRoster()
    const sheet = await openEditor('oncall')

    // One assertion per pane the binding lives on, because a pane mounts only
    // while it is showing. Visiting each is the point: it also proves the rail
    // routes to the right one.
    gotoPane(sheet, 'place')
    expect(within(sheet).getByRole('combobox', { name: 'Workspace' })).toHaveTextContent('oncall')
    expect(within(sheet).getByRole('combobox', { name: 'Memory Store' })).toHaveTextContent('oncall-mem')

    gotoPane(sheet, 'template')
    expect(within(sheet).getByRole('combobox', { name: 'Agent Template' })).toHaveTextContent('ops-agent')

    gotoPane(sheet, 'model')
    expect(within(sheet).getByRole('combobox', { name: 'Edit default model' })).toHaveTextContent('claude-opus-5')
  })

  it('opens the create dialog from "New agent"', async () => {
    await renderRoster()
    const sheet = await openCreate()
    // Create mode has no agent to edit yet, so the bindings start on the defaults.
    expect(within(sheet).getByRole('combobox', { name: 'Workspace' })).toHaveTextContent('default')
    expect(within(sheet).getByRole('combobox', { name: 'Memory Store' })).toHaveTextContent('default')
    // The Agent Template is the exception: it has NO safe default, because
    // pre-filling the built-in made a new agent an alias for the default agent.
    expect(within(sheet).getByRole('combobox', { name: 'Agent Template' }))
      .toHaveTextContent('Select an agent template…')
  })
})

describe('agent editor — create', () => {
  it('refuses an empty name without calling the api', async () => {
    await renderRoster()
    const sheet = await openCreate()

    fireEvent.click(within(sheet).getByRole('button', { name: 'Create' }))

    expect(await within(sheet).findByText('Name is required')).toBeInTheDocument()
    expect(mockApi.createWardingAgent).not.toHaveBeenCalled()
    // The dialog stays open so the user can fix it in place.
    expect(screen.getByRole('dialog', { name: 'Create a new agent' })).toBeInTheDocument()
  })

  it('refuses an agent with no Agent Template chosen, without calling the api', async () => {
    await renderRoster()
    const sheet = await openCreate()

    const user = userEvent.setup()
    await user.type(within(sheet).getByPlaceholderText('e.g. oncall'), 'staging')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Create' }))

    // The template used to be pre-filled with 'warding', so an agent created
    // this way became an alias for the DEFAULT agent and the chat picker
    // appeared to "fall back to default". It is now an explicit choice.
    expect(await within(sheet).findByText('Agent Template is required')).toBeInTheDocument()
    expect(mockApi.createWardingAgent).not.toHaveBeenCalled()
  })

  it('creates the agent with the chosen bindings', async () => {
    await renderRoster()
    const sheet = await openCreate()

    const user = userEvent.setup()
    await user.type(within(sheet).getByPlaceholderText('e.g. oncall'), 'staging')
    // The template must be picked deliberately — nothing pre-fills it.
    // Keyboard-driven: a POINTER click on the Radix select inside this dialog
    // recurses in happy-dom's blur handling (RangeError: Maximum call stack size
    // exceeded), which then wedges React's act queue for every later test here.
    const template = within(sheet).getByRole('combobox', { name: 'Agent Template' })
    fireEvent.keyDown(template, { key: 'ArrowDown' })
    fireEvent.click(await screen.findByRole('option', { name: 'ops-agent' }))
    fireEvent.click(within(sheet).getByRole('button', { name: 'Create' }))

    await waitFor(() =>
      expect(mockApi.createWardingAgent).toHaveBeenCalledWith({
        name: 'staging',
        kiro_agent: 'ops-agent',
        workspace: 'default',
        memory_store: 'default',
        triggers: '',
      }),
    )
  })
})

describe('agent editor — save', () => {
  it('saves the bindings for the edited agent', async () => {
    await renderRoster()
    const sheet = await openEditor('oncall')

    // Save is gated on there being something to save, so make one real edit; the
    // point of this test is the payload's SHAPE, which every other field pins.
    gotoPane(sheet, 'routing')
    fireEvent.change(within(sheet).getByRole('textbox', { name: 'Triggers' }), { target: { value: 'pager' } })
    fireEvent.click(within(sheet).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockApi.updateWardingAgent).toHaveBeenCalled())
    expect(mockApi.updateWardingAgent).toHaveBeenCalledWith('oncall', {
      kiro_agent: 'ops-agent',
      workspace: 'oncall',
      memory_store: 'oncall-mem',
      triggers: 'pager',
      model: 'claude-opus-5',
    })
  })

  it('offers no Save until something is actually pending', async () => {
    // The wake pane's pause/run controls apply immediately, so a live Save beside
    // them would imply those toggles are drafts that Cancel could roll back.
    await renderRoster()
    const sheet = await openEditor('oncall')

    expect(within(sheet).getByRole('button', { name: 'Save changes' })).toBeDisabled()
    gotoPane(sheet, 'routing')
    fireEvent.change(within(sheet).getByRole('textbox', { name: 'Triggers' }), { target: { value: 'pager' } })
    expect(within(sheet).getByRole('button', { name: 'Save changes' })).toBeEnabled()

    // Typing it back is not a pending change.
    fireEvent.change(within(sheet).getByRole('textbox', { name: 'Triggers' }), { target: { value: '' } })
    expect(within(sheet).getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  it('sends edited routing triggers', async () => {
    await renderRoster()
    const sheet = await openEditor('oncall')

    gotoPane(sheet, 'routing')
    fireEvent.change(within(sheet).getByRole('textbox', { name: 'Triggers' }), {
      target: { value: 'incident, prod outage' },
    })
    fireEvent.click(within(sheet).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockApi.updateWardingAgent).toHaveBeenCalled())
    expect(mockApi.updateWardingAgent).toHaveBeenCalledWith(
      'oncall',
      expect.objectContaining({ triggers: 'incident, prod outage' }),
    )
  })

  it('does not touch the default from the editor at all', async () => {
    // Promotion lives on the roster bar now, not per-agent: a per-agent control
    // could only ever offer promotion (the backend refuses to unset a default
    // without naming a replacement), which read as a broken switch.
    await renderRoster()
    const sheet = await openEditor('oncall')

    expect(within(sheet).queryByRole('switch')).not.toBeInTheDocument()
    gotoPane(sheet, 'routing')
    fireEvent.change(within(sheet).getByRole('textbox', { name: 'Triggers' }), { target: { value: 'pager' } })
    fireEvent.click(within(sheet).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(mockApi.updateWardingAgent).toHaveBeenCalled())
    expect(mockApi.setDefaultAgent).not.toHaveBeenCalled()
  })
})

describe('agent editor — stale writes', () => {
  it('does not close the panel when a write for a DIFFERENT agent lands', async () => {
    // Save A, dismiss while it is in flight, then open B: A's success must not
    // dismiss B's panel or discard B's edits.
    let resolveA: (v: unknown) => void = () => {}
    mockApi.updateWardingAgent.mockImplementation(() => new Promise(res => { resolveA = res }))
    await renderRoster()

    const sheetA = await openEditor('oncall')
    fireEvent.click(within(sheetA).getByRole('button', { name: 'Save changes' }))
    pressEscape()
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit agent oncall' })).not.toBeInTheDocument(),
    )

    const sheetB = await openEditor('warding')
    resolveA({ ok: true })

    // B survives, and A's outcome is not reported against it.
    await waitFor(() => expect(mockApi.wardingAgents).toHaveBeenCalled())
    expect(screen.getByRole('dialog', { name: 'Edit agent warding' })).toBeInTheDocument()
    expect(within(sheetB).queryByRole('button', { name: 'Save changes' })).toBeInTheDocument()
  })

  it('does not report a stale write\u2019s error against the agent now open', async () => {
    let rejectA: (e: unknown) => void = () => {}
    mockApi.updateWardingAgent.mockImplementation(() => new Promise((_res, rej) => { rejectA = rej }))
    await renderRoster()

    const sheetA = await openEditor('oncall')
    fireEvent.click(within(sheetA).getByRole('button', { name: 'Save changes' }))
    pressEscape()
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit agent oncall' })).not.toBeInTheDocument(),
    )

    const sheetB = await openEditor('warding')
    rejectA(new Error('oncall write blew up'))

    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Edit agent warding' })).toBeInTheDocument())
    expect(within(sheetB).queryByText('oncall write blew up')).not.toBeInTheDocument()
  })

  it('does not close a REOPENED panel for the same agent', async () => {
    // The narrower case a name comparison could not catch: dismiss and reopen
    // the SAME agent, and the stale completion still matched by name.
    let resolveA: (v: unknown) => void = () => {}
    mockApi.updateWardingAgent.mockImplementation(() => new Promise(res => { resolveA = res }))
    await renderRoster()

    const first = await openEditor('oncall')
    fireEvent.click(within(first).getByRole('button', { name: 'Save changes' }))
    pressEscape()
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit agent oncall' })).not.toBeInTheDocument(),
    )

    await openEditor('oncall')
    resolveA({ ok: true })

    await waitFor(() => expect(mockApi.wardingAgents).toHaveBeenCalled())
    expect(screen.getByRole('dialog', { name: 'Edit agent oncall' })).toBeInTheDocument()
  })

  it('does not navigate away when a stale chat request completes', async () => {
    // Navigation is the most disruptive outcome on this page, so it is guarded
    // by the same panel identity as the writes.
    let resolveSlot: (v: unknown) => void = () => {}
    mockApi.createChatSlot.mockImplementation(() => new Promise(res => { resolveSlot = res }))
    await renderRoster()

    const sheet = await openEditor('oncall')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Chat with this agent' }))
    pressEscape()
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit agent oncall' })).not.toBeInTheDocument(),
    )

    const replacement = await openEditor('warding')
    resolveSlot({ key: 'slot-1', title: 'oncall' })

    // The replacement panel survives; the user is not thrown into /chat.
    await waitFor(() => expect(mockApi.createChatSlot).toHaveBeenCalled())
    expect(replacement).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Edit agent warding' })).toBeInTheDocument()
  })
})

describe('agent roster — default agent bar', () => {
  it('names the current default and switches it on pick, with no Save step', async () => {
    await renderRoster()

    const picker = screen.getByRole('combobox', { name: 'New sessions use' })
    expect(picker).toHaveTextContent('warding')

    fireEvent.click(picker)
    fireEvent.click(await screen.findByRole('option', { name: 'oncall' }))

    // The write is immediate — this control is not part of any form.
    await waitFor(() => expect(mockApi.setDefaultAgent).toHaveBeenCalledWith('oncall'))
    expect(mockApi.updateWardingAgent).not.toHaveBeenCalled()
  })

  it('is hidden when there is nothing to choose between', async () => {
    mockApi.wardingAgents.mockResolvedValue({ agents: [DEFAULT_AGENT], default_agent: 'warding' })
    await renderRoster(1)

    expect(screen.getByTestId('agent-card')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'New sessions use' })).not.toBeInTheDocument()
  })
})

/* The collision warning's test lives in AgentEditorSelect.test.tsx, not here.
   It is the only test on this page that drives a Radix Select to completion from
   INSIDE the Radix Dialog, and that combination cannot run in this harness:
   Radix commits discrete events via `ReactDOM.flushSync(...)`, Testing Library
   wraps interactions in `act()`, and React throws "Should not already be
   working." on a flushSync nested inside a flush. That file mocks SimpleSelect
   to keep the assertion; the REAL Radix path is verified end-to-end in
   scripts/verify-agents-dialog-select.mjs. */

describe('agent editor — chat with this agent', () => {
  it('keeps the panel open and surfaces the error when the session cannot be created', async () => {
    // `dispatch(thunk)` RESOLVES with a rejected action; only `unwrap()` throws.
    // Without it a failed create still closed the panel and navigated to /chat,
    // silently showing whatever session happened to be active.
    mockApi.createChatSlot.mockRejectedValue(new Error('gateway is offline'))
    await renderRoster()
    const sheet = await openEditor('oncall')

    fireEvent.click(within(sheet).getByRole('button', { name: 'Chat with this agent' }))

    await waitFor(() => expect(within(sheet).getByText('gateway is offline')).toBeInTheDocument())
    expect(screen.getByRole('dialog', { name: 'Edit agent oncall' })).toBeInTheDocument()
  })
})

describe('agent editor — delete', () => {
  it('deletes a non-default agent only after a confirm step', async () => {
    await renderRoster()
    const sheet = await openEditor('oncall')

    // First press arms the confirm; it must NOT delete. A one-click destructive
    // button in a slide-in panel was the flagged regret risk.
    gotoPane(sheet, 'danger')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Delete agent' }))
    expect(mockApi.deleteWardingAgent).not.toHaveBeenCalled()
    expect(within(sheet).getByText(/Delete agent oncall\?/)).toBeInTheDocument()

    fireEvent.click(within(sheet).getByTestId('confirm-delete-agent'))
    await waitFor(() => expect(mockApi.deleteWardingAgent).toHaveBeenCalledWith('oncall'))
  })

  it('abandons the delete when the confirm step is cancelled', async () => {
    await renderRoster()
    const sheet = await openEditor('oncall')

    gotoPane(sheet, 'danger')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Delete agent' }))
    fireEvent.click(within(sheet).getByTestId('cancel-delete-agent'))
    expect(within(sheet).queryByTestId('confirm-delete-agent')).not.toBeInTheDocument()
    expect(mockApi.deleteWardingAgent).not.toHaveBeenCalled()
  })

  it('hides the danger zone on the default agent', async () => {
    await renderRoster()
    const sheet = await openEditor('warding')

    // The backend refuses to delete the default agent, so the affordance is not
    // offered rather than offered-then-rejected.
    expect(within(sheet).queryByRole('button', { name: 'Delete agent' })).not.toBeInTheDocument()
    expect(within(sheet).queryByText('Danger zone')).not.toBeInTheDocument()
  })
})

describe('agent editor — keyboard', () => {
  it('closes on Escape', async () => {
    await renderRoster()
    await openEditor('oncall')

    pressEscape()
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit agent oncall' })).not.toBeInTheDocument(),
    )
  })

  /* The nested-dialog Escape test lives in AgentEditorSelect.test.tsx — reaching
     the nested dialog means driving a Radix Select from inside the Radix Dialog,
     which this harness cannot do (see that file's header). */
})

describe('AgentAvatar', () => {
  function renderAvatar(seed: string) {
    const { container, unmount } = render(<AgentAvatar seed={seed} size={38} />)
    const img = container.querySelector('img')!
    const src = img.getAttribute('src')!
    return { img, src, unmount }
  }

  it('renders a decorative img backed by a local data URI', async () => {
    const { img, src } = renderAvatar('warding')
    expect(img).toBeTruthy()
    // Generated in-process — never an http(s) URL, so no agent name leaves the
    // machine and the roster works offline.
    expect(src.startsWith('data:image/svg+xml')).toBe(true)
    expect(img).toHaveAttribute('aria-hidden', 'true')
    expect(img).toHaveAttribute('alt', '')
  })

  it('is deterministic per seed and distinct across seeds', async () => {
    const first = renderAvatar('oncall')
    first.unmount()
    const second = renderAvatar('oncall')
    expect(second.src).toBe(first.src)

    const other = renderAvatar('warding')
    expect(other.src).not.toBe(first.src)
  })
})
