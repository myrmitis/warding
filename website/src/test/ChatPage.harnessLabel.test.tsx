/**
 * The composer names the harness the gateway says serves the session.
 *
 * `harness` rides on the slot the gateway serializes: the backend of the
 * session's latest turn, which stays the one it started on when
 * `agent.acp_backend` changes under an open chat. The label is read from the slot,
 * never derived from config in the browser, so a slot that has run no turn shows
 * nothing rather than a guess.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { Provider } from 'react-redux'
import { MemoryRouter } from 'react-router-dom'
import { configureStore } from '@reduxjs/toolkit'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import chatReducer from '../store/chatSlice'
import dashboardReducer from '../store/dashboardSlice'
import notificationsReducer from '../store/notificationsSlice'
import { ThemeProvider } from '../hooks/useTheme'
import type { RootState } from '../store'

interface VirtuosoMockProps {
  data?: unknown[]
  itemContent: (index: number, item: unknown) => ReactNode
}
vi.mock('react-virtuoso', () => ({ Virtuoso: ({ data, itemContent }: VirtuosoMockProps) => <div data-testid="virtuoso">{data?.map((d: unknown, i: number) => <div key={i}>{itemContent(i, d)}</div>)}</div> }))
vi.mock('../api/client', () => ({
  api: {
    chatSlots: vi.fn().mockResolvedValue([]),
    chatSlotDetail: vi.fn().mockResolvedValue({ messages: [], running: false, has_more: false, total: 0 }),
    chatHistory: vi.fn().mockResolvedValue({ sessions: [] }),
    models: vi.fn().mockResolvedValue([
      { model_name: 'auto', description: 'Models chosen by task' },
      { model_name: 'claude-opus-5', description: 'Claude Opus 5' },
      { model_name: 'claude-sonnet-5', description: 'Claude Sonnet 5' },
    ]),
    agents: vi.fn().mockResolvedValue([]),
    agentDetail: vi.fn().mockResolvedValue({ model: 'claude-opus-5' }),
    // The backend resolver owns the default-model precedence; the composer
    // asks it what an un-pinned slot would run on.
    agentResolvedModel: vi.fn().mockResolvedValue({ model: 'claude-opus-5' }),
    chatSlotModel: vi.fn().mockResolvedValue({ ok: true }),
    workspaces: vi.fn().mockResolvedValue({ workspaces: [] }),
    slackChannels: vi.fn().mockResolvedValue([]),
    spawnList: vi.fn().mockResolvedValue({ agents: [] }),
  },
  SEARCH_MIN_CHARS: 2,
}))
vi.mock('../hooks/useVoiceInput', () => ({ useVoiceInput: () => ({ recording: false, transcribing: false, toggle: vi.fn() }), voiceInputSupported: false }))
vi.mock('../hooks/useBranding', () => ({ useBranding: () => ({ botName: 'Test', avatar: '' }) }))
vi.mock('../hooks/useAgents', () => ({ useAgents: () => ({ agents: [{ name: 'warding' }], defaultAgent: 'warding' }) }))
vi.mock('../components/MarkdownRenderer', () => ({ default: ({ content }: { content: string }) => <span>{content}</span> }))
vi.mock('../components/WelcomeView', () => ({ default: () => null }))
vi.mock('../components/MarkdownPanel', () => ({ default: () => null }))
vi.mock('../pages/chat/ActivityViewer', () => ({ default: () => null }))
vi.mock('../components/DetailPanel', () => ({ default: () => null }))
vi.mock('../hooks/useWebSocket', () => ({ useWebSocket: () => ({ subscribeLogs: () => {} }) }))

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
})

import ChatPage from '../pages/ChatPage'

function makeStore(harness?: { id: string; label: string } | null) {
  return configureStore({
    reducer: { dashboard: dashboardReducer, chat: chatReducer, notifications: notificationsReducer },
    preloadedState: {
      dashboard: {
        status: null,
        slots: [{ key: 'slot-a', messages: 0, running: false, mode: '', agent: 'warding', model: 'auto', harness, pending_approval: false, waiting_for_input: false, last_activity_ts: undefined }],
        unreadSlots: [], refreshTrigger: 0, approvalMode: 'normal',
        subagentRunning: {}, subagentDetails: {}, subagentText: {},
      } as unknown as RootState['dashboard'],
      chat: {
        activeSlot: 'slot-a', messages: [],
        slotRunning: false, slotStopping: false, slotState: 'idle',
        history: [], historyHasMore: false, pendingInput: null,
        subagents: {}, toolLog: [], activityOpen: false, activityTab: 'tools',
        slotHasMore: false, slotOldestIndex: 0, loadingOlder: false,
        slotStatusDetail: {}, slotContextPct: {}, slotActivity: {}, slotHistory: [],
        historyOffset: 0, _wsChunkedDuringFetch: false,
        slotMessages: {}, slotLoading: false,
      } as unknown as RootState['chat'],
      notifications: { items: [] } as unknown as RootState['notifications'],
    },
  })
}

async function renderChat(harness?: { id: string; label: string } | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    render(
      <QueryClientProvider client={qc}>
        <Provider store={makeStore(harness)}>
          <ThemeProvider>
            <MemoryRouter><ChatPage /></MemoryRouter>
          </ThemeProvider>
        </Provider>
      </QueryClientProvider>,
    )
  })
  await waitFor(() => expect(screen.getByLabelText('Message input')).toBeTruthy())
}

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  vi.clearAllMocks()
})

describe('ChatPage — harness label', { timeout: 15_000 }, () => {
  it('names the harness the slot reports, next to the model', async () => {
    await renderChat({ id: 'codex', label: 'Codex (ChatGPT)' })
    const label = await waitFor(() => screen.getByTestId('composer-harness'))
    expect(label.textContent).toBe('Codex (ChatGPT)')
    expect(label.getAttribute('title')).toBe('Running on Codex (ChatGPT)')
  })

  it('shows nothing for a slot the gateway has no harness for yet', async () => {
    await renderChat(null)
    await waitFor(() => screen.getByTitle('Model: auto'))
    expect(screen.queryByTestId('composer-harness')).toBeNull()
  })

  it('shows nothing for a gateway that does not report one', async () => {
    await renderChat(undefined)
    await waitFor(() => screen.getByTitle('Model: auto'))
    expect(screen.queryByTestId('composer-harness')).toBeNull()
  })
})
