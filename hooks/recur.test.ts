import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'
import { captureContext, resembles, ruleRefusal } from './render'
import { parseMet } from './store'

// A FAILURE MET BEFORE IS A LESSON OWED, AND NO MODEL IS ASKED. When a call fails and no
// lesson describes it, the mod asks the CLI whether the failure's signature was met in an
// earlier session (`compound met`). If it was, and no lesson was owed for it before, the
// first call of the tool to pass afterwards is captured as it stands: `why: recurred`. The
// judge is asked only about a failure met for the first time. A refusal that is a rule of
// the harness, met before, is such a failure too.

const CLI = '/opt/compound/bin/compound'
const NO_FIX = JSON.stringify({ same_goal: false, call_mistake: false, recurs: false, evidence: '', verdict: 'NONE', reason: 'the next step of the work' })
const ISOLATED = 'This agent is isolated in the worktree /w/.claude/worktrees/agent-a1 but this command names git in a form too complex to verify'
const DENIED = "The user doesn't want to proceed with this tool use. The tool use was rejected."

type Met = { sig: string | null; sessions: number; captured: boolean }
// `settle`: lets the fix judge, which runs behind the call, finish.
type World = { logged: Record<string, unknown>[]; asked: string[]; met: (error: string) => Met; metCalls: string[]; fail: (command: string) => string | undefined; settle: () => Promise<void> }

let worlds = 0

function world(on: On): World {
  worlds += 1
  const n = worlds
  const w: World = { logged: [], asked: [], met: () => ({ sig: null, sessions: 0, captured: false }), metCalls: [], fail: () => undefined, settle: async () => undefined }
  const claims = new Set<string>()
  const owed: Record<string, unknown>[] = []
  mock.env(on, { HOME: '/home/me', COMPOUND_HOME: '/home/me/compound', COMPOUND_PROMPT_MIN_CHARS: '100000' })
  const clock = mock.clock(on, { now: 1_800_000_000_000 })
  w.settle = () => clock.settle()
  on('session.id', () => ({ value: `recur-session-${n}` }))
  on('session.root', () => ({ value: `/work/recur-${n}` }))
  on('session.cwd', () => ({ value: `/work/recur-${n}` }))
  on('session.repo', () => ({ value: null }))
  on('session.messages', () => ({ value: [] }))
  on('fs.exists', () => ({ value: true }))
  on('command.register', () => ({ value: undefined }) as never)
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.panes', () => ({ value: [] }))
  on('process.run', (_$, e) => {
    const argv = [...e.argv]
    const done = (stdout: string, exitCode = 0) => ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    if (argv[0] === '/bin/sh') {
      if (argv[2]?.includes('find')) return done('')
      const key = argv.slice(4).join('/')
      if (claims.has(key)) return done('', 1)
      claims.add(key)
      return done('')
    }
    const verb = argv[1]
    if (verb === 'log') {
      const event = JSON.parse(e.init?.stdin ?? '{}') as Record<string, unknown>
      w.logged.push(event)
      if (event.type === 'capture') owed.push({ ts: '2026-10-11T12:00:00Z', session: `recur-session-${n}`, ...event })
      return done('')
    }
    if (verb === 'met') {
      const asked = JSON.parse(e.init?.stdin ?? '{}') as { error?: string }
      w.metCalls.push(asked.error ?? '')
      return done(JSON.stringify(w.met(asked.error ?? '')))
    }
    if (verb === 'check') return done('{"hits":[],"guards":0,"tools":[]}')
    if (verb === 'events') return done(argv.includes('--unsettled') ? JSON.stringify(owed) : '[]')
    if (verb === 'list') return done('[]')
    if (verb === 'evidence') return done(argv[2] === 'list' ? '[]' : '{"noted":[]}')
    return done('')
  })
  on('model.complete', (_$, e) => {
    w.asked.push(String((e as unknown as { prompt?: unknown }).prompt ?? ''))
    return { value: { isAnswered: true as const, text: NO_FIX, usage: { input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 } } }
  })
  on('tool.call', (_$, e) => {
    const command = String((e as unknown as { command?: unknown }).command ?? '')
    const error = w.fail(command)
    return (error === undefined ? { result: {}, text: 'ok' } : { result: {}, text: error, isError: true }) as never
  })
  on('classic.Stop', () => ({}) as never)
  on('prompt.submit', (_$, e) => ({ text: e.text, ...(e.context === undefined ? {} : { context: e.context }) }))
  return w
}

