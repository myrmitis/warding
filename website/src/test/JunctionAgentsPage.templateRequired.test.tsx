/* The agent create sheet must not pre-fill the Agent Template field.
 *
 * It used to open with `junction` already selected, so an agent created without
 * touching that field became an alias for the DEFAULT agent: dispatch flattens an
 * agent alias to its `kiro_agent` pointer, so the agent appeared in the chat
 * picker and then the default answered — reported as "the picker falls back to
 * the default". These tests pin that the field starts UNSELECTED and
 * that Create refuses until it is chosen, so the broken row cannot be minted.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders } from './helpers'
import JunctionAgentsPage from '../pages/JunctionAgentsPage'

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as typeof ResizeObserver

const mockCreate = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    junctionAgents: vi.fn().mockResolvedValue({ agents: [], default_agent: 'junction' }),
    agentsInstalled: vi.fn().mockResolvedValue([{ name: 'junction' }, { name: 'reviewer' }]),
    workspaces: vi.fn().mockResolvedValue({ workspaces: [{ name: 'default', dir: 'workspace' }] }),
    junctionConfig: vi.fn().mockResolvedValue({ memory_stores: { default: {} } }),
    agentResolvedModel: vi.fn().mockResolvedValue({ model: '' }),
    createJunctionAgent: (...args: unknown[]) => mockCreate(...args),
    updateJunctionAgent: vi.fn().mockResolvedValue({}),
    deleteJunctionAgent: vi.fn().mockResolvedValue({}),
    setDefaultAgent: vi.fn().mockResolvedValue({}),
    createWorkspace: vi.fn().mockResolvedValue({}),
  },
}))

async function openCreateSheet() {
  renderWithProviders(<JunctionAgentsPage />)
  const newAgent = await screen.findByTestId('new-agent')
  fireEvent.click(newAgent)
  return newAgent
}

describe('agent create sheet — Agent Template must be explicit', () => {
  beforeEach(() => {
    mockCreate.mockReset()
    mockCreate.mockResolvedValue({ ok: true })
  })

  it('opens with the template unselected, showing the placeholder', async () => {
    await openCreateSheet()
    const trigger = await screen.findByRole('combobox', { name: 'Agent Template' })
    // The placeholder, NOT a pre-selected 'junction'. Asserting the absence of
    // the old default is the actual regression: a trigger that reads 'junction'
    // is the bug, however the placeholder happens to render.
    expect(trigger).toHaveTextContent('Select an agent template…')
    expect(trigger).not.toHaveTextContent('junction')
  })

  it('refuses Create while no template is chosen, and does not call the API', async () => {
    await openCreateSheet()
    // Queried by placeholder: the Name field is labelled by its surrounding
    // <Field>, which does not wire htmlFor, so getByLabelText does not resolve it.
    fireEvent.change(await screen.findByPlaceholderText('e.g. oncall'), {
      target: { value: 'researcher' },
    })
    fireEvent.click(screen.getByText('Create'))

    await waitFor(() =>
      expect(screen.getByText('Agent Template is required')).toBeInTheDocument(),
    )
    // The guard's whole point: no request is issued, so the server's own
    // refusal is a backstop rather than the only line of defence.
    expect(mockCreate).not.toHaveBeenCalled()
  })
})
