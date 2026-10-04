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
// The judge names the one candidate, with the words of the request that ask for it.
const NAMED = '{"substantial":true,"items":[{"name":"release-notes-format","quote":"Write the release notes"}],"requests":[]}'
// `compound find --request --json`: the one lesson reaches the floor, and no verdict is held.
const FOUND = JSON.stringify({ words: ['release', 'notes'], items: JSON.parse(ITEMS), floor: 1.5, memo_key: 'a'.repeat(32), prompts: [], surfer: 'ok' })
const STATUS = JSON.stringify({
  ok: true,
  totals: { reused: 3, guarded: 1, recalled: 1, recorded: 5, since: '2026-09-12T10:00:00Z' },
  health: [{ check: 'python', status: 'PASS', detail: '3.12.1' }],
  store: { project: { lessons: 1, skills: 0, guards: 0 }, user: { lessons: 0, skills: 0, guards: 0 }, general: { lessons: 0, skills: 2, guards: 0 } },
  lessons: [{ name: 'release-notes-format', level: 'project', kind: 'lesson', guard: false, reuse: 3, guard_hits: 0, recall: 1, flag: '' }],
  recent: [],
  open: { ineffective: [], unsettled: [{ id: 'abc123', age: '2h', project: '/work/alpha', failed: './x', fixed: './x --y', command: '/compound:learn settle abc123', decline: 'compound skip --settles abc123 --why "<reason>"' }], candidates: [], skips: [], errors: [] },
})
// What the CLI prints for the pane's `list --json` and for `show release-notes-format --json`.
const LISTED = JSON.stringify([
  { level: 'project', kind: 'lesson', name: 'release-notes-format', description: 'Use when writing release notes.', path: '/p/l/release-notes-format', match: ['notes\\.md$'], counts: { reuse: 3, guard: 0, recall: 1, learn: 1 }, ineffective: false },
  { level: 'user', kind: 'lesson', name: 'never-used', description: 'Use when nothing happens.', path: '/u/l/never-used', match: [], counts: { reuse: 0, guard: 0, recall: 0, learn: 1 }, ineffective: false },
  { level: 'general', kind: 'skill', name: 'a-skill', description: 'Use when a skill is wanted.', path: '/g/s/a-skill', match: [] },
])
const SHOWN = JSON.stringify({
  level: 'project', kind: 'lesson', name: 'release-notes-format', description: 'Use when writing release notes.', path: '/p/l/release-notes-format', match: ['notes\\.md$'],
  counts: { reuse: 3, guard: 0, recall: 1, learn: 1 }, ineffective: false, text: '---\nname: release-notes-format\n---\nOne line per change.\n',
  body: 'One line per change, newest first.\n\nEach line starts with the issue number, and a line that is very long is wrapped where the pane ends and never cut short.',
  last: { ts: '2027-01-15T07:59:35Z', type: 'reuse' }, files: [],
})
const EVENTS = JSON.stringify([{ ts: '2026-10-03T12:00:00Z', type: 'guard', lesson: 'no-marker-echo' }])

// `owed` is what the CLI answers `events --unsettled --session S`: the log's own account of
// what the session owes. The world keeps it as the log would: a capture or an ineffective
// recall the mod logs is owed from then on, until the test says the log holds its settlement.
// `tool` answers a tool call in the engine's place (undefined: the default below), `show` is
// what the CLI prints for `show <name> --json`, and `asked` counts the questions put to the judge.
type Answer = { text: string; isError?: true }
// `listed` is what the CLI prints for the pane's `list --json`, `showCode` and `listCode` their exit
// codes, `wait` is awaited before either answers, `closed` are the panes the mod closed, and
// `focusAsked` is what each open asked of the keyboard.
type World = { calls: string[][]; logged: Record<string, unknown>[]; memos: Record<string, unknown>[]; found: () => string; judge: () => Promise<string>; check: string; events: string; owed: Record<string, unknown>[]; statuses: (string | undefined)[]; opened: string[]; isLost: boolean; tool: (command: string) => Answer | undefined; show: string; asked: number; listed: string; showCode: number; listCode: number; wait: () => Promise<void>; closed: string[]; status: string; focusAsked: unknown[]; used: (name: string) => string }

// Everything the mod reaches for through `$`, answered from memory: the CLI by its
// subcommand, the judge by `world.judge`, and a marker where the engine's own band would be.
function world(on: On, env: Record<string, string> = {}): World {
  const w: World = { calls: [], logged: [], memos: [], found: () => FOUND, judge: async () => NAMED, check: '{"hits":[],"guards":1}', events: EVENTS, owed: [], statuses: [], opened: [], isLost: false, tool: () => undefined, show: '', asked: 0, listed: LISTED, showCode: 0, listCode: 0, wait: async () => undefined, closed: [], status: STATUS, focusAsked: [], used: () => '{"used":false,"name":""}' }
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
    w.focusAsked.push((e as { focus?: unknown }).focus)
    return { value: { isPlaced: true as const } }
  })
  on('ui.close', (_$, e) => {
    w.closed.push(e.id)
    return { value: undefined }
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
    const failed = (exitCode: number, stderr: string) => ({ value: { exitCode, stdout: '', stderr, isStdoutTruncated: false, isStderrTruncated: false } })
    // The pane lists without the scripts; the reuse check lists with them.
    if (verb === 'list' && !argv.includes('--scripts') && !argv.includes('--level')) return w.wait().then(() => (w.listCode === 0 ? done(w.listed) : failed(w.listCode, 'compound: the store cannot be read')))
    if (verb === 'list') return done(ITEMS)
    if (verb === 'status') return done(w.status)
    if (verb === 'show' && w.showCode !== 0) return w.wait().then(() => failed(w.showCode, `compound: no lesson or skill named '${argv[2]}'`))
    if (verb === 'show') return w.wait().then(() => done(w.show))
    if (verb === 'events') return done(argv.includes('--unsettled') ? (argv.includes('--session') ? JSON.stringify(w.owed) : '[]') : w.events)
    if (verb === 'find') return done(w.found())
    if (verb === 'memo') {
      w.memos.push(JSON.parse(e.init?.stdin ?? '{}') as Record<string, unknown>)
      return done('')
    }
    if (verb === 'check') return done(w.check)
    // `compound use --json -- <name>`: whether the skill is one the CLI counts.
    if (verb === 'use') return done(w.used(argv[argv.length - 1] ?? ''))
    if (verb === 'show') return done(w.show)
    return done('')
  })
  on('model.complete', async () => {
    w.asked += 1
    return { value: { isAnswered: true as const, text: await w.judge(), usage: { input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 } } }
  })
  // A Bash call fails unless it carries its flag; every other call succeeds.
  on('tool.call', (_$, e) => {
    const command = String((e as unknown as { command?: unknown }).command ?? '')
    const answer = w.tool(command)
    if (answer !== undefined) return { result: {}, ...answer } as never
    const failed = command === './deploy.sh'
    return (failed ? { result: {}, text: 'deploy.sh: error: a target is required', isError: true } : { result: {}, text: 'ok' }) as never
  })
  on('classic.Stop', () => ({}) as never)
  // The engine's own expansion of a skill: its text as computed.
  on('skill.prompt', (_$, e) => ({ text: e.text }))
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
    return NAMED
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
    expect(w.logged.map(e => e.type), JSON.stringify(w.logged)).toEqual(['judge', 'reuse'])

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
  expect(w.logged.map(e => e.type)).toEqual(['judge', 'judge', 'capture'])

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
    expect(w.logged.map(e => e.type)).toEqual(['judge', 'reuse'])
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
  // Nothing was found, so nothing happened: the log holds only the judge's verdict.
  expect(w.logged.map(e => e.type)).toEqual(['judge'])
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
    // A lesson's name is something to press.
    expect((await ui.find({ type: 'Button', key: 'open:release-notes-format' }))?.props.label).toBe('release-notes-format')
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

