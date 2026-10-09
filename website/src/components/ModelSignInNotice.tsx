import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trans } from 'react-i18next'
import { Loader2, LogIn, RefreshCw } from 'lucide-react'

import { api } from '../api/client'
import type { AuthRequiredInfo } from '../lib/authRequired'
import { i18nT } from '../i18n/t'
import { Btn } from './ui'

/**
 * Why the model list is empty when the agent is not signed in.
 *
 * `/api/models` has nothing to list for an agent whose last start was refused
 * for want of a sign-in, so the picker would offer Auto alone with no
 * explanation. This says what to do instead, and "Check again" asks the gateway
 * to start the agent once (the same check Settings > Agents & plans runs) so the
 * list heals right after the user signs in rather than at the next poll.
 */
export default function ModelSignInNotice({ info }: { info: AuthRequiredInfo }) {
  const qc = useQueryClient()
  const check = useMutation({
    mutationFn: () => api.checkRoutingHarness(info.harness),
    onSettled: () => qc.invalidateQueries({ queryKey: ['available-models'] }),
  })
  const stillSignedOut = check.data?.probe?.status === 'needs_login'
  return (
    <div
      className="mx-1.5 mb-1 rounded-lg border border-warn-subtle bg-warn-subtle px-3 py-2.5 flex flex-col gap-1.5 text-[13px] leading-5"
      data-testid="model-sign-in-notice"
      data-harness={info.harness}
    >
      <div className="flex items-start gap-2 min-w-0">
        <LogIn className="lucide-inline shrink-0 mt-[3px] text-warn" aria-hidden="true" />
        <div className="min-w-0 flex flex-col gap-0.5" style={{ overflowWrap: 'anywhere' }}>
          <p className="m-0 font-medium text-text-strong">
            {i18nT('components.modelEffortDropdown.sign_in_to_see_models', { agent: info.agent })}
          </p>
          <p className="m-0 text-muted">
            {info.login
              ? (
                <Trans
                  i18nKey="components.modelEffortDropdown.sign_in_run_command"
                  components={{ command: <code className="font-mono text-[12px] text-text bg-bg-hover rounded px-1 py-px">{info.login}</code> }}
                />
              )
              : i18nT('components.modelEffortDropdown.sign_in_generic', { agent: info.agent })}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <Btn onClick={() => check.mutate()} disabled={check.isPending} data-testid="model-sign-in-check">
          {check.isPending
            ? <Loader2 className="lucide-inline animate-spin" aria-hidden="true" />
            : <RefreshCw className="lucide-inline" aria-hidden="true" />}
          {i18nT('components.modelEffortDropdown.check_again')}
        </Btn>
        {stillSignedOut && !check.isPending && (
          <span className="text-[12px] text-muted" role="status">
            {i18nT('components.modelEffortDropdown.still_not_signed_in')}
          </span>
        )}
      </div>
    </div>
  )
}
