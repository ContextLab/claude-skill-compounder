import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderElement, Timer } from 'claude-code'
import type { CompoundBand, CompoundBoard, CompoundBusyKind } from '../types'
import { isOff, isQuiet, knobsFrom, type Knobs } from './knobs'
import { fixPrompt, parseFix, parseRecall, parseReuse, recallPrompt, reusePrompt } from './judge'
import {
  bareRetry, betweenLine, BUDGET, callText, candidateText, captureContext, changesStore, cliCall, digest, errorReport, errorStatus, FIX_ATTEMPTS, guarded, guardReason, mentionsCli, ranBetween,
  sameCall, soleCli, soleCliShape,
  heldStep, inputOf, isCommand, judged, knownContext, newsKey, owedStatus, promotedText, ranOut, recallContext, refusal, repeatDue, repeatKey, repeatStatus, reportsEvents, reusable,
  reuseContext, reuseStatus, shellError, shellFailure, stopDebt, stopNudge, stopStrengthen, storeNews, toast, turnAfterCall, turnAfterPrompt, turnAfterStop, typedByUser,
  unsettledContext, usedStatus, userOrigin,
  type Failure, type Held, type Repeat, type Turn,
} from './render'
import { oneLine, redact } from './safe'
import {
  askedTimes, learnedSince, mayNudge, memoOf, otherProjects, parseEvents, parseFound, parseGuards, parseGuardTools, parseHits, parseInventory, parseLogged, parseMoved, parseOwed, parseShow,
  parseTimedOut, parseUnsettled, parseUsed, settlers,
  type Earlier, type Event, type Found, type Item,
} from './store'
import {
  allLines, bandRow, began as checkBegan, boardFrom, boardLines, captured, detailFrom, detailLines, emptyPane, ended as checkEnded, erred, failedDetail, firstKey, forPane, forSession, FRAME_MS,
  greeted, GUARD_SHOW_MS, inventoried, itemsFrom, keyLines, motion, newTurn, noted, openedBy, openKey, paneAll, paneBack, paneItems, paneOpening, paneRead, phaseKey,
  reuseFound, reuseIdle, settledBy, stepped, synced, unfixed, watched, weakened,
  type Line, type Seg,
} from './view'

// compound: before a substantial task it looks for existing work to reuse, and after a
// problem is solved it has the lesson written down. Five moments, each one a hook:
//
//   1 reuse    prompt.submit   a typed, substantial prompt gets the existing work that covers it
//   2 guard    tool.call       a call matching a lesson's `match` is refused once per session
//   3 recall   tool.call       a failed call gets the recorded lesson that describes it
//                              (a call refused before it ran is not a failed call, and a Bash
//                              call that exited 0 with a shell error in its output is one)
//   4 capture  tool.call       a success after a held failure makes the session owe a lesson
//                              (one failure is held per agent loop; a failure a lesson is
//                              recalled for leaves it held; the held call passing unchanged
//                              with nothing run between is a retry, not a fix)
//   5 stop     classic.Stop    an owed lesson, or an owed strengthening of one, refuses the stop
//                              once; a long turn is asked once
//
// And once per session, at its first typed prompt, it tells the session what earlier
// sessions in this project left unsettled.
//
// Two more things are seen. A SKILL THAT IS USED: when the engine expands a skill's prompt
// (`skill.prompt`: the Skill tool, a typed `/name`, a preload, one event for each), the CLI
// is asked to count it (`compound use`), which it does for a skill it lists. That is done
// AFTER the hook has answered, so the skill waits for nothing. A REQUEST THAT KEEPS COMING
// BACK: when the reuse check's judge names earlier requests of the same kind, made in
// enough other sessions, and no recorded work covers the request, the note added to the
// prompt offers to make it a skill, once per session per kind of request.
//
// WHAT IS OWED, AND WHAT SETTLED IT, IS THE CLI'S TO SAY. While the session owes a lesson
// or a strengthening, the mod asks `compound events --unsettled --session S` after EVERY
// tool call (any tool, the main loop or a subagent) and at the stop, and the band, the
// status entry and the refusal follow that answer. The text of a command settles nothing:
// it is read only to turn the "recording" spinner, to leave the CLI's own calls unguarded,
// and to know that a call may have written an event worth a toast.
//
// A REFUSAL HAPPENS AT MOST ONCE. A guard's deny and a stop's refusal each need a claim
// (see `claim`), and a claim that cannot be made means the mod does not refuse.
//
// A plugin gets ONE unmatched tool.call hook, so moments 2, 3 and 4 share it.
//
// THE MOD NEVER READS OR WRITES A LESSON FILE OR THE EVENT LOG. Every store operation is
// one `$.process.run` of bin/compound, and ./store reads what it prints. Every firing
// writes an event that way and sets the status entry.
//
// EVERY CLI CALL HAS A BUDGET (./render BUDGET): 1.5 s for the check a tool call waits
// for, 2 s for anything else on a tool-call or stop path, 5 s at a typed prompt. Before a
// tool call the mod makes ONE call, `check`, and no listing. A subcommand that ran out of
// time is not called again until the next typed prompt (`stalled`), so a slow CLI costs a
// turn one budget per subcommand and not one per tool call. Every failure of the mod itself is
// caught, logged as an `error`, and told to Claude at the next typed prompt. Lesson text is
// only ever shown to Claude as a quotation (./render), never as the mod's own instruction.
// COMPOUND_OFF=1 switches all of it off.
//
// WHAT THE PERSON SEES is drawn from values kept in `$.state` (see ../types and ./view):
// the band above the prompt, which shows the check in flight and what the last moment did,
// and the `/compound` pane, a dashboard read from `compound status --json` and `compound
// events --json`, with a list of every lesson (`compound list --json`) and a view of one
// (`compound show <name> --json`) behind its Buttons. The pane's reads are made when it
// opens, at a press and on a timer after an event, never on a path a tool call waits on.
// A drawing problem never breaks a turn: every render hook answers
// `next(e)` on any failure, and logs one `error` per session per kind. One timer animates
// the band, and it runs only while a spinner turns or a result fades. COMPOUND_QUIET=1
// turns the band off; the status entry and the toasts stay.
//
// Everything that touches `$` is in this file: the engine follows `$` into a function
// declared here and never across an import. The pure halves are ./judge (the three
// questions), ./render (the messages), ./store (the CLI's JSON), ./knobs and ./safe.

const LOGGED_CALL = 4000
const LOGGED_ERROR = 2000
// What `spawn` answers in place of an exit code: the child could not start, it was killed
// at its budget, or it was not started because its subcommand ran out of time this turn.
const NOT_STARTED = -1
const TIMED_OUT = -2
const SKIPPED = -3
// How many prompt-log candidates the judge is shown.
const CANDIDATES_MAX = 5
// By its path: a session whose PATH holds no `sh` still has its claims, and so its refusals.
const SH = '/bin/sh'
const CLAIMS_KEPT_DAYS = 14
const SETTINGS_TTL_MS = 30000
const INVENTORY_TTL_MS = 60000
// How many other projects' lessons are looked at when a call fails.
const OTHER_PROJECTS = 6
// How many unsettled captures a session's first prompt is told about.
const UNSETTLED_SHOWN = 5
// The pane's id, how long after an event its data is read again, and how many events it asks for.
const PANE = 'compound'
const BOARD_AFTER_MS = 400
const BOARD_EVENTS = 20
// The log also holds one `judge` event per question, which the pane does not draw: this
// many rows are read so that twenty of the others are among them.
const BOARD_READ = 80
// The rows the pane asks for where it opens above the prompt.
const PANE_ROWS = 34

const BAND = atom({ plugin: 'compound', key: 'band' } as const, null)
const FRAME = atom({ plugin: 'compound', key: 'frame' } as const, 0)
const BOARD = atom({ plugin: 'compound', key: 'board' } as const, null)
// Which of the pane's views is shown, and what the list and the lesson views were read as.
const VIEW = atom({ plugin: 'compound', key: 'pane' } as const, null)

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
// The subcommands that ran out of time in a session's current turn. None of them is
// called again until the next typed prompt starts a turn.
const stalled = new Map<string, Set<string>>()
// The sessions whose last `check` said that no lesson carries a pattern: nothing can hit,
// so no call is made before a tool call. Forgotten at each typed prompt and whenever the
// session runs a CLI command that changes the store.
const noGuards = new Set<string>()
// The tools some guard applies to, as a session's last `check` said: before a call of any
// other tool nothing can hit, so no call is made. Forgotten when `noGuards` is.
const guardTools = new Map<string, Set<string>>()
// What a guard refused, as `<session>:<agent loop>:<tool>`, until that loop's next call of
// the tool: a `retry` event then says whether it was the refused call sent again.
const refusedCalls = new Map<string, { lessons: string[]; text: string }>()
// The events of a session's own CLI calls that were already toasted, per session.
const told = new Map<string, Set<string>>()
// What each session owes, as the CLI last said: the ids of its unsettled captures, the
// lessons it owes a strengthening for, and the time of the oldest of them in seconds.
type Owing = { ids: string[]; weak: string[]; since: number }
const owing = new Map<string, Owing>()
let sweptClaims = false
let ownCli: string | undefined
let settings: { at: number; off: boolean; quiet: boolean; knobs: Knobs } | undefined
// The band's one timer, whether a frame is being drawn, and what the last frame showed.
let ticker: Timer | undefined
let ticking = false
let drawn = ''
// The wait before the pane's data is read again, and how many checks were given an id.
let boardWait: Timer | undefined
let checks = 0
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

