import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

// Mock data for various endpoints
export const mockMemorySettings = {
  history_idle_hours: 24,
  history_max_days: 30,
  auto_consolidate: true,
}

export const mockMemoryPreferences = {
  content: '# My Preferences\n\n- Use TypeScript\n- Follow the house style guide',
  last_updated: '2026-03-20T10:00:00Z',
}

export const mockMemoryProjects = {
  content: '# Projects\n\n## Warding\n\nAI-powered development assistant.',
  last_updated: '2026-03-20T10:00:00Z',
}

export const mockMemoryHistory = {
  content: '# Today\n\n- Worked on integration tests\n- Fixed memory consolidation',
  last_updated: '2026-03-20T10:00:00Z',
}

export const mockCrons = [
  {
    id: 'cron-1',
    name: 'Check system status',
    rule: 'Check system status',
    message: 'Check system health',
    schedule: '*/5 * * * *',
    enabled: true,
    last_run: '2026-03-20T10:00:00Z',
    next_run: '2026-03-20T10:05:00Z',
    last_status: '',
  },
  {
    id: 'cron-2',
    name: 'Backup database',
    rule: 'Backup database',
    message: 'Run backup script',
    schedule: '0 2 * * *',
    enabled: false,
    last_run: '2026-03-19T02:00:00Z',
    next_run: null,
    last_status: '',
  },
]

export const mockSkills = [
  {
    name: 'acme-writing',
    key: 'acme-writing',
    description: 'Acme writing guidelines for documents',
    always: true,
    source: 'warding',
    dir: '/path/to/skills/acme-writing',
  },
  {
    name: 'code-search',
    key: 'code-search',
    description: 'Search code in internal repositories',
    always: false,
    source: 'warding',
    dir: '/path/to/skills/code-search',
  },
]

export const mockSkillDetail = {
  name: 'acme-writing',
  key: 'acme-writing',
  content: '---\nname: acme-writing\ndescription: Acme writing guidelines for documents\nalways: true\ntriggers: writing, docs, narrative\ntags: [skill, writing, acme]\n---\n# Acme Writing\n\nGuidelines for clear technical writing.',
  description: 'Acme writing guidelines for documents',
  always: true,
  source: 'warding',
  dir: '/path/to/skills/acme-writing',
}

export const mockCodeSearchDetail = {
  name: 'code-search',
  key: 'code-search',
  content: '---\nname: code-search\ndescription: Search code in internal repositories\ntags: [skill, code, search]\n---\n# Code Search\n\nSearch internal code repositories.',
  description: 'Search code in internal repositories',
  always: false,
  source: 'warding',
  dir: '/path/to/skills/code-search',
}

export const mockMcpServers = [
  {
    name: 'corp-mcp',
    status: 'ok',
    enabled: true,
    tools: ['ReadWebPage', 'TrackerGetTask'],
    disabledTools: [],
    command: 'node /path/to/corp-mcp',
    presence: { warding: true, kiroGlobal: true, ccGlobal: false },
  },
  {
    name: 'acme-slack-mcp',
    status: 'ok',
    enabled: false,
    tools: ['search', 'post_message'],
    disabledTools: ['post_message'],
    command: 'node /path/to/slack-mcp',
    presence: { warding: false, kiroGlobal: false, ccGlobal: false },
  },
]

export const mockHooks = [
  {
    id: 'hook-1',
    name: 'Deploy Notifier',
    event: 'UserPromptSubmit',
    matcher: '*deploy*',
    command: 'echo "Deploy started"',
    timeout: 30,
    enabled: true,
    last_run: Math.floor(Date.now() / 1000) - 3600,
    last_status: 'ok',
    run_count: 15,
  },
]

