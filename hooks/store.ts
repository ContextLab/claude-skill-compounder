// How the CLI's JSON is read. The mod never opens a lesson file or the event log: it asks
// `compound`, and these functions turn what it prints into values. Pure: text in, values
// out. Anything that is not the expected shape yields an empty answer or `undefined`, and
// the caller decides whether that is an error.

export type Kind = 'lesson' | 'skill' | 'script'

export type Item = {
  kind: Kind
  name: string
  level: string
  description: string
  path: string
  match: string[]
  // Set on a project-level lesson that belongs to a project other than the session's.
  project?: string
}

export type Hit = { name: string; level: string; path: string; text: string }
export type Earlier = { id: string; date: string; project: string; session: string; text: string; score: number }
export type Event = Record<string, unknown> & { type: string }

function parsed(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : typeof value === 'number' ? String(value) : ''
}

// The rows of a reply that is a list, or an object holding one list under any of `keys`.
function rows(value: unknown, keys: readonly string[]): Record<string, unknown>[] | undefined {
  let list: unknown = value
  const o = record(value)
  if (o !== undefined) {
    const key = keys.find(k => Array.isArray(o[k]))
    list = key === undefined ? undefined : o[key]
  }
  if (!Array.isArray(list)) return undefined
  return list.map(record).filter((r): r is Record<string, unknown> => r !== undefined)
}

function kindOf(value: unknown): Kind | undefined {
  return value === 'lesson' || value === 'skill' || value === 'script' ? value : undefined
}

function itemOf(r: Record<string, unknown>): Item | undefined {
  const kind = kindOf(r.kind)
  const name = str(r.name)
  if (kind === undefined || name === '') return undefined
  // The CLI lists every lesson and says which are in force. One whose platform or shell is
  // not this machine's (`applies: false`), or that the user switched off (`disabled: true`),
  // is neither offered for reuse nor recalled.
  if (r.applies === false || r.disabled === true) return undefined
  const match = Array.isArray(r.match) ? r.match.filter((m): m is string => typeof m === 'string') : []
  const project = str(r.project)
  return { kind, name, level: str(r.level), description: str(r.description), path: str(r.path), match, ...(project === '' ? {} : { project }) }
}

// `compound list --scripts --json`. undefined when the output is not the list it should be.
export function parseInventory(stdout: string): Item[] | undefined {
  const list = rows(parsed(stdout), ['items', 'inventory', 'lessons'])
  if (list === undefined) return undefined
  return list.map(itemOf).filter((i): i is Item => i !== undefined)
}

// `compound check`: the names under "timed_out", the lessons whose pattern the CLI gave up
// on. A list of names, or of rows that carry one.
export function parseTimedOut(stdout: string): string[] {
  const o = record(parsed(stdout))
  if (o === undefined || !Array.isArray(o.timed_out)) return []
  return o.timed_out.map(t => (typeof t === 'string' ? t : str(record(t)?.name))).filter(t => t !== '')
}

// `compound check --guards`: the number under "guards", how many lessons carry a pattern.
// undefined when the reply does not say.
export function parseGuards(stdout: string): number | undefined {
  const o = record(parsed(stdout))
  return o !== undefined && typeof o.guards === 'number' ? o.guards : undefined
}

// `compound check --guards`: the tool names under "tools", the tools some guard applies
// to. undefined when the reply does not say, and then every tool is asked about.
export function parseGuardTools(stdout: string): string[] | undefined {
  const o = record(parsed(stdout))
  if (o === undefined || !Array.isArray(o.tools) || !o.tools.every(t => typeof t === 'string')) return undefined
  return o.tools as string[]
}

// `compound check`: {"hits":[{name,level,path,text}]}.
export function parseHits(stdout: string): Hit[] | undefined {
  const o = record(parsed(stdout))
  if (o === undefined || !Array.isArray(o.hits)) return undefined
  return o.hits
    .map(record)
    .filter((r): r is Record<string, unknown> => r !== undefined && str(r.name) !== '')
    .map(r => ({ name: str(r.name), level: str(r.level), path: str(r.path), text: str(r.text) }))
}

