import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'
import { refusal, sameCall } from './render'
import { boardFrom, eventWord } from './view'

// What the mod logs so that `compound report` can count it: the call that follows a
// refusal. The world beneath the mod is the test's: the CLI's replies by subcommand, and
// what `compound log` was handed. And what the report showed to be wrong: a refusal of the
// harness that was taken for a failed call.

type World = { logged: Record<string, unknown>[]; check: string }

let worlds = 0

function world(on: On, env: Record<string, string> = {}): World {
  worlds += 1
  const n = worlds
  const w: World = { logged: [], check: '{"hits":[],"guards":1,"tools":["Bash"]}' }
  mock.env(on, { HOME: '/home/me', COMPOUND_HOME: '/home/me/compound', COMPOUND_PROMPT_MIN_CHARS: '100000', COMPOUND_QUIET: '1', ...env })
  on('session.id', () => ({ value: `measure-session-${n}` }))
  on('session.root', () => ({ value: `/work/measure-${n}` }))
  on('session.repo', () => ({ value: null }))
  on('session.messages', () => ({ value: [] }))
  on('fs.exists', () => ({ value: true }))
  on('command.register', () => ({ value: undefined }) as never)
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.panes', () => ({ value: [] }))
  on('process.run', (_$, e) => {
    const argv = [...e.argv]
    const verb = argv[0]?.endsWith('/compound') ? argv[1] : argv[0]
    const done = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    if (verb === 'log') {
      w.logged.push(JSON.parse(e.init?.stdin ?? '{}') as Record<string, unknown>)
      return done('')
    }
    if (verb === 'list') return done('[]')
    if (verb === 'check') return done(w.check)
    if (verb === 'events') return done('[]')
    return done('')
  })
  on('model.complete', () => {
    return { value: { isAnswered: true as const, text: '{"name":null}', usage: { input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 } } }
  })
  on('tool.call', () => ({ result: {}, text: 'ok' }) as never)
  on('classic.Stop', () => ({}) as never)
  on('prompt.submit', (_$, e) => ({ text: e.text, ...(e.context === undefined ? {} : { context: e.context }) }))
  return w
}

const hit = (name: string) => JSON.stringify({ hits: [{ name, level: 'user', path: `/u/l/${name}`, text: 'Print it with printf.' }], guards: 1, tools: ['Bash'] })
const of = (w: World, type: string) => w.logged.filter(e => e.type === type)

test('the call sent after a refusal is the same call when its text is, whatever the space around it', async () => {
  expect(sameCall('echo ====', 'echo ====')).toBe(true)
  expect(sameCall('echo ====', ' echo ====\n')).toBe(true)
  expect(sameCall('echo ====', "printf '%s\\n' ====")).toBe(false)
  expect(sameCall('echo ====', 'echo  ====')).toBe(false)
})

test('a compound command held for approval of one of its parts was refused, not run: it is no failure to recall a lesson for', async () => {
  // The harness's wording, as two recalls in the event log carry it.
  const held = 'This Bash command contains multiple operations. The following part requires approval: tail -5; git log -S"def cmd_memo" --oneline -- bin/compound'
  expect(refusal(held)).toBe('permission')
  // A command that ran and printed the same words did fail.
  expect(refusal(`Exit code 1\n${held}`)).toBe(undefined)
})

test('a retry event has a word, and the pane\'s timeline leaves it out as it leaves out a verdict', async () => {
  expect(eventWord('retry')).toBe('retried')
  const status = JSON.stringify({ ok: true, health: [], store: {}, lessons: [], recent: [], open: {} })
  const rows = JSON.stringify([
    { ts: '2026-10-03T12:00:00Z', type: 'guard', lesson: 'no-marker-echo', watched: true },
    { ts: '2026-10-03T12:00:05Z', type: 'retry', lessons: ['no-marker-echo'], tool: 'Bash', same: false, text: 'printf x' },
  ])
  expect(boardFrom(status, rows, 's1', 1_800_000_000_000)!.recent.map(r => r.type)).toEqual(['guard'])
})

test('through the hooks: a refusal is watched, and a different call that follows it is logged once as one', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: 1_800_000_000_000 })
  w.check = hit('no-marker-echo')
  const refused = await $.tool.call({ tool: 'Bash', command: 'echo ====' } as never)
  expect(refused.deny).toContain('lesson=no-marker-echo')
  expect(of(w, 'guard').map(e => [e.lesson, e.tool, e.text, e.watched])).toEqual([['no-marker-echo', 'Bash', 'echo ====', true]])
  expect(of(w, 'retry')).toEqual([])
  w.check = '{"hits":[],"guards":1,"tools":["Bash"]}'
  const ran = await $.tool.call({ tool: 'Bash', command: "printf '%s\\n' ====" } as never)
  expect(ran.deny).toBe(undefined)
  expect(of(w, 'retry')).toEqual([{ type: 'retry', lessons: ['no-marker-echo'], tool: 'Bash', same: false, text: "printf '%s\\n' ====" }])
  // Only the first call that follows is the session's answer to the refusal.
  await $.tool.call({ tool: 'Bash', command: 'ls' } as never)
  expect(of(w, 'retry').length).toBe(1)
})

test('through the hooks: the refused call sent again runs, and is logged as the same call', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: 1_800_000_000_000 })
  w.check = hit('no-marker-echo')
  expect((await $.tool.call({ tool: 'Bash', command: 'echo ====' } as never)).deny).toContain('lesson=no-marker-echo')
  const again = await $.tool.call({ tool: 'Bash', command: 'echo ====' } as never)
  expect(again.deny).toBe(undefined)
  expect(of(w, 'retry')).toEqual([{ type: 'retry', lessons: ['no-marker-echo'], tool: 'Bash', same: true, text: 'echo ====' }])
  expect(of(w, 'guard').length).toBe(1)
})

test('through the hooks: a call of another tool, or of the CLI to read the lesson, is not the call that follows', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: 1_800_000_000_000 })
  w.check = hit('no-marker-echo')
  await $.tool.call({ tool: 'Bash', command: 'echo ====' } as never)
  w.check = '{"hits":[],"guards":1,"tools":["Bash"]}'
  await $.tool.call({ tool: 'Bash', command: 'compound show no-marker-echo' } as never)
  await $.tool.call({ tool: 'Write', file_path: '/work/a.txt', content: 'x' } as never)
  expect(of(w, 'retry')).toEqual([])
  await $.tool.call({ tool: 'Bash', command: 'printf x' } as never)
  expect(of(w, 'retry').map(e => e.same)).toEqual([false])
})

test('through the hooks: a call that follows a refusal and is refused by another guard is logged before it is denied', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: 1_800_000_000_000 })
  w.check = hit('no-marker-echo')
  await $.tool.call({ tool: 'Bash', command: 'echo ====' } as never)
  w.check = hit('no-timeout')
  const second = await $.tool.call({ tool: 'Bash', command: 'timeout 5 ls' } as never)
  expect(second.deny).toContain('lesson=no-timeout')
  expect(of(w, 'retry')).toEqual([{ type: 'retry', lessons: ['no-marker-echo'], tool: 'Bash', same: false, text: 'timeout 5 ls' }])
  // The second refusal is watched in its turn.
  w.check = '{"hits":[],"guards":1,"tools":["Bash"]}'
  await $.tool.call({ tool: 'Bash', command: 'ls' } as never)
  expect(of(w, 'retry').map(e => e.lessons)).toEqual([['no-marker-echo'], ['no-timeout']])
})