export const mockMemoryGraph = {
  nodes: [
    { id: 'p1', label: 'Use TypeScript', group: 'preference', title: 'Use TypeScript' },
    { id: 'p2', label: 'Follow the house style guide', group: 'preference', title: 'Follow the house style guide' },
    { id: 'pr1', label: 'Warding', group: 'project', title: 'Warding' },
    { id: 'pr2', label: 'Warding: AI-powered assistant', group: 'project', title: 'AI-powered development assistant' },
    { id: 's1', label: 'pref.editor', group: 'semantic', title: 'pref.editor = vim' },
    { id: 'l1', label: 'Check PRs before building', group: 'lesson', title: 'Always check for existing open PRs' },
    { id: 'h1', label: '2026-03-25', group: 'history', title: '2026-03-25 work session' },
  ],
  edges: [
    { from: 'pr1', to: 'pr2' },
    { from: 'l1', to: 'pr1' },
  ],
}

// Request handlers
export const handlers = [
  // Minting a sandbox document URL. Every surface that renders model-authored
  // HTML in an iframe now asks the gateway for a document URL instead of
  // building a `blob:` one, so ANY suite that mounts one of those frames against
  // the real api client reaches this. Answered here rather than per-suite: the
  // catch-all fallback returns an empty 200, which resolves to no `url`, and the
  // frame then never mounts — a failure that surfaces as an unrelated-looking
  // `expected null not to be null` in whichever shard happens to run it.
  http.post('/api/sandbox-doc', () => {
    return HttpResponse.json({ url: '/sandbox-doc/msw-test-doc/msw-test-token' })
  }),

  // Memory endpoints
  http.get('/api/memory/settings', () => {
    return HttpResponse.json(mockMemorySettings)
  }),
  
  http.put('/api/memory/settings', async ({ request }) => {
    const body = await request.json()
    return HttpResponse.json({ ...mockMemorySettings, ...body })
  }),
  
  http.get('/api/memory/preferences', () => {
    return HttpResponse.json(mockMemoryPreferences)
  }),
  
  http.put('/api/memory/preferences', async ({ request }) => {
    const body = await request.json() as { content: string }
    return HttpResponse.json({ ...mockMemoryPreferences, content: body.content })
  }),
  
  http.get('/api/memory/projects', () => {
    return HttpResponse.json(mockMemoryProjects)
  }),
  
  http.put('/api/memory/projects', async ({ request }) => {
    const body = await request.json() as { content: string }
    return HttpResponse.json({ ...mockMemoryProjects, content: body.content })
  }),
  
  http.get('/api/memory/history', () => {
    return HttpResponse.json(mockMemoryHistory)
  }),
  
  http.put('/api/memory/history', async ({ request }) => {
    const body = await request.json() as { content: string }
    return HttpResponse.json({ ...mockMemoryHistory, content: body.content })
  }),
  
  http.post('/api/memory/consolidate', async ({ request }) => {
    const body = await request.json() as { key: string; include_history: boolean }
    return HttpResponse.json({ success: true, key: body.key })
  }),
  
  http.get('/api/memory/stats', () => {
    return HttpResponse.json({
      total_entries: 42,
      total_size_bytes: 102400,
      oldest_entry: '2026-01-01T00:00:00Z',
      newest_entry: '2026-03-20T10:00:00Z',
    })
  }),
  
  http.get('/api/memory/embedding-status', () => {
    return HttpResponse.json({
      enabled: false,
      model: null,
      total_embeddings: 0,
    })
  }),
  
  http.get('/api/memory/semantic', () => {
    return HttpResponse.json({
      entries: [],
      total: 0,
    })
  }),

  http.get('/api/memory/graph', () => {
    return HttpResponse.json(mockMemoryGraph)
  }),
  
  // Cron endpoints
  http.get('/api/cron-folders', () => {
    return HttpResponse.json([])
  }),

  http.get('/api/crons', () => {
    return HttpResponse.json({ jobs: mockCrons })
  }),
  
  http.post('/api/crons', async ({ request }) => {
    const body = await request.json() as { name: string; message: string; every?: number; cron?: string; agent?: string }
    const newCron = {
      id: `cron-${Date.now()}`,
      name: body.name,
      rule: body.name,
      message: body.message,
      schedule: body.cron || `every ${body.every}s`,
      enabled: true,
      last_run: null,
      next_run: null,
      last_status: '',
      agent: body.agent || '',
    }
    return HttpResponse.json(newCron, { status: 201 })
  }),
  
  http.delete('/api/crons/:id', () => {
    return HttpResponse.json({ success: true })
  }),
  
  http.post('/api/crons/:id/enable', async ({ request }) => {
    const body = await request.json() as { enabled: boolean }
    return HttpResponse.json({ success: true, enabled: body.enabled })
  }),
  
  // Skills endpoints
  http.get('/api/skills', () => {
    return HttpResponse.json(mockSkills)
  }),
  
  http.get('/api/skills/:name', ({ params }) => {
    const name = params.name as string
    if (name === 'code-search') return HttpResponse.json(mockCodeSearchDetail)
    return HttpResponse.json(mockSkillDetail)
  }),

  // Directory browser: SKILL.md is the only file in each fixture skill,
  // mirroring the typical case for a flat-layout skill.  Routes use the
  // ``/-/`` separator (GitLab-style) so a skill named e.g. ``utils/tree``
  // can't collide with the browser endpoint.
  http.get('/api/skills/:name/-/tree', ({ params }) => {
    const name = params.name as string
    return HttpResponse.json({
      name,
      root: `/path/to/skills/${name}`,
      entries: [{ path: 'SKILL.md', type: 'file', size: 256 }],
    })
  }),

  http.get('/api/skills/:name/-/file', ({ params, request }) => {
    const name = params.name as string
    const url = new URL(request.url)
    const path = url.searchParams.get('path')
    if (path !== 'SKILL.md') return new HttpResponse(null, { status: 404 })
    const detail = name === 'code-search' ? mockCodeSearchDetail : mockSkillDetail
    return HttpResponse.json({ name, path, content: detail.content })
  }),

  http.post('/api/skills', async ({ request }) => {
    const body = await request.json() as { name: string; content: string }
    return HttpResponse.json({
      name: body.name,
      key: body.name,
      content: body.content,
      always: false,
      source: 'warding',
      dir: `/path/to/skills/${body.name}`,
    }, { status: 201 })
  }),
  
  http.put('/api/skills/:name', async ({ request }) => {
    const body = await request.json() as { content: string }
    return HttpResponse.json({
      ...mockSkillDetail,
      content: body.content,
    })
  }),
  
  http.delete('/api/skills/:name', () => {
    return HttpResponse.json({ success: true })
  }),
  
  // MCP endpoints
  http.get('/api/mcp', () => {
    return HttpResponse.json(mockMcpServers)
  }),
  
  http.get('/api/mcp/probe', () => {
    return HttpResponse.json([])
  }),
  
  http.post('/api/mcp/toggle', async ({ request }) => {
    const body = await request.json() as { name: string; enabled: boolean }
    return HttpResponse.json({ success: true, name: body.name, enabled: body.enabled })
  }),
  
  http.post('/api/mcp/toggle-tool', async ({ request }) => {
    const body = await request.json() as { server: string; tool: string; enabled: boolean }
    return HttpResponse.json({ success: true, tool: body.tool, enabled: body.enabled })
  }),
  
  http.post('/api/mcp/toggle-all', async ({ request }) => {
    const body = await request.json() as { enabled: boolean }
    return HttpResponse.json({ success: true, enabled: body.enabled })
  }),
  
  http.post('/api/mcp/probe', () => {
    return HttpResponse.json(mockMcpServers)
  }),
  
  http.post('/api/mcp/sync', () => {
    return HttpResponse.json({ success: true })
  }),
  
  http.post('/api/mcp/remove', async ({ request }) => {
    const body = await request.json() as { name: string }
    return HttpResponse.json({ success: true, name: body.name })
  }),
  
  // Sessions endpoint for consolidation
  http.get('/api/sessions', () => {
    return HttpResponse.json({
      sessions: [],
    })
  }),
  
  // Lessons endpoint
  http.get('/api/lessons', () => {
    return HttpResponse.json({
      lessons: [],
    })
  }),
  
  http.post('/api/lessons', async ({ request }) => {
    const body = await request.json() as { rule: string; category: string }
    return HttpResponse.json(
      {
        rule: body.rule,
        category: body.category,
        ts: new Date().toISOString(),
      },
      { status: 201 }
    )
  }),
  
  http.delete('/api/lessons', () => {
    return HttpResponse.json({ success: true })
  }),
  
  // Agents endpoint
  http.get('/api/agents/installed', () => {
    return HttpResponse.json([
      { name: 'default', source: 'builtin' },
      { name: 'warding', source: 'builtin' },
    ])
  }),
  
  // Hooks endpoints
  http.get('/api/hooks', () => {
    return HttpResponse.json({ hooks: mockHooks })
  }),

  http.post('/api/hooks', async ({ request }) => {
    const body = await request.json() as any
    return HttpResponse.json(
      {
        id: `hook-${Date.now()}`,
        ...body,
        last_run: 0,
        last_status: '',
        run_count: 0,
        enabled: true,
      },
      { status: 201 }
    )
  }),

  http.put('/api/hooks/:id', async ({ request }) => {
    const body = await request.json()
    return HttpResponse.json({ success: true, ...body })
  }),

  http.delete('/api/hooks/:id', () => {
    return HttpResponse.json({ success: true })
  }),

  http.post('/api/hooks/:id/toggle', () => {
    return HttpResponse.json({ success: true })
  }),

  http.post('/api/hooks/:id/test', () => {
    return HttpResponse.json({
      result: {
        exit_code: 0,
        duration_ms: 100,
        stdout: 'Test output',
        stderr: '',
      },
    })
  }),

  // Fork slot endpoint
  http.post('/api/chat/slots/:slot/fork', ({ params }) => {
    return HttpResponse.json({ ok: true, key: `${params.slot}-fork` })
  }),

  // Dashboard config endpoints
  http.get('/api/dashboard/config', () => {
    return HttpResponse.json({ restore_sessions: false, restore_window_minutes: 30, merge_queued_messages: false })
  }),

  http.put('/api/dashboard/config', async ({ request }) => {
    await request.json()
    return HttpResponse.json({ ok: true })
  }),

  // Chat config endpoint
  http.get('/api/chat/config', () => {
    return HttpResponse.json({ historyExpanded: false, notifLimit: 50, collapseAllSteps: true })
  }),
]

