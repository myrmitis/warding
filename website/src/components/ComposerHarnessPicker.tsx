import { Check, ChevronDown, Cpu } from 'lucide-react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu'
import type { RoutingChatChoice } from '../api/client'
import { useRoutingHarnesses, useSetChatHarness } from '../hooks/useChatHarness'
import { i18nT } from '../i18n/t'

const CHIP_CLASS = 'inline-flex items-center gap-1 h-7 px-2 text-[12px] text-muted shrink-0'

function choiceName(choice: RoutingChatChoice): string {
  return choice.id === 'auto' ? i18nT('pages.settings.agentsPanel.chat_harness_auto') : choice.label
}

/**
 * The composer's harness chip, and the menu that picks the agent new chats
 * start on (`agent.acp_backend`, the same setting as Settings ▸ Agents & plans).
 *
 * The chip names the agent this chat runs on (`runningLabel`, from the gateway).
 * A chat with no turn yet has none, so the chip names the agent its first
 * message will start. An ACP session cannot move to another agent, so a pick
 * never changes a chat that already runs; the menu says so.
 *
 * When the gateway has no harness view (an older gateway, or the request
 * failed), the chip is the plain label it was before this menu existed.
 */
export default function ComposerHarnessPicker({ runningLabel, markOnly }: {
  runningLabel?: string
  /** Narrow shelf: show an icon, not the name. */
  markOnly: boolean
}) {
  const view = useRoutingHarnesses()
  const { pick, pending, error } = useSetChatHarness()
  const chat = view.data?.chat
  const startsOn = chat?.choices.find(c => c.id === chat.selected)
  const label = runningLabel ?? startsOn?.label
  if (!label) return null

  const title = runningLabel
    ? i18nT('components.chatInput.harness', { name: runningLabel })
    : i18nT('pages.settings.agentsPanel.chat_harness_starts_on', { agent: label })
  const face = markOnly
    ? <Cpu className="lucide-inline" aria-hidden="true" />
    : <span className="truncate max-w-[160px]">{label}</span>

  if (!chat) {
    return (
      <span
        className={CHIP_CLASS}
        title={title}
        data-testid="composer-harness"
        {...(markOnly ? { role: 'img', 'aria-label': title } : {})}
      >
        {face}
      </span>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={`${CHIP_CLASS} rounded-md bg-transparent border-none cursor-pointer hover:text-text hover:bg-[color-mix(in_srgb,var(--bg-elevated)_84%,var(--text))] transition-colors`}
          title={title}
          aria-label={title}
          data-testid="composer-harness"
        >
          {face}
          <ChevronDown size={12} className="shrink-0 opacity-60" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[220px] max-w-[300px]" data-testid="composer-harness-menu">
        <DropdownMenuLabel>{i18nT('pages.settings.agentsPanel.chat_harness_title')}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={pending ?? chat.configured}
          onValueChange={id => { if (id !== chat.configured) pick(id) }}
        >
          {chat.choices.map(choice => {
            const unavailable = choice.installed === false
            const autoTarget = choice.id === 'auto'
              ? chat.choices.find(c => c.id === choice.resolves_to)
              : undefined
            const note = unavailable
              ? i18nT('components.chatInput.harness_not_installed')
              : choice.status === 'needs_login'
                ? i18nT('components.chatInput.harness_needs_sign_in')
                : autoTarget?.label ?? ''
            return (
              <DropdownMenuRadioItem
                key={choice.id}
                value={choice.id}
                disabled={unavailable || pending !== null}
                data-testid={`composer-harness-${choice.id}`}
                // Stay open: the check mark moves and the note below stays in view.
                onSelect={e => e.preventDefault()}
                className="data-[state=checked]:text-text-strong"
              >
                <span className="w-3 shrink-0 text-accent" aria-hidden="true">
                  {(pending ?? chat.configured) === choice.id && <Check size={12} />}
                </span>
                <span className="truncate">{choiceName(choice)}</span>
                {note && <span className="ml-auto pl-3 text-[11px] text-muted shrink-0">{note}</span>}
              </DropdownMenuRadioItem>
            )
          })}
        </DropdownMenuRadioGroup>
        {(runningLabel || error) && <DropdownMenuSeparator />}
        {runningLabel && (
          <p className="px-3 py-1.5 text-[12px] text-muted leading-snug">
            {i18nT('components.chatInput.harness_stays_note', { name: runningLabel })}
          </p>
        )}
        {error && (
          <p role="alert" className="px-3 py-1.5 text-[12px] text-danger leading-snug">{error}</p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
