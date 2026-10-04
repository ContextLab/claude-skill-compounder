import { expect, test } from 'claude-code/testing'
import { bodyOf, learnedSince, mayNudge, parseGuards, parseGuardTools, parseLeft, parseMoved, parseOwed, parseUnsettled, settlers, otherProjects, askedTimes, memoOf, parseEarlier, parseUsed, parseEvents, parseFound, parseHits, parseInventory, parseShow, parseTimedOut, seconds, type Event } from './store'

test('the inventory is the list the CLI prints, with unknown rows dropped', async () => {
  const out = JSON.stringify([
    { level: 'project', kind: 'lesson', name: 'alpha', description: 'Use when A.', path: '/p/a', match: ['^x'], counts: { recall: 1 }, ineffective: false },
    { level: 'user', kind: 'skill', name: 'b', description: 'Use when B.', path: '/u/b', match: [] },
    { level: 'project', kind: 'script', name: 'scripts/c.sh', description: '', path: '/p/scripts/c.sh', match: [] },
    { level: 'project', kind: 'widget', name: 'd' },
    { level: 'project', kind: 'lesson' },
    'not a row',
  ])
  const items = parseInventory(out)
  expect(items?.map(i => `${i.kind}:${i.name}`)).toEqual(['lesson:alpha', 'skill:b', 'script:scripts/c.sh'])
  expect(items?.[0]?.match).toEqual(['^x'])
  expect(parseInventory('[]')).toEqual([])
})

test('inventory output that is not a list is unreadable', async () => {
  for (const bad of ['', 'nothing recorded yet', '{"error":"x"}', '42', '[1,']) expect(parseInventory(bad)).toBe(undefined)
})

