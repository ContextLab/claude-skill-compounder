// What this mod is allowed to put on disk. Everything it writes ends up somewhere a later
// session reads: a note line is loaded into every session of the project, and the state
// log is read back for lessons from other projects. So command and error text is masked
// before it is kept, judged or logged, and a lesson is made one plain line.
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

// One line that cannot end the comment a note line is parsed back by, cannot be read as
// an option by the CLI it is handed to, and carries no secret the masks know.
export function plain(text: string): string {
  return redact(text)
    .replace(/<!--|-->/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[-\s]+/, '')
}
