import { expect, test } from 'claude-code/testing'
import type { CompoundBand } from '../types'
import {
  ago, bandRow, bar, began, boardFrom, boardLines, BUSY, BUSY_MAX_MS, captured, dateText, emptyBand, ended, erred, ERROR, eventLook, eventTail, eventText, eventWord, FLASH_MS, forSession,
  frameAt, FRAME_MS, FRAMES, FRESH_MS, GONE_MS, greeted, HINT, inventoried, listed, motion, newTurn, noted, NOTES, OWED, phaseAt, phaseKey, reuseFound, reuseIdle, reuseText, settledBy, stepped, synced, trackSegs,
  unfixed, WATCHING, WEAK, weakened, width, WORDS,
  type Seg,
} from './view'

const T0 = 1_000_000
const text = (row: readonly Seg[]) => row.map(s => s.text).join('')
const fresh = () => emptyBand('s1')

// ---- glyphs and colours ----

test('every result has a glyph one cell wide, a colour and a label, and the states are told apart', async () => {
  const looks = [...Object.values(NOTES), OWED, WEAK, ERROR]
  for (const look of looks) {
    expect([...look.glyph].length).toBe(1)
    expect(look.color).not.toBe('')
    expect(look.label).not.toBe('')
  }
  // The moments a person must tell apart at a glance differ in glyph and in colour.
  const apart = [NOTES.reuse, NOTES.guard, NOTES.recall, OWED, NOTES.recorded, ERROR]
  expect(new Set(apart.map(l => l.glyph)).size).toBe(apart.length)
  expect(new Set([NOTES.reuse.color, NOTES.guard.color, NOTES.recall.color, OWED.color, NOTES.recorded.color]).size).toBe(5)
  for (const frame of FRAMES) expect([...frame].length).toBe(1)
})

test('the timeline draws every event type of the log with the band\'s own glyphs', async () => {
  for (const type of ['reuse', 'guard', 'recall', 'capture', 'remind', 'refuse', 'learn', 'skip', 'nudge', 'promote', 'candidate', 'skill', 'rm', 'error']) {
    expect(eventLook(type).glyph).not.toBe('·')
  }
  expect(eventLook('reuse')).toEqual(NOTES.reuse)
  expect(eventLook('guard')).toEqual(NOTES.guard)
  expect(eventLook('learn')).toEqual(NOTES.recorded)
  expect(eventLook('capture')).toEqual(OWED)
  expect(eventLook('something-new').glyph).toBe('·')
})

// ---- frames and phases ----

test('the spinner turns one frame every tenth of a second and wraps', async () => {
  expect(FRAME_MS).toBe(100)
  expect(frameAt(0)).toBe(FRAMES[0])
  expect(frameAt(FRAME_MS)).toBe(FRAMES[1])
  expect(frameAt(FRAME_MS * FRAMES.length)).toBe(FRAMES[0])
  expect(frameAt(-5)).toBe(FRAMES[0])
})

test('a result flashes, stays, dims and goes', async () => {
  expect(phaseAt(T0, T0)).toBe('flash')
  expect(phaseAt(T0, T0 + FLASH_MS)).toBe('fresh')
  expect(phaseAt(T0, T0 + FRESH_MS)).toBe('dim')
  expect(phaseAt(T0, T0 + GONE_MS)).toBe('gone')
  // A clock that ran backwards shows the result, never hides it.
  expect(phaseAt(T0, T0 - 50)).toBe('flash')
})

// ---- the band's state ----

test('a band belongs to one session: another session\'s starts over', async () => {
  const band = captured(fresh(), T0)
  expect(forSession(band, 's1')).toBe(band)
  expect(forSession(band, 's2')).toEqual(emptyBand('s2'))
  expect(forSession(null, 's2')).toEqual(emptyBand('s2'))
  expect(forSession(undefined, 's2')).toEqual(emptyBand('s2'))
})

test('a check in flight spins under its own label until it ends', async () => {
  for (const kind of ['reuse', 'guard', 'recall', 'fix', 'record'] as const) {
    const band = began(fresh(), 'a', kind, T0)
    expect(motion(band, T0)).toBe('spin')
    const row = bandRow(band, T0 + 250, 100)
    expect(row[0]!.text).toBe(`${frameAt(T0 + 250)} `)
    expect(text(row)).toContain(BUSY[kind])
    const done = ended(band, 'a')
    expect(done.busy).toEqual([])
    expect(bandRow(done, T0 + 300, 100)).toEqual([])
    expect(motion(done, T0 + 300)).toBe('still')
  }
  expect(BUSY.reuse).toBe('checking for reusable work')
  expect(BUSY.recall).toBe('matching a recorded lesson')
  expect(BUSY.fix).toBe('is this the fix?')
})

test('two checks at once: the newest is shown, and ending one leaves the other', async () => {
  const band = began(began(fresh(), 'a', 'reuse', T0), 'b', 'recall', T0 + 10)
  expect(text(bandRow(band, T0 + 20, 100))).toContain(BUSY.recall)
  expect(text(bandRow(ended(band, 'b'), T0 + 20, 100))).toContain(BUSY.reuse)
  // The same id begun twice is one check.
  expect(began(band, 'a', 'reuse', T0 + 30).busy.length).toBe(2)
  // Ending a check that is not there changes nothing.
  expect(ended(band, 'zz')).toBe(band)
})

test('a check that never reported its end stops spinning after a minute', async () => {
  const band = began(fresh(), 'a', 'fix', T0)
  expect(motion(band, T0 + BUSY_MAX_MS - 1)).toBe('spin')
  expect(motion(band, T0 + BUSY_MAX_MS)).toBe('still')
  expect(bandRow(band, T0 + BUSY_MAX_MS, 100)).toEqual([])
  // And the next check that begins drops it from the state.
  expect(began(band, 'b', 'reuse', T0 + BUSY_MAX_MS).busy.map(b => b.id)).toEqual(['b'])
})

test('a result is drawn with its glyph, colour and name, fades, and is gone', async () => {
  const band = noted(fresh(), 'guard', 'zsh-equals-word', T0)
  const flash = bandRow(band, T0 + 100, 100)
  expect(text(flash)).toBe('■ compound guard stopped a call · zsh-equals-word')
  expect(flash[0]).toEqual({ text: '■ ', color: 'error', bold: true })
  expect(flash[2]!.color).toBe('error')
  const plain = bandRow(band, T0 + FLASH_MS, 100)
  expect(plain[0]!.bold).toBe(false)
  expect(plain.some(s => s.dim !== true)).toBe(true)
  const dim = bandRow(band, T0 + FRESH_MS, 100)
  expect(text(dim)).toBe(text(flash))
  expect(dim.every(s => s.dim === true)).toBe(true)
  expect(bandRow(band, T0 + GONE_MS, 100)).toEqual([])
  expect(motion(band, T0 + 100)).toBe('fade')
  expect(motion(band, T0 + GONE_MS)).toBe('still')
})

