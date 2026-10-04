# compound UI/UX audit (2026-10-04)

Audit only; nothing in the repo was edited. Evidence comes from: reading `hooks/view.ts`,
`hooks/render.ts`, `hooks/register.ts`, `bin/compound`, `docs/design.md` ("Seeing it work"),
`README.md` ("How you see it working"); the four PNGs in `docs/media/`; running
`bin/compound status | list | find python | events` against the owner's real store (80 events:
77 `learn`, 2 `reuse`, 1 `guard`); and rendering `boardLines` / `bandRow` from `hooks/view.ts`
with bun against the real `status --json` / `events --json` at 100, 60 and 40 columns.
Engine capabilities (Select, Button hotkeys, CommandOutput) were checked in the bundled
`claude-code.d.ts` / `reference.md` of the plugin-authoring skill (build 2.1.289).

Measured on this machine: `status --json` 0.13 s, `events --json --limit 20` 0.05 s,
`list --json` 0.08 s (wall clock, one run each).

---

## Ranked proposals

### 1. Say WHICH lesson / WHAT fix, not just a count  (S-M)

**Observed.** The three moments the user most wants named are shown as counts or bare labels.

- Reuse. `hooks/register.ts:703-704`:
  `$.ui.status(reuseStatus(answer.items.length, answer.earlier.length))` and
  `noted(band, 'reuse', reuseText(answer.items.length, answer.earlier.length), now)`.
  `hooks/render.ts:310-313`: ``if (items > 0) return `${items} reusable` ``.
  Rendered band: `◆ compound reuse found · 1 lesson or skill, 2 earlier requests`.
  The names are in hand on the line above (`lessons: answer.items.map(i => i.name)`, 693).
- Pane Recent drops the names too. `hooks/view.ts:365-366`:
  `return reuseText(names(e.lessons).length, names(e.prompts).length) || 'nothing'`.
  Real pane row: `12:58 ◆ reuse    1 lesson or skill, 2 earlier requests`, while the CLI prints
  the name for the same event: `2026-10-04T16:58:04Z reuse    09f47a44 claude-skill-compoun speckit-execute`.
- Owed. `hooks/register.ts:957-958`: `$.ui.status('lesson owed')` /
  `captured(band, now)` — no text. Screenshot `docs/media/demo-1-capture.png`:
  `● compound lesson owed   ✓ failed → ✓ fixed → ● owed → ○ recorded`, with
  `compound: lesson owed` again in the status area. "owed" appears three times; what is owed
  appears nowhere. `was.call` and `call` (the failed and working calls) are in scope at 944-947.

**Change.** Put the first name in the band/status, count the rest; give the owed state a
subject.

```
before  ◆ compound reuse found · 1 lesson or skill, 2 earlier requests
after   ◆ compound reuse found · speckit-execute  +2 earlier requests

before  compound: 2 reusable
after   compound: reuse cdl-bib-cite +1

before  ● compound lesson owed   ✓ failed → ✓ fixed → ● owed → ○ recorded
after   ● compound lesson owed · import tomllib → import tomli   ✓ failed → ✓ fixed → ● owed → ○ recorded

pane before  12:58 ◆ reuse    1 lesson or skill, 2 earlier requests
pane after   12:58 ◆ reuse    speckit-execute  +2 earlier requests
```

The owed subject must pass `redact()` (as the capture context already does) and `oneLine`;
the existing width cascade in `bandRow` (view.ts:306-315) already clips `name` last.
`captured()` needs a text argument and `CompoundBand` a field for it, because `owed` persists
after the note fades (`mainOf` 'owed' branch has `name: ''`, view.ts:267).

**Files.** `hooks/view.ts` (`reuseText`, `eventText`, `captured`, `mainOf`), `hooks/render.ts`
(`reuseStatus`), `hooks/register.ts` (two call sites), `types/index.d.ts`, tests in
`view.test.ts` / `render.test.ts` / `ui.test.ts`, the band table in `docs/design.md` and README.

**Not verified.** How a good short "what was fixed" string reads for long multi-line Bash
calls; a first-token diff of failed vs fixed may be needed and I did not prototype it. After a
reload or a `synced()` from the CLI the text would have to be re-derived from
`events --unsettled` (its rows carry `fixed`), or the band falls back to the bare label.

