// What the mission says, from the prompts a session was given. Pure: rows in, text out.
//
// The format is the one hooks/mission.sh settled on after a real failure: each request is
// a block of `> `-prefixed lines under a header, never a quoted string, because a prompt
// that contains a quote of its own closes a quoted string early and a prefix cannot be
// closed by anything the text contains.

export type Row = { text: string }

export const FIRST_CHARS = 1200
export const EACH_CHARS = 400
export const RECENT = 3
// A prompt shorter than this is "continue" or "yes do it": counted, never quoted.
export const SHORT_WORDS = 6
const PREFIX = '> '

// Words, for a text that may not put spaces between them: a hyphen separates as a space
// does, and each CJK character counts as a word.
export function words(text: string): number {
  const cjk = text.match(/[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/g)?.length ?? 0
  return text.split(/[\s-]+/).filter(w => w !== '').length + cjk
}

// Cut at `cap` characters without leaving half of a surrogate pair behind.
function cutAt(text: string, cap: number): string {
  const code = text.charCodeAt(cap - 1)
  return text.slice(0, code >= 0xd800 && code <= 0xdbff ? cap - 1 : cap)
}

// A slash command: one word of letters after the slash, then nothing or a space. A
// request that begins with a path ("/Users/me/proj/parser.py is the file...") is not one.
export function isCommand(text: string): boolean {
  return /^\/[A-Za-z][A-Za-z0-9:_-]*(\s|$)/.test(text)
}

export function substantive(text: string): boolean {
  return words(text) >= SHORT_WORDS
}

// The prefixed lines of one request, with a marker where the cap cut it.
function quoted(text: string, cap: number): string[] {
  if (text.length <= cap) return text.split('\n').map(line => PREFIX + line)
  const kept = cutAt(text, cap)
  return [...kept.split('\n').map(line => PREFIX + line), `${PREFIX}[... ${text.length - kept.length} more chars]`]
}

function block(text: string, index: number, of: number, cap: number): string {
  return [`(request ${index + 1} of ${of}, ${text.length} chars)`, ...quoted(text, cap)].join('\n')
}

// Which requests are quoted: the first substantive one, and the most recent RECENT
// substantive ones after it. With none substantive but the first, the last RECENT rows.
export function chosen(rows: readonly Row[]): number[] {
  const subs = rows.map((r, i) => (substantive(r.text) ? i : -1)).filter(i => i >= 0)
  const first = subs[0] ?? 0
  const later = subs.filter(i => i !== first)
  const recent = later.length > 0 ? later.slice(-RECENT) : rows.map((_, i) => i).filter(i => i !== first).slice(-RECENT)
  return [first, ...recent].filter((i, at, all) => i < rows.length && all.indexOf(i) === at).sort((a, b) => a - b)
}

// The whole mission, or '' when there is nothing to state. Statements of fact only: an
// imperative in injected context was refused as prompt injection when this was measured.
export function mission(rows: readonly Row[]): string {
  if (rows.length === 0) return ''
  const picks = chosen(rows)
  const first = picks[0]
  const out = [
    `The user's requests in this session, verbatim, oldest first. ${rows.length} recorded; ${picks.length} quoted below.`,
  ]
  let last = -1
  for (const i of picks) {
    const skipped = rows.slice(last + 1, i).reduce((n, r) => n + r.text.length, 0)
    if (skipped > 0) out.push(`[... ${skipped} characters of this session's requests are not quoted here ...]`)
    out.push(block(rows[i]!.text, i, rows.length, i === first ? FIRST_CHARS : EACH_CHARS))
    last = i
  }
  return out.join('\n\n')
}

// For a prompt too short to stand alone: the last substantive request before it.
export function lastSubstantive(rows: readonly Row[]): string {
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    if (substantive(rows[i]!.text)) {
      return [
        `The user's last substantive request in this session, verbatim (request ${i + 1} of ${rows.length}, ${rows[i]!.text.length} chars):`,
        ...quoted(rows[i]!.text, FIRST_CHARS),
      ].join('\n')
    }
  }
  return ''
}

// Not everything that arrives as a prompt was typed by the user. A subagent's hand-back, a
// background task's notice and a harness reminder come in on the same channel, and
// history-surfer stores them as prompts: on 2026-10-03 a 14,588-character subagent report
// was being stated back as "request 11 of 11". Those are recognised by how the harness
// frames them and are never part of the mission.
export function typedByUser(text: string): boolean {
  const head = text.trimStart().slice(0, 60)
  // The harness frames what it injects in a hyphenated lowercase tag (<agent-message,
  // <task-notification, <system-reminder, <local-command-stdout, <command-name,
  // <teammate-message) or a bracketed notice. Markup a user types, <div>, has no hyphen.
  if (/^<[a-z]+(-[a-z]+)+[\s>]/.test(head)) return false
  return !/^(\[SYSTEM NOTIFICATION|\[Request interrupted|Another Claude session sent a message)/.test(head)
}

// Does a closing message claim the work is finished? Read from its last two sentences. A
// sentence that negates, hedges, waits or asks is not a claim: "I could not get this
// done", "the suite is not passing", "waiting for the subagent to complete" and "shall I
// mark it complete?" each carry a done-word and each say the opposite.
const DONE = /\b(done|complete[d]?|finished|all set|implemented|fixed|ready|passes|passing)\b/i
const NOT_A_CLAIM = /\b(not|no|never|cannot|can't|couldn't|unable|won't|isn't|aren't|wasn't|n't|yet|still|waiting|pending|once|when|until|if|shall|should|would you|do you|are you)\b/i

export function claimsDone(message: string): boolean {
  const sentences = message.slice(-600).split(/(?<=[.!?])\s+|\n+/).map(t => t.trim()).filter(t => t !== '')
  const claim = (t: string) => DONE.test(t) && !NOT_A_CLAIM.test(t) && !t.endsWith('?')
  const last = sentences[sentences.length - 1]
  // The message ends on its last sentence: one that waits, negates or asks takes back
  // whatever the sentence before it claimed.
  if (last === undefined || NOT_A_CLAIM.test(last) || last.endsWith('?')) return false
  return sentences.slice(-2).some(claim)
}

// The store history-surfer keeps: one JSON object per line. Rows for one session, with
// slash commands, empty prompts, harness frames and immediate repeats dropped.
export function storeRows(raw: string, session: string): Row[] {
  const out: Row[] = []
  for (const line of raw.split('\n')) {
    if (!line.includes(session)) continue
    try {
      const r = JSON.parse(line) as { session_id?: string; prompt?: string; is_command?: boolean }
      if (r.session_id !== session) continue
      const text = (r.prompt ?? '').trim()
      if (text === '' || isCommand(text) || !typedByUser(text)) continue
      // history-surfer's own flag catches a built-in typed without its slash ("config"),
      // and also flags a request that begins with a path. Only a short one is believed.
      if (r.is_command === true && !substantive(text)) continue
      // It also records one prompt twice, from stdin and from the transcript.
      if (out.length > 0 && out[out.length - 1]!.text === text) continue
      out.push({ text })
    } catch {
      continue
    }
  }
  return out
}
