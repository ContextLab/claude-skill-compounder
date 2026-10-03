// The two questions this mod asks a model, and how their answers are read.
// Pure text in, pure values out: the replay scores exactly these functions.

export type Lesson = { id: string; text: string; scope: 'project' | 'global' | 'elsewhere'; project?: string }
export type Pair = { failed: string; error: string; worked: string }
export type FixVerdict =
  | { verdict: 'LESSON'; lesson: string }
  | { verdict: 'KNOWN'; id: string }
  | { verdict: 'NONE'; reason: string }

const CALL_HEAD = 1500
const CALL_TAIL = 700
const ERROR_HEAD = 500
const ERROR_TAIL = 900

// Head and tail with the cut marked, so a judge never reads a truncated call as a broken one.
// Errors keep more tail than head: the message that names the mistake is usually last.
export function excerpt(text: string, head: number, tail: number): string {
  if (text.length <= head + tail) return text
  return `${text.slice(0, head)}\n[... ${text.length - head - tail} characters omitted here ...]\n${text.slice(-tail)}`
}

function listed(lessons: readonly Lesson[]): string {
  if (lessons.length === 0) return '(none)'
  return lessons.map(l => `${l.id}: ${l.text}`).join('\n')
}

export function fixPrompt(pair: Pair, lessons: readonly Lesson[]): string {
  return [
    "You review one pair of tool calls from a coding agent's session: a call that FAILED and a later call that SUCCEEDED.",
    'Most such pairs hold no lesson: the later call is simply the next thing the agent did. Decide whether this one does.',
    'A marker like "[... N characters omitted here ...]" means the text was shortened for you. The real call was complete; never treat a cut as a mistake.',
    '',
    'It is a lesson only when ALL FOUR hold:',
    'A. same_goal: the later call is another attempt at the SAME thing the failed call was doing, not the next step of the work.',
    'B. call_mistake: the failure came from HOW the call was written: a wrong flag, wrong syntax, a missing program, a shell quirk, wrong usage of a script.',
    '   Not when a test, linter or check legitimately reported a problem in the work, a search found nothing, an assert in a patch script did not match,',
    '   freshly written code had a bug, or one URL or file was unavailable.',
    '   Not when the output was what the agent wanted and only an exit status was non-zero.',
    '   Exception: a non-zero status that stopped the REST of an && chain, or a shell that rejected the command, IS a call mistake.',
    'C. evidence: you can quote, word for word, the part of the error text that names the mistake.',
    'D. recurs: a future session, knowing nothing of this one, would predictably write the call the same wrong way, and one sentence would prevent it.',
    '',
    'If an existing lesson already covers the mistake, the verdict is KNOWN with its id.',
    '',
    'Existing lessons:',
    listed(lessons),
    '',
    'FAILED CALL:',
    excerpt(pair.failed, CALL_HEAD, CALL_TAIL),
    '',
    'ITS ERROR:',
    excerpt(pair.error, ERROR_HEAD, ERROR_TAIL),
    '',
    'LATER SUCCESSFUL CALL:',
    excerpt(pair.worked, CALL_HEAD, CALL_TAIL),
    '',
    'Reply with exactly one line of JSON and nothing else:',
    '{"same_goal":true|false,"call_mistake":true|false,"evidence":"<exact quote from ITS ERROR, or empty>","recurs":true|false,"verdict":"LESSON"|"KNOWN"|"NONE","id":"<existing lesson id, for KNOWN>","lesson":"<for LESSON, one sentence: the mistake, then what to do instead, quoting the working form>","reason":"<for NONE, a few words>"}',
  ].join('\n')
}

export function recallPrompt(failed: string, error: string, lessons: readonly Lesson[]): string {
  return [
    "A tool call in a coding agent's session just failed.",
    'Does one of the recorded lessons below describe this mistake and how to avoid it?',
    'Answer with a lesson only when it clearly applies to this failure.',
    '',
    'Recorded lessons:',
    listed(lessons),
    '',
    'FAILED CALL:',
    excerpt(failed, CALL_HEAD, CALL_TAIL),
    '',
    'ITS ERROR:',
    excerpt(error, ERROR_HEAD, ERROR_TAIL),
    '',
    'Reply with exactly one line of JSON and nothing else: {"id":"<lesson id>"} or {"id":null}',
  ].join('\n')
}

// The first {...} span of a reply, parsed; undefined when there is none or it is not JSON.
function firstObject(text: string): Record<string, unknown> | undefined {
  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start < 0 || end <= start) return undefined
  try {
    const value: unknown = JSON.parse(text.slice(start, end + 1))
    return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : undefined
  } catch {
    return undefined
  }
}

// Whitespace-insensitive containment: the judge's quote must really be in the error text.
function quoted(evidence: unknown, error: string): boolean {
  if (typeof evidence !== 'string') return false
  const squeeze = (t: string) => t.replace(/\s+/g, ' ').trim()
  const q = squeeze(evidence)
  return q.length >= 6 && squeeze(error).includes(q)
}

// A reply that cannot be read is NONE: an unreadable answer never writes a lesson. So is a
// LESSON whose own checks do not all hold, or whose evidence is not in the error it cites.
export function parseFix(text: string, lessons: readonly Lesson[], error: string): FixVerdict {
  const o = firstObject(text)
  if (o === undefined) return { verdict: 'NONE', reason: 'unreadable reply' }
  if (o.verdict === 'KNOWN' && typeof o.id === 'string' && lessons.some(l => l.id === o.id)) {
    return { verdict: 'KNOWN', id: o.id }
  }
  if (o.verdict === 'LESSON' && typeof o.lesson === 'string' && o.lesson.trim().length >= 20) {
    if (o.same_goal !== true || o.call_mistake !== true || o.recurs !== true) {
      return { verdict: 'NONE', reason: 'a check did not hold' }
    }
    if (!quoted(o.evidence, error)) return { verdict: 'NONE', reason: 'evidence not found in the error' }
    return { verdict: 'LESSON', lesson: o.lesson.trim().replace(/\s+/g, ' ') }
  }
  return { verdict: 'NONE', reason: typeof o.reason === 'string' && o.reason !== '' ? o.reason : 'no lesson' }
}

export function parseRecall(text: string, lessons: readonly Lesson[]): Lesson | undefined {
  const o = firstObject(text)
  if (o === undefined || typeof o.id !== 'string') return undefined
  return lessons.find(l => l.id === o.id)
}
