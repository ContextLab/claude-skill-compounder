# 2026-10-04: v0.4.0 release and the audit

## Done

- Released `v0.4.0` (tag and GitHub release). `plugin.json` went from `1.0.0` to `0.4.0`
  so the manifest and the tag agree. The release notes first recommended a tag-pinned
  install line; that was corrected the same hour, because `compound update` exits 1 on a
  checkout pinned to a tag (detached HEAD). The code still behaves that way.
- Pane fix (`cfe654b`): the Most used table is in columns under its legend, Recent pads
  to the longest event type, no stray ellipsis at mid widths.
- Installer fixes: `install.sh` refuses a python older than 3.9 (not tested against a
  real old interpreter: none is on this machine), installs a tag without git's
  detached-HEAD advice, and removes a clone it made when the ref has no `bin/compound`.
  `compound install` says to start a new session. README: four possible `WARN` rows on a
  new install, and the pre-call check measured at about 45 ms.
- Recorded user lesson `rm-glob-after-cd-denied` (settles capture `7cd2f808`).

## The audit

Four agents; their full reports are in `notes/2026-10-04-audit/`:

| File | Subject |
|-|-|
| `audit-ui.md` | band, pane, toasts, CLI text |
| `audit-quality.md` | lesson and reuse quality, latency, replay over 45,185 historical Bash calls |
| `audit-install.md` | install, update, uninstall in a sandbox; the marketplace route |
| `general-pool/` | six drafted general lessons as the CLI wrote them, their bodies, the `compound add` commands (`build.sh`), and four guard patterns tested for later (`guards.py`, `guards.out`) |

The general-pool agent's written report exists only in the session transcript; its
substance is the table below.

### General-pool drafts (all recall lessons, none a guard)

| Name | Failure |
|-|-|
| `zsh-no-matches-found` | an unquoted glob that matches nothing aborts the line |
| `zsh-equals-not-found` | `echo =====` fails with `==== not found` |
| `zsh-status-path-variables` | `status` is read-only; assigning `path` breaks `PATH` |
| `sed-in-place-bsd` | GNU-style `sed -i` fails on macOS or leaves a `file-e` backup |
| `pip-externally-managed` | PEP 668 refusal; use a venv |
| `macos-gnu-only-commands` | `timeout`, `date -d`, `grep -P`, `stat -c` |

Tested on macOS and zsh only. 12 of 12 real haiku sessions recalled the right lesson or
none. Weak: in both pip sessions the model was shown the lesson and still used
`--break-system-packages`.

Blocking gap before they ship: a general recall lesson becomes "ineffective" after two
recalls and cannot be strengthened (`add --update` refuses general lessons), so the stop
is refused and the session can only `skip`.

### Open bugs found and not fixed (each needs a decision)

- `compound update` on a tag-pinned checkout exits 1.
- Guard patterns anchored with `(^|[;&|]\s*)` miss a command on a new line, after `do`,
  or inside `$(`; `skills/learn/SKILL.md` teaches that anchor.
- Guards are tested against `Write`, `Agent` and hand-back text, not only commands.
- A recall right after a guard refusal counts toward "ineffective".
- A harness or permission refusal followed by a working call is judged a fix (the only
  organic capture so far was one).
- 79% of zsh shell errors in the replay came back with exit 0, so recall and capture
  never see them.
- The pane clips its own labels at 40 columns.
- Install is silent when another `compound` earlier on `PATH` shadows the link.
- No curl-able uninstall; the Claude Code minimum (2.1.288) is checked nowhere.

### Proposals, in the order recommended to the owner

1. Trustworthy capture and guards: drop non-command failures before the judge; guards
   match commands only, with a multi-line anchor; exit-0 shell errors count as failures.
2. Platform and shell condition on a lesson, and a way to strengthen or switch off a
   general lesson; then ship the six drafts (four of them as guards).
3. Install: default to the newest release tag, `update` moves between tags, curl-able
   uninstall, Claude Code version check, a marketplace route once it is shown to load
   the function hooks.
4. Indicators: name the lesson and the work found instead of a count; a totals line
   ("guards stopped N calls, M lessons recalled, K reuses"); a once-per-session
   `compound ready · N lessons`; relative times.
5. Pane drill-down: open a lesson from the pane, show the settling command on Open rows.
6. Reuse precision: rarity-weighted words; 0 of 4 items named in the two real injections
   were relevant.