// The prompt-log half of `compound find --json`: {"prompts":[{id, ts, project, prompt}]},
// best first as the CLI ranked them. The CLI's rows carry no session, so the current
// session's own prompts are recognised by their text (`mine`), compared the way the CLI
// stores a prompt: whitespace squeezed, the first 300 characters.
export function squeezed(text: string): string {
  return text.split(/\s+/).filter(w => w !== '').join(' ').slice(0, 300)
}

// `least` is how many of the searched words a prompt must share to be a candidate at all:
// a row the CLI scored below it is dropped, and a row with no score is kept.
export function parseEarlier(stdout: string, session: string, mine: readonly string[], most: number, least = 0): Earlier[] | undefined {
  const o = record(parsed(stdout))
  if (o === undefined) return undefined
  const list = rows(o, ['prompts'])
  if (list === undefined) return []
  const own = new Set(mine.map(squeezed))
  const out: Earlier[] = []
  for (const r of list) {
    const text = str(r.prompt) || str(r.text)
    const from = str(r.session) || str(r.session_id)
    if (text.trim() === '' || (session !== '' && from === session) || own.has(squeezed(text))) continue
    if (out.some(e => e.text === text)) continue
    const score = typeof r.score === 'number' ? r.score : -1
    if (score >= 0 && score < least) continue
    const project = str(r.project)
    out.push({ id: str(r.id), date: (str(r.ts) || str(r.date)).slice(0, 10), project: project.split('/').filter(p => p !== '').pop() ?? '', session: from, text, score: Math.max(0, score) })
    if (out.length >= most) break
  }
  return out
}

// A request the CLI holds a verdict for: what the judge answered the last time this text was
// asked in this project against this store.
export type Memo = { verdict: 'named' | 'nothing' | 'not-substantial'; items: string[]; earlier: Earlier[] }
// `compound find --request --json`: the words the prompt log was searched for, the
// candidates that reached the floor, the candidate earlier requests, the key the verdict is
// remembered under, and the verdict already remembered, if there is one.
export type Found = { words: string[]; items: Item[]; earlier: Earlier[]; key: string; memo: Memo | undefined }

export function parseFound(stdout: string, session: string, mine: readonly string[], most: number): Found | undefined {
  const o = record(parsed(stdout))
  if (o === undefined) return undefined
  const earlier = parseEarlier(stdout, session, mine, most)
  if (earlier === undefined) return undefined
  const words = Array.isArray(o.words) ? o.words.filter((w): w is string => typeof w === 'string') : []
  const items = (rows(o, ['items']) ?? []).map(itemOf).filter((i): i is Item => i !== undefined)
  const m = record(o.memo)
  const verdict = m?.verdict
  let memo: Memo | undefined
  if (m !== undefined && (verdict === 'named' || verdict === 'nothing' || verdict === 'not-substantial')) {
    const names = Array.isArray(m.items) ? m.items.filter((n): n is string => typeof n === 'string') : []
    // What was remembered is offered again as it was: nothing of it is this session's own prompt.
    memo = { verdict, items: names, earlier: parseEarlier(JSON.stringify({ prompts: m.prompts ?? [] }), '', [], most) ?? [] }
  }
  return { words, items, earlier, key: str(o.memo_key), memo }
}

// What `compound memo` reads on stdin: the verdict on a request, with the names and the
// earlier requests it named, as the CLI's own `find` rows.
export function memoOf(key: string, verdict: Memo['verdict'], items: readonly Item[], earlier: readonly Earlier[]): string {
  return JSON.stringify({
    key,
    verdict,
    items: items.map(i => i.name),
    prompts: earlier.map(e => ({ id: e.id, ts: e.date, project: e.project, session: e.session, prompt: e.text })),
  })
}

// `since` is how many recalls are later than the lesson's last rewrite, and `limit` how many
// make it ineffective; both are undefined when the CLI did not say. `guarded` is whether
// the lesson's guard refused a call in this session, which is the CLI's to say too: a
// recall after that is not counted against the lesson.
export type Shown = { text: string; path: string; level: string; recalls: number; ineffective: boolean | undefined; since: number | undefined; limit: number | undefined; guarded: boolean | undefined }