// ---- the pane's drill-down ----

type Node = { type: string; props?: Record<string, unknown>; children?: (Node | string)[] }

// The rows of a drawn pane as a terminal shows them: a Text by its text, and a Button by its
// label, after its hotkey when it has one (`a: all lessons`).
async function rowsOf(ui: { drawn: () => Promise<unknown> }): Promise<string[]> {
  const said = (n: Node | string): string =>
    typeof n === 'string' ? n : n.type === 'Button' ? `${n.props?.hotkey === undefined ? '' : `${String(n.props.hotkey)}: `}${String(n.props?.label ?? '')}` : (n.children ?? []).map(said).join('')
  return (((await ui.drawn()) as Node).children ?? []).map(said)
}

const open = ($: Parameters<TestBody>[0]) => $.command.run({ command: 'compound', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } })

test('opening the pane asks for no keyboard, and its first row says which keys work and how the pane gets them', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  await open($)
  // Typing stays with the prompt: the pane is opened without `focus`.
  expect(w.focusAsked).toEqual([undefined])
  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'Pane', requestId: 'compound', props: PANE })
    // Without the keyboard: how to give it, then the keys, each a Button drawn with its hotkey.
    expect((await rowsOf(ui))[0]).toBe(surface === 'terminal' ? 'ctrl+x tab for keys  a: all lessons  r: refresh  x: close' : 'a: all lessons  r: refresh  x: close')
    for (const [key, hotkey] of [['all', 'a'], ['refresh', 'r'], ['close', 'x']] as const) {
      const button = await ui.find({ type: 'Button', key })
      expect([button?.props.hotkey, button?.props.plain]).toEqual([hotkey, true])
    }
    expect((await ui.find({ type: 'Button', key: 'close' }))?.props.role).toBe('dismiss')
    // With the keyboard, a tree that fits its window is walked by the arrows.
    await ui.redraw({ ...PANE, isFocused: true, bodyColumns: 100, scroll: { offset: 0, bodyRows: 60 } })
    expect((await rowsOf(ui))[0]).toBe(surface === 'terminal' ? '↑↓ select · enter open · esc to the prompt  a: all lessons  r: refresh  x: close' : 'a: all lessons  r: refresh  x: close')
    // A tree taller than its window is scrolled by them, and Tab walks the rows.
    await ui.redraw({ ...PANE, isFocused: true, bodyColumns: 100, scroll: { offset: 0, bodyRows: 8 } })
    expect((await rowsOf(ui))[0]).toBe(surface === 'terminal' ? '↑↓ scroll · tab select · enter open · esc to the prompt  a: all lessons  r: refresh  x: close' : 'a: all lessons  r: refresh  x: close')
    // Each open row is followed by the command that settles it, as the CLI gave it.
    const rows = await rowsOf(ui)
    expect(rows[rows.findIndex(r => r.includes('abc123 ./x --y')) + 1]).toBe('      /compound:learn settle abc123')
    expect(rows[rows.findIndex(r => r.includes('abc123 ./x --y')) + 2]).toBe('      or compound skip --settles abc123 --why "<reason>"')
    // Close closes the pane.
    await ui.press({ key: 'close' })
    expect(w.closed).toEqual(['compound'])
    w.closed.length = 0
    await ui.unmount()
  }
})

