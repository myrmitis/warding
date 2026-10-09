import { memo } from 'react'
import { Trans } from 'react-i18next'
import { Loader2, LogIn, Play } from 'lucide-react'

import { authRequiredOf } from '../../lib/authRequired'
import { i18nT } from '../../i18n/t'
import { useLanguageGeneration } from '../../i18n/useLanguageGeneration'

export interface ErrorCardProps {
  /** Server- or client-authored error prose, rendered verbatim. */
  content: string
  /**
   * Continue handler. Passed ONLY for the newest error row of a slot whose last
   * turn ended without a reply — a historical error further up the transcript is
   * settled and must not offer to resume anything.
   */
  onContinue?: () => void
  /** True while a continue request is in flight, so the press cannot double-fire. */
  continuing?: boolean
  /**
   * The row's `meta`. An `auth_required` code turns the card into the translated
   * sign-in notice built from the agent and command the gateway named, and drops
   * the Continue action: nothing can resume until the user signs in.
   */
  meta?: Record<string, unknown>
}

/**
 * The error row in a chat transcript.
 *
 * Every one of these carries prose that already tells the reader to retry
 * ("⟳ Connection lost — please retry."), but until now there was nothing to
 * click: recovering meant retyping the prompt. When the turn is genuinely
 * resumable the card grows an action, so the instruction and the affordance sit
 * in the same place.
 *
 * The button is deliberately absent rather than disabled when the turn is not
 * resumable — a permanently greyed control on a red card reads as a broken
 * feature, and there is no state the user could reach that would enable it.
 */
export const ErrorCard = memo(function ErrorCard({ content, onContinue, continuing, meta }: ErrorCardProps) {
  useLanguageGeneration() // memo() bails out of the provider-level repaint; subscribe directly
  const signIn = authRequiredOf(meta)
  if (signIn) {
    return (
      <div
        className="bg-warn-subtle ring-1 ring-inset forced-colors:border ring-warn/25 rounded-md self-center w-full max-w-full min-w-0 px-3 py-2.5 flex items-start gap-2.5 text-[13px] leading-5 animate-scale-in"
        data-testid="error-card"
        data-code="auth_required"
        data-harness={signIn.harness}
      >
        <LogIn className="lucide-inline shrink-0 mt-[3px] text-warn" aria-hidden="true" />
        <div className="min-w-0 flex flex-col gap-0.5" style={{ overflowWrap: 'anywhere' }}>
          <p className="m-0 font-medium text-text-strong" data-testid="error-card-title">
            {i18nT('pages.chat.errorCard.auth_required_title', { agent: signIn.agent })}
          </p>
          <p className="m-0 text-muted" data-testid="error-card-detail">
            {signIn.login
              ? (
                <Trans
                  i18nKey="pages.chat.errorCard.auth_required_run_command"
                  components={{ command: <code className="font-mono text-[12px] text-text bg-bg-hover rounded px-1 py-px">{signIn.login}</code> }}
                />
              )
              : i18nT('pages.chat.errorCard.auth_required_sign_in', { agent: signIn.agent })}
          </p>
        </div>
      </div>
    )
  }
  if (!onContinue) {
    return (
      <div
        className="bg-danger-subtle text-danger text-[13px] leading-5 px-3 py-2 rounded-md ring-1 ring-inset forced-colors:border ring-danger/15 self-center animate-scale-in"
        data-testid="error-card"
      >
        {content}
      </div>
    )
  }
  return (
    <div
      className="bg-danger-subtle ring-1 ring-inset forced-colors:border ring-danger/20 rounded-md self-center w-full max-w-full min-w-0 px-3 py-2 flex items-center gap-3 animate-scale-in"
      data-testid="error-card"
      data-continuable="true"
    >
      <div className="text-danger text-[13px] leading-5 flex-1 min-w-0" style={{ overflowWrap: 'anywhere' }}>
        {content}
      </div>
      <button
        type="button"
        onClick={onContinue}
        disabled={continuing}
        className="shrink-0 inline-flex items-center gap-2 text-[12px] leading-5 font-medium px-3 py-1 rounded-md bg-accent text-accent-fg border-none cursor-pointer hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        title={i18nT('pages.chat.errorCard.continue_hint')}
        data-testid="error-card-continue"
      >
        {continuing
          ? <Loader2 size={12} className="lucide-inline shrink-0 animate-spin" aria-hidden="true" />
          : <Play size={12} className="lucide-inline shrink-0" aria-hidden="true" />}
        {i18nT('pages.chat.errorCard.continue')}
      </button>
    </div>
  )
})
