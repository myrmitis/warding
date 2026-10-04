/**
 * StewardEditor — the create / edit dialog for one Issue Radar steward.
 *
 * `steward` absent or null means CREATE; a record means EDIT. The two modes share
 * every field, and differ in three places only: the title, the submit verb, and
 * what is SENT — create posts a full `StewardSpec`, edit sends a `StewardPatch` holding
 * just the fields that actually moved. Sending the whole record as a "patch"
 * would make this dialog overwrite a field another surface changed while it sat
 * open (pause writes `paused_reason`, the roster can flip `enabled`), so the diff
 * is a correctness property, not an optimization.
 *
 * ── Two things about this file that look like omissions and are not ──
 *
 * **The 409 is matched on the message, not a status code.** `issueRadarApi`
 * flattens every failure through `parseErrorBody` into `new Error(body.error)`,
 * so the route's `code: "steward_conflict"` and the 409 itself are both gone by the
 * time a caller sees it. Widening the client to carry the status is the right
 * long-term fix and belongs in `api.ts`, which this component does not own. Until
 * then `isNameTakenError` reads the store's own phrase — see its comment for why
 * the match is safe on this route.
 *
 * **Backstop wake is read-only.** The mock shows it as a field, but no
 * `backstop_wake_*` key exists on `Steward`, `StewardSpec`, `StewardPatch` or
 * `steward_store._DEFAULT_STEWARD` — `_validated_steward_patch` would drop it silently. An
 * editable input would therefore be a control that appears to save and does not,
 * which is worse than an honest read-only one. It is rendered with its real
 * value and a line saying it is fixed, exactly as the editing cap one section
 * below is.
 *
 * ── Closing is guarded, once there is something to lose ──
 *
 * Escape, the overlay, the header × and the footer's Cancel all route through
 * `requestClose`, which asks for confirmation only when the draft differs from
 * the values the form opened with. An untouched dialog still closes on ONE
 * Escape: a prompt on every close is its own annoyance, and it teaches the user
 * to dismiss the prompt without reading it — which is exactly when it stops
 * protecting anything.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog'
import { Badge, Btn, IconButton, Input, Toggle } from '../../../components/ui'
import SimpleSelect from '../../../components/SimpleSelect'
import { useAgents } from '../../../hooks/useAgents'
import { useAvailableModels } from '../../../hooks/useAvailableModels'
import StewardPlate, { stewardPlateVariant, stewardPlateVariantCount } from './StewardPlate'
import { issueRadarApi, type Steward, type StewardPatch, type StewardSpec } from '../api'
import { repoScopeKey } from '../lib/links'
import { useIssueRadar } from '../context'
import { useImeGuard } from '../../../hooks/useImeGuard'

/** Backstop wake, in seconds. A CONSTANT, not state: see the file header. */
const BACKSTOP_WAKE_SECONDS = 120

/** `steward_store._DEFAULT_STEWARD`, mirrored so a fresh dialog shows what the store
 *  would have stored anyway — a create form that disagrees with the server's
 *  defaults teaches the user the wrong numbers. */
const DEFAULTS = {
  agent: 'junction',
  model: '',
  extraPrompt: '',
  labels: [] as string[],
  autoResolveConflicts: true,
  autoMerge: true,
  unattended: true,
  maxOpen: 3,
  worktreeRoot: '',
}

/** `max_open` bounds, mirroring `_validated_steward_patch`, which DROPS an
 *  out-of-range value rather than clamping it — so a 0 typed here would silently
 *  keep the old number if it were not clamped before sending.
 *
 *  The cap does not loosen the store's separate one-editing-phase-at-a-time rule
 *  (`steward_store.EDITING_PHASES`): two work items editing at once means two
 *  worktrees holding uncommitted changes, which is how a fix for one issue lands
 *  on another issue's branch. The Limits copy introduces that rule to the user;
 *  it is not a number they can raise. */
const SLOT_MIN = 1
const SLOT_MAX = 20

/** Every editable field, in one bag, so create and edit share one reducer-ish
 *  shape and the edit-mode diff has something to compare against. */
interface Draft {
  name: string
  /** Pinned face, or null for "derive from the seed". */
  variant: number | null
  agent: string
  model: string
  extraPrompt: string
  labels: string[]
  autoResolveConflicts: boolean
  autoMerge: boolean
  unattended: boolean
  maxOpen: number
  worktreeRoot: string
}

