import type {
  CompoundBand, CompoundBoard, CompoundBusyKind, CompoundCheck, CompoundLesson, CompoundLevel, CompoundNoteKind, CompoundRecent, CompoundStep,
} from '../types'
import { oneLine } from './safe'

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
  unsettled: { glyph: '●', color: 'warning', label: 'unsettled from earlier sessions' },
  recorded: { glyph: '✔', color: 'success', label: 'lesson recorded' },
  rewritten: { glyph: '✔', color: 'success', label: 'lesson rewritten' },
  declined: { glyph: '○', color: 'inactive', label: 'lesson declined' },
  moved: { glyph: '⇡', color: 'suggestion', label: 'lesson moved to the user level' },
  proposed: { glyph: '⇡', color: 'suggestion', label: 'lesson proposed to the general pool' },
  skill: { glyph: '✦', color: 'suggestion', label: 'lesson made a skill' },
  removed: { glyph: '−', color: 'inactive', label: 'removed' },
  ineffective: { glyph: '▲', color: 'warning', label: 'lesson ineffective' },
  nudge: { glyph: '?', color: 'suggestion', label: 'asked whether anything was learned' },
}

// What the band says while a failed call is held and no fix was seen yet.
export const WATCHING = 'watching for the fix'

// The states that stay until they are settled.
export const OWED: Look = { glyph: '●', color: 'warning', label: 'lesson owed' }
export const WEAK: Look = { glyph: '▲', color: 'warning', label: 'strengthening owed' }
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

