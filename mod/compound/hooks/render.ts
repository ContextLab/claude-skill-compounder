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

export function words(text: string): number {
  return text.split(/\s+/).filter(w => w !== '').length
}

export function substantive(text: string): boolean {
  return words(text) >= SHORT_WORDS
}

function block(text: string, index: number, of: number, cap: number): string {
  const cut = text.length > cap
  const body = (cut ? text.slice(0, cap) : text).split('\n').map(line => PREFIX + line)
  if (cut) body.push(`${PREFIX}[... ${text.length - cap} more chars]`)
  return [`(request ${index + 1} of ${of}, ${text.length} chars)`, ...body].join('\n')
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
        ...rows[i]!.text.slice(0, FIRST_CHARS).split('\n').map(line => PREFIX + line),
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
  const head = text.trimStart().slice(0, 40)
  return !/^(<agent-message|<task-notification|<system-reminder|\[SYSTEM NOTIFICATION|Another Claude session sent a message)/.test(head)
}

// Does a closing message claim the work is finished?
export function claimsDone(message: string): boolean {
  return /\b(done|complete[d]?|finished|all set|implemented|fixed|ready|passes|passing)\b/i.test(message.slice(-600))
}

// The store history-surfer keeps: one JSON object per line. Rows for one session, with
// commands and empty prompts dropped.
export function storeRows(raw: string, session: string): Row[] {
  const out: Row[] = []
  for (const line of raw.split('\n')) {
    if (!line.includes(session)) continue
    try {
      const r = JSON.parse(line) as { session_id?: string; prompt?: string; is_command?: boolean }
      if (r.session_id !== session || r.is_command === true) continue
      const text = (r.prompt ?? '').trim()
      if (text !== '' && !text.startsWith('/') && typedByUser(text)) out.push({ text })
    } catch {
      continue
    }
  }
  return out
}
