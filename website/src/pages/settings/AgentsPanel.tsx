import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Check, CheckCircle2, Circle, Copy, ExternalLink, Loader2, LogIn, Download, RefreshCw, TimerReset } from 'lucide-react'

import { SettingsCard, SettingsInput, SettingsSection, SettingsSelect, SettingsToggle } from '../../components/settings'
import { Badge, Btn } from '../../components/ui'
import ErrorNotice from '../../components/ErrorNotice'
import {
  api,
  type RoutingBilling,
  type RoutingChatChoice,
  type RoutingChatHarness,
  type RoutingHarnessRow,
  type RoutingHarnessesView,
  type RoutingLaneEdit,
  type RoutingProbeStatus,
} from '../../api/client'
import { addTab as addDockTerminal } from '../../hooks/useBottomTerminal'
import { onTerminalReady, sendToTerminalSession, useTerminalEnabled } from '../../utils/terminalRegistry'
import { copyToClipboard } from '../../utils/clipboard'
import { parseErrorCode } from '../../utils/errorReport'
import { fmtNumber, fmtRelative, fmtTime } from '../../i18n/format'
import { i18nT } from '../../i18n/t'

/**
 * Settings > Agents & plans: connect every coding agent you pay for, and decide
 * how the harness router spends each plan.
 *
 * {{productName}} never performs a sign-in and never sees a credential. Each
 * agent keeps its own login, so "Sign in" runs that agent's own login command in
 * the dashboard terminal (or copies it when the terminal is off), and "Check"
 * asks the gateway to start the agent once and report whether it is signed in.
 * Routing controls write the lane for that agent in `routing.json`. The chat
 * harness picker writes `agent.acp_backend`, the one agent new chats start on.
 */

export const ROUTING_HARNESSES_QUERY_KEY = ['routing', 'harnesses'] as const
const QUERY_KEY = ROUTING_HARNESSES_QUERY_KEY
const BILLING_OPTIONS: RoutingBilling[] = ['subscription', 'free', 'metered']
// How long "Copied" / "Sent to terminal" stays on a button.
const FLASH_MS = 2000
// A dock terminal whose shell never reports ready counts as a failed send.
const TERMINAL_READY_TIMEOUT_MS = 6000

// Catalog keys by harness id for the plan line under each agent's name. An
// agent without an entry shows the generic line.
const PLAN_KEYS: Record<string, string> = {
  claude: 'pages.settings.agentsPanel.plan_claude',
  codex: 'pages.settings.agentsPanel.plan_codex',
  cursor: 'pages.settings.agentsPanel.plan_cursor',
  grok: 'pages.settings.agentsPanel.plan_grok',
  opencode: 'pages.settings.agentsPanel.plan_opencode',
}

function kindLabel(kind: string): string {
  switch (kind) {
    case 'plan': return i18nT('pages.settings.agentsPanel.kind_plan')
    case 'implement': return i18nT('pages.settings.agentsPanel.kind_implement')
    case 'debug': return i18nT('pages.settings.agentsPanel.kind_debug')
    case 'review': return i18nT('pages.settings.agentsPanel.kind_review')
    case 'test': return i18nT('pages.settings.agentsPanel.kind_test')
    case 'research': return i18nT('pages.settings.agentsPanel.kind_research')
    case 'docs': return i18nT('pages.settings.agentsPanel.kind_docs')
    case 'quick': return i18nT('pages.settings.agentsPanel.kind_quick')
    case 'bulk': return i18nT('pages.settings.agentsPanel.kind_bulk')
    default: return kind
  }
}

function billingLabel(billing: RoutingBilling): string {
  switch (billing) {
    case 'subscription': return i18nT('pages.settings.agentsPanel.billing_subscription')
    case 'free': return i18nT('pages.settings.agentsPanel.billing_free')
    case 'metered': return i18nT('pages.settings.agentsPanel.billing_metered')
  }
}

