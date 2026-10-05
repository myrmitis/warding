/**
 * Wire contracts for the class and `meta` markers the gateway stamps on a
 * transcript row.
 *
 * `cls` is a space-separated class list — `msg msg-a`, `msg msg-a multitask-reply` —
 * and other consumers already match a single class with a whitespace-bounded
 * test. Today's producers emit each marker token on its own, so equality would
 * match too; membership is defensive against a token later arriving alongside
 * others, which would silently kill the guard while tests stayed green.
 *
 * The values live here rather than inline at the call sites so the tree has
 * exactly one spelling of each.
 */

/** The `cls` token that marks a note breadcrumb. */
export const RECONCILE_NOTE_CLS = 'reconcile-note'

/**
 * True when `cls` carries `token` as a whole class.
 *
 * Splitting is what makes this a class test rather than a substring test:
 * `reconcile-note-draft` contains the token but is a different class.
 */
function hasClassToken(cls: string | undefined | null, token: string): boolean {
  if (typeof cls !== 'string' || cls.length === 0) return false
  return cls.trim().split(/\s+/).includes(token)
}

/** True when `cls` carries the note class as a whole class. */
export function isReconcileNote(cls: string | undefined | null): boolean {
  return hasClassToken(cls, RECONCILE_NOTE_CLS)
}

/**
 * The markers on a Multitask Mode answer: a forwarded topic result, a meta
 * render, or a question back to the user. The gateway writes both. The `meta`
 * key is the durable one: the periodic slot flush keeps `meta` for every role
 * but keeps `cls` only for role === 'system'. The class covers the live frame.
 */
export const MULTITASK_REPLY_CLS = 'multitask-reply'
export const MULTITASK_REPLY_META_KEY = 'multitask_reply'

/** True when a transcript row carries the Multitask Mode answer marker (class or meta). */
export function hasMultitaskReplyMarker(
  msg: { cls?: string | null; meta?: Record<string, unknown> },
): boolean {
  const meta = msg.meta
  if (meta?.[MULTITASK_REPLY_META_KEY] === true) return true
  return hasClassToken(msg.cls, MULTITASK_REPLY_CLS)
}