const captures = (w: World) => w.logged.filter(e => e.type === 'capture')
const NO_TIMEOUT = 'Exit code 127\n(eval):1: command not found: timeout'

// ---- the pure halves --------------------------------------------------------------------

test('the CLI\'s answer is read as data, and a failure with no signature is no answer', () => {
  expect(parseMet('{"sig":"command not found: timeout","sessions":2,"captured":false}')).toEqual({ sig: 'command not found: timeout', sessions: 2, captured: false })
  expect(parseMet('{"sig":null,"sessions":0,"captured":false}')).toBe(undefined)
  expect(parseMet('{"sig":"two\\nlines","sessions":3,"captured":false}')).toBe(undefined)
  expect(parseMet('{"sig":"x not found","sessions":"many","captured":"yes"}')).toEqual({ sig: 'x not found', sessions: 0, captured: false })
  expect(parseMet('compound: error')).toBe(undefined)
})

test('the refusals that are rules are the harness\'s and a safety check\'s', () => {
  expect(['harness', 'safety', 'permission', 'hook', undefined].map(ruleRefusal)).toEqual([true, true, false, false, false])
})

test('the message beside a fix says the failure came back, and how often', () => {
  const pair = { failed: 'timeout 5 make', error: NO_TIMEOUT, fixed: 'gtimeout 5 make', id: 'ab12cd34' }
  expect(captureContext({ ...pair, met: 3 }, CLI).split('\n')[0]).toBe(
    '[compound] This failure was met before, in 3 earlier sessions, and no recorded lesson describes it: each of them worked it out again, as this one just did. This session now owes the lesson, so the next one does not.',
  )
  expect(captureContext({ ...pair, met: 1 }, CLI)).toContain('in 1 earlier session,')
  expect(captureContext(pair, CLI).split('\n')[0]).toBe('[compound] A failed call was just fixed. This session now owes a lesson, so the next session does not repeat the failure.')
})

test('a passing call that shares a word of substance with the failed one looks like another go at it', () => {
  const yes: [string, string][] = [
    ['./build.sh', './build.sh --profile dev'],
    ['timeout 5 make test', 'gtimeout 5 make test'],
    ['cd /w && git -C "$(pwd)" status', 'git status'],
    ['python3 scripts/check.py --all', '/opt/homebrew/bin/python3.12 scripts/check.py --all'],
    ['S=/tmp/x; grep -rn TODO --include=*.py src', "grep -rn TODO --include='*.py' src"],
  ]
  for (const [failed, passed] of yes) expect(resembles(failed, passed)).toBe(true)
  const no: [string, string][] = [
    ['./build.sh', 'echo alpha'],
    ['cd /work/project && timeout 5 make', 'cd /work/project && ls -la'],
    ['timeout 5 make test', 'git status'],
    ['export X=1; ./deploy.sh', 'export X=1; cat notes.txt'],
    ['', 'ls'],
  ]
  for (const [failed, passed] of no) expect(resembles(failed, passed)).toBe(false)
})

// ---- through the hooks ------------------------------------------------------------------

