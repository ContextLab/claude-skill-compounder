import { expect, mock, test, type TestBody } from 'claude-code/testing'
import type { On } from 'claude-code'
import { BUSY, ERROR, FRAME_MS, FRAMES, FRESH_MS, GONE_MS, HINT, NOTES, OWED, WEAK } from './view'

// The band and the pane, drawn through the mod's own hooks on every surface that draws
// them. The world beneath the mod is the test's: the CLI's replies, the judge's answer,
// the clock. What is checked is the tree the hooks hand a surface, never a surface's paint.

// What the test draws where the engine's own drawing would be: seeing it means the mod drew nothing.
const BENEATH = 'drawn beneath the mod'
const SURFACES = ['terminal', 'desktop'] as const
const T0 = 1_800_000_000_000
const PROMPT = 'Write the release notes for version 2.1 of this project in the format this project uses, and print them here.'

const ITEMS = JSON.stringify([
  { kind: 'lesson', name: 'release-notes-format', level: 'project', description: 'Use when writing release notes.', path: '/p/l/release-notes-format', match: [] },
])
const STATUS = JSON.stringify({
  ok: true,
  totals: { reused: 3, guarded: 1, recalled: 1, recorded: 5, since: '2026-09-12T10:00:00Z' },
  health: [{ check: 'python', status: 'PASS', detail: '3.12.1' }],
  store: { project: { lessons: 1, skills: 0, guards: 0 }, user: { lessons: 0, skills: 0, guards: 0 }, general: { lessons: 0, skills: 2, guards: 0 } },
  lessons: [{ name: 'release-notes-format', level: 'project', kind: 'lesson', guard: false, reuse: 3, guard_hits: 0, recall: 1, flag: '' }],
  recent: [],
  open: { ineffective: [], unsettled: [{ id: 'abc123', age: '2h', project: '/work/alpha', failed: './x', fixed: './x --y' }], candidates: [], skips: [], errors: [] },
})
const EVENTS = JSON.stringify([{ ts: '2026-10-03T12:00:00Z', type: 'guard', lesson: 'no-marker-echo' }])

// `owed` is what the CLI answers `events --unsettled --session S`: the log's own account of
// what the session owes. The world keeps it as the log would: a capture or an ineffective
// recall the mod logs is owed from then on, until the test says the log holds its settlement.
type World = { calls: string[][]; logged: Record<string, unknown>[]; judge: () => Promise<string>; check: string; events: string; owed: Record<string, unknown>[]; statuses: (string | undefined)[]; opened: string[]; isLost: boolean }