function StatusBadge({ status, checking }: { status: RoutingProbeStatus; checking: boolean }) {
  if (checking) {
    return (
      <Badge variant="muted">
        <Loader2 className="lucide-inline animate-spin" aria-hidden="true" />
        {i18nT('pages.settings.agentsPanel.status_checking')}
      </Badge>
    )
  }
  switch (status) {
    case 'connected': return <Badge variant="ok">{i18nT('pages.settings.agentsPanel.status_connected')}</Badge>
    case 'needs_login': return <Badge variant="warn">{i18nT('pages.settings.agentsPanel.status_needs_login')}</Badge>
    case 'not_installed': return <Badge variant="muted">{i18nT('pages.settings.agentsPanel.status_not_installed')}</Badge>
    case 'timeout': return <Badge variant="err">{i18nT('pages.settings.agentsPanel.status_timeout')}</Badge>
    case 'error': return <Badge variant="err">{i18nT('pages.settings.agentsPanel.status_error')}</Badge>
    default: return <Badge variant="muted">{i18nT('pages.settings.agentsPanel.status_unknown')}</Badge>
  }
}

/** Open a dock terminal and type *command* into it once the shell is ready. */
function runInDockTerminal(command: string): Promise<boolean> {
  const sessionId = addDockTerminal()
  if (!sessionId) return Promise.resolve(false)
  return new Promise(resolve => {
    let settled = false
    const settle = (ok: boolean) => {
      if (settled) return
      settled = true
      resolve(ok)
    }
    const unsub = onTerminalReady(sessionId, () => settle(sendToTerminalSession(sessionId, command)))
    setTimeout(() => { unsub(); settle(false) }, TERMINAL_READY_TIMEOUT_MS)
  })
}

/** A button that runs a setup command in the dock terminal, or copies it. */
function CommandButton({ command, icon, label, primary }: {
  command: string
  icon: ReactNode
  label: string
  primary?: boolean
}) {
  const terminalEnabled = useTerminalEnabled()
  const [flash, setFlash] = useState<'' | 'sent' | 'copied' | 'failed'>('')
  const timer = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => () => clearTimeout(timer.current), [])

  const show = (next: 'sent' | 'copied' | 'failed') => {
    clearTimeout(timer.current)
    setFlash(next)
    timer.current = setTimeout(() => setFlash(''), FLASH_MS)
  }

  const onClick = async () => {
    if (terminalEnabled && await runInDockTerminal(command)) {
      show('sent')
      return
    }
    show(await copyToClipboard(command) ? 'copied' : 'failed')
  }

  const text = flash === 'sent'
    ? i18nT('pages.settings.agentsPanel.sent_to_terminal')
    : flash === 'copied'
      ? i18nT('pages.settings.agentsPanel.copied_paste_in_a_terminal')
      : flash === 'failed'
        ? i18nT('pages.settings.agentsPanel.could_not_run_or_copy')
        : label
  return (
    <Btn primary={primary} onClick={onClick} title={command}>
      {flash === 'sent' || flash === 'copied' ? <Check className="lucide-inline" /> : icon}
      {text}
    </Btn>
  )
}

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex items-center gap-2 min-w-0">
      <code className="font-mono text-[12px] text-muted truncate min-w-0" title={command}>{command}</code>
      <Btn
        aria-label={i18nT('pages.settings.agentsPanel.copy_command')}
        title={i18nT('pages.settings.agentsPanel.copy_command')}
        onClick={async () => { setCopied(await copyToClipboard(command)) }}
        className="shrink-0"
      >
        {copied ? <Check className="lucide-inline" /> : <Copy className="lucide-inline" />}
      </Btn>
    </div>
  )
}

/** A number field that saves on blur or Enter, not on every keystroke. */
function NumberField({ label, description, value, min, step, onCommit, disabled }: {
  label: string
  description: string
  value: number
  min: number
  step: number
  onCommit: (value: number) => void
  disabled?: boolean
}) {
  const [draft, setDraft] = useState(String(value))
  useEffect(() => { setDraft(String(value)) }, [value])
  const commit = () => {
    const parsed = Number(draft)
    if (!Number.isFinite(parsed) || parsed < min) { setDraft(String(value)); return }
    if (parsed !== value) onCommit(parsed)
  }
  return (
    <SettingsInput
      label={label}
      description={description}
      type="number"
      min={min}
      step={step}
      value={draft}
      onChange={setDraft}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter') commit() }}
      disabled={disabled}
    />
  )
}

function ModelField({ value, onCommit, disabled }: { value: string; onCommit: (v: string) => void; disabled?: boolean }) {
  const [draft, setDraft] = useState(value)
  useEffect(() => { setDraft(value) }, [value])
  const commit = () => { if (draft.trim() !== value) onCommit(draft.trim()) }
  return (
    <SettingsInput
      label={i18nT('pages.settings.agentsPanel.model')}
      description={i18nT('pages.settings.agentsPanel.model_description')}
      value={draft}
      placeholder={i18nT('pages.settings.agentsPanel.model_placeholder')}
      onChange={setDraft}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter') commit() }}
      disabled={disabled}
    />
  )
}

