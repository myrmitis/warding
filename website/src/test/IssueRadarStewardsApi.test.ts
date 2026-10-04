import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// The STEWARDS half of the Issue Radar client, tested at the fetch boundary — the
// component tests mock `issueRadarApi`, so every translation below is invisible to
// them and silent when it breaks: a steward id that never reaches the query resolves
// to "no such steward", a DELETE that degrades to POST retires nothing, and a work
// write that drops `number` overwrites the wrong issue's record.
//
// The phase predicates are here for the same reason. They mirror frozensets in
// `steward_store.py`, and a drift between the two is invisible until a fleet quietly
// stops picking up work because a finished item is still charged to a slot.
import {
  issueRadarApi,
  STEWARD_PHASES,
  TERMINAL_PHASES,
  TTL_ACTIVE_PHASES,
  EDITING_PHASES,
  countsTowardOpen,
  type StewardPhase,
  type RepoRef,
} from '../apps/issue-radar/api'

const REF: RepoRef = { owner: 'o', repo: 'r' }
/** A self-managed GitLab ref: identity is owner/repo PLUS provider and host. */
const GL: RepoRef = { owner: 'group/sub', repo: 'svc', provider: 'gitlab', host: 'gl.corp' }

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

/** A failure whose body is NOT json — an html error page or an empty 502. */
function brokenBody(status: number): Response {
  return {
    ok: false,
    status,
    json: async () => {
      throw new Error('not json')
    },
  } as unknown as Response
}

let fetchMock: ReturnType<typeof vi.fn>

/** The url of the Nth fetch call. */
const calledUrl = (n = 0): string => String(fetchMock.mock.calls[n][0])
/** The RequestInit of the Nth fetch call. */
const calledInit = (n = 0): RequestInit => fetchMock.mock.calls[n][1] as RequestInit
/** The parsed json body of the Nth fetch call. */
const sentBody = (n = 0): Record<string, unknown> =>
  JSON.parse(String(calledInit(n).body)) as Record<string, unknown>

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('steward reads — url and query construction', () => {
  it('lists stewards under the app prefix with the repo identity', async () => {
    await issueRadarApi.stewards(REF)
    expect(calledUrl()).toBe('/api/apps/issue-radar/stewards?owner=o&repo=r')
  })

  it('carries provider and host for a self-managed instance', async () => {
    // `group/sub`+`svc` names a DIFFERENT project on gitlab.com than on gl.corp,
    // so a read that drops the host answers about the wrong repo.
    await issueRadarApi.stewards(GL)
    const url = calledUrl()
    expect(url).toContain('provider=gitlab')
    expect(url).toContain('host=gl.corp')
    expect(url).toContain('owner=group%2Fsub')
  })

  it('sends the steward id when reading one steward page', async () => {
    await issueRadarApi.steward(REF, 'c_beef')
    expect(calledUrl()).toBe('/api/apps/issue-radar/steward?owner=o&repo=r&id=c_beef')
  })

  it('reads name suggestions from the stewards collection', async () => {
    await issueRadarApi.suggestStewardNames(REF)
    expect(calledUrl()).toBe('/api/apps/issue-radar/stewards/names?owner=o&repo=r')
  })

  it('reads protocol settings from the repo-wide route', async () => {
    await issueRadarApi.getStewardSettings(REF)
    expect(calledUrl()).toBe('/api/apps/issue-radar/stewards/settings?owner=o&repo=r')
  })

  it('sends no method, body or write header on a read', async () => {
    // A GET carrying `Content-Type: application/json` is the shape a read
    // accidentally copied from a write; it is also how a read becomes a preflight.
    await issueRadarApi.stewards(REF)
    const init = calledInit()
    expect(init.method).toBeUndefined()
    expect(init.body).toBeUndefined()
    expect(init.headers).toBeUndefined()
  })
})