test('a lesson that does not apply on this machine, or that the user switched off, is not in the inventory', async () => {
  const row = (name: string, more: Record<string, unknown>) => ({ level: 'general', kind: 'lesson', name, description: 'Use when.', path: `/g/${name}`, match: ['^x'], ...more })
  const out = JSON.stringify([
    row('here', { applies: true, disabled: false }),
    row('elsewhere', { applies: false, disabled: false }),
    row('switched-off', { applies: true, disabled: true }),
    row('says-nothing', {}),
  ])
  expect(parseInventory(out)?.map(i => i.name)).toEqual(['here', 'says-nothing'])
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
  expect(shown).toEqual({ text: 'Do the thing.\nSecond line.', path: '/u/a', level: 'user', recalls: 3, ineffective: true, since: undefined, limit: undefined, guarded: undefined })
  expect(parseShow('a (user lesson)\n/u/a\n')).toEqual({ text: 'a (user lesson)\n/u/a', path: '', level: '', recalls: 0, ineffective: undefined, since: undefined, limit: undefined, guarded: undefined })
  const counted = parseShow(JSON.stringify({ text: 'x', counts: { recall: 4 }, recalls_since: 1, recur_limit: 2 }))
  expect([counted.since, counted.limit]).toEqual([1, 2])
  // Whether the lesson's guard refused a call in this session is the CLI's to say.
  expect(counted.guarded).toBe(undefined)
  expect(parseShow(JSON.stringify({ text: 'x', guarded_in_session: true })).guarded).toBe(true)
  expect(parseShow(JSON.stringify({ text: 'x', guarded_in_session: false })).guarded).toBe(false)
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

// What settles a debt is decided by the CLI and tested there (tests/test_settle.py,
// tests/test_reach.py): a debt the CLI no longer lists is settled, and one it lists is owed
// whatever else the reply holds.
const owedOf = (events: Event[]) => parseOwed(JSON.stringify(events))

test('what a session owes is exactly the captures and the recalls the CLI lists', async () => {
  expect(owedOf([])).toEqual({ debts: [], weak: [], since: 0 })
  expect(owedOf([cap('1')])?.debts.map(d => d.key)).toEqual(['1'])
  expect(owedOf([cap('2'), { type: 'reuse' }, cap('3')])?.debts.map(d => d.key)).toEqual(['2', '3'])
  expect(owedOf([{ ...cap('1'), id: 'abcd1234' }])?.debts[0]).toEqual({ id: 'abcd1234', key: '1', tool: 'Bash', failed: 'f-1', error: 'e-1', fixed: 'x-1' })
  // The mod reads no settlement out of a reply: a row of another type changes nothing.
  expect(owedOf([cap('1'), { type: 'learn', lesson: 'a' }, { type: 'skip', why: 'typo' }])?.debts.map(d => d.key)).toEqual(['1'])
  expect(parseOwed('compound: error')).toBe(undefined)
})

test('a capture with no call id is keyed on its time', async () => {
  expect(owedOf([{ type: 'capture', ts: '2026-10-03T00:00:00Z' }])?.debts[0]?.key).toBe('2026-10-03T00:00:00Z')
})

test('what is owed dates from its oldest row', async () => {
  const at = Date.UTC(2026, 9, 3, 12) / 1000
  expect(owedOf([{ ...cap('1'), ts: '2026-10-03T12:00:05Z' }, { type: 'recall', lesson: 'a', ineffective: true, ts: '2026-10-03T12:00:00Z' }])?.since).toBe(at)
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

test('a strengthening is owed for each lesson whose recall the CLI lists, with its newest failing call', async () => {
  const recall = (lesson: string, call = './build.sh', guard = false): Event => ({ type: 'recall', lesson, ineffective: true, call, guard })
  expect(owedOf([recall('a')])?.weak).toEqual([{ name: 'a', guard: false, call: './build.sh' }])
  expect(owedOf([recall('a'), recall('a', 'second call', true)])?.weak).toEqual([{ name: 'a', guard: true, call: 'second call' }])
  expect(owedOf([recall('a'), recall('b')])?.weak.map(s => s.name)).toEqual(['a', 'b'])
  expect(owedOf([{ type: 'recall', ineffective: true }])?.weak).toEqual([])
  // Listed is owed: the rewrite, the decline, the removal that settle one are the CLI's to apply.
  expect(owedOf([recall('a'), { type: 'learn', lesson: 'a', update: true }, { type: 'skip', why: 'x' }, { type: 'rm', lesson: 'a' }])?.weak.length).toBe(1)
})

test('what settled a debt is shown from the session\'s own events, a settlement by id, and what became of a weak lesson', async () => {
  const at = (type: string, more: Record<string, unknown>): Event => ({ type, ts: '2026-10-03T12:00:00Z', session: 'other', ...more })
  const mine = at('learn', { lesson: 'x', session: 'me' })
  const byId = at('skip', { why: 'no', session: '', settles: 'abcd1234' })
  const gone = at('rm', { lesson: 'weak-one', session: '' })
  const renamed = at('promote', { lesson: 'weak-anywhere', was: 'weak-one', to: 'user' })
  const rewritten = at('learn', { lesson: 'weak-one', update: true })
  const rows = [mine, byId, gone, renamed, rewritten, at('skip', { why: 'theirs' }), at('learn', { lesson: 'theirs' }), at('capture', { session: 'me' }), at('recall', { lesson: 'weak-one', session: 'me' })]
  expect(settlers(rows, 'me', ['abcd1234'], ['weak-one'])).toEqual([mine, byId, gone, renamed, rewritten])
  expect(settlers(rows, 'me', [], [])).toEqual([mine])
  expect(settlers(rows, '', [], [])).toEqual([])
})

test('a lesson first recorded since the failure was held is that failure\'s own', async () => {
  const learn = (lesson: string, update: boolean): Event => ({ type: 'learn', lesson, update })
  expect(learnedSince([learn('a', false)], 'a')).toBe(true)
  expect(learnedSince([learn('a', true)], 'a')).toBe(false)
  expect(learnedSince([learn('b', false), { type: 'recall', lesson: 'a' }], 'a')).toBe(false)
  expect(learnedSince([], 'a')).toBe(false)
  expect(learnedSince([learn('', false)], '')).toBe(false)
})

test('unsettled captures are read from the CLI, leaving out this session\'s own', async () => {
  const now = Date.UTC(2026, 9, 3) / 1000
  const out = JSON.stringify([
    { type: 'capture', id: 'aaaa1111', ts: '2026-10-01T00:00:00Z', session: 'old', failed: 'f', error: 'e', fixed: 'x' },
    { type: 'capture', id: 'bbbb2222', ts: '2026-10-02T23:00:00Z', session: 'mine', failed: 'f2', error: 'e2', fixed: 'x2' },
    { type: 'capture', ts: '2026-10-02T00:00:00Z', session: 'old' },
  ])
  expect(parseUnsettled(out, 'mine', now)).toEqual([{ id: 'aaaa1111', age: '2d', failed: 'f', error: 'e', fixed: 'x' }])
  expect(parseUnsettled('[]', 'mine', now)).toEqual([])
  expect(parseUnsettled('compound: error', 'mine', now)).toBe(undefined)
})

test('a lesson left in place by the automatic move is read with the project that holds it', async () => {
  expect(parseLeft('{"name":"a","moved":false,"candidate":true,"from":"/work/alpha","seen_in":"/work/beta","command":"x"}')).toBe('/work/alpha')
  expect(parseLeft('{"name":"a","moved":true}')).toBe(undefined)
  expect(parseLeft('not json')).toBe(undefined)
})

test('a move the CLI refused for the name is read with the project and the lessons in the way', async () => {
  const out = '{"name":"a","moved":false,"candidate":true,"from":"/work/alpha","seen_in":"/work/beta","command":"x","conflict":["/work/beta/.claude/compound/lessons/a"]}'
  expect(parseLeft(out)).toBe('/work/alpha')
  expect(parseMoved(out)?.conflict).toEqual(['/work/beta/.claude/compound/lessons/a'])
})

test('a move the CLI made says which project the lesson left and which keep a committed copy', async () => {
  expect(parseMoved('{"name":"a","moved":true,"from":"/work/gamma","seen_in":"/work/beta","also":["/work/alpha"]}')).toEqual({ from: '/work/gamma', also: ['/work/alpha'], conflict: [] })
  expect(parseMoved('{"name":"a","moved":true,"from":"/work/gamma"}')).toEqual({ from: '/work/gamma', also: [], conflict: [] })
  expect(parseMoved('{"name":"a","moved":false,"from":"/work/alpha","conflict":["/p/a"]}')).toEqual({ from: '/work/alpha', also: [], conflict: ['/p/a'] })
  expect(parseMoved('not json')).toBe(undefined)
})

test('`check --guards` says how many lessons carry a pattern; a reply without the count says nothing', async () => {
  expect(parseGuards('{"hits": [], "guards": 0}')).toBe(0)
  expect(parseGuards('{"hits": [{"name":"a"}], "guards": 3}')).toBe(3)
  expect(parseGuards('{"hits": []}')).toBe(undefined)
  expect(parseGuards('{"hits": [], "guards": "none"}')).toBe(undefined)
  expect(parseGuards('not json')).toBe(undefined)
})

test('`check --guards` names the tools the guards apply to; a reply without them says nothing', async () => {
  expect(parseGuardTools('{"hits": [], "guards": 2, "tools": ["Bash", "Edit"]}')).toEqual(['Bash', 'Edit'])
  expect(parseGuardTools('{"hits": [], "guards": 0, "tools": []}')).toEqual([])
  expect(parseGuardTools('{"hits": [], "guards": 1}')).toBe(undefined)
  expect(parseGuardTools('{"hits": [], "tools": "Bash"}')).toBe(undefined)
  expect(parseGuardTools('{"hits": [], "tools": ["Bash", 3]}')).toBe(undefined)
  expect(parseGuardTools('not json')).toBe(undefined)
})

// ---- what `find --request` prints ----

const REQUESTED = JSON.stringify({
  words: ['release', 'changelog', 7],
  items: [
    { kind: 'lesson', name: 'release-tagging', level: 'project', description: 'Use when tagging a release.', path: '/p/l/release-tagging', match: [], score: 3, weight: 2.5, matched: ['release'] },
    { kind: 'skill', name: 'reuse', level: 'general', description: 'The package\'s own.', path: '/pkg/skills/reuse', match: [] },
    { name: 'no kind' },
  ],
  floor: 1.5,
  memo_key: '0123456789abcdef0123456789abcdef',
  prompts: [
    { id: 'p1', ts: '2026-09-30T10:00:00Z', project: '/work/alpha', session: 's9', scope: 'all', score: 4, weight: 0.5, prompt: 'write a release script' },
    { id: 'p2', ts: '2026-09-29T10:00:00Z', project: '/work/alpha', session: 's1', scope: 'all', score: 4, weight: 0.4, prompt: 'asked in this session' },
  ],
  surfer: 'ok',
})

test('a request\'s candidates, earlier requests, words and key are read from one reply', async () => {
  const found = parseFound(REQUESTED, 's1', [], 5)
  expect(found?.words).toEqual(['release', 'changelog'])
  expect(found?.items.map(i => i.name)).toEqual(['release-tagging', 'reuse'])
  expect(found?.earlier.map(e => e.id)).toEqual(['p1'])
  expect(found?.key).toBe('0123456789abcdef0123456789abcdef')
  expect(found?.memo).toBe(undefined)
  expect(parseFound('not json', 's1', [], 5)).toBe(undefined)
  expect(parseFound('[]', 's1', [], 5)).toBe(undefined)
  expect(parseFound('{}', 's1', [], 5)).toEqual({ words: [], items: [], earlier: [], key: '', memo: undefined })
})

test('a remembered verdict comes back with what it named, and is written as the CLI reads it', async () => {
  const item = { kind: 'lesson' as const, name: 'release-tagging', level: 'project', description: '', path: '/p', match: [] }
  const earlier = { id: 'p1', date: '2026-09-30', project: 'alpha', session: 's9', text: 'write a release script', score: 4 }
  const written = JSON.parse(memoOf('k'.repeat(32), 'named', [item], [earlier])) as Record<string, unknown>
  expect(written).toEqual({ key: 'k'.repeat(32), verdict: 'named', items: ['release-tagging'], prompts: [{ id: 'p1', ts: '2026-09-30', project: 'alpha', session: 's9', prompt: 'write a release script' }] })
  // The CLI gives the same rows back under "memo"; they are read as earlier requests again,
  // and are not dropped for being this session's own.
  const reply = JSON.stringify({ ...JSON.parse(REQUESTED), prompts: [], surfer: 'memo', memo: { verdict: 'named', items: written.items, prompts: written.prompts, ts: '2026-10-01T00:00:00Z' } })
  const memo = parseFound(reply, 's9', ['write a release script'], 5)?.memo
  expect(memo?.verdict).toBe('named')
  expect(memo?.items).toEqual(['release-tagging'])
  expect(memo?.earlier).toEqual([{ ...earlier, score: 0 }])
  for (const verdict of ['nothing', 'not-substantial']) {
    expect(parseFound(JSON.stringify({ memo: { verdict } }), 's1', [], 5)?.memo).toEqual({ verdict, items: [], earlier: [], repeats: [], asked: [] })
  }
  for (const bad of [{ verdict: 'unanswered' }, { items: [] }, 'named', null]) {
    expect(parseFound(JSON.stringify({ memo: bad }), 's1', [], 5)?.memo).toBe(undefined)
  }
})

test('an earlier request names the sessions that asked it, and this session is never one of them', async () => {
  const row = (session: string, sessions: unknown, prompt = 'write the weekly digest') => ({ id: `${session}:1`, ts: '2026-09-01T00:00:00Z', project: '/w/alpha', session, prompt, score: 3, ...(sessions === undefined ? {} : { sessions }) })
  const read = (rows: unknown[], mine: string[] = []) => parseEarlier(JSON.stringify({ prompts: rows }), 'now', mine, 5)!
  expect(read([row('a', ['a', 'b', 'now'])])[0]!.sessions).toEqual(['a', 'b'])
  // A CLI that names no sessions: the row's own is all there is.
  expect(read([row('a', undefined)])[0]!.sessions).toBe(undefined)
  // This session's own prompt is no earlier request, unless another session asked the same words.
  expect(read([row('now', ['now'])])).toEqual([])
  expect(read([row('now', undefined)])).toEqual([])
  expect(read([row('a', undefined)], ['write the weekly digest'])).toEqual([])
  expect(read([row('a', ['a', 'now'])], ['write the weekly digest']).map(e => [e.session, e.sessions])).toEqual([['a', ['a']]])
  expect(read([row('now', ['now', 'b'])]).map(e => [e.session, e.sessions])).toEqual([['b', ['b']]])
  // A session id is one printable line, or it is not one.
  expect(read([row('a', ['a', 'b\nc', 7, ''])])[0]!.sessions).toEqual(['a'])
})

test('how often a kind of request was made is counted in sessions, this one included', async () => {
  const e = (session: string, sessions?: string[]) => ({ id: `${session}:1`, date: '2026-09-01', project: 'alpha', session, text: 't', score: 1, ...(sessions === undefined ? {} : { sessions }) })
  expect(askedTimes([], [], 'now')).toBe(0)
  expect(askedTimes([e('a')], [], 'now')).toBe(2)
  expect(askedTimes([e('a'), e('a')], [], 'now')).toBe(2)
  expect(askedTimes([e('a', ['a', 'b']), e('c')], ['b', 'd', 'now'], 'now')).toBe(5)
  // A row with no session says nothing about sessions.
  expect(askedTimes([e('')], [], 'now')).toBe(0)
  expect(askedTimes([e('now', ['now'])], ['now'], 'now')).toBe(0)
})

test('what `compound use` printed is a counted skill, a skill not counted, or unreadable', async () => {
  expect(parseUsed('{"used":true,"name":"finish-task","level":"general","path":"/g"}')).toEqual({ used: true, name: 'finish-task', level: 'general' })
  expect(parseUsed('{"used":false,"name":"x","reason":"no"}')).toEqual({ used: false, name: '', level: '' })
  expect(parseUsed('{"used":true,"name":"a\nb","level":"user"}')).toBe(undefined)
  expect(parseUsed('{"used":"yes"}')).toBe(undefined)
  expect(parseUsed('nope')).toBe(undefined)
})

test('a verdict is kept with the requests of the same kind, and comes back with who asked', async () => {
  const again = { id: 'p1', date: '2026-09-01', project: 'alpha', session: 's0', text: 'write the digest', score: 0, sessions: ['s0', 's7'] }
  const written = JSON.parse(memoOf('k'.repeat(32), 'nothing', [], [], [again])) as Record<string, unknown>
  expect(written.repeats).toEqual([{ id: 'p1', ts: '2026-09-01', project: 'alpha', session: 's0', prompt: 'write the digest', sessions: ['s0', 's7'] }])
  expect('repeats' in (JSON.parse(memoOf('k'.repeat(32), 'nothing', [], [])) as Record<string, unknown>)).toBe(false)
  const memo = parseFound(JSON.stringify({ memo: { verdict: 'nothing', items: [], prompts: [], repeats: written.repeats, asked: ['s1', 's2', 3, 'a\nb'] } }), 's9', [], 5)?.memo
  expect(memo?.repeats).toEqual([again])
  expect(memo?.asked).toEqual(['s1', 's2'])
})
