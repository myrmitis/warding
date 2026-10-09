import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { ErrorCard } from '../pages/chat/ErrorCard'

/**
 * The error row used to be an actionless div whose own copy told the reader to
 * retry. These tests pin the two shapes: settled (no action) and resumable
 * (Continue), plus the guard that a press cannot double-fire.
 */
describe('ErrorCard', () => {
  it('renders the prose verbatim with no action when the turn is not resumable', () => {
    render(<ErrorCard content="⟳ Connection lost — please retry." />)
    expect(screen.getByTestId('error-card')).toHaveTextContent('⟳ Connection lost — please retry.')
    // Deliberately ABSENT rather than disabled: a permanently greyed button on a
    // red card reads as a broken feature.
    expect(screen.queryByTestId('error-card-continue')).toBeNull()
  })

  it('renders a Continue action when the turn is resumable', () => {
    render(<ErrorCard content="boom" onContinue={() => {}} />)
    expect(screen.getByTestId('error-card-continue')).toBeTruthy()
    expect(screen.getByTestId('error-card')).toHaveAttribute('data-continuable', 'true')
  })

  it('invokes onContinue on press', () => {
    const onContinue = vi.fn()
    render(<ErrorCard content="boom" onContinue={onContinue} />)
    fireEvent.click(screen.getByTestId('error-card-continue'))
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it('disables the action while a continue is in flight', () => {
    const onContinue = vi.fn()
    render(<ErrorCard content="boom" onContinue={onContinue} continuing />)
    const btn = screen.getByTestId('error-card-continue') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(onContinue).not.toHaveBeenCalled()
  })

  it('keeps the error prose visible in the resumable shape', () => {
    render(<ErrorCard content="⟳ Session busy — please retry." onContinue={() => {}} />)
    expect(screen.getByTestId('error-card')).toHaveTextContent('⟳ Session busy — please retry.')
  })

  describe('a harness that is not signed in', () => {
    const meta = { code: 'auth_required', harness: 'codex', agent: 'Codex (ChatGPT)', login: 'codex login' }

    it('renders the translated notice with the agent and its command in a code span', () => {
      render(<ErrorCard content="Codex (ChatGPT) is not signed in. Run `codex login`." meta={meta} />)
      const card = screen.getByTestId('error-card')
      expect(card).toHaveAttribute('data-code', 'auth_required')
      expect(card).toHaveAttribute('data-harness', 'codex')
      expect(screen.getByTestId('error-card-title')).toHaveTextContent('Codex (ChatGPT) is not signed in')
      const detail = screen.getByTestId('error-card-detail')
      expect(detail).toHaveTextContent('Run codex login in a terminal, then send your message again.')
      const code = detail.querySelector('code')
      expect(code?.textContent).toBe('codex login')
    })

    it('never prints the raw server prose or a JSON-RPC error', () => {
      render(<ErrorCard content="JSON-RPC error: {'code': -32000}" meta={meta} />)
      expect(screen.getByTestId('error-card').textContent).not.toMatch(/JSON-RPC|-32000/)
    })

    it('offers no Continue even when the caller passes one', () => {
      // Nothing can resume until the user signs in, so the control would promise
      // a recovery that cannot happen.
      render(<ErrorCard content="x" meta={meta} onContinue={() => {}} />)
      expect(screen.queryByTestId('error-card-continue')).toBeNull()
      expect(screen.getByTestId('error-card')).not.toHaveAttribute('data-continuable')
    })

    it('names no command for an agent that publishes none', () => {
      render(<ErrorCard content="x" meta={{ code: 'auth_required', harness: 'kimi', agent: 'Kimi Code', login: '' }} />)
      const detail = screen.getByTestId('error-card-detail')
      expect(detail).toHaveTextContent('Sign in to Kimi Code, then send your message again.')
      expect(detail.querySelector('code')).toBeNull()
    })

    it('falls back to the harness id when the agent label is missing', () => {
      render(<ErrorCard content="x" meta={{ code: 'auth_required', harness: 'codex' }} />)
      expect(screen.getByTestId('error-card-title')).toHaveTextContent('codex is not signed in')
    })

    it('uses no emoji icon', () => {
      render(<ErrorCard content="x" meta={meta} />)
      expect(screen.getByTestId('error-card').textContent).not.toMatch(/\p{Extended_Pictographic}/u)
    })

    it('leaves any other code on the plain card', () => {
      render(<ErrorCard content="boom" meta={{ code: 'something_else' }} onContinue={() => {}} />)
      expect(screen.getByTestId('error-card')).toHaveTextContent('boom')
      expect(screen.getByTestId('error-card-continue')).toBeTruthy()
    })
  })
})
