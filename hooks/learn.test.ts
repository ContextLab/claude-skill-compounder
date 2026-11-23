import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'
import { BUDGET } from './render'
import { BUSY, GONE_MS, INSIGHTS_STARTED, NOTES, OWED } from './view'

// The learn loop through the mod's own hooks: a failed call that no lesson describes is
// held, later successes are put to the judge as its fix, and the band says what is held
// for as long as it is. The world beneath the mod is the test's: the CLI's replies by
// subcommand, the judge's answer and what it was asked, the tool's result, the clock.

const BENEATH = 'drawn beneath the mod'
const T0 = 1_800_000_000_000
const BAND = { hasSurvey: false, isCollapsed: false, isWorking: true, maxRows: 10, bodyColumns: 120, scroll: { offset: 0, bodyRows: 10 }, view: {} }
const LESSONS = JSON.stringify([
  { kind: 'lesson', name: 'zsh-no-matches-found', level: 'general', description: 'Use when zsh says no matches found.', path: '/g/l/zsh-no-matches-found', match: [] },
])
const NO_LESSON = '{"name":null}'
const RECALLED = '{"name":"zsh-no-matches-found"}'
const fix = (evidence: string) => JSON.stringify({ same_goal: true, call_mistake: true, recurs: true, evidence, verdict: 'FIX' })
const FIX = fix('a target is required')
const NO_FIX = JSON.stringify({ same_goal: false, call_mistake: false, recurs: false, evidence: '', verdict: 'NONE', reason: 'the next step of the work' })
const TRACK_FAILED = '● failed → ○ fixed → ○ owed → ○ recorded'

type Answer = { text: string; isError?: true }
type Run = { argv: string[]; timeoutMs: number | undefined; env: Record<string, string> }
// `unsettled` is what the CLI answers `events --unsettled --project P`; `start` answers
// `insights --start`, and `runs` keeps every call with its budget and environment.
type World = { logged: Record<string, unknown>[]; judge: () => Promise<string>; prompts: string[]; tool: (command: string) => Answer | undefined; calls: string[][]; runs: Run[]; unsettled: string; start: () => Promise<{ code: number; stdout: string }>; statuses: (string | undefined)[]; surfaces: string[] }

let worlds = 0