// The verb of a Bash call that is the CLI's own call, or undefined: see ./render soleCli.
// Only the path the mod itself runs qualifies. The bare name `compound` never does, and no
// question is put to a shell about what it would run: the shell that answers is never the
// shell that runs the call.
async function ownCall($: EngineInterface, command: string): Promise<string | undefined> {
  if (soleCliShape(command) === undefined) return undefined
  return soleCli(command, await cliPath($))
}

// Where CLI calls run: the repository's root, or where the session started. Never the
// shell's current directory, which moves with every `cd`.
async function projectRoot($: EngineInterface): Promise<string> {
  const repo = await $.session.repo()
  return repo?.root ?? (await $.session.root())
}

async function readSettings($: EngineInterface): Promise<{ off: boolean; quiet: boolean; knobs: Knobs }> {
  if (settings !== undefined && Date.now() - settings.at < SETTINGS_TTL_MS) return settings
  // `$.env.get` takes a literal name, so each is written out.
  const isSwitchedOff = isOff(await $.env.get('COMPOUND_OFF'))
  const quiet = isQuiet(await $.env.get('COMPOUND_QUIET'))
  const found = knobsFrom({
    promptMinChars: await $.env.get('COMPOUND_PROMPT_MIN_CHARS'),
    turnMinCalls: await $.env.get('COMPOUND_TURN_MIN_CALLS'),
    nudgeCooldown: await $.env.get('COMPOUND_NUDGE_COOLDOWN'),
    model: await $.env.get('COMPOUND_MODEL'),
    judgeTimeout: await $.env.get('COMPOUND_JUDGE_TIMEOUT'),
    repeatMin: await $.env.get('COMPOUND_REPEAT_MIN'),
  })
  settings = { at: Date.now(), off: isSwitchedOff, quiet, knobs: found }
  return settings
}

async function off($: EngineInterface): Promise<boolean> {
  return (await readSettings($)).off
}

async function knobs($: EngineInterface): Promise<Knobs> {
  return (await readSettings($)).knobs
}

// One CLI call, with the session stamped on it and the three store locations passed
// through when they are set. `project` runs it as another project. A call that is not
// `counted` (the pane's own reads) neither marks its subcommand as out of time nor is
// skipped for it. `timeoutMs` is its
// budget: past it the child is killed, the answer is TIMED_OUT, and the subcommand is not
// started again in this turn (SKIPPED). Never rejects: a child that could not start is
// NOT_STARTED with the reason as its stderr.
async function spawn($: EngineInterface, args: readonly string[], stdin?: string, project?: string, timeoutMs: number = BUDGET.call, counted = true): Promise<Ran> {
  const verb = args[0] ?? ''
  let sid = ''
  let began = 0
  try {
    sid = await $.session.id()
    if (counted && stalled.get(sid)?.has(verb) === true) {
      return { code: SKIPPED, stdout: '', stderr: `compound ${verb} ran out of time earlier in this turn and is not called again in it` }
    }
    const env: Record<string, string> = { CLAUDE_CODE_SESSION_ID: sid }
    const home = await $.env.get('COMPOUND_HOME')
    if (home) env.COMPOUND_HOME = home
    const claudeDir = await $.env.get('COMPOUND_CLAUDE_DIR')
    if (claudeDir) env.COMPOUND_CLAUDE_DIR = claudeDir
    const pinned = project ?? (await $.env.get('COMPOUND_PROJECT'))
    if (pinned) env.COMPOUND_PROJECT = pinned
    const argv = [await cliPath($), ...args]
    const cwd = await projectRoot($)
    began = Date.now()
    const done = await $.process.run(argv, { cwd, env, timeoutMs, ...(stdin === undefined ? {} : { stdin }) })
    return { code: done.exitCode, stdout: done.stdout, stderr: done.stderr }
  } catch (err) {
    if (began > 0 && ranOut(Date.now() - began, timeoutMs)) {
      if (counted && sid !== '') stalled.set(sid, (stalled.get(sid) ?? new Set<string>()).add(verb))
      return { code: TIMED_OUT, stdout: '', stderr: `compound ${verb} did not answer within ${timeoutMs} ms and was stopped; it is not called again in this turn` }
    }
    return { code: NOT_STARTED, stdout: '', stderr: said(err) }
  }
}

// ---- what the person sees: the band and the pane ----------------------------------------

// A drawing failure, from a place that cannot wait for the log: kept for the next typed
// prompt, once per session per kind.
function drawFailed($: EngineInterface, sid: string, kind: 'band' | 'pane', err: unknown): void {
  const id = `${sid}\u0000ui.${kind}\u0000`
  if (failedOnce.has(id)) return
  void failOnce($, sid, `ui.${kind}`, err).catch(() => undefined)
}

function stopTicker(): void {
  ticker?.cancel()
  ticker = undefined
}

// One frame: the spinner's next glyph, or a fading result's next phase. The timer stops
// itself the moment nothing on the band moves, with one last frame that draws what is left.
async function tick($: EngineInterface): Promise<void> {
  if (ticking) return
  ticking = true
  try {
    const now = await $.clock.now()
    const band = await read($, BAND)
    const how = motion(band, now)
    const key = phaseKey(band, now)
    if (how === 'still') stopTicker()
    if (how === 'spin' || key !== drawn) {
      drawn = key
      await update($, FRAME, () => now)
    }
  } catch (err) {
    stopTicker()
    drawFailed($, 'unknown', 'band', err)
  } finally {
    ticking = false
  }
}

// Starts the band's timer unless it runs: there is one, whatever starts it and however often.
function animate($: EngineInterface): void {
  if (ticker !== undefined) return
  ticker = $.clock.every(FRAME_MS, () => {
    void tick($)
  })
}

// Changes the band's state, which redraws the band. Never rejects, and does nothing when
// the band is switched off.
async function paint($: EngineInterface, change: (band: CompoundBand, now: number) => CompoundBand): Promise<void> {
  let sid = 'unknown'
  try {
    const s = await readSettings($)
    if (s.off || s.quiet) return
    sid = await $.session.id()
    const now = await $.clock.now()
    const next = await update($, BAND, kept => change(forSession(kept, sid), now))
    if (next !== null && motion(next, now) !== 'still') animate($)
  } catch (err) {
    drawFailed($, sid, 'band', err)
  }
}

// Runs `work` with the band's spinner turning under `kind`'s label.
async function during<T>($: EngineInterface, kind: CompoundBusyKind, work: () => Promise<T>): Promise<T> {
  checks += 1
  const id = `${kind}-${checks}`
  await paint($, (band, now) => checkBegan(band, id, kind, now))
  try {
    return await work()
  } finally {
    await paint($, band => checkEnded(band, id))
  }
}

// Whether the session still holds a failed call whose fix it is watching for, in any of its
// agent loops. One that has outlived its turns is dropped here, as a success would drop it.
function holds(sid: string): boolean {
  const turn = turns.get(sid)?.n ?? 0
  let any = false
  for (const [key, was] of held) {
    if (!key.startsWith(`${sid}:`)) continue
    if (heldStep(was, was.tool, turn) === 'expired') held.delete(key)
    else any = true
  }
  return any
}

// The band is made to say what the mod holds: while a failure is held the row shows it, and
// when the last one is dropped (its fix captured, its attempts used up, its turns over, the
// module started over) the row lets go of it. Called wherever `held` may have changed.
async function watch($: EngineInterface, sid: string): Promise<void> {
  const holding = holds(sid)
  await paint($, (band, now) => watched(band, holding, now))
}

// How many failures of the mod this session has not been told about.
function untold(sid: string): number {
  return (failures.get(sid)?.length ?? 0) + (failures.get('unknown')?.length ?? 0)
}

// Reads the pane's data again: `compound status --json` and `compound events --json`. Only
// while the pane is open, and never from a path a tool call waits on.
async function refreshBoard($: EngineInterface): Promise<void> {
  let sid = 'unknown'
  try {
    sid = await $.session.id()
    if (!(await $.ui.panes()).some(pane => pane.id === PANE)) return
    // Exit 1 is a health check that failed: the report is still the answer.
    const status = await spawn($, ['status', '--json'], undefined, undefined, BUDGET.command, false)
    const recent = await spawn($, ['events', '--json', '--limit', String(BOARD_READ)], undefined, undefined, BUDGET.prompt, false)
    const now = await $.clock.now()
    const board: CompoundBoard | undefined = status.code === 0 || status.code === 1 ? boardFrom(status.stdout, recent.code === 0 ? recent.stdout : '', sid, now) : undefined
    const problem = status.code === 0 || status.code === 1 ? 'compound status --json printed something unreadable' : `compound status ${why(status)}`
    await update($, BOARD, () => board ?? { session: sid, at: now, health: [], checks: 0, levels: [], lessons: [], recent: [], open: { unsettled: [], ineffective: [], candidates: [], errors: [], skips: 0 }, problem: oneLine(problem, 300) })
    // The list or the lesson on screen is read again with the dashboard.
    const pane = forPane(await read($, VIEW), sid)
    if (pane.view === 'all') await readItems($, sid)
    if (pane.view === 'lesson' && pane.detail !== null) await readLesson($, sid, pane.detail.name)
  } catch (err) {
    drawFailed($, sid, 'pane', err)
  }
}

