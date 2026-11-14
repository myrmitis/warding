import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type RoutingHarnessesView } from '../api/client'
import { parseErrorCode } from '../utils/errorReport'
import { i18nT } from '../i18n/t'

export const ROUTING_HARNESSES_QUERY_KEY = ['routing', 'harnesses'] as const

/**
 * The gateway's harness view (`/api/routing/harnesses`): every docked agent and
 * the chat harness choice. One key and one fetcher, so Settings, the first-run
 * gate and the composer read the same cache entry.
 */
export function useRoutingHarnesses({ enabled }: { enabled?: boolean } = {}) {
  return useQuery<RoutingHarnessesView | null>({
    queryKey: ROUTING_HARNESSES_QUERY_KEY,
    // Partial `api/client` mocks are common in the unit suite; a missing method
    // must not throw on mount.
    queryFn: () => Promise.resolve(api.routingHarnesses?.()).then(v => v ?? null),
    ...(enabled === undefined ? {} : { enabled }),
  })
}

/**
 * Writes `agent.acp_backend`, the agent new chats start on. Settings ▸ Agents &
 * plans and the composer's harness menu both save through here.
 *
 * After a save, the model list is refetched too: `/api/models` lists what the
 * configured agent advertises, so a list kept from the previous agent offers
 * models the new one cannot run.
 */
export function useSetChatHarness() {
  const qc = useQueryClient()
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: (harness: string) => api.setChatHarness(harness),
    onError: err => {
      // ApiError keeps the raw response body, where the backend's `code` lives.
      const code = parseErrorCode((err as { body?: string }).body)
      setError(code === 'unknown_harness'
        ? i18nT('pages.settings.agentsPanel.chat_harness_unknown')
        : i18nT('pages.settings.agentsPanel.chat_harness_save_failed'))
    },
    onSuccess: () => setError(''),
    onSettled: async (_data, err, harness) => {
      await qc.invalidateQueries({ queryKey: ROUTING_HARNESSES_QUERY_KEY })
      if (err) return
      void qc.invalidateQueries({ queryKey: ['available-models'] })
      // A local overlay (config.local.json) outranks the file this write lands in.
      // The view reads the merged value back, so a difference is said, not hidden.
      const now = qc.getQueryData<RoutingHarnessesView | null>(ROUTING_HARNESSES_QUERY_KEY)?.chat?.configured
      if (now && now !== harness) setError(i18nT('pages.settings.agentsPanel.chat_harness_overridden'))
    },
  })
  return {
    pick: (harness: string) => mutation.mutate(harness),
    /** The agent being saved right now, else `null`. */
    pending: mutation.isPending ? mutation.variables ?? null : null,
    error,
  }
}