// A SKILL.md without its frontmatter: the lesson as it is read.
export function bodyOf(text: string): string {
  const m = /^---\n[\s\S]*?\n---\n?/.exec(text)
  return (m === null ? text : text.slice(m[0].length)).trim()
}

// `compound show <name> --json`: the lesson's text, how often it has been recalled, and
// whether the CLI now counts it ineffective. Output that is not JSON is taken as the text.
export function parseShow(stdout: string): Shown {
  const o = record(parsed(stdout))
  if (o === undefined) return { text: bodyOf(stdout), path: '', level: '', recalls: 0, ineffective: undefined, since: undefined, limit: undefined, guarded: undefined }
  const counts = record(o.counts)
  const recalls = counts !== undefined && typeof counts.recall === 'number' ? counts.recall : 0
  return {
    text: bodyOf(str(o.text) || str(o.body)),
    path: str(o.path),
    level: str(o.level),
    recalls,
    ineffective: typeof o.ineffective === 'boolean' ? o.ineffective : undefined,
    since: typeof o.recalls_since === 'number' ? o.recalls_since : undefined,
    limit: typeof o.recur_limit === 'number' ? o.recur_limit : undefined,
    guarded: typeof o.guarded_in_session === 'boolean' ? o.guarded_in_session : undefined,
  }
}

// Project-level lessons recorded in OTHER projects, from the log's `learn` events: the
// pool a second project's failure is matched against. A name the current inventory already
// holds is this project's, or has already moved up. Newest projects first, a few of them.
export function otherProjects(events: readonly Event[], have: ReadonlySet<string>, most: number): { project: string; names: string[] }[] {
  const byProject = new Map<string, Set<string>>()
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i]!
    const name = str(e.lesson)
    const project = str(e.project)
    if (e.type !== 'learn' || e.level !== 'project' || e.kind === 'skill' || name === '' || project === '' || have.has(name)) continue
    if (!byProject.has(project)) {
      if (byProject.size >= most) continue
      byProject.set(project, new Set())
    }
    byProject.get(project)!.add(name)
  }
  return [...byProject.entries()].map(([project, names]) => ({ project, names: [...names] }))
}

// `compound events --json`: a list, or one JSON object per line.
export function parseEvents(stdout: string): Event[] | undefined {
  const whole = rows(parsed(stdout), ['events'])
  const list = whole ?? stdout.split('\n').filter(l => l.trim() !== '').map(l => record(parsed(l)))
  if (list.some(r => r === undefined)) return undefined
  return (list as Record<string, unknown>[]).filter(r => typeof r.type === 'string') as Event[]
}

// An event's time in seconds, whether the log keeps a number or an ISO string. 0 when it has neither.
export function seconds(event: Event): number {
  const ts = event.ts
  if (typeof ts === 'number') return ts > 1e12 ? ts / 1000 : ts
  if (typeof ts === 'string') {
    if (/^[0-9]+(\.[0-9]+)?$/.test(ts)) return Number(ts)
    const at = Date.parse(ts)
    return Number.isNaN(at) ? 0 : at / 1000
  }
  return 0
}

// A lesson owed: `id` is the capture's, `key` is what its one refusal is claimed under.
export type Debt = { id: string; key: string; tool: string; failed: string; error: string; fixed: string }
export type Strengthening = { name: string; guard: boolean; call: string }
// What a session owes, as the CLI says: `since` is the time of the oldest of them, in seconds.
export type Owed = { debts: Debt[]; weak: Strengthening[]; since: number }

// `compound events --unsettled --session S --json`: what the session still owes. WHAT
// SETTLES A DEBT IS THE CLI'S TO SAY, and nothing here decides it: a `capture` row is a
// lesson owed, a `recall` row is a strengthening owed for its lesson, and a debt that was
// settled is simply not in the reply. undefined when the reply is not a list of events.
export function parseOwed(stdout: string): Owed | undefined {
  const events = parseEvents(stdout)
  if (events === undefined) return undefined
  const out: Owed = { debts: [], weak: [], since: 0 }
  for (const e of events) {
    const name = str(e.lesson)
    if (e.type === 'capture') {
      out.debts.push({ id: str(e.id), key: str(e.call) || str(e.ts), tool: str(e.tool), failed: str(e.failed), error: str(e.error), fixed: str(e.fixed) })
    } else if (e.type === 'recall' && name !== '') {
      out.weak = [...out.weak.filter(s => s.name !== name), { name, guard: e.guard === true, call: str(e.call) }]
    } else continue
    const at = seconds(e)
    if (at > 0 && (out.since === 0 || at < out.since)) out.since = at
  }
  return out
}

