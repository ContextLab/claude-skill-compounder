import { expect, test } from 'claude-code/testing'
import { chosen, claimsDone, lastSubstantive, mission, storeRows, substantive } from './render'

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