test('each moment\'s result reads as what happened', async () => {
  const row = (band: CompoundBand) => text(bandRow(band, T0 + 1, 100))
  expect(row(noted(fresh(), 'reuse', reuseText(['scripts/bibdupcheck.py', 'cdl-bib-cite'], 1), T0))).toBe('◆ compound reuse found · bibdupcheck.py, cdl-bib-cite · 1 earlier request')
  expect(row(noted(fresh(), 'recall', 'build-needs-profile', T0))).toBe('↺ compound lesson recalled · build-needs-profile')
  expect(row(noted(fresh(), 'moved', 'zsh-equals-word', T0))).toBe('⇡ compound lesson moved to the user level · zsh-equals-word')
  expect(row(noted(fresh(), 'unsettled', '2 lessons', T0))).toBe('● compound owed from earlier sessions · 2 lessons')
  expect(row(noted(fresh(), 'nudge', '31 tool calls', T0))).toBe('? compound asked whether anything was learned · 31 tool calls')
  expect(reuseText(['cdl-bib-cite'], 0)).toBe('cdl-bib-cite')
  expect(reuseText([], 2)).toBe('2 earlier requests')
  expect(reuseText([], 0)).toBe('')
})

test('a result names the thing: the items found, what a guard stopped, what a lesson is owed for', async () => {
  // As many names as fit, the first always, then how many more. A script is named by its file.
  const names = ['scripts/bibdupcheck.py', 'cdl-bib-cite', 'bib-duplicate-check', 'release-notes-format']
  expect(reuseText(names, 0)).toBe('bibdupcheck.py, cdl-bib-cite, bib-duplicate-check +1')
  expect(reuseText(names, 0, 100)).toBe('bibdupcheck.py, cdl-bib-cite, bib-duplicate-check, release-notes-format')
  expect(listed(['a-name-longer-than-the-room', 'b'], 10)).toBe('a-name-longer-than-the-room +1')
  expect(listed(['a', 'b', 'c'], 4)).toBe('a +2')
  expect(listed([], 10)).toBe('')
  // Nothing here calls a script "a lesson or skill": the thing is named, not classed.
  expect(reuseText(names, 3)).not.toContain('lesson')
  expect(reuseText(names, 3)).toBe('bibdupcheck.py, cdl-bib-cite, bib-duplicate-check +1 · 3 earlier requests')

  // A band too narrow for the list keeps as many names as fit, whole, and counts the rest.
  const found = reuseFound(fresh(), names, 2, T0)
  expect(text(bandRow(found, T0 + 1, 120))).toBe('◆ compound reuse found · bibdupcheck.py, cdl-bib-cite, bib-duplicate-check +1 · 2 earlier requests')
  expect(text(bandRow(found, T0 + 1, 60))).toBe('◆ compound reuse found · bibdupcheck.py, cdl-bib-cite +2')
  expect(text(bandRow(found, T0 + 1, 44))).toBe('◆ compound reuse found · bibdupcheck.py +3')
  expect(text(bandRow(found, T0 + 1, 36))).toBe('◆ compound reuse found · bibdupchec…')
  expect(reuseFound(fresh(), [], 2, T0).note).toEqual({ kind: 'reuse', text: '2 earlier requests', at: T0 })

  // A guard: the lesson, then the call it stopped, which is the first thing a narrow band drops.
  const guard = noted(fresh(), 'guard', 'zsh-equals-word', T0, 'echo ==== separator ====')
  expect(text(bandRow(guard, T0 + 1, 100))).toBe('■ compound guard stopped a call · zsh-equals-word  echo ==== separator ====')
  const stopped = bandRow(guard, T0 + FLASH_MS, 100).find(s => s.text === 'echo ==== separator ====')!
  expect(stopped.dim).toBe(true)
  expect(text(bandRow(guard, T0 + 1, 60))).toBe('■ compound guard stopped a call · zsh-equals-word')
  expect(noted(fresh(), 'guard', 'x', T0).note).toEqual({ kind: 'guard', text: 'x', at: T0 })

  // A lesson owed says for which fix, and keeps saying it while it is owed.
  const owed = captured(fresh(), T0, './deploy.sh --target staging')
  expect(text(bandRow(owed, T0 + 3_600_000, 100))).toBe('● compound lesson owed · ./deploy.sh --target staging   ✓ failed → ✓ fixed → ● owed → ○ recorded')
  // The CLI's count leaves the subject as it is unless it names a newer one, and settling clears it.
  expect(synced(owed, 1, [], T0 + 5)).toBe(owed)
  expect(synced(owed, 2, [], T0 + 5, 'make test').owedText).toBe('make test')
  expect(text(bandRow(synced(owed, 2, [], T0 + 5, 'make test'), T0 + GONE_MS, 100))).toContain('2 lessons owed · make test')
  expect(synced(owed, 0, [], T0 + 5).owedText).toBe('')
  expect(settledBy(owed, { type: 'learn', lesson: 'deploy-needs-target', update: false }, T0 + 9).owedText).toBe('')
  expect(settledBy(owed, { type: 'skip', why: 'a typo' }, T0 + 9).owedText).toBe('')
  // A band kept from before the subject existed draws as it did.
  expect(text(bandRow({ ...fresh(), owed: 1, track: { step: 'owed', at: T0 } }, T0, 100))).toBe('● compound lesson owed   ✓ failed → ✓ fixed → ● owed → ○ recorded')
})

