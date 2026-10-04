// The mod's settings, read from the environment by ./register and validated here. A value of
// the wrong shape takes the default: a typo is not a setting. No `$`, no I/O.

export type Knobs = {
  promptMinChars: number
  turnMinCalls: number
  nudgeCooldown: number
  recurLimit: number
  model: string
  judgeTimeoutMs: number
  repeatMin: number
}

export type RawKnobs = {
  promptMinChars?: string
  turnMinCalls?: string
  nudgeCooldown?: string
  recurLimit?: string
  model?: string
  judgeTimeout?: string
  repeatMin?: string
}

// haiku: the cheapest alias, and the fastest. The reuse check holds every substantial
// prompt for one model call, so speed is what the user feels. Its judgements are looser
// than a larger model's, and a false "this is a fix" costs one `compound skip`, not a
// written lesson.
export const DEFAULT_MODEL = 'haiku'

export const DEFAULTS: Knobs = {
  promptMinChars: 80,
  turnMinCalls: 25,
  nudgeCooldown: 1800,
  recurLimit: 2,
  model: DEFAULT_MODEL,
  judgeTimeoutMs: 10000,
  // How many sessions must have made one kind of request, this one included, before the
  // reuse check offers to make it a skill. Two would offer at the first repetition.
  repeatMin: 3,
}

// A whole number of at most nine digits and at least `min`, or the default.
export function whole(raw: string | undefined, fallback: number, min = 0): number {
  if (raw === undefined || !/^[0-9]{1,9}$/.test(raw)) return fallback
  const n = Number(raw)
  return n >= min ? n : fallback
}

// A model alias or id: letters, digits and the punctuation ids carry. Anything else is the default.
export function modelName(raw: string | undefined): string {
  return raw !== undefined && /^[A-Za-z0-9][A-Za-z0-9._:\[\]-]{0,79}$/.test(raw) ? raw : DEFAULT_MODEL
}

export function knobsFrom(raw: RawKnobs): Knobs {
  return {
    promptMinChars: whole(raw.promptMinChars, DEFAULTS.promptMinChars),
    turnMinCalls: whole(raw.turnMinCalls, DEFAULTS.turnMinCalls, 1),
    nudgeCooldown: whole(raw.nudgeCooldown, DEFAULTS.nudgeCooldown),
    recurLimit: whole(raw.recurLimit, DEFAULTS.recurLimit, 1),
    model: modelName(raw.model),
    // Seconds in the environment, milliseconds to the engine. Zero is no timeout at all,
    // which the prompt path cannot afford, so it takes the default.
    judgeTimeoutMs: whole(raw.judgeTimeout, DEFAULTS.judgeTimeoutMs / 1000, 1) * 1000,
    repeatMin: whole(raw.repeatMin, DEFAULTS.repeatMin, 2),
  }
}

// COMPOUND_OFF=1 and nothing else switches the mod off.
export function isOff(raw: string | undefined): boolean {
  return raw === '1'
}

// COMPOUND_QUIET=1 and nothing else turns the band above the prompt off.
export function isQuiet(raw: string | undefined): boolean {
  return raw === '1'
}
