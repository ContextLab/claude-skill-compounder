import { expect, test } from 'claude-code/testing'
import { excerpt, fixPrompt, parseFix, parseRecall, type Lesson } from './judge'

const ERROR = "Exit code 127\n(eval):4: command not found: timeout"
const KNOWN: Lesson[] = [{ id: 'n1', text: 'macOS has no timeout(1); use curl --max-time.', scope: 'global' }]

function reply(fields: Record<string, unknown>): string {
  return JSON.stringify({ same_goal: true, call_mistake: true, recurs: true, evidence: 'command not found: timeout', ...fields })
}
const LESSON = { verdict: 'LESSON', lesson: 'macOS has no timeout(1); pass curl --max-time instead.' }

test('a short text is passed whole and a long one keeps head and tail around a mark', async () => {
  expect(excerpt('abc', 10, 10)).toBe('abc')
  const cut = excerpt('a'.repeat(50) + 'b'.repeat(50), 10, 5)
  expect(cut.startsWith('aaaaaaaaaa\n[... 85 characters omitted here ...]\n')).toBe(true)
  expect(cut.endsWith('bbbbb')).toBe(true)
})

test('a lesson whose checks hold and whose evidence is in the error is a lesson', async () => {
  expect(parseFix(reply(LESSON), [], ERROR)).toEqual({ verdict: 'LESSON', lesson: LESSON.lesson })
})

test('a lesson is refused when its evidence is not in the error text', async () => {
  const v = parseFix(reply({ ...LESSON, evidence: 'the script was cut off mid-line' }), [], ERROR)
  expect(v).toEqual({ verdict: 'NONE', reason: 'evidence not found in the error' })
})

test('a lesson is refused when any one check is false', async () => {
  for (const check of ['same_goal', 'call_mistake', 'recurs']) {
    expect(parseFix(reply({ ...LESSON, [check]: false }), [], ERROR).verdict).toBe('NONE')
  }
})

test('KNOWN stands only for an id that is in the list it was given', async () => {
  expect(parseFix(reply({ verdict: 'KNOWN', id: 'n1' }), KNOWN, ERROR)).toEqual({ verdict: 'KNOWN', id: 'n1' })
  expect(parseFix(reply({ verdict: 'KNOWN', id: 'n9' }), KNOWN, ERROR).verdict).toBe('NONE')
})

test('a reply that is not JSON writes nothing', async () => {
  expect(parseFix('I think this is a lesson.', [], ERROR)).toEqual({ verdict: 'NONE', reason: 'unreadable reply' })
})

test('a recall answers a listed lesson, and nothing for null or an unlisted id', async () => {
  expect(parseRecall('{"id":"n1"}', KNOWN)?.id).toBe('n1')
  expect(parseRecall('{"id":null}', KNOWN)).toBeUndefined()
  expect(parseRecall('{"id":"n9"}', KNOWN)).toBeUndefined()
})

test('the prompt carries the existing lessons and marks a shortened call', async () => {
  const prompt = fixPrompt({ failed: 'x'.repeat(5000), error: ERROR, worked: 'curl --max-time 40 u' }, KNOWN)
  expect(prompt.includes('n1: macOS has no timeout(1)')).toBe(true)
  expect(prompt.includes('characters omitted here')).toBe(true)
  expect(prompt.includes('command not found: timeout')).toBe(true)
})