test('a session is greeted once: with the store\'s counts when the inventory was read, without them at a short prompt', async () => {
  // The first reuse check found nothing: the greeting, with what the store holds.
  const first = reuseIdle(inventoried(fresh(), 34, 7), T0)
  expect(first.greeted).toBe('full')
  expect(text(bandRow(first, T0 + 1, 100))).toBe(`◇ compound ready · 34 lessons (7 guards)  ${HINT}`)
  expect(text(bandRow(first, T0 + 1, 50))).toBe('◇ compound ready · 34 lessons (7 guards)')
  expect(bandRow(first, T0 + GONE_MS, 100)).toEqual([])
  expect(text(bandRow(reuseIdle(inventoried(fresh(), 1, 1), T0), T0 + 1, 50))).toBe('◇ compound ready · 1 lesson (1 guard)')
  // The first check found something: its result carries the greeting, and the next does not.
  const found = reuseFound(inventoried(fresh(), 34, 7), ['cdl-bib-cite'], 0, T0)
  expect(text(bandRow(found, T0 + 1, 100))).toBe('◆ compound reuse found · cdl-bib-cite  34 lessons (7 guards) ready')
  expect(text(bandRow(reuseFound(inventoried(newTurn(found), 34, 7), ['cdl-bib-cite'], 0, T0 + 9), T0 + 10, 100))).toBe('◆ compound reuse found · cdl-bib-cite')
  expect(inventoried(found, 35, 7)).toBe(found)
  // A prompt too short for a check: greeted without counts, and the counts follow once, when they are known.
  const bare = greeted(fresh(), T0)
  expect(text(bandRow(bare, T0 + 1, 100))).toBe(`◇ compound ready · ${HINT}`)
  expect(greeted(newTurn(bare), T0 + 5)).toEqual(newTurn(bare))
  const later = reuseIdle(inventoried(newTurn(bare), 34, 7), T0 + 9)
  expect(text(bandRow(later, T0 + 10, 50))).toBe('◇ compound ready · 34 lessons (7 guards)')
  expect(greeted(newTurn(later), T0 + 20)).toEqual(newTurn(later))
  // A result the turn already put on the band is not written over by a greeting.
  const told = noted(fresh(), 'unsettled', '2 lessons', T0)
  expect(greeted(told, T0 + 1)).toBe(told)
  expect(reuseIdle(inventoried(told, 3, 0), T0 + 1).note?.kind).toBe('unsettled')
  // Another session starts over.
  expect(forSession(later, 's2').greeted).toBe(undefined)
})

test('a reuse check that found nothing closes dim and is gone in three seconds, with no blank row after the spinner', async () => {
  const greetedBand = newTurn(reuseIdle(inventoried(fresh(), 34, 7), T0))
  const idle = reuseIdle(ended(began(greetedBand, 'r', 'reuse', T0 + 100), 'r'), T0 + 600)
  const row = bandRow(idle, T0 + 601, 100)
  expect(text(row)).toBe('◇ compound nothing to reuse')
  expect(row.every(s => s.dim === true && s.bold !== true)).toBe(true)
  expect(motion(idle, T0 + 601)).toBe('fade')
  expect(bandRow(idle, T0 + 600 + (GONE_MS - FRESH_MS) - 1, 100).length > 0).toBe(true)
  expect(bandRow(idle, T0 + 600 + (GONE_MS - FRESH_MS), 100)).toEqual([])
  expect(motion(idle, T0 + 600 + (GONE_MS - FRESH_MS))).toBe('still')
  // A check that failed is an error on the band, not "nothing to reuse".
  const failed = erred(greetedBand, 1)
  expect(reuseIdle(failed, T0 + 600)).toBe(failed)
})

// ---- the learn loop ----

test('the track shows the four steps with the current one bright', async () => {
  expect(text(trackSegs('failed', false))).toBe('● failed → ○ fixed → ○ owed → ○ recorded')
  expect(text(trackSegs('fixed', false))).toBe('✓ failed → ● fixed → ○ owed → ○ recorded')
  expect(text(trackSegs('owed', false))).toBe('✓ failed → ✓ fixed → ● owed → ○ recorded')
  expect(text(trackSegs('recorded', false))).toBe('✓ failed → ✓ fixed → ✓ owed → ✔ recorded')
  expect(text(trackSegs('declined', false))).toBe('✓ failed → ✓ fixed → ✓ owed → ○ declined')
  expect(text(trackSegs('owed', true))).toBe('✓ ✓ ● owed ○')
  const owed = trackSegs('owed', false)
  const current = owed.filter(s => s.bold === true)
  expect(current).toEqual([{ text: '● owed', color: 'warning', bold: true }])
  // Every other step is dim.
  expect(owed.filter(s => s.bold !== true).every(s => s.dim === true)).toBe(true)
  expect(trackSegs('recorded', false).find(s => s.bold === true)!.color).toBe('success')
})

test('a failure, its fix, a lesson owed and the lesson recorded move the track along', async () => {
  let band = stepped(fresh(), 'failed', T0)
  expect(text(bandRow(band, T0 + 1, 100))).toBe(`◌ compound ${WATCHING}   ● failed → ○ fixed → ○ owed → ○ recorded`)
  // A failure nobody fixed fades like any result.
  expect(bandRow(band, T0 + GONE_MS, 100)).toEqual([])

  band = began(stepped(band, 'fixed', T0 + 10), 'f', 'fix', T0 + 10)
  expect(text(bandRow(band, T0 + 20, 100))).toContain('is this the fix?   ✓ failed → ● fixed → ○ owed → ○ recorded')
  // While the judge is asked the track stays, however long it takes.
  expect(text(bandRow(band, T0 + GONE_MS + 20, 100))).toContain('● fixed')

  band = captured(ended(band, 'f'), T0 + 30)
  expect(band.owed).toBe(1)
  expect(text(bandRow(band, T0 + 40, 100))).toBe('● compound lesson owed   ✓ failed → ✓ fixed → ● owed → ○ recorded')
  // Owed stays until it is settled: an hour later it is still there, and nothing animates.
  expect(text(bandRow(band, T0 + 3_600_000, 100))).toBe('● compound lesson owed   ✓ failed → ✓ fixed → ● owed → ○ recorded')
  expect(motion(band, T0 + 3_600_000)).toBe('still')
  // A new failure does not push the owed lesson off the track.
  expect(stepped(band, 'failed', T0 + 50)).toBe(band)
  expect(newTurn(band).track).toEqual(band.track)

  const recording = began(band, 'r', 'record', T0 + 60)
  expect(text(bandRow(recording, T0 + 61, 100))).toContain('recording the lesson   ✓ failed → ✓ fixed → ● owed → ○ recorded')

  const done = settledBy(band, { type: 'learn', lesson: 'deploy-needs-target', update: false }, T0 + 70)
  expect(done.owed).toBe(0)
  expect(text(bandRow(done, T0 + 71, 100))).toBe('✔ compound lesson recorded · deploy-needs-target   ✓ failed → ✓ fixed → ✓ owed → ✔ recorded')
  expect(bandRow(done, T0 + 71, 100)[0]).toEqual({ text: '✔ ', color: 'success', bold: true })
  expect(bandRow(done, T0 + 70 + GONE_MS, 100)).toEqual([])
})

