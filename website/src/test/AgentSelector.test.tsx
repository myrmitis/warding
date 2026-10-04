import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AgentSelector from '../components/AgentSelector'
import type { JunctionAgent } from '../components/AgentSelector'

const agents: JunctionAgent[] = [
  { name: 'coding', kiro_agent: 'junction', workspace: 'default', memory_store: 'default' },
  { name: 'oncall', kiro_agent: 'ops-agent', workspace: 'oncall', memory_store: 'oncall-kb' },
  { name: 'research', kiro_agent: 'junction', workspace: 'research', memory_store: 'research-mem' },
]

describe('AgentSelector', () => {
  it('renders current agent name', () => {
    render(<AgentSelector agents={agents} defaultAgent="coding" value="coding" onChange={() => {}} />)
    expect(screen.getByText('coding')).toBeInTheDocument()
  })

  it('shows dropdown on click', () => {
    render(<AgentSelector agents={agents} defaultAgent="coding" value="coding" onChange={() => {}} />)
    fireEvent.click(screen.getByLabelText('Switch agent'))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
  })

  it('displays kiro_agent as subtitle', () => {
    render(<AgentSelector agents={agents} defaultAgent="coding" value="coding" onChange={() => {}} />)
    fireEvent.click(screen.getByLabelText('Switch agent'))
    expect(screen.getByText('ops-agent')).toBeInTheDocument()
  })

  it('marks default agent with badge', () => {
    render(<AgentSelector agents={agents} defaultAgent="coding" value="oncall" onChange={() => {}} />)
    fireEvent.click(screen.getByLabelText('Switch agent'))
    expect(screen.getByText('default')).toBeInTheDocument()
  })

  it('calls onChange with Junction agent name on selection', () => {
    const onChange = vi.fn()
    render(<AgentSelector agents={agents} defaultAgent="coding" value="coding" onChange={onChange} />)
    fireEvent.click(screen.getByLabelText('Switch agent'))
    fireEvent.click(screen.getByText('oncall'))
    expect(onChange).toHaveBeenCalledWith('oncall')
  })

  it('uses defaultAgent when value is empty', () => {
    render(<AgentSelector agents={agents} defaultAgent="coding" value="" onChange={() => {}} />)
    expect(screen.getByText('coding')).toBeInTheDocument()
  })
})