---

### 2. A "compound interest" headline: cumulative totals on the pane and in `compound status`  (M)

**Observed.** No surface totals anything. The pane opens with
`✔ healthy  9 checks` (view.ts:476-481) and the CLI with nine `PASS` rows. The payoff — how
often the store helped — is only derivable by reading a 33-row table in which 31 rows say
`never used`:

```
  agent-not-finished-until-handback     user   lesson  0      0      0       never used
  ...
  zsh-equals-word                       user   guard   0      1      0
```

The per-lesson tallies already exist (`tally()` bin/compound:985; `reuse`, `guard_hits`,
`recall` in `status --json`), so totals are a sum, not new bookkeeping.

**Change.** One headline line, first thing on both surfaces, built in `build_status()` as a new
`totals` object so the pane and the text report cannot disagree (CLAUDE.md: one implementation).

```
pane / status, after:
✔ healthy · 34 lessons, 7 guards, 6 skills
  1 call stopped by a guard · 2 prompts given existing work · 0 failures answered from a lesson
  77 lessons recorded · last helped 2m ago (reuse speckit-execute)
```

Also add a "this session" count to the band's guard note when it is > 1 lifetime hit:
`■ compound guard stopped a call · zsh-equals-word (2nd time)` — the lifetime count is
obtainable without a new CLI call only if `check` returns it with the hit; today
`parseHits` gives names (register.ts:791). That needs `check` to add `hits` per lesson from
the tally it would have to read; **`check` runs before a tool call under the 1.5 s
`BUDGET.check`, so this must be measured before adopting** — otherwise keep the ordinal to
the pane only.

**Files.** `bin/compound` (`build_status`, `cmd_status`), `hooks/view.ts` (`boardFrom`,
`boardLines`), `types/index.d.ts`, `docs/design.md`, `tests/test_*.py`, `view.test.ts`.

**Not verified / not available.** "Time saved" and "tokens saved" cannot be computed from the
log as it is: the only durations logged are the mod's own cost (`ms`, `gather_ms`, `judge_ms`
on `reuse`; `ms` on `guard` and `capture`). I found no field recording how long the failed
call or the fix took. A saved-time figure would be an invented estimate; I recommend counts
only unless a `failed_ms`/`turns_to_fix` field is added to `capture`.

---

### 3. First run and idle: no sign the mod is loaded; a reuse check that finds nothing ends in silence  (S-M)

**Observed.**
- `session.start` (register.ts:1128-1136) registers the command and does
  `paint($, band => ({ ...band, busy: [] }))` and `boardStale($)` — nothing visible. grep for
  `welcome|first run|loaded` in `hooks/`, README and design.md finds no greeting.