test('pressing a lesson shows it: reading, then what `compound show --json` printed, and back returns to where it was pressed', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  const clock = mock.clock(on, { now: T0 })
  w.show = SHOWN
  for (const surface of SURFACES) {
    await open($)
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'Pane', requestId: 'compound', props: { ...PANE, isFocused: true } })
    const shows = () => w.calls.filter(c => c[1] === 'show')
    const before = shows().length
    w.wait = () => clock.sleep(300)
    const pressing = ui.press({ key: 'open:release-notes-format' })
    await clock.settle()
    // While the CLI is asked the view says so, under the lesson's name, and offers the way back.
    expect((await rowsOf(ui)).slice(1)).toEqual(['release-notes-format', 'Reading the lesson…'])
    expect((await rowsOf(ui))[0]).toContain('b: back')
    expect(await ui.find({ type: 'Button', key: 'all' })).toBeUndefined()
    await clock.advance(300)
    await pressing
    w.wait = async () => undefined
    expect(shows().slice(before)).toEqual([[shows()[0]![0]!, 'show', 'release-notes-format', '--json']])
    const rows = await rowsOf(ui)
    expect(rows.slice(1, 9)).toEqual([
      'release-notes-format',
      'project · guard',
      '◆ 3 reused  ■ 0 guarded  ↺ 1 recalled  ▸ 0 used',
      'last fired 25s ago (reused)',
      'guard pattern',
      '  notes\\.md$',
      '/p/l/release-notes-format',
      ' ',
    ])
    expect(rows[9]).toBe('Use when writing release notes.')
    expect(rows.slice(11)).toEqual(['One line per change, newest first.', ' ', 'Each line starts with the issue number, and a line that is', 'very long is wrapped where the pane ends and never cut', 'short.'])
    expect(rows.join('\n')).not.toContain('---')
    expect((await ui.find({ type: 'Text', text: 'release-notes-format' }))?.props.bold).toBe(true)
    // Back is the dashboard again, and it asked the CLI nothing.
    const calls = w.calls.length
    await ui.press({ key: 'back' })
    expect((await rowsOf(ui)).some(r => r.startsWith('Most used'))).toBe(true)
    expect(await ui.find({ type: 'Button', key: 'all' })).toBeDefined()
    expect(w.calls.length).toBe(calls)
    // No lesson is read on a path a tool call waits on.
    await $.tool.call({ tool: 'Bash', command: 'ls' })
    expect(shows().length).toBe(before + 1)
    expect(w.logged.filter(e => e.type === 'error')).toEqual([])
    await ui.unmount()
  }
})

test('a lesson the CLI cannot show says why, logs no error, and Refresh asks again', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  for (const surface of SURFACES) {
    await open($)
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'Pane', requestId: 'compound', props: PANE })
    w.showCode = 1
    await ui.press({ key: 'open:release-notes-format' })
    expect((await rowsOf(ui)).slice(1)).toEqual(['release-notes-format', '✖ compound show exit 1: compound: no lesson or skill named', "  'release-notes-format'"])
    expect((await ui.find({ type: 'Text', text: /^✖ $/ }))?.props.color).toBe(ERROR.color)
    // What the CLI printed is not the object it should be.
    w.showCode = 0
    w.show = 'not json'
    await ui.press({ key: 'refresh' })
    expect((await rowsOf(ui)).slice(1).join(' ')).toContain('compound show --json printed something unreadable')
    // Refresh asks again, and the lesson is there.
    w.show = SHOWN
    await ui.press({ key: 'refresh' })
    expect((await rowsOf(ui)).slice(1, 3)).toEqual(['release-notes-format', 'project · guard'])
    // A lesson that is gone is the store's state, not a failure of the mod.
    expect(w.logged.filter(e => e.type === 'error')).toEqual([])
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
})

test('the all-lessons view lists every lesson and skill by level; each opens, and back returns to the list, then the dashboard', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  const clock = mock.clock(on, { now: T0 })
  w.show = SHOWN
  for (const surface of SURFACES) {
    await open($)
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'Pane', requestId: 'compound', props: { ...PANE, bodyColumns: 100 } })
    const lists = () => w.calls.filter(c => c[1] === 'list' && !c.includes('--scripts'))
    const before = lists().length
    w.wait = () => clock.sleep(300)
    const pressing = ui.press({ key: 'all' })
    await clock.settle()
    expect((await rowsOf(ui)).slice(1)).toEqual(['Reading the store…'])
    await clock.advance(300)
    await pressing
    w.wait = async () => undefined
    expect(lists().slice(before).map(c => c.slice(1))).toEqual([['list', '--json']])
    const rows = await rowsOf(ui)
    expect(rows[0]).toContain('b: back')
    expect(rows.slice(1)).toEqual([
      'All lessons  2 lessons (1 guard)  1 skill  ◆ reused  ■ guarded  ↺ recalled  ▸ used',
      ' ',
      'project  1 lesson (1 guard)  0 skills',
      '  release-notes-format  guard   ◆ 3  ■ 0  ↺ 1  ▸ 0  Use when writing release notes.',
      ' ',
      'user  1 lesson (0 guards)  0 skills',
      '  never-used            lesson  ◆ 0  ■ 0  ↺ 0  ▸ 0  Use when nothing happens.',
      ' ',
      'general  0 lessons (0 guards)  1 skill',
      '  a-skill               skill   ◆ 0  ■ 0  ↺ 0  ▸ 0  Use when a skill is wanted.',
    ])
    // Every row is a Button, also the lesson nothing has used and the skill.
    for (const name of ['release-notes-format', 'never-used', 'a-skill']) expect((await ui.find({ type: 'Button', key: `open:${name}` }))?.props.label).toBe(name)
    // A lesson opened from the list goes back to the list; the list goes back to the dashboard.
    await ui.press({ key: 'open:release-notes-format' })
    expect((await rowsOf(ui)).slice(1, 3)).toEqual(['release-notes-format', 'project · guard'])
    await ui.press({ key: 'back' })
    expect((await rowsOf(ui))[1]).toContain('All lessons')
    // Refresh in the list reads the list again.
    w.listed = '[]'
    await ui.press({ key: 'refresh' })
    expect(await rowsOf(ui)).toContain('  nothing recorded yet')
    // A list the CLI cannot give says why, over the rows it had.
    w.listCode = 2
    await ui.press({ key: 'refresh' })
    expect((await rowsOf(ui))[1]).toBe('✖ compound list exit 2: compound: the store cannot be read')
    w.listCode = 0
    w.listed = LISTED
    await ui.press({ key: 'back' })
    expect((await rowsOf(ui)).some(r => r.startsWith('Most used'))).toBe(true)
    expect(w.logged.filter(e => e.type === 'error')).toEqual([])
    await ui.unmount()
  }
})

test('no row of any view is wider than the pane at 30, 40, 60 and 100 columns, and every key is in the first rows', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  w.show = SHOWN
  for (const surface of SURFACES) {
    await open($)
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'Pane', requestId: 'compound', props: PANE })
    const fits = async (view: string, keys: readonly string[]) => {
      for (const columns of [30, 40, 60, 100]) {
        for (const isFocused of [true, false]) {
          await ui.redraw({ ...PANE, isFocused, bodyColumns: columns })
          const rows = await rowsOf(ui)
          for (const row of rows) expect([...row].length <= columns, `${surface} ${view} ${columns}: ${row}`).toBe(true)
          const head = rows.slice(0, 4).join(' ')
          for (const key of keys) expect(head, `${surface} ${view} ${columns}`).toContain(key)
        }
      }
    }
    await fits('board', ['a: all', 'r: refresh', 'x: close'])
    await ui.press({ key: 'all' })
    await fits('all', ['b: back', 'r: refresh', 'x: close'])
    await ui.press({ key: 'open:never-used' })
    await fits('lesson', ['b: back', 'r: refresh', 'x: close'])
    await ui.press({ key: 'back' })
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
})