test('a failure an earlier session met is captured at the next call of the tool that passes, and no model is asked about the fix', async ($, on) => {
  const w = world(on)
  w.fail = command => (command.startsWith('timeout ') ? NO_TIMEOUT : undefined)
  w.met = () => ({ sig: 'command not found: timeout', sessions: 2, captured: false })
  await $.tool.call({ tool: 'Bash', command: 'timeout 5 make test' })
  expect(w.metCalls.length).toBe(1)
  // Another tool's call is not an attempt at it.
  await $.tool.call({ tool: 'Write', file_path: '/work/x', content: 'y' } as never)
  expect(captures(w)).toEqual([])
  const fixed = await $.tool.call({ tool: 'Bash', command: 'gtimeout 5 make test' })
  expect(w.asked).toEqual([])
  const row = captures(w)[0]!
  expect([row.failed, row.fixed, row.why, row.sig, row.met, row.ms]).toEqual(['timeout 5 make test', 'gtimeout 5 make test', 'recurred', 'command not found: timeout', 2, 0])
  expect(JSON.stringify(fixed.context ?? [])).toContain('This failure was met before, in 2 earlier sessions')
  // It is owed: the stop is refused for it.
  const stop = await $.classic.Stop({ stop_hook_active: false } as never)
  expect(String((stop as { block?: unknown }).block ?? '')).toContain('This session owes a lesson')
  // And it was the one fix: a later pass captures nothing more.
  await $.tool.call({ tool: 'Bash', command: 'gtimeout 9 make docs' })
  expect(captures(w).length).toBe(1)
})

test('a failure met for the first time goes to the judge as before', async ($, on) => {
  const w = world(on)
  w.fail = command => (command.startsWith('timeout ') ? NO_TIMEOUT : undefined)
  w.met = () => ({ sig: 'command not found: timeout', sessions: 0, captured: false })
  await $.tool.call({ tool: 'Bash', command: 'timeout 5 make test' })
  await $.tool.call({ tool: 'Bash', command: 'gtimeout 5 make test' })
  await w.settle()
  expect(w.asked.length).toBe(1)
  expect(captures(w)).toEqual([])
})

test('a failure a lesson was owed for once already is not owed again', async ($, on) => {
  const w = world(on)
  w.fail = command => (command.startsWith('timeout ') ? NO_TIMEOUT : undefined)
  w.met = () => ({ sig: 'command not found: timeout', sessions: 4, captured: true })
  await $.tool.call({ tool: 'Bash', command: 'timeout 5 make test' })
  await $.tool.call({ tool: 'Bash', command: 'gtimeout 5 make test' })
  await w.settle()
  expect(captures(w)).toEqual([])
  expect(w.asked.length).toBe(1)
})

test('the failed call sent again unchanged and passing is a retry, met before or not', async ($, on) => {
  const w = world(on)
  let down = true
  w.fail = command => (command.startsWith('curl ') && down ? 'Exit code 6\ncurl: (6) Could not resolve host: registry.example' : undefined)
  w.met = () => ({ sig: 'curl: (N) Could not resolve host: registry.example', sessions: 3, captured: false })
  await $.tool.call({ tool: 'Bash', command: 'curl -fsS https://registry.example/x' })
  down = false
  await $.tool.call({ tool: 'Bash', command: 'curl -fsS https://registry.example/x' })
  expect(captures(w)).toEqual([])
  expect(w.asked).toEqual([])
})

test('a refusal that is a rule of the harness, met in an earlier session, is a failure with a lesson to it', async ($, on) => {
  const w = world(on)
  w.fail = command => (command.includes('git -C') ? ISOLATED : undefined)
  w.met = () => ({ sig: 'This agent is isolated in the worktree <PATH> but this command names git in a form too complex to verify', sessions: 5, captured: false })
  await $.tool.call({ tool: 'Bash', command: 'cd /w && git -C "$(pwd)" status' })
  expect(w.metCalls.length).toBe(1)
  await $.tool.call({ tool: 'Bash', command: 'git status' })
  const row = captures(w)[0]!
  expect([row.failed, row.fixed, row.why, row.met]).toEqual(['cd /w && git -C "$(pwd)" status', 'git status', 'recurred', 5])
  expect(w.asked).toEqual([])
})

