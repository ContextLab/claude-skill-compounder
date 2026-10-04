import type { EngineInterface, Register } from 'claude-code'
import { isOff, knobsFrom, type Knobs } from './knobs'
import { candidateFloor, fixPrompt, parseFix, parseRecall, parseReuse, recallPrompt, reusePrompt, significantWords } from './judge'
import {
  callText, candidateText, captureContext, changesStore, cliCall, digest, errorReport, errorStatus, FIX_ATTEMPTS, guarded, guardReason, heldStep,
  inputOf, isCommand, judged, knownContext, promotedText, recallContext, reusable, reuseContext, reuseStatus, stopDebt, stopNudge,
  stopStrengthen, turnAfterCall, turnAfterPrompt, turnAfterStop, typedByUser, unsettledContext, userOrigin,
  type Failure, type Held, type Turn,
} from './render'
import { oneLine, redact } from './safe'
import {
  debts, mayNudge, otherProjects, parseEarlier, parseEvents, parseHits, parseInventory, parseLeft, parseShow, parseTimedOut, parseUnsettled,
  strengthenings,
  type Earlier, type Event, type Item,
} from './store'

// compound: before a substantial task it looks for existing work to reuse, and after a
// problem is solved it has the lesson written down. Five moments, each one a hook:
//
//   1 reuse    prompt.submit   a typed, substantial prompt gets the existing work that covers it
//   2 guard    tool.call       a call matching a lesson's `match` is refused once per session
//   3 recall   tool.call       a failed call gets the recorded lesson that describes it
//   4 capture  tool.call       a success after a held failure makes the session owe a lesson
//   5 stop     classic.Stop    an owed lesson, or an owed strengthening of one, refuses the stop
//                              once; a long turn is asked once
//
// And once per session, at its first typed prompt, it tells the session what earlier
// sessions in this project left unsettled.
//
// A REFUSAL HAPPENS AT MOST ONCE. A guard's deny and a stop's refusal each need a claim
// (see `claim`), and a claim that cannot be made means the mod does not refuse.
//
// A plugin gets ONE unmatched tool.call hook, so moments 2, 3 and 4 share it.
//
// THE MOD NEVER READS OR WRITES A LESSON FILE OR THE EVENT LOG. Every store operation is
// one `$.process.run` of bin/compound, and ./store reads what it prints. Every firing
// writes an event that way and sets the status entry. Every failure of the mod itself is
// caught, logged as an `error`, and told to Claude at the next typed prompt. Lesson text is
// only ever shown to Claude as a quotation (./render), never as the mod's own instruction.
// COMPOUND_OFF=1 switches all of it off.
//
// Everything that touches `$` is in this file: the engine follows `$` into a function
// declared here and never across an import. The pure halves are ./judge (the three
// questions), ./render (the messages), ./store (the CLI's JSON), ./knobs and ./safe.

const LOGGED_CALL = 4000
const LOGGED_ERROR = 2000
const CLI_TIMEOUT_MS = 15000
// The guard holds a tool call while `compound check` runs. Past this the child is killed
// and the call runs unguarded.
const GUARD_TIMEOUT_MS = 1500
const CLAIM_TIMEOUT_MS = 5000
// How many prompt-log candidates the judge is shown.
const CANDIDATES_MAX = 5
const CLAIMS_KEPT_DAYS = 14
const SETTINGS_TTL_MS = 30000
const INVENTORY_TTL_MS = 60000
// How many other projects' lessons are looked at when a call fails.
const OTHER_PROJECTS = 6
// How many unsettled captures a session's first prompt is told about.
const UNSETTLED_SHOWN = 5

type Ran = { code: number; stdout: string; stderr: string }
type Reply = { text: string | undefined; ms: number; reason: string }
// What a claim answers. `mine`: this instance acts. `taken`: it was already done in this
// session. `unusable`: the record on disk cannot be made, so nothing is known across copies.
type Claim = 'mine' | 'taken' | 'unusable'