function world(on: On, env: Record<string, string> = {}): World {
  worlds += 1
  const n = worlds
  const w: World = { logged: [], judge: async () => NO_LESSON, prompts: [], tool: () => undefined, calls: [], runs: [], unsettled: '[]', start: async () => ({ code: 0, stdout: '{"started": false, "why": "not due"}' }), statuses: [], surfaces: ['terminal'] }
  mock.env(on, { HOME: '/home/me', COMPOUND_HOME: '/home/me/compound', COMPOUND_PROMPT_MIN_CHARS: '100000', ...env })
  on('session.id', () => ({ value: `learn-session-${n}` }))
  on('session.root', () => ({ value: `/work/learn-${n}` }))
  on('session.repo', () => ({ value: null }))
  on('session.surfaces', () => ({ value: w.surfaces as never }))
  on('session.messages', () => ({ value: [] }))
  on('fs.exists', () => ({ value: true }))
  on('command.register', () => ({ value: undefined }) as never)
  on('ui.status', (_$, e) => {
    w.statuses.push((e as unknown as { text?: string }).text)
    return { value: undefined }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('ui.panes', () => ({ value: [] }))
  const owed: Record<string, unknown>[] = []
  on('process.run', (_$, e) => {
    const argv = [...e.argv]
    w.calls.push(argv)
    w.runs.push({ argv, timeoutMs: e.init?.timeoutMs, env: { ...(e.init?.env ?? {}) } })
    const verb = argv[0]?.endsWith('/compound') ? argv[1] : argv[0]
    const done = (stdout: string, exitCode = 0) => ({ value: { exitCode, stdout, stderr: exitCode === 0 ? '' : 'compound: failed', isStdoutTruncated: false, isStderrTruncated: false } })
    if (verb === 'insights') return w.start().then(r => done(r.stdout, r.code))
    if (verb === 'log') {
      const event = JSON.parse(e.init?.stdin ?? '{}') as Record<string, unknown>
      w.logged.push(event)
      if (event.type === 'capture') owed.push({ ts: '2026-10-05T12:00:00Z', session: `learn-session-${n}`, ...event })
      return done('')
    }
    if (verb === 'list') return done(LESSONS)
    if (verb === 'check') return done('{"hits":[],"guards":0,"tools":[]}')
    if (verb === 'events') return done(argv.includes('--unsettled') ? (argv.includes('--session') ? JSON.stringify(owed) : w.unsettled) : '[]')
    return done('')
  })
  on('model.complete', async (_$, e) => {
    w.prompts.push(String((e as unknown as { prompt?: unknown }).prompt ?? ''))
    return { value: { isAnswered: true as const, text: await w.judge(), usage: { input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 } } }
  })
  // `./deploy.sh` with no target fails; `w.tool` answers any other call it wants to.
  on('tool.call', (_$, e) => {
    const command = String((e as unknown as { command?: unknown }).command ?? '')
    const answer = w.tool(command)
    if (answer !== undefined) return { result: {}, ...answer } as never
    return (command === './deploy.sh' ? { result: {}, text: 'Exit code 2\ndeploy.sh: error: a target is required', isError: true } : { result: {}, text: 'ok' }) as never
  })
  on('classic.Stop', () => ({}) as never)
  on('prompt.submit', (_$, e) => ({ text: e.text, ...(e.context === undefined ? {} : { context: e.context }) }))
  on('ui.render', { component: 'AbovePrompt', plugin: 'compound' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, null, BENEATH) as never
  })
  return w
}

const of = (w: World, type: string) => w.logged.filter(e => e.type === type)
const NO_MATCH: Answer = { text: 'Exit code 1\n(eval):1: no matches found: *.nope', isError: true }

// ---- a recalled failure and the failure held before it ----

test('a failure that a lesson is recalled for leaves an earlier held failure held: its fix is still captured', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')

  // The first failure: no lesson describes it, so it is held.
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(await shown()).toContain(`watching for the fix   ${TRACK_FAILED}`)

  // Before its fix, another call fails for another reason, one a recorded lesson describes.
  w.tool = command => (command.startsWith('ls ') ? NO_MATCH : undefined)
  w.judge = async () => RECALLED
  const recalled = await $.tool.call({ tool: 'Bash', command: 'ls *.nope' })
  expect(JSON.stringify(recalled.context ?? [])).toContain('zsh-no-matches-found')
  expect(of(w, 'recall').map(e => [e.lesson, e.at])).toEqual([['zsh-no-matches-found', 'failure']])
  // The row says the lesson was recalled, and still carries the failure that is held.
  expect(await shown()).toContain(NOTES.recall.label)
  expect(await shown()).toContain(TRACK_FAILED)

  // The fix of the first failure arrives: it is put to the judge, and the lesson is owed.
  const asked = w.prompts.length
  w.judge = async () => FIX
  const fixed = await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  // The judge runs behind the call: the result came back without waiting for it.
  expect(JSON.stringify(fixed.context ?? [])).not.toContain('owes a lesson')
  await clock.settle()
  expect(w.prompts.length).toBe(asked + 1)
  expect(of(w, 'capture').map(e => [e.failed, e.fixed])).toEqual([['./deploy.sh', './deploy.sh --target staging']])
  // What it produced is given beside the loop's next result, of any tool, and once.
  const next = await $.tool.call({ tool: 'Read', file_path: '/work/notes.md' } as never)
  expect(JSON.stringify(next.context ?? [])).toContain('./deploy.sh --target staging')
  expect(JSON.stringify(next.context ?? [])).toContain('owes a lesson')
  const after = await $.tool.call({ tool: 'Read', file_path: '/work/notes.md' } as never)
  expect(JSON.stringify(after.context ?? [])).not.toContain('owes a lesson')
  expect(await shown()).toContain('✓ failed → ✓ fixed → ● owed → ○ recorded')
  // The judge was shown the call that failed between the two.
  expect(w.prompts[asked]).toContain('Bash (failed): ls *.nope')
  await ui.unmount()
})

test('the held call itself, failing again with a lesson recalled for it, is let go: the lesson answers it', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => RECALLED
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(of(w, 'recall').length).toBe(1)
  // Nothing is held: a success that follows is not put to the judge, and the row lets go.
  const asked = w.prompts.length
  w.judge = async () => FIX
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  expect(w.prompts.length).toBe(asked)
  expect(of(w, 'capture')).toEqual([])
  expect(await shown()).not.toContain('failed')
  await ui.unmount()
})

test('a held failure still gets five judged successes and no more, whatever fails between them', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.tool = command => (command.startsWith('ls ') ? NO_MATCH : undefined)
  for (let i = 0; i < 7; i += 1) {
    w.judge = async () => RECALLED
    await $.tool.call({ tool: 'Bash', command: `ls *.nope${i}` })
    w.judge = async () => NO_FIX
    await $.tool.call({ tool: 'Bash', command: `echo ${i}` })
    await clock.settle()
  }
  expect(of(w, 'judge').filter(e => e.moment === 'fix').length).toBe(5)
  expect(of(w, 'recall').length).toBe(7)
})

