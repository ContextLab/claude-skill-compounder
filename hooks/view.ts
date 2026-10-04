import type {
  CompoundBand, CompoundBoard, CompoundBusyKind, CompoundCheck, CompoundDetail, CompoundItem, CompoundLesson, CompoundLevel, CompoundNoteKind, CompoundOpen, CompoundPane,
  CompoundPaneView, CompoundRecent, CompoundStep, CompoundTotals,
} from '../types'
import { drawn, oneLine, plain } from './safe'

// What the band above the prompt and the `/compound` pane show. Pure: values in, values
// out, no `$`. ./register keeps the band's state and the pane's data in `$.state`, changes
// them with the functions here, and turns the segments these functions answer into the
// surface's own Text elements.
//
// A glyph is one cell wide on every terminal font the mod was looked at in: none of them
// is an emoji.

// ---- glyphs, colours, labels -----------------------------------------------------------

export type Look = { glyph: string; color: string; label: string }

// A colour is a theme key (`success`, `error`, `warning`, `suggestion`, `claude`) or an
// ANSI name, so both follow the person's own theme.
export const SPINNER_COLOR = 'claude'

export const BUSY: Record<CompoundBusyKind, string> = {
  reuse: 'checking for reusable work',
  guard: 'checking the guards',
  recall: 'matching a recorded lesson',
  fix: 'is this the fix?',
  record: 'recording the lesson',
}

export const NOTES: Record<CompoundNoteKind, Look> = {
  reuse: { glyph: '◆', color: 'cyan', label: 'reuse found' },
  guard: { glyph: '■', color: 'error', label: 'guard stopped a call' },
  recall: { glyph: '↺', color: 'magenta', label: 'lesson recalled' },
  unsettled: { glyph: '●', color: 'warning', label: 'owed from earlier sessions' },
  recorded: { glyph: '✔', color: 'success', label: 'lesson recorded' },
  rewritten: { glyph: '✔', color: 'success', label: 'lesson rewritten' },
  declined: { glyph: '○', color: 'inactive', label: 'lesson declined' },
  moved: { glyph: '⇡', color: 'suggestion', label: 'lesson moved to the user level' },
  proposed: { glyph: '⇡', color: 'suggestion', label: 'lesson proposed to the general pool' },
  skill: { glyph: '✦', color: 'suggestion', label: 'lesson made a skill' },
  removed: { glyph: '−', color: 'inactive', label: 'removed' },
  ineffective: { glyph: '▲', color: 'warning', label: 'lesson ineffective' },
  nudge: { glyph: '?', color: 'suggestion', label: 'asked whether anything was learned' },
  ready: { glyph: '◇', color: 'suggestion', label: 'ready' },
  idle: { glyph: '◇', color: 'inactive', label: 'nothing to reuse' },
}

// What the greeting says beside the counts.
export const HINT = '/compound opens the dashboard'

// What the band says while a failed call is held and no fix was seen yet.
export const WATCHING = 'watching for the fix'

// The states that stay until they are settled.
export const OWED: Look = { glyph: '●', color: 'warning', label: 'lesson owed' }
export const WEAK: Look = { glyph: '▲', color: 'warning', label: 'lesson to strengthen' }
export const ERROR: Look = { glyph: '✖', color: 'error', label: 'compound error' }

// The event types of the log, as the pane's timeline draws them: the band's own glyphs.
const EVENTS: Record<string, Look> = {
  reuse: NOTES.reuse,
  guard: NOTES.guard,
  recall: NOTES.recall,
  capture: OWED,
  remind: NOTES.unsettled,
  refuse: { glyph: '■', color: 'warning', label: 'stop refused' },
  learn: NOTES.recorded,
  skip: NOTES.declined,
  nudge: NOTES.nudge,
  promote: NOTES.moved,
  candidate: { glyph: '⇡', color: 'inactive', label: 'could move to the user level' },
  skill: NOTES.skill,
  rm: NOTES.removed,
  error: ERROR,
}

export function eventLook(type: string): Look {
  return EVENTS[type] ?? { glyph: '·', color: 'inactive', label: type }
}

// The word a person is shown for each event type. The type names are the log's; these are
// the words of the pane and of `compound status`, which holds the same table (EVENT_WORDS).
export const WORDS: Record<string, string> = {
  reuse: 'reused',
  guard: 'guarded',
  recall: 'recalled',
  capture: 'owed',
  remind: 'reminded',
  refuse: 'refused',
  learn: 'recorded',
  skip: 'declined',
  nudge: 'asked',
  promote: 'moved',
  candidate: 'candidate',
  skill: 'skill',
  rm: 'removed',
  judge: 'judged',
  error: 'error',
  retry: 'retried',
}

export function eventWord(type: string): string {
  return WORDS[type] ?? type
}

// ---- time ------------------------------------------------------------------------------

// Ten frames a second while a spinner shows. A result is bright for FLASH_MS, plain until
// FRESH_MS, dim until GONE_MS, and then not drawn. A check that never reported its end
// (its hook was abandoned) stops counting after BUSY_MAX_MS, so no spinner turns forever.
export const FRAMES = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'] as const
export const FRAME_MS = 100
export const FLASH_MS = 1200
export const FRESH_MS = 5000
export const GONE_MS = 8000
export const BUSY_MAX_MS = 60000
// A guard check is fast: its spinner shows only once it has taken this long.
export const GUARD_SHOW_MS = 350

export function frameAt(now: number): string {
  return FRAMES[Math.floor(Math.max(0, now) / FRAME_MS) % FRAMES.length] ?? FRAMES[0]
}

export type Phase = 'flash' | 'fresh' | 'dim' | 'gone'

export function phaseAt(at: number, now: number): Phase {
  const age = Math.max(0, now - at)
  if (age < FLASH_MS) return 'flash'
  if (age < FRESH_MS) return 'fresh'
  if (age < GONE_MS) return 'dim'
  return 'gone'
}

// ---- the band's state ------------------------------------------------------------------

export function emptyBand(session: string): CompoundBand {
  return { session, busy: [], note: null, owed: 0, weak: [], errors: 0, track: null }
}

// The state as this session's: another session's (the one before a /clear) starts over.
export function forSession(band: CompoundBand | null | undefined, session: string): CompoundBand {
  return band === null || band === undefined || band.session !== session ? emptyBand(session) : band
}

function liveBusy(band: CompoundBand, now: number) {
  return band.busy.filter(b => now - b.since < BUSY_MAX_MS)
}

export function began(band: CompoundBand, id: string, kind: CompoundBusyKind, now: number): CompoundBand {
  return { ...band, busy: [...liveBusy(band, now).filter(b => b.id !== id), { id, kind, since: now }] }
}

export function ended(band: CompoundBand, id: string): CompoundBand {
  return band.busy.some(b => b.id === id) ? { ...band, busy: band.busy.filter(b => b.id !== id) } : band
}

export function noted(band: CompoundBand, kind: CompoundNoteKind, text: string, now: number, detail = ''): CompoundBand {
  const more = oneLine(detail, 80)
  return { ...band, note: { kind, text: oneLine(text, 80), at: now, ...(more === '' ? {} : { detail: more }) } }
}

// ---- the greeting, and a check that found nothing ---------------------------------------

// The guards are among the lessons: a lesson that carries a pattern.
function readyText(c: { lessons: number; guards: number }): string {
  return `${count(c.lessons, 'lesson')} (${count(c.guards, 'guard')})`
}

function noteShows(band: CompoundBand, now: number): boolean {
  return band.note !== null && phaseAt(band.note.at, now) !== 'gone'
}

// The inventory was read at a prompt: the store's counts, kept for the greeting.
export function inventoried(band: CompoundBand, lessons: number, guards: number): CompoundBand {
  return band.greeted === 'full' ? band : { ...band, counts: { lessons, guards } }
}

