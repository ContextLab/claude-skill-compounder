import { expect, test } from 'claude-code/testing'
import { firstObject, fixPrompt, INVENTORY_MAX, listed, named, parseFix, parseRecall, parseReuse, quoted, recallPrompt, reusePrompt } from './judge'
import type { Item } from './store'

const item = (kind: Item['kind'], name: string, level = 'project', description = 'Use when testing.'): Item => ({ kind, name, level, description, path: `/p/${name}`, match: [] })
const ITEMS: Item[] = [item('script', 'scripts/release.sh'), item('skill', 'cdl-bib-cite', 'user'), item('lesson', 'build-needs-profile')]
const LESSONS = ITEMS.filter(i => i.kind === 'lesson')
const ERROR = 'Exit code 2\nbuild.sh: error: a profile is required, e.g. ./build.sh --profile dev'

// ---- prompts ----

test('the inventory is listed lessons first, one line each, and an empty one says so', async () => {
  expect(listed([])).toBe('(none)')
  const lines = listed(ITEMS).split('\n')
  expect(lines[0]).toBe('build-needs-profile [lesson, project]: Use when testing.')
  expect(lines[1]).toBe('cdl-bib-cite [skill, user]: Use when testing.')
  expect(lines[2]).toBe('scripts/release.sh [script, project]: Use when testing.')
})

test('a long inventory is cut with a count, and a long description with a mark', async () => {
  const many = Array.from({ length: INVENTORY_MAX + 7 }, (_, i) => item('lesson', `l${i}`))
  const lines = listed(many).split('\n')
  expect(lines.length).toBe(INVENTORY_MAX + 1)
  expect(lines[INVENTORY_MAX]).toBe('[... 7 more entries not listed ...]')
  expect(listed([item('lesson', 'long', 'user', 'x'.repeat(500))]).length < 300).toBe(true)
})

test('each prompt carries its data and the one-line reply shape', async () => {
  const reuse = reusePrompt('Please build a release script for this repo', ITEMS)
  expect(reuse.includes('REQUEST:\nPlease build a release script for this repo')).toBe(true)
  expect(reuse.includes('scripts/release.sh [script, project]')).toBe(true)
  expect(reuse.includes('{"substantial":true|false,"items":["<exact name>"],"keywords":["<word>"]}')).toBe(true)
  const recall = recallPrompt('./build.sh', ERROR, LESSONS)
  expect(recall.includes('FAILED CALL:\n./build.sh')).toBe(true)
  expect(recall.includes('{"name":null}')).toBe(true)
  const fix = fixPrompt({ failed: './build.sh', error: ERROR, worked: './build.sh --profile dev' }, LESSONS)
  expect(fix.includes('LATER SUCCESSFUL CALL:\n./build.sh --profile dev')).toBe(true)
  expect(fix.includes('"verdict":"FIX"|"KNOWN"|"NONE"')).toBe(true)
})

test('a long request is shortened in the prompt with the cut marked', async () => {
  const p = reusePrompt('a'.repeat(9000), ITEMS)
  expect(p.includes('[... 5000 characters omitted here ...]')).toBe(true)
})

// ---- reading a reply ----

test('the object is found inside a fence or a sentence, and nothing else is one', async () => {
  expect(firstObject('```json\n{"a":1}\n```')).toEqual({ a: 1 })
  expect(firstObject('Sure! {"a":1} Hope that helps.')).toEqual({ a: 1 })
  for (const bad of ['', 'no json here', '{"a":', '[1,2]', '{a:1}', '}{', 'null', '"text"']) {
    expect(firstObject(bad)).toBe(undefined)
  }
})

test('a reuse reply names inventory items and keywords', async () => {
  const a = parseReuse('{"substantial":true,"items":["scripts/release.sh","cdl-bib-cite"],"keywords":["release","tag"]}', ITEMS)
  expect(a?.substantial).toBe(true)
  expect(a?.items.map(i => i.name)).toEqual(['scripts/release.sh', 'cdl-bib-cite'])
  expect(a?.keywords).toEqual(['release', 'tag'])
})

test('a name is read as the model decorates it, and never guessed from a fragment', async () => {
  // Measured 2026-10-03: haiku answered "lesson release-tagging (project)" for the name release-tagging.
  for (const said of ['build-needs-profile', 'lesson build-needs-profile (project)', 'build-needs-profile [lesson, project]', '"build-needs-profile"', ' build-needs-profile: ', 'Lesson build-needs-profile']) {
    expect(named(said, ITEMS)?.name).toBe('build-needs-profile')
  }
  expect(named('script scripts/release.sh (project)', ITEMS)?.name).toBe('scripts/release.sh')
  for (const said of ['build', 'build-needs', 'needs-profile lesson', '', 'the build lesson', 'build-needs-profile and cdl-bib-cite']) {
    expect(named(said, ITEMS)).toBe(undefined)
  }
})

