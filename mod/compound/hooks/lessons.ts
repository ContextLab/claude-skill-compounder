import type { EngineInterface, Register } from 'claude-code'
import { enterCall, leaveCall } from './calls'
import { evidenceOf, fixPrompt, parseFix, parseRecall, recallPrompt, type Lesson } from './judge'
import { plain, redact } from './safe'

// compound-lessons: the write-down half of skill-compounder, as function hooks.
//
// One tool.call hook sees every call and its result. A failure is held per agent loop.
// The next successes in that loop are put to a model with the failure: "is this the fix,
// and is it already written down?" A new lesson is written by THIS hook, through
// `skillnote add`, so nothing depends on the agent choosing to record it. A failure that
// matches a recorded lesson gets that lesson back beside its error, and a lesson that
// recurs in a second project is moved to the user's global notes.
//
// Notes stay where bin/skillnote puts them; this module keeps no copy. Its own log,
// <state>/mod/events.jsonl, is the record the measurements read.
//
// EVERY CALL AND ERROR IS MASKED ON THE WAY IN (./safe), before it is held, judged or
// logged, and no command text is written into a note at all: a note line is loaded into
// every later session of the project, comment and all.

// COMPOUND_JUDGE_MODEL overrides it; the replay is how a choice between models is scored.
const JUDGE_MODEL = 'sonnet'
const JUDGE_TIMEOUT_MS = 15000
// How many successes after one failure are put to the judge before the failure is dropped.
const FIX_ATTEMPTS = 2
// Failures of these are path or match slips, one-off by nature, and they are frequent.
const SKIPPED: ReadonlySet<string> = new Set(['Read', 'Edit', 'Write', 'NotebookEdit'])
const REPLAY_BATCH = 4
const LOGGED_CALL = 300

type Pending = { call: string; error: string; left: number }
type Row = Record<string, unknown>
type Answer = { text: string | undefined; ms: number }

// Module variables start over on a reload; a held failure lost that way costs one lesson.
const pending = new Map<string, Pending>()
let cache: { root: string; lessons: Lesson[] } | undefined
let replayed = false

async function stateDir($: EngineInterface): Promise<string> {
  const set = await $.env.get('SKILL_COMPOUNDER_STATE')
  if (set) return `${set}/mod`
  return `${await $.env.get('HOME')}/.claude/skill-compounder/mod`
}

// Appended by one `cat >>`, because two agent loops may log at once and a read-then-write
// through $.fs would drop a row.
async function record($: EngineInterface, row: Row): Promise<void> {
  const dir = await stateDir($)
  const line = JSON.stringify({ ts: Math.floor(Date.now() / 1000), session: await $.session.id(), ...row })
  await $.process.run(['sh', '-c', 'mkdir -p "$1" && cat >> "$1/events.jsonl"', 'sh', dir], {
    stdin: `${line}\n`,
    timeoutMs: 10000,
  })
}

// Where a project note belongs: the repository's root, or where the session started. Never
// the shell's current directory, which moves with every `cd` and would make one repository
// look like several projects.
async function projectRoot($: EngineInterface): Promise<string> {
  const repo = await $.session.repo()
  return repo?.root ?? (await $.session.root())
}

async function skillnote($: EngineInterface, args: readonly string[], cwd: string) {
  const bin = (await $.env.get('COMPOUND_SKILLNOTE')) || 'skillnote'
  return $.process.run([bin, ...args], { cwd, timeoutMs: 20000 })
}

async function listed($: EngineInterface, scope: 'project' | 'global', root: string): Promise<Lesson[]> {
  const ran = await skillnote($, ['list', '--scope', scope, '--project', root, '--json'], root)
  if (ran.exitCode !== 0) return []
  try {
    const rows = JSON.parse(ran.stdout) as { id: string; text: string }[]
    return rows.filter(r => !r.text.startsWith('moved to global:')).map(r => ({ id: r.id, text: r.text, scope }))
  } catch {
    return []
  }
}

