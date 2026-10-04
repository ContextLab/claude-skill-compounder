import type { EngineInterface, Register } from 'claude-code'
import { fixPrompt, parseFix, parseRecall, parseReuse, recallPrompt, reusePrompt } from './judge'
import { isOff, knobsFrom, type Knobs } from './knobs'
import {
  callText, captureContext, changesStore, cliCall, digest, EARLIER_MAX, errorReport, errorStatus, guarded, guardReason, inputOf, isCommand,
  judged, knownContext, promotedText, recallContext, reusable, reuseContext, reuseStatus, stopDebt, stopNudge, typedByUser, userOrigin,
  type Failure,
} from './render'
import { oneLine, redact } from './safe'
import {
  debts, mayNudge, otherProjects, parseEarlier, parseEvents, parseHits, parseInventory, parseShow, type Earlier, type Event, type Item,
} from './store'

// compound: before a substantial task it looks for existing work to reuse, and after a
// problem is solved it has the lesson written down. Five moments, each one a hook:
//
//   1 reuse    prompt.submit   a typed, substantial prompt gets the existing work that covers it
//   2 guard    tool.call       a call matching a lesson's `match` is refused once per session
//   3 recall   tool.call       a failed call gets the recorded lesson that describes it
//   4 capture  tool.call       a success after a held failure makes the session owe a lesson
//   5 stop     classic.Stop    an owed lesson refuses the stop once; a long turn is asked once
//
// A plugin gets ONE unmatched tool.call hook, so moments 2, 3 and 4 share it.
//
// THE MOD NEVER READS OR WRITES A LESSON FILE OR THE EVENT LOG. Every store operation is
// one `$.process.run` of bin/compound, and ./store reads what it prints. Every firing
// writes an event that way and sets the status entry. Every failure of the mod itself is
// caught, logged as an `error`, and told to Claude at the next typed prompt.
// COMPOUND_OFF=1 switches all of it off.
//
// Everything that touches `$` is in this file: the engine follows `$` into a function
// declared here and never across an import. The pure halves are ./judge (the three
// questions), ./render (the messages), ./store (the CLI's JSON), ./knobs and ./safe.

// How many successes after one failure are put to the judge before the failure is dropped.
const FIX_ATTEMPTS = 2
const LOGGED_CALL = 4000
const LOGGED_ERROR = 2000
const CLI_TIMEOUT_MS = 15000
const SETTINGS_TTL_MS = 30000
const INVENTORY_TTL_MS = 60000
// How many other projects' lessons are looked at when a call fails.
const OTHER_PROJECTS = 6

type Ran = { code: number; stdout: string; stderr: string }
type Reply = { text: string | undefined; ms: number; reason: string }
type Held = { call: string; error: string; left: number }
type Turn = { calls: number; start: number }

// Module variables are per process and survive /clear, so everything that belongs to a
// session is keyed on the session id (and, for a held failure, on the agent loop too).
const held = new Map<string, Held>()
const turns = new Map<string, Turn>()
const commands = new Set<string>()
const failures = new Map<string, Failure[]>()
let ownCli: string | undefined
let settings: { at: number; off: boolean; knobs: Knobs } | undefined
let listed: { at: number; root: string; items: Item[] } | undefined
let elsewhere: { at: number; root: string; items: Item[] } | undefined

function nowS(): number {
  return Math.floor(Date.now() / 1000)
}

function said(err: unknown): string {
  return err instanceof Error ? `${err.name}: ${err.message}` : String(err)
}

// ---- the CLI, the model, the environment ----------------------------------------------

// The CLI this mod calls and names in every message: the one shipped beside it, else
// COMPOUND_BIN, else whatever `compound` is on PATH.
async function cliPath($: EngineInterface): Promise<string> {
  if (ownCli !== undefined) return ownCli
  const own = `${$.plugin.root}/bin/compound`
  if (await $.fs.exists(own)) {
    ownCli = own
    return own
  }
  return (await $.env.get('COMPOUND_BIN')) || 'compound'
}

// Where CLI calls run: the repository's root, or where the session started. Never the
// shell's current directory, which moves with every `cd`.
async function projectRoot($: EngineInterface): Promise<string> {
  const repo = await $.session.repo()
  return repo?.root ?? (await $.session.root())
}

