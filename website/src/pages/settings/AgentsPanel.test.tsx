import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { AgentsPanel } from './AgentsPanel'
import {
  api,
  type RoutingChatChoice,
  type RoutingChatHarness,
  type RoutingHarnessRow,
  type RoutingHarnessesView,
} from '../../api/client'

vi.mock('../../api/client', () => ({
  api: {
    routingHarnesses: vi.fn(),
    checkRoutingHarness: vi.fn(),
    editRoutingLane: vi.fn(),
    editRoutingSettings: vi.fn(),
    clearRoutingCooldown: vi.fn(),
    setChatHarness: vi.fn(),
  },
}))

const terminal = vi.hoisted(() => ({ enabled: true, sent: [] as string[] }))
vi.mock('../../utils/terminalRegistry', () => ({
  useTerminalEnabled: () => terminal.enabled,
  onTerminalReady: (_id: string, cb: () => void) => { cb(); return () => {} },
  sendToTerminalSession: (_id: string, code: string) => { terminal.sent.push(code); return true },
}))
vi.mock('../../hooks/useBottomTerminal', () => ({ addTab: () => 'term-1' }))
const clipboard = vi.hoisted(() => ({ copied: [] as string[] }))
vi.mock('../../utils/clipboard', () => ({
  copyToClipboard: async (text: string) => { clipboard.copied.push(text); return true },
}))

function row(over: Partial<RoutingHarnessRow>): RoutingHarnessRow {
  return {
    harness: 'codex',
    label: 'Codex (ChatGPT)',
    billing: 'subscription',
    featured: true,
    installed: true,
    setup: { install: 'npm i -g @openai/codex', login: 'codex login', docs_url: 'https://example.test/codex' },
    hint: '',
    lane: {
      id: 'codex', harness: 'codex', label: 'Codex (ChatGPT)', billing: 'subscription', enabled: true,
      weight: 1, model: '', window_hours: 5, window_limit: 0, daily_limit: 0,
    },
    lane_count: 1,
    routed: true,
    window_used: 2,
    day_used: 3,
    cooldown_until: 0,
    cooldown_reason: '',
    probe: { status: 'connected', detail: '', models: 4, checked_at: 1_800_000_000 },
    ...over,
  }
}

function view(rows: RoutingHarnessRow[]): RoutingHarnessesView {
  return {
    code: 'ok', enabled: true, source: 'auto', path: '/home/x/.warding/routing.json', warnings: [],
    kinds: ['plan', 'implement'], preview: { plan: 'codex', implement: '' }, harnesses: rows,
  }
}

function choice(over: Partial<RoutingChatChoice> & { id: string }): RoutingChatChoice {
  return {
    label: over.id, installed: true, status: 'connected', setup: null, hint: '', ...over,
  }
}

const AUTO = choice({ id: 'auto', label: '', installed: null, status: '', resolves_to: 'claude' })
const CLAUDE = choice({
  id: 'claude', label: 'Claude Code',
  setup: { install: 'npm i -g claude', login: 'claude auth login', docs_url: 'https://example.test/claude' },
})
const CODEX_NEEDS_LOGIN = choice({
  id: 'codex', label: 'Codex (ChatGPT)', status: 'needs_login',
  setup: { install: 'npm i -g @openai/codex', login: 'codex login', docs_url: 'https://example.test/codex' },
})
const CURSOR_MISSING = choice({
  id: 'cursor', label: 'Cursor Agent', installed: false, status: 'not_installed',
  setup: { install: 'curl cursor | bash', login: 'cursor-agent login', docs_url: 'https://example.test/cursor' },
})
const KIRO_MISSING = choice({
  id: 'kiro', label: 'Kiro CLI', installed: false, status: 'not_installed', hint: 'Optional. Install kiro-cli.',
})

