#!/bin/sh
# Records docs/media/demo.gif: three scenes of REAL interactive sessions, driven by vhs.
# Nothing on screen is scripted output: the sessions run on --model sonnet, and what
# they do varies from take to take, so a take is looked at before it is kept.
#
# To re-record:
#   dev/demo.sh world            build the throwaway world, print its directory (resets it)
#   dev/demo.sh cards            record the three title cards        -> takes/cards.mp4
#   dev/demo.sh learn  [N]       scenes 1 and 2, one session         -> takes/learn-N.mp4
#   dev/demo.sh later  [N]       scene 3, a new session elsewhere    -> takes/later-N.mp4
#   dev/demo.sh events           what the mod logged, one line an event (did the take work?)
#   dev/demo.sh join CUTS        cut and join the takes into docs/media/demo.gif
#
# A good `learn` take is one whose event log shows capture (a failure, then its fix) and
# learn. Scene 1 is wanted with a real failure first: when the session converts the file
# on its first try there is no capture, so run `dev/demo.sh world` and `learn` again.
# `later` is recorded against the store the kept `learn` take left, and may be repeated:
# each repeat is a new session, and a guard refuses once per session.
#
# CUTS is a file of lines `<take file> <start seconds> <end seconds>`; the listed pieces
# are joined in order, and everything between them (the model thinking) is left out.
# Pick the times by looking: `ffmpeg -ss T -i take.mp4 -frames:v 1 f.png`. The cuts of
# the published GIF are dev/demo.cuts. A line `still <take file> <seconds> <name>.png`
# writes one frame to docs/media.
#
# The world: $TMPDIR/compound-demo holds a copy of this package (so no path on screen is
# under the real home), a store, a Claude directory the copy is installed into (never the
# real one), and two projects, acme-api and billing-svc. The session itself still uses
# the real account. env.sh there defines `claude` as a function that adds
#   --plugin-dir <the copy> --setting-sources project --tools Bash,Skill --allowedTools Bash,Skill
# so the command typed on screen is `claude --model sonnet`; see dev/ui-check.tape for why
# each flag and each unset variable is needed. The session has the Bash and Skill tools
# only: with Write it converts the file by hand and runs nothing. Its shell reads a
# profile in the world (ZDOTDIR) whose PATH is the system directories and Homebrew, so
# python3 is the system's 3.9 (no tomllib) and `which` prints no home path. It spends
# model calls.
set -eu
repo="$(cd "$(dirname "$0")/.." && pwd -P)"
world="$(cd "${TMPDIR:-/tmp}" && pwd -P)/compound-demo"
# Outside the world, so `world` (which starts the store over) keeps the takes.
takes="$(cd "${TMPDIR:-/tmp}" && pwd -P)/compound-demo-takes"

build_world() {
  rm -rf "$world"
  mkdir -p "$world/home" "$world/claude" "$world/surfer" "$world/bin" "$world/zdot" "$takes" \
    "$world/acme-api" "$world/billing-svc" "$world/compound"
  # The package as it stands in the working tree, without history, notes or media.
  for part in .claude-plugin bin hooks skills lessons types tsconfig.json; do
    [ -e "$repo/$part" ] && cp -R "$repo/$part" "$world/compound/$part"
  done

  # Large enough, and with enough kinds of value, that nobody converts it by hand.
  cat > "$world/acme-api/config.toml" <<'TOML'
title = "acme-api"
released = 2026-09-28T09:30:00Z

[server]
host = "0.0.0.0"
port = 8080
workers = 4
timeouts = { read = 30, write = 30, idle = 120 }
allowed_origins = ["https://acme.example", "https://admin.acme.example"]

[database]
name = "acme"
pool_size = 10
replicas = ["db-1.internal", "db-2.internal", "db-3.internal"]
statement_timeout = 2.5

[cache]
backend = "redis"
ttl_seconds = 300
key_prefix = "acme:"

[logging]
level = "info"
format = """
%(asctime)s %(levelname)s
%(name)s: %(message)s"""

[features]
beta = true
rate_limits = { anonymous = 60, member = 600 }

[[routes]]
path = "/v1/orders"
methods = ["GET", "POST"]
auth = true

[[routes]]
path = "/v1/health"
methods = ["GET"]
auth = false

[[routes]]
path = "/v1/invoices"
methods = ["GET"]
auth = true
cache_seconds = 45
TOML
  cat > "$world/billing-svc/defaults.toml" <<'TOML'
[server]
port = 8000
workers = 2

[billing]
currency = "USD"
retries = 3
TOML
  cat > "$world/billing-svc/local.toml" <<'TOML'
[server]
port = 9100

[billing]
retries = 5
TOML

  # A neutral shell for the session: the Bash tool starts zsh, which reads its profile
  # from ZDOTDIR, so the PATH there decides what `which python3` prints. With the system
  # directories first, python3 is macOS's own 3.9 and no path on screen is under a home.
  real_claude="$(command -v claude)"
  path="$world/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
  printf 'export PATH="%s"\n' "$path" > "$world/zdot/.zshenv"
  cp "$world/zdot/.zshenv" "$world/zdot/.zshrc"
  surfer="$(command -v surfer || true)"
  [ -n "$surfer" ] && ln -s "$surfer" "$world/bin/surfer"
  cat > "$world/env.sh" <<SH
# usage: . env.sh <project directory name>
export COMPOUND_HOME="$world/home" COMPOUND_CLAUDE_DIR="$world/claude"
export COMPOUND_PROJECT="$world/\${1:-acme-api}"
export CLAUDE_HISTORY_SURFER_DIR="$world/surfer" CLAUDE_CODE_PLUGIN_DIRS=""
export PATH="$path" ZDOTDIR="$world/zdot" PS1='\$ '
unset COMPOUND_OFF COMPOUND_QUIET CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT
claude() { "$real_claude" --plugin-dir "$world/compound" --setting-sources project --tools Bash,Skill --allowedTools Bash,Skill "\$@"; }
cd "\$COMPOUND_PROJECT"
SH
  # The title cards: a shell function the cards tape calls, printed by printf.
  cat > "$world/cards.sh" <<'SH'
card() {
  clear
  printf '\n\n\n\n\n\n\n\n\n\n\n\n            \033[1;38;5;208m%s\033[0m   \033[1m%s\033[0m\n\n                \033[38;5;245m%s\033[0m\n' "$1" "$2" "$3"
}
PS1=''
tput civis
clear
SH
  # Installed into the world's own Claude directory, so `compound status` there reports
  # an enabled mod and a linked CLI. The real ~/.claude is not named anywhere.
  ( . "$world/env.sh" acme-api && COMPOUND_NO_SURFER=1 "$world/compound/bin/compound" install \
      --claude-dir "$world/claude" --bin-dir "$world/bin" >/dev/null )
}