test('a press that fails breaks nothing: the pane goes on, and Claude is told once', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  await open($)
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'Pane', requestId: 'compound', props: PANE })
  // What every handler asks the engine first starts failing.
  w.isLost = true
  for (const key of ['all', 'open:release-notes-format', 'refresh', 'all']) await ui.press({ key })
  w.isLost = false
  // The dashboard is still the view, and its keys still work.
  await ui.redraw({ ...PANE, bodyColumns: 61 })
  expect((await rowsOf(ui)).some(r => r.startsWith('Most used'))).toBe(true)
  await ui.press({ key: 'all' })
  expect((await rowsOf(ui))[1]).toContain('All lessons')
  const told = await $.prompt.submit({ text: 'what happened?', wait: false, origin: { kind: 'composer' } })
  const report = (told.context ?? []).join('\n')
  expect(report.split('ui.pane').length - 1).toBe(1)
  await ui.unmount()
})

test('/compound typed again, and a pane closed, start at the dashboard', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  w.show = SHOWN
  await open($)
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'Pane', requestId: 'compound', props: PANE })
  await ui.press({ key: 'all' })
  await ui.press({ key: 'open:never-used' })
  expect((await rowsOf(ui))[0]).toContain('b: back')
  await open($)
  expect((await rowsOf(ui))[0]).toContain('a: all lessons')
  await ui.press({ key: 'all' })
  await ui.press({ key: 'close' })
  expect((await rowsOf(ui))[0]).toContain('a: all lessons')
  await $.command.run({ command: 'compound', args: 'close', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } })
  expect(w.closed).toEqual(['compound', 'compound'])
  await ui.unmount()
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

// ---- what counts as a failed call ----

test('a call refused before it ran is not a failed call: no judge, nothing held, nothing watched', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  // Refusals as the harness worded them on this machine, 2026-10-04.
  const refusals = [
    'Permission for this action was denied by the Claude Code auto mode classifier. Reason: Blocked by classifier.',
    "This agent is isolated in the worktree /work/alpha/.claude/worktrees/agent-1, but this command is too complex to verify that it stays inside the worktree. Refusing to run it — a worktree-isolated agent's git operations must target its own worktree.",
    "Claude requested permissions to write to /work/alpha/parseDuration.js, but you haven't granted it yet.",
    "...Do not work around the check by splitting, scripting, or re-issuing the removal through another tool or shell ... What was flagged: Dangerous rm operation detected: '/Users/jmanning/claude-skill-compounder/lessons/*'",
  ]
  for (const [i, text] of refusals.entries()) {
    w.tool = () => ({ text, isError: true })
    const ran = await $.tool.call({ tool: 'Bash', command: `rm -rf lessons/* # ${i}` })
    expect(ran.context ?? []).toEqual([])
  }
  expect(w.asked).toBe(0)
  expect(w.logged).toEqual([])
  expect(await shown()).not.toContain('watching for the fix')
  // Nothing was held, so the call that then works is not put to the judge as a fix.
  w.tool = () => ({ text: 'ok' })
  w.judge = async () => FIX
  await $.tool.call({ tool: 'Bash', command: 'rm -r lessons/old' })
  expect(w.asked).toBe(0)
  expect(w.logged).toEqual([])
  // The same command, really run and really failing, is a failed call.
  w.tool = () => ({ text: 'Exit code 1\nrm: lessons/old: No such file or directory', isError: true })
  w.judge = async () => '{"name":null}'
  await $.tool.call({ tool: 'Bash', command: 'rm -r lessons/old' })
  expect(w.asked).toBe(1)
  expect(await shown()).toContain('watching for the fix')
  await ui.unmount()
})

test('a Bash call that exits 0 with a shell error in its output is a failed call: recalled, held, and captured when fixed', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  const ui = await $.ui.mount({ plugin: 'compound', surface: 'terminal', component: 'AbovePrompt', props: BAND })
  const shown = async () => (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
  // A pipeline's status is its last command's: `timeout` is missing and the call "succeeds".
  w.tool = () => ({ text: '(eval):1: command not found: timeout\n' })
  w.judge = async () => '{"name":null}'
  await $.tool.call({ tool: 'Bash', command: 'timeout 5 ./slow.sh | tail -5' })
  expect(w.asked).toBe(1)
  expect(await shown()).toContain('watching for the fix')
  expect(w.logged.map(e => [e.type, e.moment, e.verdict, typeof e.ms])).toEqual([['judge', 'recall', 'none', 'number']])
  // The call that works is judged as its fix, and the evidence is the shell's own line.
  w.tool = () => ({ text: 'done' })
  w.judge = async () => JSON.stringify({ same_goal: true, call_mistake: true, recurs: true, evidence: 'command not found: timeout', verdict: 'FIX' })
  await $.tool.call({ tool: 'Bash', command: 'perl -e "alarm 5; exec @ARGV" ./slow.sh | tail -5' })
  const capture = w.logged.find(e => e.type === 'capture')
  expect(capture?.failed).toBe('timeout 5 ./slow.sh | tail -5')
  expect(String(capture?.error)).toContain('(eval):1: command not found: timeout')
  expect(w.logged.filter(e => e.type === 'judge').map(e => [e.moment, e.verdict])).toEqual([['recall', 'none'], ['fix', 'fix']])
  await ui.unmount()
})

test('output that only mentions a shell error, or another tool\'s output, is a success', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  w.tool = () => ({ text: 'notes.md:12:(eval):1: command not found: timeout\nnotes.md:40:  zsh: command not found: gtimeout' })
  await $.tool.call({ tool: 'Bash', command: "grep -n 'command not found' notes.md" })
  w.tool = () => ({ text: '(eval):1: command not found: timeout' })
  await $.tool.call({ tool: 'WebFetch', url: 'https://example.com/log.txt', prompt: 'the log' } as never)
  expect(w.asked).toBe(0)
  expect(w.logged).toEqual([])
})