// Everything the mod reaches for through `$`, answered from memory: the CLI by its
// subcommand, the judge by `world.judge`, and a marker where the engine's own band would be.
function world(on: On, env: Record<string, string> = {}): World {
  const w: World = { calls: [], logged: [], judge: async () => '{"substantial":true,"items":["release-notes-format"],"requests":[]}', check: '{"hits":[],"guards":1}', events: EVENTS, owed: [], statuses: [], opened: [], isLost: false }
  mock.env(on, { HOME: '/home/me', COMPOUND_HOME: '/home/me/compound', ...env })
  on('session.id', () => {
    if (w.isLost) throw new Error('the session is gone')
    return { value: 'session-under-test' }
  })
  on('session.root', () => ({ value: '/work/alpha' }))
  on('session.repo', () => ({ value: null }))
  on('session.messages', () => ({ value: [] }))
  on('fs.exists', () => ({ value: true }))
  on('command.register', () => ({ value: undefined }) as never)
  on('ui.status', (_$, e) => {
    w.statuses.push((e as unknown as { text?: string }).text)
    return { value: undefined }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('ui.open', (_$, e) => {
    w.opened.push(e.id)
    return { value: { isPlaced: true as const } }
  })
  on('ui.panes', () => ({ value: [{ id: 'compound', title: 'compound', isShown: true, isFocused: false, isPlaced: true }] }))
  on('process.run', (_$, e) => {
    const argv = [...e.argv]
    w.calls.push(argv)
    const verb = argv[0]?.endsWith('/compound') ? argv[1] : argv[0]
    const done = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    if (verb === 'log') {
      const event = JSON.parse(e.init?.stdin ?? '{}') as Record<string, unknown>
      w.logged.push(event)
      if (event.type === 'capture' || (event.type === 'recall' && event.ineffective === true)) {
        w.owed.push({ ts: '2026-10-03T12:00:00Z', session: 'session-under-test', ...event })
      }
      return done('')
    }
    if (verb === 'list') return done(ITEMS)
    if (verb === 'status') return done(STATUS)
    if (verb === 'events') return done(argv.includes('--unsettled') ? (argv.includes('--session') ? JSON.stringify(w.owed) : '[]') : w.events)
    if (verb === 'find') return done('{"words":[],"items":[],"prompts":[],"surfer":"ok"}')
    if (verb === 'check') return done(w.check)
    return done('')
  })
  on('model.complete', async () => ({ value: { isAnswered: true as const, text: await w.judge(), usage: { input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 } } }))
  // A Bash call fails unless it carries its flag; every other call succeeds.
  on('tool.call', (_$, e) => {
    const command = String((e as unknown as { command?: unknown }).command ?? '')
    const failed = command === './deploy.sh'
    return (failed ? { result: {}, text: 'deploy.sh: error: a target is required', isError: true } : { result: {}, text: 'ok' }) as never
  })
  on('classic.Stop', () => ({}) as never)
  on('prompt.submit', (_$, e) => ({ text: e.text, ...(e.context === undefined ? {} : { context: e.context }) }))
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, null, BENEATH) as never
  })
  on('ui.render', { component: 'Pane' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, null, BENEATH) as never
  })
  return w
}

const BAND = { hasSurvey: false, isWorking: true, maxRows: 10, bodyColumns: 95, scroll: { offset: 0, bodyRows: 10 }, view: {} }
const PANE = { title: 'compound', isFocused: false, bodyColumns: 60, placement: 'inline' as const, scroll: { offset: 0, bodyRows: 30 }, view: {} }

test('the band spins while the reuse check runs, shows what it found, fades, and then draws nothing', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  // The judge answers half a second in: until then the check is in flight.
  w.judge = async () => {
    await clock.sleep(500)
    return '{"substantial":true,"items":["release-notes-format"],"requests":[]}'
  }
  for (const surface of SURFACES) {
    w.logged.length = 0
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'AbovePrompt', props: BAND, viewport: { columns: 100, rows: 40 } })
    // Nothing has happened: the mod draws nothing and the engine's band stands.
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()

    const submitted = $.prompt.submit({ text: `${PROMPT} (${surface})`, wait: false, origin: { kind: 'composer' } })
    await clock.settle()
    expect((await ui.find({ type: 'Text', text: BUSY.reuse }))?.text).toBe(BUSY.reuse)
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeUndefined()
    const first = (await ui.findAll({ type: 'Text' }))[0]!
    expect((FRAMES as readonly string[]).includes(first.text.trim())).toBe(true)
    expect(first.props.color).toBe('claude')

    // One frame later the spinner has turned, with no act of the test's but the clock.
    await clock.advance(FRAME_MS)
    const second = (await ui.findAll({ type: 'Text' }))[0]!
    expect((FRAMES as readonly string[]).includes(second.text.trim())).toBe(true)
    expect(second.text).not.toBe(first.text)

    await clock.advance(500)
    await submitted
    const found = await ui.find({ type: 'Text', text: NOTES.reuse.label })
    expect(found?.props.color).toBe(NOTES.reuse.color)
    // The result names what was found, and the session's first result carries the greeting.
    expect(await ui.find({ type: 'Text', text: 'release-notes-format' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /lesson or skill|reusable/ })).toBeUndefined()
    expect((await ui.find({ type: 'Text', text: '1 lesson (0 guards) ready' })) !== undefined).toBe(surface === SURFACES[0])
    expect(w.statuses[w.statuses.length - 1]).toBe('reuse release-notes-format')
    expect((await ui.findAll({ type: 'Text' }))[0]!.text).toBe(`${NOTES.reuse.glyph} `)
    expect(await ui.find({ type: 'Text', text: BUSY.reuse })).toBeUndefined()
    expect(w.logged.map(e => e.type), JSON.stringify(w.logged)).toEqual(['reuse'])

    // It dims, and then it is gone and the engine's band stands again.
    await clock.advance(GONE_MS - 1500)
    expect((await ui.find({ type: 'Text', text: NOTES.reuse.label }))?.props.dimColor).toBe(true)
    await clock.advance(2000)
    expect(await ui.find({ type: 'Text', text: NOTES.reuse.label })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()

    // Nothing animates now: an hour passes and no state is written, no CLI is called.
    const calls = w.calls.length
    await clock.advance(3_600_000)
    expect(w.calls.length).toBe(calls)
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
    await ui.unmount()
  }
})

