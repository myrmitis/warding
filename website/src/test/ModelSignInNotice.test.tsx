import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Provider } from 'react-redux'
import { configureStore } from '@reduxjs/toolkit'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import ModelEffortDropdown from '../components/ModelEffortDropdown'
import ModelSignInNotice from '../components/ModelSignInNotice'
import chatReducer from '../store/chatSlice'
import dashboardReducer from '../store/dashboardSlice'
import notificationsReducer from '../store/notificationsSlice'
import { api } from '../api/client'

/**
 * `/api/models` has nothing to list for an agent that is not signed in, so the
 * picker would offer Auto alone with no explanation. The notice says what to
 * do, and "Check again" asks the gateway to start the agent once so the list
 * heals right after the user signs in.
 */
const info = { harness: 'codex', agent: 'Codex (ChatGPT)', login: 'codex login' }

const baseProps = {
  anchorRect: { right: 400, top: 300 } as DOMRect,
  dropdownRef: React.createRef<HTMLDivElement>(),
  inputRef: React.createRef<HTMLInputElement>(),
  models: [{ name: 'auto', description: 'Default' }],
  activeModel: 'auto',
  onSelectModel: vi.fn(),
  filter: '',
  setFilter: vi.fn(),
  onClose: vi.fn(),
  hasEffort: false,
  slot: 'dashboard:1',
  currentEffort: '',
  onListKeyDown: vi.fn(),
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const store = configureStore({
    reducer: { dashboard: dashboardReducer, chat: chatReducer, notifications: notificationsReducer },
  })
  const invalidate = vi.spyOn(qc, 'invalidateQueries')
  render(<Provider store={store}><QueryClientProvider client={qc}>{ui}</QueryClientProvider></Provider>)
  return { invalidate }
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('ModelSignInNotice', () => {
  it('names the agent and shows its command in a code span', () => {
    wrap(<ModelSignInNotice info={info} />)
    const notice = screen.getByTestId('model-sign-in-notice')
    expect(notice).toHaveTextContent('Sign in to see Codex (ChatGPT) models')
    expect(notice).toHaveTextContent('Run codex login in a terminal, then check again.')
    expect(notice.querySelector('code')?.textContent).toBe('codex login')
  })

  it('names no command for an agent that publishes none', () => {
    wrap(<ModelSignInNotice info={{ harness: 'kimi', agent: 'Kimi Code', login: '' }} />)
    const notice = screen.getByTestId('model-sign-in-notice')
    expect(notice).toHaveTextContent('Sign in to Kimi Code, then check again.')
    expect(notice.querySelector('code')).toBeNull()
  })

  it('Check again starts the agent once and refreshes the model list', async () => {
    const check = vi.spyOn(api, 'checkRoutingHarness').mockResolvedValue({
      code: 'ok',
      harness: 'codex',
      probe: { status: 'connected', detail: '', models: 3, checked_at: 1 },
    } as never)
    const { invalidate } = wrap(<ModelSignInNotice info={info} />)

    fireEvent.click(screen.getByTestId('model-sign-in-check'))

    await waitFor(() => expect(check).toHaveBeenCalledWith('codex'))
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['available-models'] }),
    )
    expect(screen.queryByText('Still not signed in.')).toBeNull()
  })

  it('says so when the check finds the agent still signed out', async () => {
    vi.spyOn(api, 'checkRoutingHarness').mockResolvedValue({
      code: 'ok',
      harness: 'codex',
      probe: { status: 'needs_login', detail: '', models: 0, checked_at: 1 },
    } as never)
    wrap(<ModelSignInNotice info={info} />)

    fireEvent.click(screen.getByTestId('model-sign-in-check'))

    expect(await screen.findByText('Still not signed in.')).toBeInTheDocument()
  })

  it('disables the button while a check is running', async () => {
    let release: (v: never) => void = () => {}
    vi.spyOn(api, 'checkRoutingHarness').mockReturnValue(new Promise(r => { release = r as never }))
    wrap(<ModelSignInNotice info={info} />)

    fireEvent.click(screen.getByTestId('model-sign-in-check'))

    await waitFor(() => expect((screen.getByTestId('model-sign-in-check') as HTMLButtonElement).disabled).toBe(true))
    release({ code: 'ok', harness: 'codex', probe: { status: 'connected' } } as never)
  })
})

describe('ModelEffortDropdown — sign-in state', () => {
  it('renders the notice above the list when the agent needs a sign-in', () => {
    wrap(<ModelEffortDropdown {...baseProps} signIn={info} />)
    expect(screen.getByTestId('model-sign-in-notice')).toBeInTheDocument()
    // Auto is still offered: it resolves server-side once the agent is signed in.
    expect(screen.getByRole('listbox')).toBeInTheDocument()
  })

  it('renders nothing extra for a signed-in agent', () => {
    wrap(<ModelEffortDropdown {...baseProps} />)
    expect(screen.queryByTestId('model-sign-in-notice')).toBeNull()
    wrap(<ModelEffortDropdown {...baseProps} signIn={null} />)
    expect(screen.queryByTestId('model-sign-in-notice')).toBeNull()
  })
})
