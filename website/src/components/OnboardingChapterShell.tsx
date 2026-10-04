import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react'
import { createPortal } from 'react-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'

import { i18nT } from '../i18n/t'
import junctionGlyphUrl from '../assets/junction-glyph.svg'
import { BrandGlyph } from './BrandIcon'

// Route lockup: a trunk line crossing the upper panel with the Junction mark
// set on it as the interchange, and one branch peeling off below. The art
// stays in the top half so it never runs behind the headline.
function RouteLockup() {
  const reduceMotion = useReducedMotion()
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-x-0 top-[34%] h-[2px] bg-accent-fg/20" />
      <div className="absolute left-1/2 top-[34%] h-[2px] w-[42%] origin-left rotate-[32deg] bg-accent-fg/15" />
      <motion.div
        className="absolute left-1/2 top-[34%] flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-2xl bg-accent-fg text-accent shadow-lg"
        initial={reduceMotion ? false : { opacity: 0, scale: 0.86 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.45, type: 'spring', bounce: 0.3 }}
      >
        <BrandGlyph url={junctionGlyphUrl} size={40} />
      </motion.div>
    </div>
  )
}

// The accent left panel — brand lockup + route motif + the flow's copy.
// Factored out so the persistent HOST and the standalone shell render the exact
// same aside; when it lives in the host it is mounted ONCE and only its copy
// text changes between flows, so the lockup never re-runs its entrance.
// Exported so the first-run CLI setup gate (KiroPrerequisiteGate) renders the SAME
// panel — identical size, identical route positions — instead of a look-alike
// copy that drifts.
export function ShellAside({ copy }: { copy: ShellAsideCopy }) {
  return (
    <aside className="relative flex min-h-[248px] w-full shrink-0 overflow-hidden bg-accent text-accent-fg sm:min-h-0 sm:w-[36%]">
      <RouteLockup />
      <div className="relative z-10 flex w-full flex-col p-7 sm:p-10">
        <div className="flex items-center gap-3">
          <BrandGlyph url={junctionGlyphUrl} size={24} />
          <span className="text-[15px] font-bold">{i18nT('components.onboardingChapterShell.junction')}</span>
        </div>
        <div className="mt-auto max-w-[290px]">
          <h1 className="text-4xl font-semibold leading-[1.05] tracking-[-0.02em] sm:text-[clamp(2.2rem,4vw,3.5rem)]">
            {copy.panelHeadline}
          </h1>
          <p className="mt-5 max-w-[270px] text-sm leading-relaxed text-accent-fg/80">
            {copy.panelBody}
          </p>
        </div>
        <p className="mt-8 text-[12px] font-medium text-accent-fg/75">{copy.panelFootnote}</p>
      </div>
    </aside>
  )
}

// Shared class strings so the host-owned <section> slot and the standalone
// shell's <section> are byte-identical (same flex layout / min-heights).
// Exported for the Kiro CLI setup gate, which composes the same three pieces
// (scrim + panel + section) around its own non-chapter content.
export const SECTION_CLASS =
  'flex min-h-[calc(100vh-248px)] min-w-0 flex-1 flex-col bg-card sm:min-h-0'
export const SCRIM_CLASS =
  'fixed inset-0 z-[120] flex min-h-0 overflow-y-auto bg-bg/70 backdrop-blur-sm p-0 text-text sm:items-center sm:justify-center sm:p-6'
export const PANEL_CLASS =
  'relative flex min-h-screen w-full flex-col overflow-hidden bg-card shadow-xl sm:h-[min(760px,calc(100vh-48px))] sm:min-h-0 sm:max-w-6xl sm:flex-row sm:rounded-2xl sm:border sm:border-border'

export interface ShellAsideCopy {
  ariaLabel: string
  panelHeadline: string
  panelBody: string
  panelFootnote: string
}

interface OnboardingShellApi {
  // The single persistent dialog element. Flows use it for their focus trap.
  dialogRef: RefObject<HTMLDivElement>
  // The persistent right-column <section>; flows portal their header/body/footer
  // into it. Null until the host has mounted the chrome.
  sectionSlot: HTMLElement | null
  // A flow registers its aside copy while open (and clears it on close). The
  // host shows the chrome whenever any flow is registered.
  setAsideCopy: (id: string, copy: ShellAsideCopy | null) => void
}

const OnboardingShellContext = createContext<OnboardingShellApi | null>(null)

/**
 * Single persistent host for the first-run modal chrome. Wrap the first-run
 * flows (AgentImportFlow + OnboardingFlow) in ONE of these so the scrim, accent
 * panel, and floating mascots mount exactly once and stay mounted across the
 * import→customize (and step 1→2) hand-offs. Only the right-column content and
 * the aside copy swap — nothing in the accent panel remounts, so the track
 * lockup never replays its entrance. That is the fix for the transition glitch.
 *
 * When a flow renders OUTSIDE a host (e.g. a unit test rendering it standalone),
 * OnboardingChapterShell falls back to rendering its own full chrome, so
 * behavior is unchanged in isolation.
 */
