import type { EngineInterface, Register } from 'claude-code'
import { fixPrompt, parseFix, parseRecall, recallPrompt, type Lesson } from './judge'

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

// COMPOUND_JUDGE_MODEL overrides it; the replay is how a choice between models is scored.
const JUDGE_MODEL = 'sonnet'
const JUDGE_TIMEOUT_MS = 15000
// How many successes after one failure are put to the judge before the failure is dropped.
const FIX_ATTEMPTS = 2
// Failures of these are path or match slips, one-off by nature, and they are frequent.
const SKIPPED: ReadonlySet<string> = new Set(['Read', 'Edit', 'Write', 'NotebookEdit'])
const REPLAY_BATCH = 4

type Pending = { call: string; error: string; left: number; recalled: boolean }
type Row = Record<string, unknown>

// Module variables start over on a reload; a held failure lost that way costs one lesson.
const pending = new Map<string, Pending>()
let cache: { cwd: string; lessons: Lesson[] } | undefined

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

async function skillnote($: EngineInterface, args: readonly string[], cwd: string) {
  const bin = (await $.env.get('COMPOUND_SKILLNOTE')) || 'skillnote'
  return $.process.run([bin, ...args], { cwd, timeoutMs: 20000 })
}

async function listed($: EngineInterface, scope: 'project' | 'global', cwd: string): Promise<Lesson[]> {
  const ran = await skillnote($, ['list', '--scope', scope, '--project', cwd, '--json'], cwd)
  if (ran.exitCode !== 0) return []
  try {
    const rows = JSON.parse(ran.stdout) as { id: string; text: string }[]
    return rows.filter(r => !r.text.startsWith('moved to global:')).map(r => ({ id: r.id, text: r.text, scope }))
  } catch {
    return []
  }
}

// Lessons this mod wrote in OTHER projects and has not yet promoted: the pool a second
// project's failure is matched against, which is what makes a lesson user-wide.
async function elsewhere($: EngineInterface, cwd: string, have: ReadonlySet<string>): Promise<Lesson[]> {
  const path = `${await stateDir($)}/events.jsonl`
  if (!(await $.fs.exists(path))) return []
  const out: Lesson[] = []
  for (const line of (await $.fs.read(path)).split('\n')) {
    if (!line.includes('"ev":"lesson"')) continue
    try {
      const r = JSON.parse(line) as { id: string; text: string; project: string }
      if (r.project !== cwd && !have.has(r.id)) out.push({ id: r.id, text: r.text, scope: 'elsewhere', project: r.project })
    } catch {
      continue
    }
  }
  return out
}

async function lessons($: EngineInterface, cwd: string): Promise<Lesson[]> {
  if (cache !== undefined && cache.cwd === cwd) return cache.lessons
  const here = [...(await listed($, 'project', cwd)), ...(await listed($, 'global', cwd))]
  const all = [...here, ...(await elsewhere($, cwd, new Set(here.map(l => l.id))))]
  cache = { cwd, lessons: all }
  return all
}

async function ask($: EngineInterface, prompt: string): Promise<string | undefined> {
  const model = (await $.env.get('COMPOUND_JUDGE_MODEL')) || JUDGE_MODEL
  const r = await $.model.complete({ model, prompt, timeoutMs: JUDGE_TIMEOUT_MS, maxTokens: 500 })
  return r.isAnswered ? r.text : undefined
}

// A lesson met again. One written in another project has now occurred in two, so it moves
// to the user's global notes: `skillnote promote` moves the line and leaves a tombstone.
async function recurred($: EngineInterface, cwd: string, lesson: Lesson, at: string): Promise<void> {
  await record($, { ev: 'recur', id: lesson.id, at, project: cwd })
  if (lesson.scope !== 'elsewhere' || lesson.project === undefined) return
  const ran = await skillnote($, ['promote', lesson.id, '--to', 'global', '--project', lesson.project], cwd)
  await record($, { ev: ran.exitCode === 0 ? 'promote' : 'promote-failed', id: lesson.id, from: lesson.project, stderr: ran.stderr.slice(0, 300) })
  cache = undefined
}