// ---- a recall after the guard refused ----

test('a failure after the lesson\'s guard refused in this session is recalled and is not counted as the lesson failing', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000', COMPOUND_RECUR_LIMIT: '1' })
  mock.clock(on, { now: T0 })
  // The guard refuses the call once; sent again, it runs and fails.
  w.check = hit('release-notes-format')
  const refused = await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(refused.deny).toContain('lesson=release-notes-format')
  expect(w.asked).toBe(0)
  w.judge = async () => '{"name":"release-notes-format"}'
  // The CLI's account: the guard refused in this session, so no recall of it counts.
  w.show = JSON.stringify({ name: 'release-notes-format', level: 'project', path: '/p/l/release-notes-format', text: 'Print it with printf.', counts: { recall: 0 }, recalls_since: 0, recur_limit: 1, guarded_in_session: true })
  const again = await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  const recall = w.logged.find(e => e.type === 'recall')
  expect([recall?.lesson, recall?.ineffective, recall?.after_guard, typeof recall?.ms]).toEqual(['release-notes-format', false, true, 'number'])
  expect(w.owed).toEqual([])
  expect(JSON.stringify(again.context)).toContain('A recorded lesson may describe this failure')
  expect(JSON.stringify(again.context)).not.toContain('is not preventing that failure')
  const stop = await $.classic.Stop({ stop_hook_active: false } as never)
  expect(stop.block).toBe(undefined)
  // Without a refusal in the session, the same answer from the CLI is a recurrence that counts.
  w.show = JSON.stringify({ name: 'release-notes-format', text: 'Print it with printf.', counts: { recall: 1 }, recalls_since: 0, recur_limit: 1, guarded_in_session: false })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(w.logged.filter(e => e.type === 'recall').map(e => [e.ineffective, e.after_guard])).toEqual([[false, true], [true, false]])
})

// ---- a lesson of the general pool ----

test('a general lesson that recurs past the limit is recalled, and the session owes nothing for it', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000', COMPOUND_RECUR_LIMIT: '1' })
  mock.clock(on, { now: T0 })
  w.judge = async () => '{"name":"release-notes-format"}'
  // The CLI's account: the lesson ships with the package and was recalled far past the limit.
  w.show = JSON.stringify({ name: 'release-notes-format', level: 'general', path: '/pkg/lessons/release-notes-format', text: 'Print it with printf.', counts: { recall: 5 }, recalls_since: 5, recur_limit: 1, guarded_in_session: false, ineffective: false, recurring: true })
  const failed = await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  const recall = w.logged.find(e => e.type === 'recall')
  expect([recall?.lesson, recall?.ineffective]).toEqual(['release-notes-format', false])
  expect(w.owed).toEqual([])
  expect(JSON.stringify(failed.context)).toContain('A recorded lesson may describe this failure')
  expect(JSON.stringify(failed.context)).not.toContain('is not preventing that failure')
  expect(JSON.stringify(failed.context)).not.toContain('--update')
  const stop = await $.classic.Stop({ stop_hook_active: false } as never)
  expect(stop.block).toBe(undefined)
  expect(w.logged.filter(e => e.type === 'refuse')).toEqual([])
  // The same answer for a lesson of the user's own is a strengthening owed.
  w.show = JSON.stringify({ name: 'release-notes-format', level: 'user', path: '/u/l/release-notes-format', text: 'Print it with printf.', counts: { recall: 5 }, recalls_since: 5, recur_limit: 1, guarded_in_session: false })
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(w.logged.filter(e => e.type === 'recall').map(e => e.ineffective)).toEqual([false, true])
})

// ---- every verdict is logged ----

test('every question put to the judge writes a judge event with its ms, whatever the answer', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  const verdicts = () => w.logged.filter(e => e.type === 'judge').map(e => [e.moment, e.verdict])
  // Reuse: nothing named, not substantial, named, unreadable.
  for (const [n, reply] of ['{"substantial":true,"items":[],"requests":[]}', '{"substantial":false,"items":[],"requests":[]}', NAMED, 'I cannot say.'].entries()) {
    w.judge = async () => reply
    await $.prompt.submit({ text: `${PROMPT} (${n})`, wait: false, origin: { kind: 'composer' } })
  }
  expect(verdicts()).toEqual([['reuse', 'nothing'], ['reuse', 'not-substantial'], ['reuse', 'named'], ['reuse', 'unreadable']])
  expect(w.logged.filter(e => e.type === 'judge').map(e => typeof e.ms)).toEqual(['number', 'number', 'number', 'number'])
  expect(w.logged.filter(e => e.type === 'judge')[2]?.named).toEqual(['release-notes-format'])
  expect(typeof w.logged.filter(e => e.type === 'judge')[0]?.prompt_id).toBe('string')
  w.logged.length = 0
  // Recall: none, then a fix that is none, then a fix that is known.
  w.judge = async () => '{"name":null}'
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  w.judge = async () => '{"verdict":"NONE","reason":"the next step"}'
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  w.judge = async () => KNOWN
  await $.tool.call({ tool: 'Bash', command: './deploy.sh --target staging' })
  // Recall: named.
  w.judge = async () => '{"name":"release-notes-format"}'
  await $.tool.call({ tool: 'Bash', command: './deploy.sh' })
  expect(verdicts()).toEqual([['recall', 'none'], ['fix', 'none'], ['fix', 'known'], ['recall', 'named']])
  const rows = w.logged.filter(e => e.type === 'judge')
  expect(rows.map(e => typeof e.ms)).toEqual(['number', 'number', 'number', 'number'])
  expect(rows.map(e => e.tool)).toEqual(['Bash', 'Bash', 'Bash', 'Bash'])
  expect(rows[1]?.reason).toBe('the next step')
  expect(rows[2]?.named).toEqual(['release-notes-format'])
  expect(w.logged.filter(e => e.type === 'recall').map(e => typeof e.ms)).toEqual(['number', 'number'])
})

// ---- guards apply to tools ----