record() { # record <tape> <output name>
  [ -f "$world/env.sh" ] || build_world
  cd "$world"
  rm -f "$takes/$2.mp4"
  sed "s|@OUT@|$takes/$2.mp4|" "$repo/dev/$1" > "$world/$1"
  vhs "$world/$1" || echo "vhs exited $?: the take may be incomplete"
  echo "take: $takes/$2.mp4"
}

events() {
  python3 - "$world/home/events.jsonl" <<'PY'
import json, sys
try:
    rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
except FileNotFoundError:
    rows = []
for e in rows:
    rest = {k: (v if len(str(v)) < 90 else str(v)[:90] + '...') for k, v in e.items() if k not in ('ts', 'type', 'session', 'project')}
    print(e.get('ts'), e.get('type'), (e.get('project') or '').rsplit('/', 1)[-1], json.dumps(rest))
PY
}

join() { # join <cuts file>
  out="$repo/docs/media"
  work="$world/join"
  rm -rf "$work"
  mkdir -p "$work" "$out"
  n=0
  : > "$work/list.txt"
  while read -r a b c d; do
    case "$a" in ''|'#'*) continue ;; esac
    if [ "$a" = still ]; then
      ffmpeg -v error -y -ss "$c" -i "$takes/$b" -frames:v 1 "$out/$d" </dev/null
      continue
    fi
    n=$((n + 1))
    piece="$work/$(printf '%03d' "$n").mp4"
    ffmpeg -v error -y -ss "$b" -to "$c" -i "$takes/$a" -an -r "${DEMO_FPS:-10}" \
      -c:v libx264 -preset veryfast -crf 14 -pix_fmt yuv420p "$piece" </dev/null
    echo "file '$piece'" >> "$work/list.txt"
  done < "$1"
  ffmpeg -v error -y -f concat -safe 0 -i "$work/list.txt" -c copy "$work/all.mp4" </dev/null
  filters="fps=${DEMO_FPS:-10},scale=${DEMO_WIDTH:-1000}:-1:flags=lanczos"
  ffmpeg -v error -y -i "$work/all.mp4" -vf "$filters,palettegen=max_colors=${DEMO_COLORS:-128}:stats_mode=diff" "$work/palette.png" </dev/null
  ffmpeg -v error -y -i "$work/all.mp4" -i "$work/palette.png" \
    -lavfi "$filters [x]; [x][1:v] paletteuse=dither=none:diff_mode=rectangle" "$out/demo.gif" </dev/null
  ls -l "$out/demo.gif"
  ffprobe -v error -show_entries format=duration -of csv=p=0 "$work/all.mp4"
}

case "${1:-}" in
  world) build_world; echo "$world" ;;
  cards) record demo-cards.tape cards ;;
  learn) record demo-learn.tape "learn-${2:-1}"; events ;;
  later) record demo-later.tape "later-${2:-1}"; events ;;
  events) events ;;
  join) join "${2:-$repo/dev/demo.cuts}" ;;
  *) sed -n '2,32p' "$0"; exit 2 ;;
esac