function chat(over: Partial<RoutingChatHarness> = {}): RoutingChatHarness {
  return {
    configured: 'auto',
    selected: 'claude',
    choices: [AUTO, CLAUDE, CODEX_NEEDS_LOGIN, CURSOR_MISSING, KIRO_MISSING],
    ...over,
  }
}

function withChat(rows: RoutingHarnessRow[], c: RoutingChatHarness | undefined): RoutingHarnessesView {
  return { ...view(rows), chat: c }
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AgentsPanel />
    </QueryClientProvider>,
  )
}

const harnesses = vi.mocked(api.routingHarnesses)
const checkHarness = vi.mocked(api.checkRoutingHarness)
const editLane = vi.mocked(api.editRoutingLane)
const editSettings = vi.mocked(api.editRoutingSettings)
const setChatHarness = vi.mocked(api.setChatHarness)

beforeEach(() => {
  vi.clearAllMocks()
  terminal.enabled = true
  terminal.sent = []
  clipboard.copied = []
  checkHarness.mockResolvedValue({ code: 'ok', harness: 'codex', probe: row({}).probe })
  editLane.mockResolvedValue({ code: 'ok', lane: row({}).lane! })
  editSettings.mockResolvedValue({ code: 'ok', settings: { route_tasks: true } })
})

