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
export type CompoundNote = { kind: CompoundNoteKind; text: string; at: number }

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
  weak: string[]
  // Failures of the mod itself that Claude was not yet told about.
  errors: number
  track: CompoundTrack | null
}

export type CompoundLevel = { level: string; lessons: number; skills: number; guards: number }
export type CompoundLesson = { name: string; level: string; guard: boolean; reuse: number; guards: number; recall: number; flag: string }
export type CompoundRecent = { at: number; type: string; text: string }
export type CompoundCheck = { check: string; status: string; detail: string }

// What the pane shows, as `compound status --json` and `compound events --json` gave it.
export type CompoundBoard = {
  session: string
  at: number
  // The health checks that did not pass.
  health: CompoundCheck[]
  checks: number
  levels: CompoundLevel[]
  lessons: CompoundLesson[]
  recent: CompoundRecent[]
  open: { unsettled: string[]; ineffective: string[]; candidates: string[]; errors: string[]; skips: number }
  // Why the CLI could not be read, when it could not.
  problem: string
}

declare module 'claude-code' {
  interface PluginState {
    compound: {
      band: CompoundBand | null
      // The time of the band's last animation frame, in milliseconds.
      frame: number
      board: CompoundBoard | null
    }
  }
}