function draftFromSteward(steward: Steward | null | undefined): Draft {
  if (!steward) {
    return {
      name: '',
      variant: null,
      agent: DEFAULTS.agent,
      model: DEFAULTS.model,
      extraPrompt: DEFAULTS.extraPrompt,
      labels: DEFAULTS.labels,
      autoResolveConflicts: DEFAULTS.autoResolveConflicts,
      autoMerge: DEFAULTS.autoMerge,
      unattended: DEFAULTS.unattended,
      maxOpen: DEFAULTS.maxOpen,
      worktreeRoot: DEFAULTS.worktreeRoot,
    }
  }
  return {
    name: steward.name,
    variant: steward.avatar_variant,
    agent: steward.agent,
    model: steward.model,
    extraPrompt: steward.extra_prompt,
    labels: Array.isArray(steward.labels) ? [...steward.labels] : [],
    autoResolveConflicts: steward.auto_resolve_conflicts,
    autoMerge: steward.auto_merge,
    unattended: steward.unattended,
    maxOpen: steward.max_open,
    worktreeRoot: steward.worktree_root,
  }
}

/** Membership-equal, not order-equal: the chip strip renders repo labels in the
 *  repo's order and appends free entries, so re-opening the dialog can reorder a
 *  list that did not change. An order-only difference must not send a write. */
function sameLabels(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  const set = new Set(a)
  return b.every(x => set.has(x))
}

/**
 * Whether two drafts hold the same values — what the close guard measures
 * dirtiness with.
 *
 * Enumerated from the object's OWN keys rather than a hand-written list of
 * comparisons, so a field added to `Draft` later is covered without anyone
 * remembering to extend this. Every field but `labels` is a primitive; `labels`
 * is an array and gets the same membership comparison the edit-mode patch diff
 * uses, so a chip strip that merely reordered is not a change.
 */
function sameDraft(a: Draft, b: Draft): boolean {
  const { labels: aLabels, ...aRest } = a
  const { labels: bLabels, ...bRest } = b
  if (!sameLabels(aLabels, bLabels)) return false
  return (Object.keys(aRest) as (keyof typeof aRest)[]).every(k => aRest[k] === bRest[k])
}

/**
 * Whether a failed steward write was the duplicate-name conflict.
 *
 * The phrase comes from `steward_store.create_steward` / `update_steward`
 * (`steward name {name!r} is already taken…`), which is the ONLY text either raise
 * puts on that condition. `HTTP 409` is the second shape: `parseErrorBody` falls
 * back to it when a 409's body is not json, and on these two routes the only
 * other `StewardStoreError` is the empty-name guard — which the submit button's own
 * disabled state makes unreachable — so attributing a bare 409 here to the name
 * cannot mislabel a different conflict.
 */
export function isNameTakenError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err ?? '')
  return /already taken/i.test(message) || /\bHTTP 409\b/.test(message)
}

/** Section heading: a small muted label with a hairline rule running to the
 *  right edge, as the mock has it. Not `PanelSectionHeader` — that one is sized
 *  and spaced for a side panel's list groups, and carries a count slot. */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-5 mb-2.5 flex items-center gap-2 first:mt-0">
      <span className="text-[11px] font-semibold uppercase tracking-[.07em] text-muted">
        {children}
      </span>
      <span className="h-px flex-1 bg-border" />
    </div>
  )
}

/** Field label + control + hint, stacked. The control is NESTED inside the
 *  `<label>` as well as pointed at by `htmlFor`: the association is then true
 *  both ways round, and the whole label row becomes part of the control's hit
 *  area. The hint stays OUTSIDE the label — a label that swallowed a 2-line
 *  explanation would be read out in full every time the field takes focus. */
function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="min-w-0">
      {/* The control IS both nested and bound by htmlFor→id, but `label-has-for`
          only recognises a NATIVE control written as a literal child, and every
          caller passes either the custom `Input` or a `children` expression it
          cannot look inside. `label-has-associated-control`, the rule that
          replaced this deprecated one, is satisfied and stays on. */}
      {/* eslint-disable-next-line jsx-a11y/label-has-for */}
      <label htmlFor={id} className="block">
        <span className="mb-1.5 block text-[13px] font-semibold text-text">{label}</span>
        {children}
      </label>
      {hint && <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{hint}</p>}
    </div>
  )
}

/** Pickable pill. A real button with `aria-pressed`, so the selected state is in
 *  the accessibility tree and not only in the border colour.
 *
 *  `mono` is OPT-IN, and only for a chip whose text is a token rather than
 *  prose: the app font is user-configurable through `--font-body`, while
 *  Tailwind's `font-mono` reads `--mono`, so a chip that hardcodes it ignores
 *  the user's choice. A repo label IS a token; a steward's name is not. */
