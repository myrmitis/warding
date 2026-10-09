/**
 * The webhook pane of the agent editor: which webhook tokens can wake this agent.
 *
 * Read-only by design. Minting and revoking stay on the Webhooks page, which
 * owns the one-time secret reveal and the kill switch; this pane answers the
 * agent-shaped question — "can an outside system wake THIS agent, and with what
 * credential" — and links out for management.
 *
 * Honesty rule, same as AgentWakeSection's: absence of an answer and an answer
 * of "none" are different claims. And a third case is specific to webhooks —
 * a token with NO binding may name any agent per request, so while one exists,
 * "no tokens are bound to this agent" alone would be false reassurance. Unbound
 * tokens are surfaced as a separate line rather than folded into the list.
 */
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Webhook, ExternalLink, TriangleAlert, ShieldCheck, WebhookOff } from 'lucide-react'
import { api, type WebhookTokenEntry } from '../api/client'
import { Badge, Btn, Skeleton } from './ui'
import { timeAgo } from '../utils/timeAgo'
import { agentWebhooksQueryKey, webhookBoundToAgent, webhookCanCallIn } from './agent/wakesAgent'

import { i18nT } from '../i18n/t'

function TokenRow({ token, systemOff }: { token: WebhookTokenEntry; systemOff: boolean }) {
  // "Last used" labelled inline: the never-used sibling implies the meaning,
  // but a row seen alone does not.
  const used = token.last_used_at
    ? i18nT('components.agentWebhookSection.last_used_ago', { time: timeAgo(token.last_used_at) })
    : i18nT('pages.webhooksPage.never_used')
  // A disabled binding still exists — hiding it would send a user who wonders
  // why their webhook stopped firing off to mint a duplicate — but it cannot
  // call in, so the row must not look live. The global kill switch silences a
  // token the same way its own switch does, so it dims the row the same way.
  const off = !webhookCanCallIn(token, !systemOff)
  return (
    <div
      className={`border-t border-border py-2 first:border-t-0 ${off ? 'opacity-60' : ''}`}
      data-testid="agent-webhook-row"
    >
      <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3">
        <div className="flex w-full items-center gap-2 sm:contents">
          <Badge variant="muted" className="shrink-0 font-mono">
            <Webhook className="lucide-inline" aria-hidden="true" />
            {i18nT('components.agentWebhookSection.webhook')}
          </Badge>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12.5px] text-text-strong">{token.label}</div>
            <div className="text-[10.5px] text-muted">
              {/* The non-secret slice is the only identity a caller can be asked
                  to read back over the phone; the raw secret is unrecoverable. */}
              <span className="font-mono">{token.display_prefix}…{token.last4}</span>
              {' · '}{used}
            </div>
          </div>
          {token.enabled === false && (
            <Badge variant="muted" className="ml-auto shrink-0 sm:ml-0" data-testid="agent-webhook-row-off">
              <WebhookOff className="lucide-inline" aria-hidden="true" />
              {i18nT('components.agentWebhookSection.off')}
            </Badge>
          )}
          {token.require_signature && (
            <Badge variant="muted" className={`shrink-0 ${off ? '' : 'ml-auto sm:ml-0'}`} title={i18nT('pages.webhooksPage.request_signing')}>
              <ShieldCheck className="lucide-inline" aria-hidden="true" />
              {i18nT('components.agentWebhookSection.signed')}
            </Badge>
          )}
        </div>
      </div>
    </div>
  )
}

export default function AgentWebhookSection({ agent }: { agent: string }) {
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: agentWebhooksQueryKey,
    queryFn: () => api.webhooks(),
  })
  const tokens: WebhookTokenEntry[] = data?.tokens || []
  const killSwitchOff = !!data && data.switch_on === false
  const bound = tokens.filter(t => webhookBoundToAgent(t, agent))
  // Only tokens that can actually call in belong in the any-agent warning: a
  // silenced unbound token — its own switch or the global one — cannot in fact
  // wake anything, and warning about it two lines under "nothing can call in"
  // would have the pane contradicting itself about a security-relevant fact.
  const unbound = tokens.filter(
    t => !t.agent && webhookCanCallIn(t, !killSwitchOff),
  )

  const body = isLoading
    ? <Skeleton className="h-12" />
    : isError
      ? (
        <div className="flex items-center gap-2 rounded-md border border-warn-subtle bg-warn-subtle px-3 py-2.5 text-[11.5px] leading-relaxed text-muted" role="alert">
          <TriangleAlert className="lucide-inline shrink-0" aria-hidden="true" />
          <span className="flex-1">{i18nT('components.agentWebhookSection.could_not_load_webhooks')}</span>
          <Btn onClick={() => { void refetch() }}>{i18nT('components.agentWebhookSection.retry')}</Btn>
        </div>
      )
      : bound.length === 0
        ? (
          <div className="flex items-center gap-2 rounded-md border border-border bg-bg-accent px-3 py-2.5 text-[11.5px] leading-relaxed text-muted" data-testid="agent-webhook-empty">
            <WebhookOff className="lucide-inline shrink-0" aria-hidden="true" />
            {i18nT('components.agentWebhookSection.no_tokens_are_bound_to_this_agent')}
          </div>
        )
        : <div>{bound.map(t => <TokenRow key={t.id} token={t} systemOff={killSwitchOff} />)}</div>

  return (
    <section className="flex flex-col gap-3" data-testid="agent-webhook-section">
      <div className="flex items-center gap-2">
        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-muted">{i18nT('components.agentWebhookSection.webhooks_that_wake_this_agent')}</h3>
        <Btn className="ml-auto" onClick={() => navigate('/webhooks')}>
          <ExternalLink className="lucide-inline" aria-hidden="true" />
          {i18nT('components.agentWebhookSection.open_webhooks')}
        </Btn>
      </div>
      <p className="m-0 text-[11.5px] leading-relaxed text-muted">{i18nT('components.agentWebhookSection.outside_systems_holding_one_of_these_credentials')}</p>
      {body}
      {/* The kill switch silences every token, bound ones included — without
          this line the list above reads as live while nothing can actually
          call in. */}
      {killSwitchOff && (
        <p className="m-0 flex items-center gap-2 rounded-md border border-warn-subtle bg-warn-subtle px-3 py-2.5 text-[11.5px] leading-relaxed text-text" data-testid="agent-webhook-switch-off">
          <TriangleAlert className="lucide-inline shrink-0" aria-hidden="true" />
          {i18nT('components.agentWebhookSection.inbound_webhooks_are_switched_off')}
        </p>
      )}
      {/* An unbound token may name ANY agent per request — this one included —
          so its existence belongs in this pane's answer, not only on the
          Webhooks page. */}
      {!isLoading && !isError && unbound.length > 0 && (
        <p className="m-0 flex items-center gap-2 text-[11.5px] leading-relaxed text-muted" data-testid="agent-webhook-unbound-note">
          <TriangleAlert className="lucide-inline shrink-0" aria-hidden="true" />
          {i18nT('components.agentWebhookSection.unbound_tokens_can_wake_any_agent', { count: unbound.length })}
        </p>
      )}
    </section>
  )
}