const hit = (name: string) => JSON.stringify({ hits: [{ name, level: 'project', path: `/p/l/${name}`, text: 'Print it with printf.' }], guards: 1 })
const FIX = JSON.stringify({ same_goal: true, call_mistake: true, recurs: true, evidence: 'a target is required', verdict: 'FIX' })

test('a guard that stops a call is shown with the lesson\'s name, in the guard\'s colour', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  for (const surface of SURFACES) {
    // A guard stops a call once a session per lesson: each surface meets a lesson of its own.
    w.check = hit(`no-marker-echo-${surface}`)
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'AbovePrompt', props: BAND })
    const ran = await $.tool.call({ tool: 'Bash', command: 'echo GUARDED_MARKER' })
    expect(ran.deny).toContain(`lesson=no-marker-echo-${surface}`)
    expect((await ui.find({ type: 'Text', text: NOTES.guard.label }))?.props.color).toBe(NOTES.guard.color)
    expect(await ui.find({ type: 'Text', text: `no-marker-echo-${surface}` })).toBeDefined()
    // And with the call it stopped.
    expect((await ui.find({ type: 'Text', text: 'echo GUARDED_MARKER' }))?.props.dimColor).toBe(true)
    expect((await ui.findAll({ type: 'Text' }))[0]!.text).toBe(`${NOTES.guard.glyph} `)
    await ui.unmount()
  }
})

test('a failure, its fix, the lesson owed and the lesson recorded walk the track, and owed stays until settled', async ($, on) => {
  const surface = 'terminal'
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  const clock = mock.clock(on, { now: T0 })
  w.judge = async () => '{"name":null}'
  const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')

  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(await shown()).toContain('watching for the fix   ● failed → ○ fixed → ○ owed → ○ recorded')

  // The judge is asked whether the next success is the fix: the spinner says so.
  w.judge = async () => {
    await clock.sleep(300)
    return FIX
  }
  const fixing = $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  await clock.settle()
  expect(await shown()).toContain(`${BUSY.fix}   ✓ failed → ● fixed → ○ owed → ○ recorded`)
  await clock.advance(300)
  await fixing
  // The lesson owed is named by its fix; at the band's 95 columns the track keeps its glyphs.
  expect(await shown()).toBe(`${OWED.glyph} compound lesson owed · ./deploy.sh --target staging   ✓ ✓ ● owed ○`)
  expect(w.statuses[w.statuses.length - 1]).toBe('lesson owed: ./deploy.sh --target staging')
  expect((await ui.find({ type: 'Text', text: '● owed' }))?.props).toEqual({ color: 'warning', bold: true })
  expect(w.logged.map(e => e.type)).toEqual(['capture'])

  // Owed stays, and nothing animates while it does.
  await clock.advance(3_600_000)
  expect(await shown()).toContain('lesson owed')

  // The session records the lesson with the CLI: the event it wrote settles the track.
  w.events = JSON.stringify([{ ts: '2026-10-03T12:05:00Z', type: 'learn', lesson: 'deploy-needs-target', update: false, session: 'session-under-test' }])
  await $.tool.call({ tool: 'Bash', command: '/opt/compound/bin/compound add --name deploy-needs-target --when "Use when deploying."' })
  expect(await shown()).toBe(`${NOTES.recorded.glyph} compound lesson recorded · deploy-needs-target   ✓ failed → ✓ fixed → ✓ owed → ✔ recorded`)
  expect((await ui.find({ type: 'Text', text: '✔ recorded' }))?.props).toEqual({ color: 'success', bold: true })
  await clock.advance(GONE_MS)
  expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
  await ui.unmount()
})