// Reads one lesson for the pane: `compound show <name> --json`. A lesson the CLI cannot
// show is the view's to say, not a failure of the mod. The answer is drawn only while that
// lesson is still the one shown.
async function readLesson($: EngineInterface, sid: string, name: string): Promise<void> {
  const ran = await spawn($, ['show', name, '--json'], undefined, undefined, BUDGET.prompt, false)
  const now = await $.clock.now()
  const detail = ran.code === 0 ? detailFrom(ran.stdout, now) : undefined
  const problem = ran.code === 0 ? 'compound show --json printed something unreadable' : `compound show ${why(ran)}`
  await update($, VIEW, kept => paneRead(forPane(kept, sid), name, detail ?? failedDetail(name, problem, now)))
}

// Reads every lesson and skill for the pane: `compound list --json`.
async function readItems($: EngineInterface, sid: string): Promise<void> {
  const ran = await spawn($, ['list', '--json'], undefined, undefined, BUDGET.prompt, false)
  const items = ran.code === 0 ? itemsFrom(ran.stdout) : undefined
  const problem = ran.code === 0 ? 'compound list --json printed something that is not a list' : `compound list ${why(ran)}`
  await update($, VIEW, kept => paneItems(forPane(kept, sid), items, problem))
}

// A view that changed starts at its top: the window is the engine's, and it is asked.
async function paneTop($: EngineInterface): Promise<void> {
  try {
    await $.ui.scroll({ in: PANE, to: 'start' })
  } catch {
    // A surface that scrolls nothing has nothing to move.
  }
}

// A view that changed has its ring put on a row: the lesson the person came back from, else
// the first row there is to open. Left alone, the ring of a redrawn tree is on its first
// Button, which is the key row's. Only a pane that holds the keyboard has a ring to move.
async function paneRing($: EngineInterface, sid: string, from?: string): Promise<void> {
  try {
    const pane = forPane(await read($, VIEW), sid)
    const board = await read($, BOARD)
    const lines = pane.view === 'all' ? allLines(pane.items, '', 100) : pane.view === 'board' ? boardLines(board !== null && board.session === sid ? board : null, 100) : []
    const keys = lines.flatMap(line => line).map(seg => seg.key)
    const key = from !== undefined && keys.includes(openKey(from)) ? openKey(from) : firstKey(lines)
    if (key === undefined) return
    await $.ui.focus({ requestId: PANE, key })
    // A row below the window is brought into it; one already showing does not move.
    await $.ui.scroll({ in: PANE, to: { key } })
  } catch {
    // A surface with no ring has nothing to move.
  }
}

// One press of a Button of the pane, by its key: a lesson's name opens the lesson, and the
// key row's Buttons change the view, read it again or close the pane. A press is the
// person's own act, so the CLI reads it makes are on no path a tool call waits on. Never
// rejects: a failure is kept for the next typed prompt, once per session, and the pane
// stays as it was.
async function pressed($: EngineInterface, key: string): Promise<void> {
  let sid = 'unknown'
  try {
    sid = await $.session.id()
    const session = sid
    const name = openedBy(key)
    if (name !== undefined) {
      await update($, VIEW, kept => paneOpening(forPane(kept, session), name))
      await paneTop($)
      await readLesson($, session, name)
    } else if (key === 'all') {
      await update($, VIEW, kept => paneAll(forPane(kept, session)))
      await paneTop($)
      await readItems($, session)
      await paneRing($, session)
    } else if (key === 'back') {
      const was = forPane(await read($, VIEW), session)
      await update($, VIEW, kept => paneBack(forPane(kept, session)))
      await paneTop($)
      await paneRing($, session, was.view === 'lesson' ? was.detail?.name : undefined)
    } else if (key === 'refresh') {
      await refreshBoard($)
    } else if (key === 'close') {
      // The next `/compound` starts at the dashboard.
      await update($, VIEW, () => emptyPane(session))
      await $.ui.close({ id: PANE })
    }
  } catch (err) {
    drawFailed($, sid, 'pane', err)
  }
}

// The log changed: the pane's data is read again shortly, once for a burst of events.
function boardStale($: EngineInterface): void {
  if (boardWait !== undefined) return
  try {
    boardWait = $.clock.after(BOARD_AFTER_MS, () => {
      boardWait = undefined
      void refreshBoard($)
    })
  } catch {
    boardWait = undefined
  }
}

// What `h` built, as the tree a render hook answers with.
function tree(node: ReturnType<typeof h>): RenderElement {
  if (node === null || node === undefined || typeof node !== 'object' || Array.isArray(node)) throw new Error('the drawing built no element')
  return node as RenderElement
}

function textProps(seg: Seg): Record<string, unknown> {
  return {
    ...(seg.color === undefined ? {} : { color: seg.color }),
    ...(seg.dim === true ? { dimColor: true } : {}),
    ...(seg.bold === true ? { bold: true } : {}),
    ...(seg.inverse === true ? { inverse: true } : {}),
  }
}

// Why a CLI call failed, in one line.
function why(ran: Ran): string {
  if (ran.code === TIMED_OUT) return ran.stderr
  if (ran.code === NOT_STARTED) return `could not start: ${ran.stderr.trim()}`
  return `exit ${ran.code}: ${ran.stderr.trim() || ran.stdout.trim() || '(no output)'}`
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
  // A failure of the drawing itself is not drawn: that is the one thing that could loop.
  if (!where.startsWith('ui.')) await paint($, band => erred(band, untold(sid)))
  const logged = await spawn($, ['log'], JSON.stringify({ type: 'error', where, message }))
  boardStale($)
  if (logged.code !== 0) {
    // The log itself failing is one failure of the session, however many events it loses.
    const id = `${sid}\u0000cli.log\u0000${logged.code === SKIPPED ? TIMED_OUT : logged.code}`
    if (!failedOnce.has(id)) {
      failedOnce.add(id)
      kept.push({ where: 'cli.log', message: oneLine(why(logged), 300) })
    }
  }
}

// A failure that would repeat on every call (an unusable claims directory, a guard check
// that does not answer, a CLI subcommand that fails the same way): logged once per
// session. `what` tells two failures at one place apart.
async function failOnce($: EngineInterface, sid: string, where: string, err: unknown, what = ''): Promise<void> {
  const id = `${sid}\u0000${where}\u0000${what}`
  if (failedOnce.has(id)) return
  failedOnce.add(id)
  await fail($, where, err)
}

