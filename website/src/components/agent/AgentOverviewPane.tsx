/**
 * The agent editor's overview pane: three facts, then the wiring diagram.
 *
 * The strip answers what the previous layout answered only by making the reader
 * assemble it from three separate explanation boxes — how often this agent runs
 * unattended, whether its storage is private, and which model it actually ends up
 * on. Those boxes are gone; the facts they carried are here, and each is a value
 * rather than a sentence.
 */
import { Boxes, Clock, Cpu, Database, FolderOpen, Users, Waypoints, Webhook } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import AgentOverviewDiagram, { type AgentWireNode } from './AgentOverviewDiagram'
import type { AgentPaneKey } from './agentEditorSections'

/** Every node the diagram draws. A new node must join this union, and the
 *  union forces a `NODE_PANE` entry — so an unmapped node is a compile error
 *  rather than a button that answers nothing, which is the affordance bug
 *  this pane exists to prevent. */
type AgentNodeKey =
  | 'schedules' | 'routing' | 'webhook' | 'template' | 'workspace' | 'memory' | 'model'

/** Which editor pane each diagram node opens. Workspace and memory store are
 *  two nodes but one pane — the editor binds them side by side. */
const NODE_PANE: Record<AgentNodeKey, AgentPaneKey> = {
  schedules: 'schedules',
  routing: 'routing',
  webhook: 'webhook',
  template: 'template',
  workspace: 'place',
  memory: 'place',
  model: 'model',
}

export interface AgentOverviewPaneProps {
  hub: React.ReactNode
  /** Provider-branded name for the template field, e.g. "Agent Template". */
  templateLabel: string
  template: string
  workspace: string
  memoryStore: string
  /** The label to show for the model: either a pinned id or the inherit wording. */
  modelLabel: string
  /** True when nothing is pinned on the agent, so the value is an absence. */
  modelInherited: boolean
  /** What the pin resolves to once inheritance is applied. '' when unknown. */
  resolvedModel: string
  activeSchedules: number
  /** Schedules could not be read, so the count is unknown rather than zero. */
  schedulesUnknown?: boolean
  routingWords: number
  /** How many other agents point at this agent's workspace or memory store. Drives
   *  the stat only, where the OR is the honest reading of "its storage". */
  sharingAgents: number
  /** Another agent points at this agent's workspace. Separate from the memory flag:
   *  tagging both from one OR-ed value labels a private workspace "Shared"
   *  whenever only the memory store is. */
  workspaceShared: boolean
  /** Another agent points at this agent's memory store. */
  memoryShared: boolean
  /** Webhook tokens bound to this agent. Unbound tokens are the pane's business,
   *  not the diagram's: charging them here would draw N solid inputs per agent
   *  for bindings that do not exist. */
  webhookTokens: number
  /** The webhook store could not be read — unknown rather than zero. */
  webhooksUnknown?: boolean
  /** Opens the editor pane that edits what a clicked diagram node shows. The
   *  diagram is the overview's index, so a node that names a surface takes
   *  the reader there rather than only describing it. */
  onNavigate: (pane: AgentPaneKey) => void
}

function Stat({ icon, value, label }: { icon?: React.ReactNode; value: string; label: string }) {
  return (
    // `basis` plus a min width so three cells WRAP on a narrow pane instead of
    // squeezing until their labels collide. `last:border-r-0` is not enough once
    // they wrap — a wrapped row's last cell is mid-strip — so the border is on
    // the leading edge of every cell but the first instead.
    <div className="min-w-[132px] flex-1 basis-full border-t border-border px-3 py-2 first:border-t-0
                    sm:basis-[132px] sm:border-l sm:border-t-0 sm:first:border-l-0">
      <div className="flex items-center gap-1.5 text-[15px] leading-tight text-text-strong">
        {icon}
        <span className="truncate">{value}</span>
      </div>
      <div className="mt-0.5 text-[10px] uppercase tracking-[0.06em] text-muted">{label}</div>
    </div>
  )
}

