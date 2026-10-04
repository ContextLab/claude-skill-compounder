import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'
import { BUSY, GONE_MS, NOTES, OWED } from './view'

// The learn loop through the mod's own hooks: a failed call that no lesson describes is
// held, later successes are put to the judge as its fix, and the band says what is held
// for as long as it is. The world beneath the mod is the test's: the CLI's replies by
// subcommand, the judge's answer and what it was asked, the tool's result, the clock.

const BENEATH = 'drawn beneath the mod'
const T0 = 1_800_000_000_000
const BAND = { hasSurvey: false, isWorking: true, maxRows: 10, bodyColumns: 120, scroll: { offset: 0, bodyRows: 10 }, view: {} }
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
type World = { logged: Record<string, unknown>[]; judge: () => Promise<string>; prompts: string[]; tool: (command: string) => Answer | undefined; calls: string[][] }

let worlds = 0

function world(on: On, env: Record<string, string> = {}): World {
  worlds += 1
  const n = worlds
  const w: World = { logged: [], judge: async () => NO_LESSON, prompts: [], tool: () => undefined, calls: [] }
  mock.env(on, { HOME: '/home/me', COMPOUND_HOME: '/home/me/compound', COMPOUND_PROMPT_MIN_CHARS: '100000', ...env })
  on('session.id', () => ({ value: `learn-session-${n}` }))
  on('session.root', () => ({ value: `/work/learn-${n}` }))
  on('session.repo', () => ({ value: null }))
  on('session.messages', () => ({ value: [] }))
  on('fs.exists', () => ({ value: true }))
  on('command.register', () => ({ value: undefined }) as never)
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.panes', () => ({ value: [] }))
  const owed: Record<string, unknown>[] = []
  on('process.run', (_$, e) => {
    const argv = [...e.argv]
    w.calls.push(argv)
    const verb = argv[0]?.endsWith('/compound') ? argv[1] : argv[0]
    const done = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    if (verb === 'log') {
      const event = JSON.parse(e.init?.stdin ?? '{}') as Record<string, unknown>
      w.logged.push(event)
      if (event.type === 'capture') owed.push({ ts: '2026-10-05T12:00:00Z', session: `learn-session-${n}`, ...event })
      return done('')
    }
    if (verb === 'list') return done(LESSONS)
    if (verb === 'check') return done('{"hits":[],"guards":0,"tools":[]}')
    if (verb === 'events') return done(argv.includes('--unsettled') && argv.includes('--session') ? JSON.stringify(owed) : '[]')
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
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => {
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
  mock.clock(on, { now: T0 })
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
  expect(w.prompts.length).toBe(asked + 1)
  expect(of(w, 'capture').map(e => [e.failed, e.fixed])).toEqual([['./deploy.sh', './deploy.sh --target staging']])
  expect(JSON.stringify(fixed.context ?? [])).toContain('./deploy.sh --target staging')
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
  mock.clock(on, { now: T0 })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.tool = command => (command.startsWith('ls ') ? NO_MATCH : undefined)
  for (let i = 0; i < 7; i += 1) {
    w.judge = async () => RECALLED
    await $.tool.call({ tool: 'Bash', command: `ls *.nope${i}` })
    w.judge = async () => NO_FIX
    await $.tool.call({ tool: 'Bash', command: `echo ${i}` })
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
  mock.clock(on, { now: T0 })
  let down = true
  w.tool = command => (command === CURL && down ? TIMED_OUT : undefined)
  await $.tool.call({ tool: 'Bash', command: CURL })
  w.judge = async () => NO_FIX
  await $.tool.call({ tool: 'Bash', command: 'git status --short' })
  down = false
  const asked = w.prompts.length
  await $.tool.call({ tool: 'Bash', command: CURL })
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
  mock.clock(on, { now: T0 })
  const JQ = "jq -r '.version' package.json"
  let installed = false
  w.tool = command => (command === JQ && !installed ? { text: 'Exit code 127\n(eval):1: command not found: jq', isError: true } : undefined)
  await $.tool.call({ tool: 'Bash', command: JQ })
  // A file written, a file read, and the install: the read is not listed.
  await $.tool.call({ tool: 'Write', file_path: '/work/.tool-versions', content: 'jq 1.7' } as never)
  await $.tool.call({ tool: 'Read', file_path: '/work/package.json' } as never)
  w.judge = async () => NO_FIX
  await $.tool.call({ tool: 'Bash', command: 'brew install jq' })
  installed = true
  const asked = w.prompts.length
  w.judge = async () => fix('command not found: jq')
  await $.tool.call({ tool: 'Bash', command: JQ })
  expect(w.prompts.length).toBe(asked + 1)
  const prompt = w.prompts[asked]!
  const between = prompt.slice(prompt.indexOf('CALLS BETWEEN THE TWO, in'), prompt.indexOf('LATER SUCCESSFUL CALL:'))
  expect(between.split('\n').slice(1, 3)).toEqual(['Write: {"file_path":"/work/.tool-versions","content":"jq 1.7"}', 'Bash: brew install jq'])
  expect(between).not.toContain('Read')
  expect(of(w, 'capture').map(e => [e.failed, e.fixed])).toEqual([[JQ, JQ]])
})
