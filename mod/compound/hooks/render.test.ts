import { expect, test } from 'claude-code/testing'
import { chosen, claimsDone, isCommand, lastSubstantive, mission, storeRows, substantive, typedByUser } from './render'

const LONG = 'please refactor the parser so that it handles nested quotes correctly'
const CHANGE = 'change of plan: keep the parser and rewrite only the tokenizer instead'

test('a prompt of fewer than six words is not substantive', async () => {
  expect(substantive('yes do it')).toBe(false)
  expect(substantive(LONG)).toBe(true)
})

test('a change of direction between short prompts is quoted, and the short ones are not', async () => {
  const rows = [LONG, CHANGE, 'continue', 'yes', 'ok do it'].map(text => ({ text }))
  expect(chosen(rows)).toEqual([0, 1])
  const text = mission(rows)
  expect(text.includes(`> ${CHANGE}`)).toBe(true)
  expect(text.includes('> continue')).toBe(false)
  expect(text.includes('5 recorded; 2 quoted below')).toBe(true)
})

test('with only one substantive request the last rows are quoted after it', async () => {
  expect(chosen([LONG, 'continue', 'yes'].map(text => ({ text })))).toEqual([0, 1, 2])
})

test('every line of a request carries the prefix, so a quote inside it closes nothing', async () => {
  const text = mission([{ text: 'he said "stop here"\n\nand then: build the "second" thing please' }])
  const body = text.split('\n').slice(3)
  expect(body.every(line => line.startsWith('> '))).toBe(true)
})

test('a request over its cap is cut with a marker that says how much is gone', async () => {
  const text = mission([{ text: `${'word '.repeat(400)}end` }])
  expect(text.includes('> [... 803 more chars]')).toBe(true)
})

test('what is skipped between quoted requests is counted, not silently dropped', async () => {
  const rows = [LONG, 'continue', CHANGE].map(text => ({ text }))
  expect(mission(rows).includes("[... 8 characters of this session's requests are not quoted here ...]")).toBe(true)
})

test('no rows is no mission', async () => {
  expect(mission([])).toBe('')
  expect(lastSubstantive([{ text: 'yes' }])).toBe('')
})

test('the last substantive request is the one a short prompt gets', async () => {
  const text = lastSubstantive([LONG, CHANGE, 'continue'].map(t => ({ text: t })))
  expect(text.includes('request 2 of 3')).toBe(true)
  expect(text.includes(`> ${CHANGE}`)).toBe(true)
})

test('a completion claim is read from the end of the message', async () => {
  expect(claimsDone('I ran the nine commands. All done.')).toBe(true)
  expect(claimsDone('Still working through the list.')).toBe(false)
})

test('store rows are this session only, with commands and empty prompts dropped', async () => {
  const raw = [
    { session_id: 's1', prompt: LONG },
    { session_id: 's2', prompt: 'another session' },
    { session_id: 's1', prompt: '/compact' },
    { session_id: 's1', prompt: 'config', is_command: true },
    { session_id: 's1', prompt: '   ' },
    { session_id: 's1', prompt: CHANGE },
  ].map(r => JSON.stringify(r)).join('\n')
  expect(storeRows(`${raw}\nnot json`, 's1').map(r => r.text)).toEqual([LONG, CHANGE])
})

test('a subagent hand-back or a task notice stored as a prompt is not a request', async () => {
  expect(typedByUser('<agent-message from="a7">\n[Subagent hand-back] The text below')).toBe(false)
  expect(typedByUser('<task-notification>\n<task-id>b1</task-id>')).toBe(false)
  expect(typedByUser('[SYSTEM NOTIFICATION - NOT USER INPUT]')).toBe(false)
  expect(typedByUser('ok, continue: build it!')).toBe(true)
  const raw = [
    { session_id: 's1', prompt: LONG },
    { session_id: 's1', prompt: '<agent-message from="a7">a very long report that is not a request at all' },
  ].map(r => JSON.stringify(r)).join('\n')
  expect(storeRows(raw, 's1').map(r => r.text)).toEqual([LONG])
})

// ---- found by the red team of 2026-10-03

test('the store holds a prompt once however many times history-surfer recorded it', async () => {
  const raw = [
    { session_id: 's1', seq: 1, source: 'stdin', prompt: LONG },
    { session_id: 's1', seq: 2, source: 'stdin', prompt: CHANGE },
    { session_id: 's1', seq: 3, source: 'transcript', prompt: CHANGE },
  ].map(r => JSON.stringify(r)).join('\n')
  expect(storeRows(raw, 's1').map(r => r.text)).toEqual([LONG, CHANGE])
})

test('a request that begins with a path is a request, and a slash command is not', async () => {
  const path = '/Users/nobody/proj/parser.py is the file I care about: fix the nested quotes'
  expect(isCommand(path)).toBe(false)
  expect(isCommand('/compact')).toBe(true)
  expect(isCommand('/compact focus on the parser')).toBe(true)
  expect(isCommand('/code-review ultra')).toBe(true)
  const raw = [{ session_id: 's1', prompt: path, is_command: true }, { session_id: 's1', prompt: '/clear' }]
    .map(r => JSON.stringify(r)).join('\n')
  expect(storeRows(raw, 's1').map(r => r.text)).toEqual([path])
})

test('a negated, interim or questioning message is not a completion claim', async () => {
  for (const no of [
    'I could not get this done.',
    'not finished and nothing is fixed yet',
    'Are you ready for me to start?',
    'The suite is not passing.',
    'Shall I mark it complete?',
    "I've completed the four echo commands and dispatched the subagent. Waiting for the subagent to complete.",
  ]) expect(claimsDone(no)).toBe(false)
  for (const yes of ['All done.', 'The fix is implemented and the suite passes.', 'Everything is complete.']) {
    expect(claimsDone(yes)).toBe(true)
  }
})

test('the request a short prompt gets is cut with a marker, never silently', async () => {
  const text = lastSubstantive([{ text: `${'word '.repeat(400)}DO NOT DELETE THE DATABASE` }])
  expect(text.includes('more chars]')).toBe(true)
})

test('a cut never leaves half of a character behind', async () => {
  const text = mission([{ text: `${'x'.repeat(1199)}\u{1F600}${' tail word'.repeat(20)}` }])
  expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/.test(text)).toBe(false)
})

test('a request with no spaces between its words is still substantive', async () => {
  expect(substantive('请把解析器重写成可以处理嵌套引号的版本并且补全所有测试')).toBe(true)
  expect(substantive('fix-the-parser-so-nested-quotes-work-and-add-tests')).toBe(true)
  expect(substantive('ok do it')).toBe(false)
})

test('every harness frame on the prompt channel is recognised, and typed markup is not', async () => {
  for (const frame of ['<local-command-stdout>x', '<command-name>/clear</command-name>', '[Request interrupted by user]',
    '<teammate-message from="b">hi']) expect(typedByUser(frame)).toBe(false)
  expect(typedByUser('<div> is the element I mean; please restyle it')).toBe(true)
})