test('a reuse reply cannot invent an item, repeat one, or reuse anything for a trivial prompt', async () => {
  const invented = parseReuse('{"substantial":true,"items":["made-up","scripts/release.sh","scripts/release.sh"],"keywords":[]}', ITEMS)
  expect(invented?.items.map(i => i.name)).toEqual(['scripts/release.sh'])
  const trivial = parseReuse('{"substantial":false,"items":["scripts/release.sh"],"keywords":["release"]}', ITEMS)
  expect(trivial).toEqual({ substantial: false, items: [], keywords: [] })
})

test('reuse keywords are trimmed, de-duplicated, non-strings dropped, and capped', async () => {
  const a = parseReuse('{"substantial":true,"items":[],"keywords":[" release ","release",7,null,"","a","b","c","d","e","f","g"]}', ITEMS)
  expect(a?.keywords).toEqual(['release', 'a', 'b', 'c', 'd', 'e'])
})

test('a malformed reuse reply is unreadable, not a no', async () => {
  for (const bad of [
    '',
    'I think this is substantial.',
    '{"substantial":"yes","items":[],"keywords":[]}',
    '{"substantial":true,"items":"scripts/release.sh","keywords":[]}',
    '{"substantial":true,"items":[]}',
    '{"items":[],"keywords":[]}',
    '{"substantial":true,"items":[],"keywords":[',
    '[true,[],[]]',
  ]) {
    expect(parseReuse(bad, ITEMS)).toBe(undefined)
  }
})

test('a recall reply is a recorded lesson, a readable no, or unreadable', async () => {
  expect(parseRecall('{"name":"build-needs-profile"}', LESSONS)?.lesson?.name).toBe('build-needs-profile')
  expect(parseRecall('{"name":null}', LESSONS)).toEqual({ lesson: undefined })
  expect(parseRecall('{"name":"not-recorded"}', LESSONS)).toEqual({ lesson: undefined })
  for (const bad of ['', 'none of them', '{}', '{"name":3}', '{"name":["build-needs-profile"]}', '{"id":"build-needs-profile"}', '{"name":']) {
    expect(parseRecall(bad, LESSONS)).toBe(undefined)
  }
})

function fix(fields: Record<string, unknown>): string {
  return JSON.stringify({ same_goal: true, call_mistake: true, recurs: true, evidence: 'a profile is required', verdict: 'FIX', ...fields })
}

test('a fix whose checks hold and whose evidence is in the error stands', async () => {
  expect(parseFix(fix({}), LESSONS, ERROR)).toEqual({ verdict: 'FIX', evidence: 'a profile is required' })
})

test('a fix is refused when any one check is false', async () => {
  for (const check of ['same_goal', 'call_mistake', 'recurs']) {
    expect(parseFix(fix({ [check]: false }), LESSONS, ERROR)).toEqual({ verdict: 'NONE', reason: 'a check did not hold' })
    expect(parseFix(fix({ [check]: 'true' }), LESSONS, ERROR)?.verdict).toBe('NONE')
  }
})

test('a fix is refused when its evidence is not in the error, or is only the exit status', async () => {
  expect(parseFix(fix({ evidence: 'the script was cut off mid-line' }), LESSONS, ERROR)).toEqual({ verdict: 'NONE', reason: 'evidence not found in the error' })
  expect(parseFix(fix({ evidence: 'Exit code 2' }), LESSONS, ERROR)?.verdict).toBe('NONE')
  expect(parseFix(fix({ evidence: '' }), LESSONS, ERROR)?.verdict).toBe('NONE')
  expect(parseFix(fix({ evidence: 42 }), LESSONS, ERROR)?.verdict).toBe('NONE')
  expect(quoted('a  profile\nis required', ERROR)).toBe(true)
})

test('KNOWN stands only for a lesson in the list it was given', async () => {
  expect(parseFix(fix({ verdict: 'KNOWN', name: 'build-needs-profile' }), LESSONS, ERROR)).toEqual({ verdict: 'KNOWN', lesson: LESSONS[0]! })
  expect(parseFix(fix({ verdict: 'KNOWN', name: 'nope' }), LESSONS, ERROR)?.verdict).toBe('NONE')
  expect(parseFix(fix({ verdict: 'KNOWN' }), LESSONS, ERROR)?.verdict).toBe('NONE')
})

test('NONE keeps its reason, and a malformed fix reply is unreadable', async () => {
  expect(parseFix('{"verdict":"NONE","reason":"next step of the work"}', LESSONS, ERROR)).toEqual({ verdict: 'NONE', reason: 'next step of the work' })
  expect(parseFix('{"verdict":"NONE"}', LESSONS, ERROR)).toEqual({ verdict: 'NONE', reason: 'no lesson' })
  for (const bad of ['', 'It is a fix.', '{"same_goal":true}', '{"verdict":true}', '{"verdict":"MAYBE"}', '{"verdict":"FIX"', '["FIX"]']) {
    expect(parseFix(bad, LESSONS, ERROR)).toBe(undefined)
  }
})