test('COMPOUND_QUIET=1 turns the band off and leaves the moments, the status entry and the pane', async ($, on) => {
  const w = world(on, { COMPOUND_QUIET: '1' })
  mock.clock(on, { now: T0 })
  for (const surface of SURFACES) {
    w.logged.length = 0
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'AbovePrompt', props: BAND })
    await $.prompt.submit({ text: `${PROMPT} (${surface})`, wait: false, origin: { kind: 'composer' } })
    expect(w.logged.map(e => e.type)).toEqual(['reuse'])
    expect(await ui.find({ type: 'Text', text: NOTES.reuse.label })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
    await ui.unmount()
    const pane = await $.ui.mount({ plugin: 'compound', surface, component: 'Pane', requestId: 'compound', props: PANE })
    expect(await pane.find({ type: 'Text', text: BENEATH })).toBeUndefined()
    await pane.unmount()
  }
})

const NOTHING = '{"substantial":false,"items":[],"requests":[]}'

test('the first reuse check of a session that finds nothing greets with the store\'s counts; the next closes dim and goes', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  w.judge = async () => {
    await clock.sleep(500)
    return NOTHING
  }
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND, viewport: { columns: 100, rows: 40 } })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  const first = $.prompt.submit({ text: `${PROMPT} (first)`, wait: false, origin: { kind: 'composer' } })
  await clock.settle()
  expect(await shown()).toContain(BUSY.reuse)
  const calls = w.calls.length
  await clock.advance(500)
  await first
  // The counts are the listing's that the check had already read: no call was made for them.
  expect(await shown()).toBe(`${NOTES.ready.glyph} compound ready · 1 lesson (0 guards)  ${HINT}`)
  expect(w.calls.slice(calls).filter(c => c[1] === 'list' || c[1] === 'status')).toEqual([])
  expect(w.logged.map(e => e.type)).toEqual([])
  await clock.advance(GONE_MS)
  expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()

  // The next check that finds nothing: no blank row after the spinner, a dim line for three seconds.
  const second = $.prompt.submit({ text: `${PROMPT} (second)`, wait: false, origin: { kind: 'composer' } })
  await clock.settle()
  await clock.advance(500)
  await second
  expect(await shown()).toBe(`${NOTES.idle.glyph} compound ${NOTES.idle.label}`)
  expect((await ui.findAll({ type: 'Text' })).every(t => t.props.dimColor === true)).toBe(true)
  await clock.advance(GONE_MS - FRESH_MS)
  expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
  // Nothing animates after it.
  const after = w.calls.length
  await clock.advance(3_600_000)
  expect(w.calls.length).toBe(after)
  await ui.unmount()
})

test('a first prompt too short for a reuse check is greeted once, without counts and without a CLI call', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  const clock = mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND, viewport: { columns: 100, rows: 40 } })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  await $.prompt.submit({ text: 'hello there', wait: false, origin: { kind: 'composer' } })
  expect(await shown()).toBe(`${NOTES.ready.glyph} compound ready · ${HINT}`)
  expect(w.calls.filter(c => c[1] === 'list' || c[1] === 'status')).toEqual([])
  await clock.advance(GONE_MS)
  expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
  await $.prompt.submit({ text: 'and again', wait: false, origin: { kind: 'composer' } })
  expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
  await ui.unmount()
})

test('COMPOUND_QUIET=1 shows no greeting and no "nothing to reuse"', async ($, on) => {
  const w = world(on, { COMPOUND_QUIET: '1' })
  mock.clock(on, { now: T0 })
  w.judge = async () => NOTHING
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  for (const n of ['one', 'two']) {
    await $.prompt.submit({ text: `${PROMPT} (${n})`, wait: false, origin: { kind: 'composer' } })
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: NOTES.ready.label })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: NOTES.idle.label })).toBeUndefined()
  }
  await ui.unmount()
})

