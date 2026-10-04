// What may leave this mod as text. A tool call and its error are sent to a model, written
// to the event log and quoted back into the session, so both are masked first.
//
// The masking is a LOWER BOUND. It knows assignments and flags whose name says secret,
// authorization headers, credentials in a URL, and a few well-known token shapes. A secret
// passed as a bare positional argument is not recognisable and is not caught.

const MASK = '<redacted>'

export function redact(text: string): string {
  return text
    .replace(/\b([A-Za-z_][A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|PASS|KEY|CREDENTIALS?|AUTH)[A-Za-z0-9_]*)=("[^"]*"|'[^']*'|[^\s;&|]+)/gi, `$1=${MASK}`)
    .replace(/(--?(?:token|password|passwd|secret|api[-_]?key|auth|credentials?)(?:=|\s+))("[^"]*"|'[^']*'|[^\s;&|]+)/gi, `$1${MASK}`)
    .replace(/(Authorization:\s*(?:Bearer|Basic|Token)\s+)[^\s"']+/gi, `$1${MASK}`)
    .replace(/(\bBearer\s+)[A-Za-z0-9._~+/=-]{12,}/g, `$1${MASK}`)
    .replace(/(\b[a-z][a-z0-9+.-]*:\/\/)[^/\s:@]+:[^/\s@]+@/gi, `$1${MASK}@`)
    .replace(/\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[abpr]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})/g, MASK)
}

// One masked line: for a status entry, a toast, or a field of an event.
export function oneLine(text: string, cap: number): string {
  const flat = redact(text).replace(/\s+/g, ' ').trim()
  return flat.length <= cap ? flat : `${flat.slice(0, cap - 1)}…`
}

// Head and tail with the cut marked, so a reader never takes a shortened call for a broken
// one. Errors keep more tail than head: the message that names the mistake is usually last.
export function excerpt(text: string, head: number, tail: number): string {
  if (text.length <= head + tail) return text
  return `${text.slice(0, head)}\n[... ${text.length - head - tail} characters omitted here ...]\n${text.slice(-tail)}`
}