// Module variables are per process and survive /clear, so everything that belongs to a
// session is keyed on the session id (and, for a held failure, on the agent loop too).
const held = new Map<string, Held>()
const turns = new Map<string, Turn>()
const commands = new Set<string>()
const failures = new Map<string, Failure[]>()
// What this process has already done once, as `<session>\0<key>`: the first check of every claim.
const claimed = new Set<string>()
// Failures that are logged once per session however often they repeat, as `<session>\0<where>`.
const failedOnce = new Set<string>()
// How many failure reports each session has been given.
const reports = new Map<string, number>()
let sweptClaims = false
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
async function spawn($: EngineInterface, args: readonly string[], stdin?: string, project?: string, timeoutMs = CLI_TIMEOUT_MS): Promise<Ran> {
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
      timeoutMs,
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

// A failure that would repeat on every call (an unusable claims directory, a guard check
// that does not answer): logged once per session.
async function failOnce($: EngineInterface, sid: string, where: string, err: unknown): Promise<void> {
  const id = `${sid}\u0000${where}`
  if (failedOnce.has(id)) return
  failedOnce.add(id)
  await fail($, where, err)
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

// ONCE, AND ONE INSTANCE. "Once per session" is held in two places.
//
// This process's own record (`claimed`) is checked first and is always usable: whatever
// happens on disk, one instance never does the same thing twice.
//
// The record on disk is what holds across instances. The package can be loaded twice in
// one session (a checkout named by --plugin-dir and the installed copy named by
// CLAUDE_CODE_PLUGIN_DIRS), and then every hook runs in two environments that share no
// variables; a module reload also starts the variables over. `mkdir` without -p is atomic,
// so whichever instance creates <compound home>/claims/<session>/<key> first owns that
// event. The directory is the user's own, under COMPOUND_HOME (default ~/.claude/compound),
// never a shared temporary directory.
//
// When that directory cannot be made for any reason other than "it already exists", the
// answer is `unusable`, and what the caller does with it depends on what is at stake. A
// REFUSAL (a guard's deny, a stop's refusal) needs `mine`: with no record that it happened,
// a refusal could repeat, so the mod does not refuse. Anything else proceeds, since this
// process's own record already keeps it to once here.
const CLAIM_SH = [
  'mkdir -p "$1" 2>/dev/null',
  'if mkdir "$1/$2" 2>/dev/null; then exit 0; fi',
  'if [ -d "$1/$2" ]; then exit 1; fi',
  'echo "cannot create $1/$2" >&2',
  'exit 3',
].join('\n')

// Claims of sessions that ended more than two weeks ago, removed once per process.
const SWEEP_SH = 'case "$1" in */claims) [ -d "$1" ] && find "$1" -mindepth 1 -maxdepth 1 -type d -mtime +"$2" -exec rm -rf {} + ;; esac; exit 0'

async function claimsRoot($: EngineInterface): Promise<string | undefined> {
  const strip = (t: string) => t.replace(/\/+$/, '')
  const userHome = await $.env.get('HOME')
  let home = await $.env.get('COMPOUND_HOME')
  if (!home) {
    const claudeDir = await $.env.get('COMPOUND_CLAUDE_DIR')
    home = `${strip(claudeDir || '~/.claude')}/compound`
  }
  if (home === '~' || home.startsWith('~/')) {
    if (!userHome) return undefined
    home = `${strip(userHome)}${home.slice(1)}`
  }
  // A relative path is read the way the CLI reads it: from where the CLI runs.
  if (!home.startsWith('/')) home = `${await projectRoot($)}/${home}`
  return `${strip(home)}/claims`
}

async function claim($: EngineInterface, sid: string, key: string): Promise<Claim> {
  const id = `${sid}\u0000${key}`
  if (claimed.has(id)) return 'taken'
  claimed.add(id)
  const safe = (t: string) => t.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 96) || '_'
  try {
    const root = await claimsRoot($)
    if (root === undefined) {
      await failOnce($, sid, 'claim', 'no home directory is known, so there is nowhere to keep the claims; nothing is refused in this session')
      return 'unusable'
    }
    if (!sweptClaims) {
      sweptClaims = true
      await $.process.run(['sh', '-c', SWEEP_SH, 'sh', root, String(CLAIMS_KEPT_DAYS)], { timeoutMs: CLAIM_TIMEOUT_MS })
    }
    const ran = await $.process.run(['sh', '-c', CLAIM_SH, 'sh', `${root}/${safe(sid)}`, safe(key)], { timeoutMs: CLAIM_TIMEOUT_MS })
    if (ran.exitCode === 0) return 'mine'
    if (ran.exitCode === 1) return 'taken'
    await failOnce($, sid, 'claim', `${ran.stderr.trim() || `exit ${ran.exitCode}`}; the claims directory is unusable, so nothing is refused in this session`)
    return 'unusable'
  } catch (err) {
    await failOnce($, sid, 'claim', `${said(err)}; the claims directory is unusable, so nothing is refused in this session`)
    return 'unusable'
  }
}

// For anything that is not a refusal: act unless it is known to be done already.
async function firstTime($: EngineInterface, sid: string, key: string): Promise<boolean> {
  return (await claim($, sid, key)) !== 'taken'
}

// For a refusal: act only when the claim is on record.
async function mayRefuse($: EngineInterface, sid: string, key: string): Promise<boolean> {
  return (await claim($, sid, key)) === 'mine'
}

async function registerCommand($: EngineInterface): Promise<void> {
  const sid = await $.session.id()
  if (commands.has(sid)) return
  commands.add(sid)
  await $.command.register({ name: 'compound', description: 'What compound has stored, reused, guarded and recalled, and whether it is healthy.' })
}

// ---- moment 1: reuse ------------------------------------------------------------------

// Candidate earlier requests: the prompt log searched with the prompt's own significant
// words. Candidates only; the judge decides which of them are like this request.
async function earlierCandidates($: EngineInterface, sid: string, text: string, words: readonly string[]): Promise<Earlier[]> {
  if (words.length === 0) return []
  const found = await cli($, ['find', '--json', ...words])
  if (found === undefined) return []
  // The CLI's prompt rows carry no session, so this session's own prompts are recognised by text.
  const mine = [text, ...(await $.session.messages()).filter(m => m.role === 'user').map(m => m.text)]
  const earlier = parseEarlier(found.stdout, sid, mine, CANDIDATES_MAX, candidateFloor(words.length))
  if (earlier === undefined) {
    await fail($, 'reuse.find', `compound find --json printed something unreadable: ${found.stdout.slice(0, 200)}`)
    return []
  }
  return earlier.map(e => ({ ...e, text: redact(e.text) }))
}

// What earlier sessions in this project fixed and neither recorded nor declined. Asked of
// the CLI at the first typed prompt of a session and told once; it refuses no stop.
async function unsettledReminder($: EngineInterface, sid: string): Promise<string> {
  if (!(await firstTime($, sid, 'unsettled'))) return ''
  const ran = await cli($, ['events', '--unsettled', '--project', await projectRoot($), '--json'])
  if (ran === undefined) return ''
  const open = parseUnsettled(ran.stdout, sid, nowS())
  if (open === undefined) {
    await fail($, 'unsettled.parse', `compound events --unsettled --json printed something unreadable: ${ran.stdout.slice(0, 200)}`)
    return ''
  }
  if (open.length === 0) return ''
  // The newest few: a long backlog is in `compound status`, not in every session's first prompt.
  const shown = open.slice(-UNSETTLED_SHOWN).map(c => ({ ...c, failed: redact(c.failed), error: redact(c.error), fixed: redact(c.fixed) }))
  await log($, { type: 'remind', captures: shown.map(c => c.id) })
  $.ui.status(`compound: ${open.length} unsettled`)
  return unsettledContext(shown, await cliPath($))
}

// Candidates first, then ONE question: the inventory and the candidate earlier requests go
// to the judge together, and only what it names is added to the prompt.
async function reuseCheck($: EngineInterface, sid: string, text: string, k: Knobs): Promise<string> {
  const began = Date.now()
  const request = redact(text)
  if (!(await firstTime($, sid, `reuse-${digest(text)}-${Math.floor(nowS() / 20)}`))) return ''
  const items = reusable((await inventory($)) ?? [])
  const words = significantWords(request)
  const candidates = await earlierCandidates($, sid, text, words)
  // Nothing recorded and nothing like it asked before: no model call is made.
  if (items.length === 0 && candidates.length === 0) return ''
  const gathered = Date.now() - began
  const reply = await ask($, reusePrompt(request, items, candidates), k)
  if (reply.text === undefined) {
    await fail($, 'reuse.judge', `${k.model} gave no answer: ${reply.reason}`)
    return ''
  }
  const answer = parseReuse(reply.text, items, candidates)
  if (answer === undefined) {
    await fail($, 'reuse.parse', `${k.model} answered something unreadable: ${reply.text.slice(0, 200)}`)
    return ''
  }
  const context = answer.substantial ? reuseContext(answer.items, answer.earlier, await cliPath($)) : ''
  if (context === '') return ''
  await log($, {
    type: 'reuse',
    lessons: answer.items.map(i => i.name),
    prompts: answer.earlier.map(e => e.id),
    words,
    candidates: candidates.length,
    prompt_id: digest(text),
    // What the check added to the prompt, in milliseconds: gathering, and the judge.
    ms: Date.now() - began,
    gather_ms: gathered,
    judge_ms: reply.ms,
  })
  $.ui.status(reuseStatus(answer.items.length, answer.earlier.length))
  return context
}

async function onPrompt($: EngineInterface, raw: string, kind: string | undefined, midTurn: boolean): Promise<string[]> {
  if (await off($)) return []
  const text = raw.trim()
  if (text === '' || !userOrigin(kind) || !typedByUser(text) || isCommand(text)) return []
  const sid = await $.session.id()
  // The user typed. With the session idle a turn starts here, and what the stop moment
  // counts starts over; typed over a running turn, the prompt waits for that turn's stop.
  turns.set(sid, turnAfterPrompt(turns.get(sid), nowS(), midTurn))
  if (!midTurn) $.ui.status(undefined)
  await registerCommand($)
  const out: string[] = []
  // The mod's own failures since the last report: each is told once.
  if (hasFailures(sid)) {
    const nth = (reports.get(sid) ?? 0) + 1
    reports.set(sid, nth)
    out.push(errorReport(takeFailures(sid), await cliPath($), nth))
  }
  try {
    const owed = await unsettledReminder($, sid)
    if (owed !== '') out.push(owed)
  } catch (err) {
    await fail($, 'unsettled', err)
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
  // The call waits for this child, so it gets a short time. A check that does not answer,
  // or fails, is killed and the call runs: the guard fails open.
  const ran = await spawn($, ['check'], JSON.stringify({ tool, input }), undefined, GUARD_TIMEOUT_MS)
  if (ran.code !== 0) {
    const why = ran.code === -1 ? `did not answer within ${GUARD_TIMEOUT_MS} ms or could not start (${ran.stderr.trim()})` : `exit ${ran.code}: ${ran.stderr.trim() || '(no output)'}`
    await failOnce($, sid, 'guard.check', `compound check ${why}; calls run unguarded while this lasts`)
    return undefined
  }
  const slow = parseTimedOut(ran.stdout)
  if (slow.length > 0) await failOnce($, sid, 'guard.pattern', `compound check gave up on the match pattern of: ${slow.join(', ')}; rewrite the pattern so it cannot backtrack`)
  const hits = parseHits(ran.stdout)
  if (hits === undefined) {
    await fail($, 'guard.parse', `compound check printed something unreadable: ${ran.stdout.slice(0, 200)}`)
    return undefined
  }
  // Once per session per lesson: the claim is the record, so the same call sent again
  // runs. With no record there is no refusal.
  const fresh = []
  for (const h of hits) {
    if (await mayRefuse($, sid, `guard-${h.name}`)) fresh.push(h)
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

// A lesson met again. When it is another project's, the CLI is asked to move it to the user
// level, and does so only when git does not track it there: a tracked lesson stays, is read
// from where it is, and is offered to the user as a move. The recurrence is logged, marked
// ineffective when this one makes it so. Answers the text Claude reads beside the result.
async function recurred($: EngineInterface, found: Item, tool: string, call: string, error: string, k: Knobs, known: boolean): Promise<string[]> {
  const cliAt = await cliPath($)
  const out: string[] = []
  let lesson = found
  let asProject = lesson.project
  if (asProject !== undefined) {
    // Exit 3: tracked, left in place. Exit 2: not movable as it is (the name is taken in
    // another project, or the lesson is gone): it is read from where it is, if it is there.
    const moved = await cli($, ['promote', lesson.name, '--to', 'user', '--auto', '--seen-in', await projectRoot($), '--json'], undefined, [0, 2, 3], asProject)
    if (moved !== undefined && moved.code === 0) {
      forgetInventory()
      out.push(promotedText(lesson.name, asProject, cliAt))
      $.ui.toast(`compound: lesson ${lesson.name} moved to the user level`)
      lesson = { ...lesson, level: 'user', path: '' }
      asProject = undefined
    } else if (moved !== undefined && moved.code === 3) {
      out.push(candidateText(lesson.name, parseLeft(moved.stdout) ?? asProject, cliAt))
    }
  }
  const shown = await cli($, ['show', lesson.name, '--json'], undefined, [0], asProject)
  const read = shown === undefined ? undefined : parseShow(shown.stdout)
  const text = read === undefined || read.text === '' ? lesson.description : read.text
  if (read !== undefined && read.path !== '') lesson = { ...lesson, path: read.path }
  // The CLI's counts are from before this recurrence is logged: this one is added.
  const count = (read?.recalls ?? 0) + 1
  // A lesson left in another project is that project's to rewrite: this session is not
  // asked to strengthen it, and owes nothing for it.
  const ineffective = asProject === undefined && (read?.since === undefined ? count >= k.recurLimit : read.since + 1 >= (read.limit ?? k.recurLimit))
  await log($, {
    type: 'recall',
    lesson: lesson.name,
    tool,
    call: call.slice(0, LOGGED_CALL),
    error: error.slice(-LOGGED_ERROR),
    at: known ? 'fix' : 'failure',
    guard: lesson.match.length > 0,
    ineffective,
  })
  if (ineffective) $.ui.toast(`compound: lesson ${lesson.name} is ineffective (recalled ${count} times)`)
  $.ui.status(ineffective ? `compound: ${lesson.name} ineffective` : `compound: recalled ${lesson.name}`)
  out.push(known ? knownContext(lesson, text, count, ineffective, cliAt, call) : recallContext(lesson, text, count, ineffective, cliAt, call))
  return out
}

async function lessons($: EngineInterface): Promise<Item[]> {
  const here = ((await inventory($)) ?? []).filter(i => i.kind === 'lesson')
  return [...here, ...(await lessonsElsewhere($, here))]
}

async function onFailure($: EngineInterface, sid: string, key: string, tool: string, callId: string, call: string, errorText: string): Promise<string[]> {
  // The instance that claims the failure holds it, and so is the only one that judges the fix.
  if (!(await firstTime($, sid, `fail-${callId}`))) return []
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
    held.set(key, { tool, call, error, left: FIX_ATTEMPTS, turn: turns.get(sid)?.n ?? 0 })
    return []
  }
  // A failure answered with a recorded lesson is not held: the fix teaches nothing new.
  held.delete(key)
  return recurred($, hit, tool, call, error, k, false)
}

async function onSuccess($: EngineInterface, sid: string, key: string, tool: string, callId: string, agent: string | undefined, call: string): Promise<string[]> {
  const was = held.get(key)
  const step = heldStep(was, tool, turns.get(sid)?.n ?? 0)
  if (step === 'expired') held.delete(key)
  // Another tool's success is not an attempt at the failed call: no question is asked.
  if (was === undefined || step !== 'judge') return []
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
  if (answer.verdict === 'KNOWN') return recurred($, answer.lesson, tool, was.call, was.error, k, true)
  await log($, {
    type: 'capture',
    id: digest(`${sid}:${callId}`),
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
  if (changesStore(verb)) forgetInventory()
  if (failed) return
  // A debt settled, by a lesson or by declining it: nothing is owed, and the entry goes.
  if (verb === 'skip') {
    $.ui.status(undefined)
  } else if (verb === 'add') {
    const learned = await events($, ['--session', await $.session.id(), '--type', 'learn'])
    const last = learned?.[learned.length - 1]
    const name = last === undefined || typeof last.lesson !== 'string' ? '' : last.lesson
    $.ui.toast(name === '' ? 'compound: lesson recorded' : `compound: lesson recorded: ${name}`)
    $.ui.status(undefined)
  } else if (verb === 'promote') {
    $.ui.toast('compound: lesson moved')
  }
}

// ---- moment 5: stop -------------------------------------------------------------------

// The stop goes through: the turn is over, and a prompt that was waiting starts the next.
function turnEnded(sid: string): undefined {
  const turn = turns.get(sid)
  if (turn !== undefined) turns.set(sid, turnAfterStop(turn, nowS()))
  return undefined
}

async function onStop($: EngineInterface, followsBlock: boolean): Promise<string | undefined> {
  if (await off($)) return undefined
  const sid = await $.session.id()
  const rows = await events($, ['--session', sid])
  if (rows === undefined) return turnEnded(sid)
  const cliAt = await cliPath($)
  // A debt is refused once: the claim is the record, so a stop that follows a refusal for
  // one debt can still be refused for a newer one, and never twice for the same. A debt
  // whose claim cannot be put on record is not refused at all.
  const owed = debts(rows)
  const fresh: string[] = []
  for (const d of owed) {
    if (await mayRefuse($, sid, `stop-${d.key}`)) fresh.push(d.key)
  }
  // A recalled lesson that did not prevent its failure is owed a strengthening, on the
  // same terms: once per session per lesson, and only with the claim on record.
  const weak = strengthenings(rows)
  const weakFresh = []
  for (const w of weak) {
    if (await mayRefuse($, sid, `strengthen-${w.name}`)) weakFresh.push(w)
  }
  const refusals: string[] = []
  if (fresh.length > 0) {
    await log($, { type: 'refuse', why: 'debt', debts: fresh })
    refusals.push(stopDebt(owed, cliAt))
  }
  if (weakFresh.length > 0) {
    await log($, { type: 'refuse', why: 'strengthen', lessons: weakFresh.map(w => w.name) })
    refusals.push(stopStrengthen(weakFresh, cliAt))
  }
  if (refusals.length > 0) {
    $.ui.status(fresh.length > 0 ? 'compound: lesson owed' : `compound: strengthen ${weakFresh[0]?.name ?? ''}`)
    return refusals.join('\n\n')
  }
  const turn = turns.get(sid)
  const k = await knobs($)
  if (followsBlock || owed.length > 0 || weak.length > 0 || turn === undefined || turn.calls < k.turnMinCalls) return turnEnded(sid)
  // The cooldown is the user's, not the session's: the last nudge anywhere counts.
  const nudges = await events($, ['--type', 'nudge', '--limit', '1'])
  if (nudges === undefined || !mayNudge(rows, turn.start, nowS(), k.nudgeCooldown, nudges)) return turnEnded(sid)
  if (!(await mayRefuse($, sid, `nudge-${turn.n}`))) return turnEnded(sid)
  const calls = turn.calls
  turns.set(sid, { ...turn, calls: 0 })
  await log($, { type: 'nudge', calls })
  await log($, { type: 'refuse', why: 'nudge', calls })
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
      extra = await onPrompt($, e.text, e.origin?.kind, e.turnId !== undefined)
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
      // A subagent's calls are its own loop's: they do not count toward the main turn.
      turns.set(sid, turnAfterCall(turns.get(sid) ?? turnAfterPrompt(undefined, nowS(), false), e.agentId))
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
          : await onSuccess($, sid, key, tool, e.tool_use_id, e.agentId, call)
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