- The band is by design empty at rest (design.md: "it draws nothing when there is nothing to
  show"). In the owner's real log the mod itself has produced 3 visible moments in 80 events
  (`Counter({'learn': 77, 'reuse': 2, 'guard': 1})`), so most sessions show nothing at all.
- `reuseJudged` returns `''` with no note on three paths (register.ts:677, 690): the user
  sees `⣻ compound checking for reusable work` and then a blank row — indistinguishable from
  a failure.
- `compound install` ends with `Check it with: <cli> status` (bin/compound:2687); nothing tells
  the user what they will see in a session or that `/compound` exists.

**Change.**
(a) Once per session, at the first typed prompt (use the existing `firstTime` claim, as
`unsettled` does), a note that fades on the normal 8 s schedule:

```
◇ compound ready · 34 lessons · 7 guards · /compound for the dashboard
```

The counts come from the inventory `reuseJudged` already reads under `BUDGET.prompt`
(register.ts:670), so no extra CLI call and nothing on a tool-call path. For a prompt shorter
than `promptMinChars` (no inventory read) show the line without counts.
(b) A dim, short-lived close to the reuse spinner: `◇ compound nothing to reuse` drawn
straight into the `dim` phase (3 s). It uses the existing fade timer; no new timer.
(c) One more line at the end of `install`: `In a session: /compound opens the dashboard; a row above the prompt shows what compound is doing.`

**Files.** `hooks/view.ts` (two `NOTES` kinds, a start-in-dim option on `noted`),
`hooks/register.ts`, `types/index.d.ts` (`CompoundNoteKind`), `bin/compound` (install text),
`docs/design.md` band table, `ui.test.ts`.

**Not verified.** Whether (b) is welcome or noise on every substantial prompt is a taste call
for the owner; it could sit behind the existing `COMPOUND_QUIET`. I did not run a live session,
so I have not seen how a note painted during `prompt.submit` interleaves with the engine's own
spinner row.

---

### 4. The pane is read-only: no drill-down, and nothing in "Open" can be acted on  (M-L)

**Observed.** The pane's only controls are (register.ts:1295-1296)
`h(Button, { key: 'refresh', label: 'Refresh', hotkey: 'r', ... })` and
`h(Button, { key: 'close', label: 'Close', hotkey: 'x', role: 'dismiss', ... })`.
Everything else is `Text`. "Most used" shows at most six names clipped to 28 cells
(view.ts:518-519: real row `patch-scripts-match-current…`), with no way to read the lesson.
"Open" rows are dim text (view.ts:491) while the text report carries the command that settles
each (`/compound:learn settle <id>`, bin/compound:3158). In `docs/media/demo-2-pane.png` the
buttons read `[ Refresh ]  [ Close ]` — the hotkeys `r` / `x` are not shown anywhere on the
pane; README mentions `r` only.

**Change.**
- Make each lesson row a `plain` Button (or one `Select`; both exist in this build's element
  table) whose press reads `compound show <name> --json` and swaps the pane to a detail view:
  description, match patterns, counts, last used, path, body; `b` goes back. The read happens
  in an `onPress`, i.e. on no tool-call path, under `BUDGET.command`; the result goes into
  `$.state` and the render hook draws from it, as the rule requires.
- Add a "Lessons" view (`l`) listing all, not only the six used; `g` filters guards.
- Under "Open", print the settling command on the row, as the CLI does.
- Footer hint, dim: `r refresh · l lessons · x close` (labels alone do not reveal hotkeys on
  the terminal per the screenshot).

```
Most used  ◆ reused  ■ guarded  ↺ recalled
› patch-scripts-match-current-text   ◆ ▇ 1   ■ 0   ↺ 0
  zsh-equals-word                    ◆ 0     ■ ▇ 1 ↺ 0
                                                     enter read · l all lessons · r refresh · x close
```

**Files.** `hooks/register.ts` (pane render hook, a `DETAIL`/`VIEW` atom), `hooks/view.ts`
(`detailLines`, `lessonLines`), `types/index.d.ts`, `ui.test.ts`, `docs/design.md`, README.

**Not verified.** I read that `Select` and `plain` Buttons exist and that "Tab and the arrows
walk its buttons" in a focused pane (reference.md:105); I did not build it, so focus behaviour
with ~12 row-buttons, and whether the inline (non-fullscreen) placement at `PANE_ROWS = 34`
scrolls acceptably, is untested.

---

### 5. One vocabulary across the six surfaces; retire the jargon  (M)

**Observed.** The same thing has different names by surface, and several are internal terms.

| Concept | Band | Status entry | Pane | CLI |
|-|-|-|-|-|
| fix captured, lesson not written | `lesson owed` | `lesson owed` | Open: `lesson owed`; Recent: `capture` | `unsettled` |
| earlier sessions' debts | `unsettled from earlier sessions · 2 lessons owed` (register.ts:656) | `2 unsettled` (655) | `lessons owed` | `unsettled` |
| ineffective lesson | `strengthening owed` (view.ts:51) | `strengthen <name>` | `ineffective lesson` | `ineffective` |
| the three counters | – | – | `reused / guarded / recalled` | status: `reuse  guard  recall`; list: `USE/GRD/RCL` |
| per-level counts | – | – | `Levels` | `Store` |

- Pane Recent prints the raw event type, not the label the band uses (view.ts:537:
  `{ text: e.type.padEnd(8), color: look.color }`), so the user reads `capture`, `remind`,
  `refuse`, `nudge`, `skip` — log field values documented only in the CLI docstring.
- Guards are a subset of lessons (bin/compound:3049: `"guards": sum(1 for row in mine if row["match"])`;
  real store: 32 lessons of which 7 guards) but the pane sets them side by side as if
  disjoint. `docs/media/demo-2-pane.png`, after ONE lesson was recorded:
  `user   1 lesson   1 guard   0 skills`.
- Toast word order varies (render.ts:197-202): `lesson recorded: ${name}` /
  `lesson ${name} moved to the user level` / `lesson ${name} is now a skill` / `${name} removed`.

**Change.**
- Pick user words and use them everywhere: "to record" (for owed/unsettled/capture),
  "needs strengthening" (for ineffective/strengthening owed), "reused / stopped / recalled".
- Pane Recent: draw `look.label` shortened, not `e.type`:
  `09:52 ● fix found     python3 -c "import tomli…` / `09:52 ✔ recorded  python3-no-tomllib-use-tomli`.
- Levels: `user   32 lessons (7 guards)   4 skills`.
- Toasts: one shape, `<name>: <what happened>` — `zsh-equals-word: recorded`,
  `zsh-equals-word: moved to user level`, `zsh-equals-word: removed`.
- `compound list` header `USE/GRD/RCL` -> three columns named as in `status`; `Store` -> `Levels`.

**Files.** `hooks/view.ts`, `hooks/render.ts`, `hooks/register.ts` (status strings),
`bin/compound` (`cmd_status`, `cmd_list`), docs, and every test that asserts these strings.
The event `type` names in the log stay as they are (they are the contract); only what is
drawn changes.

**Not verified.** The exact replacement words are a naming decision for the owner; the
inconsistencies themselves are all quoted from code/output above.

---

### 6. Times: the pane shows HH:MM with no day; the CLI shows raw UTC  (S)

**Observed.** `clock()` (view.ts:437-442) prints hours and minutes only. Rendered from the
real log today, the newest-first timeline reads as if out of order, because rows from
yesterday carry no date:

```
Recent
  12:58 ◆ reuse    1 lesson or skill, 2 earlier requests
  02:50 ◆ reuse    1 lesson or skill
  22:50 ■ guard    zsh-equals-word
  22:50 ✔ learn    probe-reaches-rule-under-test
```

The CLI prints the stored UTC string plus a session-id column
(bin/compound:1255-1260), e.g.
`2026-10-04T16:58:04Z reuse    09f47a44 claude-skill-compoun speckit-execute` — 4 hours off
the pane's `12:58` for the same event, and the project name is cut at 20 characters
(`project[:20]`). The same report's Health section already uses relative time
(`2m ago (reuse)`), via `age_text()`.

**Change.** Relative age on both: `age_text` in the CLI (`2m ago`, `14h ago`, `3d ago`), the
same buckets in `view.ts` computed from `board.at`. Drop the session column from the text
report (keep it in `events`/`--json`), and stop truncating the project name when the
terminal has room.

```
Recent
   2m  ◆ reuse    speckit-execute                     claude-skill-compounder
  10h  ◆ reuse    patch-scripts-match-current-text    claude-skill-compounder
  14h  ■ guard    zsh-equals-word                     tmp.ylSPuSdkBm
```

**Files.** `hooks/view.ts` (`clock` -> `ago`, `boardLines`), `bin/compound` (`event_line`),
tests, docs.

**Not verified.** A relative age on the pane goes stale between refreshes (the pane redraws
only when its data is re-read); acceptable to me since the pane re-reads on every event, but
if not, print `Sat 22:50` for anything older than today instead.

---

### 7. CLI text output: no colour, not width-aware, signal buried  (M)

**Observed.**
- No colour and no terminal-width handling anywhere: grep of `bin/compound` for
  `\033|\x1b|NO_COLOR|get_terminal_size|columns` finds nothing; `isatty` is used for stdin
  only (1288, 1298). `PASS`/`WARN`/`FAIL` are plain text.
- `compound list` is 150 columns wide on the real store (measured); the WHEN column is cut at
  a fixed 70 characters mid-word regardless of the terminal (bin/compound:1583
  `row["description"][:70]`): `Use when a subagent's task notification says it stopped with backgroun`.
- `compound status` lists every lesson; 31 of 33 real rows are `0 0 0 never used`.
- `compound find` prints `[1/1 words]` (bin/compound:1712) — a score with no explanation —
  and whole multi-sentence descriptions on one line (the `cdl-bib-cite` row is 400+ chars).

**Change.** Standard library only, so it stays within the CLI's rule:
- Colour when `sys.stdout.isatty()` and `NO_COLOR` is unset: green/yellow/red on the Health
  status, the pane's three colours on the counters, dim for `never used`. `--json` unaffected.
- `shutil.get_terminal_size()` to size the last column of `list` and the summary of
  `event_line`, ending a cut with `…`.
- `status`: lessons with any use first, then one line `31 lessons never used (compound list shows them)`.
- `find`: `matched 1 of 1 words` or drop it when every word matched; clip the description to
  the terminal width.

```
Lessons
  name                              level  kind    reused  stopped  recalled
  patch-scripts-match-current-text  user   lesson  1       0        0
  zsh-equals-word                   user   guard   0       1        0
  speckit-execute                   user   skill   1       0        0
  30 more never used · compound list shows all
```

**Files.** `bin/compound` (`table`, `cmd_status`, `cmd_list`, `cmd_find`, `event_line`),
`tests/test_*.py`, `docs/design.md`.

**Not verified.** `/compound status` returns this same text into the transcript
(register.ts:1170-1172) through a spawned process, so `isatty()` will be false there and it
stays uncoloured — I believe that is the right outcome but did not run it in a session.
Whether any test or the mod parses the text form of `status`/`list` (rather than `--json`)
I did not exhaustively check; the mod's calls I read all pass `--json`.

---

## Bugs (separate from the proposals)

1. **Stray `…` on every "Most used" row at mid widths.** Rendered at 60 columns:
   `  patch-scripts-match-c…  ◆ ▇ 1        ■ 0          ↺ 0    …`.
   Cause: view.ts:518 budgets each counter cell as `BAR_CELLS + 6` = 12, but a cell is 13
   wide (`'  ◆ '` is 4, then `padEnd(BAR_CELLS + 3 ...)` is 9), and the last cell's trailing
   pad is then clipped by `fit()`, which appends `…` to cut whitespace. Fix: budget
   `3 * (BAR_CELLS + 7)` and do not pad the last cell (or have `fit` drop trailing spaces
   rather than ellipsize them).
2. **`candidate` rows are misaligned in Recent.** view.ts:537 pads the type with
   `padEnd(8)`; `candidate` is 9 characters. Rendered:
   ```
     19:00 ✔ learn    x
     19:00 ⇡ candidate x in y
   ```
3. **Recent has no date** (proposal 6): rows from different days are indistinguishable and
   look out of order. Rendered output quoted above.
4. **Levels double-counts a guard as a lesson and a guard** (proposal 5):
   `user   1 lesson   1 guard` in `docs/media/demo-2-pane.png` for a single recorded lesson.
5. **Narrow pane truncates its own fixed labels.** At 40 columns the Levels rows render
   `  user      32 lessons   7 guards   4 s…` and the legend `↺ recal…`; the third counter
   column is cut off entirely (`↺ ` with no number). `boardLines` has no narrow layout; only
   `fit()` clipping. The pane floor is 24 columns (register.ts:1285).
6. **"lesson or skill" may be said of a script** — unconfirmed. `reuseText` (view.ts:322)
   says `lesson or skill`, but README's reuse example lists
   `script scripts/bibdupcheck.py (project)` among the items offered, and the event docstring
   says "a script's name is its path relative to the project". I did not reproduce a reuse
   hit on a script. Proposal 1 (naming the item) removes the wording.

## What I looked at and found fine

- The band's width cascade works as documented at 120/80/50/30 columns (track loses words,
  then marks, then track, then the name is clipped).
- Glyphs are single-cell and distinct in the four screenshots; colour use on the band is
  consistent with the table in design.md.
- The fade timing and the one-timer rule: nothing proposed above adds a timer or a CLI read
  before a tool call, except the optional guard ordinal in proposal 2, which is flagged.