test('the judge saying "no fix" takes the track back; a recalled lesson owes nothing', async () => {
  const fixing = stepped(stepped(fresh(), 'failed', T0), 'fixed', T0 + 5)
  expect(unfixed(fixing).track).toBe(null)
  const owed = captured(fresh(), T0)
  expect(unfixed(owed)).toBe(owed)
})

test('declining settles the debt and every strengthening', async () => {
  const band = weakened(captured(fresh(), T0), 'flaky-lesson', T0 + 1)
  const done = settledBy(band, { type: 'skip', why: 'a typo' }, T0 + 10)
  expect(done.owed).toBe(0)
  expect(done.weak).toEqual([])
  expect(text(bandRow(done, T0 + 11, 100))).toBe('○ compound lesson declined   ✓ failed → ✓ fixed → ✓ owed → ○ declined')
})

test('a lesson recorded with nothing owed flashes without a track', async () => {
  const done = settledBy(fresh(), { type: 'learn', lesson: 'a', update: false }, T0)
  expect(done.track).toBe(null)
  expect(text(bandRow(done, T0 + 1, 100))).toBe('✔ compound lesson recorded · a')
})

test('an ineffective lesson owes a strengthening until it is rewritten', async () => {
  const band = weakened(fresh(), 'build-needs-profile', T0)
  expect(text(bandRow(band, T0 + 1, 100))).toBe('▲ compound lesson ineffective · build-needs-profile')
  // The result fades into the state that stays.
  expect(text(bandRow(band, T0 + GONE_MS, 100))).toBe('▲ compound lesson to strengthen · build-needs-profile')
  expect(weakened(band, 'build-needs-profile', T0 + 5).weak).toEqual(['build-needs-profile'])
  const other = settledBy(band, { type: 'learn', lesson: 'another', update: true }, T0 + 10)
  expect(other.weak).toEqual(['build-needs-profile'])
  const fixed = settledBy(band, { type: 'learn', lesson: 'build-needs-profile', update: true }, T0 + 10)
  expect(fixed.weak).toEqual([])
  expect(text(bandRow(fixed, T0 + 11, 100))).toBe('✔ compound lesson rewritten · build-needs-profile')
})

test('what the session did with the CLI is a result: moved, proposed, made a skill, removed', async () => {
  const kind = (event: Record<string, unknown> & { type: string }) => settledBy(fresh(), event, T0).note?.kind
  expect(kind({ type: 'promote', lesson: 'a', to: 'user' })).toBe('moved')
  expect(kind({ type: 'promote', lesson: 'a', to: 'general' })).toBe('proposed')
  expect(kind({ type: 'promote', lesson: 'a', to: 'user', auto: true })).toBe(undefined)
  expect(kind({ type: 'skill', lesson: 'a' })).toBe('skill')
  expect(kind({ type: 'rm', lesson: 'a' })).toBe('removed')
  expect(kind({ type: 'guard', lesson: 'a' })).toBe(undefined)
})

test('errors stay until Claude is told, and what else is open rides along as marks', async () => {
  const band = erred(fresh(), 2)
  expect(text(bandRow(band, T0, 100))).toBe('✖ compound 2 compound errors · Claude is told at the next prompt')
  expect(bandRow(band, T0, 100)[0]!.color).toBe('error')
  expect(bandRow(erred(band, 0), T0, 100)).toEqual([])
  expect(erred(band, 2)).toBe(band)
  // Owed and an error at once: the error leads, the debt is a mark and the track stays.
  const both = erred(captured(fresh(), T0), 1)
  const row = text(bandRow(both, T0 + GONE_MS, 140))
  expect(row).toContain('1 compound error')
  expect(row).toContain('● owed → ○ recorded')
  // The track already says a lesson is owed: no second mark for it.
  expect(row).not.toContain('1 owed')
  // A debt the stop moment counted with no track in sight is a mark beside a spinner or an error.
  const untracked = { ...erred(captured(fresh(), T0), 1), track: null }
  expect(text(bandRow(untracked, T0 + GONE_MS, 140))).toBe('✖ compound 1 compound error · Claude is told at the next prompt  ● 1 owed')
  expect(text(bandRow(began({ ...untracked, errors: 0 }, 'x', 'reuse', T0), T0 + 1, 140))).toBe(`${frameAt(T0 + 1)} compound checking for reusable work  ● 1 owed`)
  expect(text(bandRow(began(erred(weakened(fresh(), 'a', T0), 1), 'x', 'reuse', T0 + GONE_MS), T0 + GONE_MS, 140))).toContain('▲ 1 to strengthen  ✖ 1 error')
})

test('the stop moment\'s count is the log\'s: it sets what is owed and clears what was settled', async () => {
  const band = synced(fresh(), 2, ['a'], T0)
  expect(band.owed).toBe(2)
  expect(band.track).toEqual({ step: 'owed', at: T0 })
  expect(text(bandRow(band, T0 + GONE_MS, 100))).toContain('2 lessons owed')
  expect(text(bandRow(band, T0 + GONE_MS, 100))).toContain('▲ 1 to strengthen')
  const clear = synced(band, 0, [], T0 + 5)
  expect(clear.track).toBe(null)
  expect(bandRow(clear, T0 + GONE_MS, 100)).toEqual([])
})

test('a typed prompt clears what the last turn said and keeps what is owed', async () => {
  const band = began(noted(captured(erred(fresh(), 1), T0), 'guard', 'x', T0), 'b', 'fix', T0)
  const next = newTurn(band)
  expect(next.note).toBe(null)
  expect(next.busy).toEqual([])
  expect(next.owed).toBe(1)
  expect(next.errors).toBe(1)
  expect(newTurn(stepped(fresh(), 'failed', T0)).track).toBe(null)
})

// ---- width ----

test('the row never overflows: the track shrinks, the marks go, the name is cut', async () => {
  const band = settledBy(captured(fresh(), T0), { type: 'learn', lesson: 'a-very-long-lesson-name-that-goes-on-and-on-and-on', update: false }, T0 + 1)
  for (let columns = 12; columns <= 140; columns += 1) {
    for (const now of [T0 + 2, T0 + FRESH_MS + 2]) {
      expect(width(bandRow(band, now, columns)) <= columns, `${columns} columns`).toBe(true)
      expect(width(bandRow(erred(band, 3), now, columns)) <= columns, `${columns} columns with marks`).toBe(true)
    }
  }
  expect(text(bandRow(band, T0 + 2, 100))).toContain('✓ ✓ ✓ ✔ recorded')
  expect(text(bandRow(band, T0 + 2, 140))).toContain('✓ owed → ✔ recorded')
  expect(text(bandRow(band, T0 + 2, 40))).toContain('…')
  expect(bandRow(band, T0 + 2, 8)).toEqual([])
  // At 100 columns the ordinary rows fit whole.
  expect(text(bandRow(captured(fresh(), T0), T0, 100))).toContain('○ recorded')
})