// Fallback (LAST — specific handlers above always win): happy-dom performs REAL
// network I/O for DOM-driven loads (widget `<script src>`, blob: `<iframe>`
// navigation) that jsdom never did; left alone they dial localhost — ECONNREFUSED
// spam plus a fork-worker socket-teardown crash. This fallback answers any
// otherwise-unmatched request so nothing dials.
//
// LOUD-BY-DEFAULT (fail-closed): rather than empty-200 everything-except-`/api`
// (which would silently pass a test whose component fetched a mistyped
// non-`/api` resource, an app-backend `/apps/{name}/api/*` route, or an external
// URL), we 501 EVERYTHING except a NARROW allowlist of the same-origin
// DOM-driven loads this fallback actually exists for. So a missing/typo'd mock —
// API or otherwise — surfaces loudly instead of masquerading as success.
//
// Allowlisted (empty-200, no dial): `blob:`/`data:` URLs (live-iframe srcdoc /
// blob navigation), SAME-ORIGIN static asset paths happy-dom eager-loads for
// a widget iframe (`/vendor/*` runtime scripts, `/assets/*`, `/static/*`, and
// bare root files like `/logo.png`), and SAME-ORIGIN app-route iframe targets
// (`/pdf`) that a real backend would serve but this suite never boots. Everything
// else — `/api/**`, `/apps/*/api/*`, cross-origin — gets 501.
//
// `/pdf` (PdfPreview / FileRenderers): `disableIframePageLoading` makes
// happy-dom itself refuse the navigation and throw a loud, harmless
// `NotSupportedError` synchronously — but that refusal is not the end of the
// story. happy-dom's `AsyncTaskManager` still tracks the underlying fetch task
// and can retry/resolve it later, off the DOM-connect call stack, well after
// the test that triggered it has finished. With no matching mock this fallback
// 501s that stray request, which surfaces as a genuine `ECONNREFUSED` socket
// dial seconds later — landing during vitest's fork-worker teardown, where it
// can crash the whole worker instead of failing one test. Matching it here
// (like the static-asset paths above) lets happy-dom's own retry find a
// same-origin 200 instead of a 501, so it resolves quietly instead of falling
// through to a real dial.
// Must match `environmentOptions.happyDOM.url` in vite.config.ts — that is
// happy-dom's actual document origin for every test, NOT its own factory
// default (localhost:3000). vite.config.ts pins it to the gateway's real
// default port (6776) so "the dashboard" and "a dev server" stay
// distinguishable in tests; when this drifts from that value, same-origin
// asset requests injected by DOM-driven loads (e.g. dashboardTheme.ts's
// <link>/<iframe> elements) fall through to the loud 501 below instead of
// the empty-200 allowlist branch, and happy-dom's retry/abort handling around
// that unexpected response can crash the fork worker on teardown.
const TEST_ORIGIN = 'http://localhost:6776'
const DOM_DRIVEN_LOAD_RE = /^\/(vendor|assets|static)\/|^\/pdf$|^\/[^/]+\.[a-z0-9]+$/i