// The events to tell the person about once a debt is gone from the CLI's answer: what this
// session wrote, a `learn` or `skip` of any session that names a capture that is gone, and
// whatever happened to a lesson whose strengthening is gone. For the display only: the
// debt was already settled, by the CLI's account, before this is asked.
export function settlers(events: readonly Event[], session: string, goneIds: readonly string[], goneWeak: readonly string[]): Event[] {
  return events.filter(e => {
    if (e.type !== 'learn' && e.type !== 'skip' && e.type !== 'rm' && e.type !== 'skill' && e.type !== 'promote') return false
    if (session !== '' && str(e.session) === session) return true
    const settles = str(e.settles)
    if ((e.type === 'learn' || e.type === 'skip') && settles !== '' && goneIds.includes(settles)) return true
    return e.type !== 'skip' && (goneWeak.includes(str(e.lesson)) || goneWeak.includes(str(e.was)))
  })
}

// Whether `events` (this session's `learn` events since a failure was held) hold the
// first recording of the lesson `name`. Such a lesson is younger than the failure: it is
// that failure's own lesson, and meeting it at the fix is no recurrence.
export function learnedSince(events: readonly Event[], name: string): boolean {
  return name !== '' && events.some(e => e.type === 'learn' && e.update !== true && str(e.lesson) === name)
}

// Whether a big turn may be asked about lessons: nothing was recorded or owed in this
// session since the turn began, and the last nudge in ANY session (`nudges`, the log's
// `nudge` events) is at least `cooldown` seconds old.
export function mayNudge(events: readonly Event[], turnStart: number, now: number, cooldown: number, nudges: readonly Event[]): boolean {
  for (const e of events) {
    if ((e.type === 'learn' || e.type === 'skip' || e.type === 'capture') && seconds(e) >= turnStart) return false
  }
  for (const e of nudges) {
    if (e.type === 'nudge' && now - seconds(e) < cooldown) return false
  }
  return true
}

export type Unsettled = { id: string; age: string; failed: string; error: string; fixed: string }

function ageText(s: number): string {
  if (s < 0) return '0s'
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

// `compound events --unsettled --json`: the captures nothing has settled. This session's
// own are left out (the stop moment handles those), and so is a row with no id.
export function parseUnsettled(stdout: string, session: string, now: number): Unsettled[] | undefined {
  const events = parseEvents(stdout)
  if (events === undefined) return undefined
  const out: Unsettled[] = []
  for (const e of events) {
    const id = str(e.id)
    if (e.type !== 'capture' || id === '' || (session !== '' && str(e.session) === session)) continue
    out.push({ id, age: ageText(now - seconds(e)), failed: str(e.failed), error: str(e.error), fixed: str(e.fixed) })
  }
  return out
}

// `compound promote <name> --to user --auto --json` when it left the lesson where it is:
// the project root that holds it. undefined for a move, or for output that is not that.
export function parseLeft(stdout: string): string | undefined {
  const o = record(parsed(stdout))
  if (o === undefined || o.moved !== false) return undefined
  const from = str(o.from)
  return from === '' ? undefined : from
}

// `compound promote <name> --to user --auto --json`, whatever it did: the project root the
// lesson left or stays in, the projects that keep a committed copy of it (`also`), and the
// lessons of the same name and another text that stand in the way (`conflict`).
export function parseMoved(stdout: string): { from: string; also: string[]; conflict: string[] } | undefined {
  const o = record(parsed(stdout))
  if (o === undefined) return undefined
  const from = str(o.from)
  if (from === '') return undefined
  const list = (value: unknown) => (Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string' && v !== '') : [])
  return { from, also: list(o.also), conflict: list(o.conflict) }
}
