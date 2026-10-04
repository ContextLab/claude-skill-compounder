import { expect, test } from 'claude-code/testing'
import { bodyOf, debts, mayNudge, otherProjects, parseEarlier, parseEvents, parseHits, parseInventory, parseShow, parseTimedOut, seconds, type Event } from './store'

test('the inventory is the list the CLI prints, with unknown rows dropped', async () => {
  const out = JSON.stringify([
    { level: 'project', kind: 'lesson', name: 'a', description: 'Use when A.', path: '/p/a', match: ['^x'], counts: { recall: 1 }, ineffective: false },
    { level: 'user', kind: 'skill', name: 'b', description: 'Use when B.', path: '/u/b', match: [] },
    { level: 'project', kind: 'script', name: 'scripts/c.sh', description: '', path: '/p/scripts/c.sh', match: [] },
    { level: 'project', kind: 'widget', name: 'd' },
    { level: 'project', kind: 'lesson' },
    'not a row',
  ])
  const items = parseInventory(out)
  expect(items?.map(i => `${i.kind}:${i.name}`)).toEqual(['lesson:a', 'skill:b', 'script:scripts/c.sh'])
  expect(items?.[0]?.match).toEqual(['^x'])
  expect(parseInventory('[]')).toEqual([])
})

test('inventory output that is not a list is unreadable', async () => {
  for (const bad of ['', 'nothing recorded yet', '{"error":"x"}', '42', '[1,']) expect(parseInventory(bad)).toBe(undefined)
})

test('guard hits are read from {"hits":[...]}, and anything else is unreadable', async () => {
  expect(parseHits('{"hits":[{"name":"z","level":"user","path":"/u/z","text":"Quote it."},{"level":"user"}]}')).toEqual([{ name: 'z', level: 'user', path: '/u/z', text: 'Quote it.' }])
  expect(parseHits('{"hits":[]}')).toEqual([])
  for (const bad of ['', '[]', '{"hits":"none"}', '{}']) expect(parseHits(bad)).toBe(undefined)
})

const FOUND = JSON.stringify({
  words: ['release'],
  items: [],
  prompts: [
    { id: 'p1', ts: '2026-09-30T10:00:00Z', project: '/Users/me/alpha', scope: 'project', score: 1, prompt: 'write a release script' },
    { id: 'p2', ts: '2026-09-29T10:00:00Z', project: '/Users/me/beta', scope: 'all', score: 1, prompt: 'the   prompt typed\njust now' },
    { id: 'p3', ts: '2026-09-28T10:00:00Z', project: '/Users/me/beta', scope: 'all', score: 1, prompt: 'write a release script' },
    { id: 'p4', ts: '2026-09-27T10:00:00Z', project: '', scope: 'all', score: 1, prompt: 'tag the release' },
    { id: 'p5', ts: '2026-09-26T10:00:00Z', project: '/x', scope: 'all', score: 1, prompt: 'release notes' },
    { id: 'p6', ts: '2026-09-25T10:00:00Z', project: '/x', scope: 'all', score: 1, prompt: 'one more release' },
  ],
  surfer: 'ok',
})

test('earlier requests drop this session\'s own prompts and repeats, and stop at the cap', async () => {
  const earlier = parseEarlier(FOUND, 's1', ['the prompt typed just now'], 3)
  expect(earlier?.map(e => e.id)).toEqual(['p1', 'p4', 'p5'])
  expect(earlier?.[0]).toEqual({ id: 'p1', date: '2026-09-30', project: 'alpha', session: '', text: 'write a release script', score: 1 })
})

test('a logged prompt that shares fewer words than asked is not a candidate; one with no score is kept', async () => {
  const out = JSON.stringify({ prompts: [
    { id: 'a', score: 1, prompt: 'shares one word' },
    { id: 'b', score: 3, prompt: 'shares three words' },
    { id: 'c', prompt: 'the CLI gave no score' },
    { id: 'd', score: 2, prompt: 'shares two words' },
  ] })
  expect(parseEarlier(out, 's1', [], 5, 2)?.map(e => e.id)).toEqual(['b', 'c', 'd'])
  expect(parseEarlier(out, 's1', [], 5)?.map(e => e.id)).toEqual(['a', 'b', 'c', 'd'])
  expect(parseEarlier(out, 's1', [], 5, 2)?.[0]?.score).toBe(3)
})

test('the lessons whose pattern the check gave up on are read as names or as rows', async () => {
  expect(parseTimedOut('{"hits":[],"timed_out":["slow-one",{"name":"slow-two"},7,{}]}')).toEqual(['slow-one', 'slow-two'])
  expect(parseTimedOut('{"hits":[]}')).toEqual([])
  expect(parseTimedOut('not json')).toEqual([])
})

test('a row that names its session is dropped when it is the current one', async () => {
  const out = JSON.stringify({ prompts: [{ id: 'a', session: 's1', prompt: 'mine' }, { id: 'b', session: 's2', prompt: 'theirs' }] })
  expect(parseEarlier(out, 's1', [], 3)?.map(e => e.id)).toEqual(['b'])
})

test('find output with no prompt list is no earlier request, and non-JSON is unreadable', async () => {
  expect(parseEarlier('{"words":[],"items":[],"surfer":"missing"}', 's1', [], 3)).toEqual([])
  expect(parseEarlier('no lesson, skill or script matches', 's1', [], 3)).toBe(undefined)
  expect(parseEarlier('[]', 's1', [], 3)).toBe(undefined)
})