function HarnessCard({ row, index, checking, onCheck, onEdit, onResume, saving, compact }: {
  row: RoutingHarnessRow
  compact?: boolean
  index: number
  checking: boolean
  onCheck: () => void
  onEdit: (fields: RoutingLaneEdit) => void
  onResume: (lane: string) => void
  saving: boolean
}) {
  const status: RoutingProbeStatus = !row.installed ? 'not_installed' : row.probe.status
  const planKey = PLAN_KEYS[row.harness]
  const lane = row.lane
  const resting = row.cooldown_until > 0
  // Installed but unable to start for want of a piece (Claude Code without its
  // ACP adapter) is still an install problem: offer the install command.
  const needsInstall = !row.installed || status === 'not_installed'
  // A sign-in refusal is already said by the badge, the Sign in button and the
  // command row, in the user's language. The probe's own detail is whatever the
  // agent wrote (an older record can still hold a raw JSON-RPC error), so it is
  // never shown for it.
  const showDetail = !!row.probe.detail && (status === 'error' || status === 'not_installed')
  return (
    <SettingsCard index={index}>
      <div className="flex items-start justify-between gap-4" data-testid={`agent-${row.harness}`}>
        <div className="flex flex-col gap-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Bot className="lucide-inline text-muted shrink-0" aria-hidden="true" />
            <span className="text-sm font-medium text-text-strong">{row.label}</span>
            <StatusBadge status={status} checking={checking} />
            {resting && (
              <Badge variant="warn">
                {i18nT('pages.settings.agentsPanel.resting_until', { time: fmtTime(row.cooldown_until * 1000) })}
              </Badge>
            )}
          </div>
          <p className="text-[13px] text-muted">
            {planKey ? i18nT(planKey) : i18nT('pages.settings.agentsPanel.plan_generic')}
          </p>
          {row.installed && row.probe.checked_at > 0 && !checking && (
            <p className="text-[12px] text-muted">
              {i18nT('pages.settings.agentsPanel.last_checked', { when: fmtRelative(row.probe.checked_at * 1000) })}
              {status === 'connected' && row.probe.models > 0 && (
                <> · {i18nT('pages.settings.agentsPanel.models_count', { n: fmtNumber(row.probe.models) })}</>
              )}
            </p>
          )}
          {showDetail && (
            <p className="text-[12px] text-warn font-mono break-words">{row.probe.detail}</p>
          )}
          {!row.setup && row.hint && <p className="text-[12px] text-muted">{row.hint}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          {row.setup && needsInstall && (
            <CommandButton
              command={row.setup.install}
              icon={<Download className="lucide-inline" />}
              label={i18nT('pages.settings.agentsPanel.install')}
              primary
            />
          )}
          {row.setup && !needsInstall && (
            <CommandButton
              command={row.setup.login}
              icon={<LogIn className="lucide-inline" />}
              label={i18nT('pages.settings.agentsPanel.sign_in')}
              primary={status !== 'connected'}
            />
          )}
          {row.installed && (
            <Btn onClick={onCheck} disabled={checking}>
              <RefreshCw className="lucide-inline" />
              {i18nT('pages.settings.agentsPanel.check')}
            </Btn>
          )}
          {row.setup && (
            <a
              href={row.setup.docs_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[12px] text-muted hover:text-text inline-flex items-center gap-1"
            >
              {i18nT('pages.settings.agentsPanel.docs')}
              <ExternalLink className="lucide-inline" aria-hidden="true" />
            </a>
          )}
        </div>
      </div>

      {row.setup && (
        <CopyCommand command={needsInstall ? row.setup.install : row.setup.login} />
      )}

      {!compact && (row.installed || lane) && (
        <>
          <SettingsToggle
            label={i18nT('pages.settings.agentsPanel.use_for_routing')}
            description={i18nT('pages.settings.agentsPanel.use_for_routing_description')}
            checked={!!lane?.enabled && row.installed}
            onChange={v => onEdit({ enabled: v })}
            disabled={saving || !row.installed}
          />
          {lane && lane.enabled && row.installed && (
            <>
              <SettingsSelect
                label={i18nT('pages.settings.agentsPanel.billing')}
                description={i18nT('pages.settings.agentsPanel.billing_description')}
                value={lane.billing}
                options={BILLING_OPTIONS}
                optionLabels={BILLING_OPTIONS.map(billingLabel)}
                onChange={v => onEdit({ billing: v as RoutingBilling })}
                disabled={saving}
              />
              <NumberField
                label={i18nT('pages.settings.agentsPanel.plan_size')}
                description={i18nT('pages.settings.agentsPanel.plan_size_description')}
                value={lane.weight}
                min={0.05}
                step={0.5}
                onCommit={v => onEdit({ weight: v })}
                disabled={saving}
              />
              <NumberField
                label={i18nT('pages.settings.agentsPanel.window_limit', { hours: fmtNumber(lane.window_hours) })}
                description={i18nT('pages.settings.agentsPanel.window_limit_description')}
                value={lane.window_limit}
                min={0}
                step={1}
                onCommit={v => onEdit({ window_limit: Math.round(v) })}
                disabled={saving}
              />
              <ModelField value={lane.model} onCommit={v => onEdit({ model: v })} disabled={saving} />
              <div className="flex items-center justify-between gap-3">
                <p className="text-[12px] text-muted">
                  {i18nT('pages.settings.agentsPanel.usage_line', {
                    window: fmtNumber(row.window_used),
                    hours: fmtNumber(lane.window_hours),
                    day: fmtNumber(row.day_used),
                  })}
                </p>
                {resting && (
                  <Btn onClick={() => onResume(lane.id)} disabled={saving}>
                    <TimerReset className="lucide-inline" />
                    {i18nT('pages.settings.agentsPanel.resume_now')}
                  </Btn>
                )}
              </div>
            </>
          )}
        </>
      )}
    </SettingsCard>
  )
}

/** The row's name: the catalog word for `auto`, else the harness's own product name. */
function chatChoiceName(choice: RoutingChatChoice): string {
  return choice.id === 'auto' ? i18nT('pages.settings.agentsPanel.chat_harness_auto') : choice.label
}

/**
 * The harness new chats start on. Every entry comes from the gateway's own list
 * (selectable harnesses plus what the host has installed), never from a list here.
 * An agent that is not installed cannot be chosen; one that needs sign-in can,
 * because signing in later is the usual order, and its sign-in command sits beside
 * it. A chat that is already open keeps the agent it started on, which the
 * description says in so many words.
 */
export function ChatHarnessPicker({ chat, pending, error, onPick }: {
  chat: RoutingChatHarness
  /** The agent being saved right now, shown as chosen while the write is in flight. */
  pending: string | null
  error: string
  onPick: (harness: string) => void
}) {
  const current = pending ?? chat.configured
  const startsOn = chat.choices.find(c => c.id === chat.selected)
  // What `auto` would pick, shown on its own row whichever harness is chosen now.
  const autoId = chat.choices.find(c => c.id === 'auto')?.resolves_to
  const autoTarget = autoId ? chat.choices.find(c => c.id === autoId) : undefined
  return (
    <SettingsSection title={i18nT('pages.settings.agentsPanel.chat_harness_title')}>
      <SettingsCard>
        <div
          data-setting-label={i18nT('pages.settings.agentsPanel.chat_harness_title')}
          data-setting-key="agent.acp_backend"
        >
          <p className="text-[12px] text-muted mb-2 leading-relaxed">
            {i18nT('pages.settings.agentsPanel.chat_harness_description')}
          </p>
          <div
            className="flex flex-col gap-1.5"
            role="radiogroup"
            aria-label={i18nT('pages.settings.agentsPanel.chat_harness_title')}
          >
            {chat.choices.map(choice => {
              const selected = choice.id === current
              const unavailable = choice.installed === false
              const needsLogin = choice.status === 'needs_login'
              const login = choice.setup?.login ?? ''
              return (
                <div
                  key={choice.id}
                  data-testid={`chat-harness-${choice.id}`}
                  className={`rounded-md border px-3 py-2 transition-colors ${selected ? 'border-accent bg-accent-subtle' : 'border-border'} ${unavailable ? 'opacity-70' : ''}`}
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    disabled={unavailable || pending !== null}
                    onClick={() => { if (!selected) onPick(choice.id) }}
                    className="flex w-full items-center gap-2.5 flex-wrap text-left bg-transparent border-none p-0 cursor-pointer disabled:cursor-not-allowed"
                  >
                    {selected
                      ? <CheckCircle2 className="lucide-inline text-accent shrink-0" aria-hidden="true" />
                      : <Circle className="lucide-inline text-muted shrink-0" aria-hidden="true" />}
                    <span className="text-[13px] font-medium text-text-strong">{chatChoiceName(choice)}</span>
                    {choice.id !== 'auto' && (
                      <StatusBadge status={unavailable ? 'not_installed' : choice.status || 'unknown'} checking={false} />
                    )}
                    {selected && <Badge variant="ok">{i18nT('pages.settings.agentsPanel.chat_harness_active')}</Badge>}
                  </button>
                  {choice.id === 'auto' && (
                    <p className="text-[12px] text-muted mt-1 pl-6">
                      {autoTarget
                        ? i18nT('pages.settings.agentsPanel.chat_harness_auto_description', { agent: autoTarget.label })
                        : i18nT('pages.settings.agentsPanel.chat_harness_auto_none')}
                    </p>
                  )}
                  {unavailable && (
                    <p className="text-[12px] text-muted mt-1 pl-6">
                      {i18nT('pages.settings.agentsPanel.chat_harness_not_installed_reason')}
                    </p>
                  )}
                  {needsLogin && !unavailable && (
                    <div className="mt-1 flex flex-col gap-1 pl-6">
                      <p className="text-[12px] text-warn">{i18nT('pages.settings.agentsPanel.chat_harness_needs_login_note')}</p>
                      {login
                        ? <CopyCommand command={login} />
                        : choice.hint && <p className="text-[12px] text-muted">{choice.hint}</p>}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <p className="text-[12px] text-muted mt-2" aria-live="polite">
            {startsOn
              ? i18nT('pages.settings.agentsPanel.chat_harness_starts_on', { agent: startsOn.label })
              : i18nT('pages.settings.agentsPanel.chat_harness_none_ready')}
          </p>
          <ErrorNotice message={error} className="mt-2" />
        </div>
      </SettingsCard>
    </SettingsSection>
  )
}

/** The panel. `compact` (first-run setup) shows connection state only: no
 *  routing controls and no pick grid, which mean nothing before an agent works. */
export function AgentsPanel({ compact = false }: { compact?: boolean } = {}) {
  const qc = useQueryClient()
  const [error, setError] = useState('')
  const [chatError, setChatError] = useState('')
  const [checking, setChecking] = useState<Set<string>>(new Set())

  const view = useQuery<RoutingHarnessesView | null>({
    queryKey: QUERY_KEY,
    // Partial `api/client` mocks are common in this suite; a missing method
    // must not throw on mount.
    queryFn: () => Promise.resolve(api.routingHarnesses?.()).then(v => v ?? null),
  })

  const check = async (harness: string) => {
    setChecking(prev => new Set(prev).add(harness))
    try {
      await api.checkRoutingHarness(harness)
    } catch {
      setError(i18nT('pages.settings.agentsPanel.check_failed'))
    } finally {
      setChecking(prev => { const next = new Set(prev); next.delete(harness); return next })
      qc.invalidateQueries({ queryKey: QUERY_KEY })
    }
  }

  const edit = useMutation({
    mutationFn: ({ harness, fields }: { harness: string; fields: RoutingLaneEdit }) =>
      api.editRoutingLane(harness, fields),
    onError: () => setError(i18nT('pages.settings.agentsPanel.save_failed')),
    onSuccess: () => setError(''),
    onSettled: () => qc.invalidateQueries({ queryKey: QUERY_KEY }),
  })

  const chatHarness = useMutation({
    mutationFn: (harness: string) => api.setChatHarness(harness),
    onError: err => {
      // ApiError keeps the raw response body, where the backend's `code` lives.
      const code = parseErrorCode((err as { body?: string }).body)
      setChatError(code === 'unknown_harness'
        ? i18nT('pages.settings.agentsPanel.chat_harness_unknown')
        : i18nT('pages.settings.agentsPanel.chat_harness_save_failed'))
    },
    onSuccess: () => setChatError(''),
    onSettled: async (_data, err, harness) => {
      await qc.invalidateQueries({ queryKey: QUERY_KEY })
      if (err) return
      // A local overlay (config.local.json) outranks the file this write lands in.
      // The view reads the merged value back, so a difference is said, not hidden.
      const now = qc.getQueryData<RoutingHarnessesView | null>(QUERY_KEY)?.chat?.configured
      if (now && now !== harness) setChatError(i18nT('pages.settings.agentsPanel.chat_harness_overridden'))
    },
  })

  const resume = useMutation({
    mutationFn: (lane: string) => api.clearRoutingCooldown(lane),
    onSettled: () => qc.invalidateQueries({ queryKey: QUERY_KEY }),
  })

  const settings = useMutation({
    mutationFn: (routeTasks: boolean) => api.editRoutingSettings({ route_tasks: routeTasks }),
    onError: () => setError(i18nT('pages.settings.agentsPanel.save_failed')),
    onSuccess: () => setError(''),
    onSettled: () => qc.invalidateQueries({ queryKey: QUERY_KEY }),
  })

  // A first visit shows every installed agent as "Not checked". Probe those once
  // so the panel answers "am I signed in?" without a click; a probe starts the
  // agent without sending a prompt, so it spends no plan quota.
  const autoChecked = useRef(false)
  const rows = view.data?.harnesses ?? []
  useEffect(() => {
    if (autoChecked.current || rows.length === 0) return
    autoChecked.current = true
    for (const row of rows) {
      if (row.installed && row.probe.status === 'unknown') void check(row.harness)
    }
    // Fires once per mount after the first load; `check` is stable in effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows.length])

  const installed = rows.filter(r => r.installed)
  const byLane = new Map(rows.filter(r => r.lane).map(r => [r.lane!.id, r.label]))

  return (
    <>
      {view.data?.chat && !compact && (
        <ChatHarnessPicker
          chat={view.data.chat}
          pending={chatHarness.isPending ? chatHarness.variables ?? null : null}
          error={chatError}
          onPick={harness => chatHarness.mutate(harness)}
        />
      )}
      <SettingsSection
        title={i18nT('pages.settings.agentsPanel.your_agents_and_plans')}
        badge={installed.length > 0
          ? <Badge variant="muted">{i18nT('pages.settings.agentsPanel.installed_count', { n: fmtNumber(installed.length) })}</Badge>
          : undefined}
      >
        <div className="flex items-start justify-between gap-4 mb-2">
          <p className="text-[13px] text-muted">{i18nT('pages.settings.agentsPanel.intro')}</p>
          {installed.length > 0 && (
            <Btn onClick={() => { for (const r of installed) void check(r.harness) }} className="shrink-0">
              <RefreshCw className="lucide-inline" />
              {i18nT('pages.settings.agentsPanel.check_all')}
            </Btn>
          )}
        </div>
        {view.isError && <ErrorNotice message={i18nT('pages.settings.agentsPanel.could_not_load_agents')} />}
        {rows.map((row, i) => (
          <HarnessCard
            key={row.harness}
            row={row}
            index={i}
            checking={checking.has(row.harness)}
            onCheck={() => void check(row.harness)}
            onEdit={fields => edit.mutate({ harness: row.harness, fields })}
            onResume={lane => resume.mutate(lane)}
            saving={edit.isPending}
            compact={compact}
          />
        ))}
        <ErrorNotice message={error} className="mt-2" />
      </SettingsSection>

      {view.data && !compact && (
        <SettingsSection title={i18nT('pages.settings.agentsPanel.who_gets_what')}>
          <SettingsCard>
            <p className="text-[13px] text-muted">{i18nT('pages.settings.agentsPanel.who_gets_what_description')}</p>
            <SettingsToggle
              configKey="routing.route_tasks"
              label={i18nT('pages.settings.agentsPanel.route_task_steps')}
              description={i18nT('pages.settings.agentsPanel.route_task_steps_description')}
              checked={!!view.data.route_tasks}
              onChange={v => settings.mutate(v)}
              disabled={settings.isPending}
            />
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              {view.data.kinds.map(kind => {
                const laneId = view.data?.preview[kind] ?? ''
                return (
                  <div key={kind} className="contents">
                    <dt className="text-muted">{kindLabel(kind)}</dt>
                    <dd className="text-text-strong">
                      {laneId ? byLane.get(laneId) ?? laneId : i18nT('pages.settings.agentsPanel.no_agent_available')}
                    </dd>
                  </div>
                )
              })}
            </dl>
          </SettingsCard>
        </SettingsSection>
      )}
    </>
  )
}

export default AgentsPanel