test('the band yields to a survey', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  for (const surface of SURFACES) {
    w.check = hit(`lesson-${surface}`)
    await $.tool.call({ tool: 'Bash', command: 'echo GUARDED_MARKER' })
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'AbovePrompt', props: { ...BAND, hasSurvey: true } })
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
    await ui.redraw({ ...BAND, hasSurvey: false })
    expect(await ui.find({ type: 'Text', text: NOTES.guard.label })).toBeDefined()
    await ui.unmount()
  }
})

test('a band that cannot be drawn leaves the engine\'s own, and reports one error however often it is asked', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  for (const surface of SURFACES) {
    w.check = hit(`lesson-${surface}`)
    await $.tool.call({ tool: 'Bash', command: 'echo GUARDED_MARKER' })
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'AbovePrompt', props: BAND })
    expect(await ui.find({ type: 'Text', text: NOTES.guard.label })).toBeDefined()
    // What the hook asks the engine while it draws starts failing.
    w.isLost = true
    await ui.redraw({ ...BAND, bodyColumns: 90 })
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
    await ui.redraw({ ...BAND, bodyColumns: 91 })
    await ui.redraw({ ...BAND, bodyColumns: 92 })
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeDefined()
    w.isLost = false
    await ui.redraw({ ...BAND, bodyColumns: 93 })
    expect(await ui.find({ type: 'Text', text: NOTES.guard.label })).toBeDefined()
    await ui.unmount()
  }
  // One error for the session, however many drawings failed on however many surfaces:
  // Claude is told at the next typed prompt.
  const told = await $.prompt.submit({ text: 'what happened?', wait: false, origin: { kind: 'composer' } })
  const report = (told.context ?? []).join('\n')
  expect(report.split('ui.band').length - 1).toBe(1)
  expect(report).toContain('session.id')
})

test('/compound opens the dashboard: levels, the most used, recent events and what is open, on every surface', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  for (const surface of SURFACES) {
    w.opened.length = 0
    w.events = EVENTS
    const ran = await $.command.run({ command: 'compound', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } })
    expect(ran.text).toContain('Dashboard opened')
    expect(w.opened).toEqual(['compound'])

    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'Pane', requestId: 'compound', props: PANE })
    const lines = (await ui.findAll({ type: 'Text' })).map(t => t.text)
    const all = lines.join('')
    expect(all).toContain('healthy')
    for (const heading of ['Open', 'Levels', 'Most used', 'Recent']) expect(lines).toContain(heading)
    expect(all).toContain('1 lesson owed')
    expect(all).toContain('abc123 ./x --y (2h, alpha)')
    // The totals, from the same status reply; the levels say the guards are among the lessons.
    expect(lines).toContain('Compound interest')
    for (const total of ['reuses offered', 'call stopped by a guard', 'lesson recalled', 'lessons recorded']) expect(all).toContain(total)
    expect(all).toContain('(0 guards)')
    // The timeline says the word a person reads and how long ago, not the log's type or a time of day.
    expect(all).toContain(`${NOTES.guard.glyph} guarded no-marker-echo`)
    expect(all).not.toMatch(/\d\d:\d\d /)
    expect(all).toContain('release-notes-format')
    expect(lines).toContain('▇▇▇')
    expect(all).toContain('no-marker-echo')
    // The timeline's glyph and colour are the band's.
    expect((await ui.find({ type: 'Text', text: new RegExp(`^${NOTES.guard.glyph} $`) }))?.props.color).toBe(NOTES.guard.color)
    expect(await ui.find({ type: 'Text', text: BENEATH })).toBeUndefined()
    // Every status and events read was `--json`, through the CLI.
    const reads = w.calls.filter(c => c[1] === 'status' || (c[1] === 'events' && c.includes('--limit')))
    expect(reads.length >= 2 && reads.every(c => c.includes('--json'))).toBe(true)

    // Refresh reads the CLI again and draws what it says now.
    w.events = JSON.stringify([{ ts: '2026-10-03T12:09:00Z', type: 'error', where: 'guard.check', message: 'timed out' }])
    const before = w.calls.filter(c => c[1] === 'status').length
    await ui.press({ key: 'refresh' })
    expect(w.calls.filter(c => c[1] === 'status').length).toBe(before + 1)
    expect((await ui.findAll({ type: 'Text' })).map(t => t.text).join('')).toContain('guard.check: timed out')
    expect((await ui.find({ type: 'Text', text: new RegExp(`^${ERROR.glyph} $`) }))?.props.color).toBe(ERROR.color)
    expect(await ui.find({ type: 'Button', key: 'close' })).toBeDefined()
    await ui.unmount()
  }
})

