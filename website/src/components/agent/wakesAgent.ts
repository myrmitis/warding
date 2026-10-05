import type { CronJob } from '../../types'

/**
 * Whether `job` wakes `agent`, in the order the backend resolves it.
 *
 * 1. A script or command job opens no session, so it runs as NO agent — whatever
 *    `agent` it happens to carry. Checked first, so a stale `agent_id` on such a
 *    job cannot list it under an agent it never wakes.
 * 2. A sequence of MORE THAN ONE agent takes precedence over `agent_id` at run
 *    time (`len(agents) > 1` in the gateway's dispatch), so such a job belongs to
 *    the agents it names and to no others — in particular, an empty `agent_id` on
 *    one must NOT read as "the default agent". A one-element sequence does NOT
 *    take precedence, so it falls through to `agent_id` like any other job.
 * 3. Otherwise the bound `agent`, and an empty one means the default agent.
 *
 * Shared rather than private to the wake pane: the rail also counts these jobs,
 * and two copies of this precedence would drift into disagreeing about which
 * agent a sequence job belongs to.
 */
export function wakesAgent(job: CronJob, agent: string, isDefaultAgent: boolean): boolean {
  if (job.script || job.command) return false
  const seq = (job.agent_sequence || []).map(a => (a || '').trim()).filter(Boolean)
  if (seq.length > 1) return seq.includes(agent)
  const bound = (job.agent || '').trim()
  return bound ? bound === agent : isDefaultAgent
}

/** Query key shared by the wake pane and the rail's count, so one fetch serves
 *  both instead of the rail issuing a second identical request. */
export const agentWakeQueryKey = (agent: string) => ['crons', 'agent-wake', agent]

/** The agent editor's own entry under the `webhooks` prefix. Deliberately NOT
 *  the page's bare `['webhooks']`: the two have different queryFns — the page
 *  substitutes an empty view on failure so an old gateway renders as
 *  unconfigured, while the editor must THROW so a failure renders as unknown
 *  rather than "nothing wakes this agent" — and sharing one key would let
 *  whichever mounts first decide the other's shape. Mint/revoke on the page
 *  still reaches this cache, because invalidation matches keys by prefix. */
export const agentWebhooksQueryKey = ['webhooks', 'agent-editor']

/** A webhook token shape sufficient for the two predicates below. Structural
 *  rather than the api client's entry type, so this module stays type-only
 *  independent of the client. */
interface WebhookTokenLike {
  agent?: string
  enabled?: boolean
}

/** Whether `token` is bound to `agent`. Shared for the same reason wakesAgent is:
 *  the rail badge and the webhook pane both answer "whose token is this", and
 *  two spellings of the predicate would drift into disagreeing. */
export function webhookBoundToAgent(token: WebhookTokenLike, agent: string): boolean {
  return (token.agent || '') === agent && agent !== ''
}

/** Whether `token` can actually start a turn right now. Two switches silence a
 *  token the same way — its own admission switch and the store-wide kill
 *  switch — and every "live" claim (rail count, row dimming, the any-agent
 *  disclosure) must hold both, or the surfaces drift into contradicting each
 *  other about a security-relevant fact. */
export function webhookCanCallIn(token: WebhookTokenLike, switchOn: boolean): boolean {
  return switchOn && token.enabled !== false
}