// Lessons this mod wrote in OTHER projects and that are still there to be moved: the pool
// a second project's failure is matched against. A lesson that was promoted, could not be
// promoted, or was found gone has left the pool for good.
async function elsewhere($: EngineInterface, root: string, have: ReadonlySet<string>): Promise<Lesson[]> {
  const path = `${await stateDir($)}/events.jsonl`
  if (!(await $.fs.exists(path))) return []
  const written = new Map<string, Lesson>()
  for (const line of (await $.fs.read(path)).split('\n')) {
    if (line === '') continue
    try {
      const r = JSON.parse(line) as { ev: string; id?: string; text?: string; project?: string }
      if (r.id === undefined) continue
      if (r.ev === 'lesson' && r.text !== undefined && r.project !== undefined) {
        written.set(r.id, { id: r.id, text: r.text, scope: 'elsewhere', project: r.project })
      } else if (r.ev === 'promote' || r.ev === 'promote-failed' || r.ev === 'gone') {
        written.delete(r.id)
      }
    } catch {
      continue
    }
  }
  return [...written.values()].filter(l => l.project !== root && !have.has(l.id))
}

async function lessons($: EngineInterface, root: string): Promise<Lesson[]> {
  if (cache !== undefined && cache.root === root) return cache.lessons
  const here = [...(await listed($, 'project', root)), ...(await listed($, 'global', root))]
  const all = [...here, ...(await elsewhere($, root, new Set(here.map(l => l.id))))]
  cache = { root, lessons: all }
  return all
}

async function ask($: EngineInterface, prompt: string): Promise<Answer> {
  const model = (await $.env.get('COMPOUND_JUDGE_MODEL')) || JUDGE_MODEL
  const began = Date.now()
  const r = await $.model.complete({ model, prompt, timeoutMs: JUDGE_TIMEOUT_MS, maxTokens: 500 })
  return { text: r.isAnswered ? r.text : undefined, ms: Date.now() - began }
}

// A lesson met again. Answers whether it still stands. One written in another project has
// now occurred in two, so it moves to the user's global notes: `skillnote promote` moves
// the line and leaves a tombstone. If the note is no longer there to move -- removed by
// hand since -- the lesson is withdrawn and is not stated back.
async function recurred($: EngineInterface, root: string, lesson: Lesson, at: string): Promise<boolean> {
  if (lesson.scope !== 'elsewhere' || lesson.project === undefined) {
    await record($, { ev: 'recur', id: lesson.id, at, project: root })
    return true
  }
  cache = undefined
  const still = (await listed($, 'project', lesson.project)).some(l => l.id === lesson.id)
  if (!still) {
    await record($, { ev: 'gone', id: lesson.id, from: lesson.project })
    return false
  }
  await record($, { ev: 'recur', id: lesson.id, at, project: root })
  const ran = await skillnote($, ['promote', lesson.id, '--to', 'global', '--project', lesson.project], root)
  await record($, { ev: ran.exitCode === 0 ? 'promote' : 'promote-failed', id: lesson.id, from: lesson.project, stderr: ran.stderr.slice(0, 300) })
  return true
}

async function replay($: EngineInterface, path: string): Promise<void> {
  const rows = (await $.fs.read(path)).split('\n').filter(l => l.trim() !== '').map(l => JSON.parse(l) as Row)
  const out: string[] = []
  for (let i = 0; i < rows.length; i += REPLAY_BATCH) {
    const batch = rows.slice(i, i + REPLAY_BATCH).map(async row => {
      const known = (row.lessons as Lesson[] | undefined) ?? []
      const pair = { failed: redact(String(row.failed)), error: redact(String(row.error)), worked: redact(String(row.worked)) }
      const reply = await ask($, fixPrompt(pair, known))
      const verdict = reply.text === undefined ? { verdict: 'UNANSWERED' } : parseFix(reply.text, known, pair.error)
      return JSON.stringify({ id: row.id, label: row.label, ms: reply.ms, ...verdict })
    })
    out.push(...(await Promise.all(batch)))
  }
  await $.fs.write(`${path}.results.jsonl`, `${out.join('\n')}\n`)
}