test('the pane is read again when the mod logs an event, once for a burst, and never before a tool call returns', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  const clock = mock.clock(on, { now: T0 })
  w.check = hit('no-marker-echo')
  await $.command.run({ command: 'compound', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } })
  await clock.advance(1000)
  const statusCalls = () => w.calls.filter(c => c[1] === 'status').length
  const before = statusCalls()
  await $.tool.call({ tool: 'Bash', command: 'echo GUARDED_MARKER_1' })
  // The call has returned and the dashboard was not read on its way.
  expect(statusCalls()).toBe(before)
  await clock.advance(1000)
  expect(statusCalls()).toBe(before + 1)
})

test('/compound status, and a run nobody typed, print the report as text and open nothing', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  const typed = await $.command.run({ command: 'compound', args: 'status', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } })
  expect(typed.text).toContain('"health"')
  const sdk = await $.command.run({ command: 'compound', args: '', origin: { kind: 'sdk' } as never, presentation: { isFullscreen: false, columns: 80 } })
  expect(sdk.text).toContain('"health"')
  expect(w.opened).toEqual([])
  expect(w.calls.some(c => c[1] === 'status' && !c.includes('--json'))).toBe(true)
})

// ---- settled is what the log says, however the CLI was run ---------------------------------

// A failed call and its fix: the session owes a lesson, and the band and the status entry say so.
async function owe($: Parameters<TestBody>[0], w: World, agentId?: string): Promise<void> {
  const agent = agentId === undefined ? {} : { agentId }
  w.judge = async () => '{"name":null}'
  await $.tool.call({ tool: 'Bash', command: './deploy.sh', ...agent } as never)
  w.judge = async () => FIX
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging', ...agent } as never)
}

const ADD = 'add --name deploy-needs-target --when "Use when deploying." --body "Pass --target."'
// Every way a session has been seen to run the CLI. None of them is read by the mod.
const RECORDING_FORMS = [
  `compound find deploy && compound ${ADD}`,
  `/opt/compound/bin/compound find deploy; /opt/compound/bin/compound ${ADD}`,
  `(compound ${ADD})`,
  `out=$(compound ${ADD})`,
  `echo \`compound ${ADD}\``,
  `C=/opt/compound/bin/compound; $C ${ADD}`,
  `"/opt/with space/bin/compound" ${ADD}`,
  `env COMPOUND_HOME=/tmp/h compound ${ADD}`,
  `bash -c 'compound ${ADD}'`,
  `( cd /tmp && compound ${ADD} )`,
  `./record-the-lesson.sh`,
]

test('a lesson recorded settles the band and the status entry, however the command that recorded it was written', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  const clock = mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  let n = 0
  for (const command of RECORDING_FORMS) {
    n += 1
    await owe($, w)
    expect(await shown(), command).toContain(OWED.label)
    expect(w.statuses[w.statuses.length - 1], command).toBe('lesson owed: ./deploy.sh --target staging')
    // The call writes the lesson: the log now holds its `learn`, and nothing is owed.
    w.owed = []
    w.events = JSON.stringify([{ ts: `2026-10-03T12:${String(n).padStart(2, '0')}:00Z`, type: 'learn', lesson: 'deploy-needs-target', update: false, session: 'session-under-test' }])
    await $.tool.call({ tool: 'Bash', command })
    expect(await shown(), command).toContain(`${NOTES.recorded.label} · deploy-needs-target`)
    expect(await shown(), command).not.toContain('● owed')
    expect(await shown(), command).not.toContain('1 owed')
    expect(await shown(), command).not.toContain(OWED.label)
    expect(w.statuses[w.statuses.length - 1], command).toBe(undefined)
    // The result fades, and with nothing owed the band is the engine's again.
    await clock.advance(GONE_MS)
    expect(await ui.find({ type: 'Text', text: BENEATH }), command).toBeDefined()
  }
  await ui.unmount()
})