async function readSettings($: EngineInterface): Promise<{ off: boolean; knobs: Knobs }> {
  if (settings !== undefined && Date.now() - settings.at < SETTINGS_TTL_MS) return settings
  // `$.env.get` takes a literal name, so each is written out.
  const isSwitchedOff = isOff(await $.env.get('COMPOUND_OFF'))
  const read = knobsFrom({
    promptMinChars: await $.env.get('COMPOUND_PROMPT_MIN_CHARS'),
    turnMinCalls: await $.env.get('COMPOUND_TURN_MIN_CALLS'),
    nudgeCooldown: await $.env.get('COMPOUND_NUDGE_COOLDOWN'),
    recurLimit: await $.env.get('COMPOUND_RECUR_LIMIT'),
    model: await $.env.get('COMPOUND_MODEL'),
    judgeTimeout: await $.env.get('COMPOUND_JUDGE_TIMEOUT'),
  })
  settings = { at: Date.now(), off: isSwitchedOff, knobs: read }
  return settings
}

async function off($: EngineInterface): Promise<boolean> {
  return (await readSettings($)).off
}

async function knobs($: EngineInterface): Promise<Knobs> {
  return (await readSettings($)).knobs
}

// One CLI call, with the session stamped on it and the three store locations passed
// through when they are set. `project` runs it as another project. Never rejects: a child
// that could not start or ran out of time is exit code -1 with the reason as its stderr.
async function spawn($: EngineInterface, args: readonly string[], stdin?: string, project?: string): Promise<Ran> {
  try {
    const env: Record<string, string> = { CLAUDE_CODE_SESSION_ID: await $.session.id() }
    const home = await $.env.get('COMPOUND_HOME')
    if (home) env.COMPOUND_HOME = home
    const claudeDir = await $.env.get('COMPOUND_CLAUDE_DIR')
    if (claudeDir) env.COMPOUND_CLAUDE_DIR = claudeDir
    const pinned = project ?? (await $.env.get('COMPOUND_PROJECT'))
    if (pinned) env.COMPOUND_PROJECT = pinned
    const done = await $.process.run([await cliPath($), ...args], {
      cwd: await projectRoot($),
      env,
      timeoutMs: CLI_TIMEOUT_MS,
      ...(stdin === undefined ? {} : { stdin }),
    })
    return { code: done.exitCode, stdout: done.stdout, stderr: done.stderr }
  } catch (err) {
    return { code: -1, stdout: '', stderr: said(err) }
  }
}

// A failure of the mod itself: kept for this session, shown in the status entry, and
// written to the event log as an `error`. When the CLI is what failed to log it, memory is
// the only record, and the next typed prompt still reports it.
async function fail($: EngineInterface, where: string, err: unknown): Promise<void> {
  const message = oneLine(said(err), 500)
  let sid = 'unknown'
  try {
    sid = await $.session.id()
  } catch {
    // The session id is only the key the failure is kept under.
  }
  const kept = failures.get(sid) ?? []
  kept.push({ where, message })
  failures.set(sid, kept)
  try {
    $.ui.status(errorStatus(kept.length))
  } catch {
    // A surface that cannot show a status entry does not make the failure worse.
  }
  const logged = await spawn($, ['log'], JSON.stringify({ type: 'error', where, message }))
  if (logged.code !== 0) kept.push({ where: 'cli.log', message: oneLine(`exit ${logged.code}: ${logged.stderr}`, 300) })
}

// A failure with no `$` call at all, for a `.catch` handler's one-second grace.
function failQuietly(where: string, message: string): void {
  const kept = failures.get('unknown') ?? []
  kept.push({ where, message: oneLine(message, 500) })
  failures.set('unknown', kept)
}

function hasFailures(sid: string): boolean {
  return (failures.get(sid)?.length ?? 0) + (failures.get('unknown')?.length ?? 0) > 0
}

// What has failed in this session and was not yet told to Claude; taking it empties it.
function takeFailures(sid: string): Failure[] {
  const out = [...(failures.get(sid) ?? []), ...(failures.get('unknown') ?? [])]
  failures.delete(sid)
  failures.delete('unknown')
  return out
}