describe('AgentsPanel', () => {
  it('shows each agent with its connection status and the routing picks', async () => {
    harnesses.mockResolvedValue(view([
      row({}),
      row({
        harness: 'grok', label: 'Grok Build', lane: null, routed: false,
        probe: { status: 'needs_login', detail: 'Authentication required', models: 0, checked_at: 1_800_000_000 },
        setup: { install: 'npm i -g @xai-official/grok', login: 'grok login', docs_url: 'https://example.test/grok' },
      }),
      row({ harness: 'cursor', label: 'Cursor Agent', installed: false, lane: null, routed: false }),
    ]))
    mount()

    const codex = await screen.findByTestId('agent-codex')
    expect(within(codex).getByText('Connected')).toBeInTheDocument()
    const grok = await screen.findByTestId('agent-grok')
    expect(within(grok).getByText('Needs sign-in')).toBeInTheDocument()
    // The status says it; the agent's own words are not repeated under it.
    expect(screen.queryByText('Authentication required')).toBeNull()
    expect(within(screen.getByTestId('agent-cursor')).getByText('Not installed')).toBeInTheDocument()
    // The pick grid names the lane's agent, and says so when a kind has none.
    expect(screen.getByText('Planning')).toBeInTheDocument()
    expect(screen.getByText('No agent available')).toBeInTheDocument()
  })

  it('shows Needs sign-in and the command, never a raw JSON-RPC error, for a refused sign-in', async () => {
    const raw = "JSON-RPC error: {'code': -32000, 'message': 'Authentication required'}"
    harnesses.mockResolvedValue(view([
      row({ probe: { status: 'needs_login', detail: raw, models: 0, checked_at: 1_800_000_000 } }),
    ]))
    mount()

    const codex = await screen.findByTestId('agent-codex')
    expect(within(codex).getByText('Needs sign-in')).toBeInTheDocument()
    expect(codex.textContent).not.toMatch(/JSON-RPC|-32000|Authentication required/)
    // The command is on screen for the user to run or copy.
    expect(screen.getByText('codex login')).toBeInTheDocument()
    expect(within(codex).getByRole('button', { name: /Sign in/ })).toBeInTheDocument()
  })

  it('still shows the detail for a failure that is not a sign-in', async () => {
    harnesses.mockResolvedValue(view([
      row({ probe: { status: 'error', detail: 'spawn failed: EACCES', models: 0, checked_at: 1_800_000_000 } }),
    ]))
    mount()

    expect(await screen.findByText('spawn failed: EACCES')).toBeInTheDocument()
  })

  it('runs the sign-in command in the dock terminal', async () => {
    harnesses.mockResolvedValue(view([
      row({ probe: { status: 'needs_login', detail: '', models: 0, checked_at: 1 } }),
    ]))
    mount()

    fireEvent.click(await screen.findByRole('button', { name: /Sign in/ }))
    await waitFor(() => expect(terminal.sent).toEqual(['codex login']))
    expect(await screen.findByText('Opened in terminal')).toBeInTheDocument()
  })

  it('copies the command instead when the terminal is off', async () => {
    terminal.enabled = false
    harnesses.mockResolvedValue(view([row({ installed: false, lane: null })]))
    mount()

    fireEvent.click(await screen.findByRole('button', { name: /Install/ }))
    await waitFor(() => expect(clipboard.copied).toEqual(['npm i -g @openai/codex']))
    expect(terminal.sent).toEqual([])
  })

  it('probes installed agents that were never checked, once', async () => {
    harnesses.mockResolvedValue(view([
      row({ probe: { status: 'unknown', detail: '', models: 0, checked_at: 0 } }),
      row({ harness: 'cursor', installed: false, lane: null, probe: { status: 'unknown', detail: '', models: 0, checked_at: 0 } }),
    ]))
    mount()

    await waitFor(() => expect(checkHarness).toHaveBeenCalledTimes(1))
    expect(checkHarness).toHaveBeenCalledWith('codex')
  })

  it('writes routing changes for that agent', async () => {
    harnesses.mockResolvedValue(view([row({})]))
    mount()

    fireEvent.click(await screen.findByRole('switch', { name: /Use for routing/ }))
    await waitFor(() => expect(editLane).toHaveBeenCalledWith('codex', { enabled: false }))
  })

  it('offers the install command when an installed agent is missing a piece', async () => {
    // Claude Code without its ACP adapter: the CLI is on PATH, but the probe
    // says not installed, so Sign in would be the wrong next step.
    harnesses.mockResolvedValue(view([row({
      harness: 'claude', label: 'Claude Code',
      setup: { install: 'npm i -g claude-pieces', login: 'claude auth login', docs_url: 'https://example.test/c' },
      probe: { status: 'not_installed', detail: 'claude-agent-acp not found', models: 0, checked_at: 1 },
    })]))
    mount()

    const card = await screen.findByTestId('agent-claude')
    expect(within(card).getByText('Not installed')).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: /Sign in/ })).toBeNull()
    fireEvent.click(within(card).getByRole('button', { name: /Install/ }))
    await waitFor(() => expect(terminal.sent).toEqual(['npm i -g claude-pieces']))
  })

  it('turns Task Runner step routing on and off', async () => {
    harnesses.mockResolvedValue({ ...view([row({})]), route_tasks: false })
    mount()

    const toggle = await screen.findByRole('switch', { name: /Route Task Runner steps/ })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(toggle.closest('[data-setting-key]')).toHaveAttribute('data-setting-key', 'routing.route_tasks')
    fireEvent.click(toggle)
    await waitFor(() => expect(editSettings).toHaveBeenCalledWith({ route_tasks: true }))
  })

  it('leaves step routing out of the first-run view', async () => {
    harnesses.mockResolvedValue({ ...view([row({})]), route_tasks: true })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AgentsPanel compact />
      </QueryClientProvider>,
    )
    await screen.findByTestId('agent-codex')
    expect(screen.queryByRole('switch', { name: /Route Task Runner steps/ })).toBeNull()
  })

  it('fills in the installed and model counts', async () => {
    harnesses.mockResolvedValue(view([row({})]))
    mount()

    expect(await screen.findByText('Installed: 1')).toBeInTheDocument()
    expect(screen.getByText(/Models: 4/)).toBeInTheDocument()
  })

  it('commits plan and model edits on blur or Enter, and resets invalid numbers', async () => {
    harnesses.mockResolvedValue(view([row({})]))
    mount()
    await screen.findByTestId('agent-codex')
    const numbers = screen.getAllByRole('spinbutton')
    fireEvent.change(numbers[0], { target: { value: '-1' } })
    fireEvent.blur(numbers[0])
    expect(numbers[0]).toHaveValue(1)
    expect(editLane).not.toHaveBeenCalled()
    fireEvent.change(numbers[0], { target: { value: '2' } })
    fireEvent.keyDown(numbers[0], { key: 'Enter' })
    await waitFor(() => expect(editLane).toHaveBeenCalledWith('codex', { weight: 2 }))
    fireEvent.change(numbers[1], { target: { value: '101.6' } })
    fireEvent.blur(numbers[1])
    await waitFor(() => expect(editLane).toHaveBeenCalledWith('codex', { window_limit: 102 }))
    const model = screen.getByRole('textbox')
    fireEvent.change(model, { target: { value: '  served-model  ' } })
    fireEvent.keyDown(model, { key: 'Enter' })
    await waitFor(() => expect(editLane).toHaveBeenCalledWith('codex', { model: 'served-model' }))
  })

  it('clears only the selected lane cooldown when resumed', async () => {
    vi.mocked(api.clearRoutingCooldown).mockResolvedValue({ code: 'ok', cleared: ['codex'] })
    harnesses.mockResolvedValue(view([row({ cooldown_until: 1_900_000_000 })]))
    mount()
    fireEvent.click(await screen.findByRole('button', { name: /Resume now/ }))
    await waitFor(() => expect(api.clearRoutingCooldown).toHaveBeenCalledWith('codex'))
  })

  describe('chat harness picker', () => {
    const rows = [row({})]

    it('lists exactly the gateway\'s choices, each with its status', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat()))
      mount()

      const group = await screen.findByRole('radiogroup', { name: 'Chat harness' })
      const names = within(group).getAllByRole('radio').map(r => r.textContent)
      expect(names).toHaveLength(5)
      expect(within(screen.getByTestId('chat-harness-claude')).getByText('Connected')).toBeInTheDocument()
      expect(within(screen.getByTestId('chat-harness-codex')).getByText('Needs sign-in')).toBeInTheDocument()
      expect(within(screen.getByTestId('chat-harness-cursor')).getByText('Not installed')).toBeInTheDocument()
      // Kiro is offered whatever the host has, and says it is missing.
      expect(within(screen.getByTestId('chat-harness-kiro')).getByText('Not installed')).toBeInTheDocument()
    })

    it('marks the configured choice, and says what Automatic resolves to', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat()))
      mount()

      const auto = await screen.findByRole('radio', { name: /Automatic/ })
      expect(auto).toHaveAttribute('aria-checked', 'true')
      expect(screen.getByRole('radio', { name: /Claude Code/ })).toHaveAttribute('aria-checked', 'false')
      expect(screen.getByText('The first installed agent. Right now: Claude Code.')).toBeInTheDocument()
      expect(screen.getByText('New chats start on Claude Code.')).toBeInTheDocument()
    })

    it('keeps naming what Automatic would pick while another harness is chosen', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat({ configured: 'codex', selected: 'codex' })))
      mount()

      expect(await screen.findByText('The first installed agent. Right now: Claude Code.')).toBeInTheDocument()
      expect(screen.getByText('New chats start on Codex (ChatGPT).')).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /Automatic/ })).toHaveAttribute('aria-checked', 'false')
      expect(screen.getByRole('radio', { name: /Codex \(ChatGPT\)/ })).toHaveAttribute('aria-checked', 'true')
    })

    it('says plainly that it applies to new chats and open chats keep theirs', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat()))
      mount()

      expect(await screen.findByText(/A chat that is already open keeps the one it started with until it ends/)).toBeInTheDocument()
    })

    it('disables a harness that is not installed, with the reason', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat()))
      mount()

      const cursor = await screen.findByRole('radio', { name: /Cursor Agent/ })
      expect(cursor).toBeDisabled()
      fireEvent.click(cursor)
      expect(setChatHarness).not.toHaveBeenCalled()
      expect(within(screen.getByTestId('chat-harness-cursor')).getByText(/Not installed\. Install it below/)).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /Kiro CLI/ })).toBeDisabled()
    })

    it('still lets a harness that needs sign-in be chosen, and shows its sign-in command', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat()))
      setChatHarness.mockResolvedValue({})
      mount()

      const codex = await screen.findByRole('radio', { name: /Codex \(ChatGPT\)/ })
      expect(codex).toBeEnabled()
      const card = screen.getByTestId('chat-harness-codex')
      expect(within(card).getByText('codex login')).toBeInTheDocument()
      expect(within(card).getByText(/Chats on it fail until it is signed in/)).toBeInTheDocument()
      fireEvent.click(codex)
      await waitFor(() => expect(setChatHarness).toHaveBeenCalledWith('codex'))
    })

    it('writes the choice and re-reads the view', async () => {
      harnesses.mockResolvedValueOnce(withChat(rows, chat()))
      harnesses.mockResolvedValue(withChat(rows, chat({ configured: 'claude', selected: 'claude' })))
      setChatHarness.mockResolvedValue({})
      mount()

      fireEvent.click(await screen.findByRole('radio', { name: /Claude Code/ }))
      await waitFor(() => expect(setChatHarness).toHaveBeenCalledWith('claude'))
      await waitFor(() => expect(screen.getByRole('radio', { name: /Claude Code/ })).toHaveAttribute('aria-checked', 'true'))
      expect(harnesses.mock.calls.length).toBeGreaterThan(1)
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })

    it('does not write again for the harness that is already chosen', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat({ configured: 'claude' })))
      mount()

      fireEvent.click(await screen.findByRole('radio', { name: /Claude Code/ }))
      expect(setChatHarness).not.toHaveBeenCalled()
    })

    it('maps an unknown_harness refusal to its own message', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat()))
      setChatHarness.mockRejectedValue(Object.assign(new Error('refused'), {
        body: JSON.stringify({ error: 'Unknown harness', code: 'unknown_harness' }),
      }))
      mount()

      fireEvent.click(await screen.findByRole('radio', { name: /Claude Code/ }))
      expect(await screen.findByText(/cannot run that agent, so nothing was changed\./)).toBeInTheDocument()
    })

    it('shows a generic message for any other failure', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat()))
      setChatHarness.mockRejectedValue(new Error('boom'))
      mount()

      fireEvent.click(await screen.findByRole('radio', { name: /Claude Code/ }))
      expect(await screen.findByText('Could not change the chat harness.')).toBeInTheDocument()
    })

    it('says so when a local override keeps a different harness', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat({ configured: 'auto' })))
      setChatHarness.mockResolvedValue({})
      mount()

      fireEvent.click(await screen.findByRole('radio', { name: /Claude Code/ }))
      expect(await screen.findByText(/config\.local\.json sets a different agent/)).toBeInTheDocument()
    })

    it('says no agent can start a chat when nothing is installed', async () => {
      harnesses.mockResolvedValue(withChat([], chat({
        selected: '', choices: [{ ...AUTO, resolves_to: '' }, CURSOR_MISSING, KIRO_MISSING],
      })))
      mount()

      expect(await screen.findByText('No installed agent can start a chat yet. Install one below.')).toBeInTheDocument()
      expect(screen.getByText('The first installed agent. None is installed yet.')).toBeInTheDocument()
    })

    it('is absent from a gateway that does not report it', async () => {
      harnesses.mockResolvedValue(withChat(rows, undefined))
      mount()

      await screen.findByTestId('agent-codex')
      expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    })

    it('is not part of the first-run panel', async () => {
      harnesses.mockResolvedValue(withChat(rows, chat()))
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={qc}>
          <AgentsPanel compact />
        </QueryClientProvider>,
      )

      await screen.findByTestId('agent-codex')
      expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    })
  })
})