// ---- what the timer needs ----

test('nothing moves on an empty band, and a redraw is asked for only when a phase turns', async () => {
  expect(motion(null, T0)).toBe('still')
  expect(motion(undefined, T0)).toBe('still')
  expect(motion(fresh(), T0)).toBe('still')
  expect(phaseKey(null, T0)).toBe('')
  const band = noted(fresh(), 'reuse', '1 lesson or skill', T0)
  const keys = [0, 500, FLASH_MS, FLASH_MS + 500, FRESH_MS, FRESH_MS + 500, GONE_MS].map(ms => phaseKey(band, T0 + ms))
  expect(keys[0]).toBe(keys[1])
  expect(keys[2]).toBe(keys[3])
  expect(keys[4]).toBe(keys[5])
  expect(new Set(keys).size).toBe(4)
})

// ---- the pane ----

const STATUS = JSON.stringify({
  ok: true,
  totals: { reused: 4, guarded: 9, recalled: 1, recorded: 7, since: '2026-09-12T10:00:00Z' },
  health: [
    { check: 'python', status: 'PASS', detail: '3.12.1' },
    { check: 'cli', status: 'WARN', detail: '`compound` is not on PATH' },
    { check: 'duplicates', status: 'FAIL', detail: 'x at /a, /b' },
  ],
  store: { project: { lessons: 2, skills: 0, guards: 1 }, user: { lessons: 5, skills: 4, guards: 0 }, general: { lessons: 0, skills: 2, guards: 0 } },
  lessons: [
    { name: 'never-used', level: 'user', kind: 'lesson', guard: false, reuse: 0, guard_hits: 0, recall: 0, flag: 'never used' },
    { name: 'build-needs-profile', level: 'project', kind: 'lesson', guard: false, reuse: 4, guard_hits: 0, recall: 2, flag: 'ineffective' },
    { name: 'no-marker-echo', level: 'project', kind: 'lesson', guard: true, reuse: 0, guard_hits: 9, recall: 0, flag: '' },
  ],
  recent: [{ ts: '2026-10-03T12:00:00Z', type: 'guard', lesson: 'no-marker-echo' }],
  open: {
    ineffective: [{ name: 'build-needs-profile', level: 'project', path: '/p', recall: 2 }],
    unsettled: [{ id: 'abc123', age: '2h', project: '/work/alpha', failed: './x', fixed: './x --y' }],
    candidates: [{ lesson: 'zsh-equals-word', from: '/work/beta', seen_in: ['/work/alpha'], command: 'c' }],
    skips: [{ why: 'a typo' }],
    errors: [{ where: 'reuse.judge', message: 'no answer' }],
  },
})
const EVENTS = JSON.stringify([
  { ts: '2026-10-03T12:00:00Z', type: 'reuse', lessons: ['a', 'b'], prompts: ['p'] },
  { ts: '2026-10-03T12:01:00Z', type: 'recall', lesson: 'build-needs-profile', ineffective: true },
  { ts: '2026-10-03T12:02:00Z', type: 'capture', fixed: './deploy.sh --target staging' },
  { ts: '2026-10-03T12:03:00Z', type: 'refuse', why: 'debt' },
  { ts: '2026-10-03T12:04:00Z', type: 'learn', lesson: 'deploy-needs-target', update: false },
])

test('the pane\'s data is what the CLI printed: levels, the most used first, events, what is open', async () => {
  const board = boardFrom(STATUS, EVENTS, 's1', T0)!
  expect(board.session).toBe('s1')
  expect(board.checks).toBe(3)
  expect(board.health.map(h => h.check)).toEqual(['cli', 'duplicates'])
  expect(board.levels).toEqual([
    { level: 'project', lessons: 2, skills: 0, guards: 1 },
    { level: 'user', lessons: 5, skills: 4, guards: 0 },
    { level: 'general', lessons: 0, skills: 2, guards: 0 },
  ])
  expect(board.lessons.map(l => l.name)).toEqual(['no-marker-echo', 'build-needs-profile', 'never-used'])
  expect(board.lessons[0]).toEqual({ name: 'no-marker-echo', level: 'project', guard: true, reuse: 0, guards: 9, recall: 0, flag: '' })
  expect(board.recent[0]).toEqual({ at: Date.parse('2026-10-03T12:00:00Z') / 1000, type: 'reuse', text: 'a, b', tail: '1 earlier request' })
  expect(board.recent.map(r => `${r.type} ${r.text}`)).toEqual([
    'reuse a, b',
    'recall build-needs-profile (ineffective)',
    'capture ./deploy.sh --target staging',
    'refuse lesson owed',
    'learn deploy-needs-target',
  ])
  expect(board.open.unsettled).toEqual(['abc123 ./x --y (2h, alpha)'])
  expect(board.open.ineffective).toEqual(['build-needs-profile (recalled 2 times)'])
  expect(board.open.candidates).toEqual(['zsh-equals-word in beta'])
  expect(board.open.errors).toEqual(['reuse.judge: no answer'])
  expect(board.open.skips).toBe(1)
  // With no events reply, the status's own recent rows are the timeline.
  expect(boardFrom(STATUS, '', 's1', T0)!.recent.map(r => r.type)).toEqual(['guard'])
  expect(boardFrom('not json', EVENTS, 's1', T0)).toBe(undefined)
  // The judge's verdicts are in the log to be measured: the timeline leaves them out.
  const judged = JSON.stringify([{ ts: '2026-10-03T12:00:00Z', type: 'guard', lesson: 'a' }, { ts: '2026-10-03T12:00:01Z', type: 'judge', moment: 'fix', verdict: 'none', ms: 800 }])
  expect(boardFrom(STATUS, judged, 's1', T0)!.recent.map(r => r.type)).toEqual(['guard'])
  expect(boardFrom('[]', EVENTS, 's1', T0)).toBe(undefined)
})