// ---- the band while a failure is held ----

test('while a failure is held the row shows it: dim once it is old, never empty, and with no timer running', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const texts = async () => ui.findAll({ type: 'Text' })
  const shown = async () => (await texts()).map(t => t.text).join('')

  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(await shown()).toBe(`◌ compound watching for the fix   ${TRACK_FAILED}`)
  expect((await ui.find({ type: 'Text', text: '● failed' }))?.props).toEqual({ color: 'error', bold: true })

  // Past the eight seconds a result fades in, the failure is still held and still shown, dim.
  await clock.advance(GONE_MS + 3000)
  expect(await shown()).toBe(`◌ compound watching for the fix   ${TRACK_FAILED}`)
  expect((await texts()).every(t => t.props.dimColor === true)).toBe(true)
  // Nothing animates now: an hour passes, no CLI is called, and the row is as it was.
  const calls = w.calls.length
  await clock.advance(3_600_000)
  expect(w.calls.length).toBe(calls)
  expect(await shown()).toBe(`◌ compound watching for the fix   ${TRACK_FAILED}`)

  // A later success is put to the judge: the spinner turns, the track is at `fixed`.
  w.judge = async () => {
    await clock.sleep(300)
    return NO_FIX
  }
  const trying = $.tool.call({ tool: 'Bash', command: 'ls' })
  await clock.settle()
  expect(await shown()).toContain(`${BUSY.fix}   ✓ failed → ● fixed → ○ owed → ○ recorded`)
  await clock.advance(300)
  await trying
  // The judge said it was no fix. The failure is still held, so the row is not empty: it is
  // back at the failure, at once and for as long as it is held.
  expect(await shown()).toBe(`◌ compound watching for the fix   ${TRACK_FAILED}`)
  await clock.advance(3000)
  expect(await shown()).toBe(`◌ compound watching for the fix   ${TRACK_FAILED}`)
  await clock.advance(GONE_MS)
  expect(await shown()).toBe(`◌ compound watching for the fix   ${TRACK_FAILED}`)

  // The fix: the lesson is owed, and the row says that.
  w.judge = async () => FIX
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  expect(await shown()).toContain(`${OWED.label} · ./deploy.sh --target staging`)
  expect(await shown()).toContain('✓ failed → ✓ fixed → ● owed → ○ recorded')
  await ui.unmount()
})

test('the row lets go of a failure when the mod does: after its five attempts', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => NO_FIX
  for (let i = 0; i < 4; i += 1) {
    await $.tool.call({ tool: 'Bash', command: `echo ${i}` })
    expect(await shown()).toContain(`watching for the fix   ${TRACK_FAILED}`)
  }
  await $.tool.call({ tool: 'Bash', command: 'echo 4' })
  expect(await shown()).toBe(BENEATH)
  // And nothing is asked about a sixth.
  const asked = w.prompts.length
  await $.tool.call({ tool: 'Bash', command: 'echo 5' })
  expect(w.prompts.length).toBe(asked)
  await clock.advance(GONE_MS)
  expect(await shown()).toBe(BENEATH)
  await ui.unmount()
})

test('the row keeps a held failure through the turn after its own, and lets go at the one after that', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  await $.prompt.submit({ text: 'deploy it', wait: false, origin: { kind: 'composer' } })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  await clock.advance(GONE_MS + 1000)
  expect(await shown()).toBe(`◌ compound watching for the fix   ${TRACK_FAILED}`)
  // The next turn: the failure is still held, and a success in it is still judged.
  await $.prompt.submit({ text: 'try again', wait: false, origin: { kind: 'composer' } })
  await clock.advance(GONE_MS + 1000)
  expect(await shown()).toBe(`◌ compound watching for the fix   ${TRACK_FAILED}`)
  // The turn after that: it is dropped, and the row with it.
  await $.prompt.submit({ text: 'never mind', wait: false, origin: { kind: 'composer' } })
  await clock.advance(GONE_MS + 1000)
  expect(await shown()).toBe(BENEATH)
  const asked = w.prompts.length
  w.judge = async () => FIX
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  expect(w.prompts.length).toBe(asked)
  await ui.unmount()
})

test('COMPOUND_QUIET=1 hides a held failure, and the failure is still held and its fix captured', async ($, on) => {
  const w = world(on, { COMPOUND_QUIET: '1' })
  const clock = mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(await shown()).toBe(BENEATH)
  await clock.advance(GONE_MS + 1000)
  expect(await shown()).toBe(BENEATH)
  w.judge = async () => FIX
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  await clock.settle()
  expect(of(w, 'capture').length).toBe(1)
  expect(await shown()).toBe(BENEATH)
  await ui.unmount()
})