// A CLI call whose exit code must be one of `ok`. Anything else is logged as an error and
// answered `undefined`, so a caller reads "the CLI could not say" and adds nothing.
async function cli($: EngineInterface, args: readonly string[], stdin?: string, ok: readonly number[] = [0], project?: string): Promise<Ran | undefined> {
  const ran = await spawn($, args, stdin, project)
  if (ok.includes(ran.code)) return ran
  await fail($, `cli.${args[0] ?? ''}`, `exit ${ran.code}: ${ran.stderr.trim() || ran.stdout.trim() || '(no output)'}`)
  return undefined
}

// Appends one event. The CLI fills in `ts`, `session` and `project`.
async function log($: EngineInterface, event: Record<string, unknown>): Promise<void> {
  const ran = await spawn($, ['log'], JSON.stringify(event))
  if (ran.code !== 0) await fail($, 'cli.log', `exit ${ran.code}: ${ran.stderr.trim() || '(no output)'}`)
}

async function events($: EngineInterface, args: readonly string[]): Promise<Event[] | undefined> {
  const ran = await cli($, ['events', '--json', ...args])
  if (ran === undefined) return undefined
  const rows = parseEvents(ran.stdout)
  if (rows === undefined) await fail($, 'events.parse', `compound events --json printed something unreadable: ${ran.stdout.slice(0, 200)}`)
  return rows
}

// Every lesson and skill at all three levels and the project's scripts, as the CLI lists
// them. Cached for a minute: the pre-call guard asks on every tool call.
async function inventory($: EngineInterface): Promise<Item[] | undefined> {
  const root = await projectRoot($)
  if (listed !== undefined && listed.root === root && Date.now() - listed.at < INVENTORY_TTL_MS) return listed.items
  const ran = await cli($, ['list', '--scripts', '--json'])
  if (ran === undefined) return undefined
  const items = parseInventory(ran.stdout)
  if (items === undefined) {
    await fail($, 'inventory.parse', `compound list --json printed something that is not a list: ${ran.stdout.slice(0, 200)}`)
    return undefined
  }
  listed = { at: Date.now(), root, items }
  return items
}

// Project-level lessons recorded in other projects, found through the log's `learn` events
// and listed by the CLI run as each of those projects. Only a failed call asks for these.
async function lessonsElsewhere($: EngineInterface, have: readonly Item[]): Promise<Item[]> {
  const root = await projectRoot($)
  if (elsewhere !== undefined && elsewhere.root === root && Date.now() - elsewhere.at < INVENTORY_TTL_MS) return elsewhere.items
  const learned = await events($, ['--type', 'learn'])
  const out: Item[] = []
  for (const other of otherProjects(learned ?? [], new Set(have.map(i => i.name)), OTHER_PROJECTS)) {
    // Exit 2 is a project that is gone or unreadable now: its lessons are simply not offered.
    const ran = await spawn($, ['list', '--level', 'project', '--json'], undefined, other.project)
    if (ran.code !== 0) continue
    for (const item of parseInventory(ran.stdout) ?? []) {
      if (item.kind === 'lesson' && other.names.includes(item.name) && !out.some(o => o.name === item.name)) {
        out.push({ ...item, project: other.project })
      }
    }
  }
  elsewhere = { at: Date.now(), root, items: out }
  return out
}

function forgetInventory(): void {
  listed = undefined
  elsewhere = undefined
}

// One question to the judge model, bounded by COMPOUND_JUDGE_TIMEOUT. Never rejects.
async function ask($: EngineInterface, prompt: string, k: Knobs): Promise<Reply> {
  const began = Date.now()
  try {
    const r = await $.model.complete({ model: k.model, prompt, timeoutMs: k.judgeTimeoutMs, maxTokens: 400 })
    if (r.isAnswered) return { text: r.text, ms: Date.now() - began, reason: '' }
    return { text: undefined, ms: Date.now() - began, reason: r.reason === 'aborted' ? `no answer within ${k.judgeTimeoutMs / 1000} s` : r.reason }
  } catch (err) {
    return { text: undefined, ms: Date.now() - began, reason: said(err) }
  }
}

