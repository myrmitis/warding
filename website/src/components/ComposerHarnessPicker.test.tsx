import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import ComposerHarnessPicker from './ComposerHarnessPicker'
import { api, type RoutingChatChoice, type RoutingHarnessesView } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    routingHarnesses: vi.fn(),
    setChatHarness: vi.fn(),
  },
}))

function choice(over: Partial<RoutingChatChoice> & { id: string }): RoutingChatChoice {
  return { label: over.id, installed: true, status: 'connected', setup: null, hint: '', ...over }
}

const CHOICES: RoutingChatChoice[] = [
  choice({ id: 'auto', label: '', installed: null, status: '', resolves_to: 'claude' }),
  choice({ id: 'claude', label: 'Claude Code' }),
  choice({ id: 'codex', label: 'Codex (ChatGPT)', status: 'needs_login' }),
  choice({ id: 'opencode', label: 'OpenCode', installed: false, status: 'not_installed' }),
]

function harnessView(configured = 'claude'): RoutingHarnessesView {
  return {
    code: 'ok', enabled: true, source: 'auto', path: '', warnings: [], kinds: [], preview: {}, harnesses: [],
    chat: { configured, selected: configured === 'auto' ? 'claude' : configured, choices: CHOICES },
  } as unknown as RoutingHarnessesView
}

function renderPicker(props: { runningLabel?: string; markOnly?: boolean } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ComposerHarnessPicker markOnly={false} {...props} />
    </QueryClientProvider>,
  )
}

async function openMenu() {
  const chip = await screen.findByTestId('composer-harness')
  await waitFor(() => expect(chip.tagName).toBe('BUTTON'))
  fireEvent.keyDown(chip, { key: 'Enter' })
  return screen.findByTestId('composer-harness-menu')
}

describe('ComposerHarnessPicker', () => {
  beforeEach(() => {
    vi.mocked(api.routingHarnesses).mockReset()
    vi.mocked(api.setChatHarness).mockReset()
  })

  it('renders nothing when there is no running harness and no harness view', async () => {
    vi.mocked(api.routingHarnesses).mockResolvedValue(null as unknown as RoutingHarnessesView)
    const { container } = renderPicker()
    await waitFor(() => expect(api.routingHarnesses).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('falls back to the plain label when the gateway has no harness view', async () => {
    vi.mocked(api.routingHarnesses).mockRejectedValue(new Error('offline'))
    renderPicker({ runningLabel: 'Codex (ChatGPT)', markOnly: true })
    const chip = await screen.findByRole('img', { name: 'Running on Codex (ChatGPT)' })
    expect(chip).toHaveAttribute('data-testid', 'composer-harness')
    expect(chip.tagName).toBe('SPAN')
  })

  it('names the harness a new chat starts on and lists every choice', async () => {
    vi.mocked(api.routingHarnesses).mockResolvedValue(harnessView('claude'))
    renderPicker()
    const chip = await screen.findByRole('button', { name: 'New chats start on Claude Code.' })
    expect(chip).toHaveTextContent('Claude Code')

    const menu = await openMenu()
    expect(screen.getByTestId('composer-harness-claude')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('composer-harness-auto')).toHaveTextContent('Automatic')
    expect(screen.getByTestId('composer-harness-auto')).toHaveTextContent('Claude Code')
    expect(screen.getByTestId('composer-harness-codex')).toHaveTextContent('Needs sign-in')
    expect(screen.getByTestId('composer-harness-opencode')).toHaveTextContent('Not installed')
    expect(screen.getByTestId('composer-harness-opencode')).toHaveAttribute('data-disabled')
    expect(menu).not.toHaveTextContent('This chat stays on')
  })

  it('saves a pick and keeps the open chat on its harness', async () => {
    vi.mocked(api.routingHarnesses).mockResolvedValue(harnessView('codex'))
    vi.mocked(api.setChatHarness).mockImplementation(async () => {
      vi.mocked(api.routingHarnesses).mockResolvedValue(harnessView('claude'))
      return {}
    })
    renderPicker({ runningLabel: 'Codex (ChatGPT)' })
    expect(await screen.findByRole('button', { name: 'Running on Codex (ChatGPT)' })).toBeInTheDocument()

    const menu = await openMenu()
    expect(menu).toHaveTextContent('Your pick applies to new chats. This chat stays on Codex (ChatGPT).')
    fireEvent.click(screen.getByTestId('composer-harness-claude'))

    await waitFor(() => expect(api.setChatHarness).toHaveBeenCalledWith('claude'))
    await waitFor(() => expect(screen.getByTestId('composer-harness-claude')).toHaveAttribute('aria-checked', 'true'))
    // The chip still names what this chat runs on.
    expect(screen.getByTestId('composer-harness')).toHaveTextContent('Codex (ChatGPT)')
  })

  it('says why a save was refused', async () => {
    vi.mocked(api.routingHarnesses).mockResolvedValue(harnessView('claude'))
    vi.mocked(api.setChatHarness).mockRejectedValue(Object.assign(new Error('400'), {
      body: JSON.stringify({ code: 'unknown_harness' }),
    }))
    renderPicker()
    await openMenu()
    fireEvent.click(screen.getByTestId('composer-harness-auto'))
    expect(await screen.findByRole('alert')).toHaveTextContent('cannot run that agent')
  })
})