describe('steward writes — method, route and body', () => {
  it('creates a steward with POST on the collection, spec flattened onto the ref', async () => {
    await issueRadarApi.createSteward(REF, { name: 'Andromeda', max_open: 2, labels: ['bug'] })
    expect(calledUrl()).toBe('/api/apps/issue-radar/stewards')
    expect(calledInit().method).toBe('POST')
    expect(sentBody()).toEqual({
      owner: 'o', repo: 'r', name: 'Andromeda', max_open: 2, labels: ['bug'],
    })
  })

  it('updates a steward with PUT, patch flattened alongside the id', async () => {
    await issueRadarApi.updateSteward(REF, 'c_beef', { unattended: false, model: 'claude-opus-5' })
    expect(calledUrl()).toBe('/api/apps/issue-radar/steward')
    expect(calledInit().method).toBe('PUT')
    expect(sentBody()).toEqual({
      owner: 'o', repo: 'r', id: 'c_beef', unattended: false, model: 'claude-opus-5',
    })
  })

  it('sends an empty patch as a valid no-op write', async () => {
    // The store drops unknown keys and validates the known ones, so `{}` is
    // legal — it must not be turned into a body with a stray undefined.
    await issueRadarApi.updateSteward(REF, 'c_beef', {})
    expect(sentBody()).toEqual({ owner: 'o', repo: 'r', id: 'c_beef' })
  })

  it('retires a steward with DELETE and the id in the BODY', async () => {
    // Retire is DELETE-with-a-body by contract, not a query-param delete like
    // `disconnect`. A method that degrades to POST hits a different handler and
    // retires nothing while resolving as success.
    await issueRadarApi.retireSteward(REF, 'c_beef')
    expect(calledUrl()).toBe('/api/apps/issue-radar/steward')
    expect(calledInit().method).toBe('DELETE')
    expect(sentBody()).toEqual({ owner: 'o', repo: 'r', id: 'c_beef' })
  })

  it('records work with PUT, carrying steward id, issue number and the flat patch', async () => {
    await issueRadarApi.recordStewardWork(REF, 'c_beef', 2187, {
      phase: 'implementing',
      next: 'push the branch',
      pr_number: 42,
      tried_approach: 'patch the caller',
      tried_rejected_because: 'the caller is generated',
      event: 'opened a branch',
      event_kind: 'implement',
    })
    expect(calledUrl()).toBe('/api/apps/issue-radar/steward/work')
    expect(calledInit().method).toBe('PUT')
    expect(sentBody()).toEqual({
      owner: 'o', repo: 'r', steward_id: 'c_beef', number: 2187,
      phase: 'implementing', next: 'push the branch', pr_number: 42,
      tried_approach: 'patch the caller',
      tried_rejected_because: 'the caller is generated',
      event: 'opened a branch', event_kind: 'implement',
    })
  })

  it('keeps an explicit null in a work patch', async () => {
    // `pr_number: null` means "there is no PR any more" and must survive to the
    // wire; dropping it leaves a stale PR number attached to the item.
    await issueRadarApi.recordStewardWork(REF, 'c_beef', 7, { pr_number: null })
    expect(sentBody().pr_number).toBeNull()
  })

  it('pauses with a reason and resumes without one', async () => {
    await issueRadarApi.setStewardPaused(REF, 'c_beef', true, 'main is red')
    expect(calledUrl()).toBe('/api/apps/issue-radar/steward/pause')
    expect(calledInit().method).toBe('POST')
    expect(sentBody()).toEqual({
      owner: 'o', repo: 'r', id: 'c_beef', paused: true, reason: 'main is red',
    })

    fetchMock.mockClear()
    await issueRadarApi.setStewardPaused(REF, 'c_beef', false)
    expect(sentBody()).toEqual({
      owner: 'o', repo: 'r', id: 'c_beef', paused: false, reason: '',
    })
  })

  it('merges protocol settings with PUT on the repo-wide route', async () => {
    await issueRadarApi.putStewardSettings(REF, { claim_ttl_hours: 24 })
    expect(calledUrl()).toBe('/api/apps/issue-radar/stewards/settings')
    expect(calledInit().method).toBe('PUT')
    expect(sentBody()).toEqual({ owner: 'o', repo: 'r', settings: { claim_ttl_hours: 24 } })
  })

  it('declares a json content type on every write', async () => {
    const writes: Array<() => Promise<unknown>> = [
      () => issueRadarApi.createSteward(REF, { name: 'Leo' }),
      () => issueRadarApi.updateSteward(REF, 'c_1', { enabled: false }),
      () => issueRadarApi.retireSteward(REF, 'c_1'),
      () => issueRadarApi.recordStewardWork(REF, 'c_1', 1, { phase: 'claimed' }),
      () => issueRadarApi.setStewardPaused(REF, 'c_1', true),
      () => issueRadarApi.putStewardSettings(REF, { commit_trailer: 'Steward: {name}' }),
    ]
    for (const write of writes) {
      fetchMock.mockClear()
      await write()
      expect(calledInit().headers).toEqual({ 'Content-Type': 'application/json' })
    }
  })
})

describe('steward calls carry the session cookie', () => {
  it('sets same-origin credentials on every steward read and write', async () => {
    // The gateway authenticates by cookie. `credentials: 'omit'` (the default for
    // a cross-origin request) turns every one of these into a 401.
    const calls: Array<() => Promise<unknown>> = [
      () => issueRadarApi.stewards(REF),
      () => issueRadarApi.steward(REF, 'c_1'),
      () => issueRadarApi.suggestStewardNames(REF),
      () => issueRadarApi.getStewardSettings(REF),
      () => issueRadarApi.createSteward(REF, { name: 'Leo' }),
      () => issueRadarApi.updateSteward(REF, 'c_1', { enabled: false }),
      () => issueRadarApi.retireSteward(REF, 'c_1'),
      () => issueRadarApi.recordStewardWork(REF, 'c_1', 1, { phase: 'claimed' }),
      () => issueRadarApi.setStewardPaused(REF, 'c_1', true),
      () => issueRadarApi.putStewardSettings(REF, { claim_ttl_hours: 48 }),
    ]
    for (const call of calls) {
      fetchMock.mockClear()
      await call()
      expect(calledInit().credentials).toBe('same-origin')
    }
    expect(calls).toHaveLength(10)
  })
})