// ONE INSTANCE ACTS, ONCE. The package can be loaded twice in one session (a checkout
// named by --plugin-dir and the installed copy named by CLAUDE_CODE_PLUGIN_DIRS), and then
// every hook runs in two environments that share no variables. `mkdir` without -p is
// atomic, so whichever instance creates <tmp>/compound-claims/<session>/<key> first owns
// that event. The same directory is what makes "once per session" survive a module reload.
// It lives under the system's temporary directory, which the system clears; it is not part
// of the store. When the directory cannot be made at all the caller proceeds: a check that
// runs twice is better than one that never runs.
async function claim($: EngineInterface, sid: string, key: string): Promise<boolean> {
  const safe = (t: string) => t.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 96) || '_'
  const tmp = ((await $.env.get('TMPDIR')) || '/tmp').replace(/\/+$/, '')
  const dir = `${tmp}/compound-claims/${safe(sid)}`
  try {
    const ran = await $.process.run(['sh', '-c', 'mkdir -p "$1" || exit 3; mkdir "$1/$2" 2>/dev/null', 'sh', dir, safe(key)], { timeoutMs: 10000 })
    if (ran.exitCode === 3) await fail($, 'claim', `cannot create ${dir}: ${ran.stderr.trim()}`)
    return ran.exitCode === 0 || ran.exitCode === 3
  } catch (err) {
    await fail($, 'claim', err)
    return true
  }
}

async function registerCommand($: EngineInterface): Promise<void> {
  const sid = await $.session.id()
  if (commands.has(sid)) return
  commands.add(sid)
  await $.command.register({ name: 'compound', description: 'What compound has stored, reused, guarded and recalled, and whether it is healthy.' })
}

// ---- moment 1: reuse ------------------------------------------------------------------

async function earlierRequests($: EngineInterface, sid: string, text: string, keywords: readonly string[]): Promise<Earlier[]> {
  if (keywords.length === 0) return []
  const found = await cli($, ['find', '--json', ...keywords])
  if (found === undefined) return []
  // The CLI's prompt rows carry no session, so this session's own prompts are recognised by text.
  const mine = [text, ...(await $.session.messages()).filter(m => m.role === 'user').map(m => m.text)]
  const earlier = parseEarlier(found.stdout, sid, mine, EARLIER_MAX)
  if (earlier === undefined) {
    await fail($, 'reuse.find', `compound find --json printed something unreadable: ${found.stdout.slice(0, 200)}`)
    return []
  }
  return earlier
}

async function reuseCheck($: EngineInterface, sid: string, text: string, k: Knobs): Promise<string> {
  const began = Date.now()
  const items = reusable((await inventory($)) ?? [])
  // Nothing recorded yet: there is nothing to reuse, and no model call is made.
  if (items.length === 0) return ''
  if (!(await claim($, sid, `reuse-${digest(text)}-${Math.floor(nowS() / 20)}`))) return ''
  const reply = await ask($, reusePrompt(redact(text), items), k)
  if (reply.text === undefined) {
    await fail($, 'reuse.judge', `${k.model} gave no answer: ${reply.reason}`)
    return ''
  }
  const answer = parseReuse(reply.text, items)
  if (answer === undefined) {
    await fail($, 'reuse.parse', `${k.model} answered something unreadable: ${reply.text.slice(0, 200)}`)
    return ''
  }
  if (!answer.substantial) return ''
  const earlier = await earlierRequests($, sid, text, answer.keywords)
  const context = reuseContext(answer.items, earlier, await cliPath($))
  if (context === '') return ''
  await log($, {
    type: 'reuse',
    lessons: answer.items.map(i => i.name),
    prompts: earlier.map(e => e.id),
    keywords: answer.keywords,
    prompt_id: digest(text),
    // What the check added to the prompt, in milliseconds, and the judge's share of it.
    ms: Date.now() - began,
    judge_ms: reply.ms,
  })
  $.ui.status(reuseStatus(answer.items.length, earlier.length))
  return context
}