test('the pane lists what is open first, then the levels, the most used and the events, newest first', async () => {
  const lines = boardLines(boardFrom(STATUS, EVENTS, 's1', T0), 60).map(text)
  const at = (needle: string) => lines.findIndex(l => l.includes(needle))
  expect(lines[0]).toBe('✖ 1 check failed  3 checks  cli')
  expect(lines[1]).toBe('  ✖ duplicates: x at /a, /b')
  expect(at('Open') < at('Levels') && at('Levels') < at('Most used') && at('Most used') < at('Recent')).toBe(true)
  expect(lines).toContain('  ● 1 lesson owed')
  expect(lines).toContain('  ▲ 1 ineffective lesson')
  expect(lines).toContain('  ✖ 1 error in the last 7 days')
  expect(lines).toContain('  ○ 1 lesson declined')
  // A guard is a lesson that carries a pattern: it is counted among the lessons, and the row says so.
  expect(lines).toContain('  project  2 lessons (1 guard)   0 skills')
  expect(lines).toContain('  user     5 lessons (0 guards)  4 skills')
  expect(lines[at('Most used')]).toBe('Most used              ◆ reused     ■ guarded    ↺ recalled')
  // A lesson never used is not among the most used.
  expect(at('never-used')).toBe(-1)
  expect(lines[at('no-marker-echo  ')]).toBe('  no-marker-echo       0            9 ▇▇▇▇▇▇     0')
  // The timeline says the word a person reads for each event, never the log's type name.
  expect(at('recorded deploy-needs-target') < at('reused   a, b · 1 earlier request')).toBe(true)
  expect(at('● owed     ./deploy.sh --target staging') > 0).toBe(true)
  for (const type of ['learn ', 'reuse ', 'capture', 'refuse ', 'recall ']) expect(at(` ${type}`), type).toBe(-1)
  // The timeline's glyph and colour are the band's.
  const learn = boardLines(boardFrom(STATUS, EVENTS, 's1', T0), 60).find(l => text(l).includes('recorded deploy'))!
  expect(learn.some(s => s.text === '✔ ' && s.color === 'success')).toBe(true)
})

test('the most used table is in columns: each count ends under its legend glyph and each bar starts in one cell', async () => {
  const lessons = [
    { name: 'the-last-column-holds-the-longest-bar', reuse: 0, guard_hits: 0, recall: 12 },
    { name: 'a-long-lesson-name-that-is-cut-in-a-narrow-pane', reuse: 12, guard_hits: 0, recall: 3 },
    { name: 'short', reuse: 0, guard_hits: 7, recall: 0 },
    { name: 'mid-length-name', reuse: 1, guard_hits: 1, recall: 1 },
  ]
  const board = boardFrom(JSON.stringify({ health: [], store: {}, lessons, open: {} }), '[]', 's1', T0)!
  for (const columns of [36, 44, 49, 60, 100, 140]) {
    const lines = boardLines(board, columns).map(text)
    const head = lines.findIndex(l => l.startsWith('Most used'))
    const rows = lines.slice(head + 1, head + 1 + lessons.length)
    for (const line of boardLines(board, columns)) expect(width(line) <= columns, `${columns}: ${text(line)}`).toBe(true)
    const glyphs = ['◆', '■', '↺'].map(g => [...lines[head]!].indexOf(g))
    expect(glyphs.every(g => g > 0), `${columns}: ${lines[head]}`).toBe(true)
    for (const row of rows) {
      const cells = [...row]
      for (const g of glyphs) {
        // The count's last digit is under the glyph, and the cell after it is the gap before the bar.
        expect(/\d/.test(cells[g] ?? ''), `${columns}: a digit under the glyph in "${row}"`).toBe(true)
        expect(cells[g + 1] === undefined || cells[g + 1] === ' ', `${columns}: a gap after the count in "${row}"`).toBe(true)
        expect([undefined, ' ', '▇']).toContain(cells[g + 2])
      }
      expect(row).toBe(row.trimEnd())
      expect(row.endsWith('…')).toBe(false)
    }
  }
  // A two-digit count widens the count column for every row; one digit stays under the glyph.
  const wide = boardLines(board, 100).map(text)
  expect(wide[wide.findIndex(l => l.startsWith('Most used')) + 1]).toContain(' 12 ▇▇▇▇▇▇')
})

test('the recent rows are in columns whatever the longest event type', async () => {
  const events = JSON.stringify([
    { ts: '2026-10-03T12:00:00Z', type: 'learn', lesson: 'x' },
    { ts: '2026-10-03T12:01:00Z', type: 'candidate', lesson: 'x', project: 'y' },
  ])
  const lines = boardLines(boardFrom(STATUS, events, 's1', T0), 80).map(text)
  const rows = lines.slice(lines.indexOf('Recent') + 1)
  expect(rows.length).toBe(2)
  const starts = rows.map(r => r.indexOf(' x') )
  expect(starts[0]).toBe(starts[1])
})

test('the pane opens with the totals: what the log holds of the mod helping, and since when', async () => {
  const now = new Date(2026, 9, 4, 14, 0, 0).getTime()
  const board = boardFrom(STATUS, EVENTS, 's1', now)!
  expect(board.totals).toEqual({ reused: 4, guarded: 9, recalled: 1, recorded: 7, since: Date.parse('2026-09-12T10:00:00Z') / 1000 })
  const lines = boardLines(board, 100).map(text)
  const head = lines.indexOf(`Compound interest  since ${dateText(board.totals!.since, now)}`)
  expect(head, lines.join('\n')).toBe(lines.findIndex(l => l === '') + 1)
  expect(head < lines.indexOf('Open')).toBe(true)
  expect(lines[head + 1]).toBe('  ◆ 4 reuses offered  ■ 9 calls stopped by a guard  ↺ 1 lesson recalled  ✔ 7 lessons recorded')
  const row = boardLines(board, 100)[head + 1]!
  expect(row.find(s => s.text.includes('■'))!.color).toBe(NOTES.guard.color)
  // A narrow pane wraps the totals; it never cuts them.
  const narrow = boardLines(board, 30).map(text)
  const at = narrow.indexOf('Compound interest')
  expect(narrow.slice(at, at + 6)).toEqual(['Compound interest', `  since ${dateText(board.totals!.since, now)}`, '  ◆ 4 reuses offered', '  ■ 9 calls stopped by a guard', '  ↺ 1 lesson recalled', '  ✔ 7 lessons recorded'])
  // Nothing is claimed that the log cannot support.
  expect(lines.join(' ')).not.toMatch(/saved|tokens|minutes/)
  // An empty log, and a status from a CLI that totals nothing.
  const empty = boardFrom(JSON.stringify({ health: [], store: {}, lessons: [], open: {}, totals: { reused: 0, guarded: 0, recalled: 0, recorded: 0, since: null } }), '[]', 's1', now)!
  expect(boardLines(empty, 60).map(text)).toContain('  nothing yet')
  const old = boardFrom(JSON.stringify({ health: [], store: {}, lessons: [], open: {} }), '[]', 's1', now)!
  expect(old.totals).toBe(undefined)
  expect(boardLines(old, 60).map(text).some(l => l.includes('Compound interest'))).toBe(false)
})