test('a lesson declined settles them too: after another command in the same call, from a subagent, and from a terminal', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  const clock = mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  const skip = (minute: number, more: Record<string, unknown>) => JSON.stringify([{ ts: `2026-10-03T13:0${minute}:00Z`, type: 'skip', why: 'a typo', ...more }])

  await owe($, w)
  w.owed = []
  w.events = skip(1, { session: 'session-under-test' })
  await $.tool.call({ tool: 'Bash', command: 'compound show deploy-needs-target; compound skip --why "a typo"' })
  expect(await shown()).toContain(NOTES.declined.label)
  expect(await shown()).not.toContain(OWED.label)
  expect(w.statuses[w.statuses.length - 1]).toBe(undefined)
  await clock.advance(GONE_MS)

  // A subagent fixes a call and declines the lesson in its own loop.
  await owe($, w, 'agent-7')
  expect(await shown()).toContain(OWED.label)
  w.owed = []
  w.events = skip(2, { session: 'session-under-test' })
  await $.tool.call({ tool: 'Bash', command: '$COMPOUND skip --why "a typo"', agentId: 'agent-7' } as never)
  expect(await shown()).toContain(NOTES.declined.label)
  expect(await shown()).not.toContain(OWED.label)
  await clock.advance(GONE_MS)

  // Declined in a terminal, by its id: the row belongs to no session, and the next call of
  // any tool finds the debt gone.
  await owe($, w)
  const id = String(w.owed[0]?.id)
  await $.tool.call({ tool: 'Read', file_path: '/work/alpha/README.md' } as never)
  expect(await shown(), 'still owed while the log says so').toContain(OWED.label)
  w.owed = []
  w.events = skip(3, { session: '', settles: id })
  await $.tool.call({ tool: 'Read', file_path: '/work/alpha/README.md' } as never)
  expect(await shown()).toContain(NOTES.declined.label)
  expect(await shown()).not.toContain(OWED.label)
  expect(w.statuses[w.statuses.length - 1]).toBe(undefined)

  // Nothing is owed now: a call asks the CLI nothing about debts.
  await clock.advance(GONE_MS)
  const asked = () => w.calls.filter(c => c.includes('--unsettled') && c.includes('--session')).length
  const before = asked()
  await $.tool.call({ tool: 'Read', file_path: '/work/alpha/README.md' } as never)
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  expect(asked()).toBe(before)
  await ui.unmount()
})

const KNOWN = JSON.stringify({ verdict: 'KNOWN', name: 'release-notes-format' })

test('with a lesson and a strengthening both owed, rewriting the weak lesson leaves the band what the log holds: nothing', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000', COMPOUND_RECUR_LIMIT: '1' })
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  await owe($, w)
  // The same call fails again, and this time a recorded lesson describes it: it did not prevent it.
  w.judge = async () => '{"name":"release-notes-format"}'
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(w.logged.filter(e => e.type === 'recall').map(e => e.ineffective)).toEqual([true])
  expect(w.owed.map(e => e.type)).toEqual(['capture', 'recall'])
  expect(await shown()).toContain('owed')
  // `add --update` of that lesson, from this session: the log holds no debt after it.
  w.owed = []
  w.events = JSON.stringify([{ ts: '2026-10-03T14:00:00Z', type: 'learn', lesson: 'release-notes-format', update: true, session: 'session-under-test' }])
  await $.tool.call({ tool: 'Bash', command: 'compound add --update --name release-notes-format --match "deploy\\.sh$"' })
  expect(await shown()).toContain(`${NOTES.rewritten.label} · release-notes-format`)
  expect(await shown()).not.toContain('owed')
  expect(await shown()).not.toContain('to strengthen')
  expect(w.statuses[w.statuses.length - 1]).toBe(undefined)
  await ui.unmount()
})