async function onPrompt($: EngineInterface, raw: string, kind: string | undefined): Promise<string[]> {
  if (await off($)) return []
  const text = raw.trim()
  if (text === '' || !userOrigin(kind) || !typedByUser(text) || isCommand(text)) return []
  const sid = await $.session.id()
  // The user typed: what the stop moment counts starts over here.
  turns.set(sid, { calls: 0, start: nowS() })
  await registerCommand($)
  const out: string[] = []
  // The mod's own failures so far, once per session.
  if (hasFailures(sid) && (await claim($, sid, 'errors-reported'))) {
    out.push(errorReport(takeFailures(sid), await cliPath($)))
  }
  const k = await knobs($)
  if (text.length < k.promptMinChars) return out
  try {
    const reuse = await reuseCheck($, sid, text, k)
    if (reuse !== '') out.push(reuse)
  } catch (err) {
    await fail($, 'reuse', err)
  }
  return out
}

// ---- moment 2: guard ------------------------------------------------------------------

async function guard($: EngineInterface, sid: string, tool: string, input: Record<string, unknown>): Promise<string | undefined> {
  const began = Date.now()
  const items = await inventory($)
  // No lesson has a `match`: nothing can hit, and the call is not held for a process start.
  if (items === undefined || !items.some(i => i.match.length > 0)) return undefined
  const ran = await cli($, ['check'], JSON.stringify({ tool, input }))
  if (ran === undefined) return undefined
  const hits = parseHits(ran.stdout)
  if (hits === undefined) {
    await fail($, 'guard.parse', `compound check printed something unreadable: ${ran.stdout.slice(0, 200)}`)
    return undefined
  }
  // Once per session per lesson: the claim is the record, so the same call sent again runs.
  const fresh = []
  for (const h of hits) {
    if (await claim($, sid, `guard-${h.name}`)) fresh.push(h)
  }
  const first = fresh[0]
  if (first === undefined) return undefined
  const text = callText(tool, input).slice(0, LOGGED_CALL)
  const ms = Date.now() - began
  for (const h of fresh) await log($, { type: 'guard', lesson: h.name, tool, text, ms })
  $.ui.status(`compound: guard ${first.name}`)
  return guardReason(fresh, await cliPath($))
}

// ---- moments 3 and 4: recall and capture ----------------------------------------------

// A lesson met again. It is logged as a recurrence, moved to the user level when it was
// another project's, and reported ineffective when the CLI now counts it so. Answers the
// text Claude reads beside the call's result.
async function recurred($: EngineInterface, found: Item, tool: string, error: string, k: Knobs, known: boolean): Promise<string[]> {
  const cliAt = await cliPath($)
  const out: string[] = []
  let lesson = found
  let asProject = lesson.project
  await log($, { type: 'recall', lesson: lesson.name, tool, error: error.slice(-LOGGED_ERROR), at: known ? 'fix' : 'failure' })
  if (asProject !== undefined) {
    // Recorded in one project and now met in a second: it moves up. Moved, never copied.
    const moved = await cli($, ['promote', lesson.name, '--to', 'user'], undefined, [0], asProject)
    if (moved !== undefined) {
      forgetInventory()
      out.push(promotedText(lesson.name, asProject))
      $.ui.toast(`compound: lesson ${lesson.name} moved to the user level`)
      lesson = { ...lesson, level: 'user', path: '' }
      asProject = undefined
    }
  }
  const shown = await cli($, ['show', lesson.name, '--json'], undefined, [0], asProject)
  const read = shown === undefined ? undefined : parseShow(shown.stdout)
  const text = read === undefined || read.text === '' ? lesson.description : read.text
  if (read !== undefined && read.path !== '') lesson = { ...lesson, path: read.path }
  const count = Math.max(1, read?.recalls ?? 1)
  const ineffective = read?.ineffective ?? count >= k.recurLimit
  if (ineffective) $.ui.toast(`compound: lesson ${lesson.name} is ineffective (recalled ${count} times)`)
  $.ui.status(ineffective ? `compound: ${lesson.name} ineffective` : `compound: recalled ${lesson.name}`)
  out.push(known ? knownContext(lesson, text, count, ineffective, cliAt) : recallContext(lesson, text, count, ineffective, cliAt))
  return out
}

async function lessons($: EngineInterface): Promise<Item[]> {
  const here = ((await inventory($)) ?? []).filter(i => i.kind === 'lesson')
  return [...here, ...(await lessonsElsewhere($, here))]
}