test('no check is made before a call of a tool no guard applies to', async ($, on) => {
  const w = world(on, { COMPOUND_PROMPT_MIN_CHARS: '100000' })
  mock.clock(on, { now: T0 })
  const checks = () => w.calls.filter(c => c[1] === 'check').length
  w.check = '{"hits":[],"guards":2,"tools":["Bash","Edit"]}'
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  expect(checks()).toBe(1)
  // A file's content and an agent's prompt are not commands: nothing is asked before them.
  await $.tool.call({ tool: 'Write', file_path: '/work/alpha/notes.md', content: 'Run the tests; git commit -m done' } as never)
  await $.tool.call({ tool: 'Agent', prompt: 'run the suite; git commit only if green' } as never)
  expect(checks()).toBe(1)
  await $.tool.call({ tool: 'Edit', file_path: '/work/alpha/.env', old_string: 'a', new_string: 'b' } as never)
  await $.tool.call({ tool: 'Bash', command: 'ls -la' })
  expect(checks()).toBe(3)
  // The store changed: what was known about the guards is asked again.
  w.events = '[]'
  await $.tool.call({ tool: 'Bash', command: 'compound add --update --name release-notes-format --match x --tool Write' })
  await $.tool.call({ tool: 'Write', file_path: '/work/alpha/notes.md', content: 'x' } as never)
  expect(checks()).toBe(4)
})

test('a prompt is asked of the CLI in one call, its verdict is given to the CLI to keep, and a kept verdict asks no model', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  await $.prompt.submit({ text: `${PROMPT} (first)`, wait: false, origin: { kind: 'composer' } })
  const find = w.calls.find(c => c.includes('find'))!
  expect(find.slice(1)).toEqual(['find', '--request', '--json'])
  expect(w.asked).toBe(1)
  // The verdict goes to the CLI, with the key the CLI gave and what was named.
  expect(w.memos).toEqual([{ key: 'a'.repeat(32), verdict: 'named', items: ['release-notes-format'], prompts: [] }])
  const first = w.logged.find(e => e.type === 'reuse')!
  expect(first.lessons).toEqual(['release-notes-format'])
  expect(first.words).toEqual(['release', 'notes'])
  expect(first.memo).toBe(undefined)

  // The CLI now holds a verdict for the prompt: nothing is asked, and the same thing is added.
  const earlier = { id: 'old:1', ts: '2026-09-01', project: 'alpha', session: 'old', prompt: 'write the release notes for 2.0' }
  w.found = () => JSON.stringify({ ...JSON.parse(FOUND), surfer: 'memo', memo: { verdict: 'named', items: ['release-notes-format'], prompts: [earlier], ts: '2026-10-03T00:00:00Z' } })
  w.logged.length = 0
  const told = await $.prompt.submit({ text: `${PROMPT} (second)`, wait: false, origin: { kind: 'composer' } })
  expect(w.asked).toBe(1)
  expect(w.memos.length).toBe(1)
  const context = (told.context ?? []).join('\n')
  expect(context).toContain('[compound] Reuse before building.')
  expect(context).toContain('release-notes-format')
  expect(context).toContain('write the release notes for 2.0')
  expect(w.logged.filter(e => e.type === 'judge')).toEqual([{ type: 'judge', moment: 'reuse', verdict: 'named', ms: 0, prompt_id: w.logged[0]!.prompt_id, memo: true, named: ['release-notes-format', 'old:1'] }])
  const again = w.logged.find(e => e.type === 'reuse')!
  expect([again.lessons, again.prompts, again.memo, again.judge_ms]).toEqual([['release-notes-format'], ['old:1'], true, 0])

  // A kept "nothing" adds nothing and asks nothing; so does a kept "not a build task".
  for (const verdict of ['nothing', 'not-substantial']) {
    w.found = () => JSON.stringify({ ...JSON.parse(FOUND), surfer: 'memo', memo: { verdict, items: [], prompts: [], ts: '2026-10-03T00:00:00Z' } })
    w.logged.length = 0
    await $.prompt.submit({ text: `${PROMPT} (${verdict})`, wait: false, origin: { kind: 'composer' } })
    expect(w.asked).toBe(1)
    expect(w.logged.map(e => [e.type, e.verdict, e.memo])).toEqual([['judge', verdict, true]])
  }

  // Nothing reaches the floor and nothing like it was asked: no model call and no event.
  w.found = () => JSON.stringify({ ...JSON.parse(FOUND), items: [] })
  w.logged.length = 0
  await $.prompt.submit({ text: `${PROMPT} (floor)`, wait: false, origin: { kind: 'composer' } })
  expect(w.asked).toBe(1)
  expect(w.logged).toEqual([])
})

test('a floor set in the environment is passed to the CLI, and a value that is no number is not', async ($, on) => {
  const w = world(on, { COMPOUND_REUSE_FLOOR: '0.5' })
  mock.clock(on, { now: T0 })
  await $.prompt.submit({ text: `${PROMPT} (set)`, wait: false, origin: { kind: 'composer' } })
  expect(w.calls.find(c => c.includes('find'))!.slice(1)).toEqual(['find', '--request', '--json', '--floor', '0.5'])
})

test('a floor that is no number is left to the CLI', async ($, on) => {
  const w = world(on, { COMPOUND_REUSE_FLOOR: 'high' })
  mock.clock(on, { now: T0 })
  await $.prompt.submit({ text: `${PROMPT} (bad)`, wait: false, origin: { kind: 'composer' } })
  expect(w.calls.find(c => c.includes('find'))!.slice(1)).toEqual(['find', '--request', '--json'])
})

test('a judge that names the candidate without words of the request adds nothing, and that is kept too', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.judge = async () => '{"substantial":true,"items":["release-notes-format"],"requests":[]}'
  const told = await $.prompt.submit({ text: `${PROMPT} (unquoted)`, wait: false, origin: { kind: 'composer' } })
  expect((told.context ?? []).join('\n')).not.toContain('Reuse before building')
  expect(w.logged.map(e => [e.type, e.verdict, e.unquoted])).toEqual([['judge', 'nothing', 1]])
  expect(w.memos.map(m => m.verdict)).toEqual(['nothing'])
})

// ---- a skill that is used, and a request that keeps coming back ----