export function OnboardingShellHost({ children }: { children: ReactNode }) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const [sectionSlot, setSectionSlot] = useState<HTMLElement | null>(null)
  const [copies, setCopies] = useState<Record<string, ShellAsideCopy>>({})

  const setAsideCopy = useCallback((id: string, copy: ShellAsideCopy | null) => {
    setCopies(prev => {
      if (copy === null) {
        if (!(id in prev)) return prev
        const next = { ...prev }
        delete next[id]
        return next
      }
      const cur = prev[id]
      if (
        cur
        && cur.ariaLabel === copy.ariaLabel
        && cur.panelHeadline === copy.panelHeadline
        && cur.panelBody === copy.panelBody
        && cur.panelFootnote === copy.panelFootnote
      ) {
        return prev
      }
      return { ...prev, [id]: copy }
    })
  }, [])

  const api = useMemo<OnboardingShellApi>(
    () => ({ dialogRef, sectionSlot, setAsideCopy }),
    [sectionSlot, setAsideCopy],
  )

  // Exactly one flow is open at a time by construction; if two ever overlap for
  // a commit, the most recently registered wins.
  const ids = Object.keys(copies)
  const active = ids.length > 0 ? copies[ids[ids.length - 1]] : null

  return (
    <OnboardingShellContext.Provider value={api}>
      {children}
      {active
        && createPortal(
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={active.ariaLabel}
            className={SCRIM_CLASS}
          >
            <div className={PANEL_CLASS}>
              <ShellAside copy={active} />
              <section ref={setSectionSlot} className={SECTION_CLASS} />
            </div>
          </div>,
          document.body,
        )}
    </OnboardingShellContext.Provider>
  )
}

/**
 * Two-column first-run modal shell: a translucent scrim, an accent left panel
 * with the brand lockup + floating mascots, and a right column with a FIXED
 * header (eyebrow + "Skip all" and an optional title/description block), a
 * SCROLLABLE body, and an optional PINNED footer.
 *
 * The header/footer are passed as SLOTS so each flow keeps its own title copy,
 * focus refs, and footer navigation — the Import flow hides the title/footer on
 * its full-panel scanning/error/empty states, while the Customize chapter
 * always shows them.
 *
 * When rendered inside an <OnboardingShellHost>, this component does NOT render
 * its own chrome: it registers its aside copy with the host and portals just
 * the right-column content (header + body + footer) into the host's persistent
 * <section>. Outside a host it renders the full chrome itself (standalone /
 * tests). Either way the flow call sites are identical.
 */
export default function OnboardingChapterShell({
  panelHeadline,
  panelBody,
  panelFootnote,
  eyebrow,
  onSkipAll,
  skipDisabled,
  header,
  footer,
  dialogRef,
  ariaLabel,
  children,
}: {
  panelHeadline: string
  panelBody: string
  panelFootnote: string
  // The uppercase eyebrow above the stage title, e.g. "CUSTOMIZE · 1 OF 2" or
  // "IMPORT SETUP · 1 OF 4". A plain node so each flow owns its counter logic.
  // A single-screen chapter passes just its name, with no counter.
  eyebrow: ReactNode
  // Omit to render NO skip affordance at all — that is how a MANDATORY chapter
  // (the Privacy chapter) is expressed: there is no handler because there is no
  // way past it but forward. Every skippable chapter passes one.
  onSkipAll?: () => void
  skipDisabled?: boolean
  // Stage title/description block. Nullable: the Import flow passes null for its
  // full-panel scanning/error/empty states, which carry their own headings.
  header?: ReactNode
  // Pinned footer navigation. Nullable for the same full-panel states.
  footer?: ReactNode
  // Standalone mode: the dialog element. Inside a host the dialog is host-owned
  // and this ref is unused (the flow reads the host's dialogRef for its trap).
  dialogRef: RefObject<HTMLDivElement>
  ariaLabel: string
  children: ReactNode
}) {
  const host = useContext(OnboardingShellContext)
  // Stable per-mount id so the flow's aside-copy registration can be cleared on
  // close/unmount without colliding with the other flow's registration.
  const id = useId()

  // Register the aside copy with the host while mounted; clear it on unmount.
  // Deps are all primitive strings, so this never loops on node identity.
  useEffect(() => {
    if (!host) return
    host.setAsideCopy(id, { ariaLabel, panelHeadline, panelBody, panelFootnote })
    return () => host.setAsideCopy(id, null)
  }, [host, id, ariaLabel, panelHeadline, panelBody, panelFootnote])

  // The right-column content — identical markup in both host and standalone
  // modes, so the flows' header/body/footer render the same either way.
  const sectionInner = (
    <>
      <header className="shrink-0 px-6 pt-7 sm:px-10 sm:pt-10">
        <div className="flex items-center justify-between gap-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
            {eyebrow}
          </p>
          {onSkipAll && (
            <button
              type="button"
              aria-label={i18nT('components.onboardingChapterShell.skip_all_setup_and_onboarding')}
              disabled={skipDisabled}
              onClick={onSkipAll}
              className="inline-flex items-center gap-1.5 text-[13px] font-medium text-muted transition-colors hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
            >
              {i18nT('components.onboardingChapterShell.skip_all')} <ArrowRight className="lucide-inline" />
            </button>
          )}
        </div>
        {header}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <main className="w-full px-6 pb-8 pt-6 sm:px-10 sm:pb-10 sm:pt-6">
          <div className="mx-auto max-w-2xl">{children}</div>
        </main>
      </div>
      {footer && (
        <footer className="flex shrink-0 flex-wrap items-center justify-end gap-3 px-6 pt-4 pb-6 sm:px-10 sm:pb-10">
          {footer}
        </footer>
      )}
    </>
  )

  // Host mode: portal the right-column content into the persistent <section>.
  if (host) {
    return host.sectionSlot ? createPortal(sectionInner, host.sectionSlot) : null
  }

  // Standalone mode: render the full chrome ourselves.
  return createPortal(
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      className={SCRIM_CLASS}
    >
      <div className={PANEL_CLASS}>
        <ShellAside copy={{ ariaLabel, panelHeadline, panelBody, panelFootnote }} />
        <section className={SECTION_CLASS}>{sectionInner}</section>
      </div>
    </div>,
    document.body,
  )
}

export { OnboardingShellContext }