test('a time is how long ago: seconds, minutes, hours, yesterday, then the date', async () => {
  const now = new Date(2026, 9, 4, 14, 0, 0).getTime()
  const s = (d: Date) => Math.floor(d.getTime() / 1000)
  expect(ago(s(new Date(now - 5_000)), now)).toBe('5s')
  expect(ago(s(new Date(now - 125_000)), now)).toBe('2m')
  expect(ago(s(new Date(now - 3 * 3_600_000)), now)).toBe('3h')
  // 23:00 the evening before is fifteen hours ago; 00:30 the day before is yesterday.
  expect(ago(s(new Date(2026, 9, 3, 23, 0)), now)).toBe('15h')
  expect(ago(s(new Date(2026, 9, 3, 0, 30)), now)).toBe('yesterday')
  expect(ago(s(new Date(2026, 9, 2, 23, 30)), now)).toBe('2 Oct')
  expect(ago(s(new Date(2025, 11, 31, 12, 0)), now)).toBe('31 Dec 2025')
  expect(ago(0, now)).toBe('?')
  // A time ahead of the clock is a date, never a negative age.
  expect(ago(s(new Date(2026, 9, 9, 12, 0)), now)).toBe('9 Oct')
  // The pane's rows from different days cannot be confused, and the ages are in one column.
  const iso = (d: Date) => d.toISOString().replace(/\.\d+Z$/, 'Z')
  const events = JSON.stringify([
    { ts: iso(new Date(2026, 9, 2, 22, 50)), type: 'learn', lesson: 'old-one' },
    { ts: iso(new Date(2026, 9, 3, 2, 50)), type: 'guard', lesson: 'zsh-equals-word' },
    { ts: iso(new Date(now - 120_000)), type: 'reuse', lessons: ['speckit-execute'], prompts: [] },
  ])
  const lines = boardLines(boardFrom(STATUS, events, 's1', now), 80).map(text)
  expect(lines.slice(lines.indexOf('Recent') + 1)).toEqual([
    '         2m ◆ reused   speckit-execute',
    '  yesterday ■ guarded  zsh-equals-word',
    '      2 Oct ✔ recorded old-one',
  ])
})

test('every event type has a word, and the three counters are named by theirs', async () => {
  for (const type of ['reuse', 'guard', 'recall', 'capture', 'remind', 'refuse', 'learn', 'skip', 'nudge', 'promote', 'candidate', 'skill', 'rm', 'error']) {
    expect(eventWord(type), type).toBe(WORDS[type]!)
    expect(eventWord(type).length <= 9, type).toBe(true)
  }
  expect([eventWord('reuse'), eventWord('guard'), eventWord('recall'), eventWord('capture'), eventWord('learn'), eventWord('skip')]).toEqual(['reused', 'guarded', 'recalled', 'owed', 'recorded', 'declined'])
  expect(eventWord('something-new')).toBe('something-new')
  const head = boardLines(boardFrom(STATUS, EVENTS, 's1', T0), 100).map(text).find(l => l.startsWith('Most used'))!
  expect(head).toContain('◆ reused')
  expect(head).toContain('■ guarded')
  expect(head).toContain('↺ recalled')
})

// What a pane holds when no name and no free text is long: every label is the pane's own.
const SHORT = JSON.stringify({
  totals: { reused: 12, guarded: 3, recalled: 4, recorded: 77, since: '2026-09-12T10:00:00Z' },
  health: [{ check: 'python', status: 'PASS', detail: '3.12.1' }, { check: 'cli', status: 'WARN', detail: 'w' }, { check: 'mod last fired', status: 'WARN', detail: 'w' }, { check: 'prompt log', status: 'WARN', detail: 'w' }],
  store: { project: { lessons: 2, skills: 0, guards: 1 }, user: { lessons: 32, skills: 4, guards: 7 }, general: { lessons: 0, skills: 6, guards: 0 } },
  lessons: [{ name: 'tomli', level: 'user', guard: true, reuse: 12, guard_hits: 3, recall: 4, flag: '' }, { name: 'zsh', level: 'user', guard: false, reuse: 1, guard_hits: 0, recall: 0, flag: '' }],
  open: {
    unsettled: [{ id: 'a1', age: '2h', project: '/w/p', failed: 'ls', fixed: 'ls -a' }],
    ineffective: [{ name: 'zsh', recall: 2 }],
    candidates: [{ lesson: 'zsh', from: '/w/b' }, { lesson: 'tomli', from: '/w/b' }],
    errors: [{ where: 'x', message: 'y' }],
    skips: [{ why: 'w' }],
  },
})
const SHORT_EVENTS = JSON.stringify([
  { ts: '2026-10-03T12:00:00Z', type: 'reuse', lessons: ['tomli'], prompts: ['p'] },
  { ts: '2026-10-03T12:01:00Z', type: 'candidate', lesson: 'zsh', project: 'y' },
  { ts: '2026-10-03T12:02:00Z', type: 'guard', lesson: 'zsh' },
  { ts: '2026-10-03T12:03:00Z', type: 'remind', captures: ['a1'] },
])