test('a shown lesson is its body, its recall count and the CLI\'s verdict', async () => {
  const skill = '---\nname: a\ndescription: Use when A.\n---\nDo the thing.\nSecond line.\n'
  expect(bodyOf(skill)).toBe('Do the thing.\nSecond line.')
  expect(bodyOf('no frontmatter here')).toBe('no frontmatter here')
  const shown = parseShow(JSON.stringify({ name: 'a', level: 'user', path: '/u/a', text: skill, counts: { reuse: 0, guard: 0, recall: 3, learn: 1 }, ineffective: true }))
  expect(shown).toEqual({ text: 'Do the thing.\nSecond line.', path: '/u/a', level: 'user', recalls: 3, ineffective: true })
  expect(parseShow('a (user lesson)\n/u/a\n')).toEqual({ text: 'a (user lesson)\n/u/a', path: '', level: '', recalls: 0, ineffective: undefined })
})

test('events are read from a list or from one object per line', async () => {
  expect(parseEvents('[{"type":"learn","ts":"2026-10-03T00:00:00Z"},{"no":"type"}]')?.length).toBe(1)
  expect(parseEvents('{"type":"skip"}\n{"type":"learn"}\n')?.map(e => e.type)).toEqual(['skip', 'learn'])
  expect(parseEvents('[]')).toEqual([])
  expect(parseEvents('')).toEqual([])
  expect(parseEvents('compound: error')).toBe(undefined)
})

test('an event time is read from ISO text, seconds or milliseconds', async () => {
  expect(seconds({ type: 'x', ts: '2026-10-03T00:00:00Z' })).toBe(Date.UTC(2026, 9, 3) / 1000)
  expect(seconds({ type: 'x', ts: 1790000000 })).toBe(1790000000)
  expect(seconds({ type: 'x', ts: 1790000000000 })).toBe(1790000000)
  expect(seconds({ type: 'x', ts: '1790000000' })).toBe(1790000000)
  expect(seconds({ type: 'x', ts: 'yesterday' })).toBe(0)
  expect(seconds({ type: 'x' })).toBe(0)
})

const cap = (call: string): Event => ({ type: 'capture', tool: 'Bash', failed: `f-${call}`, error: `e-${call}`, fixed: `x-${call}`, call })

test('a capture is owed until a learn or a skip comes after it', async () => {
  expect(debts([])).toEqual([])
  expect(debts([cap('1')]).map(d => d.key)).toEqual(['1'])
  expect(debts([cap('1'), { type: 'learn', lesson: 'a' }])).toEqual([])
  expect(debts([cap('1'), { type: 'skip', why: 'typo' }])).toEqual([])
  expect(debts([{ type: 'learn', lesson: 'a' }, cap('1')]).map(d => d.key)).toEqual(['1'])
  expect(debts([cap('1'), { type: 'learn', lesson: 'a' }, cap('2'), { type: 'reuse' }, cap('3')]).map(d => d.key)).toEqual(['2', '3'])
  expect(debts([cap('1')])[0]).toEqual({ key: '1', tool: 'Bash', failed: 'f-1', error: 'e-1', fixed: 'x-1' })
})

test('a capture with no call id is keyed on its time', async () => {
  expect(debts([{ type: 'capture', ts: '2026-10-03T00:00:00Z' }])[0]?.key).toBe('2026-10-03T00:00:00Z')
})

test('other projects\' lessons come from learn events, newest project first, minus what is already here', async () => {
  const learn = (lesson: string, project: string, level = 'project', kind = 'lesson'): Event => ({ type: 'learn', lesson, project, level, kind })
  const events = [learn('a', '/p/one'), learn('b', '/p/two'), learn('c', '/p/one'), learn('u', '/p/one', 'user'), learn('s', '/p/one', 'project', 'skill'), learn('here', '/p/three'), { type: 'recall', lesson: 'a', project: '/p/four' }]
  expect(otherProjects(events, new Set(['here']), 6)).toEqual([{ project: '/p/one', names: ['c', 'a'] }, { project: '/p/two', names: ['b'] }])
  expect(otherProjects(events, new Set(['here']), 1)).toEqual([{ project: '/p/one', names: ['c', 'a'] }])
  expect(otherProjects([], new Set(), 6)).toEqual([])
})

test('a long turn is asked only when nothing was recorded in it and the last nudge anywhere is old', async () => {
  const at = (type: string, s: number, session = 's1'): Event => ({ type, ts: s, session })
  expect(mayNudge([], 1000, 2000, 1800, [])).toBe(true)
  expect(mayNudge([at('learn', 900)], 1000, 2000, 1800, [])).toBe(true)
  expect(mayNudge([at('learn', 1500)], 1000, 2000, 1800, [])).toBe(false)
  expect(mayNudge([at('skip', 1500)], 1000, 2000, 1800, [])).toBe(false)
  expect(mayNudge([at('capture', 1500)], 1000, 2000, 1800, [])).toBe(false)
  // The cooldown is global: a nudge in ANOTHER session, which this session's rows do not hold, counts.
  expect(mayNudge([], 1000, 2000, 1800, [at('nudge', 500, 'another-session')])).toBe(false)
  expect(mayNudge([], 1000, 2000, 1800, [at('nudge', 100, 'another-session')])).toBe(true)
  expect(mayNudge([], 1000, 2000, 0, [at('nudge', 1999, 'another-session')])).toBe(true)
  // Only `nudge` rows count there, whatever the CLI was asked for.
  expect(mayNudge([], 1000, 2000, 1800, [at('reuse', 1999)])).toBe(true)
})