export function noted(band: CompoundBand, kind: CompoundNoteKind, text: string, now: number): CompoundBand {
  return { ...band, note: { kind, text: oneLine(text, 80), at: now } }
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

export function captured(band: CompoundBand, now: number): CompoundBand {
  return { ...band, owed: band.owed + 1, track: { step: 'owed', at: now } }
}

// An event that settled something, as the band shows it: the result it flashes and where
// the track ends. The counts it leaves are a first guess; `synced` then sets them to what
// the CLI says is still owed.
export function settledBy(band: CompoundBand, event: Record<string, unknown> & { type: string }, now: number): CompoundBand {
  const name = typeof event.lesson === 'string' ? event.lesson : ''
  const closes = band.owed > 0 || band.track !== null
  if (event.type === 'skip') {
    return { ...noted(band, 'declined', '', now), owed: 0, weak: [], track: closes ? { step: 'declined', at: now } : null }
  }
  if (event.type === 'learn') {
    if (event.update === true && band.weak.includes(name)) return { ...noted(band, 'rewritten', name, now), weak: band.weak.filter(w => w !== name) }
    return { ...noted(band, event.update === true ? 'rewritten' : 'recorded', name, now), owed: 0, track: closes ? { step: 'recorded', at: now } : null }
  }
  if (event.type === 'promote' && event.auto !== true) return noted(band, event.to === 'general' ? 'proposed' : 'moved', name, now)
  if (event.type === 'skill') return noted(band, 'skill', name, now)
  if (event.type === 'rm') return { ...noted(band, 'removed', name, now), weak: band.weak.filter(w => w !== name) }
  return band
}

export function weakened(band: CompoundBand, name: string, now: number): CompoundBand {
  return { ...noted(band, 'ineffective', name, now), weak: band.weak.includes(name) ? band.weak : [...band.weak, name] }
}

// What the CLI said the session owes: the counts are the log's, not the band's guess. A
// band that already says so is answered as it is, so nothing is redrawn for it.
export function synced(band: CompoundBand, owed: number, weak: readonly string[], now: number): CompoundBand {
  let track = band.track
  if (owed > 0 && track?.step !== 'owed') track = { step: 'owed', at: now }
  if (owed === 0 && track?.step === 'owed') track = null
  if (band.owed === owed && track === band.track && band.weak.length === weak.length && band.weak.every((w, i) => w === weak[i])) return band
  return { ...band, owed, weak: [...weak], track }
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

export type Seg = { text: string; color?: string; dim?: boolean; bold?: boolean; inverse?: boolean }

export function width(segs: readonly Seg[]): number {
  return segs.reduce((n, s) => n + [...s.text].length, 0)
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

type Main = { glyph: string; color: string; label: string; name: string; phase: Phase; from: 'busy' | 'note' | 'error' | 'owed' | 'weak' }

function mainOf(band: CompoundBand, now: number): Main | undefined {
  const busy = liveBusy(band, now)
  const last = busy[busy.length - 1]
  if (last !== undefined) return { glyph: frameAt(now), color: SPINNER_COLOR, label: BUSY[last.kind], name: '', phase: 'fresh', from: 'busy' }
  const phase = notePhase(band, now)
  if (band.note !== null && phase !== 'gone') {
    const look = NOTES[band.note.kind]
    return { ...look, name: band.note.text, phase, from: 'note' }
  }
  if (band.errors > 0) return { ...ERROR, label: `${count(band.errors, 'compound error')}`, name: 'Claude is told at the next prompt', phase: 'fresh', from: 'error' }
  if (band.owed > 0) return { ...OWED, label: band.owed === 1 ? OWED.label : `${band.owed} lessons owed`, name: '', phase: 'fresh', from: 'owed' }
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
  let marks = main === undefined ? [] : badges(band, main, step === 'owed')
  let track: Seg[] = step === undefined ? [] : [{ text: '   ' }, ...trackSegs(step, false)]
  // Too wide: the track loses its words, then the marks go, then the track, then the name is cut.
  const total = () => width(head) + width(name) + width(marks) + width(track)
  if (total() > columns && step !== undefined) track = [{ text: '   ' }, ...trackSegs(step, true)]
  if (total() > columns) marks = []
  if (total() > columns) track = []
  let row = [...head, ...name, ...marks, ...track]
  if (width(row) > columns) {
    const room = columns - width(head) - 3
    row = room >= 4 && name[1] !== undefined ? [...head, { text: ' · ', dim: true }, { ...name[1], text: clip(name[1].text, room) }] : head
    if (width(row) > columns) row = [{ text: clip(row.map(s => s.text).join(''), columns), ...(main === undefined ? { dim: true } : { color: main.color }) }]
  }
  return faded ? row.map(s => ({ ...s, dim: true, bold: false })) : row
}

// The text of a reuse result: how many recorded items and earlier requests were found.
export function reuseText(items: number, earlier: number): string {
  const parts: string[] = []
  if (items > 0) parts.push(count(items, 'lesson or skill', 'lessons and skills'))
  if (earlier > 0) parts.push(count(earlier, 'earlier request'))
  return parts.join(', ')
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

function str(value: unknown): string {
  return typeof value === 'string' ? value : typeof value === 'number' ? String(value) : ''
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

function base(path: string): string {
  return path.replace(/\/+$/, '').split('/').pop() ?? path
}

// One event of the log as a line of the timeline: what it was about, without its type.
export function eventText(e: Record<string, unknown>): string {
  const lesson = str(e.lesson)
  switch (str(e.type)) {
    case 'reuse':
      return reuseText(names(e.lessons).length, names(e.prompts).length) || 'nothing'
    case 'guard':
    case 'recall':
      return e.ineffective === true ? `${lesson} (ineffective)` : lesson
    case 'capture':
      return oneLine(str(e.fixed), 60)
    case 'remind':
      return count(names(e.captures).length, 'unsettled capture')
    case 'refuse':
      return str(e.why) === 'debt' ? 'a lesson is owed' : str(e.why) === 'strengthen' ? 'a lesson needs strengthening' : 'a long turn'
    case 'learn':
      return e.update === true ? `${lesson} (rewritten)` : lesson
    case 'skip':
      return oneLine(str(e.why), 60)
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
  const rows = Array.isArray(parsed(events)) ? list(parsed(events)) : list(s.recent)
  const recent: CompoundRecent[] = rows.slice(-20).map(e => ({ at: Math.floor(Date.parse(str(e.ts)) / 1000) || 0, type: str(e.type), text: eventText(e) }))
  const open = record(s.open) ?? {}
  return {
    session,
    at: now,
    health: health.filter(h => h.status !== 'PASS'),
    checks: health.length,
    levels,
    lessons,
    recent,
    open: {
      unsettled: list(open.unsettled).map(u => `${str(u.id)} ${oneLine(str(u.fixed), 50)} (${str(u.age)}${str(u.project) === '' ? '' : `, ${base(str(u.project))}`})`),
      ineffective: list(open.ineffective).map(i => `${str(i.name)} (recalled ${num(i.recall)} times)`),
      candidates: list(open.candidates).map(c => `${str(c.lesson)} in ${base(str(c.from))}`),
      errors: list(open.errors).map(e => oneLine(`${str(e.where)}: ${str(e.message)}`, 100)),
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

export function clock(at: number): string {
  if (at <= 0) return '--:--'
  const d = new Date(at * 1000)
  const two = (n: number) => String(n).padStart(2, '0')
  return `${two(d.getHours())}:${two(d.getMinutes())}`
}

export type Line = Seg[]

function heading(text: string, tail = ''): Line {
  return tail === '' ? [{ text, bold: true }] : [{ text, bold: true }, { text: `  ${tail}`, dim: true }]
}

function legend(look: Look, text: string): Seg[] {
  return [{ text: `  ${look.glyph}`, color: look.color }, { text: ` ${text}`, dim: true }]
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

const BAR_CELLS = 6
const NAME_MIN = 8
// One counter column of the Most used table: the widest legend entry and a cell between.
const LEGEND_CELL = 13

// The pane as lines, each at most `columns` cells wide: the levels, the lessons most used,
// the recent events and what is open. `events` is how many timeline rows there is room for.
export function boardLines(board: CompoundBoard | null | undefined, columns: number, events = 8): Line[] {
  if (board === null || board === undefined) return [[{ text: 'Reading the store…', dim: true }]]
  if (board.problem !== '') return [[{ text: `${ERROR.glyph} `, color: ERROR.color }, { text: board.problem }]].map(l => fit(l, columns))
  const out: Line[] = []
  const failed = board.health.filter(h => h.status === 'FAIL')
  const warned = board.health.filter(h => h.status !== 'FAIL')
  out.push([
    failed.length > 0 ? { text: '✖ ', color: 'error' } : warned.length > 0 ? { text: '▲ ', color: 'warning' } : { text: '✔ ', color: 'success' },
    { text: failed.length > 0 ? `${count(failed.length, 'check')} failed` : warned.length > 0 ? count(warned.length, 'warning') : 'healthy', bold: true },
    { text: `  ${board.checks} checks`, dim: true },
    ...(warned.length > 0 ? [{ text: `  ${warned.map(h => h.check).join(', ')}`, color: 'warning', dim: true }] : []),
  ])
  for (const h of failed) out.push([{ text: '  ✖ ', color: 'error' }, { text: `${h.check}: `, bold: true }, { text: h.detail, dim: true }])

  // What waits for someone comes first: the pane may show only its top rows.
  const o = board.open
  const waiting = o.unsettled.length + o.ineffective.length + o.candidates.length + o.errors.length
  out.push([], heading('Open', waiting === 0 ? 'nothing waits for anyone' : ''))
  const group = (rows: readonly string[], look: Look, what: string) => {
    if (rows.length === 0) return
    out.push([{ text: `  ${look.glyph} `, color: look.color }, { text: what, color: look.color, bold: true }])
    for (const row of rows.slice(0, 3)) out.push([{ text: `    ${row}`, dim: true }])
    if (rows.length > 3) out.push([{ text: `    and ${rows.length - 3} more`, dim: true }])
  }
  group(o.unsettled, OWED, count(o.unsettled.length, 'lesson owed', 'lessons owed'))
  group(o.ineffective, WEAK, count(o.ineffective.length, 'ineffective lesson'))
  group(o.candidates, eventLook('candidate'), count(o.candidates.length, 'lesson that could move to the user level', 'lessons that could move to the user level'))
  group(o.errors, ERROR, `${count(o.errors.length, 'error')} in the last 7 days`)
  if (o.skips > 0) out.push([{ text: `  ${NOTES.declined.glyph} `, dim: true }, { text: `${count(o.skips, 'lesson')} declined`, dim: true }])

  out.push([], heading('Levels'))
  const wide = Math.max(...board.levels.map(l => l.level.length))
  for (const l of board.levels) {
    out.push([
      { text: `  ${l.level.padEnd(wide)}  ` },
      { text: String(l.lessons).padStart(3), bold: l.lessons > 0, ...(l.lessons > 0 ? {} : { dim: true }) },
      { text: ` ${l.lessons === 1 ? 'lesson ' : 'lessons'}  `, dim: true },
      { text: String(l.guards).padStart(2), ...(l.guards > 0 ? { color: NOTES.guard.color, bold: true } : { dim: true }) },
      { text: ` ${l.guards === 1 ? 'guard ' : 'guards'}  `, dim: true },
      { text: String(l.skills).padStart(2), ...(l.skills > 0 ? { color: NOTES.skill.color, bold: true } : { dim: true }) },
      { text: ` ${l.skills === 1 ? 'skill' : 'skills'}`, dim: true },
    ])
  }

  // The legend is the header of the three counter columns: each glyph sits over its counts,
  // the counts are right-aligned under it and every bar starts in the same cell. A pane too
  // narrow for the legend's words keeps the glyphs and shortens the bars.
  const used = board.lessons.filter(l => l.reuse + l.guards + l.recall > 0)
  const shown = used.slice(0, 6)
  const kinds: readonly (readonly [Look, string, (l: CompoundBoard['lessons'][number]) => number])[] = [
    [NOTES.reuse, 'reused', l => l.reuse],
    [NOTES.guard, 'guarded', l => l.guards],
    [NOTES.recall, 'recalled', l => l.recall],
  ]
  const most = Math.max(1, ...used.flatMap(l => [l.reuse, l.guards, l.recall]))
  const digits = String(Math.max(0, ...shown.flatMap(l => [l.reuse, l.guards, l.recall]))).length
  // The last column is not padded, so the table is one cell narrower than three columns.
  const roomy = columns >= 2 + NAME_MIN + kinds.length * LEGEND_CELL - 1
  const bars = roomy ? BAR_CELLS : 3
  const cellWide = roomy ? LEGEND_CELL : 2 + digits + 1 + bars
  const named = Math.max(NAME_MIN, Math.min(28, columns - (kinds.length * cellWide - 1) - 2, Math.max(...shown.map(l => l.name.length), 0)))
  const column = (segs: Seg[], last: boolean): Seg[] => (last ? segs : [...segs, { text: ' '.repeat(Math.max(0, cellWide - width(segs))) }])
  out.push([], [
    { text: 'Most used', bold: true },
    { text: ' '.repeat(named + 2 - 'Most used'.length) },
    ...kinds.flatMap(([look, word], i) => column([{ text: `  ${' '.repeat(digits - 1)}${look.glyph}`, color: look.color }, ...(roomy ? [{ text: ` ${word}`, dim: true }] : [])], i === kinds.length - 1)),
  ])
  if (used.length === 0) out.push([{ text: '  nothing was reused, guarded or recalled yet', dim: true }])
  for (const l of shown) {
    out.push([
      { text: `  ${clip(l.name, named).padEnd(named)}`, ...(l.flag === 'ineffective' ? { color: WEAK.color } : {}) },
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

  out.push([], heading('Recent'))
  if (board.recent.length === 0) out.push([{ text: '  no events yet', dim: true }])
  const recent = board.recent.slice(-Math.max(1, events)).reverse()
  const typed = Math.max(8, ...recent.map(e => e.type.length))
  for (const e of recent) {
    const look = eventLook(e.type)
    out.push([{ text: `  ${clock(e.at)} `, dim: true }, { text: `${look.glyph} `, color: look.color }, { text: e.text === '' ? e.type : e.type.padEnd(typed), color: look.color }, { text: e.text === '' ? '' : ` ${e.text}` }])
  }
  return out.map(l => fit(l, columns))
}