// A typed prompt too short for a reuse check: the session's first is greeted without the
// counts, which nothing has read yet. A result this turn already put on the band stays.
export function greeted(band: CompoundBand, now: number): CompoundBand {
  if (band.greeted !== undefined || noteShows(band, now)) return band
  return { ...noted(band, 'ready', '', now, HINT), greeted: 'bare' }
}

// The reuse check found something: the items, by name, and how many earlier requests. The
// session's first result also carries the greeting.
export function reuseFound(band: CompoundBand, items: readonly string[], earlier: number, now: number): CompoundBand {
  const greet = band.counts !== undefined && band.greeted !== 'full'
  const next = noted(band, 'reuse', reuseText(items, earlier), now, greet && band.counts !== undefined ? `${readyText(band.counts)} ready` : '')
  const names = items.map(i => oneLine(base(i), 80))
  return { ...next, note: next.note === null || names.length === 0 ? next.note : { ...next.note, names }, ...(greet ? { greeted: 'full' as const } : {}) }
}

// The reuse check ran and added nothing. The session's first is the greeting, with the
// counts; after that a dim close that is gone in three seconds, so the spinner does not
// end in a blank row. A check that failed says so as an error, and says nothing here.
export function reuseIdle(band: CompoundBand, now: number): CompoundBand {
  if (band.errors > 0 || noteShows(band, now)) return band
  if (band.counts !== undefined && band.greeted !== 'full') return { ...noted(band, 'ready', readyText(band.counts), now, HINT), greeted: 'full' }
  return { ...band, note: { kind: 'idle', text: '', at: now - FRESH_MS } }
}

// A call failed and is held, or a later call is being judged as its fix. Neither replaces
// the track of a lesson that is already owed.
export function stepped(band: CompoundBand, step: 'failed' | 'fixed', now: number): CompoundBand {
  return band.track?.step === 'owed' ? band : { ...band, track: { step, at: now } }
}

// The judge said the later call was no fix: the track goes back to the failure.
export function unfixed(band: CompoundBand): CompoundBand {
  return band.track?.step === 'fixed' ? { ...band, track: null } : band
}

// `text` says what the lesson is owed for: the call that worked.
export function captured(band: CompoundBand, now: number, text = ''): CompoundBand {
  return { ...band, owed: band.owed + 1, owedText: oneLine(text, 80), track: { step: 'owed', at: now } }
}

// An event that settled something, as the band shows it: the result it flashes and where
// the track ends. The counts it leaves are a first guess; `synced` then sets them to what
// the CLI says is still owed.
export function settledBy(band: CompoundBand, event: Record<string, unknown> & { type: string }, now: number): CompoundBand {
  const name = typeof event.lesson === 'string' ? event.lesson : ''
  const closes = band.owed > 0 || band.track !== null
  if (event.type === 'skip') {
    return { ...noted(band, 'declined', '', now), owed: 0, owedText: '', weak: [], track: closes ? { step: 'declined', at: now } : null }
  }
  if (event.type === 'learn') {
    if (event.update === true && band.weak.includes(name)) return { ...noted(band, 'rewritten', name, now), weak: band.weak.filter(w => w !== name) }
    return { ...noted(band, event.update === true ? 'rewritten' : 'recorded', name, now), owed: 0, owedText: '', track: closes ? { step: 'recorded', at: now } : null }
  }
  if (event.type === 'promote' && event.auto !== true) return noted(band, event.to === 'general' ? 'proposed' : 'moved', name, now)
  if (event.type === 'skill') return noted(band, 'skill', name, now)
  if (event.type === 'rm') return { ...noted(band, 'removed', name, now), weak: band.weak.filter(w => w !== name) }
  return band
}

export function weakened(band: CompoundBand, name: string, now: number): CompoundBand {
  return { ...noted(band, 'ineffective', name, now), weak: band.weak.includes(name) ? band.weak : [...band.weak, name] }
}

// What the CLI said the session owes: the counts are the log's, not the band's guess, and
// `text` is what the newest lesson owed is for (the band keeps what it has when the caller
// has none). A band that already says so is answered as it is, so nothing is redrawn for it.
export function synced(band: CompoundBand, owed: number, weak: readonly string[], now: number, text?: string): CompoundBand {
  let track = band.track
  if (owed > 0 && track?.step !== 'owed') track = { step: 'owed', at: now }
  if (owed === 0 && track?.step === 'owed') track = null
  const owedText = owed === 0 ? '' : text === undefined || text === '' ? (band.owedText ?? '') : oneLine(text, 80)
  if (band.owed === owed && track === band.track && (band.owedText ?? '') === owedText && band.weak.length === weak.length && band.weak.every((w, i) => w === weak[i])) return band
  return { ...band, owed, owedText, weak: [...weak], track }
}

export function erred(band: CompoundBand, errors: number): CompoundBand {
  return band.errors === errors ? band : { ...band, errors }
}

// A typed prompt starts a turn: what the last turn's moments said is gone, and what is
// owed stays.
export function newTurn(band: CompoundBand): CompoundBand {
  return { ...band, busy: [], note: null, track: band.track?.step === 'owed' ? band.track : null }
}

// Whether anything on the band moves: a spinner turns, a result fades, or nothing does and
// no timer is needed.
export type Motion = 'spin' | 'fade' | 'still'

function trackPhase(band: CompoundBand, now: number): Phase {
  if (band.track === null) return 'gone'
  if (band.track.step === 'owed') return 'fresh'
  if (band.track.step === 'fixed' && liveBusy(band, now).some(b => b.kind === 'fix')) return 'fresh'
  return phaseAt(band.track.at, now)
}

function notePhase(band: CompoundBand, now: number): Phase {
  return band.note === null ? 'gone' : phaseAt(band.note.at, now)
}

export function motion(band: CompoundBand | null | undefined, now: number): Motion {
  if (band === null || band === undefined) return 'still'
  if (liveBusy(band, now).length > 0) return 'spin'
  const moving = (p: Phase, persistent: boolean) => p !== 'gone' && !persistent
  return moving(notePhase(band, now), false) || moving(trackPhase(band, now), band.track?.step === 'owed') ? 'fade' : 'still'
}

// What a redraw would change apart from the spinner's frame: two times with one key draw
// the same band, so a fading result is redrawn only when its phase turns.
export function phaseKey(band: CompoundBand | null | undefined, now: number): string {
  if (band === null || band === undefined) return ''
  return `${liveBusy(band, now).length}|${notePhase(band, now)}|${trackPhase(band, now)}`
}

// ---- the band's row --------------------------------------------------------------------

// A segment with a `key` is something to press: the pane draws it as a Button of that key
// whose label is the text. With a `hotkey` the surface draws the key before the label
// (`a: all lessons`), which is three cells more.
export type Seg = { text: string; color?: string; dim?: boolean; bold?: boolean; inverse?: boolean; key?: string; hotkey?: string }

// NOTHING THAT IS DRAWN CARRIES A CONTROL CHARACTER. A name, a call, a path or a lesson's
// text comes from a lesson file, a tool's output or the event log, and an escape sequence
// in it would recolour the row, move the cursor, set the terminal's title or write a link.
// It is taken out in two places, and every string passes both: where the CLI's JSON is
// read (`str`), and where a row leaves this file (`bandRow`, `boardLines`), which also
// covers the band's own state, kept in `$.state` and read back.
function clean(segs: readonly Seg[]): Seg[] {
  return segs.map(seg => ({ ...seg, text: drawn(seg.text) }))
}

export function width(segs: readonly Seg[]): number {
  return segs.reduce((n, s) => n + [...s.text].length + (s.hotkey === undefined ? 0 : 3), 0)
}

function clip(text: string, room: number): string {
  const chars = [...text]
  if (chars.length <= room) return text
  return room <= 1 ? chars.slice(0, Math.max(0, room)).join('') : `${chars.slice(0, room - 1).join('')}…`
}