describe('steward calls surface the server error', () => {
  it('rejects with the server message on a non-OK response', async () => {
    fetchMock.mockResolvedValue(jsonResponse(409, {
      error: "steward name 'Leo' is already taken in this repo",
    }))
    await expect(issueRadarApi.createSteward(REF, { name: 'Leo' }))
      .rejects.toThrow("steward name 'Leo' is already taken in this repo")
  })

  it('rejects rather than resolving an empty record on a failed read', async () => {
    // Resolving `{}` here is the dangerous failure: the steward list renders as
    // "no stewards yet" and the user is invited to create duplicates.
    fetchMock.mockResolvedValue(jsonResponse(500, { error: 'boom' }))
    await expect(issueRadarApi.stewards(REF)).rejects.toThrow('boom')
  })

  it('falls back to the status code when the error body is not json', async () => {
    fetchMock.mockResolvedValue(brokenBody(502))
    await expect(issueRadarApi.steward(REF, 'c_1')).rejects.toThrow('HTTP 502')
  })

  it('rejects a failed work write instead of reporting recorded progress', async () => {
    fetchMock.mockResolvedValue(jsonResponse(409, {
      error: 'steward c_1 is already editing #7',
    }))
    await expect(issueRadarApi.recordStewardWork(REF, 'c_1', 9, { phase: 'implementing' }))
      .rejects.toThrow('already editing #7')
  })

  it('returns the parsed body on success', async () => {
    const body = { steward: { id: 'c_beef', name: 'Andromeda' } }
    fetchMock.mockResolvedValue(jsonResponse(200, body))
    await expect(issueRadarApi.updateSteward(REF, 'c_beef', { max_open: 1 })).resolves.toEqual(body)
  })
})

describe('phase classification mirrors steward_store.py', () => {
  it('classifies the terminal phases', async () => {
    expect([...TERMINAL_PHASES].sort()).toEqual(
      ['handed-back', 'preempted', 'resolved', 'skipped', 'yielded'],
    )
  })

  it('ages only pre-PR phases toward the claim ttl', async () => {
    // A parked PR is stronger evidence of a live claim than any heartbeat, so
    // those phases must NOT age toward the TTL.
    expect([...TTL_ACTIVE_PHASES].sort()).toEqual(['claimed', 'implementing', 'investigating'])
    expect(TTL_ACTIVE_PHASES.has('awaiting-ci')).toBe(false)
    expect(TTL_ACTIVE_PHASES.has('awaiting-merge')).toBe(false)
  })

  it('treats exactly the two uncommitted-worktree phases as editing', async () => {
    expect([...EDITING_PHASES].sort()).toEqual(['addressing-review', 'implementing'])
  })

  it('draws every classified phase from the phase list', async () => {
    const known = new Set<string>(STEWARD_PHASES)
    for (const set of [TERMINAL_PHASES, TTL_ACTIVE_PHASES, EDITING_PHASES]) {
      for (const phase of set) expect(known.has(phase)).toBe(true)
    }
    expect(STEWARD_PHASES).toHaveLength(13)
  })

  it('never marks a terminal phase as ttl-active or editing', async () => {
    for (const phase of TERMINAL_PHASES) {
      expect(TTL_ACTIVE_PHASES.has(phase)).toBe(false)
      expect(EDITING_PHASES.has(phase)).toBe(false)
    }
  })

  it('countsTowardOpen counts every unfinished phase', async () => {
    // No carve-out: a steward never parks a slot on a human. An issue whose next step
    // belongs to a person is labelled, recorded as a pass and released, so every
    // phase a steward still holds is charged to `max_open`.
    const counted = STEWARD_PHASES.filter((p) => !TERMINAL_PHASES.has(p))
    expect(counted).toEqual([
      'selected', 'claimed', 'investigating', 'implementing',
      'awaiting-ci', 'addressing-review', 'awaiting-merge', 'awaiting-reply',
    ])
    for (const phase of counted) expect(countsTowardOpen(phase)).toBe(true)
  })

  it('countsTowardOpen rejects every terminal phase', async () => {
    for (const phase of TERMINAL_PHASES) expect(countsTowardOpen(phase)).toBe(false)
  })

  it('classifies every phase in the list', async () => {
    // No phase may be unreachable by the predicate — a new phase added to the
    // union without a decision here would silently count toward a slot.
    for (const phase of STEWARD_PHASES as readonly StewardPhase[]) {
      expect(typeof countsTowardOpen(phase)).toBe('boolean')
    }
  })
})