export const registerLessons: Register = on => {
  // COMPOUND_REPLAY=<labelled pairs> scores the real judge on stored pairs and does nothing
  // else. A path that does not exist is logged and the mod runs as usual: a typo in a
  // test variable must not switch the hook off without a trace.
  on('session.start', async ($, e, next) => {
    const path = await $.env.get('COMPOUND_REPLAY')
    if (!path) return next(e)
    if (await $.fs.exists(path)) {
      await replay($, path)
      replayed = true
    } else {
      await record($, { ev: 'replay-failed', path })
    }
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    // The mission half counts calls and tracks subagents through ./calls; see there.
    enterCall(e.tool_use_id, e.agentId)
    const ran = await next(e).finally(() => leaveCall(e.tool_use_id))
    const tool = String(e.tool)
    if (ran.deny !== undefined || SKIPPED.has(tool)) return ran
    if (replayed || (await $.env.get('COMPOUND_LESSONS')) === '0') return ran

    const key = e.agentId ?? 'main'
    const call = redact(e.tool === 'Bash' ? e.command : `${tool} ${JSON.stringify(e)}`)
    const root = await projectRoot($)

    if (ran.isError === true) {
      const error = redact(String(ran.text ?? ''))
      const known = await lessons($, root)
      const reply = known.length > 0 ? await ask($, recallPrompt(call, error, known)) : undefined
      let hit = reply?.text === undefined ? undefined : parseRecall(reply.text, known)
      if (hit !== undefined && !(await recurred($, root, hit, 'fail'))) hit = undefined
      // A failure that was answered with a recorded lesson is not held: there is nothing
      // new to learn from the fix.
      if (hit === undefined) pending.set(key, { call, error, left: FIX_ATTEMPTS })
      else pending.delete(key)
      await record($, { ev: 'fail', agent: e.agentId ?? null, tool, call: call.slice(0, LOGGED_CALL), recalled: hit?.id ?? null, ms: reply?.ms ?? 0 })
      if (hit === undefined) return ran
      return { ...ran, context: [...(ran.context ?? []), `A lesson recorded earlier matches this failure (${hit.id}): ${hit.text}`] }
    }

    const held = pending.get(key)
    if (held === undefined) return ran
    held.left -= 1
    if (held.left <= 0) pending.delete(key)

    const known = await lessons($, root)
    const reply = await ask($, fixPrompt({ failed: held.call, error: held.error, worked: call }, known))
    const verdict = reply.text === undefined ? { verdict: 'NONE' as const, reason: 'judge unanswered' } : parseFix(reply.text, known, held.error)
    const audit = { ms: reply.ms, evidence: reply.text === undefined ? '' : evidenceOf(reply.text) }
    if (verdict.verdict === 'NONE') {
      await record($, { ev: 'judged', verdict: 'NONE', reason: verdict.reason, ...audit })
      return ran
    }
    pending.delete(key)

    if (verdict.verdict === 'KNOWN') {
      const lesson = known.find(l => l.id === verdict.id)
      if (lesson === undefined || !(await recurred($, root, lesson, 'fix'))) return ran
      return { ...ran, context: [...(ran.context ?? []), `This fail-then-fix is already recorded (${lesson.id}): ${lesson.text}`] }
    }

    // `--` ends the options: a lesson is text, whatever it begins with. The note carries
    // no command text; the pair is in this module's log, masked, for whoever audits it.
    const wrote = await skillnote(
      $,
      ['add', '--scope', 'project', '--source', 'session', '--why', 'written by compound-lessons from a failed call and the call that fixed it', '--project', root, '--', verdict.lesson],
      root,
    )
    const id = /recorded \(([^)]+)\)/.exec(wrote.stdout)?.[1]
    if (wrote.exitCode !== 0 || id === undefined) {
      await record($, { ev: 'write-failed', exit: wrote.exitCode, stderr: plain(wrote.stderr).slice(0, 300), text: verdict.lesson, ...audit })
      return ran
    }
    cache = undefined
    await record($, { ev: 'lesson', id, project: root, text: verdict.lesson, failed: held.call.slice(0, LOGGED_CALL), worked: call.slice(0, LOGGED_CALL), ...audit })
    return { ...ran, context: [...(ran.context ?? []), `This fail-then-fix has been written down as project note ${id}: ${verdict.lesson}`] }
  })
}