test('at 30, 40 and 60 columns the pane cuts none of its own labels: only a name or free text ever ends in an ellipsis', async () => {
  const now = Date.parse('2026-10-04T11:59:59Z')
  for (const columns of [30, 40, 60, 100]) {
    const lines = boardLines(boardFrom(SHORT, SHORT_EVENTS, 's1', now), columns)
    for (const line of lines) {
      expect(width(line) <= columns, `${columns}: ${text(line)}`).toBe(true)
      expect(text(line).endsWith('…'), `${columns}: ${text(line)}`).toBe(false)
    }
    const all = lines.map(text)
    // Every label is whole, on however many lines it took.
    const flat = all.map(l => l.trim()).join(' ')
    for (const label of ['3 warnings', '4 checks', 'cli, mod last fired, prompt log', 'Compound interest', '12 reuses offered', '3 calls stopped by a guard', '4 lessons recalled', '77 lessons recorded',
      '1 lesson owed', '1 ineffective lesson', '2 lessons that could move to the user level', '1 error in the last 7 days', '1 lesson declined', 'Levels', 'Most used', 'Recent']) {
      expect(flat, `${columns}: ${label}`).toContain(label)
    }
  }
  // The timeline keeps its words while there is room for them, and its glyphs always.
  const recent = (columns: number) => {
    const all = boardLines(boardFrom(SHORT, SHORT_EVENTS, 's1', now), columns).map(text)
    return all.slice(all.indexOf('Recent') + 1)
  }
  expect(recent(40)).toEqual(['  23h ● reminded  1 lesson owed', '  23h ■ guarded   zsh', '  23h ⇡ candidate zsh', '  23h ◆ reused    tomli'])
  expect(recent(30)).toEqual(['  23h ● 1 lesson owed', '  23h ■ zsh', '  23h ⇡ zsh', '  23h ◆ tomli'])
  // What a row adds beside its names is there when it fits whole, and is never cut.
  expect(recent(60)[3]).toBe('  23h ◆ reused    tomli · 1 earlier request')
  // The levels: a sentence a level where it fits, columns under the heading where it does not.
  const at = (columns: number) => boardLines(boardFrom(SHORT, SHORT_EVENTS, 's1', now), columns).map(text)
  expect(at(60)).toContain('  user     32 lessons (7 guards)  4 skills')
  expect(at(60)).toContain('  project   2 lessons (1 guard)   0 skills')
  for (const columns of [30, 40]) {
    expect(at(columns)).toContain('Levels lessons (guards) skills')
    expect(at(columns)).toContain('  project    2      (1)      0')
    expect(at(columns)).toContain('  user      32      (7)      4')
    expect(at(columns)).toContain('  general    0      (0)      6')
  }
  // A long name and a long call are cut, and nothing else is.
  const long = JSON.parse(SHORT) as { lessons: { name: string }[]; open: { unsettled: { fixed: string }[] } }
  long.lessons[0]!.name = 'a-lesson-name-that-goes-on-and-on-and-on-and-on'
  long.open.unsettled[0]!.fixed = 'python3 -c "import tomli; print(tomli.__version__)"'
  const events = JSON.stringify([{ ts: '2026-10-03T12:02:00Z', type: 'guard', lesson: 'zsh-equals-word', text: 'echo ==== a long separator line ====' }])
  for (const columns of [30, 40]) {
    const all = boardLines(boardFrom(JSON.stringify(long), events, 's1', now), columns).map(text)
    const cut = all.filter(l => l.includes('…'))
    expect(cut.length, `${columns}: ${cut.join(' | ')}`).toBe(3)
    expect(cut.every(l => l.includes('a-less') || l.includes('python3') || l.includes('zsh-equals')), cut.join(' | ')).toBe(true)
  }
})

test('the pane never draws a line wider than it was given', async () => {
  const board = boardFrom(STATUS, EVENTS, 's1', T0)
  for (const columns of [24, 30, 40, 60, 100]) {
    for (const line of boardLines(board, columns)) expect(width(line) <= columns, `${columns}: ${text(line)}`).toBe(true)
  }
})

test('a pane with nothing to show says so', async () => {
  expect(boardLines(null, 40).map(text)).toEqual(['Reading the store…'])
  const empty = boardFrom(JSON.stringify({ health: [{ check: 'python', status: 'PASS', detail: '' }], store: {}, lessons: [], open: {} }), '[]', 's1', T0)!
  const lines = boardLines(empty, 60).map(text)
  expect(lines[0]).toBe('✔ healthy  1 checks')
  expect(lines).toContain('Open  nothing waits for anyone')
  expect(lines).toContain('  nothing was reused, guarded or recalled yet')
  expect(lines).toContain('  no events yet')
  const broken = { ...empty, problem: 'compound status could not start' }
  expect(boardLines(broken, 60).map(text)).toEqual(['✖ compound status could not start'])
})

test('a bar is one cell a use while the counts fit, in proportion past that, and never empty for a use', async () => {
  expect(bar(0, 9, 6)).toBe('')
  expect(bar(1, 1, 6)).toBe('▇')
  expect(bar(3, 4, 6)).toBe('▇▇▇')
  expect(bar(9, 9, 6)).toBe('▇▇▇▇▇▇')
  expect(bar(1, 90, 6)).toBe('▇')
  expect(bar(45, 90, 6)).toBe('▇▇▇')
})

test('an event\'s line says what it was about', async () => {
  expect(eventText({ type: 'guard', lesson: 'a' })).toBe('a')
  expect(eventText({ type: 'skip', why: 'a typo, nothing to learn' })).toBe('a typo, nothing to learn')
  expect(eventText({ type: 'nudge', calls: 31 })).toBe('31 tool calls')
  expect(eventText({ type: 'promote', lesson: 'a', to: 'general' })).toBe('a → general')
  expect(eventText({ type: 'remind', captures: ['x', 'y'] })).toBe('2 lessons owed')
  expect(eventText({ type: 'remind', captures: ['x'] })).toBe('1 lesson owed')
  expect(['debt', 'strengthen', 'nudge'].map(why => eventText({ type: 'refuse', why }))).toEqual(['lesson owed', 'to strengthen', 'long turn'])
  // A reuse names what was offered; a guard, the lesson and the call it stopped.
  const reuse = { type: 'reuse', lessons: ['scripts/bibdupcheck.py', 'cdl-bib-cite'], prompts: ['p1', 'p2'] }
  expect([eventText(reuse), eventTail(reuse)]).toEqual(['bibdupcheck.py, cdl-bib-cite', '2 earlier requests'])
  expect([eventText({ type: 'reuse', lessons: [], prompts: ['p1'] }), eventTail({ type: 'reuse', lessons: [], prompts: ['p1'] })]).toEqual(['1 earlier request', ''])
  expect(eventText({ type: 'reuse', lessons: [], prompts: [] })).toBe('nothing')
  expect(eventTail({ type: 'guard', lesson: 'a' })).toBe('')
  expect(eventText({ type: 'guard', lesson: 'zsh-equals-word', text: 'echo ==== x ====' })).toBe('zsh-equals-word · echo ==== x ====')
  // What is neither a name nor free text always fits the timeline.
  for (const e of [{ type: 'remind', captures: Array.from({ length: 12 }, (_, i) => `c${i}`) }, { type: 'refuse', why: 'strengthen' }, { type: 'nudge', calls: 1234 }]) expect(eventText(e).length <= 16, eventText(e)).toBe(true)
  expect(eventText({ type: 'error', where: 'guard.check', message: 'timed out' })).toBe('guard.check: timed out')
  expect(eventText({ type: 'learn', lesson: 'a', update: true })).toBe('a (rewritten)')
})
