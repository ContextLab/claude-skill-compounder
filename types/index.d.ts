// The values compound keeps in the session (`$.state`), which its band and its pane draw
// from. Plain JSON. ./hooks/view.ts holds every function that reads or changes them.

// A check that is in flight: the spinner's label follows its kind.
export type CompoundBusyKind = 'reuse' | 'guard' | 'recall' | 'fix' | 'record'
export type CompoundBusy = { id: string; kind: CompoundBusyKind; since: number }

// What a moment did. The band shows the newest one, and it fades.
export type CompoundNoteKind =
  | 'reuse'
  | 'guard'
  | 'recall'
  | 'unsettled'
  | 'recorded'
  | 'rewritten'
  | 'declined'
  | 'moved'
  | 'proposed'
  | 'skill'
  | 'removed'
  | 'ineffective'
  | 'nudge'
  | 'used'
  | 'repeat'
  | 'ready'
  | 'idle'
// `text` names the thing (the lesson, the items found); `detail` is what else there is room
// for (the call a guard stopped), and is the first to go in a narrow band. `names` are the
// items `text` lists, so a band too narrow for the text lists as many as fit and counts the
// rest.
export type CompoundNote = { kind: CompoundNoteKind; text: string; at: number; detail?: string; names?: string[] }

// Where the learn loop stands: a call failed, a later call fixed it, a lesson is owed, and
// it was recorded or declined.
export type CompoundStep = 'failed' | 'fixed' | 'owed' | 'recorded' | 'declined'
export type CompoundTrack = { step: CompoundStep; at: number }

export type CompoundBand = {
  session: string
  busy: CompoundBusy[]
  note: CompoundNote | null
  // Lessons this session owes, and the lessons it owes a strengthening for.
  owed: number
  // What the newest of them is for: the call that worked, on one line.
  owedText?: string
  weak: string[]
  // Failures of the mod itself that Claude was not yet told about.
  errors: number
  track: CompoundTrack | null
  // Since when the mod holds a failed call whose fix it is watching for, in milliseconds;
  // absent while it holds none. The row shows it for as long as it is there.
  held?: number
  // The greeting a session gets once: the store's counts, known once the inventory was
  // read at a prompt, and how much of the greeting was said.
  counts?: { lessons: number; guards: number }
  greeted?: 'bare' | 'full'
}

export type CompoundLevel = { level: string; lessons: number; skills: number; guards: number }
export type CompoundLesson = { name: string; level: string; guard: boolean; reuse: number; guards: number; recall: number; use: number; flag: string }
// One row of what is open: what it is, the command that settles it (and a second one, where
// there is a second way), and the lesson a press of the row opens.
export type CompoundOpen = { text: string; command?: string; more?: string; lesson?: string }
// `text` is what the event was about; `tail` is what the row adds when it has the room.
export type CompoundRecent = { at: number; type: string; text: string; tail?: string }
export type CompoundCheck = { check: string; status: string; detail: string }
// What the log holds of the mod helping, one per event, and the time of its oldest event
// in seconds (0 when it holds none).
export type CompoundTotals = { reused: number; guarded: number; recalled: number; used: number; recorded: number; since: number }

// What the pane shows, as `compound status --json` and `compound events --json` gave it.
export type CompoundBoard = {
  session: string
  at: number
  // The health checks that did not pass.
  health: CompoundCheck[]
  checks: number
  totals?: CompoundTotals
  levels: CompoundLevel[]
  lessons: CompoundLesson[]
  recent: CompoundRecent[]
  open: { unsettled: CompoundOpen[]; ineffective: CompoundOpen[]; candidates: CompoundOpen[]; errors: CompoundOpen[]; skips: number }
  // Why the CLI could not be read, when it could not.
  problem: string
}

// One lesson or skill of the all-lessons view, as `compound list --json` gave it. `kind` is
// `lesson`, `guard` (a lesson that carries a pattern) or `skill`.
export type CompoundItem = { name: string; level: string; kind: string; reuse: number; guards: number; recall: number; use: number; flag: string; description: string }
// One lesson, as `compound show <name> --json` gave it. `loading` while the CLI is asked,
// `failed` with `problem` when it could not say. `at` is when it was read, in milliseconds;
// `last` is the newest reuse, guard, recall or use that names the lesson, its time in seconds.
export type CompoundDetail = {
  name: string
  state: 'loading' | 'ready' | 'failed'
  problem: string
  at: number
  level: string
  kind: string
  match: string[]
  description: string
  body: string
  reuse: number
  guards: number
  recall: number
  use: number
  flag: string
  last: { at: number; type: string } | null
  path: string
  files: string[]
}
// Which of the pane's views is shown: the dashboard, every lesson, or one lesson, and the
// view `back` returns to from a lesson. `items` is null until the list was read.
export type CompoundPaneView = 'board' | 'all' | 'lesson'
export type CompoundPane = {
  session: string
  view: CompoundPaneView
  back: 'board' | 'all'
  detail: CompoundDetail | null
  items: CompoundItem[] | null
  // Why the list could not be read, when it could not.
  itemsProblem: string
}

declare module 'claude-code' {
  interface PluginState {
    compound: {
      band: CompoundBand | null
      // The time of the band's last animation frame, in milliseconds.
      frame: number
      board: CompoundBoard | null
      pane: CompoundPane | null
    }
  }
}