function count(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}

export const TRACK: readonly CompoundStep[] = ['failed', 'fixed', 'owed', 'recorded']

// The learn loop as four steps. Those passed are ticked, the current one is bright, those
// ahead are dim. `compact` keeps the glyphs and the current step's name.
export function trackSegs(step: CompoundStep, compact: boolean): Seg[] {
  const at = step === 'declined' ? 3 : TRACK.indexOf(step)
  const out: Seg[] = []
  TRACK.forEach((name, i) => {
    const label = i === 3 && step === 'declined' ? 'declined' : name
    if (i > 0) out.push({ text: compact ? ' ' : ' → ', dim: true })
    if (i < at) out.push({ text: compact ? '✓' : `✓ ${label}`, color: 'success', dim: true })
    else if (i > at) out.push({ text: compact ? '○' : `○ ${label}`, dim: true })
    else if (step === 'recorded') out.push({ text: `✔ ${label}`, color: 'success', bold: true })
    else if (step === 'declined') out.push({ text: `○ ${label}`, bold: true })
    else out.push({ text: `● ${label}`, color: step === 'failed' ? 'error' : step === 'fixed' ? SPINNER_COLOR : 'warning', bold: true })
  })
  return out
}

type Main = { glyph: string; color: string; label: string; name: string; detail?: string; names?: readonly string[]; phase: Phase; from: 'busy' | 'note' | 'error' | 'owed' | 'weak' }

function mainOf(band: CompoundBand, now: number): Main | undefined {
  const busy = liveBusy(band, now)
  const last = busy[busy.length - 1]
  if (last !== undefined) return { glyph: frameAt(now), color: SPINNER_COLOR, label: BUSY[last.kind], name: '', phase: 'fresh', from: 'busy' }
  const phase = notePhase(band, now)
  if (band.note !== null && phase !== 'gone') {
    const look = NOTES[band.note.kind]
    return { ...look, name: band.note.text, detail: band.note.detail ?? '', ...(band.note.names === undefined ? {} : { names: band.note.names }), phase, from: 'note' }
  }
  if (band.errors > 0) return { ...ERROR, label: `${count(band.errors, 'compound error')}`, name: 'Claude is told at the next prompt', phase: 'fresh', from: 'error' }
  if (band.owed > 0) return { ...OWED, label: band.owed === 1 ? OWED.label : `${band.owed} lessons owed`, name: band.owedText ?? '', phase: 'fresh', from: 'owed' }
  const weak = band.weak[0]
  if (weak !== undefined) return { ...WEAK, name: band.weak.length === 1 ? weak : `${weak} +${band.weak.length - 1}`, phase: 'fresh', from: 'weak' }
  return undefined
}

// The persistent states the row is not already showing, as short marks after the main
// part. The track says "owed" itself, and a lesson just found ineffective is the one to
// strengthen.
function badges(band: CompoundBand, main: Main, tracked: boolean): Seg[] {
  const out: Seg[] = []
  const add = (look: Look, text: string) => out.push({ text: '  ', dim: true }, { text: look.glyph, color: look.color }, { text: ` ${text}`, dim: true })
  if (band.owed > 0 && main.from !== 'owed' && !tracked) add(OWED, `${band.owed} owed`)
  if (band.weak.length > 0 && main.from !== 'weak' && !(band.note?.kind === 'ineffective' && main.from === 'note' && band.weak.length === 1)) add(WEAK, `${band.weak.length} to strengthen`)
  if (band.errors > 0 && main.from !== 'error') add(ERROR, count(band.errors, 'error'))
  return out
}

// The band's one row, as segments that together are at most `columns` cells wide. Empty
// when there is nothing to show: the hook then draws nothing.
export function bandRow(band: CompoundBand | null | undefined, now: number, columns: number): Seg[] {
  return clean(bandSegs(band, now, columns))
}

function bandSegs(band: CompoundBand | null | undefined, now: number, columns: number): Seg[] {
  if (band === null || band === undefined || columns < 12) return []
  const main = mainOf(band, now)
  const phase = trackPhase(band, now)
  const step = band.track !== null && phase !== 'gone' ? band.track.step : undefined
  if (main === undefined && step === undefined) return []
  const faded = (main === undefined || main.phase === 'dim') && (step === undefined || phase === 'dim')
  // The track alone: a call failed and the mod is waiting to see what fixes it.
  const head: Seg[] = main === undefined
    ? [{ text: '◌ ', color: SPINNER_COLOR }, { text: 'compound ', dim: true }, { text: step === 'failed' ? WATCHING : 'learn loop' }]
    : [
        { text: `${main.glyph} `, color: main.color, bold: main.phase === 'flash' },
        { text: 'compound ', dim: true },
        { text: main.label, ...(main.from === 'busy' ? {} : { color: main.color }), bold: main.phase === 'flash' },
      ]
  const name: Seg[] = main !== undefined && main.name !== '' ? [{ text: ' · ', dim: true }, { text: main.name, bold: main.phase === 'flash' }] : []
  let detail: Seg[] = main?.detail === undefined || main.detail === '' ? [] : [{ text: main.name === '' ? ' · ' : '  ', dim: true }, { text: main.detail, dim: true }]
  let marks = main === undefined ? [] : badges(band, main, step === 'owed')
  let track: Seg[] = step === undefined ? [] : [{ text: '   ' }, ...trackSegs(step, false)]
  // Too wide: the track loses its words, then the detail goes, then the marks, then the
  // track, then the name is cut; a list of names keeps as many as fit and counts the rest.
  const total = () => width(head) + width(name) + width(detail) + width(marks) + width(track)
  if (total() > columns && step !== undefined) track = [{ text: '   ' }, ...trackSegs(step, true)]
  if (total() > columns) detail = []
  if (total() > columns) marks = []
  if (total() > columns) track = []
  let row = [...head, ...name, ...detail, ...marks, ...track]
  if (width(row) > columns) {
    const room = columns - width(head) - 3
    const fewer = main?.names === undefined ? '' : listed(main.names, room)
    row = room >= 4 && name[1] !== undefined ? [...head, { text: ' · ', dim: true }, { ...name[1], text: fewer !== '' && [...fewer].length <= room ? fewer : clip(name[1].text, room) }] : head
    if (width(row) > columns) row = [{ text: clip(row.map(s => s.text).join(''), columns), ...(main === undefined ? { dim: true } : { color: main.color }) }]
  }
  return faded ? row.map(s => ({ ...s, dim: true, bold: false })) : row
}

// The last part of a path: a script is named by its file.
export function base(path: string): string {
  return path.replace(/\/+$/, '').split('/').pop() ?? path
}

// Names in a row, as many as `room` cells hold and at least the first, then `+N` for the rest.
export function listed(names: readonly string[], room: number): string {
  const shown: string[] = []
  for (const name of names) {
    const rest = names.length - shown.length - 1
    if (shown.length > 0 && [...shown, name].join(', ').length + (rest > 0 ? ` +${rest}`.length : 0) > room) break
    shown.push(name)
  }
  const rest = names.length - shown.length
  return rest > 0 ? `${shown.join(', ')} +${rest}` : shown.join(', ')
}

// The text of a reuse result: the items found, by name (a script by its file name), and how
// many earlier requests.
export function reuseText(items: readonly string[], earlier: number, room = 56): string {
  const parts: string[] = []
  if (items.length > 0) parts.push(listed(items.map(base), room))
  if (earlier > 0) parts.push(count(earlier, 'earlier request'))
  return parts.join(' · ')
}

// ---- the pane --------------------------------------------------------------------------

function parsed(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined
}

// A string of the CLI's JSON, as it may be shown: see `clean`. A newline stays, for text
// that is laid out over several lines.
function str(value: unknown): string {
  return typeof value === 'string' ? plain(value) : typeof value === 'number' ? String(value) : ''
}