test('the same refusal met for the first time is left alone, and so is a permission the user withheld', async ($, on) => {
  const w = world(on)
  w.fail = command => (command.includes('git -C') ? ISOLATED : command.startsWith('rm ') ? DENIED : undefined)
  w.met = () => ({ sig: 'This agent is isolated in the worktree <PATH> but this command names git in a form too complex to verify', sessions: 0, captured: false })
  await $.tool.call({ tool: 'Bash', command: 'cd /w && git -C "$(pwd)" status' })
  await $.tool.call({ tool: 'Bash', command: 'git status' })
  // The meeting was written down by the CLI (so the next session's is the second), and nothing was held.
  expect(w.metCalls.length).toBe(1)
  expect(captures(w)).toEqual([])
  expect(w.asked).toEqual([])
  await $.tool.call({ tool: 'Bash', command: 'rm -rf build' })
  expect(w.metCalls.length).toBe(1)
})

test('calls that are not another go at it are passed over, and the one that is gets quoted as what worked', async ($, on) => {
  const w = world(on)
  w.fail = command => (command === './build.sh' ? 'Exit code 2\nbuild.sh: error: a profile is required' : undefined)
  w.met = () => ({ sig: 'build.sh: error: a profile is required', sessions: 1, captured: false })
  await $.tool.call({ tool: 'Bash', command: './build.sh' })
  for (const word of ['alpha', 'beta', 'gamma']) await $.tool.call({ tool: 'Bash', command: `echo ${word}` })
  expect(captures(w)).toEqual([])
  await $.tool.call({ tool: 'Bash', command: './build.sh --profile dev' })
  expect(captures(w).map(e => [e.failed, e.fixed, e.why])).toEqual([['./build.sh', './build.sh --profile dev', 'recurred']])
  expect(w.asked).toEqual([])
})

test('with no later call that looks like it, the lesson is still owed at the stop', async ($, on) => {
  const w = world(on)
  w.fail = command => (command.includes('git -C') ? ISOLATED : undefined)
  w.met = () => ({ sig: 'This agent is isolated in the worktree <PATH> but this command names git', sessions: 2, captured: false })
  // The session did the job with another tool: no Bash call ever repeats it. The stop finds it held.
  await $.tool.call({ tool: 'Bash', command: 'cd /w && git -C "$(pwd)" log' })
  await $.tool.call({ tool: 'Write', file_path: '/w/notes.md', content: 'x' } as never)
  await $.tool.call({ tool: 'Bash', command: 'ls -la' })
  expect(captures(w)).toEqual([])
  const stop = await $.classic.Stop({ stop_hook_active: false } as never)
  const row = captures(w)[0]!
  expect([row.failed, row.why, row.met]).toEqual(['cd /w && git -C "$(pwd)" log', 'recurred', 2])
  expect(String(row.fixed)).toContain('no later call of Bash repeated it; what ran next: Write')
  expect(String((stop as { block?: unknown }).block ?? '')).toContain('This session owes a lesson')
})

test('five passes that are not another go at it use up the attempts: the fifth is quoted, and the lesson is owed then', async ($, on) => {
  const v = world(on)
  v.fail = command => (command.startsWith('timeout ') ? NO_TIMEOUT : undefined)
  v.met = () => ({ sig: 'command not found: timeout', sessions: 1, captured: false })
  await $.tool.call({ tool: 'Bash', command: 'timeout 5 make test' })
  for (const n of [1, 2, 3, 4]) await $.tool.call({ tool: 'Bash', command: `ls dir${n}` })
  expect(captures(v)).toEqual([])
  await $.tool.call({ tool: 'Bash', command: 'ls dir5' })
  expect(captures(v).map(e => [e.failed, e.fixed])).toEqual([['timeout 5 make test', 'ls dir5']])
})