// Path-kind probe (`usePathKind`): markdown inline-code chips HEAD this endpoint
// to learn whether a path-shaped string is a file, a directory, or absent, and
// only become clickable for the first two. Any transcript-rendering test would
// otherwise hit the 501 fallback below purely as a side effect of rendering
// prose that mentions a path.
//
// The default answer is "missing" — chips stay inert, which is what a test that
// is not about chips wants. A test that needs `file`/`dir` stubs
// `globalThis.fetch` directly (see MarkdownRenderer.test.tsx), matching the
// sibling HEAD probe in DiffBlock.
handlers.push(
  http.head('/api/file-read', () =>
    new HttpResponse(null, { status: 404, headers: { 'X-Path-Kind': 'missing' } })),
)

// Vendor script paths that happy-dom eager-loads when buildSrcdoc /
// buildSketchSrcdoc append a <script src="..."> to a detached document.
// Explicit handlers (not just the catch-all) because:
//   1. They fire even if the catch-all's origin check has a stale TEST_ORIGIN.
//   2. They return valid JS (empty string, not 501) so happy-dom's script
//      loader doesn't throw a parse error that propagates as an unhandled
//      rejection in some shard configurations.
//   3. They are named — a grep for "vendor/tailwindcss" finds this immediately.
handlers.push(
  http.get('/vendor/tailwindcss-browser.js', () =>
    new HttpResponse('', { status: 200, headers: { 'Content-Type': 'application/javascript' } })),
  http.get('/vendor/mermaid.min.js', () =>
    new HttpResponse('', { status: 200, headers: { 'Content-Type': 'application/javascript' } })),
)

handlers.push(
  http.all('*', ({ request }) => {
    const scheme = request.url.slice(0, 5)
    if (scheme === 'blob:' || scheme === 'data:') {
      return new HttpResponse('', { status: 200 })
    }
    const url = new URL(request.url)
    const sameOrigin = url.origin === TEST_ORIGIN
    if (sameOrigin && DOM_DRIVEN_LOAD_RE.test(url.pathname)) {
      return new HttpResponse('', { status: 200 })
    }
    return new HttpResponse(
      `unmocked ${sameOrigin ? url.pathname : request.url} — add a handler in server.ts`,
      { status: 501 },
    )
  }),
)

export const server = setupServer(...handlers)
