import { expect, test } from 'claude-code/testing'
import {
  callText, captureContext, changesStore, cliCall, digest, errorReport, errorStatus, guarded, guardReason, inputOf, isCommand, judged,
  knownContext, recallContext, reusable, reuseContext, reuseStatus, stopDebt, stopNudge, typedByUser, userOrigin, worthChecking,
} from './render'
import type { Item } from './store'

const CLI = '/opt/compound/bin/compound'
const LESSON: Item = { kind: 'lesson', name: 'build-needs-profile', level: 'project', description: 'Use when running ./build.sh.', path: '/p/.claude/compound/lessons/build-needs-profile', match: [] }

// ---- who typed it ----

test('a slash command is one word after the slash; a path is not a command', async () => {
  for (const c of ['/compact', '/compound:learn', '/model sonnet', '/history-surfer x']) expect(isCommand(c)).toBe(true)
  for (const c of ['/Users/me/proj/parser.py is the file to fix', '/ 2', 'run /compact', '//x']) expect(isCommand(c)).toBe(false)
})

test('a harness frame on the prompt channel was not typed by the user', async () => {
  for (const framed of [
    '<task-notification>\n<task-id>a1</task-id>',
    '<agent-message from="worker">done</agent-message>',
    '  <system-reminder>note</system-reminder>',
    '<local-command-stdout>ok</local-command-stdout>',
    '[SYSTEM NOTIFICATION - background task finished]',
    '[Request interrupted by user]',
    'Another Claude session sent a message: hi',
  ]) {
    expect(typedByUser(framed)).toBe(false)
  }
  for (const typed of ['<div> is not centred, fix the CSS', 'fix the <task-notification> parser', 'please build it', '[x] is checked']) {
    expect(typedByUser(typed)).toBe(true)
  }
})

test('only a person\'s origins count as typed', async () => {
  for (const k of ['composer', 'bridge', 'sdk', 'unclassified', undefined]) expect(userOrigin(k)).toBe(true)
  for (const k of ['task-notification', 'peer', 'plugin', 'scheduled-trigger', 'coordinator', 'auto-continuation']) expect(userOrigin(k)).toBe(false)
})

test('the reuse check looks at long typed prompts and nothing else', async () => {
  const long = 'Please write a script that tags a release, updates the changelog and pushes it to the remote.'
  expect(worthChecking(long, 'composer', 80)).toBe(true)
  expect(worthChecking(long, 'task-notification', 80)).toBe(false)
  expect(worthChecking(`/compact ${long}`, 'composer', 80)).toBe(false)
  expect(worthChecking(`<task-notification>${long}`, 'composer', 80)).toBe(false)
  expect(worthChecking('yes do it', 'composer', 80)).toBe(false)
  expect(worthChecking(`   ${'x'.repeat(79)}   `, 'composer', 80)).toBe(false)
  expect(worthChecking('x'.repeat(80), 'composer', 80)).toBe(true)
})

test('the package\'s own two skills are not offered for reuse', async () => {
  const items = [
    { kind: 'skill', level: 'general', name: 'learn' },
    { kind: 'skill', level: 'general', name: 'reuse' },
    { kind: 'skill', level: 'user', name: 'learn' },
    { kind: 'lesson', level: 'general', name: 'reuse' },
    { kind: 'skill', level: 'general', name: 'other' },
  ]
  expect(reusable(items).length).toBe(3)
  expect(reusable(items.slice(0, 2))).toEqual([])
})

// ---- tool calls ----

test('read-only and bookkeeping tools are never guarded or judged; edit slips are guarded and not judged', async () => {
  for (const t of ['Read', 'Glob', 'Grep', 'TodoWrite', 'TaskUpdate', 'Skill', 'AskUserQuestion']) {
    expect(guarded(t)).toBe(false)
    expect(judged(t)).toBe(false)
  }
  for (const t of ['Edit', 'Write', 'NotebookEdit']) {
    expect(guarded(t)).toBe(true)
    expect(judged(t)).toBe(false)
  }
  for (const t of ['Bash', 'WebFetch', 'mcp__github__create_issue', 'Agent']) {
    expect(guarded(t)).toBe(true)
    expect(judged(t)).toBe(true)
  }
})