test('a strengthening whose lesson was removed is no longer owed, on the band or at the stop', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000', COMPOUND_RECUR_LIMIT: '1' })
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  w.judge = async () => '{"name":"release-notes-format"}'
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(await shown()).toContain('release-notes-format')
  expect(w.owed.map(e => e.type)).toEqual(['recall'])
  w.owed = []
  w.events = JSON.stringify([{ ts: '2026-10-03T15:00:00Z', type: 'rm', lesson: 'release-notes-format', level: 'project', session: 'session-under-test' }])
  await $.tool.call({ tool: 'Bash', command: 'compound rm release-notes-format' })
  expect(await shown()).not.toContain(WEAK.label)
  expect(await shown()).not.toContain('to strengthen')
  const stop = await $.classic.Stop({ stop_hook_active: false } as never)
  expect(stop.block).toBe(undefined)
  expect(w.logged.filter(e => e.type === 'refuse')).toEqual([])
  await ui.unmount()
})

test('the stop asks the CLI what the session owes, and refuses for exactly that', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  await owe($, w)
  // The session's own events hold a capture and nothing after it: declined in a terminal,
  // the row that settles it is in no session's events. The CLI's answer is what counts.
  w.events = JSON.stringify([{ ts: '2026-10-03T12:00:00Z', type: 'capture', session: 'session-under-test', call: 'c1', failed: './deploy.sh', fixed: './deploy.sh --target staging' }])
  const kept = w.owed
  w.owed = []
  const free = await $.classic.Stop({ stop_hook_active: false } as never)
  expect(free.block).toBe(undefined)
  expect(w.calls.some(c => c.includes('--unsettled') && c.includes('--session') && c.includes('session-under-test'))).toBe(true)
  // And while the CLI says it is owed, the stop is refused, once.
  w.owed = kept
  const refused = await $.classic.Stop({ stop_hook_active: false } as never)
  expect(refused.block).toContain('This session owes a lesson')
  expect(refused.block).toContain('./deploy.sh --target staging')
  expect(w.logged.filter(e => e.type === 'refuse').map(e => e.why)).toEqual(['debt'])
  const again = await $.classic.Stop({ stop_hook_active: true } as never)
  expect(again.block).toBe(undefined)
})

test('a lesson recorded between a failure and its fix is that failure\'s lesson, not a recurrence of it', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  const agent = { agentId: 'agent-9' }
  w.judge = async () => '{"name":null}'
  await $.tool.call({ tool: 'Bash', command: './deploy.sh', ...agent } as never)
  // The subagent records the lesson before it sends the call that works.
  w.events = JSON.stringify([{ ts: '2026-10-03T16:00:00Z', type: 'learn', lesson: 'release-notes-format', update: false, session: 'session-under-test' }])
  await $.tool.call({ tool: 'Bash', command: `compound add --name release-notes-format --when w --body b`, ...agent } as never)
  w.judge = async () => KNOWN
  const fixed = await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging', ...agent } as never)
  expect(w.logged.filter(e => e.type === 'recall')).toEqual([])
  expect(w.logged.filter(e => e.type === 'capture')).toEqual([])
  expect(JSON.stringify(fixed)).not.toContain('already recorded')

  // A lesson that was there before the failure, met again at the fix, is a recurrence.
  w.events = '[]'
  w.judge = async () => '{"name":null}'
  await $.tool.call({ tool: 'Bash', command: './deploy.sh', ...agent } as never)
  w.judge = async () => KNOWN
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging', ...agent } as never)
  expect(w.logged.filter(e => e.type === 'recall').map(e => [e.lesson, e.at])).toEqual([['release-notes-format', 'fix']])
})