function Chip({
  on,
  onClick,
  children,
  ariaLabel,
  mono,
}: {
  on?: boolean
  onClick: () => void
  children: React.ReactNode
  ariaLabel?: string
  mono?: boolean
}) {
  return (
    <button
      type="button"
      aria-pressed={!!on}
      aria-label={ariaLabel}
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[12px] transition-colors focus-ring ${
        mono ? 'font-mono' : ''
      } ${
        on
          ? 'border-accent bg-accent-subtle text-accent'
          : 'border-border bg-transparent text-muted hover:border-border-strong hover:text-text'
      }`}
    >
      {children}
    </button>
  )
}

export interface StewardEditorProps {
  open: boolean
  onClose: () => void
  /** Absent or null = create. A record = edit that steward. */
  steward?: Steward | null
}

export default function StewardEditor({ open, onClose, steward }: StewardEditorProps) {
  const ime = useImeGuard()
  const { t } = useTranslation()
  const { active } = useIssueRadar()
  const scopeKey = repoScopeKey(active)
  const qc = useQueryClient()
  const editing = !!steward

  const [draft, setDraft] = useState<Draft>(() => draftFromSteward(steward))
  /** The values the form OPENED with, and the only thing the close guard measures
   *  dirtiness against.
   *
   *  A ref, not state: nothing renders from it, and it has to be readable by the
   *  same render that computes `dirty`. It advances with the name pre-fill below,
   *  because that write is the DIALOG's, not the user's — counting it would make
   *  an untouched create form ask for confirmation on its first Escape, which is
   *  the annoyance this guard exists to avoid inflicting. */
  const baseline = useRef<Draft>(draftFromSteward(steward))
  /** True while the discard confirmation is up. Only reachable when the form is
   *  dirty, so an untouched dialog still closes on one Escape. */
  const [confirmingDiscard, setConfirmingDiscard] = useState(false)
  /** Inline, on the name field — the 409 has one specific cause and one specific
   *  field, so a banner or a toast would make the user hunt for it. */
  const [nameError, setNameError] = useState<string | null>(null)
  /** Everything else that can fail (offline, 5xx, an unknown conflict). */
  const [formError, setFormError] = useState<string | null>(null)
  const [addingLabel, setAddingLabel] = useState(false)
  const [newLabel, setNewLabel] = useState('')
  /** True once the user has touched the name, so a suggestion arriving late can
   *  never overwrite what they typed. */
  const nameTouched = useRef(false)
  const addLabelRef = useRef<HTMLInputElement>(null)

  // Re-seed on every open, and when the dialog is re-pointed at a DIFFERENT steward
  // without closing. The component itself stays mounted while closed (Radix owns
  // the exit animation), so nothing resets on its own.
  //
  // Keyed on `steward?.id`, deliberately NOT on `steward`: the roster query this record
  // comes from refetches in the background, and every refetch hands down a new
  // object for the same steward. Depending on the object identity would therefore
  // wipe a half-typed form the moment an unrelated poll landed.
  useEffect(() => {
    if (!open) return
    const seeded = draftFromSteward(steward)
    baseline.current = seeded
    setDraft(seeded)
    setNameError(null)
    setFormError(null)
    setConfirmingDiscard(false)
    setAddingLabel(false)
    setNewLabel('')
    nameTouched.current = !!steward
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `steward?.id`, not `steward`: see above.
  }, [open, steward?.id])

  const namesQuery = useQuery({
    queryKey: ['issue-radar', 'steward-names', scopeKey],
    queryFn: () => issueRadarApi.suggestStewardNames(active),
    enabled: open,
  })
  const labelsQuery = useQuery({
    queryKey: ['issue-radar', 'labels', scopeKey],
    queryFn: () => issueRadarApi.labels(active),
    enabled: open,
  })

  /** The app's own agent roster — the same `/api/agents` list the chat and
   *  schedule pickers read, so a steward can only be pointed at an agent that
   *  actually exists. `0` = never force a refresh; `App` owns the sync. */
  const { agents } = useAgents(0)
  /** THE model list, gated on `open`: this dialog stays mounted while closed
   *  (Radix owns the exit animation), and an ungated observer would spawn
   *  kiro-cli's `--list-models` merely because the Stewards view is on screen. */
  const availableModels = useAvailableModels({ enabled: open })

  /**
   * Roster names, with the CURRENT agent kept present even when the roster no
   * longer lists it.
   *
   * A steward outlives the agent config it names: deleting an agent template must
   * not make this dialog silently re-point the steward at whatever happens to sort
   * first. The stale value leads the list instead, selected and visible, so the
   * user is the one who decides to change it.
   */
  const agentOptions = useMemo<string[]>(() => {
    const roster = agents.map(a => a.name)
    if (draft.agent && !roster.includes(draft.agent)) return [draft.agent, ...roster]
    return roster
  }, [agents, draft.agent])

  /**
   * Served model ids. `''` is NOT in here — it is `SimpleSelect`'s `clearLabel`
   * row, which is the inherit-the-agent's-default choice this field has always
   * offered as its placeholder. A placeholder is not a choice the user can see
   * they have made, so it becomes a real row.
   *
   * The served list leads with a model literally NAMED `auto`, which would put
   * two identically-labelled rows in one popup with no way to tell them apart,
   * so it folds into the `''` row rather than being listed twice.
   */
  const modelOptions = useMemo<string[]>(() => {
    const served = availableModels.map(m => m.name).filter(name => name !== 'auto')
    // Same reasoning as the agent roster: a model kiro no longer serves stays
    // selectable rather than being silently swapped for a served one.
    if (draft.model && !served.includes(draft.model)) return [draft.model, ...served]
    return served
  }, [availableModels, draft.model])

  const suggestions = useMemo(() => {
    const raw = namesQuery.data?.suggestions
    return (Array.isArray(raw) ? raw : []).filter(s => typeof s === 'string' && s.trim())
  }, [namesQuery.data])

  /** Repo labels first, in the repo's own order, then any free entry the user
   *  added or the steward already owned that the repo does not (or no longer) list —
   *  dropping those would silently un-own a label on the next save. */
  const labelChoices = useMemo(() => {
    const raw = labelsQuery.data?.labels
    const repoLabels = (Array.isArray(raw) ? raw : []).map(l => l.name)
    const seen = new Set(repoLabels)
    return [...repoLabels, ...draft.labels.filter(l => !seen.has(l))]
  }, [labelsQuery.data, draft.labels])

  // Pre-fill create mode from the first unused name, so the dialog opens on a
  // valid steward instead of an empty required field. Guarded on `nameTouched`.
  //
  // The baseline moves with it. This is the dialog writing to its own form, so a
  // user who opens it and immediately presses Escape has changed nothing and must
  // not be asked to confirm.
  useEffect(() => {
    if (!open || editing || nameTouched.current) return
    if (!draft.name && suggestions.length > 0) {
      baseline.current = { ...baseline.current, name: suggestions[0] }
      setDraft(d => (d.name ? d : { ...d, name: suggestions[0] }))
    }
  }, [open, editing, draft.name, suggestions])

  const patch = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft(d => ({ ...d, [key]: value }))

  const trimmedName = draft.name.trim()
  /** In edit mode the face is pinned to the steward's stored seed, so a rename keeps
   *  it (which is what the hint promises). In create mode there is no record yet,
   *  so the name IS the seed and the preview tracks it as the user types. */
  const seed = steward ? steward.avatar_seed : trimmedName
  /** What the plates render from while the name is still empty. */
  const plateSeed = seed || 'steward'
  /** The face in effect, resolved exactly as the plate resolves it, so the strip
   *  marks the face the preview is showing even for an out-of-range stored pin. */
  const shownVariant = stewardPlateVariant(plateSeed, draft.variant)

  const rollName = () => {
    if (suggestions.length === 0) return
    const at = suggestions.indexOf(trimmedName)
    nameTouched.current = true
    setNameError(null)
    patch('name', suggestions[(at + 1) % suggestions.length])
  }

  const pickName = (name: string) => {
    nameTouched.current = true
    setNameError(null)
    patch('name', name)
  }

  const toggleLabel = (name: string) =>
    setDraft(d => ({
      ...d,
      labels: d.labels.includes(name) ? d.labels.filter(l => l !== name) : [...d.labels, name],
    }))

  const closeAddLabel = () => {
    setAddingLabel(false)
    setNewLabel('')
  }

  const commitNewLabel = () => {
    const value = newLabel.trim()
    if (!value) return
    setDraft(d => (d.labels.includes(value) ? d : { ...d, labels: [...d.labels, value] }))
    setNewLabel('')
    setAddingLabel(false)
  }

  /** Clicking the face already in effect un-pins it, so a user who pinned by
   *  accident can get back to "follows the name" without reopening the dialog. */
  const pickVariant = (index: number) =>
    patch('variant', draft.variant === index ? null : index)

  /** Number(), not parseInt(): parseInt stops at the first non-digit, so the
   *  scientific notation an ``<input type="number">`` accepts and hands back
   *  verbatim ("1e1") parses to 1 and clamps to one slot instead of ten. Number()
   *  reads it as 10; a non-integer keeps the previous value rather than being
   *  silently floored, which is what the clamp would otherwise do to "1.5". */
  const clampSlot = (raw: string, fallback: number) => {
    const n = Number(raw)
    if (!Number.isInteger(n)) return fallback
    return Math.min(SLOT_MAX, Math.max(SLOT_MIN, n))
  }

  const submit = useMutation({
    mutationFn: async () => {
      if (steward) {
        const p: StewardPatch = {}
        if (trimmedName !== steward.name) p.name = trimmedName
        if (draft.variant !== steward.avatar_variant) p.avatar_variant = draft.variant
        if (draft.agent !== steward.agent) p.agent = draft.agent
        if (draft.model !== steward.model) p.model = draft.model
        if (draft.extraPrompt !== steward.extra_prompt) p.extra_prompt = draft.extraPrompt
        if (!sameLabels(draft.labels, Array.isArray(steward.labels) ? steward.labels : [])) {
          p.labels = draft.labels
        }
        if (draft.autoResolveConflicts !== steward.auto_resolve_conflicts) {
          p.auto_resolve_conflicts = draft.autoResolveConflicts
        }
        if (draft.autoMerge !== steward.auto_merge) p.auto_merge = draft.autoMerge
        if (draft.unattended !== steward.unattended) p.unattended = draft.unattended
        if (draft.maxOpen !== steward.max_open) p.max_open = draft.maxOpen
        if (draft.worktreeRoot !== steward.worktree_root) p.worktree_root = draft.worktreeRoot
        return issueRadarApi.updateSteward(active, steward.id, p)
      }
      const spec: StewardSpec = {
        name: trimmedName,
        avatar_variant: draft.variant,
        agent: draft.agent,
        model: draft.model,
        extra_prompt: draft.extraPrompt,
        labels: draft.labels,
        auto_resolve_conflicts: draft.autoResolveConflicts,
        auto_merge: draft.autoMerge,
        unattended: draft.unattended,
        max_open: draft.maxOpen,
        worktree_root: draft.worktreeRoot,
      }
      return issueRadarApi.createSteward(active, spec)
    },
    onMutate: () => {
      setNameError(null)
      setFormError(null)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issue-radar', 'stewards', scopeKey] })
      if (steward) qc.invalidateQueries({ queryKey: ['issue-radar', 'steward', scopeKey, steward.id] })
      qc.invalidateQueries({ queryKey: ['issue-radar', 'steward-names', scopeKey] })
      onClose()
    },
    onError: (err: unknown) => {
      if (isNameTakenError(err)) {
        setNameError(t('apps.issueRadar.views.stewards.editor.name_taken'))
        return
      }
      setFormError(
        t('apps.issueRadar.views.stewards.editor.save_failed', {
          message: err instanceof Error ? err.message : String(err ?? ''),
        }),
      )
    },
  })

  const title = editing
    ? t('apps.issueRadar.views.stewards.editor.title_edit')
    : t('apps.issueRadar.views.stewards.editor.title_create')
  // The dialog's accessible name, which `DialogContent` lets `aria-label`
  // outrank the visible title for: in edit mode the title alone ("Edit steward")
  // does not say WHICH steward, and that is the one thing a screen-reader user
  // needs before typing into it.
  const dialogName = editing
    ? t('apps.issueRadar.views.stewards.editor.aria_edit', { name: steward?.name ?? '' })
    : t('apps.issueRadar.views.stewards.editor.aria_create')

  const toggles: Array<{
    key: 'autoResolveConflicts' | 'autoMerge' | 'unattended'
    label: string
    hint: string
    testId: string
  }> = [
    {
      key: 'autoResolveConflicts',
      label: t('apps.issueRadar.views.stewards.editor.conflicts_label'),
      hint: t('apps.issueRadar.views.stewards.editor.conflicts_hint'),
      testId: 'steward-editor-auto-resolve',
    },
    {
      key: 'autoMerge',
      label: t('apps.issueRadar.views.stewards.editor.automerge_label'),
      hint: t('apps.issueRadar.views.stewards.editor.automerge_hint'),
      testId: 'steward-editor-auto-merge',
    },
    {
      key: 'unattended',
      label: t('apps.issueRadar.views.stewards.editor.unattended_label'),
      hint: t('apps.issueRadar.views.stewards.editor.unattended_hint'),
      testId: 'steward-editor-unattended',
    },
  ]

  const canSubmit = trimmedName.length > 0 && !submit.isPending

  /** Whether closing now would throw work away. Computed every render rather than
   *  memoized: it is eleven primitive comparisons, and a stale answer here is a
   *  half-filled form silently discarded. */
  const dirty = !sameDraft(draft, baseline.current)

  /**
   * Every way OUT of this dialog that is not a successful save: Escape, a click
   * on the overlay, the header's × and the footer's Cancel all land here.
   *
   * A dirty form gets the confirmation; an untouched one closes immediately,
   * because a prompt on every close is its own annoyance and trains the user to
   * dismiss it without reading. A successful submit calls `onClose` directly and
   * deliberately skips this — the work is saved, so there is nothing to lose.
   */
  const requestClose = () => {
    if (dirty) {
      setConfirmingDiscard(true)
      return
    }
    onClose()
  }

  return (
    <>
    <Dialog
      open={open}
      onOpenChange={next => {
        if (!next) requestClose()
      }}
    >
      <DialogContent
        maxWidth={660}
        aria-label={dialogName}
        data-testid="steward-editor"
        // The label entry box is a layer inside this one, and Radix has no
        // concept of it — so the first Escape has to retract it instead of
        // discarding the whole half-filled form. Handled HERE, not on the input:
        // DismissableLayer's own listener is capture-phase on `document`, so it
        // runs before any handler on a descendant, and `preventDefault` on this
        // callback is the documented way to veto the dismissal.
        onEscapeKeyDown={e => {
          if (!addingLabel) return
          e.preventDefault()
          closeAddLabel()
        }}
      >
        <DialogHeader>
          <StewardPlate seed={plateSeed} variant={draft.variant} size={26} />
          <DialogTitle>{title}</DialogTitle>
          <Badge variant="muted" className="ml-auto">
            {active.owner}/{active.repo}
          </Badge>
        </DialogHeader>

        <DialogBody>
          {/* ── Identity ── */}
          <SectionLabel>{t('apps.issueRadar.views.stewards.editor.section_identity')}</SectionLabel>
          <div className="flex items-start gap-4">
            <div className="flex h-[104px] w-[104px] shrink-0 items-center justify-center rounded-lg border border-border bg-bg-elevated">
              <StewardPlate seed={plateSeed} variant={draft.variant} size={78} />
            </div>
            <div className="min-w-0 flex-1">
              <div
                role="group"
                aria-label={t('apps.issueRadar.views.stewards.editor.face_strip_label')}
                className="flex flex-wrap gap-1.5"
              >
                {Array.from({ length: stewardPlateVariantCount }, (_, i) => (
                  <button
                    key={i}
                    type="button"
                    aria-pressed={shownVariant === i}
                    aria-label={t('apps.issueRadar.views.stewards.editor.face_variant', {
                      index: i + 1,
                    })}
                    data-testid={`steward-face-${i}`}
                    onClick={() => pickVariant(i)}
                    className={`flex h-[52px] w-[52px] items-center justify-center rounded-md border transition-colors focus-ring ${
                      shownVariant === i
                        ? 'border-accent bg-accent-subtle'
                        : 'border-border bg-bg-elevated hover:border-border-strong'
                    }`}
                  >
                    <StewardPlate seed={plateSeed} variant={i} size={40} />
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-muted">
                {t('apps.issueRadar.views.stewards.editor.face_hint')}
              </p>
            </div>
          </div>

          <div className="mt-4">
            <div className="flex items-end gap-2">
              {/* The label wraps only the INPUT, not the Roll button beside it:
                  an interactive descendant of a label is a second thing to click
                  in one hit area. */}
              {/* eslint-disable-next-line jsx-a11y/label-has-for -- nested + htmlFor→id both hold; the deprecated rule cannot see through the custom `Input`. */}
              <label htmlFor="steward-editor-name" className="min-w-0 flex-1">
                <span className="mb-1.5 block text-[13px] font-semibold text-text">
                  {t('apps.issueRadar.views.stewards.editor.name_label')}
                </span>
                <Input
                  id="steward-editor-name"
                  data-testid="steward-editor-name"
                  className="w-full"
                  value={draft.name}
                  aria-invalid={nameError ? true : undefined}
                  aria-describedby={nameError ? 'steward-editor-name-error' : undefined}
                  onChange={e => {
                    nameTouched.current = true
                    setNameError(null)
                    patch('name', e.target.value)
                  }}
                />
              </label>
              <Btn
                type="button"
                onClick={rollName}
                disabled={suggestions.length === 0}
                className="shrink-0 py-2"
              >
                {t('apps.issueRadar.views.stewards.editor.name_roll')}
              </Btn>
            </div>
            {nameError && (
              <p
                id="steward-editor-name-error"
                role="alert"
                data-testid="steward-editor-name-error"
                className="mt-1.5 text-[12px] font-medium text-danger"
              >
                {nameError}
              </p>
            )}
            {suggestions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {suggestions.slice(0, 6).map(name => (
                  <Chip key={name} on={name === trimmedName} onClick={() => pickName(name)}>
                    {name}
                  </Chip>
                ))}
              </div>
            )}
            <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
              {t('apps.issueRadar.views.stewards.editor.name_hint')}
            </p>
          </div>

          {/* ── Behaviour ── */}
          <SectionLabel>{t('apps.issueRadar.views.stewards.editor.section_behaviour')}</SectionLabel>
          {/* Both pickers render a <button>, not a <select>, so an external
              `<label htmlFor>` cannot associate with them — the heading is a
              plain span and the control carries the same string as its
              `aria-label`, the pattern FolderConfigModal's agent picker uses.
              The `data-testid` sits on the wrapper because SimpleSelect
              forwards a fixed prop set and no arbitrary attributes.

              SimpleSelect (Radix Select), NOT SearchableSelect (Radix Popover):
              this dialog traps focus, and a Popover portals its content OUTSIDE
              that trap, so the trap pulls focus straight back and the popup
              reads that as focus-outside and dismisses itself on open. Radix
              Select nests inside a modal dialog by design. */}
          <div className="grid grid-cols-2 gap-4">
            <div className="min-w-0" data-testid="steward-editor-agent">
              <span className="mb-1.5 block text-[13px] font-semibold text-text">
                {t('apps.issueRadar.views.stewards.editor.agent_label')}
              </span>
              <SimpleSelect
                aria-label={t('apps.issueRadar.views.stewards.editor.agent_label')}
                options={agentOptions}
                value={draft.agent}
                onChange={v => patch('agent', v)}
              />
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                {t('apps.issueRadar.views.stewards.editor.agent_hint')}
              </p>
            </div>
            <div className="min-w-0" data-testid="steward-editor-model">
              <span className="mb-1.5 block text-[13px] font-semibold text-text">
                {t('apps.issueRadar.views.stewards.editor.model_label')}
              </span>
              <SimpleSelect
                aria-label={t('apps.issueRadar.views.stewards.editor.model_label')}
                options={modelOptions}
                value={draft.model}
                // The inherit-the-agent's-default row. `clearLabel` is the one
                // affordance that can SET `''` back, so without it a user who
                // picked a model could never return the steward to inheriting.
                clearLabel={t('apps.issueRadar.views.stewards.editor.model_auto')}
                onChange={v => patch('model', v)}
              />
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                {t('apps.issueRadar.views.stewards.editor.model_hint')}
              </p>
            </div>
          </div>
          <div className="mt-4">
            <Field
              id="steward-editor-prompt"
              label={t('apps.issueRadar.views.stewards.editor.prompt_label')}
            >
              {/* No shared textarea primitive exists; Input's class string is
                  reused verbatim so the two controls cannot drift apart.
                  The label is `Field`'s, one component up, bound by htmlFor→id —
                  which no static rule can follow across that boundary. */}
              {/* eslint-disable-next-line jsx-a11y/control-has-associated-label */}
              <textarea
                id="steward-editor-prompt"
                data-testid="steward-editor-prompt"
                rows={3}
                value={draft.extraPrompt}
                placeholder={t('apps.issueRadar.views.stewards.editor.prompt_placeholder')}
                onChange={e => patch('extraPrompt', e.target.value)}
                className="w-full resize-y rounded-md border border-border bg-bg-elevated px-3 py-2 font-body text-sm text-text outline-none transition-colors focus-ring"
              />
            </Field>
          </div>

          {/* ── Scope ── */}
          <SectionLabel>{t('apps.issueRadar.views.stewards.editor.section_scope')}</SectionLabel>
          <div>
            <span className="mb-1.5 block text-[13px] font-semibold text-text" id="steward-editor-labels-label">
              {t('apps.issueRadar.views.stewards.editor.labels_label')}
            </span>
            <div className="flex flex-wrap items-center gap-1.5" aria-labelledby="steward-editor-labels-label" role="group">
              {labelChoices.map(name => (
                <Chip
                  key={name}
                  mono
                  on={draft.labels.includes(name)}
                  onClick={() => toggleLabel(name)}
                >
                  {name}
                </Chip>
              ))}
              {addingLabel ? (
                <span className="inline-flex items-center gap-1">
                  <Input
                    ref={addLabelRef}
                    aria-label={t('apps.issueRadar.views.stewards.editor.labels_add_placeholder')}
                    data-testid="steward-editor-new-label"
                    className="w-40 py-1 font-mono text-[12px]"
                    value={newLabel}
                    onChange={e => setNewLabel(e.target.value)}
                    // Escape is NOT handled by us beyond the binding's latch
                    // reset: Radix's DismissableLayer listens on `document` with
                    // `{ capture: true }`, so it has already decided to dismiss
                    // by the time a bubble-phase handler on this input runs.
                    {...ime.bindEnter({ onEnter: commitNewLabel })}
                  />
                  <IconButton
                    aria-label={t('apps.issueRadar.views.stewards.editor.labels_add_commit')}
                    variant="accent"
                    onClick={commitNewLabel}
                  >
                    <Plus size={14} className="lucide-inline" />
                  </IconButton>
                  <IconButton
                    aria-label={t('apps.issueRadar.views.stewards.editor.labels_add_cancel')}
                    onClick={closeAddLabel}
                  >
                    <X size={14} className="lucide-inline" />
                  </IconButton>
                </span>
              ) : (
                <Chip
                  onClick={() => {
                    setAddingLabel(true)
                    // Focus after paint: the input does not exist yet on this tick.
                    requestAnimationFrame(() => addLabelRef.current?.focus())
                  }}
                  ariaLabel={t('apps.issueRadar.views.stewards.editor.labels_add')}
                >
                  <Plus size={12} className="lucide-inline" />
                  {t('apps.issueRadar.views.stewards.editor.labels_add')}
                </Chip>
              )}
            </div>
            <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
              {t('apps.issueRadar.views.stewards.editor.labels_hint')}
            </p>
          </div>

          <div className="mt-3 rounded-lg border border-border">
            {toggles.map((row, i) => (
              <div
                key={row.key}
                className={`flex items-start justify-between gap-4 px-3.5 py-3 ${
                  i > 0 ? 'border-t border-border' : ''
                }`}
              >
                <span className="min-w-0">
                  <span className="block text-[13px] text-text">{row.label}</span>
                  <span className="mt-0.5 block text-[12px] leading-relaxed text-muted">
                    {row.hint}
                  </span>
                </span>
                <span className="pt-0.5" data-testid={row.testId}>
                  <Toggle
                    checked={draft[row.key]}
                    onChange={v => patch(row.key, v)}
                    label={row.label}
                  />
                </span>
              </div>
            ))}
          </div>

          {/* ── Limits ── */}
          <SectionLabel>{t('apps.issueRadar.views.stewards.editor.section_limits')}</SectionLabel>
          <div className="grid grid-cols-2 gap-4">
            <Field
              id="steward-editor-max-open"
              label={t('apps.issueRadar.views.stewards.editor.max_open_label')}
              hint={t('apps.issueRadar.views.stewards.editor.max_open_hint')}
            >
              <Input
                id="steward-editor-max-open"
                data-testid="steward-editor-max-open"
                className="w-full tabular-nums"
                type="number"
                min={SLOT_MIN}
                max={SLOT_MAX}
                value={draft.maxOpen}
                onChange={e => patch('maxOpen', clampSlot(e.target.value, draft.maxOpen))}
              />
            </Field>
            {/* No `hint`: the read-only note below already carries the one thing
                there is to say about this field, and two muted lines under one
                control read as two different facts. */}
            <Field
              id="steward-editor-backstop"
              label={t('apps.issueRadar.views.stewards.editor.backstop_label')}
            >
              <Input
                id="steward-editor-backstop"
                data-testid="steward-editor-backstop"
                className="w-full tabular-nums"
                readOnly
                value={BACKSTOP_WAKE_SECONDS}
                aria-describedby="steward-editor-backstop-fixed"
              />
              <p id="steward-editor-backstop-fixed" className="mt-1.5 text-[12px] text-muted">
                {t('apps.issueRadar.views.stewards.editor.backstop_fixed', {
                  seconds: BACKSTOP_WAKE_SECONDS,
                })}
              </p>
            </Field>
          </div>

          {/* ── Workspace ── */}
          <SectionLabel>{t('apps.issueRadar.views.stewards.editor.section_workspace')}</SectionLabel>
          <Field
            id="steward-editor-worktree"
            label={t('apps.issueRadar.views.stewards.editor.worktree_label')}
            hint={t('apps.issueRadar.views.stewards.editor.worktree_hint')}
          >
            <Input
              id="steward-editor-worktree"
              data-testid="steward-editor-worktree"
              className="w-full font-mono"
              value={draft.worktreeRoot}
              placeholder={t('apps.issueRadar.views.stewards.editor.worktree_placeholder')}
              onChange={e => patch('worktreeRoot', e.target.value)}
            />
          </Field>
        </DialogBody>

        <DialogFooter>
          {formError && (
            <p
              role="alert"
              data-testid="steward-editor-error"
              className="mr-auto text-[12px] font-medium text-danger"
            >
              {formError}
            </p>
          )}
          <Btn type="button" onClick={requestClose} className="py-1.5">
            {t('apps.issueRadar.views.stewards.editor.cancel')}
          </Btn>
          <Btn
            type="button"
            primary
            className="py-1.5"
            data-testid="steward-editor-submit"
            disabled={!canSubmit}
            onClick={() => submit.mutate()}
          >
            {submit.isPending
              ? t('apps.issueRadar.views.stewards.editor.saving')
              : editing
                ? t('apps.issueRadar.views.stewards.editor.submit_edit')
                : t('apps.issueRadar.views.stewards.editor.submit_create')}
          </Btn>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    {/* The dirty guard, as a second Dialog rather than a bespoke overlay: Radix
        keeps a global dismissable-layer and focus-scope stack, so whichever
        dialog opened LAST owns Escape and the focus trap. That is what lets this
        one answer the keypress without the form behind it also closing — and it
        is why the repo's own dialog primitive is the affordance here instead of
        `window.confirm`, which renders as an unthemeable OS sheet in the desktop
        app. */}
    <Dialog
      open={confirmingDiscard}
      onOpenChange={next => {
        // Escape or a click outside means "I did not mean to leave" — the
        // conservative answer, since the alternative destroys the form.
        if (!next) setConfirmingDiscard(false)
      }}
    >
      <DialogContent maxWidth={420} hideClose data-testid="steward-editor-discard">
        <DialogHeader>
          <DialogTitle>{t('apps.issueRadar.views.stewards.editor.discard_title')}</DialogTitle>
        </DialogHeader>
        <DialogBody>
          <DialogDescription>
            {t('apps.issueRadar.views.stewards.editor.discard_body')}
          </DialogDescription>
        </DialogBody>
        <DialogFooter>
          <Btn
            type="button"
            primary
            className="py-1.5"
            data-testid="steward-editor-discard-keep"
            onClick={() => setConfirmingDiscard(false)}
          >
            {t('apps.issueRadar.views.stewards.editor.discard_keep')}
          </Btn>
          <Btn
            type="button"
            danger
            className="py-1.5"
            data-testid="steward-editor-discard-confirm"
            onClick={() => {
              setConfirmingDiscard(false)
              onClose()
            }}
          >
            {t('apps.issueRadar.views.stewards.editor.discard_confirm')}
          </Btn>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  )
}
