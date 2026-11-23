# Automatic `/insights` Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** compound starts a headless `claude -p /insights` by itself when one is due, turns what it finds into `insight` events, and shows them to later sessions as candidates to record or decline.

**Architecture:** Everything that reads `usage-data/`, the event log or the state file is in `bin/compound`, behind one new subcommand, `compound insights`. The mod makes one extra CLI call at a session's first prompt (`insights --start`) and reads findings from the `events --unsettled` reply it already asks for. Findings are quoted, inert reference material, never instructions.

**Tech Stack:** Python 3.9 standard library (`fcntl`, `html.parser`, `subprocess`, `hashlib`); TypeScript function hooks; `unittest` driving the real CLI; `claude plugin test`.

**Spec:** `notes/2026-11-21-insights-design.md`. Read it first: this plan gives names and order, the spec gives behaviour and the reasons.

## Global Constraints

- `bin/compound` stays one file, standard library only, Python 3.9.
- No mocks. A test writes real files and runs the real CLI (`tests/test_support.py`). No test runs `claude`.
- The mod never reads `usage-data/`, the state file or the event log. It calls the CLI.
- Tests never touch the real `~/.claude`: every test sets `COMPOUND_HOME`, `COMPOUND_CLAUDE_DIR` and `COMPOUND_NOW` as `test_support` does.
- A new `COMPOUND_*` name, subcommand, option or event type goes into `docs/design.md` in the task that adds it; `tests/test_docs.py` fails otherwise. The event-type words go in the CLI's word tables, the pane and the design together.
- A hook never breaks a turn: every new mod path is inside a `try` that ends in `fail($, ...)`.
- CLI calls from the mod take their budget from `BUDGET` in `hooks/render.ts` (`BUDGET.prompt`, 5 s, at a typed prompt).
- Fixture text in tests is invented. No text from a real session, no session ids from this machine, in any committed file.
- Values fixed by the spec: 7 days, 25 sessions, 900 s run limit, 3 findings a session, 3 distinct sessions shown, `UNSETTLED_DAYS` (14) window, `text` 600 / `goal` 200 / `why` 300 characters, `kinds` at most 8 of `^[a-z_]{1,40}$`, files over 1 000 000 bytes not read.
- Commit after each task with the trailers:
  `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01DcKtysga1X57Q3wzsFAsh9`.
- After each task: `./run_tests.sh`, `claude plugin validate --strict .`, `claude plugin test .`, all green, before the commit.

## Review Focus