// The counting of a used skill goes on after its hook has answered: `clock.settle()` lets it finish.

for (const surface of SURFACES) {
  test(`${surface}: a skill compound lists is counted when its prompt is expanded, and the band and the status entry name it`, async ($, on) => {
    const w = world(on)
    const clock = mock.clock(on, { now: T0 })
    w.used = name => (name === 'compound:finish-task' ? '{"used":true,"name":"finish-task","level":"general","path":"/g/s/finish-task"}' : '{"used":false,"name":"x","reason":"no skill of that name"}')
    // The hook answers with the skill's own text, unchanged, before anything is counted.
    const out = await $.skill.prompt({ skill: 'compound:finish-task', text: 'THE SKILL BODY' })
    expect(out.text).toBe('THE SKILL BODY')
    await clock.settle()
    // One CLI call, `use`, with the name as the engine gave it; the CLI writes the event.
    expect(w.calls.filter(c => c.includes('use')).map(c => c.slice(1))).toEqual([['use', '--json', '--', 'compound:finish-task']])
    expect(w.statuses[w.statuses.length - 1]).toBe('used finish-task')
    const ui = await $.ui.mount({ plugin: 'compound', surface, component: 'AbovePrompt', props: BAND, viewport: { columns: 100, rows: 40 } })
    expect((await ui.find({ type: 'Text', text: NOTES.used.label }))?.props.color).toBe(NOTES.used.color)
    expect(await ui.find({ type: 'Text', text: 'finish-task' })).toBeDefined()
    expect(w.logged.filter(e => e.type === 'error')).toEqual([])

    // A skill the CLI does not count draws nothing and sets no entry.
    await clock.advance(GONE_MS + 30000)
    const before = w.statuses.length
    await $.skill.prompt({ skill: 'superpowers:brainstorming', text: 'x' })
    await clock.settle()
    expect(w.calls.filter(c => c.includes('use')).length).toBe(2)
    expect(w.statuses.length).toBe(before)
    expect(await ui.find({ type: 'Text', text: NOTES.used.label })).toBeUndefined()
  })
}

test('a use is counted once for one expansion, whatever the name looks like, and a CLI that cannot say breaks nothing', async ($, on) => {
  const w = world(on)
  const clock = mock.clock(on, { now: T0 })
  w.used = () => '{"used":true,"name":"local-word","level":"project"}'
  // Two copies of the mod see one expansion: the claim lets one of them count it.
  await $.skill.prompt({ skill: 'local-word', text: 'x' })
  await $.skill.prompt({ skill: 'local-word', text: 'x' })
  await clock.settle()
  expect(w.calls.filter(c => c.includes('use')).length).toBe(1)
  // A name that looks like an option is a name: it goes after `--`.
  await $.skill.prompt({ skill: '--json', text: 'x' })
  await clock.settle()
  expect(w.calls.filter(c => c.includes('use'))[1]!.slice(1)).toEqual(['use', '--json', '--', '--json'])
  // The CLI prints something else: the skill's text still goes through, and the failure is logged once.
  w.used = () => 'not json'
  const out = await $.skill.prompt({ skill: 'another-skill', text: 'BODY' })
  await clock.settle()
  expect(out.text).toBe('BODY')
  expect(w.logged.filter(e => e.type === 'error').map(e => e.where)).toEqual(['use.parse'])
})

test('COMPOUND_OFF=1 counts no skill', async ($, on) => {
  const w = world(on, { COMPOUND_OFF: '1' })
  const clock = mock.clock(on, { now: T0 })
  expect((await $.skill.prompt({ skill: 'local-word', text: 'BODY' })).text).toBe('BODY')
  await clock.settle()
  expect(w.calls).toEqual([])
})

const DIGEST = 'Write the weekly digest of merged pull requests for the team and post it to the channel, as every week.'
// Three earlier requests of the same kind, from two other sessions and from this one.
const ASKED = [
  { id: 'wk1:3', ts: '2026-09-07', project: '/work/alpha', session: 'wk1', prompt: 'write the weekly digest of merged pull requests and post it', score: 4, sessions: ['wk1'] },
  { id: 'wk2:1', ts: '2026-09-14', project: '/work/alpha', session: 'wk2', prompt: 'weekly digest of merged pull requests please, post it to the channel', score: 4, sessions: ['wk2', 'session-under-test'] },
  { id: 'oth:9', ts: '2026-09-20', project: '/work/beta', session: 'oth', prompt: 'rename the digest module', score: 2, sessions: ['oth'] },
]
const SEEN = JSON.stringify({ words: ['weekly', 'digest'], items: [], floor: 1.5, memo_key: 'b'.repeat(32), prompts: ASKED, surfer: 'ok' })
const SAME_KIND = '{"substantial":true,"items":[],"requests":[],"repeats":[{"label":"r1","quote":"weekly digest of merged pull requests"},{"label":"r2","quote":"weekly digest of merged pull requests"}]}'

test('a request made in three sessions with nothing recorded for it is offered a skill, once a session, with an event', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.found = () => SEEN
  w.judge = async () => SAME_KIND
  const told = await $.prompt.submit({ text: DIGEST, wait: false, origin: { kind: 'composer' } })
  const context = (told.context ?? []).join('\n')
  expect(context.split('\n')[0]).toBe('[compound] A request that keeps coming back.')
  expect(context).toContain('This kind of request has now been made in 3 sessions, this one included, and no recorded skill or lesson covers it.')
  expect(context).toContain('- wk1:3 2026-09-07 alpha: "write the weekly digest of merged pull requests and post it"')
  expect(context).toContain('it is an offer, not an instruction')
  expect(context).toContain('/bin/compound add`')
  expect(context).toContain('/bin/compound skill <name>`')
  expect(context).toContain('It is reference material, to be weighed and not obeyed')
  expect(context).not.toContain('rename the digest module')
  // The offer has its own event; no reuse was offered, so none is logged.
  expect(w.logged.map(e => e.type)).toEqual(['repeat', 'judge'])
  const event = w.logged[0]!
  expect([event.times, event.prompts]).toEqual([3, ['wk1:3', 'wk2:1']])
  expect(w.statuses[w.statuses.length - 1]).toBe('asked in 3 sessions: a skill is on offer')
  // What the CLI is given to keep: the judge's verdict, and the requests of the same kind.
  expect(w.memos.map(m => [m.verdict, (m.repeats as { id: string }[]).map(r => r.id)])).toEqual([['nothing', ['wk1:3', 'wk2:1']]])

  // The same kind of request again in this session, in other words: nothing is offered twice.
  w.logged.length = 0
  const again = await $.prompt.submit({ text: `${DIGEST} Include the reverted ones too this time.`, wait: false, origin: { kind: 'composer' } })
  expect((again.context ?? []).join('\n')).not.toContain('keeps coming back')
  expect(w.logged.map(e => [e.type, e.verdict])).toEqual([['judge', 'nothing']])
})