// A failure reported from a `.catch` handler, which has one second: it is kept for the
// next typed prompt and shown in the status entry, with nothing awaited.
function failQuietly($: EngineInterface, where: string, message: string): void {
  const kept = failures.get('unknown') ?? []
  kept.push({ where, message: oneLine(message, 500) })
  failures.set('unknown', kept)
  try {
    $.ui.status(errorStatus(kept.length))
  } catch {
    // A surface that cannot show a status entry does not make the failure worse.
  }
  void paint($, band => erred(band, untold(band.session)))
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

// A failed CLI call: each distinct failure of a subcommand is logged once per session. A
// call that was skipped because its subcommand already ran out of time is not a new failure.
async function cliFailed($: EngineInterface, verb: string, ran: Ran): Promise<void> {
  if (ran.code === SKIPPED) return
  const message = why(ran)
  let sid = 'unknown'
  try {
    sid = await $.session.id()
  } catch {
    // The session id is only the key the failure is kept under.
  }
  await failOnce($, sid, `cli.${verb}`, message, ran.code === TIMED_OUT ? 'timeout' : message)
}

// A CLI call whose exit code must be one of `ok`. Anything else is logged as an error and
// answered `undefined`, so a caller reads "the CLI could not say" and adds nothing.
async function cli($: EngineInterface, args: readonly string[], stdin?: string, ok: readonly number[] = [0], project?: string, timeoutMs: number = BUDGET.call): Promise<Ran | undefined> {
  const ran = await spawn($, args, stdin, project, timeoutMs)
  if (ok.includes(ran.code)) return ran
  await cliFailed($, args[0] ?? '', ran)
  return undefined
}

// Appends one event. The CLI fills in `ts`, `session` and `project`.
async function log($: EngineInterface, event: Record<string, unknown>): Promise<void> {
  const ran = await spawn($, ['log'], JSON.stringify(event))
  if (ran.code !== 0) await cliFailed($, 'log', ran)
  boardStale($)
}

// Appends one event and answers it as the CLI wrote it, with the fields the CLI filled in,
// or undefined when the CLI did not say. One call, the one `log` makes anyway.
async function written($: EngineInterface, event: Record<string, unknown>): Promise<Event | undefined> {
  const ran = await spawn($, ['log', '--json'], JSON.stringify(event))
  boardStale($)
  if (ran.code !== 0) {
    await cliFailed($, 'log', ran)
    return undefined
  }
  return parseLogged(ran.stdout)
}

async function events($: EngineInterface, args: readonly string[], timeoutMs: number = BUDGET.call): Promise<Event[] | undefined> {
  const ran = await cli($, ['events', '--json', ...args], undefined, [0], undefined, timeoutMs)
  if (ran === undefined) return undefined
  const rows = parseEvents(ran.stdout)
  if (rows === undefined) await fail($, 'events.parse', `compound events --json printed something unreadable: ${ran.stdout.slice(0, 200)}`)
  return rows
}

// Every lesson and skill at all three levels and the project's scripts, as the CLI lists
// them. Cached for a minute. Asked for at a typed prompt and after a failed or fixing
// call, never before a tool call.
async function inventory($: EngineInterface, timeoutMs: number = BUDGET.call): Promise<Item[] | undefined> {
  const root = await projectRoot($)
  if (listed !== undefined && listed.root === root && Date.now() - listed.at < INVENTORY_TTL_MS) return listed.items
  const ran = await cli($, ['list', '--scripts', '--json'], undefined, [0], undefined, timeoutMs)
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

// The store changed: what was listed, and what was known about guards, is asked again.
function forgetInventory(sid: string): void {
  listed = undefined
  elsewhere = undefined
  noGuards.delete(sid)
  guardTools.delete(sid)
}

// One `judge` event for a question put to the model, whatever it answered: the verdict and
// the milliseconds the call took. What the question led to (a `reuse`, a `recall`, a
// `capture`) is logged where it happens.
async function ruled($: EngineInterface, moment: 'reuse' | 'recall' | 'fix', verdict: string, reply: Reply, more: Record<string, unknown> = {}): Promise<void> {
  await log($, { type: 'judge', moment, verdict, ms: reply.ms, ...more })
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
      await $.process.run([SH, '-c', SWEEP_SH, 'sh', root, String(CLAIMS_KEPT_DAYS)], { timeoutMs: BUDGET.claim })
    }
    const ran = await $.process.run([SH, '-c', CLAIM_SH, 'sh', `${root}/${safe(sid)}`, safe(key)], { timeoutMs: BUDGET.claim })
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
  await $.command.register({ name: 'compound', description: 'Opens the compound dashboard: what is stored, reused, guarded and recalled, and what is open. `/compound status` prints the report.' })
}

// ---- moment 1: reuse ------------------------------------------------------------------

// What the CLI finds for a typed prompt, in one call: the lessons, skills and scripts whose
// weighted overlap with it reaches the floor, the earlier requests that share its rare words,
// and the verdict it holds for this very prompt against this very store, if it holds one.
// Candidates only; the judge decides which of them cover the request. undefined when the CLI
// could not say.
async function gathered($: EngineInterface, sid: string, text: string, request: string): Promise<Found | undefined> {
  const floor = (await $.env.get('COMPOUND_REUSE_FLOOR')) ?? ''
  const args = ['find', '--request', '--json', ...(/^\d{1,4}(\.\d{1,4})?$/.test(floor) ? ['--floor', floor] : [])]
  const ran = await cli($, args, request, [0], undefined, BUDGET.prompt)
  if (ran === undefined) return undefined
  // The CLI's prompt rows carry no session, so this session's own prompts are recognised by text.
  const mine = [text, ...(await $.session.messages()).filter(m => m.role === 'user').map(m => m.text)]
  const found = parseFound(ran.stdout, sid, mine, CANDIDATES_MAX)
  if (found === undefined) {
    await fail($, 'reuse.find', `compound find --json printed something unreadable: ${ran.stdout.slice(0, 200)}`)
    return undefined
  }
  return { ...found, items: reusable(found.items), earlier: found.earlier.map(e => ({ ...e, text: redact(e.text) })) }
}

// What earlier sessions in this project fixed and neither recorded nor declined. Asked of
// the CLI at the first typed prompt of a session and told once; it refuses no stop.
async function unsettledReminder($: EngineInterface, sid: string): Promise<string> {
  if (!(await firstTime($, sid, 'unsettled'))) return ''
  const ran = await cli($, ['events', '--unsettled', '--project', await projectRoot($), '--json'], undefined, [0], undefined, BUDGET.prompt)
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
  $.ui.status(`${open.length} owed from earlier sessions`)
  await paint($, (band, now) => noted(band, 'unsettled', `${open.length} ${open.length === 1 ? 'lesson' : 'lessons'}`, now, shown[shown.length - 1]?.fixed ?? ''))
  return unsettledContext(shown, await cliPath($))
}

// Candidates first, then ONE question: the candidates and the candidate earlier requests go
// to the judge together, and only what it names is added to the prompt. A prompt the CLI
// holds a verdict for is not put to the judge again.
async function reuseCheck($: EngineInterface, sid: string, text: string, k: Knobs): Promise<string> {
  const began = Date.now()
  const request = redact(text)
  if (!(await firstTime($, sid, `reuse-${digest(text)}-${Math.floor(nowS() / 20)}`))) return ''
  const context = await during($, 'reuse', () => reuseJudged($, sid, text, request, began, k))
  // The check ran and added nothing: the band says so, and the session's first is greeted.
  if (context === '') await paint($, (band, now) => reuseIdle(band, now))
  return context
}

async function reuseJudged($: EngineInterface, sid: string, text: string, request: string, began: number, k: Knobs): Promise<string> {
  const listing = await inventory($, BUDGET.prompt)
  // The listing also says whether any lesson carries a pattern, so the guard need not ask.
  if (listing !== undefined && !listing.some(i => i.match.length > 0)) noGuards.add(sid)
  // The same listing gives the greeting its counts: no call is made for them.
  if (listing !== undefined) await paint($, band => inventoried(band, listing.filter(i => i.kind === 'lesson').length, listing.filter(i => i.match.length > 0).length))
  const found = await gathered($, sid, text, request)
  if (found === undefined) return ''
  const { items, earlier: candidates, memo } = found
  const asked = { prompt_id: digest(text) }
  const gatheredMs = Date.now() - began
  if (memo !== undefined) {
    // The same prompt, project and store as a verdict the CLI holds: no model is asked.
    const again = memo.items.map(n => items.find(i => i.name === n)).filter((i): i is Item => i !== undefined)
    // The memo also knows which sessions asked this very request since it was judged. A
    // request that builds nothing reuses nothing, and can still be one that keeps coming back.
    const repeat = await repeated($, sid, again, [...memo.earlier, ...memo.repeats], memo.asked, k, { ...asked, memo: true })
    const context = reuseContext(memo.verdict === 'not-substantial' ? [] : again, memo.verdict === 'not-substantial' ? [] : memo.earlier, await cliPath($), repeat)
    await ruled($, 'reuse', memo.verdict === 'not-substantial' ? memo.verdict : context !== '' ? 'named' : 'nothing', { text: '', ms: 0, reason: '' }, {
      ...asked,
      memo: true,
      ...(context === '' ? {} : { named: [...again.map(i => i.name), ...memo.earlier.map(e => e.id), ...also(repeat, memo.earlier)] }),
    })
    if (context === '') return ''
    return reuseNamed($, again, memo.earlier, context, { words: found.words, candidates: candidates.length, ...asked, ms: Date.now() - began, gather_ms: gatheredMs, judge_ms: 0, memo: true }, repeat)
  }
  // Nothing reached the floor and nothing like it was asked before: no model call is made.
  if (items.length === 0 && candidates.length === 0) return ''
  const reply = await ask($, reusePrompt(request, items, candidates), k)
  if (reply.text === undefined) {
    await ruled($, 'reuse', 'unanswered', reply, { ...asked, reason: oneLine(reply.reason, 200) })
    await fail($, 'reuse.judge', `${k.model} gave no answer: ${reply.reason}`)
    return ''
  }
  const answer = parseReuse(reply.text, request, items, candidates)
  if (answer === undefined) {
    await ruled($, 'reuse', 'unreadable', reply, asked)
    await fail($, 'reuse.parse', `${k.model} answered something unreadable: ${reply.text.slice(0, 200)}`)
    return ''
  }
  // The earlier requests of the same kind: the ones that asked for the same deliverable, and
  // the ones the judge named as the same procedure asked for again.
  const alike = [...answer.earlier, ...answer.repeats.filter(e => !answer.earlier.includes(e))]
  // A prompt that builds nothing (a routine to run) is given no existing work, and may still
  // be offered a skill for the routine: `parseReuse` gives it no items and no covering requests.
  const repeat = await repeated($, sid, answer.items, alike, [], k, asked)
  const context = reuseContext(answer.items, answer.earlier, await cliPath($), repeat)
  const verdict = !answer.substantial ? 'not-substantial' : context === '' ? 'nothing' : 'named'
  await ruled($, 'reuse', verdict, reply, {
    ...asked,
    ...(context === '' ? {} : { named: [...answer.items.map(i => i.name), ...answer.earlier.map(e => e.id), ...also(repeat, answer.earlier)] }),
    ...(answer.unquoted > 0 ? { unquoted: answer.unquoted } : {}),
  })
  // The verdict is kept by the CLI, so this prompt asked again against this store costs no model call.
  // The verdict that is kept is the judge's own: an offer is made anew from it each time.
  const kept = !answer.substantial ? 'not-substantial' : answer.items.length + answer.earlier.length === 0 ? 'nothing' : 'named'
  if (found.key !== '') await cli($, ['memo'], memoOf(found.key, kept, answer.items, answer.earlier, alike))
  if (context === '') return ''
  // What the check added to the prompt, in milliseconds: gathering, and the judge.
  return reuseNamed($, answer.items, answer.earlier, context, { words: found.words, candidates: candidates.length, ...asked, ms: Date.now() - began, gather_ms: gatheredMs, judge_ms: reply.ms }, repeat)
}

// The ids of the earlier requests an offer rests on that are not already named as covering the request.
function also(repeat: Repeat | undefined, earlier: readonly Earlier[]): string[] {
  return repeat === undefined ? [] : repeat.rows.filter(e => !earlier.includes(e)).map(e => e.id)
}

// A request that keeps coming back: made in at least COMPOUND_REPEAT_MIN sessions, this one
// included, with no recorded work that covers it. The offer is made once per session per
// kind of request (a claim), and a `repeat` event says it was made. undefined otherwise.
async function repeated($: EngineInterface, sid: string, items: readonly Item[], alike: readonly Earlier[], askedBy: readonly string[], k: Knobs, more: Record<string, unknown>): Promise<Repeat | undefined> {
  try {
    const times = askedTimes(alike, askedBy, sid)
    if (!repeatDue(items, times, k.repeatMin)) return undefined
    if (!(await firstTime($, sid, `repeat-${repeatKey(alike)}`))) return undefined
    await log($, { type: 'repeat', times, prompts: alike.map(e => e.id), ...more })
    return { times, rows: alike }
  } catch (err) {
    await fail($, 'repeat', err)
    return undefined
  }
}

// Something was named: the `reuse` event, the status entry and the band say so. With only
// an offer to make a skill there is no reuse: the offer's own event was written.
async function reuseNamed($: EngineInterface, items: readonly Item[], earlier: readonly Earlier[], context: string, more: Record<string, unknown>, repeat?: Repeat): Promise<string> {
  if (items.length + earlier.length > 0) {
    await log($, { type: 'reuse', lessons: items.map(i => i.name), prompts: earlier.map(e => e.id), ...more })
    $.ui.status(reuseStatus(items.map(i => i.name), earlier.length))
    await paint($, (band, now) => reuseFound(band, items.map(i => i.name), earlier.length, now))
  }
  if (repeat !== undefined) {
    $.ui.status(repeatStatus(repeat.times))
    await paint($, (band, now) => noted(band, 'repeat', `${repeat.times} sessions`, now, 'a skill is on offer'))
  }
  return context
}

// ---- a skill that is used ---------------------------------------------------------------

const SKILL_NAME = 200
// Two copies of the mod in one session each see the expansion: one counts it. The claim is
// per skill and 20-second window, as the reuse check's is.
const USE_WINDOW_S = 20

// A session invoked a skill. The CLI decides whether it is one compound counts (a skill it
// lists, the package's `learn` and `reuse` left out) and writes the `use` event; the band
// and the status entry say so. Called without being awaited, after the hook has answered:
// the skill's expansion waits for none of this. Never rejects.
async function skillUsed($: EngineInterface, skill: string): Promise<void> {
  try {
    const name = oneLine(skill, SKILL_NAME)
    if (name === '' || (await off($))) return
    const sid = await $.session.id()
    if (!(await firstTime($, sid, `use-${name}-${Math.floor(nowS() / USE_WINDOW_S)}`))) return
    const ran = await cli($, ['use', '--json', '--', name])
    if (ran === undefined) return
    const used = parseUsed(ran.stdout)
    if (used === undefined) {
      await fail($, 'use.parse', `compound use --json printed something unreadable: ${ran.stdout.slice(0, 200)}`)
      return
    }
    if (!used.used) return
    $.ui.status(usedStatus(used.name))
    await paint($, (band, now) => noted(band, 'used', used.name, now, used.level))
    boardStale($)
  } catch (err) {
    await fail($, 'use', err).catch(() => undefined)
  }
}

async function onPrompt($: EngineInterface, raw: string, kind: string | undefined, midTurn: boolean): Promise<string[]> {
  if (await off($)) return []
  const text = raw.trim()
  if (text === '' || !userOrigin(kind) || !typedByUser(text) || isCommand(text)) return []
  const sid = await $.session.id()
  // The user typed. With the session idle a turn starts here, and what the stop moment
  // counts starts over; typed over a running turn, the prompt waits for that turn's stop.
  turns.set(sid, turnAfterPrompt(turns.get(sid), nowS(), midTurn))
  if (!midTurn) {
    $.ui.status(undefined)
    // A failure is held through the turn after its own: the row keeps it until then.
    const holding = holds(sid)
    await paint($, (band, now) => watched(newTurn(band), holding, now))
    // A new turn: a subcommand that ran out of time is tried again, and so is the check.
    stalled.delete(sid)
    noGuards.delete(sid)
    guardTools.delete(sid)
  }
  await registerCommand($)
  const out: string[] = []
  // The mod's own failures since the last report: each is told once.
  if (hasFailures(sid)) {
    const nth = (reports.get(sid) ?? 0) + 1
    reports.set(sid, nth)
    out.push(errorReport(takeFailures(sid), await cliPath($), nth))
    await paint($, band => erred(band, 0))
  }
  try {
    const owed = await unsettledReminder($, sid)
    if (owed !== '') out.push(owed)
  } catch (err) {
    await fail($, 'unsettled', err)
  }
  const k = await knobs($)
  if (text.length < k.promptMinChars) {
    // Too short for a reuse check: the session's first such prompt is still greeted.
    await paint($, (band, now) => greeted(band, now))
    return out
  }
  try {
    const reuse = await reuseCheck($, sid, text, k)
    if (reuse !== '') out.push(reuse)
  } catch (err) {
    await fail($, 'reuse', err)
  }
  return out
}

// ---- moment 2: guard ------------------------------------------------------------------

// THE PRE-CALL PATH MAKES ONE CLI CALL, `check`, and no listing. The reply also counts the
// lessons that carry a `match`; when there is none, nothing can hit, and the calls that
// follow are not held for a process start at all.
async function guard($: EngineInterface, sid: string, loop: string, tool: string, input: Record<string, unknown>): Promise<string | undefined> {
  if (noGuards.has(sid)) return undefined
  // A lesson's patterns are tested against the calls of the tools it names (Bash, unless it
  // says otherwise): before a call of a tool no guard applies to, nothing is asked.
  const applies = guardTools.get(sid)
  if (applies !== undefined && !applies.has(tool)) return undefined
  const began = Date.now()
  // The call waits for this child, so it gets a short time. A check that does not answer,
  // or fails, is killed and the call runs: the guard fails open, and `check` is not
  // called again in this turn.
  // The band's spinner shows only for a check slow enough to notice: a fast one changes
  // no state and adds nothing to the call.
  checks += 1
  const id = `guard-${checks}`
  let shown: Promise<void> | undefined
  let late: Timer | undefined
  try {
    late = $.clock.after(GUARD_SHOW_MS, () => {
      shown = paint($, (band, now) => checkBegan(band, id, 'guard', now))
    })
  } catch {
    // No timer, no spinner: the check itself is what matters.
  }
  let ran: Ran
  try {
    ran = await spawn($, ['check', '--guards'], JSON.stringify({ tool, input }), undefined, BUDGET.check)
  } finally {
    late?.cancel()
    if (shown !== undefined) {
      await shown
      await paint($, band => checkEnded(band, id))
    }
  }
  if (ran.code === SKIPPED) return undefined
  if (ran.code !== 0) {
    await failOnce($, sid, 'guard.check', `${ran.code === TIMED_OUT ? '' : 'compound check: '}${why(ran)}; calls run unguarded while this lasts`)
    return undefined
  }
  if (parseGuards(ran.stdout) === 0) noGuards.add(sid)
  const tools = parseGuardTools(ran.stdout)
  if (tools !== undefined) guardTools.set(sid, new Set(tools))
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
  const whole = callText(tool, input)
  const text = whole.slice(0, LOGGED_CALL)
  const ms = Date.now() - began
  // `watched`: this loop's next call of the tool is logged as a `retry` event.
  for (const h of fresh) await log($, { type: 'guard', lesson: h.name, tool, text, ms, watched: true })
  refusedCalls.set(`${loop}:${tool}`, { lessons: fresh.map(h => h.name), text: whole })
  $.ui.status(`guard ${first.name}`)
  await paint($, (band, now) => noted(band, 'guard', fresh.length > 1 ? `${first.name} +${fresh.length - 1}` : first.name, now, `${tool === 'Bash' ? '' : `${tool} `}${oneLine(redact(text), 60)}`))
  return guardReason(fresh, await cliPath($))
}

// What a loop did with a tool after a guard refused its call: one `retry` event for the
// first call of that tool that follows, saying whether it was the same call. It is written
// after that call has run (or was itself refused), so the call does not wait for it. A
// call of the CLI itself is not that call: a refused session reads the lesson first.
function refusedBefore(loop: string, tool: string, input: Record<string, unknown>): Record<string, unknown> | undefined {
  const key = `${loop}:${tool}`
  const was = refusedCalls.get(key)
  if (was === undefined) return undefined
  refusedCalls.delete(key)
  const text = callText(tool, input)
  return { type: 'retry', lessons: was.lessons, tool, same: sameCall(was.text, text), text: text.slice(0, LOGGED_CALL) }
}

// ---- moments 3 and 4: recall and capture ----------------------------------------------

// A lesson met again. When it is another project's, the CLI is asked to move it to the user
// level, and does so only when git does not track it there: a tracked lesson stays, is read
// from where it is, and is offered to the user as a move. The recurrence is logged, marked
// ineffective when this one makes it so. Answers the text Claude reads beside the result.
async function recurred($: EngineInterface, sid: string, found: Item, tool: string, call: string, error: string, known: boolean, ms: number): Promise<string[]> {
  const cliAt = await cliPath($)
  const out: string[] = []
  let lesson = found
  let moved = false
  let asProject = lesson.project
  if (asProject !== undefined) {
    // Exit 3: tracked, left in place. Exit 2: not movable as it is (another project holds
    // a different lesson of its name, or the lesson is gone). Either way it is read from
    // where it is, if it is there, and offered to the user as a move when the CLI says so.
    const promoted = await cli($, ['promote', lesson.name, '--to', 'user', '--auto', '--seen-in', await projectRoot($), '--json'], undefined, [0, 2, 3], asProject)
    const left = promoted === undefined ? undefined : parseMoved(promoted.stdout)
    if (promoted !== undefined && promoted.code === 0) {
      moved = true
      forgetInventory(sid)
      out.push(promotedText(lesson.name, left?.from ?? asProject, cliAt, left?.also ?? []))
      $.ui.toast(toast('moved', lesson.name))
      lesson = { ...lesson, level: 'user', path: '' }
      asProject = undefined
    } else if (promoted !== undefined && promoted.code === 3) {
      out.push(candidateText(lesson.name, left?.from ?? asProject, cliAt))
    } else if (promoted !== undefined && left !== undefined && left.conflict.length > 0) {
      out.push(candidateText(lesson.name, left.from, cliAt, left.conflict))
    }
  }
  const shown = await cli($, ['show', lesson.name, '--json'], undefined, [0], asProject)
  const read = shown === undefined ? undefined : parseShow(shown.stdout)
  const text = read === undefined || read.text === '' ? lesson.description : read.text
  if (read !== undefined && read.path !== '') lesson = { ...lesson, path: read.path }
  // The CLI's counts are from before this recurrence is logged: this one is added.
  const count = (read?.recalls ?? 0) + 1
  // A guard refuses once per session, and the call sent again runs. A failure after the
  // lesson's guard refused in this session is the session going ahead, not the lesson
  // failing to stop it: it is recalled, and it does not count toward "ineffective". The CLI
  // says whether that refusal is in the log, and leaves such a recall out of its own count.
  const afterGuard = read?.guarded === true
  // WHETHER THIS RECALL COUNTS, AND WHETHER IT MAKES THE LESSON INEFFECTIVE, IS THE CLI'S TO
  // SAY, and it says so in its reply to the `log` that writes the recall: one place, and no
  // prediction here. The event names the lesson by `level` and `path`, which is how the CLI
  // tells a lesson left in another project (that project's to rewrite: nothing is owed for
  // it) and a lesson of the general pool (not rewritten in place: nothing is owed either)
  // from one this session can strengthen. At most one recall per session counts for a
  // lesson since it was last written, so failures that arrive together are one. With no
  // readable reply the recall asks for nothing.
  const level = read?.level || lesson.level
  const wrote = await written($, {
    type: 'recall',
    lesson: lesson.name,
    ...(level === '' ? {} : { level }),
    ...(lesson.path === '' ? {} : { path: lesson.path }),
    tool,
    call: call.slice(0, LOGGED_CALL),
    error: error.slice(-LOGGED_ERROR),
    at: known ? 'fix' : 'failure',
    guard: lesson.match.length > 0,
    after_guard: afterGuard,
    ms,
  })
  const ineffective = wrote?.ineffective === true
  if (ineffective) {
    owes(sid, [], [lesson.name])
    $.ui.toast(toast('ineffective', lesson.name, `recalled ${count} times`))
  }
  $.ui.status(ineffective ? `${lesson.name} ineffective` : `recalled ${lesson.name}`)
  await paint($, (band, now) => (ineffective ? weakened(band, lesson.name, now) : noted(unfixed(band), moved ? 'moved' : 'recall', lesson.name, now)))
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
  let ms = 0
  if (known.length > 0) {
    const reply = await during($, 'recall', () => ask($, recallPrompt(call, error, known), k))
    ms = reply.ms
    if (reply.text === undefined) {
      await ruled($, 'recall', 'unanswered', reply, { tool, reason: oneLine(reply.reason, 200) })
      await fail($, 'recall.judge', `${k.model} gave no answer: ${reply.reason}`)
    } else {
      const answer = parseRecall(reply.text, known)
      if (answer === undefined) {
        await ruled($, 'recall', 'unreadable', reply, { tool })
        await fail($, 'recall.parse', `${k.model} answered something unreadable: ${reply.text.slice(0, 200)}`)
      } else {
        hit = answer.lesson
        await ruled($, 'recall', hit === undefined ? 'none' : 'named', reply, { tool, ...(hit === undefined ? {} : { named: [hit.name] }) })
      }
    }
  }
  if (hit === undefined) {
    // One failure is held per agent loop: a newer one that no lesson describes takes its place.
    held.set(key, { tool, call, error, left: FIX_ATTEMPTS, turn: turns.get(sid)?.n ?? 0, at: nowS(), between: [], skipped: 0 })
    await paint($, (band, now) => watched(stepped(band, 'failed', now), true, now))
    return []
  }
  // A failure answered with a recorded lesson is not held: the fix teaches nothing new. A
  // failure held from before stays held: this one is another mistake, and the fix of the
  // first is still to come. Only when this is the held call itself, sent again and failing
  // again, does the lesson answer the held failure too, and it is let go.
  const was = held.get(key)
  if (was !== undefined && was.tool === tool && sameCall(was.call, call)) held.delete(key)
  else if (was !== undefined) ranBetween(was, betweenLine(tool, call, true))
  const out = await recurred($, sid, hit, tool, call, error, false, ms)
  await watch($, sid)
  return out
}

async function onSuccess($: EngineInterface, sid: string, key: string, tool: string, callId: string, agent: string | undefined, call: string): Promise<string[]> {
  const was = held.get(key)
  const step = heldStep(was, tool, turns.get(sid)?.n ?? 0)
  if (step === 'expired') {
    held.delete(key)
    await watch($, sid)
  }
  // Another tool's success is not an attempt at the failed call: no question is asked.
  if (was === undefined || step !== 'judge') return []
  // The failed call, sent again unchanged with nothing run between, and it passed: nothing
  // was fixed, so no model is asked and no lesson is owed. The failure went away by itself,
  // and it is let go, so that no later success is taken for its fix.
  if (bareRetry(was, tool, call)) {
    held.delete(key)
    await watch($, sid)
    return []
  }
  // The attempt is counted before the question is asked, so two successes that arrive
  // together cannot both be the last. The failure stays held while the judge is asked.
  was.left -= 1
  // The judge has had its attempts, or the failed call itself now passes and was no fix:
  // either way the failure is over, and it is let go.
  const done = was.left <= 0 || sameCall(was.call, call)
  const letGo = async (): Promise<void> => {
    if (done && held.get(key) === was) held.delete(key)
    await paint($, band => unfixed(band))
    await watch($, sid)
  }
  const known = await lessons($)
  const k = await knobs($)
  await paint($, (band, now) => stepped(band, 'fixed', now))
  const pair = { failed: was.call, error: was.error, worked: call, between: [...was.between], skipped: was.skipped }
  const reply = await during($, 'fix', () => ask($, fixPrompt(pair, known), k))
  if (reply.text === undefined) {
    await letGo()
    await ruled($, 'fix', 'unanswered', reply, { tool, reason: oneLine(reply.reason, 200) })
    await fail($, 'capture.judge', `${k.model} gave no answer: ${reply.reason}`)
    return []
  }
  const answer = parseFix(reply.text, known, was.error)
  if (answer === undefined) {
    await letGo()
    await ruled($, 'fix', 'unreadable', reply, { tool })
    await fail($, 'capture.parse', `${k.model} answered something unreadable: ${reply.text.slice(0, 200)}`)
    return []
  }
  await ruled($, 'fix', answer.verdict.toLowerCase(), reply, {
    tool,
    ...(answer.verdict === 'KNOWN' ? { named: [answer.lesson.name] } : {}),
    ...(answer.verdict === 'NONE' ? { reason: answer.reason } : {}),
  })
  if (answer.verdict === 'NONE') {
    await letGo()
    return []
  }
  if (held.get(key) === was) held.delete(key)
  if (answer.verdict === 'KNOWN') {
    // A lesson this session first recorded AFTER the call failed is younger than the
    // failure it matches: it is the lesson of this very failure, written before the fixing
    // call was sent. Meeting it here is no recurrence, and nothing more is owed.
    const learned = await events($, ['--session', sid, '--type', 'learn', '--since', String(was.at)])
    if (learned !== undefined && learnedSince(learned, answer.lesson.name)) {
      await paint($, band => unfixed(band))
      await watch($, sid)
      return []
    }
    const out = await recurred($, sid, answer.lesson, tool, was.call, was.error, true, reply.ms)
    await watch($, sid)
    return out
  }
  const id = digest(`${sid}:${callId}`)
  await log($, {
    type: 'capture',
    id,
    tool,
    failed: was.call.slice(0, LOGGED_CALL),
    error: was.error.slice(-LOGGED_ERROR),
    fixed: call.slice(0, LOGGED_CALL),
    evidence: answer.evidence,
    call: callId,
    agent: agent ?? null,
    ms: reply.ms,
  })
  owes(sid, [id], [])
  $.ui.status(owedStatus(redact(call)))
  await paint($, (band, now) => captured(band, now, redact(call)))
  await watch($, sid)
  return [captureContext({ failed: was.call, error: was.error, fixed: call, id }, await cliPath($))]
}

// Events the CLI wrote, told to the person once each: a toast, the status entry, the band's
// result. An event that changed the store also empties what the mod had listed.
async function tell($: EngineInterface, sid: string, rows: readonly Event[]): Promise<number> {
  const seen = told.get(sid) ?? new Set<string>()
  told.set(sid, seen)
  const fresh = storeNews(rows, seen)
  for (const news of fresh) {
    seen.add(news.key)
    if (news.toast !== undefined) $.ui.toast(news.toast)
    $.ui.status(news.status)
    const event = rows.find(row => newsKey(row) === news.key)
    if (event === undefined) continue
    if (event.type !== 'skip') forgetInventory(sid)
    await paint($, (band, now) => settledBy(band, event, now))
  }
  if (fresh.length > 0) boardStale($)
  return fresh.length
}

// The session ran a command that names the CLI: the store may have changed, and an event
// may be worth a toast. What is told follows the EVENTS that call wrote, never the
// command's text: a command that printed a plan, or failed, wrote none. `began` is when
// the call started. No debt is settled here: see `settle`.
async function onCliCall($: EngineInterface, sid: string, verb: string, began: number): Promise<void> {
  if (changesStore(verb)) forgetInventory(sid)
  if (!reportsEvents(verb)) return
  const rows = await events($, ['--session', sid, '--since', String(began - 1)])
  if (rows !== undefined) await tell($, sid, rows)
  boardStale($)
}

// The session now owes these: remembered so every later tool call asks the CLI about them.
function owes(sid: string, ids: readonly string[], weak: readonly string[]): void {
  const kept = owing.get(sid) ?? { ids: [], weak: [], since: nowS() }
  owing.set(sid, {
    ids: [...kept.ids, ...ids.filter(i => !kept.ids.includes(i))],
    weak: [...kept.weak, ...weak.filter(w => !kept.weak.includes(w))],
    since: kept.since,
  })
}

// What the display holds as owed, or undefined when it holds nothing and no question is
// worth a process. The module's own record first; after a reload that record is gone and
// the band's state, which the session keeps, still says what it shows.
async function shownOwed($: EngineInterface, sid: string): Promise<Owing | undefined> {
  const kept = owing.get(sid)
  if (kept !== undefined && kept.ids.length + kept.weak.length > 0) return kept
  try {
    const band = await read($, BAND)
    if (band !== null && band.session === sid && (band.owed > 0 || band.weak.length > 0)) return { ids: [], weak: [...band.weak], since: 0 }
  } catch {
    // No band to read: the module's record was the answer.
  }
  return undefined
}

// After a tool call, while the display says something is owed: ONE question to the CLI,
// `events --unsettled --session S`, and the band and the status entry are made to say what
// it answered. A debt that is gone was settled, in whatever way the CLI counts as settling
// (a lesson recorded or declined in this session, from a subagent, from a terminal by its
// id, a weak lesson rewritten, removed, made a skill or moved); only then is the log read
// once more, for the event to show as "recorded" or "declined".
async function settle($: EngineInterface, sid: string, was: Owing): Promise<void> {
  const ran = await cli($, ['events', '--unsettled', '--session', sid, '--json'])
  if (ran === undefined) return
  const now = parseOwed(ran.stdout)
  if (now === undefined) {
    await fail($, 'owed.parse', `compound events --unsettled --json printed something unreadable: ${ran.stdout.slice(0, 200)}`)
    return
  }
  const ids = now.debts.map(d => d.id)
  const weak = now.weak.map(w => w.name)
  const goneIds = was.ids.filter(i => !ids.includes(i))
  const goneWeak = was.weak.filter(w => !weak.includes(w))
  const clear = ids.length + weak.length === 0
  let said = 0
  if ((goneIds.length > 0 || goneWeak.length > 0) && was.since > 0) {
    const rows = await events($, ['--since', String(Math.floor(was.since) - 1)])
    if (rows !== undefined) said = await tell($, sid, settlers(rows, sid, goneIds, goneWeak))
  }
  const newest = redact(now.debts[now.debts.length - 1]?.fixed ?? '')
  await paint($, (band, at) => synced(band, ids.length, weak, at, newest))
  if (clear) {
    owing.delete(sid)
    // Settled with nothing to show for it (a lesson removed in a terminal): the entry goes.
    if (said === 0) $.ui.status(undefined)
    boardStale($)
    return
  }
  owing.set(sid, { ids, weak, since: now.since > 0 ? now.since : was.since })
  if (goneIds.length > 0 || goneWeak.length > 0) $.ui.status(ids.length > 0 ? owedStatus(newest) : `strengthen ${weak[0] ?? ''}`)
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
  // What the session owes is asked of the CLI, whose definition of settled is the only one.
  const asked = await cli($, ['events', '--unsettled', '--session', sid, '--json'])
  if (asked === undefined) return turnEnded(sid)
  const now = parseOwed(asked.stdout)
  if (now === undefined) {
    await fail($, 'owed.parse', `compound events --unsettled --json printed something unreadable: ${asked.stdout.slice(0, 200)}`)
    return turnEnded(sid)
  }
  const cliAt = await cliPath($)
  // A debt is refused once: the claim is the record, so a stop that follows a refusal for
  // one debt can still be refused for a newer one, and never twice for the same. A debt
  // whose claim cannot be put on record is not refused at all.
  const owed = now.debts
  const fresh: string[] = []
  for (const d of owed) {
    if (await mayRefuse($, sid, `stop-${d.key}`)) fresh.push(d.key)
  }
  // A recalled lesson that did not prevent its failure is owed a strengthening, on the
  // same terms: once per session per lesson, and only with the claim on record.
  const weak = now.weak
  if (owed.length + weak.length === 0) owing.delete(sid)
  else owing.set(sid, { ids: owed.map(d => d.id), weak: weak.map(w => w.name), since: now.since > 0 ? now.since : (owing.get(sid)?.since ?? 0) })
  const weakFresh = []
  for (const w of weak) {
    if (await mayRefuse($, sid, `strengthen-${w.name}`)) weakFresh.push(w)
  }
  const newest = redact(owed[owed.length - 1]?.fixed ?? '')
  await paint($, (band, now) => synced(band, owed.length, weak.map(w => w.name), now, newest))
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
    $.ui.status(fresh.length > 0 ? owedStatus(newest) : `strengthen ${weakFresh[0]?.name ?? ''}`)
    return refusals.join('\n\n')
  }
  const turn = turns.get(sid)
  const k = await knobs($)
  if (followsBlock || owed.length > 0 || weak.length > 0 || turn === undefined || turn.calls < k.turnMinCalls) return turnEnded(sid)
  // Nothing recorded, declined or captured in this turn; and the cooldown is the user's,
  // not the session's: the last nudge anywhere counts.
  const rows = await events($, ['--session', sid, '--since', String(turn.start)])
  if (rows === undefined) return turnEnded(sid)
  const nudges = await events($, ['--type', 'nudge', '--limit', '1'])
  if (nudges === undefined || !mayNudge(rows, turn.start, nowS(), k.nudgeCooldown, nudges)) return turnEnded(sid)
  if (!(await mayRefuse($, sid, `nudge-${turn.n}`))) return turnEnded(sid)
  const calls = turn.calls
  turns.set(sid, { ...turn, calls: 0 })
  await log($, { type: 'nudge', calls })
  await log($, { type: 'refuse', why: 'nudge', calls })
  $.ui.status('asked about lessons')
  await paint($, (band, now) => noted(band, 'nudge', `${calls} tool calls`, now))
  return stopNudge(calls, cliAt)
}