function num(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function list(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record).filter((r): r is Record<string, unknown> => r !== undefined) : []
}

function names(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

// One event of the log as a line of the timeline: what it was about, without its type.
// What is not a name or free text (a reminder, a refusal, a question) is at most
// LABEL_ROOM cells, which the timeline always has.
export function eventText(e: Record<string, unknown>): string {
  const lesson = str(e.lesson)
  switch (str(e.type)) {
    case 'reuse':
      // The items offered, by name; with none, how many earlier requests were.
      return reuseText(names(e.lessons), names(e.lessons).length > 0 ? 0 : names(e.prompts).length, 48) || 'nothing'
    case 'guard':
      // The lesson, and the call it stopped.
      return str(e.text) === '' ? lesson : `${lesson} · ${oneLine(str(e.text), 60)}`
    case 'recall':
      return e.ineffective === true ? `${lesson} (ineffective)` : lesson
    case 'capture':
      return oneLine(str(e.fixed), 120)
    case 'remind':
      return `${count(names(e.captures).length, 'lesson')} owed`
    case 'refuse':
      return str(e.why) === 'debt' ? 'lesson owed' : str(e.why) === 'strengthen' ? 'to strengthen' : 'long turn'
    case 'learn':
      return e.update === true ? `${lesson} (rewritten)` : lesson
    case 'skip':
      return oneLine(str(e.why), 120)
    case 'nudge':
      return `${num(e.calls)} tool calls`
    case 'promote':
      return `${lesson} → ${str(e.to) || 'user'}`
    case 'error':
      return oneLine(`${str(e.where)}: ${str(e.message)}`, 80)
    default:
      return lesson
  }
}

// What a timeline row adds after `eventText` when it has the room, and drops whole when
// it has not: the earlier requests offered beside the items of a reuse.
export function eventTail(e: Record<string, unknown>): string {
  if (str(e.type) !== 'reuse' || names(e.lessons).length === 0) return ''
  return reuseText([], names(e.prompts).length)
}

const COMMAND_MAX = 400

// One open row: its text, and the commands the CLI gave for it, each on one line.
function openRow(text: string, command?: unknown, more?: unknown): CompoundOpen {
  const [first, second] = [oneLine(str(command), COMMAND_MAX), oneLine(str(more), COMMAND_MAX)]
  return { text, ...(first === '' ? {} : { command: first }), ...(second === '' ? {} : { more: second }) }
}

// `compound status --json` and `compound events --json`, as the pane's data. undefined when
// the status is not the object it should be.
export function boardFrom(status: string, events: string, session: string, now: number): CompoundBoard | undefined {
  const s = record(parsed(status))
  const store = record(s?.store)
  if (s === undefined || store === undefined) return undefined
  const health: CompoundCheck[] = list(s.health).map(h => ({ check: str(h.check), status: str(h.status), detail: oneLine(str(h.detail), 160) }))
  const levels: CompoundLevel[] = ['project', 'user', 'general'].map(level => {
    const row = record(store[level]) ?? {}
    return { level, lessons: num(row.lessons), skills: num(row.skills), guards: num(row.guards) }
  })
  const lessons: CompoundLesson[] = list(s.lessons)
    .map(l => ({ name: str(l.name), level: str(l.level), guard: l.guard === true, reuse: num(l.reuse), guards: num(l.guard_hits), recall: num(l.recall), flag: str(l.flag) }))
    .filter(l => l.name !== '')
    .sort((a, b) => b.reuse + b.guards + b.recall - (a.reuse + a.guards + a.recall) || a.name.localeCompare(b.name))
    .slice(0, 12)
  // The judge's verdicts and the call after a refusal are in the log to be measured
  // (`compound report`), not to be read as what happened.
  const rows = (Array.isArray(parsed(events)) ? list(parsed(events)) : list(s.recent)).filter(e => str(e.type) !== 'judge' && str(e.type) !== 'retry')
  const recent: CompoundRecent[] = rows.slice(-20).map(e => {
    const tail = eventTail(e)
    return { at: Math.floor(Date.parse(str(e.ts)) / 1000) || 0, type: str(e.type), text: eventText(e), ...(tail === '' ? {} : { tail }) }
  })
  const open = record(s.open) ?? {}
  const t = record(s.totals)
  const totals: CompoundTotals | undefined = t === undefined ? undefined : { reused: num(t.reused), guarded: num(t.guarded), recalled: num(t.recalled), recorded: num(t.recorded), since: Math.floor(Date.parse(str(t.since)) / 1000) || 0 }
  return {
    session,
    at: now,
    health: health.filter(h => h.status !== 'PASS'),
    checks: health.length,
    ...(totals === undefined ? {} : { totals }),
    levels,
    lessons,
    recent,
    // Each row with the command the CLI gave for it: the text `compound status` prints.
    open: {
      unsettled: list(open.unsettled).map(u => openRow(`${str(u.id)} ${oneLine(str(u.fixed), 50)} (${str(u.age)}${str(u.project) === '' ? '' : `, ${base(str(u.project))}`})`, u.command, u.decline)),
      ineffective: list(open.ineffective).map(i => ({ ...openRow(`${str(i.name)} (recalled ${num(i.recall)} times)`, i.command), ...(str(i.name) === '' ? {} : { lesson: str(i.name) }) })),
      candidates: list(open.candidates).map(c => openRow(`${str(c.lesson)} in ${base(str(c.from))}`, c.command)),
      errors: list(open.errors).map(e => openRow(oneLine(`${str(e.where)}: ${str(e.message)}`, 100))),
      skips: list(open.skips).length,
    },
    problem: '',
  }
}

// A bar of `n` out of `most`, at most `cells` wide. One cell is one use while the largest
// count fits; past that the bars are in proportion, and any use at all shows one cell.
export function bar(n: number, most: number, cells: number): string {
  if (n <= 0 || most <= 0 || cells <= 0) return ''
  const filled = most <= cells ? n : Math.round((n / most) * cells)
  return '▇'.repeat(Math.max(1, Math.min(cells, filled)))
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const

// The local day of `at` (seconds): "3 Oct", with the year when it is not `now`'s (milliseconds).
export function dateText(at: number, now: number): string {
  const then = new Date(at * 1000)
  const day = `${then.getDate()} ${MONTHS[then.getMonth()] ?? ''}`
  return then.getFullYear() === new Date(now).getFullYear() ? day : `${day} ${then.getFullYear()}`
}

// How long ago `at` (seconds) was at `now` (milliseconds), as `compound status` says it:
// 5s, 2m, 3h, then "yesterday" for the calendar day before, then the date. Rows from
// different days are never told apart by a time of day alone.
export function ago(at: number, now: number): string {
  if (at <= 0) return '?'
  const seconds = Math.floor(now / 1000) - at
  if (seconds >= 0 && seconds < 86400) return seconds < 60 ? `${seconds}s` : seconds < 3600 ? `${Math.floor(seconds / 60)}m` : `${Math.floor(seconds / 3600)}h`
  if (seconds >= 0) {
    const then = new Date(at * 1000)
    const today = new Date(now)
    const days = Math.round((new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() - new Date(then.getFullYear(), then.getMonth(), then.getDate()).getTime()) / 86_400_000)
    if (days === 1) return 'yesterday'
  }
  return dateText(at, now)
}

export type Line = Seg[]

function heading(text: string, tail = ''): Line {
  return tail === '' ? [{ text, bold: true }] : [{ text, bold: true }, { text: `  ${tail}`, dim: true }]
}

function fit(line: Line, columns: number): Line {
  const out: Seg[] = []
  let room = columns
  for (const seg of line) {
    if (room <= 0) break
    const text = clip(seg.text, room)
    out.push({ ...seg, text })
    room -= [...text].length
  }
  return out
}

// A fixed label is never cut: its pieces stay whole and a piece the line has no room for
// starts the next line, under `indent`. A piece carries the gap before it, which a new
// line drops.
function flow(pieces: readonly Seg[][], columns: number, indent: string): Line[] {
  const out: Line[] = []
  let line: Seg[] = []
  for (const piece of pieces) {
    if (line.length > 0 && width(line) + width(piece) > columns) {
      out.push(line)
      line = []
    }
    if (line.length === 0 && out.length > 0) {
      const [first, ...rest] = piece
      line = first === undefined ? [] : [{ text: indent }, { ...first, text: first.text.trimStart() }, ...rest]
    } else line = [...line, ...piece]
  }
  if (line.length > 0) out.push(line)
  return out
}

// A sentence as pieces of one word each, the first after `lead`.
function words(text: string, style: Omit<Seg, 'text'> = {}, lead = ''): Seg[][] {
  return text.split(' ').filter(w => w !== '').map((w, i) => [{ ...style, text: i === 0 ? `${lead}${w}` : ` ${w}` }])
}

// Text on as many lines as it takes, each under `indent` and at most `columns` cells wide:
// broken at its spaces, and a word longer than a line broken where the line ends. Nothing
// is cut.
export function wrapped(text: string, columns: number, indent = '', style: Omit<Seg, 'text'> = {}): Line[] {
  const room = Math.max(1, columns - indent.length)
  const rows: string[] = []
  let line = ''
  for (const word of text.split(' ').filter(w => w !== '')) {
    if (line !== '' && [...line].length + 1 + [...word].length <= room) {
      line = `${line} ${word}`
      continue
    }
    if (line !== '') rows.push(line)
    let rest = [...word]
    while (rest.length > room) {
      rows.push(rest.slice(0, room).join(''))
      rest = rest.slice(room)
    }
    line = rest.join('')
  }
  if (line !== '' || rows.length === 0) rows.push(line)
  return rows.map(row => (indent === '' ? [{ ...style, text: row }] : [{ text: indent }, { ...style, text: row }]))
}

// The key of the Button that opens a lesson, and the lesson of such a key.
const OPEN_KEY = 'open:'

export function openKey(name: string): string {
  return `${OPEN_KEY}${name}`
}

export function openedBy(key: string): string | undefined {
  return key.startsWith(OPEN_KEY) ? key.slice(OPEN_KEY.length) : undefined
}

// The first thing to press in a view's lines: where the pane's ring starts.
export function firstKey(lines: readonly Line[]): string | undefined {
  return lines.flatMap(line => line).find(seg => seg.key !== undefined)?.key
}

// What reads the errors: no command settles one, and they leave the pane after seven days.
const READ_ERRORS = 'compound events --type error'
const COMMAND_INDENT = '      '
// From this width an open row also shows the second way to settle it.
const MORE_COLUMNS = 60

const LABEL_ROOM = 16
const BAR_CELLS = 6
const NAME_MIN = 8
// One counter column of the Most used table: the widest legend entry and a cell between.
const LEGEND_CELL = 13

// The levels. With room, a sentence a level: `user  32 lessons (7 guards)  4 skills`: the
// guards are among the lessons, a lesson that carries a pattern. Without, the same numbers
// in columns under the heading, which no pane of 30 columns or more cuts.
function levelLines(levels: CompoundBoard['levels'], columns: number): Line[] {
  const named = Math.max(0, ...levels.map(l => l.level.length))
  const digits = (of: (l: CompoundLevel) => number) => Math.max(1, ...levels.map(l => String(of(l)).length))
  const [lw, gw, sw] = [digits(l => l.lessons), digits(l => l.guards), digits(l => l.skills)]
  const guards = (l: CompoundLevel) => `(${l.guards} ${l.guards === 1 ? 'guard' : 'guards'})`
  const gWide = Math.max(0, ...levels.map(l => guards(l).length))
  const sentences: Line[] = levels.map(l => [
    { text: `  ${l.level.padEnd(named)}  ` },
    { text: String(l.lessons).padStart(lw), bold: l.lessons > 0, ...(l.lessons > 0 ? {} : { dim: true }) },
    { text: ` ${l.lessons === 1 ? 'lesson ' : 'lessons'} `, dim: true },
    { text: guards(l).padEnd(gWide), ...(l.guards > 0 ? { color: NOTES.guard.color } : { dim: true }) },
    { text: '  ' },
    { text: String(l.skills).padStart(sw), ...(l.skills > 0 ? { color: NOTES.skill.color, bold: true } : { dim: true }) },
    { text: ` ${l.skills === 1 ? 'skill' : 'skills'}`, dim: true },
  ])
  if (sentences.every(line => width(line) <= columns)) return [heading('Levels'), ...sentences]
  const heads = [' lessons', ' (guards)', ' skills'] as const
  const cells = [Math.max(heads[0].length, lw + 1), Math.max(heads[1].length, gw + 3), Math.max(heads[2].length, sw + 1)] as const
  // The names are indented under "Levels" and reach into the room before the first count,
  // so the table is as wide as its header: 30 cells.
  const indent = '  '
  const first = Math.max('Levels'.length, indent.length + named + 1 + lw - cells[0])
  const out: Line[] = [[
    { text: 'Levels'.padEnd(first), bold: true },
    ...heads.map((h, i) => ({ text: h.padStart(cells[i] ?? h.length), dim: true })),
  ]]
  for (const l of levels) {
    const name = `${indent}${l.level}`
    out.push([
      { text: name },
      { text: String(l.lessons).padStart(first + cells[0] - name.length), bold: l.lessons > 0, ...(l.lessons > 0 ? {} : { dim: true }) },
      { text: `(${l.guards})`.padStart(cells[1]), ...(l.guards > 0 ? { color: NOTES.guard.color } : { dim: true }) },
      { text: String(l.skills).padStart(cells[2]), ...(l.skills > 0 ? { color: NOTES.skill.color, bold: true } : { dim: true }) },
    ])
  }
  return out
}

// "Compound interest": what the log holds of the mod helping. Counts only: the log holds
// no duration of a failed call or of its fix, so no time and no tokens are claimed saved.
function totalLines(totals: CompoundTotals, now: number, columns: number): Line[] {
  const none = totals.since <= 0
  const out = flow([[{ text: 'Compound interest', bold: true }], ...(none ? [] : [[{ text: `  since ${dateText(totals.since, now)}`, dim: true }]])], columns, '  ')
  if (none) return [...out, [{ text: '  nothing yet', dim: true }]]
  const piece = (look: Look, n: number, what: string): Seg[] => [
    { text: `  ${look.glyph} `, color: look.color },
    { text: String(n), bold: n > 0, ...(n > 0 ? {} : { dim: true }) },
    { text: ` ${what}`, dim: true },
  ]
  return [
    ...out,
    ...flow([
      piece(NOTES.reuse, totals.reused, totals.reused === 1 ? 'reuse offered' : 'reuses offered'),
      piece(NOTES.guard, totals.guarded, totals.guarded === 1 ? 'call stopped by a guard' : 'calls stopped by a guard'),
      piece(NOTES.recall, totals.recalled, totals.recalled === 1 ? 'lesson recalled' : 'lessons recalled'),
      piece(NOTES.recorded, totals.recorded, totals.recorded === 1 ? 'lesson recorded' : 'lessons recorded'),
    ], columns, '  '),
  ]
}

// The pane as lines, each at most `columns` cells wide: the totals, what is open, the
// levels, the lessons most used and the recent events. `events` is how many timeline rows
// there is room for. Only a name or free text (a call, a path, a reason) is ever cut.
export function boardLines(board: CompoundBoard | null | undefined, columns: number, events = 8): Line[] {
  return boardRows(board, columns, events).map(clean)
}

function boardRows(board: CompoundBoard | null | undefined, columns: number, events: number): Line[] {
  if (board === null || board === undefined) return [[{ text: 'Reading the store…', dim: true }]]
  if (board.problem !== '') return [[{ text: `${ERROR.glyph} `, color: ERROR.color }, { text: board.problem }]].map(l => fit(l, columns))
  const out: Line[] = []
  const failed = board.health.filter(h => h.status === 'FAIL')
  const warned = board.health.filter(h => h.status !== 'FAIL')
  out.push(...flow([
    [
      failed.length > 0 ? { text: '✖ ', color: 'error' } : warned.length > 0 ? { text: '▲ ', color: 'warning' } : { text: '✔ ', color: 'success' },
      { text: failed.length > 0 ? `${count(failed.length, 'check')} failed` : warned.length > 0 ? count(warned.length, 'warning') : 'healthy', bold: true },
    ],
    [{ text: `  ${board.checks} checks`, dim: true }],
    // Each check that warned, by name: a name stays whole.
    ...warned.map((h, i) => [{ text: `${i === 0 ? '  ' : ' '}${h.check}${i < warned.length - 1 ? ',' : ''}`, color: 'warning', dim: true }]),
  ], columns, '  '))
  for (const h of failed) out.push([{ text: '  ✖ ', color: 'error' }, { text: `${h.check}: `, bold: true }, { text: h.detail, dim: true }])

  if (board.totals !== undefined) out.push([], ...totalLines(board.totals, board.at, columns))

  // What waits for someone comes before the tables: the pane may show only its top rows.
  const o = board.open
  const waiting = o.unsettled.length + o.ineffective.length + o.candidates.length + o.errors.length
  out.push([], ...flow([[{ text: 'Open', bold: true }], ...(waiting === 0 ? words('nothing waits for anyone', { dim: true }, '  ') : [])], columns, '  '))
  // Under each row, the command that settles it, whole: broken at its spaces where the pane
  // is narrow, never cut. The second way to settle a row is shown where there is room for it.
  // A row that names a lesson opens it.
  const group = (rows: readonly CompoundOpen[], look: Look, what: string, command = '') => {
    if (rows.length === 0) return
    out.push(...flow([[{ text: `  ${look.glyph}`, color: look.color }], ...words(what, { color: look.color, bold: true }, ' ')], columns, '    '))
    for (const row of rows.slice(0, 3)) {
      const named = row.lesson !== undefined && row.lesson !== '' && row.text.startsWith(row.lesson) ? row.lesson : undefined
      out.push(named === undefined
        ? [{ text: `    ${row.text}`, dim: true }]
        : [{ text: '    ' }, { text: named, key: openKey(named) }, { text: row.text.slice(named.length), dim: true }])
      if (row.command !== undefined) out.push(...wrapped(row.command, columns, COMMAND_INDENT))
      if (row.more !== undefined && columns >= MORE_COLUMNS) out.push(...wrapped(`or ${row.more}`, columns, COMMAND_INDENT, { dim: true }))
    }
    if (rows.length > 3) out.push([{ text: `    and ${rows.length - 3} more`, dim: true }])
    if (command !== '') out.push(...wrapped(command, columns, COMMAND_INDENT))
  }
  group(o.unsettled, OWED, count(o.unsettled.length, 'lesson owed', 'lessons owed'))
  group(o.ineffective, WEAK, count(o.ineffective.length, 'ineffective lesson'))
  group(o.candidates, eventLook('candidate'), count(o.candidates.length, 'lesson that could move to the user level', 'lessons that could move to the user level'))
  group(o.errors, ERROR, `${count(o.errors.length, 'error')} in the last 7 days`, READ_ERRORS)
  if (o.skips > 0) out.push([{ text: `  ${NOTES.declined.glyph} `, dim: true }, { text: `${count(o.skips, 'lesson')} declined`, dim: true }])

  out.push([], ...levelLines(board.levels, columns))

  // The legend is the header of the three counter columns: each glyph sits over its counts,
  // the counts are right-aligned under it and every bar starts in the same cell. A pane too
  // narrow for the legend's words keeps the glyphs and shortens the bars.
  const used = board.lessons.filter(l => l.reuse + l.guards + l.recall > 0)
  const shown = used.slice(0, 6)
  const kinds: readonly (readonly [Look, string, (l: CompoundBoard['lessons'][number]) => number])[] = [
    [NOTES.reuse, WORDS.reuse ?? '', l => l.reuse],
    [NOTES.guard, WORDS.guard ?? '', l => l.guards],
    [NOTES.recall, WORDS.recall ?? '', l => l.recall],
  ]
  const most = Math.max(1, ...used.flatMap(l => [l.reuse, l.guards, l.recall]))
  const digits = String(Math.max(0, ...shown.flatMap(l => [l.reuse, l.guards, l.recall]))).length
  // The last column is not padded, so the table is one cell narrower than three columns.
  const roomy = columns >= 2 + NAME_MIN + kinds.length * LEGEND_CELL - 1
  const bars = roomy ? BAR_CELLS : 3
  const cellWide = roomy ? LEGEND_CELL : 2 + digits + 1 + bars
  // A roomy column ends in the gap before the next, which the last column has not.
  const table = kinds.length * cellWide - (roomy ? 1 : 0)
  const named = Math.max(NAME_MIN, Math.min(28, columns - table - 2, Math.max(...shown.map(l => l.name.length), 0)))
  const column = (segs: Seg[], last: boolean): Seg[] => (last ? segs : [...segs, { text: ' '.repeat(Math.max(0, cellWide - width(segs))) }])
  out.push([], [
    { text: 'Most used', bold: true },
    { text: ' '.repeat(named + 2 - 'Most used'.length) },
    ...kinds.flatMap(([look, word], i) => column([{ text: `  ${' '.repeat(digits - 1)}${look.glyph}`, color: look.color }, ...(roomy ? [{ text: ` ${word}`, dim: true }] : [])], i === kinds.length - 1)),
  ])
  if (used.length === 0) out.push(...flow(words('nothing was reused, guarded or recalled yet', { dim: true }, '  '), columns, '  '))
  for (const l of shown) {
    const name = clip(l.name, named)
    out.push([
      { text: '  ' },
      // The name is the row's button: a press opens the lesson.
      { text: name, key: openKey(l.name), ...(l.flag === 'ineffective' ? { color: WEAK.color } : {}) },
      { text: ' '.repeat(named - [...name].length) },
      ...kinds.flatMap(([look, , of], i) => {
        const n = of(l)
        const filled = bar(n, most, bars)
        return column([
          { text: `  ${String(n).padStart(digits)}`, ...(n > 0 ? {} : { dim: true }) },
          ...(filled === '' ? [] : [{ text: ' ' }, { text: filled, color: look.color }]),
        ], i === kinds.length - 1)
      }),
    ])
  }

  // Each row says how long ago, then the word a person reads for the event's type, in
  // columns as wide as the longest of each. A pane too narrow for the words keeps the
  // glyphs, which say the type in the band's own colours.
  out.push([], heading('Recent'))
  if (board.recent.length === 0) out.push([{ text: '  no events yet', dim: true }])
  const recent = board.recent.slice(-Math.max(1, events)).reverse().map(e => ({ ...e, when: ago(e.at, board.at), word: eventWord(e.type) }))
  const aged = Math.max(0, ...recent.map(e => e.when.length))
  const typed = Math.max(0, ...recent.map(e => e.word.length))
  const worded = columns - (2 + aged + 1 + 2 + typed + 1) >= LABEL_ROOM
  for (const e of recent) {
    const look = eventLook(e.type)
    const row: Seg[] = [
      { text: `  ${e.when.padStart(aged)} `, dim: true },
      { text: `${look.glyph} `, color: look.color },
      ...(e.text === '' ? [{ text: e.word, color: look.color }] : worded ? [{ text: `${e.word.padEnd(typed)} `, color: look.color }] : []),
      { text: e.text },
    ]
    const tail: Seg[] = e.tail === undefined ? [] : [{ text: ` · ${e.tail}`, dim: true }]
    out.push(width(row) + width(tail) <= columns ? [...row, ...tail] : row)
  }
  return out.map(l => fit(l, columns))
}

// ---- the pane's views: the keys, every lesson, one lesson --------------------------------

// Why the CLI could not say, on as many lines as it takes.
function problemLines(problem: string, columns: number): Line[] {
  return wrapped(problem, columns, '  ').map((line, i) => (i === 0 ? [{ text: `${ERROR.glyph} `, color: ERROR.color }, ...line.slice(1)] : line))
}

type Strung = { segs: Seg[]; gap: string }

// Pieces in a row, each after its gap, on as many lines as it takes: a piece is never
// broken and a line never starts with a gap.
function strung(pieces: readonly Strung[], columns: number): Line[] {
  const out: Line[] = []
  let line: Seg[] = []
  for (const piece of pieces) {
    const gap: Seg[] = line.length === 0 ? [] : [{ text: piece.gap, dim: true }]
    if (line.length > 0 && width(line) + width(gap) + width(piece.segs) > columns) {
      out.push(line)
      line = [...piece.segs]
    } else line = [...line, ...gap, ...piece.segs]
  }
  if (line.length > 0) out.push(line)
  return out
}

// What the key row depends on: the view, whether the pane holds the keyboard, whether its
// tree is taller than its window, whether the view has rows to press, and whether the
// surface is a terminal (the keys named here are a terminal's).
export type PaneKeys = { view: CompoundPaneView; focused: boolean; taller: boolean; rows: boolean; terminal: boolean }

// The key row, the first of every view: what the keyboard does here, then the view's
// Buttons, each drawn with its hotkey. Keys reach a pane only while it holds the keyboard,
// which the person gives it (ctrl+x tab, or a click) and takes back (Esc): until then the
// row says how. While the tree fits its window the arrows walk the rows; a taller tree is
// scrolled by them, and Tab walks the rows. Too wide for one line, the row shortens its
// words and then wraps; a key is never dropped.
export function keyLines(k: PaneKeys, columns: number): Line[] {
  const build = (short: boolean): Strung[] => {
    const hints = !k.terminal
      ? []
      : !k.focused
        ? [short ? 'ctrl+x tab: keys' : 'ctrl+x tab for keys']
        : [...(k.taller ? ['↑↓ scroll'] : []), ...(k.rows ? [k.taller ? 'tab select' : '↑↓ select', 'enter open'] : []), short ? 'esc prompt' : 'esc to the prompt']
    const keys: (readonly [string, string, string])[] = [k.view === 'board' ? ['all', 'a', short ? 'all' : 'all lessons'] : ['back', 'b', 'back'], ['refresh', 'r', 'refresh'], ['close', 'x', 'close']]
    return [
      ...hints.map(hint => ({ segs: [{ text: hint, dim: true }], gap: ' · ' })),
      ...keys.map(([key, hotkey, label]) => ({ segs: [{ text: label, key, hotkey }], gap: '  ' })),
    ]
  }
  const long = strung(build(false), columns)
  return long.length <= 1 ? long : strung(build(true), columns)
}

// `compound list --json`, as the rows of the all-lessons view: every lesson and skill, in
// the CLI's order. undefined when it is not the list it should be.
export function itemsFrom(listing: string): CompoundItem[] | undefined {
  const rows = parsed(listing)
  if (!Array.isArray(rows)) return undefined
  return list(rows)
    .filter(r => str(r.name) !== '' && (str(r.kind) === 'lesson' || str(r.kind) === 'skill'))
    .map(r => {
      const counts = record(r.counts) ?? {}
      return {
        name: str(r.name),
        level: str(r.level),
        kind: str(r.kind) === 'lesson' && names(r.match).length > 0 ? 'guard' : str(r.kind),
        reuse: num(counts.reuse),
        guards: num(counts.guard),
        recall: num(counts.recall),
        flag: r.ineffective === true ? 'ineffective' : '',
        description: oneLine(str(r.description), 200),
      }
    })
}

const LEVELS: readonly string[] = ['project', 'user', 'general']
const KIND_CELL = 6
const ALL_NAME_MAX = 32
const DESCRIPTION_MIN = 20

// How many lessons (and guards among them) and how many skills, as the Levels rows say it.
function tallied(items: readonly CompoundItem[]): [string, string] {
  const skills = items.filter(i => i.kind === 'skill').length
  return [`${count(items.length - skills, 'lesson')} (${count(items.filter(i => i.kind === 'guard').length, 'guard')})`, count(skills, 'skill')]
}

// Every lesson and skill, by level, each row a name to press: its kind, its three counters
// and when it applies. A pane too narrow drops the description, then the counters; a name
// and a description are the only things ever cut.
export function allLines(items: readonly CompoundItem[] | null | undefined, problem: string, columns: number): Line[] {
  const failed = problem === '' ? [] : problemLines(problem, columns)
  if (items === null || items === undefined) return failed.length > 0 ? failed : [[{ text: 'Reading the store…', dim: true }]]
  const kinds: readonly (readonly [Look, string, (i: CompoundItem) => number])[] = [
    [NOTES.reuse, WORDS.reuse ?? '', i => i.reuse],
    [NOTES.guard, WORDS.guard ?? '', i => i.guards],
    [NOTES.recall, WORDS.recall ?? '', i => i.recall],
  ]
  const longest = Math.max(0, ...items.map(i => [...i.name].length))
  const digits = String(Math.max(0, ...items.flatMap(i => [i.reuse, i.guards, i.recall]))).length
  const counters = kinds.length * (2 + digits) + (kinds.length - 1) * 2
  const wanted = Math.max(NAME_MIN, Math.min(ALL_NAME_MAX, longest))
  const fixed = 2 + 2 + KIND_CELL + 2 + counters
  // The counters are drawn when they leave a name most of its room.
  const counted = columns - fixed >= Math.min(wanted, 24)
  const named = Math.max(NAME_MIN, Math.min(wanted, counted ? columns - fixed : columns - 2 - 2 - KIND_CELL))
  const described = counted ? columns - fixed - named - 2 : 0
  const [lessons, skills] = tallied(items)
  const out: Line[] = [...failed, ...flow([
    [{ text: 'All lessons', bold: true }],
    [{ text: `  ${lessons}`, dim: true }],
    [{ text: `  ${skills}`, dim: true }],
    ...(counted ? kinds.map(([look, word]): Seg[] => [{ text: `  ${look.glyph}`, color: look.color }, { text: ` ${word}`, dim: true }]) : []),
  ], columns, '  ')]
  if (items.length === 0) return [...out, [{ text: '  nothing recorded yet', dim: true }]]
  for (const level of [...LEVELS, ...items.map(i => i.level).filter((l, n, all) => !LEVELS.includes(l) && all.indexOf(l) === n)]) {
    const mine = items.filter(i => i.level === level)
    const [mineLessons, mineSkills] = tallied(mine)
    out.push([], ...flow(mine.length === 0
      ? [[{ text: level, bold: true }], [{ text: '  nothing recorded', dim: true }]]
      : [[{ text: level, bold: true }], [{ text: `  ${mineLessons}`, dim: true }], [{ text: `  ${mineSkills}`, dim: true }]], columns, '  '))
    for (const item of mine) {
      const name = clip(item.name, named)
      const row: Seg[] = [
        { text: '  ' },
        { text: name, key: openKey(item.name), ...(item.flag === 'ineffective' ? { color: WEAK.color } : {}) },
        { text: ' '.repeat(named - [...name].length + 2) },
        { text: item.kind, ...(item.kind === 'guard' ? { color: NOTES.guard.color } : item.kind === 'skill' ? { color: NOTES.skill.color } : { dim: true }) },
      ]
      if (counted) {
        row.push({ text: ' '.repeat(Math.max(0, KIND_CELL - item.kind.length)) })
        for (const [look, , of] of kinds) {
          const n = of(item)
          row.push({ text: '  ' }, { text: `${look.glyph} ${String(n).padStart(digits)}`, ...(n > 0 ? { color: look.color } : { dim: true }) })
        }
        if (described >= DESCRIPTION_MIN && item.description !== '') row.push({ text: '  ' }, { text: clip(item.description, described), dim: true })
      }
      out.push(row)
    }
  }
  return out.map(l => fit(l, columns))
}

// How much of a lesson's text the pane keeps, and how many of its lines it draws.
const BODY_MAX = 60000
const BODY_LINES = 300

export function loadingDetail(name: string): CompoundDetail {
  return { name, state: 'loading', problem: '', at: 0, level: '', kind: '', match: [], description: '', body: '', reuse: 0, guards: 0, recall: 0, flag: '', last: null, path: '', files: [] }
}

export function failedDetail(name: string, problem: string, at: number): CompoundDetail {
  return { ...loadingDetail(name), state: 'failed', problem: oneLine(problem, 300), at }
}

// `compound show <name> --json`, as the lesson view's data, read at `now` (milliseconds).
// undefined when it is not the object it should be.
export function detailFrom(shown: string, now: number): CompoundDetail | undefined {
  const d = record(parsed(shown))
  if (d === undefined || str(d.name) === '') return undefined
  const counts = record(d.counts) ?? {}
  const match = names(d.match)
  const last = record(d.last)
  const fired = last === undefined ? 0 : Math.floor(Date.parse(str(last.ts)) / 1000) || 0
  return {
    name: str(d.name),
    state: 'ready',
    problem: '',
    at: now,
    level: str(d.level),
    kind: str(d.kind) === 'lesson' && match.length > 0 ? 'guard' : str(d.kind),
    match,
    description: oneLine(str(d.description), 600),
    body: (typeof d.body === 'string' ? d.body : '').slice(0, BODY_MAX),
    reuse: num(counts.reuse),
    guards: num(counts.guard),
    recall: num(counts.recall),
    flag: d.ineffective === true ? 'ineffective' : '',
    last: last === undefined || fired <= 0 ? null : { at: fired, type: str(last.type) },
    path: oneLine(str(d.path), 400),
    files: names(d.files),
  }
}

// A line of a lesson as the pane may draw it: a tab is two cells, and no control character
// reaches the terminal.
function cleanLine(line: string): string {
  return drawn(line.replace(/\t/g, '  ').replace(/[\u0000-\u001f\u007f-\u009f]/g, ''))
}

// One lesson: its name, level and kind, its counters and when it last fired, its guard
// patterns, where it is, when it applies, and its text. Nothing is cut: a long line is
// wrapped under its own indent, and a text longer than BODY_LINES lines ends in a line
// that says how many more there are and how to read them.
export function detailLines(detail: CompoundDetail | null | undefined, columns: number): Line[] {
  if (detail === null || detail === undefined) return [[{ text: 'Reading the lesson…', dim: true }]]
  const title = wrapped(detail.name, columns, '', { bold: true, ...(detail.flag === 'ineffective' ? { color: WEAK.color } : {}) })
  if (detail.state === 'loading') return [...title, [{ text: 'Reading the lesson…', dim: true }]]
  if (detail.state === 'failed') return [...title, ...problemLines(detail.problem, columns)]
  const kind: Seg = { text: detail.kind, ...(detail.kind === 'guard' ? { color: NOTES.guard.color } : detail.kind === 'skill' ? { color: NOTES.skill.color } : {}) }
  const counter = (look: Look, n: number, word: string): Strung => ({
    segs: [{ text: `${look.glyph} `, color: look.color }, { text: String(n), bold: n > 0, ...(n > 0 ? {} : { dim: true }) }, { text: ` ${word}`, dim: true }],
    gap: '  ',
  })
  const when = detail.last === null ? '' : ago(detail.last.at, detail.at)
  const out: Line[] = [
    ...title,
    ...strung([
      { segs: [{ text: detail.level }], gap: ' · ' },
      { segs: [kind], gap: ' · ' },
      ...(detail.flag === '' ? [] : [{ segs: [{ text: detail.flag, color: WEAK.color }], gap: ' · ' }]),
    ].filter(piece => piece.segs[0]?.text !== ''), columns),
    ...strung([counter(NOTES.reuse, detail.reuse, WORDS.reuse ?? ''), counter(NOTES.guard, detail.guards, WORDS.guard ?? ''), counter(NOTES.recall, detail.recall, WORDS.recall ?? '')], columns),
    ...wrapped(detail.last === null ? 'never fired' : `last fired ${/^\d+[smh]$/.test(when) ? `${when} ago` : when} (${eventWord(detail.last.type)})`, columns, '', { dim: true }),
  ]
  if (detail.match.length > 0) {
    out.push([{ text: detail.match.length === 1 ? 'guard pattern' : 'guard patterns', dim: true }])
    for (const pattern of detail.match) out.push(...wrapped(cleanLine(pattern), columns, '  ', { color: NOTES.guard.color }))
  }
  if (detail.files.length > 0) out.push(...wrapped(`attached: ${detail.files.map(cleanLine).join(', ')}`, columns, '', { dim: true }))
  if (detail.path !== '') out.push(...wrapped(detail.path, columns, '', { dim: true }))
  if (detail.description !== '') out.push([], ...wrapped(detail.description, columns))
  out.push([])
  const lines = detail.body.replace(/\r\n?/g, '\n').split('\n')
  while (lines.length > 0 && (lines[lines.length - 1] ?? '').trim() === '') lines.pop()
  if (lines.length === 0) out.push([{ text: '(no text)', dim: true }])
  for (const raw of lines.slice(0, BODY_LINES)) {
    const line = cleanLine(raw).trimEnd()
    if (line === '') out.push([])
    else if ([...line].length <= columns) out.push([{ text: line }])
    else {
      const indent = (/^ */.exec(line)?.[0] ?? '').slice(0, Math.floor(columns / 3))
      out.push(...wrapped(line.trimStart(), columns, indent))
    }
  }
  if (lines.length > BODY_LINES) out.push(...wrapped(`… ${lines.length - BODY_LINES} more lines: compound show ${detail.name}`, columns, '', { dim: true }))
  return out
}

// ---- which view the pane shows -----------------------------------------------------------

export function emptyPane(session: string): CompoundPane {
  return { session, view: 'board', back: 'board', detail: null, items: null, itemsProblem: '' }
}

// The pane's view as this session's: another session's starts at the dashboard.
export function forPane(pane: CompoundPane | null | undefined, session: string): CompoundPane {
  return pane === null || pane === undefined || pane.session !== session ? emptyPane(session) : pane
}

// A lesson was pressed: its view opens over the one it was pressed in, and says it is reading.
export function paneOpening(pane: CompoundPane, name: string): CompoundPane {
  return { ...pane, view: 'lesson', back: pane.view === 'lesson' ? pane.back : pane.view, detail: loadingDetail(name) }
}

// The CLI answered for a lesson: drawn only while that lesson is still the one shown.
export function paneRead(pane: CompoundPane, name: string, detail: CompoundDetail): CompoundPane {
  return pane.view === 'lesson' && pane.detail?.name === name ? { ...pane, detail } : pane
}

export function paneAll(pane: CompoundPane): CompoundPane {
  return { ...pane, view: 'all' }
}

// Back: from a lesson to the view it was pressed in, from the list to the dashboard.
export function paneBack(pane: CompoundPane): CompoundPane {
  return { ...pane, view: pane.view === 'lesson' ? pane.back : 'board' }
}

// The list was read, or could not be: the rows it had stay, beside why.
export function paneItems(pane: CompoundPane, items: CompoundItem[] | undefined, problem: string): CompoundPane {
  return items === undefined ? { ...pane, itemsProblem: oneLine(problem, 300) } : { ...pane, items, itemsProblem: '' }
}