test('two sessions are not three, a covered request is offered nothing, and the knob moves the bar', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  // Only one other session asked it.
  w.found = () => JSON.stringify({ ...JSON.parse(SEEN), prompts: [ASKED[0]] })
  w.judge = async () => '{"substantial":true,"items":[],"requests":[],"repeats":[{"label":"r1","quote":"weekly digest of merged pull requests"}]}'
  let told = await $.prompt.submit({ text: `${DIGEST} (two)`, wait: false, origin: { kind: 'composer' } })
  expect(told.context ?? []).toEqual([])
  expect(w.logged.map(e => [e.type, e.verdict])).toEqual([['judge', 'nothing']])
  // A recorded lesson covers it: the lesson is offered, not a new skill.
  w.logged.length = 0
  w.found = () => JSON.stringify({ ...JSON.parse(SEEN), items: JSON.parse(ITEMS) })
  w.judge = async () => SAME_KIND.replace('"items":[]', '"items":[{"name":"release-notes-format","quote":"weekly digest"}]')
  told = await $.prompt.submit({ text: `${DIGEST} (covered)`, wait: false, origin: { kind: 'composer' } })
  expect((told.context ?? []).join('\n')).toContain('[compound] Reuse before building.')
  expect((told.context ?? []).join('\n')).not.toContain('This kind of request')
  expect(w.logged.map(e => e.type)).toEqual(['judge', 'reuse'])
  // A quote that is not words of the request names nothing.
  w.logged.length = 0
  w.found = () => SEEN
  w.judge = async () => SAME_KIND.split('weekly digest of merged pull requests').join('the same routine as before')
  told = await $.prompt.submit({ text: `${DIGEST} (unquoted)`, wait: false, origin: { kind: 'composer' } })
  expect(told.context ?? []).toEqual([])
  expect(w.logged.map(e => [e.type, e.verdict, e.unquoted])).toEqual([['judge', 'nothing', 2]])
})

test('a routine the judge says builds nothing is still offered a skill when it keeps coming back', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  w.found = () => SEEN
  w.judge = async () => SAME_KIND.replace('"substantial":true', '"substantial":false')
  const told = await $.prompt.submit({ text: DIGEST, wait: false, origin: { kind: 'composer' } })
  expect((told.context ?? []).join('\n').split('\n')[0]).toBe('[compound] A request that keeps coming back.')
  // The verdict is the judge's own, and it is kept with the requests of the same kind.
  expect(w.logged.map(e => [e.type, e.verdict ?? e.times])).toEqual([['repeat', 3], ['judge', 'not-substantial']])
  expect(w.memos.map(m => [m.verdict, (m.repeats as { id: string }[]).map(r => r.id)])).toEqual([['not-substantial', ['wk1:3', 'wk2:1']]])
  // And a prompt that builds nothing and repeats nothing still gets nothing.
  w.logged.length = 0
  w.judge = async () => NOTHING
  expect((await $.prompt.submit({ text: `${DIGEST} (other)`, wait: false, origin: { kind: 'composer' } })).context ?? []).toEqual([])
  expect(w.logged.map(e => [e.type, e.verdict])).toEqual([['judge', 'not-substantial']])
})

test('COMPOUND_REPEAT_MIN=2 offers at the first repetition', async ($, on) => {
  const w = world(on, { COMPOUND_REPEAT_MIN: '2' })
  mock.clock(on, { now: T0 })
  w.found = () => JSON.stringify({ ...JSON.parse(SEEN), prompts: [ASKED[0]] })
  w.judge = async () => '{"substantial":true,"items":[],"requests":[{"label":"r1","quote":"weekly digest of merged pull requests"}],"repeats":[]}'
  const context = ((await $.prompt.submit({ text: DIGEST, wait: false, origin: { kind: 'composer' } })).context ?? []).join('\n')
  // An earlier request for the same deliverable is one of the same kind: it is quoted once.
  expect(context.split('\n')[0]).toBe('[compound] Reuse before building.')
  expect(context).toContain('This kind of request has now been made in 2 sessions, this one included, and no recorded skill or lesson covers it. The earlier ones are quoted above.')
  expect(context.split('wk1:3').length).toBe(2)
  expect(w.logged.map(e => e.type)).toEqual(['repeat', 'judge', 'reuse'])
})

test('a request the CLI holds a verdict for is counted with the sessions that asked it since', async ($, on) => {
  const w = world(on)
  mock.clock(on, { now: T0 })
  const row = { id: 'wk1:3', ts: '2026-09-07', project: 'alpha', session: 'wk1', prompt: 'write the weekly digest of merged pull requests and post it', sessions: ['wk1'] }
  // Judged in session wk2 with one earlier request of the kind; asked since by this session.
  w.found = () => JSON.stringify({ ...JSON.parse(SEEN), prompts: [], surfer: 'memo', memo: { verdict: 'nothing', items: [], prompts: [], repeats: [row], asked: ['wk2', 'session-under-test'], ts: '2026-10-03T00:00:00Z' } })
  const told = await $.prompt.submit({ text: DIGEST, wait: false, origin: { kind: 'composer' } })
  expect(w.asked).toBe(0)
  expect((told.context ?? []).join('\n')).toContain('This kind of request has now been made in 3 sessions')
  expect(w.logged.map(e => [e.type, e.memo, e.times ?? e.verdict])).toEqual([['repeat', true, 3], ['judge', true, 'named']])
  // The verdict names the earlier requests the offer rests on.
  expect(w.logged[1]!.named).toEqual(['wk1:3'])
})