export default function AgentOverviewPane({
  hub, templateLabel, template, workspace, memoryStore, modelLabel, modelInherited,
  resolvedModel, activeSchedules, schedulesUnknown, routingWords, sharingAgents,
  workspaceShared, memoryShared, webhookTokens, webhooksUnknown, onNavigate,
}: AgentOverviewPaneProps) {
  const { t } = useTranslation()
  const unknown = t('components.agentEditor.stat_unknown')

  const inputs: Array<AgentWireNode & { key: AgentNodeKey }> = [
    {
      key: 'schedules',
      icon: Clock,
      label: t('components.agentEditor.pane_schedules'),
      // A bare count, because the node's own label already names what is being
      // counted. Sidesteps a pluralised string whose grammar differs per
      // language for a number the label makes unambiguous.
      value: schedulesUnknown
        ? unknown
        : activeSchedules > 0 ? String(activeSchedules) : t('components.agentEditor.node_none'),
      muted: schedulesUnknown || activeSchedules === 0,
    },
    {
      key: 'routing',
      icon: Waypoints,
      label: t('pages.junctionAgentsPage.triggers'),
      value: routingWords > 0 ? String(routingWords) : t('components.agentEditor.node_none'),
      muted: routingWords === 0,
    },
    {
      key: 'webhook',
      icon: Webhook,
      label: t('components.agentEditor.pane_webhook'),
      // Dashed only while NOTHING is bound: the ghost treatment means "a real
      // input that carries no agent binding", and once a token names this agent
      // that claim is false. The node reports that bindings EXIST; whether each
      // can currently call in is the rail badge's live/total and the pane's
      // per-row marker, because a disabled binding is still a binding. Unknown
      // keeps the ghost — a store that cannot be read is not evidence a
      // binding exists.
      value: webhooksUnknown
        ? unknown
        : webhookTokens > 0 ? String(webhookTokens) : t('components.agentEditor.webhook_unbound_short'),
      muted: webhooksUnknown || webhookTokens === 0,
      ghost: webhooksUnknown || webhookTokens === 0,
    },
  ]

  const outputs: Array<AgentWireNode & { key: AgentNodeKey }> = [
    {
      key: 'template',
      icon: Boxes,
      label: templateLabel,
      value: template,
      mono: true,
    },
    {
      key: 'workspace',
      icon: FolderOpen,
      label: t('pages.junctionAgentsPage.workspace_2'),
      value: workspace,
      mono: true,
      ...(workspaceShared ? { tag: t('components.agentEditor.tag_shared') } : {}),
    },
    {
      key: 'memory',
      icon: Database,
      label: t('pages.junctionAgentsPage.memory_store'),
      value: memoryStore,
      mono: true,
      ...(memoryShared ? { tag: t('components.agentEditor.tag_shared') } : {}),
    },
    {
      key: 'model',
      icon: Cpu,
      label: t('pages.junctionAgentsPage.model'),
      value: modelLabel,
      mono: !modelInherited,
      muted: modelInherited,
    },
  ]

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap rounded-lg border border-border bg-bg-accent">
        <Stat
          icon={<Clock className="lucide-inline h-[15px] w-[15px]" aria-hidden="true" />}
          value={schedulesUnknown ? unknown : String(activeSchedules)}
          label={t('components.agentEditor.stat_active_schedules')}
        />
        <Stat
          icon={<Users className="lucide-inline h-[15px] w-[15px]" aria-hidden="true" />}
          value={String(sharingAgents)}
          label={t('components.agentEditor.stat_agents_sharing')}
        />
        <Stat
          value={resolvedModel || unknown}
          label={t('components.agentEditor.stat_resolved_model')}
        />
      </div>
      <AgentOverviewDiagram
        inputs={inputs}
        outputs={outputs}
        inputsLabel={t('components.agentEditor.group_how_work_arrives')}
        outputsLabel={t('components.agentEditor.wire_what_it_works_with')}
        hub={hub}
        onNodeSelect={key => {
          // The diagram hands back a plain string; only keys this pane
          // declared (and therefore mapped) navigate.
          const pane = NODE_PANE[key as AgentNodeKey]
          if (pane) onNavigate(pane)
        }}
      />
    </div>
  )
}