test('a call\'s input is its arguments, and its text is the command or the tool and its JSON, masked', async () => {
  const e = { tool: 'Bash', tool_use_id: 'toolu_1', agentId: 'a1', command: 'DEPLOY_TOKEN=abc123def456 ./build.sh', description: 'build' }
  expect(inputOf(e)).toEqual({ command: 'DEPLOY_TOKEN=abc123def456 ./build.sh', description: 'build' })
  expect(callText('Bash', inputOf(e))).toBe('DEPLOY_TOKEN=<redacted> ./build.sh')
  expect(callText('WebFetch', { url: 'https://x.test', prompt: 'read' })).toBe('WebFetch {"url":"https://x.test","prompt":"read"}')
  const loop: Record<string, unknown> = {}
  loop.self = loop
  expect(callText('Odd', loop)).toBe('Odd (arguments could not be serialised)')
})

test('the CLI\'s own calls are recognised by verb, and only some change the store', async () => {
  expect(cliCall(`/opt/compound/bin/compound add --name x --when y <<'EOF'\nbody\nEOF`)).toBe('add')
  expect(cliCall('compound skip --why "typo"')).toBe('skip')
  expect(cliCall('cd /tmp && compound promote x --to user')).toBe('promote')
  expect(cliCall('"/path with space/bin/compound" find release')).toBe('find')
  for (const other of ['docker compound up', 'echo compound interest add', 'ls bin/compound', 'compounding add', './build.sh --profile dev']) {
    expect(cliCall(other)).toBe(undefined)
  }
  for (const v of ['add', 'promote', 'skill', 'rm', 'update']) expect(changesStore(v)).toBe(true)
  for (const v of ['skip', 'find', 'list', 'status', undefined]) expect(changesStore(v)).toBe(false)
})

test('a digest is stable, eight hex digits, and differs for different text', async () => {
  expect(digest('abc')).toBe(digest('abc'))
  expect(/^[0-9a-f]{8}$/.test(digest('abc'))).toBe(true)
  expect(digest('abc') === digest('abd')).toBe(false)
  expect(/^[0-9a-f]{8}$/.test(digest(''))).toBe(true)
})

// ---- messages ----

test('the reuse message lists items and earlier requests, and names the CLI by its path', async () => {
  const text = reuseContext(
    [{ kind: 'skill', name: 'cdl-bib-cite', level: 'user', description: 'fills a placeholder citation', path: '/u/skills/cdl-bib-cite', match: [] }, { kind: 'script', name: 'scripts/release.sh', level: 'project', description: '', path: '/p/scripts/release.sh', match: [] }],
    [{ id: 'p1', date: '2026-09-30', project: 'alpha', session: '', text: 'write a\nrelease script' }],
    CLI,
  )
  const lines = text.split('\n')
  expect(lines[0]).toBe('[compound] Reuse before building.')
  expect(lines[1]).toBe('Existing work that covers part of this request:')
  expect(lines[2]).toBe('- skill cdl-bib-cite (user): fills a placeholder citation -> /u/skills/cdl-bib-cite')
  expect(lines[3]).toBe('- script scripts/release.sh (project):  -> /p/scripts/release.sh')
  expect(lines[5]).toBe('- p1 2026-09-30 alpha: "write a release script"')
  expect(text.includes('Use these, or broaden one so it also covers this case. Build new only what none covers.')).toBe(true)
  expect(text.includes(`compound CLI: ${CLI}`)).toBe(true)
})

test('with nothing to reuse and no earlier request the reuse message is empty', async () => {
  expect(reuseContext([], [], CLI)).toBe('')
  expect(reuseContext([], [{ id: 'p1', date: '', project: '', session: '', text: 'x' }], CLI).includes('- p1: "x"')).toBe(true)
  expect(reuseStatus(2, 1)).toBe('compound: 2 reusable')
  expect(reuseStatus(0, 1)).toBe('compound: 1 earlier request')
  expect(reuseStatus(0, 3)).toBe('compound: 3 earlier requests')
})

