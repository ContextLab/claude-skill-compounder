// What may leave this mod as text. A tool call and its error are sent to a model, written
// to the event log and quoted back into the session, so both are masked first. Everything
// the mod sends to the judge or writes to an event passes through `redact`.
//
// The masking is a LOWER BOUND. It knows assignments, flags, headers and JSON members whose
// name says secret, the password arguments of a few programs, credentials in a URL, PEM
// blocks and some well-known token shapes. A secret passed as a bare positional argument
// is not recognisable and is not caught. It errs toward masking: MONKEY=1 loses its value.

const MASK = '<redacted>'

// A name that says its value is a secret, anywhere in the name and in any case.
const SECRET_NAME = '(?:TOKEN|SECRET|PASSWORD|PASSWD|PASS|PWD|KEY|CREDENTIALS?|AUTH)'
// The same for a JSON member or a header, where "key" alone is too common to mask.
const SECRET_MEMBER = '(?:api[_-]?key|access[_-]?key|private[_-]?key|secret|token|password|passwd|credentials?|authorization)'
const VALUE = `("[^"]*"|'[^']*'|[^\\s;&|]+)`

const RULES: readonly (readonly [RegExp, string])[] = [
  // A PEM block, whole, or from its first line to the end when its last line was cut off.
  [/-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)[A-Z0-9 ]*-----[\s\S]*?(?:-----END [A-Z0-9 ]*-----|$)/g, MASK],
  // TOKEN=..., MY_API_KEY=..., password=...: an assignment or a query parameter.
  [new RegExp(`\\b([A-Za-z0-9_]*${SECRET_NAME}[A-Za-z0-9_]*)=${VALUE}`, 'gi'), `$1=${MASK}`],
  // --token X, --password=X, --api-key X.
  [new RegExp(`(--?(?:token|password|passwd|secret|api[-_]?key|auth|credentials?)(?:=|\\s+))${VALUE}`, 'gi'), `$1${MASK}`],
  // curl -u user:password, curl --user user:password.
  [new RegExp(`(\\bcurl\\b[^|;&\\n]*?\\s(?:-u|--user)(?:=|\\s*))${VALUE}`, 'g'), `$1${MASK}`],
  // mysql -pPASSWORD (attached: `-p name` with a space is a database, not a password).
  [/(\b(?:mysql|mysqldump|mysqladmin|mariadb)\b[^|;&\n]*?\s-p)([^\s;&|]+)/g, `$1${MASK}`],
  // docker login -p PASSWORD, sshpass -p PASSWORD.
  [new RegExp(`(\\b(?:docker\\s+login|sshpass)\\b[^|;&\\n]*?\\s-p\\s*)${VALUE}`, 'g'), `$1${MASK}`],
  // Authorization: Bearer X, Proxy-Authorization: Basic X, Authorization: X.
  [/(\b(?:Proxy-)?Authorization\\?["']?\s*:\s*\\?["']?(?:(?:Bearer|Basic|Token|Digest|Negotiate)\s+)?)[^\s"'\\,}]+/gi, `$1${MASK}`],
  // X-Api-Key: X, X-Auth-Token: X, Api-Key: X.
  [/(\b(?:X-[A-Za-z-]*(?:Key|Token|Auth|Secret)[A-Za-z-]*|Api-Key)\s*:\s*)[^\s"'\\]+/gi, `$1${MASK}`],
  // "api_key": "X", 'token': 'X', and the same inside a shell string: \"password\": \"X\".
  [new RegExp(`(\\\\"[^"\\s\\\\]*${SECRET_MEMBER}[^"\\s\\\\]*\\\\"\\s*:\\s*\\\\")[^"\\\\]*(\\\\")`, 'gi'), `$1${MASK}$2`],
  [new RegExp(`("[^"\\s]*${SECRET_MEMBER}[^"\\s]*"\\s*:\\s*")(?:[^"\\\\]|\\\\.)*(")`, 'gi'), `$1${MASK}$2`],
  [new RegExp(`('[^'\\s]*${SECRET_MEMBER}[^'\\s]*'\\s*:\\s*')[^']*(')`, 'gi'), `$1${MASK}$2`],
  // Bearer X wherever it sits.
  [/(\bBearer\s+)[A-Za-z0-9._~+/=-]{12,}/g, `$1${MASK}`],
  // scheme://user:password@host.
  [/(\b[a-z][a-z0-9+.-]*:\/\/)[^/\s:@]+:[^/\s@]+@/gi, `$1${MASK}@`],
  // Token shapes: OpenAI/Anthropic, GitHub, AWS, Slack, GitLab, Google, Hugging Face, npm, a JWT.
  [/\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?:AKIA|ASIA)[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|glpat-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{30,}|hf_[A-Za-z0-9]{30,}|npm_[A-Za-z0-9]{30,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})/g, MASK],
]

// Characters that draw nothing, or that a terminal or a reader takes for something other
// than text: control characters (an escape sequence starts with one), zero-width characters
// and the bidirectional overrides. A newline and a tab are text.
const HIDDEN = /[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]/g
const CONTROL = /[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u2028\u2029]/g

// Text as it may be shown: without what is hidden, and with a space where a control
// character stood.
export function plain(text: string): string {
  return text.replace(HIDDEN, '').replace(CONTROL, ' ')
}

// Text for ONE row of the band or the pane: a newline and a tab are not drawn either.
export function drawn(text: string): string {
  return plain(text).replace(/[\n\t]/g, ' ')
}

export function redact(text: string): string {
  let out = text
  for (const [pattern, to] of RULES) out = out.replace(pattern, to)
  return out
}

// One masked line: for a status entry, a toast, or a field of an event.
export function oneLine(text: string, cap: number): string {
  const flat = plain(redact(text)).replace(/\s+/g, ' ').trim()
  return flat.length <= cap ? flat : `${flat.slice(0, cap - 1)}…`
}

// One word of a shell command line, for a command the mod writes out for Claude or the
// user to run: a value that is not plainly a word is single-quoted, so nothing in a name
// or a path is ever read by the shell as a command of its own.
export function shq(text: string): string {
  const flat = plain(text).replace(/[\n\t]+/g, ' ')
  return /^[A-Za-z0-9_@%+=:,./-]+$/.test(flat) ? flat : `'${flat.replace(/'/g, `'\\''`)}'`
}

// Head and tail with the cut marked, so a reader never takes a shortened call for a broken
// one. Errors keep more tail than head: the message that names the mistake is usually last.
export function excerpt(text: string, head: number, tail: number): string {
  if (text.length <= head + tail) return text
  return `${text.slice(0, head)}\n[... ${text.length - head - tail} characters omitted here ...]\n${text.slice(-tail)}`
}
