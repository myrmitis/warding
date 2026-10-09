/**
 * A harness that is not signed in, as the gateway reports it.
 *
 * The same `code` rides on two payloads: the `meta` of the error row a refused
 * turn appends, and the 503 body `/api/models` answers while the agent's last
 * start was refused for want of a sign-in. Both carry the harness id, its label
 * and its published sign-in command (empty when it publishes none). The label
 * and command are machine data: the dashboard owns every sentence built from
 * them, and the command is terminal input that is shown, never translated.
 */
export const AUTH_REQUIRED_CODE = 'auth_required'

export interface AuthRequiredInfo {
  harness: string
  /** The agent's display label; falls back to its id. */
  agent: string
  /** Shell command that signs in to the agent, or '' when none is published. */
  login: string
}

/** The sign-in facts in *source*, or null when it is not an `auth_required` payload. */
export function authRequiredOf(source: unknown): AuthRequiredInfo | null {
  if (!source || typeof source !== 'object') return null
  const s = source as Record<string, unknown>
  if (s.code !== AUTH_REQUIRED_CODE) return null
  const harness = typeof s.harness === 'string' ? s.harness : ''
  const agent = typeof s.agent === 'string' && s.agent ? s.agent : harness
  const login = typeof s.login === 'string' ? s.login : ''
  return { harness, agent, login }
}