// ---- registration ---------------------------------------------------------------------

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    try {
      if (!(await off($))) {
        await registerCommand($)
        // A reload starts the module over: a check it had in flight is no longer running,
        // and a pane left open is given its data again.
        await paint($, band => ({ ...band, busy: [] }))
        // And a failure it held is no longer held: the row says what the module holds now.
        await watch($, await $.session.id())
        boardStale($)
      }
    } catch (err) {
      await fail($, 'session.start', err)
    }
    return next(e)
  }).catch(($, e, next) => {
    failQuietly($, 'session.start', `${next.error.kind}: ${next.error.message ?? ""}`)
    return next(e)
  })

  // `/compound` opens the dashboard pane where a person typed it; `/compound status`, a
  // run nobody typed, or a surface that seats no pane, gets the report as text.
  on('command.run', { command: 'compound' }, async ($, e) => {
    const asked = e.args.trim()
    if (asked === 'close') {
      try {
        const sid = await $.session.id()
        await update($, VIEW, () => emptyPane(sid))
        await $.ui.close({ id: PANE })
      } catch (err) {
        drawFailed($, 'unknown', 'pane', err)
      }
      return { text: 'Dashboard closed.' }
    }
    if (asked === '' && e.origin.kind === 'composer') {
      try {
        // The pane opens at the dashboard and without the keyboard: what the person types
        // goes on to the prompt until they give the pane the keys (ctrl+x tab, or a click).
        const sid = await $.session.id()
        await update($, VIEW, () => emptyPane(sid))
        const opened = await $.ui.open({ id: PANE, title: 'compound', rows: PANE_ROWS })
        if (opened.isPlaced) {
          void refreshBoard($)
          return { text: 'Dashboard opened. `/compound status` prints the report; `/compound close` closes the dashboard.' }
        }
      } catch (err) {
        drawFailed($, 'unknown', 'pane', err)
      }
    }
    // Exit 1 is a health check that failed: the report is still the answer.
    const ran = await cli($, ['status'], undefined, [0, 1], undefined, BUDGET.command)
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
    failQuietly($, 'prompt.submit', `${next.error.kind}: ${next.error.message ?? ""}`)
    return next(e)
  })

  // A skill's prompt is expanded: by the Skill tool, by a typed `/name`, or as a preload. One
  // event for each, so the use is counted here and nowhere in the tool-call hook. The hook
  // answers at once; the counting goes on behind it.
  on('skill.prompt', ($, e, next) => {
    void skillUsed($, e.skill)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', async ($, e, next) => {
    const tool = String(e.tool)
    const input = inputOf(e as unknown as Record<string, unknown>)
    const verb = tool === 'Bash' && typeof input.command === 'string' ? cliCall(input.command) : undefined
    // The call is the CLI's own only when it is PROVED to be one simple `compound ...`
    // invocation and nothing else (./render soleCliShape). Any other call is checked.
    let own: string | undefined
    let sid = ''
    let recording: string | undefined
    let retry: Record<string, unknown> | undefined
    try {
      if (await off($)) return next(e)
      sid = await $.session.id()
      // A subagent's calls are its own loop's: they do not count toward the main turn.
      turns.set(sid, turnAfterCall(turns.get(sid) ?? turnAfterPrompt(undefined, nowS(), false), e.agentId))
      own = tool === 'Bash' && typeof input.command === 'string' ? await ownCall($, input.command) : undefined
      // The CLI's own call is not guarded: a lesson's text quotes the mistake it is about.
      if (guarded(tool) && own === undefined) {
        const loop = `${sid}:${e.agentId ?? 'main'}`
        retry = refusedBefore(loop, tool, input)
        const deny = await guard($, sid, loop, tool, input)
        if (deny !== undefined) {
          if (retry !== undefined) await log($, retry)
          return { deny }
        }
      }
      // The session is writing a lesson: the band says so while the CLI runs.
      if (verb === 'add') {
        checks += 1
        const id = `record-${checks}`
        recording = id
        await paint($, (band, now) => checkBegan(band, id, 'record', now))
      }
    } catch (err) {
      await fail($, 'guard', err)
    }

    const began = nowS()
    const ran = await next(e)
    if (recording !== undefined) {
      const id = recording
      await paint($, band => checkEnded(band, id))
    }
    if (sid === '') return ran
    try {
      if (retry !== undefined) await log($, retry)
    } catch (err) {
      await fail($, 'retry', err)
    }
    try {
      // While something is owed, every call may be the one that settled it, whatever its
      // tool and its text: the CLI is asked. With nothing owed, nothing is asked.
      const was = await shownOwed($, sid)
      if (was !== undefined) await settle($, sid, was)
    } catch (err) {
      await fail($, 'settle', err)
    }
    if (ran.deny !== undefined) return ran
    try {
      // What is told about a `compound` command follows the events it wrote. The call that
      // is the CLI's own is read by its verb; one that runs the CLI among other things, or
      // reaches it through a variable or a wrapper, may have written anything.
      if (own !== undefined) {
        await onCliCall($, sid, own, began)
        return ran
      }
      if (verb !== undefined || (tool === 'Bash' && typeof input.command === 'string' && mentionsCli(input.command))) await onCliCall($, sid, 'add', began)
      const key = `${sid}:${e.agentId ?? 'main'}`
      // What this loop holds now: a call that runs while it is held ran between the failure
      // and whatever fixes it, and the judge is shown it.
      // A tool that only reads or keeps books changes nothing, and is not listed.
      const before = held.get(key)
      if (!judged(tool) && (before === undefined || !guarded(tool))) return ran
      const text = String(ran.text ?? '')
      // A call that was refused before it ran (a permission, a safety check, the harness, a
      // hook) is not a failed call: no judge is asked, nothing is held, nothing is watched.
      if (ran.isError === true && refusal(text) !== undefined) return ran
      const call = callText(tool, input)
      if (!judged(tool)) {
        if (before !== undefined) ranBetween(before, betweenLine(tool, call, ran.isError === true))
        return ran
      }
      // A Bash call that exited 0 with the shell's own error in its output did fail.
      const shell = ran.isError !== true && tool === 'Bash' ? shellError(text) : undefined
      const failed = ran.isError === true || shell !== undefined
      const extra =
        ran.isError === true
          ? await onFailure($, sid, key, tool, e.tool_use_id, call, text)
          : shell !== undefined
            ? await onFailure($, sid, key, tool, e.tool_use_id, call, shellFailure(shell, text))
            : await onSuccess($, sid, key, tool, e.tool_use_id, e.agentId, call)
      // A success that was judged no fix, or that another tool made, ran between as well.
      // (A failure that was recalled is noted where it is recalled.)
      if (!failed && before !== undefined && held.get(key) === before) ranBetween(before, betweenLine(tool, call, false))
      return extra.length === 0 ? ran : { ...ran, context: [...(ran.context ?? []), ...extra] }
    } catch (err) {
      await fail($, ran.isError === true ? 'recall' : 'capture', err)
      return ran
    }
  }).catch(($, e, next) => {
    failQuietly($, 'tool.call', `${next.error.kind}: ${next.error.message ?? ""}`)
    return next(e)
  })

  // The band: one row above the prompt, or nothing at all.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    let sid = 'unknown'
    try {
      if (e.props.hasSurvey) return next(e)
      const s = await readSettings($)
      if (s.off || s.quiet) return next(e)
      const band = await read($, BAND)
      // Read for the redraw it brings: the timer writes it once a frame.
      await read($, FRAME)
      sid = await $.session.id()
      if (band === null || band.session !== sid) return next(e)
      const row = bandRow(band, await $.clock.now(), e.props.bodyColumns)
      if (row.length === 0) return next(e)
      const { Box, Text } = $.ui.resolve(e)
      return tree(h(Box, { flexDirection: 'row' }, ...row.map(seg => h(Text, textProps(seg), seg.text))))
    } catch (err) {
      drawFailed($, sid, 'band', err)
      return next(e)
    }
  }).catch(($, e, next) => next(e))

  // The pane `/compound` opens: the key row, then the view shown (the dashboard, every
  // lesson, or one lesson). The key row is first because the window is the engine's: a tree
  // taller than it is scrolled, and a row at its foot would be out of sight.
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e, next) => {
    let sid = 'unknown'
    try {
      const { Box, Button, Text } = $.ui.resolve(e)
      const board = await read($, BOARD)
      const kept = await read($, VIEW)
      sid = await $.session.id()
      const mine = board !== null && board.session === sid ? board : null
      const pane = forPane(kept, sid)
      const columns = Math.max(24, e.props.bodyColumns)
      const body: Line[] = pane.view === 'lesson' ? detailLines(pane.detail, columns) : pane.view === 'all' ? allLines(pane.items, pane.itemsProblem, columns) : boardLines(mine, columns)
      const keys = (taller: boolean): Line[] =>
        keyLines({ view: pane.view, focused: e.props.isFocused, taller, rows: body.some(line => line.some(seg => seg.key !== undefined)), terminal: e.surface === 'terminal' }, columns)
      // The arrows walk the rows while the tree fits its window, and scroll it when it does not.
      const fitting = keys(false)
      const head = fitting.length + body.length > e.props.scroll.bodyRows ? keys(true) : fitting
      // The ring starts on the first row there is to open, not on the key row above it.
      const first = body.flatMap(line => line).find(seg => seg.key !== undefined)?.key
      // A lesson named on two rows is two Buttons, and a key is drawn once.
      const seen = new Map<string, number>()
      const piece = (seg: Seg): ReturnType<typeof h> => {
        if (seg.key === undefined) return h(Text, textProps(seg), seg.text)
        const pressKey = seg.key
        const n = (seen.get(pressKey) ?? 0) + 1
        seen.set(pressKey, n)
        return h(Button, {
          key: n === 1 ? pressKey : `${pressKey}#${n}`,
          label: seg.text,
          plain: true,
          ...(seg.hotkey === undefined ? {} : { hotkey: seg.hotkey }),
          ...(pressKey === 'close' ? { role: 'dismiss' } : {}),
          ...(pressKey === first && n === 1 ? { autoFocus: true } : {}),
          onPress: () => pressed($, pressKey),
        })
      }
      const row = (line: Line): ReturnType<typeof h> => {
        const segs = line.filter(seg => seg.text !== '')
        return segs.length === 0 ? h(Text, null, ' ') : h(Box, { flexDirection: 'row' }, ...segs.map(piece))
      }
      return tree(h(Box, { flexDirection: 'column' }, ...[...head, ...body].map(row)))
    } catch (err) {
      drawFailed($, sid, 'pane', err)
      return next(e)
    }
  }).catch(($, e, next) => next(e))

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
    failQuietly($, 'classic.Stop', `${next.error.kind}: ${next.error.message ?? ""}`)
    return next(e)
  })
}