// ---- the failed call sent again unchanged ----

const TIMED_OUT: Answer = { text: 'Exit code 28\ncurl: (28) Operation timed out after 10002 milliseconds', isError: true }
const CURL = 'curl -fsS --max-time 10 https://registry.example/left-pad'

test('the failed call passing when sent again, with nothing between, is no fix: no model is asked and the failure is let go', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  let down = true
  w.tool = command => (command === CURL && down ? TIMED_OUT : undefined)
  await $.tool.call({ tool: 'Bash', command: CURL })
  expect(await shown()).toContain('watching for the fix')
  // A read in between changes nothing, and is not a call between.
  await $.tool.call({ tool: 'Read', file_path: '/work/package.json' } as never)
  down = false
  const asked = w.prompts.length
  w.judge = async () => fix('Operation timed out')
  const again = await $.tool.call({ tool: 'Bash', command: CURL })
  expect(w.prompts.length).toBe(asked)
  expect(again.context ?? []).toEqual([])
  expect(of(w, 'capture')).toEqual([])
  expect(await shown()).toBe(BENEATH)
  // The failure was let go: the next success is not taken for its fix.
  await $.tool.call({ tool: 'Bash', command: 'curl -fsS https://registry.example/right-pad' })
  expect(w.prompts.length).toBe(asked)
  await ui.unmount()
})

test('the failed call passing unchanged after other calls is put to the judge with those calls, and let go when they explain nothing', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  let down = true
  w.tool = command => (command === CURL && down ? TIMED_OUT : undefined)
  await $.tool.call({ tool: 'Bash', command: CURL })
  w.judge = async () => NO_FIX
  await $.tool.call({ tool: 'Bash', command: 'git status --short' })
  await clock.settle()
  down = false
  const asked = w.prompts.length
  await $.tool.call({ tool: 'Bash', command: CURL })
  await clock.settle()
  expect(w.prompts.length).toBe(asked + 1)
  const prompt = w.prompts[asked]!
  expect(prompt).toContain('CALLS BETWEEN THE TWO')
  expect(prompt).toContain('Bash: git status --short')
  expect(prompt).toContain('Nothing: the later call is the failed call, word for word.')
  expect(of(w, 'capture')).toEqual([])
  // No fix, and the failed call now passes: the failure is over, and nothing later is its fix.
  await $.tool.call({ tool: 'Bash', command: 'curl -fsS https://registry.example/right-pad' })
  expect(w.prompts.length).toBe(asked + 1)
})

test('the failed call passing unchanged after a call that made it work is a fix: the judge sees that call, and the lesson is owed', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  const JQ = "jq -r '.version' package.json"
  let installed = false
  w.tool = command => (command === JQ && !installed ? { text: 'Exit code 127\n(eval):1: command not found: jq', isError: true } : undefined)
  await $.tool.call({ tool: 'Bash', command: JQ })
  // A file written, a file read, and the install: the read is not listed.
  await $.tool.call({ tool: 'Write', file_path: '/work/.tool-versions', content: 'jq 1.7' } as never)
  await $.tool.call({ tool: 'Read', file_path: '/work/package.json' } as never)
  w.judge = async () => NO_FIX
  await $.tool.call({ tool: 'Bash', command: 'brew install jq' })
  await clock.settle()
  installed = true
  const asked = w.prompts.length
  w.judge = async () => fix('command not found: jq')
  await $.tool.call({ tool: 'Bash', command: JQ })
  await clock.settle()
  expect(w.prompts.length).toBe(asked + 1)
  const prompt = w.prompts[asked]!
  const between = prompt.slice(prompt.indexOf('CALLS BETWEEN THE TWO, in'), prompt.indexOf('LATER SUCCESSFUL CALL:'))
  expect(between.split('\n').slice(1, 3)).toEqual(['Write: {"file_path":"/work/.tool-versions","content":"jq 1.7"}', 'Bash: brew install jq'])
  expect(between).not.toContain('Read')
  expect(of(w, 'capture').map(e => [e.failed, e.fixed])).toEqual([[JQ, JQ]])
})

// ---- the same failure again: the lesson is named, not judged or quoted again ----