async function onFailure($: EngineInterface, sid: string, key: string, tool: string, callId: string, call: string, errorText: string): Promise<string[]> {
  // The instance that claims the failure holds it, and so is the only one that judges the fix.
  if (!(await claim($, sid, `fail-${callId}`))) return []
  const error = redact(errorText)
  const known = await lessons($)
  const k = await knobs($)
  let hit: Item | undefined
  if (known.length > 0) {
    const reply = await ask($, recallPrompt(call, error, known), k)
    if (reply.text === undefined) {
      await fail($, 'recall.judge', `${k.model} gave no answer: ${reply.reason}`)
    } else {
      const answer = parseRecall(reply.text, known)
      if (answer === undefined) await fail($, 'recall.parse', `${k.model} answered something unreadable: ${reply.text.slice(0, 200)}`)
      else hit = answer.lesson
    }
  }
  if (hit === undefined) {
    held.set(key, { call, error, left: FIX_ATTEMPTS })
    return []
  }
  // A failure answered with a recorded lesson is not held: the fix teaches nothing new.
  held.delete(key)
  return recurred($, hit, tool, error, k, false)
}

async function onSuccess($: EngineInterface, key: string, tool: string, callId: string, agent: string | undefined, call: string): Promise<string[]> {
  const was = held.get(key)
  if (was === undefined) return []
  was.left -= 1
  if (was.left <= 0) held.delete(key)
  const known = await lessons($)
  const k = await knobs($)
  const reply = await ask($, fixPrompt({ failed: was.call, error: was.error, worked: call }, known), k)
  if (reply.text === undefined) {
    await fail($, 'capture.judge', `${k.model} gave no answer: ${reply.reason}`)
    return []
  }
  const answer = parseFix(reply.text, known, was.error)
  if (answer === undefined) {
    await fail($, 'capture.parse', `${k.model} answered something unreadable: ${reply.text.slice(0, 200)}`)
    return []
  }
  if (answer.verdict === 'NONE') return []
  held.delete(key)
  if (answer.verdict === 'KNOWN') return recurred($, answer.lesson, tool, was.error, k, true)
  await log($, {
    type: 'capture',
    tool,
    failed: was.call.slice(0, LOGGED_CALL),
    error: was.error.slice(-LOGGED_ERROR),
    fixed: call.slice(0, LOGGED_CALL),
    evidence: answer.evidence,
    call: callId,
    agent: agent ?? null,
    ms: reply.ms,
  })
  $.ui.status('compound: lesson owed')
  return [captureContext({ failed: was.call, error: was.error, fixed: call }, await cliPath($))]
}

// The session ran the CLI itself: the store may have changed, and a lesson may now exist.
async function onCliCall($: EngineInterface, verb: string, failed: boolean): Promise<void> {
  if (!changesStore(verb)) return
  forgetInventory()
  if (failed) return
  if (verb === 'add') {
    const learned = await events($, ['--session', await $.session.id(), '--type', 'learn'])
    const last = learned?.[learned.length - 1]
    const name = last === undefined || typeof last.lesson !== 'string' ? '' : last.lesson
    $.ui.toast(name === '' ? 'compound: lesson recorded' : `compound: lesson recorded: ${name}`)
    $.ui.status(name === '' ? 'compound: lesson recorded' : `compound: learned ${name}`)
  } else if (verb === 'promote') {
    $.ui.toast('compound: lesson moved')
  }
}

// ---- moment 5: stop -------------------------------------------------------------------