async function replay($: EngineInterface, path: string): Promise<void> {
  const rows = (await $.fs.read(path)).split('\n').filter(l => l.trim() !== '').map(l => JSON.parse(l) as Row)
  const out: string[] = []
  for (let i = 0; i < rows.length; i += REPLAY_BATCH) {
    const batch = rows.slice(i, i + REPLAY_BATCH).map(async row => {
      const known = (row.lessons as Lesson[] | undefined) ?? []
      const pair = { failed: String(row.failed), error: String(row.error), worked: String(row.worked) }
      const reply = await ask($, fixPrompt(pair, known))
      const verdict = reply === undefined ? { verdict: 'UNANSWERED' } : parseFix(reply, known, pair.error)
      return JSON.stringify({ id: row.id, label: row.label, ...verdict })
    })
    out.push(...(await Promise.all(batch)))
  }
  await $.fs.write(`${path}.results.jsonl`, `${out.join('\n')}\n`)
}

export const register: Register = on => {
  // COMPOUND_REPLAY=<labelled pairs> scores the real judge on stored pairs and does nothing else.
  on('session.start', async ($, e, next) => {
    const path = await $.env.get('COMPOUND_REPLAY')
    if (path) await replay($, path)
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    const tool = String(e.tool)
    if (ran.deny !== undefined || SKIPPED.has(tool)) return ran
    if ((await $.env.get('COMPOUND_REPLAY')) || (await $.env.get('COMPOUND_LESSONS')) === '0') return ran

    const key = e.agentId ?? 'main'
    const call = e.tool === 'Bash' ? e.command : `${tool} ${JSON.stringify(e)}`
    const cwd = await $.session.cwd()

    if (ran.isError === true) {
      const error = String(ran.text ?? '')
      const known = await lessons($, cwd)
      const reply = known.length > 0 ? await ask($, recallPrompt(call, error, known)) : undefined
      const hit = reply === undefined ? undefined : parseRecall(reply, known)
      pending.set(key, { call, error, left: FIX_ATTEMPTS, recalled: hit !== undefined })
      await record($, { ev: 'fail', agent: e.agentId ?? null, tool, call: call.slice(0, 300), recalled: hit?.id ?? null })
      if (hit === undefined) return ran
      await recurred($, cwd, hit, 'fail')
      return { ...ran, context: [...(ran.context ?? []), `A lesson recorded earlier matches this failure (${hit.id}): ${hit.text}`] }
    }

    const held = pending.get(key)
    if (held === undefined) return ran
    held.left -= 1
    if (held.left <= 0 || held.recalled) pending.delete(key)
    // Already stated back at the failure, so there is nothing new to write.
    if (held.recalled) return ran

    const known = await lessons($, cwd)
    const reply = await ask($, fixPrompt({ failed: held.call, error: held.error, worked: call }, known))
    const verdict = reply === undefined ? { verdict: 'NONE' as const, reason: 'judge unanswered' } : parseFix(reply, known, held.error)
    if (verdict.verdict === 'NONE') {
      await record($, { ev: 'judged', verdict: 'NONE', reason: verdict.reason })
      return ran
    }
    pending.delete(key)

    if (verdict.verdict === 'KNOWN') {
      const lesson = known.find(l => l.id === verdict.id)
      if (lesson === undefined) return ran
      await recurred($, cwd, lesson, 'fix')
      return { ...ran, context: [...(ran.context ?? []), `This fail-then-fix is already recorded (${lesson.id}): ${lesson.text}`] }
    }

    const why = `written by compound-lessons: \`${held.call.slice(0, 140)}\` failed, \`${call.slice(0, 140)}\` worked`
    const wrote = await skillnote(
      $,
      ['add', '--scope', 'project', verdict.lesson, '--source', 'session', '--why', why, '--project', cwd],
      cwd,
    )
    const id = /recorded \(([^)]+)\)/.exec(wrote.stdout)?.[1]
    if (wrote.exitCode !== 0 || id === undefined) {
      await record($, { ev: 'write-failed', exit: wrote.exitCode, stderr: wrote.stderr.slice(0, 300), text: verdict.lesson })
      return ran
    }
    cache = undefined
    await record($, { ev: 'lesson', id, project: cwd, text: verdict.lesson, failed: held.call.slice(0, 300), worked: call.slice(0, 300) })
    return { ...ran, context: [...(ran.context ?? []), `This fail-then-fix has been written down as project note ${id}: ${verdict.lesson}`] }
  })
}