test('a failure a lesson was shown for in this session, met again, is named in one line: no judge, no show, and a recall marked repeat', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.tool = command => (command.startsWith('ls ') ? { text: `Exit code 1\n(eval):${command.length}: no matches found: /work/learn/${command.slice(3)}`, isError: true } : undefined)
  w.judge = async () => RECALLED
  const first = await $.tool.call({ tool: 'Bash', command: 'ls *.nope' })
  expect(JSON.stringify(first.context ?? [])).toContain('RECORDED-NOTE')
  const asked = w.prompts.length
  const shows = () => w.calls.filter(c => c[1] === 'show').length
  const shown = shows()
  // The same mistake in another call: another line number, another path.
  const again = await $.tool.call({ tool: 'Bash', command: 'ls src/*.nothing' })
  expect(w.prompts.length).toBe(asked)
  expect(shows()).toBe(shown)
  const said = (again.context ?? []).join('\n')
  expect(said.split('\n').length).toBe(1)
  expect(said).toContain('zsh-no-matches-found')
  expect(said).toContain('shown in full earlier in this session')
  expect(said).toMatch(/\/bin\/compound show zsh-no-matches-found` prints it/)
  expect(said).not.toContain('RECORDED-NOTE')
  // It is logged as a recall all the same, so the CLI counts it as it counts any.
  expect(of(w, 'recall').map(e => [e.lesson, e.repeat, e.at])).toEqual([['zsh-no-matches-found', undefined, 'failure'], ['zsh-no-matches-found', true, 'failure']])
})

test('another failure is judged as before, and so is the same one once the store has changed', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.tool = command => (command.startsWith('ls ') ? NO_MATCH : command.startsWith('cat ') ? { text: 'Exit code 1\ncat: x: No such file or directory', isError: true } : undefined)
  w.judge = async () => RECALLED
  await $.tool.call({ tool: 'Bash', command: 'ls *.nope' })
  const asked = w.prompts.length
  // Words that differ are another failure: the judge is asked.
  await $.tool.call({ tool: 'Bash', command: 'cat x' })
  expect(w.prompts.length).toBe(asked + 1)
  // A command that changes the store: the lesson may have been rewritten, so it is shown in full.
  await $.tool.call({ tool: 'Bash', command: 'compound add --update --name zsh-no-matches-found --when w --body b' })
  const full = await $.tool.call({ tool: 'Bash', command: 'ls *.nope' })
  expect(w.prompts.length).toBe(asked + 2)
  expect(JSON.stringify(full.context ?? [])).toContain('RECORDED-NOTE')
  expect(of(w, 'recall').filter(e => e.repeat === true)).toEqual([])
})

// ---- the fix judge runs behind the call ----

test('a success is returned before the fix judge answers, and what it produced comes with the loop\'s next result', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => {
    await clock.sleep(3000)
    return FIX
  }
  // The call returns while the judge has three seconds still to go.
  const fixed = await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  await clock.settle()
  expect(w.prompts.length).toBe(2)
  expect(of(w, 'capture')).toEqual([])
  expect(JSON.stringify(fixed.context ?? [])).not.toContain('owes a lesson')
  // A call made while it is still thinking gets nothing of it.
  const early = await $.tool.call({ tool: 'Write', file_path: '/work/a.txt', content: 'x' } as never)
  expect(JSON.stringify(early.context ?? [])).not.toContain('owes a lesson')
  await clock.advance(3000)
  expect(of(w, 'capture').map(e => e.fixed)).toEqual(['./deploy.sh --target staging'])
  expect(of(w, 'judge').map(e => [e.moment, e.verdict])).toEqual([['recall', 'none'], ['fix', 'fix']])
  // Another loop's result does not carry it; this loop's next does, once.
  const sub = await $.tool.call({ tool: 'Read', file_path: '/work/a.txt', agentId: 'agent-2' } as never)
  expect(JSON.stringify(sub.context ?? [])).not.toContain('owes a lesson')
  const next = await $.tool.call({ tool: 'Read', file_path: '/work/a.txt' } as never)
  expect(JSON.stringify(next.context ?? [])).toContain('This session now owes a lesson')
})

test('the stop waits for a judge still running, within its budget, and refuses for the lesson it made owed', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => {
    await clock.sleep(1500)
    return FIX
  }
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  const stopping = $.classic.Stop({ stop_hook_active: false } as never)
  await clock.advance(1500)
  const stop = await stopping
  expect(String((stop as { block?: unknown }).block ?? '')).toContain('This session owes a lesson')
  expect(of(w, 'capture').length).toBe(1)
})

test('a judge slower than the stop\'s budget lets the stop go, and what it produced comes with the next result', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => {
    await clock.sleep(6000)
    return FIX
  }
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  const stopping = $.classic.Stop({ stop_hook_active: false } as never)
  await clock.advance(2000)
  const stop = await stopping
  expect((stop as { block?: unknown }).block).toBe(undefined)
  expect(of(w, 'capture')).toEqual([])
  await clock.advance(4000)
  expect(of(w, 'capture').length).toBe(1)
  const next = await $.tool.call({ tool: 'Bash', command: 'git status' })
  expect(JSON.stringify(next.context ?? [])).toContain('This session now owes a lesson')
})

test('two successes judged at once capture one held failure once: the later answer is dropped', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => {
    await clock.sleep(500)
    return FIX
  }
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target prod' })
  await clock.settle()
  expect(w.prompts.length).toBe(3)
  await clock.advance(500)
  expect(of(w, 'judge').filter(e => e.moment === 'fix').map(e => e.verdict)).toEqual(['fix', 'fix'])
  expect(of(w, 'capture').map(e => e.fixed)).toEqual(['./deploy.sh --target staging'])
  const next = (await $.tool.call({ tool: 'Bash', command: 'git status' })).context ?? []
  expect(next.filter(c => c.includes('owes a lesson')).length).toBe(1)
})

test('the failed call passing while a judge runs lets the failure go at once: a later success asks no judge', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  let deploys = 0
  w.tool = command => (command === './deploy.sh' && ++deploys > 1 ? { text: 'ok' } : undefined)
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => {
    await clock.sleep(500)
    return NO_FIX
  }
  await $.tool.call({ tool: 'Bash', command: './setup.sh' })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  await $.tool.call({ tool: 'Bash', command: 'git commit -m x' })
  await clock.settle()
  // One question for the failure, one for each of the two calls before it was let go.
  expect(w.prompts.length).toBe(3)
  await clock.advance(500)
  expect(of(w, 'judge').filter(e => e.moment === 'fix').length).toBe(2)
  expect(of(w, 'capture')).toEqual([])
})

// ---- findings of /insights, at a session's first typed prompt ----

const finding = (n: number, more: Record<string, unknown> = {}) => ({
  ts: '2026-11-20T00:00:00Z', type: 'insight', session: 'insights', id: `in-${String(n).repeat(16).slice(0, 16)}`, source: 'facet', of: 'an-earlier-session',
  project: '/work/learn', kinds: ['wrong_approach'], text: `Friction number ${n}: the build was rerun without its profile.`, goal: 'Ship the build', learned: [], ...more,
})
const EARLIER_CAPTURE = { ts: '2026-11-20T00:00:00Z', type: 'capture', session: 'an-earlier-session', id: 'ab12cd34', failed: './build.sh', error: 'a profile is required', fixed: './build.sh --profile dev' }
const typed = (text: string) => ({ text, wait: false, origin: { kind: 'composer' as const } })
const said = (r: { context?: readonly string[] }) => (r.context ?? []).join('\n')
const starts = (w: World) => w.runs.filter(r => r.argv[1] === 'insights')

test('a finding of /insights is shown once, at the first typed prompt, and the remind event names it', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  w.unsettled = JSON.stringify([finding(1)])
  const first = said(await $.prompt.submit(typed('carry on')))
  expect(first).toContain('[compound] An analysis of earlier sessions (Claude Code\'s /insights) noted friction that a lesson may not cover yet.')
  expect(first).toContain('<<<RECORDED-INSIGHT id=in-1111111111111111 source=facet kinds=wrong_approach\n')
  expect(first).toContain('Friction number 1')
  expect(first).toContain('skip --settles in-1111111111111111 --why "..."')
  expect(of(w, 'remind')).toEqual([{ type: 'remind', insights: ['in-1111111111111111'] }])
  // The band notes it beside what else the first prompt found.
  expect(await shown()).toContain(`${NOTES.insights.label} · 1 candidate from /insights`)
  // The second prompt adds nothing, and logs nothing more.
  const second = await $.prompt.submit(typed('and then'))
  expect(said(second)).toBe('')
  expect(of(w, 'remind').length).toBe(1)
  await ui.unmount()
})

// A session nobody is at (`claude -p`: the SDK host's own prompt, and no surface to draw
// on) is shown findings all the same, and its remind says so, so the CLI does not count it.
const headlessCases: { name: string; kind: 'sdk' | 'composer' | 'bridge'; surfaces: string[]; headless: boolean }[] = [
  { name: 'a -p run: the SDK host\'s prompt and no surface', kind: 'sdk', surfaces: [], headless: true },
  { name: 'an SDK host that draws on the desktop app', kind: 'sdk', surfaces: ['desktop'], headless: false },
  { name: 'a prompt typed at the terminal', kind: 'composer', surfaces: ['terminal'], headless: false },
  { name: 'a typed prompt with no surface reported', kind: 'composer', surfaces: [], headless: false },
  { name: 'a prompt from a phone through Remote Control', kind: 'bridge', surfaces: [], headless: false },
]
for (const c of headlessCases) {
  test(`the remind carries headless: true exactly for a session nobody is at: ${c.name}`, async ($, on) => {
    const w = world(on)
    mock.clock(on, { now: T0 })
    w.surfaces = c.surfaces
    w.unsettled = JSON.stringify([finding(1)])
    const text = said(await $.prompt.submit({ text: 'carry on', wait: false, origin: { kind: c.kind } }))
    // Shown either way: a headless session may act on it.
    expect(text).toContain('<<<RECORDED-INSIGHT id=in-1111111111111111')
    expect(of(w, 'remind')).toEqual([{ type: 'remind', insights: ['in-1111111111111111'], ...(c.headless ? { headless: true } : {}) }])
  })
}

test('five findings: the three oldest are shown, and the remind event names those three', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.unsettled = JSON.stringify([1, 2, 3, 4, 5].map(n => finding(n)))
  const text = said(await $.prompt.submit(typed('carry on')))
  expect(text.split('\n').filter(l => l.startsWith('<<<RECORDED-INSIGHT')).length).toBe(3)
  expect(of(w, 'remind').map(e => e.insights)).toEqual([['in-1111111111111111', 'in-2222222222222222', 'in-3333333333333333']])
  expect(text.includes('in-4444444444444444')).toBe(false)
})

test('captures and findings together: the captures\' block comes first, and one remind event names both', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.unsettled = JSON.stringify([EARLIER_CAPTURE, finding(1, { source: 'report', project: undefined, kinds: undefined, goal: undefined, why: 'It was forgotten twice.' })])
  const text = said(await $.prompt.submit(typed('carry on')))
  const capture = text.indexOf('<<<RECORDED-CAPTURE id=ab12cd34')
  const insight = text.indexOf('<<<RECORDED-INSIGHT id=in-1111111111111111 source=report')
  expect(capture >= 0).toBe(true)
  expect(insight > capture).toBe(true)
  // A finding of the report is recorded at the user level.
  expect(text).toContain('--level user')
  expect(of(w, 'remind')).toEqual([{ type: 'remind', captures: ['ab12cd34'], insights: ['in-1111111111111111'] }])
})

test('a start that began a run is told on the band and in the status entry, and nothing is added to the prompt', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  w.start = async () => ({ code: 0, stdout: '{"started": true, "why": "due"}' })
  const first = await $.prompt.submit(typed('carry on'))
  expect(said(first)).toBe('')
  expect(w.statuses).toContain(INSIGHTS_STARTED)
  expect(await shown()).toContain(`${NOTES.insights.label} · ${INSIGHTS_STARTED}`)
  // Nothing was shown to a session, so no remind is written.
  expect(of(w, 'remind')).toEqual([])
  await $.prompt.submit(typed('and then'))
  expect(w.statuses.filter(s => s === INSIGHTS_STARTED).length).toBe(1)
  await ui.unmount()
})

test('a run that began beside findings is told in the same note and status entry as they are', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  w.unsettled = JSON.stringify([finding(1)])
  w.start = async () => ({ code: 0, stdout: '{"started": true, "why": "due"}' })
  const first = said(await $.prompt.submit(typed('carry on')))
  expect(first).toContain('<<<RECORDED-INSIGHT id=in-1111111111111111')
  expect(w.statuses).toContain(`1 candidate from /insights, ${INSIGHTS_STARTED}`)
  expect(await shown()).toContain(`${NOTES.insights.label} · 1 candidate from /insights, ${INSIGHTS_STARTED}`)
  await ui.unmount()
})

test('a run that began is told even when the reminder\'s read fails', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.unsettled = 'compound: not json'
  w.start = async () => ({ code: 0, stdout: '{"started": true, "why": "due"}' })
  expect(said(await $.prompt.submit(typed('carry on')))).toBe('')
  expect(w.statuses).toContain(INSIGHTS_STARTED)
  expect(of(w, 'error').map(e => e.where)).toEqual(['unsettled.parse'])
})

for (const stdout of ['{"started": false, "why": "too soon"}', '{"started": "true"}', '[compound] started: true', '']) {
  test(`a start that began nothing, or answered something unreadable, tells nothing: ${JSON.stringify(stdout)}`, async ($, on) => {
    const w = world(on)
    mock.clock(on, { now: T0 })
    w.start = async () => ({ code: 0, stdout })
    expect(said(await $.prompt.submit(typed('carry on')))).toBe('')
    expect(w.statuses.some(s => (s ?? '').includes(INSIGHTS_STARTED))).toBe(false)
    expect(of(w, 'error')).toEqual([])
  })
}

test('the first typed prompt starts an /insights run once a session, within the typed-prompt budget, and ignores a reply it cannot read', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  // No captures and no findings: the start is made all the same.
  w.start = async () => ({ code: 0, stdout: '[compound] this reply is never read' })
  const first = await $.prompt.submit(typed('carry on'))
  expect(said(first)).toBe('')
  expect(starts(w).map(r => r.argv.slice(1))).toEqual([['insights', '--start', '--json']])
  expect(starts(w)[0]?.timeoutMs).toBe(BUDGET.prompt)
  // It names this session to the CLI as every call does, and passes the store through.
  expect(starts(w)[0]?.env.COMPOUND_HOME).toBe('/home/me/compound')
  expect(starts(w)[0]?.env.CLAUDE_CODE_SESSION_ID).toBe(`learn-session-${worlds}`)
  await $.prompt.submit(typed('and then'))
  await $.prompt.submit(typed('and after that'))
  expect(starts(w).length).toBe(1)
})

test('the start and the reminder\'s read are made together: a slow start does not hold the read back', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  w.unsettled = JSON.stringify([finding(1)])
  w.start = async () => {
    await clock.sleep(3000)
    return { code: 0, stdout: '{"started": true}' }
  }
  const submitting = $.prompt.submit(typed('carry on'))
  await clock.settle()
  // The start has not answered, and the read was already made.
  expect(w.runs.some(r => r.argv.includes('--unsettled') && r.argv.includes('--project'))).toBe(true)
  await clock.advance(3000)
  expect(said(await submitting)).toContain('<<<RECORDED-INSIGHT id=in-1111111111111111')
})

test('a start that fails is logged as an error, and the findings are shown all the same', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.unsettled = JSON.stringify([finding(1)])
  w.start = async () => ({ code: 1, stdout: '' })
  const text = said(await $.prompt.submit(typed('carry on')))
  expect(text).toContain('<<<RECORDED-INSIGHT id=in-1111111111111111')
  expect(of(w, 'error').map(e => e.where)).toEqual(['cli.insights'])
})

// It waits out the real budget of 5 s, so it is given 15.
test('a start that runs out of its budget: the reminder is shown, one error is logged for the session, and it is not called again', { timeoutMs: 15000 }, async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.unsettled = JSON.stringify([finding(1)])
  // The engine kills a child at its budget and the run rejects: here, in real time, as it would.
  // The test runtime's own timer: the hooks' types declare none, as a hook has only `$.clock`.
  const later = (globalThis as unknown as { setTimeout: (run: () => void, ms: number) => unknown }).setTimeout
  w.start = () => new Promise((_resolve, reject) => later(() => reject(new Error('the child was killed at its budget')), BUDGET.prompt))
  const text = said(await $.prompt.submit(typed('carry on')))
  expect(text).toContain('<<<RECORDED-INSIGHT id=in-1111111111111111')
  const errors = of(w, 'error')
  expect(errors.map(e => e.where)).toEqual(['cli.insights'])
  expect(String(errors[0]?.message)).toContain(`did not answer within ${BUDGET.prompt} ms`)
  // The next prompt tells Claude of the failure once, and makes no second start.
  const second = said(await $.prompt.submit(typed('and then')))
  expect(second).toContain('cli.insights')
  expect(starts(w).length).toBe(1)
  expect(of(w, 'error').length).toBe(1)
  expect(said(await $.prompt.submit(typed('and after that')))).toBe('')
  expect(starts(w).length).toBe(1)
})

test('with COMPOUND_OFF=1 no start is made and no finding is shown: the CLI is not called at all', async ($, on) => {
  const w = world(on, { COMPOUND_OFF: '1' })
  mock.clock(on, { now: T0 })
  w.unsettled = JSON.stringify([finding(1)])
  const told = await $.prompt.submit(typed('carry on'))
  expect(said(told)).toBe('')
  expect(w.calls).toEqual([])
})

test('no tool call\'s path asks for a run: only the first typed prompt does', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  w.unsettled = JSON.stringify([finding(1)])
  // Calls before any prompt: a failure, its fix, the judge behind it, the stop.
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => FIX
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  await clock.settle()
  await $.tool.call({ tool: 'Read', file_path: '/work/notes.md' } as never)
  await $.classic.Stop({ stop_hook_active: false } as never)
  expect(starts(w)).toEqual([])
  expect(of(w, 'remind')).toEqual([])
  await $.prompt.submit(typed('carry on'))
  expect(starts(w).length).toBe(1)
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  await clock.settle()
  expect(starts(w).length).toBe(1)
})