async function onStop($: EngineInterface, followsBlock: boolean): Promise<string | undefined> {
  if (await off($)) return undefined
  const sid = await $.session.id()
  const rows = await events($, ['--session', sid])
  if (rows === undefined) return undefined
  const cliAt = await cliPath($)
  // A debt is refused once: the claim is the record, so a stop that follows a refusal for
  // one debt can still be refused for a newer one, and never twice for the same.
  const owed = debts(rows)
  let fresh = 0
  for (const d of owed) {
    if (await claim($, sid, `stop-${d.key}`)) fresh += 1
  }
  if (fresh > 0) {
    $.ui.status('compound: lesson owed')
    return stopDebt(owed, cliAt)
  }
  const turn = turns.get(sid)
  const k = await knobs($)
  if (followsBlock || owed.length > 0 || turn === undefined || turn.calls < k.turnMinCalls) return undefined
  if (!mayNudge(rows, turn.start, nowS(), k.nudgeCooldown)) return undefined
  if (!(await claim($, sid, `nudge-${Math.floor(turn.start / 20)}`))) return undefined
  const calls = turn.calls
  turn.calls = 0
  await log($, { type: 'nudge', calls })
  $.ui.status('compound: asked about lessons')
  return stopNudge(calls, cliAt)
}

// ---- registration ---------------------------------------------------------------------

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    try {
      if (!(await off($))) await registerCommand($)
    } catch (err) {
      await fail($, 'session.start', err)
    }
    return next(e)
  }).catch(($, e, next) => {
    failQuietly('session.start', `${next.error.kind}: ${next.error.message ?? ""}`)
    return next(e)
  })

  on('command.run', { command: 'compound' }, async $ => {
    // Exit 1 is a health check that failed: the report is still the answer.
    const ran = await cli($, ['status'], undefined, [0, 1])
    if (ran === undefined) return { text: `compound status could not run. CLI: ${await cliPath($)}` }
    return { text: [ran.stdout.trimEnd(), ran.stderr.trimEnd()].filter(t => t !== '').join('\n') || '(compound status printed nothing)' }
  })

  on('prompt.submit', async ($, e, next) => {
    let extra: string[] = []
    try {
      extra = await onPrompt($, e.text, e.origin?.kind)
    } catch (err) {
      await fail($, 'prompt.submit', err)
    }
    return next(extra.length === 0 ? e : { ...e, context: [...(e.context ?? []), ...extra] })
  }).catch(($, e, next) => {
    failQuietly('prompt.submit', `${next.error.kind}: ${next.error.message ?? ""}`)
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const tool = String(e.tool)
    const input = inputOf(e as unknown as Record<string, unknown>)
    const verb = tool === 'Bash' && typeof input.command === 'string' ? cliCall(input.command) : undefined
    let sid = ''
    try {
      if (await off($)) return next(e)
      sid = await $.session.id()
      let turn = turns.get(sid)
      if (turn === undefined) {
        turn = { calls: 0, start: nowS() }
        turns.set(sid, turn)
      }
      turn.calls += 1
      // The CLI's own calls are not guarded: a lesson's text quotes the mistake it is about.
      if (guarded(tool) && verb === undefined) {
        const deny = await guard($, sid, tool, input)
        if (deny !== undefined) return { deny }
      }
    } catch (err) {
      await fail($, 'guard', err)
    }

    const ran = await next(e)
    if (sid === '' || ran.deny !== undefined) return ran
    try {
      if (verb !== undefined) {
        await onCliCall($, verb, ran.isError === true)
        return ran
      }
      if (!judged(tool)) return ran
      const key = `${sid}:${e.agentId ?? 'main'}`
      const call = callText(tool, input)
      const extra =
        ran.isError === true
          ? await onFailure($, sid, key, tool, e.tool_use_id, call, String(ran.text ?? ''))
          : await onSuccess($, key, tool, e.tool_use_id, e.agentId, call)
      return extra.length === 0 ? ran : { ...ran, context: [...(ran.context ?? []), ...extra] }
    } catch (err) {
      await fail($, ran.isError === true ? 'recall' : 'capture', err)
      return ran
    }
  }).catch(($, e, next) => {
    failQuietly('tool.call', `${next.error.kind}: ${next.error.message ?? ""}`)
    return next(e)
  })

  on('classic.Stop', async ($, e, next) => {
    const result = await next(e)
    try {
      const block = await onStop($, e.stop_hook_active === true)
      if (block === undefined) return result
      return { ...result, block: result.block === undefined ? block : `${result.block}\n\n${block}` }
    } catch (err) {
      await fail($, 'stop', err)
      return result
    }
  }).catch(($, e, next) => {
    failQuietly('classic.Stop', `${next.error.kind}: ${next.error.message ?? ""}`)
    return next(e)
  })
}