1. `usage-data/` does not exist (the command was never run): `--harvest` exits 0 with zero findings and outcome `ok`, not `unreadable`. (Task 1)
2. `claude` is not on `PATH`: `--start` still answers within its budget, the run's outcome is `failed` with a message, one `error` event is written, and the next `--start` is not due for 7 days. (Task 3)
3. A facet that is not what was measured (an array, invalid UTF-8, 5 MB, `friction_counts` a string, `session_id` not the file's name): skipped and counted, the others still harvested. (Task 1)
4. A session started in a subdirectory of a repository, or through a symlinked path: its finding is listed for `--project <repository root>`. (Task 1, Task 2)
5. Finding text that holds `RECORDED-INSIGHT>>>`, `<<<RECORDED-INSIGHT`, a look-alike with other hyphens, or a line starting `[compound]`: shown inert, the block still closes once. (Task 4)

## File Structure

| File | Change |
|-|-|
| `bin/compound` | `insight` event type; `cmd_insights` and its helpers; `events --unsettled` rows; `check_settles`, `settled_by`, `cmd_add` level rule; `cmd_status` rows; docstring sections EVENT LOG and a new INSIGHTS |
| `tests/test_insights.py` | new: harvest, due, lock, start, run without `claude` |
| `tests/test_settle.py`, `tests/test_events.py`, `tests/test_status.py` | cases for findings |
| `tests/test_support.py` | `CLI_TYPES` gains `insight`; a helper that writes a `usage-data/` tree |
| `hooks/store.ts`, `hooks/store.test.ts` | `Insight`, `parseInsights` |
| `hooks/render.ts`, `hooks/render.test.ts`, `hooks/security.test.ts` | `insightContext`, `INSIGHT_RULE`, `inert` learns the marker |
| `hooks/register.ts`, `hooks/learn.test.ts` | the reminder shows findings; the `--start` call |
| `hooks/view.ts`, `hooks/view.test.ts`, `types/index.d.ts` | the band's note and the pane's Open rows |
| `docs/design.md`, `docs/guide.md`, `README.md`, `CONTRIBUTING.md` | the behaviour, the two variables, the subcommand, the journey |
| `tests/journeys/journey_insights.py` | new: the real run, by hand |

---

### Task 1: The `insight` event and the harvest

**Files:**
- Modify: `bin/compound` (docstring; `EVENT_TYPES`, `CLI_WRITES`, the word and colour tables near line 823; new helpers and `cmd_insights`; parser)
- Modify: `tests/test_support.py` (`CLI_TYPES`; `write_usage_data`)
- Create: `tests/test_insights.py`
- Modify: `docs/design.md` (CLI contract row, event table row, Words row, a section "Findings from /insights")

**Interfaces:**
- Produces, in `bin/compound`:
  - `insights_claude_dir() -> str`: `COMPOUND_CLAUDE_DIR`, else `CLAUDE_CONFIG_DIR`, else `~/.claude`, absolute.
  - `insight_id(source: str, key: str) -> str`: `"in-" + sha256(source + "\0" + key).hexdigest()[:16]`.
  - `harvest_insights(events: list, clock: float) -> dict`: `{"new": [event, ...], "facets": n, "skipped": n, "dropped": n, "report": n, "outcome": "ok"|"unreadable", "message": str}`. Pure reading; appends nothing.
  - `insights_lock(wait: bool)`: a context manager over `fcntl.flock` on `<COMPOUND_HOME>/insights.lock`; yields `True` when held, `False` when `wait` is false and it is held elsewhere.
  - `read_insights_state() -> dict`, `write_insights_state(state: dict) -> None` for `<COMPOUND_HOME>/insights.json` (atomic replace; `message` masked with `masked`).
  - `compound insights --harvest [--json]` and `compound insights [--json]`.
  - `insight` events with fields `id`, `source` (`facet`|`report`), `session` (`"insights"`), and for a facet `of`, `project`, `kinds`, `text`, `goal`, `learned`; for a report item `text`, `why`, and no `project`.
- Produces, in `tests/test_support.py`: `write_usage_data(claude_dir, facets: dict, meta: dict, report_items: list) -> str` writing `usage-data/facets/<id>.json`, `usage-data/session-meta/<id>.json` and a `report.html` whose items are `<div class="claude-md-item"><code class="cmd-code">TEXT</code><div class="cmd-why">WHY</div></div>` inside a `<section id="section-features">`.

- [ ] **Step 1: Write the failing tests** in `tests/test_insights.py` (class `HarvestTest`), each driving `compound insights --harvest --json` in a sandbox:
  - `test_a_facet_with_friction_becomes_one_event_in_its_project`: one facet with `friction_detail` "x", `friction_counts {"wrong_approach": 2}`, meta `project_path` = a temp git repository; assert one `insight` event, `source == "facet"`, `project == realpath(repo)`, `kinds == ["wrong_approach"]`, `session == "insights"`, `id` matches `^in-[0-9a-f]{16}$`.
  - `test_harvesting_twice_writes_nothing_twice`.
  - `test_a_facet_without_friction_detail_is_not_a_finding`.
  - `test_a_session_started_in_a_subdirectory_lands_at_the_repository_root` (Review Focus 4; also a symlinked path).
  - `test_a_facet_whose_project_is_gone_or_has_no_metadata_is_dropped` (`dropped == 2`).
  - `test_learned_names_the_lessons_that_session_wrote`: `seed_event` a `learn` for the facet's session with `lesson: "a-lesson"`; assert `learned == ["a-lesson"]` and the finding is still written.
  - `test_malformed_facets_are_skipped_and_the_rest_harvested` (Review Focus 3: array, invalid UTF-8, a 1 000 001-byte file, `friction_counts` a string, `session_id` unlike the file name; `skipped == 5`, one good finding).
  - `test_every_facet_malformed_is_unreadable_and_offers_nothing`: outcome `unreadable`, no `insight` event, one `error` event naming the file and key.
  - `test_kinds_keep_only_slugs_and_at_most_eight`.
  - `test_text_is_one_line_masked_and_cut`: a `friction_detail` of 700 characters with a newline and `password=hunter2secret`; assert `len(text) <= 600`, no newline, the secret absent.
  - `test_report_items_become_findings_without_a_project_once`: two items; harvest twice; two events, `source == "report"`, no `project` key, `why` set.
  - `test_a_report_with_the_section_and_no_parsable_item_is_unreadable`.
  - `test_no_usage_data_directory_is_ok_and_empty` (Review Focus 1).
  - `test_compound_log_refuses_an_insight_event`: `compound log` with `{"type": "insight"}` exits 2.
  - `test_the_state_command_prints_the_last_outcome`.
- [ ] **Step 2:** Run `python3 tests/test_insights.py`. Expected: every test fails, `insights` is not a subcommand.
- [ ] **Step 3: Implement.** Add `insight` to `EVENT_TYPES` and `CLI_WRITES` (value `"insights"`), its word (`insight`) and colour (DIM) to the tables, and `insight` to `CLI_TYPES` in `test_support.py`. Write the helpers above and `cmd_insights(args)`; register the subcommand with `--harvest`, `--start`, `--run`, `--json` (the last two answer `usage` until Task 3). Rules the signatures do not settle:
  - A facet's project: `git -C <project_path> rev-parse --show-toplevel` when that works, else the directory; `os.path.realpath` of it. Reuse the CLI's existing way of asking git if one exists; do not add a second.
  - Report parsing: an `html.parser.HTMLParser` subclass collecting the text of `cmd-code` and `cmd-why` inside each `claude-md-item`. "Has the section" means an element with a class `claude-md-item` or the id `section-features` was seen.
  - `--harvest` holds `insights_lock(wait=True)` from reading the log to the last `append_event`, validates everything first, appends second, then writes the state file (`harvested` counts; `outcome`; `finished`).
  - A report finding's key for `insight_id` is its text lowercased with runs of whitespace made one space.
- [ ] **Step 4:** Run `python3 tests/test_insights.py`. Expected: OK.
- [ ] **Step 5: Document.** In `docs/design.md`: the `compound insights` row of the CLI contract with all four forms, the `insight` row of the event table, its Words row, and the section "Findings from /insights" covering the harvest (from the spec's "The harvest"). In the docstring of `bin/compound`: `insight` in EVENT LOG and an INSIGHTS section with the file shapes read.
- [ ] **Step 6:** `./run_tests.sh && claude plugin validate --strict . && claude plugin test .` Expected: `OK: 29 test files` and both plugin commands pass.
- [ ] **Step 7: Commit** `insights: the insight event and the harvest of /insights output`.

### Task 2: Listing, showing and settling a finding

**Files:**
- Modify: `bin/compound` (`unsettled` neighbours near line 2408, `check_settles` 2442, `settled_by` 2381, `cmd_events` 5976, `cmd_add` 3982, `cmd_skip` 5888, `cmd_status` 6982, `cmd_insights`)
- Modify: `tests/test_settle.py`, `tests/test_events.py`, `tests/test_status.py`, `tests/test_insights.py`
- Modify: `docs/design.md` (the three states; `--settles` on `add` and `skip`; status Open)

**Interfaces:**
- Consumes: `insight` events and `insight_id` from Task 1.
- Produces:
  - `INSIGHT_SHOWN_SESSIONS = 3`.
  - `insight_state(event: dict, events: list, clock: float) -> str`: one of `"open"` (still listed for the reminder), `"quiet"` (shown to 3 distinct sessions, still settleable), `"settled"`, `"expired"`.
  - `events --unsettled [--project P] --json` also prints every `insight` whose state is `open`, each row carrying `type: "insight"` and its `id`. A row with no `project` passes the `--project` filter. `--session S` never selects one.
  - `remind` events may carry `insights: [id, ...]`; the showing count is the number of distinct `session` values of `remind` events naming the id.
  - `compound add --settles <finding id>` and `compound skip --settles <finding id>` write `settles: <id>`.
  - `compound insights --json` gains `findings: [{id, source, project, state, text}]`.

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_events.py`: `test_unsettled_lists_a_projects_findings_and_every_report_finding`; `test_unsettled_for_a_session_lists_no_finding`; `test_a_finding_named_by_reminds_of_three_sessions_is_no_longer_listed` (two `remind` events from one session count once); `test_a_finding_older_than_the_window_is_not_listed` (`COMPOUND_NOW` 15 days after the event).
  - `tests/test_settle.py`: `test_skip_settles_a_finding_by_id`; `test_add_settles_a_finding_by_id`; `test_a_finding_shown_three_times_can_still_be_settled`; `test_settles_refuses_an_expired_or_unknown_finding` (exit 2); `test_a_skip_aimed_at_a_finding_leaves_the_sessions_ineffective_recall_owed` (seed a `recall` with `ineffective: true` in the same session, skip the finding, assert `events --unsettled --session S` still lists the recall); `test_a_capture_is_not_settled_by_an_event_that_names_a_finding`; `test_add_refuses_a_report_finding_at_the_project_level` (exit 2, message names `--level user`) and `test_add_records_a_report_finding_at_the_user_level`.
  - `tests/test_status.py`: `test_open_lists_findings_and_the_last_insights_run`.
  - `tests/test_insights.py`: `test_the_state_command_lists_each_finding_with_its_state`.
- [ ] **Step 2:** Run the four files. Expected: the new tests fail.
- [ ] **Step 3: Implement.**
  - `settled_by(debt, event)`: when `event.settles` starts with `in-`, return `False` for every capture and recall debt. This is the first test in the function.
  - `check_settles(value, events)`: accept `value` when it is the id of an `insight` whose state is `open` or `quiet`; the capture path is unchanged. Its error message lists findings as well.
  - `settling`: unchanged for findings (a finding is never a session's own debt).
  - `cmd_add`: after the level is known, exit 2 when `--settles` names a `report` finding and the level is not `user`.
  - `cmd_events`: with `--unsettled`, append the `open` findings unless `--session` is given; let a row with no `project` through `--project`.
  - `cmd_status`: Open gains `findings`; the checks gain one informational row with the last run's `outcome` (never a failing check).
- [ ] **Step 4:** Run the four files. Expected: OK.
- [ ] **Step 5: Document** the three states, the user-level rule and the status rows in `docs/design.md`.
- [ ] **Step 6:** the full checks of Task 1 Step 6.
- [ ] **Step 7: Commit** `insights: findings are listed, shown out, expired and settled by id`.

### Task 3: When a run is due, the lock, `--start` and `--run`

**Files:**
- Modify: `bin/compound` (`cmd_insights`; the environment section of the docstring near line 503)
- Modify: `tests/test_insights.py`
- Modify: `docs/design.md` (Environment variables rows; "The CLI's time" table row for `insights --start`; README's settings table if it lists the cost knobs)

**Interfaces:**
- Consumes: `insights_lock`, `read_insights_state`, `write_insights_state`, `harvest_insights`, `insights_claude_dir` from Task 1.
- Produces:
  - `COMPOUND_INSIGHTS_DAYS` (default 7; `0` is off; not a whole number is the default) and `COMPOUND_INSIGHTS_MIN_SESSIONS` (default 25, minimum 1), read by the CLI only, resolved the way `COMPOUND_RECUR_LIMIT` is.
  - `INSIGHTS_TIMEOUT = 900`.
  - `insights_due(events: list, state: dict, clock: float) -> tuple`: `(due: bool, why: str)`; `why` is one of `off`, `disabled`, `too soon`, `too few sessions`, `due`.
  - `compound insights --start [--json]` prints `{"started": bool, "why": str}` and exits 0 in every case.
  - `compound insights --run` exits 0 when the run and the harvest finished, 1 otherwise.
  - State file gains `started` (epoch seconds) and `outcome: "running"`.

- [ ] **Step 1: Write the failing tests** (class `DueTest`, `StartTest`):
  - `test_not_due_with_fewer_than_25_sessions_in_the_log`, `test_due_with_25_sessions_and_no_earlier_run`, `test_not_due_within_7_days_of_a_start_whatever_its_outcome`, `test_due_after_7_days_and_25_new_sessions` (sessions before `started` do not count), `test_days_zero_turns_it_off`, `test_a_days_value_that_is_not_a_number_is_the_default`, `test_compound_off_is_never_due`.
  - `test_start_answers_false_while_the_lock_is_held`: the test process itself holds `fcntl.flock` on `insights.lock`; `--start` prints `started: false`; the state file is untouched.
  - `test_start_writes_started_before_the_worker_ends`: with 25 seeded sessions and `PATH` = `BASE_PATH` (no `claude`), `--start` prints `started: true`; the state file holds `started == NOW`; poll (deadline 20 s) until `outcome` is no longer `running`.
  - `test_without_claude_on_the_path_the_run_fails_and_says_so` (Review Focus 2): after the poll, `outcome == "failed"`, `message` mentions `claude`, the log has exactly one `error` event from it, and a second `--start` answers `too soon`.
  - `test_run_exits_when_the_lock_is_held`.
  - `test_run_harvests_what_is_already_there_only_after_a_successful_child`: with no `claude`, a prepared `usage-data/` yields no `insight` event.
  - `test_the_state_command_prints_the_claude_directory_it_reads`: `compound insights --json` prints `claude_dir` for the three cases (`COMPOUND_CLAUDE_DIR` set, only `CLAUDE_CONFIG_DIR` set, neither). What the child's environment holds is asserted by behaviour in the journey (Task 5), since no test runs `claude`.
- [ ] **Step 2:** Run `python3 tests/test_insights.py`. Expected: the new tests fail.
- [ ] **Step 3: Implement** as the spec's "One run at a time" and "The run" say. What the spec leaves open, decided here:
  - `--start`: `insights_lock(wait=False)`; under it, `insights_due`; write `started` and `outcome: "running"`; `subprocess.Popen([sys.executable, <this file>, "insights", "--run"], start_new_session=True, stdin/stdout/stderr = DEVNULL, close_fds=True)`; release. The lock file descriptor is not inherited.
  - `--run`: `insights_lock(wait=False)` for its whole life. Resolve `claude` with `shutil.which`; when it is missing, `outcome: "failed"`, `message: "claude was not found on PATH"`. Else `Popen(["claude", "-p", "/insights"], cwd=home_dir(), env=<caller's + COMPOUND_OFF=1 + CLAUDE_CONFIG_DIR when either directory variable was set>, start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=PIPE)`; `communicate(timeout=INSIGHTS_TIMEOUT)`; on timeout `os.killpg` the group with SIGTERM, then SIGKILL after 5 s, `outcome: "timeout"`. Success needs exit 0 and a `usage-data/report.html` whose mtime is at or after `started`. Then the harvest of Task 1, inside the same lock (factor the body of `--harvest` so it does not take the lock twice).
  - Every failed outcome writes one `error` event (`where: "insights.run"`), through the function the CLI already uses for its own errors.
  - `--run` when `started` is absent (a user ran it by hand) writes `started` itself.
- [ ] **Step 4:** Run `python3 tests/test_insights.py`. Expected: OK.
- [ ] **Step 5: Document** the two variables (table rows naming `CLI` as the reader), the due rule, the lock, the run, the cost sentence from the spec, and how to turn it off.
- [ ] **Step 6:** the full checks of Task 1 Step 6.
- [ ] **Step 7: Commit** `insights: a run starts when it is due, once at a time, with COMPOUND_OFF in the child`.

### Task 4: The mod shows findings and starts runs

**Files:**
- Modify: `hooks/store.ts`, `hooks/store.test.ts`
- Modify: `hooks/render.ts`, `hooks/render.test.ts`, `hooks/security.test.ts`
- Modify: `hooks/register.ts` (`unsettledReminder`, line 840), `hooks/learn.test.ts`
- Modify: `hooks/view.ts`, `hooks/view.test.ts`, `hooks/ui.test.ts`, `types/index.d.ts` as the band and pane need
- Modify: `docs/design.md` ("What an earlier session left unsettled", "How lesson text is presented", "Seeing it work", "The CLI's time")

**Interfaces:**
- Consumes: the `insight` rows of `compound events --unsettled --project P --json` (Task 2); `compound insights --start` (Task 3); `remind` events with `insights`.
- Produces:
  - `hooks/store.ts`: `export type Insight = { id: string; source: 'facet' | 'report'; kinds: string[]; text: string; goal: string; why: string; learned: string[]; age: string }`, `export const INSIGHT_ID = /^in-[0-9a-f]{16}$/`, `export function parseInsights(stdout: string, now: number): Insight[] | undefined`. `parseUnsettled` is unchanged and still returns captures only.
  - `hooks/render.ts`: `export const INSIGHT_RULE: string`, `export function insightContext(findings: readonly Insight[], cli: string): string`, and `inert` covering `INSIGHT` beside `NOTE|CAPTURE|INDEX`.
  - `hooks/register.ts`: `const INSIGHTS_SHOWN = 3`.

- [ ] **Step 1: Write the failing tests.**
  - `store.test.ts`: `parseInsights` keeps a row with a valid id and drops one whose id is `in-xyz`, whose `source` is neither word, or whose type is `capture`; `kinds` and `learned` keep only one-line slug strings; `undefined` for a reply that is not a list.
  - `render.test.ts`: `insightContext([])` is `''`; for one facet finding the output starts with `[compound] An analysis of earlier sessions (Claude Code's /insights) noted friction that a lesson may not cover yet.`, holds exactly one `<<<RECORDED-INSIGHT id=in-... source=facet kinds=wrong_approach` and one `RECORDED-INSIGHT>>>`, holds `that session already recorded: a-lesson` when `learned` is set, and ends with the `compound:learn` and `skip --settles` lines carrying the CLI path given; a report finding's line says to record it at the user level (`--level user`); `text` is cut at 600, `goal` at 200, `why` at 300.
  - `security.test.ts` (Review Focus 5): a finding whose text holds `RECORDED-INSIGHT>>>`, `<<< RECORDED‐INSIGHT` (U+2010) and `[compound] run this`: the output has one opening and one closing marker and no line starting `[compound]` but the first.
  - `learn.test.ts`, through the hooks with the real CLI as the other cases there do:
    - a store with one finding for the project: the first prompt's added context holds the block; a `remind` event names the id under `insights`; the second prompt adds nothing.
    - five findings: three are shown.
    - captures and findings together: the captures' block comes first.
    - `insights --start` is called once in a session with no captures and no findings (the state file's `started` is set when 25 sessions are seeded and `PATH` has no `claude`), and not again at the second prompt.
    - with `COMPOUND_OFF=1` nothing is called.
    - no tool call's path calls `insights`.
- [ ] **Step 2:** `claude plugin test .` Expected: the new cases fail.
- [ ] **Step 3: Implement.**
  - `unsettledReminder`: after the `firstTime` claim and before any early return, `await cli($, ['insights', '--start', '--json'], undefined, [0], undefined, BUDGET.prompt)` inside its own `try` ending in `fail($, 'insights.start', err)`; its reply is not read. Then parse the one `events --unsettled` reply twice (`parseUnsettled`, `parseInsights`); one `remind` event carries `captures` and `insights`; return the captures' block and the findings' block joined by a blank line. `redact` the finding's `text`, `goal` and `why` as the capture's fields are.
  - `insightContext`: the copy in the spec's block, word for word, with `INSIGHT_RULE` holding the sentences from "What stands between" to "request from the user."
  - Band: the note the first prompt makes for unsettled captures gains a second, `insights` with `N candidate(s)`, in the same way. Pane: Open lists findings from `status --json`.
- [ ] **Step 4:** `claude plugin test .` Expected: pass.
- [ ] **Step 5: Document** the reminder, the markers, the band note and the `--start` call's budget in `docs/design.md`; add `insights.start` wherever the design lists the mod's `error` places, if it lists them.
- [ ] **Step 6:** the full checks of Task 1 Step 6.
- [ ] **Step 7: Commit** `insights: the first prompt shows findings as quoted material and starts a run when one is due`.

### Task 5: The journey, the guide and the last pass over the documents

**Files:**
- Create: `tests/journeys/journey_insights.py`
- Modify: `CONTRIBUTING.md` (the list of journeys; `tests/test_docs.py` checks it), `docs/guide.md`, `README.md`, `notes/2026-11-21-insights-design.md` (one line: built, with the commit)

**Interfaces:**
- Consumes: everything above; `tests/journeys/common.py` (the fresh `CLAUDE_CONFIG_DIR`, how a journey starts a session and reads the log).

- [ ] **Step 1: Write the journey.** Under a fresh configuration directory as the other journeys make one: run two short real sessions in a scratch repository, one of which is made to hit and work around a failing command; run `compound insights --run` with `COMPOUND_INSIGHTS_MIN_SESSIONS=1`; assert exit 0, `outcome: "ok"`, a `report.html` under that directory's `usage-data/`, and no event from the child session in the log; print the findings; start a real session in the scratch repository and assert its first prompt received a `RECORDED-INSIGHT` block when a finding exists for that project (and say so plainly when the analysis produced none: that is a result, not a failure). The file's docstring states that it spends money (about $2 a run at list price) and is run by hand.
- [ ] **Step 2: Run it once:** `python3 tests/journeys/journey_insights.py`. Expected: its own pass line. Record the outcome and the cost in `notes/`.
- [ ] **Step 3: Documents.** `docs/guide.md`: `compound insights` with real output from Step 2 (invented project names). `README.md`: one paragraph under what the mod does without being asked, with the cost and `COMPOUND_INSIGHTS_DAYS=0`. Read `docs/design.md` once from the top for anything that still says the mod learns only from failures and scripts.
- [ ] **Step 4:** `./run_tests.sh && claude plugin validate --strict . && claude plugin test .` Expected: all pass.
- [ ] **Step 5: Commit** `insights: the journey, the guide and the README`.