test('a guard refusal carries the lesson and says the same call sent again will run', async () => {
  const text = guardReason([{ name: 'zsh-equals-word', level: 'user', path: '/u/lessons/zsh-equals-word', text: 'Quote it or use printf.' }], CLI)
  expect(text.includes('Lesson zsh-equals-word (user) at /u/lessons/zsh-equals-word:\nQuote it or use printf.')).toBe(true)
  expect(text.includes('send the same call again and it will run')).toBe(true)
  expect(text.includes(CLI)).toBe(true)
})

test('a recalled lesson is quoted, and an ineffective one carries the instruction to strengthen it', async () => {
  const plain = recallContext(LESSON, 'Run ./build.sh --profile dev.', 1, false, CLI)
  expect(plain.includes('A recorded lesson matches this failure: build-needs-profile (project)')).toBe(true)
  expect(plain.includes('Run ./build.sh --profile dev.')).toBe(true)
  expect(plain.includes('Strengthen')).toBe(false)
  const weak = recallContext(LESSON, 'Run ./build.sh --profile dev.', 3, true, CLI)
  expect(weak.includes('recalled 3 times AFTER the failure it describes')).toBe(true)
  expect(weak.includes('Strengthen this lesson now')).toBe(true)
  expect(weak.includes(`${CLI} add --update --name build-needs-profile`)).toBe(true)
  expect(weak.includes('--match')).toBe(true)
  expect(knownContext(LESSON, 'Run it.', 2, true, CLI).includes('already recorded as lesson build-needs-profile')).toBe(true)
})

test('a capture quotes the three texts word for word and names the skill and the way to decline', async () => {
  const text = captureContext({ failed: './build.sh', error: 'error: a profile is required', fixed: './build.sh --profile dev' }, CLI)
  expect(text.includes('THE CALL THAT FAILED:\n./build.sh\n')).toBe(true)
  expect(text.includes('ITS ERROR:\nerror: a profile is required\n')).toBe(true)
  expect(text.includes('THE CALL THAT WORKED:\n./build.sh --profile dev\n')).toBe(true)
  expect(text.includes('compound:learn')).toBe(true)
  expect(text.includes(`${CLI} skip --why "<reason>"`)).toBe(true)
})

test('a stop refusal restates each debt and says exactly what settles it', async () => {
  const one = stopDebt([{ key: '1', tool: 'Bash', failed: './build.sh', error: 'a profile is required', fixed: './build.sh --profile dev' }], CLI)
  expect(one.includes('This session owes a lesson')).toBe(true)
  expect(one.includes('THE CALL THAT FAILED:\n./build.sh\nITS ERROR:\na profile is required\nTHE CALL THAT WORKED:\n./build.sh --profile dev')).toBe(true)
  expect(one.includes('use the compound:learn skill')).toBe(true)
  expect(one.includes(`run ${CLI} skip --why "<reason>"`)).toBe(true)
  const two = stopDebt([{ key: '1', tool: 'Bash', failed: 'a', error: 'b', fixed: 'c' }, { key: '2', tool: 'Bash', failed: 'd', error: 'e', fixed: 'f' }], CLI)
  expect(two.includes('This session owes 2 lessons')).toBe(true)
  expect(two.includes('2. THE CALL THAT FAILED:\nd')).toBe(true)
})

test('the long-turn question gives the count and is asked once', async () => {
  const text = stopNudge(31, CLI)
  expect(text.includes('This turn made 31 tool calls and recorded no lesson.')).toBe(true)
  expect(text.includes('This is asked once.')).toBe(true)
})

test('the error report lists each failure on one masked line and caps the list', async () => {
  const text = errorReport([{ where: 'reuse.parse', message: 'unreadable\nanswer with API_KEY=abcdef123456' }], CLI)
  expect(text.includes('failed 1 time in this session')).toBe(true)
  expect(text.includes('- reuse.parse: unreadable answer with API_KEY=<redacted>')).toBe(true)
  expect(text.includes(`${CLI} status`)).toBe(true)
  const many = errorReport(Array.from({ length: 11 }, (_, i) => ({ where: `w${i}`, message: 'm' })), CLI)
  expect(many.includes('failed 11 times')).toBe(true)
  expect(many.includes('- ... and 3 more')).toBe(true)
  expect(errorStatus(1)).toBe('compound: 1 error')
  expect(errorStatus(2)).toBe('compound: 2 errors')
})
