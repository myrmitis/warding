/**
 * Shared /api stub for the agent-roster screenshot harnesses.
 *
 * Both `capture-agents-tab.mjs` and `capture-agents-list-modal.mjs` need the same
 * four endpoints to render a populated roster, and each had its own copy — which
 * the jscpd gate correctly flagged. The FIXTURES stay per-script (they are the
 * interesting, deliberately-different part); only the wiring lives here.
 */
import { json } from './stub-dashboard-api.mjs'

/**
 * Build a `stubDashboardApi({ extra })` handler for the agent roster.
 *
 * @param {object} opts
 * @param {Array<object>} opts.agents        `/api/agents` roster
 * @param {string} [opts.defaultAgent]       which agent new sessions use
 * @param {Array<string>} [opts.workspaces]  workspace names; defaults to the
 *   distinct workspaces the agents point at, so a caller cannot hand the select a
 *   list that is missing the value an agent is bound to.
 * @param {Array<string>} [opts.memoryStores] as above, for memory stores
 * @param {Array<string>} [opts.installed]   agent-template names
 */
export function agentsApi({ agents, defaultAgent, workspaces, memoryStores, installed }) {
  const uniq = key => [...new Set(agents.map(c => c[key]).filter(Boolean))]
  const wsNames = workspaces ?? uniq('workspace')
  const msNames = memoryStores ?? uniq('memory_store')
  const templates = installed ?? uniq('kiro_agent')

  return async function handle(path, route) {
    if (path === '/api/agents') {
      return json(route, { agents, default_agent: defaultAgent ?? agents[0]?.name ?? '' }), true
    }
    if (path === '/api/agents/installed') {
      return json(route, templates.map(name => ({ name }))), true
    }
    if (path === '/api/workspaces') {
      return json(route, { workspaces: wsNames.map(name => ({ name })) }), true
    }
    if (path === '/api/config/junction') {
      return json(route, { memory_stores: Object.fromEntries(msNames.map(n => [n, {}])) }), true
    }
    return false
  }
}
