# Surfacing study: which way of showing a lesson makes a session use it

2026-10-11. Raw rows: `surfacing-runs.jsonl` (247 sessions, one row each). Scripts:
`surfacing/surfacing_experiment.py` (driver), `surfacing/d_advisory_hook.py` (option D
prototype), `surfacing/analyze.py` (every table below; `--dose` for the second).
Local-data rows: `followthrough.jsonl`, made by `mine_followthrough.py`.

## Answer

No single route worked. Three findings decide the design:

1. **A native skill (B) and a session-start index (C) both depend on the size of the
   list, and both have a hard cap.** With 5 entries the index was read in 8 of 9 sessions
   and a native skill invoked in 3 of 9 (small model) or 6 of 9 (larger model). With all
   122 lessons the native listing fell to 0 of 12 (small) and 4 of 9 (larger); the index,
   once over the 10,000 characters Claude Code passes on from a hook, fell to 0 of 21,
   because the session is given a 2,000-character preview of it and nothing else. The same
   index cut to fit under the cap (9,552 characters for 122 lessons) was read in 10 of 15.
2. **A tool-time advisory (D) is the only route that does not depend on list size and the
   only one that reached a lesson whose moment is the end of the turn** (surfaced 18 of
   18; the end-of-turn lesson changed the final message in 6 of 6 D sessions and in 2 of
   45 sessions under every other route). But it arrives beside the result of the call
   that triggered it, so for a lesson that says "run this script instead of doing it by
   hand" it arrived after the hand work was done: script run 0 of 6.
3. **Today's reuse check (A) cannot see a need that is not in the prompt's words.** 3 of
   the 5 task prompts never reached its judge (no candidate at the floor); it surfaced
   the lesson in 3 of 9 sessions on the three lessons that matter, 2 of 6 with the full
   store.

Recommended design, in the order the data supports it:

- **Tool-time advisory from recorded evidence, for every lesson** (the mod's `tool.call`
  hook already returns `context` beside a result; this is what recall does). Fire it as
  early as the evidence allows (the first call that names the lesson's files or commands),
  once per session per lesson. This is the only route for "after X, also do Y" and
  "before ending the turn" lessons.
- **A compact index at session start, held under 10,000 characters**, limited to lessons
  that carry a script or a procedure. It is the route that made sessions run a script
  instead of redoing the work (ci-checks 5 of 5 and docs 5 of 5 at 122 entries).
- **Native skill only by promotion, never by default.** The listing budget is already
  spent on this machine (below). Promote a lesson when it has been used, and expect a
  description that names an end-of-turn moment not to route at all (0 of 16).
- Keep the reuse check for what it is for (a build request that names existing work); it
  is not a surfacing mechanism for procedures.

Not tested, and the recommendation depends on it: the advisory with triggers for 100+
lessons (false activations), and all of this on the model the user's own sessions run.

## Hard limits (documented, then verified here)

Claude Code 2.1.296. Documentation: code.claude.com/docs/en/skills.md ("Skill descriptions
are cut short"), hooks.md, hooks-guide.md, plugins/mods/reference.md.

| Limit | Documented | Verified |
|-|-|-|
| Skill listing budget | "The budget scales at 1% of the model's context window"; `SLASH_COMMAND_TOOL_CHAR_BUDGET` sets a fixed count; setting `skillListingBudgetFraction` | 30,000 characters on a 1,000,000-token window (haiku, sonnet and opus aliases all report `contextWindow: 1000000`): debug log "Skill listing over budget: 746 skills, 121016 chars > 30000 budget". 8,000 on a 200,000-token window: a real session of 2026-10-04 logged "88 skills, 31207 chars > 8000 budget" |
| Per-skill description | "combined `description` and `when_to_use` text is truncated at 1,536 characters" | not tested |
| Over budget | "drops descriptions starting with the skills you invoke least"; names always stay | with the budget forced to 3,000, a session reported 12 entries with a description and 122 with a name only; both lesson-skills it was asked about were name only |
| Number of skills | none documented | 746 loaded without error |
| Hook output | "`additionalContext`, `systemMessage` ... and its plain stdout, are capped at 10,000 characters"; over it, a file and a 2,000-character preview | a 19,024-character SessionStart index reached the session as "Output too large (18.6KB) ... Preview (first 2KB)" |
| Skill body | loads on invocation, stays; after compaction "the first 5,000 tokens of each" | not tested |

What that means for 100+ lessons. The 122 lessons on this machine are 18,087 characters of
name and description (median description 105). The user's listing was already 31,207
characters with 88 skills on 2026-10-04, over the 30,000 budget before any lesson is
added (the listing this study's own session was given shows nine skills with a name and
no description). Making every lesson a native skill puts the listing near 50,000:
about 20,000 characters of descriptions are dropped, least-invoked first, and a lesson
that has never been invoked is first in line. On a 200,000-token model the budget is
8,000 and the lessons alone are more than twice that. A session-start index has room for
about 60 lessons at full description length, or 122 at about 50 characters each.

Hook points. Standard hooks: SessionStart and UserPromptSubmit stdout become context;
PostToolUse `hookSpecificOutput.additionalContext` is "placed next to the tool result"
and cannot stop the call. The mod API (`hooks/register.ts`): `session.start`,
`prompt.submit` (adds `context`), `skill.prompt`, `tool.call` (before and after the call;
the result takes `context`, which the recall moment uses), `ui.render`; the stop moment
is a classic Stop hook. The reference documents no way for `session.start` to add
context, so an index from the mod would go out with the first `prompt.submit`.

## Experiment

Real headless sessions on the journeys' kit: temporary `COMPOUND_HOME`,
`COMPOUND_CLAUDE_DIR` and project per session, this checkout as the plugin. Five real
lessons copied from the stores, each with a task whose need arises while working and a
control:

| lesson | task (the prompt names no lesson) | what counts as used |
|-|-|-|
| end-of-turn-inflight-check (script) | start a ten-minute job detached, note the command | `inflight-check.sh` run; also whether the final message says nobody is watching |
| ci-checks-for-commit (script) | "is HEAD releasable on GitHub", in a clone of pypa/packaging | `ci-checks.sh` run |
| docs-site: a project-level lesson about checking every page of a built docs site (script) | add a docs page with a table of contents, "make sure the result is right" | the lesson's checker script run; also whether `.. contents::` (furo's error box) is left in the page |
| verify-push-with-ls-remote | commit and publish, "be certain it is really there" | `git ls-remote` |
| kill-script-leaves-children | change a config and restart a running pipeline | old worker dead and new one alive |

Conditions: none (empty store); A (lessons in the store, reuse check); B (native project
skills made by `compound skill`); C (SessionStart hook prints names and descriptions and
says `compound show <name>`); C2 (C cut to fit 10,000 characters); D (PostToolUse hook,
triggers written from the commands each lesson's text names). B, C and D ran with the
reuse check off. "Surfaced" means the lesson's body reached the session.

Small model (`haiku`), 5 lessons listed, 3 sessions per cell, surfaced / used:

| lesson | none | A | B | C | D |
|-|-|-|-|-|-|
| inflight | 0, 0 | 0, 0 | 0, 0 | 2, 2 | 3, 2 |
| ci-checks | 0, 0 | 1, 1 | 3, 3 | 3, 3 | 3, 0 |
| docs-site | 0, 0 | 2, 2 | 0, 1 | 3, 3 | 3, 3 |
| ls-remote | 0, 2 | 0, 3 | 0, 3 | 2, 3 | 3, 2 |
| kill-children | 0, 3 | 0, 3 | 1, 3 | 3, 3 | 3, 3 |
| all (of 15) | 0, 5 | 3, 9 | 4, 10 | 13, 14 | 15, 10 |

Two of the five lessons are followed unaided (ls-remote 2 of 3, kill-children 3 of 3 with
an empty store), so they say nothing about use. The rest of this report is the other
three.

Three lessons, by model and by how many other real lessons were added (surfaced, used,
and surfaced per lesson as inflight / ci-checks / docs):

| model | others | cond | surfaced | used | per lesson | context chars, mean |
|-|-|-|-|-|-|-|
| haiku | 0 | none | 0/9 | 0/9 | 0/3, 0/3, 0/3 | 0 |
| haiku | 0 | A | 3/9 | 3/9 | 0/3, 1/3, 2/3 | 2201 |
| haiku | 0 | B | 3/9 | 4/9 | 0/3, 3/3, 0/3 | 948 |
| haiku | 0 | C | 8/9 | 8/9 | 2/3, 3/3, 3/3 | 2341 |
| haiku | 0 | D | 9/9 | 5/9 | 3/3, 3/3, 3/3 | 2172 |
| haiku | 20 | B | 2/6 | 2/6 | 0/2, 1/2, 1/2 | 3956 |
| haiku | 20 | C | 4/6 | 4/6 | 0/2, 2/2, 2/2 | 5021 |
| haiku | 50 | B | 3/6 | 3/6 | 0/2, 2/2, 1/2 | 9373 |
| haiku | 50 | C | 4/6 | 4/6 | 0/2, 2/2, 2/2 | 10221 |
| haiku | 117 | A | 2/6 | 2/6 | 0/2, 2/2, 0/2 | 758 |
| haiku | 117 | B | 0/12 | 0/12 | 0/4, 0/4, 0/4 | 18575 |
| haiku | 117 | C (over the cap) | 0/12 | 0/12 | 0/4, 0/4, 0/4 | 19290 |
| haiku | 117 | C2 | 6/9 | 6/9 | 0/3, 3/3, 3/3 | 12244 |
| sonnet | 0 | none | 0/3 | 0/3 | 0/1, 0/1, 0/1 | 0 |
| sonnet | 0 | A | 1/3 | 1/3 | 0/1, 0/1, 1/1 | 1009 |
| sonnet | 0 | B | 6/9 | 6/9 | 0/3, 3/3, 3/3 | 1273 |
| sonnet | 0 | C | 6/9 | 5/9 | 0/3, 3/3, 3/3 | 1956 |
| sonnet | 0 | D | 9/9 | 3/9 | 3/3, 3/3, 3/3 | 1977 |
| sonnet | 117 | B | 4/9 | 4/9 | 0/3, 3/3, 1/3 | 18993 |
| sonnet | 117 | C (over the cap) | 0/9 | 0/9 | 0/3, 0/3, 0/3 | 19425 |
| sonnet | 117 | C2 | 4/6 | 4/6 | 0/2, 2/2, 2/2 | 10061 |

Context characters: A is the reuse message (975 to 1,076) plus what the session then
printed; B is the listing (708 for 5 skills, 18,575 for 122) plus an invoked body; C is
the index (1,040 for 5; 9,552 cut; 19,024 uncut) plus what `show` printed; D is the
advisory (981 to 1,761 each). B and C are paid in every session, D and A only when they
fire. A also costs one model call before the turn starts: 27 judge calls in 38 A
sessions, median 2,550 ms.

Outcomes, not markers:

- Docs task, defect left in the page: none 4/4; B with 5 listed 2/3 (haiku) and 0/3
  (sonnet); B with 122 listed 4/4 and 2/3; C and D with 5 listed 0/12; C over the cap
  7/7; C2 0/5. The checker script found furo's error box every time it was run.
- End-of-turn task, final message says nobody is watching the job or names a waiter: D
  6/6; C with 5 listed 2/6 (haiku 2/3, sonnet 0/3); every other cell 0/43, the empty
  store included. The script itself: D 2/6 (haiku 2/3,
  sonnet 0/3).
- ci-checks under D: the advisory came beside the session's own `gh api .../check-runs`
  call, the session already had its answer, script run 0/6.

False activations (controls, haiku, 2 per cell, 10 per condition): the lesson's text
reached the session in A 0, B 0, C 0, D 4. The 4 are the two controls built to carry the
trigger command without the need (`git push --dry-run`; killing one stray process). On
tasks, D also delivered a second lesson's advisory in 12 of 24 sessions
(end-of-turn-inflight on any push or `&`, kill-children on the docs sessions' `pkill` of
their own http.server). B and C with 5 listed: no session in 30 opened another lesson. With 122
listed, 10 of 19 docs sessions under B, C and C2 opened a lesson about spelling conventions
(B 1, C 6, C2 3), a lesson whose description matches the prompt's words (writing docs).
That is a fair match for that lesson, and it shows what a listing is matched on: the
prompt, not the need that comes up later. Under the over-cap index it was also one of
the few entries inside the 2,000-character preview.

Cost: 247 measured sessions plus 23 smoke sessions and 8 budget probes; $6.71 for the
measured ones ($1.15 haiku, $5.55 sonnet), about $7.50 in all, 109 minutes of session
time. This is more sessions than the 60 to 100 asked for; the count grew to run the
list-size and second-model cells that the first results called for.

## Local data (8 days of real sessions)

From `mine_followthrough.py`; markers are regexes on Bash commands with here-document
bodies removed, so "situation arose" is a lower bound and "by hand" an upper bound.
Sixteen windows were read by hand.

Every run of an attached script happened in the session that wrote it. No later session
ran one.

| lesson | later sessions where the situation arose | surfaced | script run | by hand |
|-|-|-|-|-|
| ci-poll-in-background | 2 since the script (4 since the lesson) | 0 | 1, the authoring session | 1 (19 polling loops, written with `for`, which the guard's `until|while` pattern does not match) |
| ci-checks-for-commit | 5 (108 `gh pr checks` calls) | 2 | 0 | 5 |
| end-of-turn-inflight-check | 1, the authoring session | 0 | 0 | 1 |
| docs-site (the project-level lesson above) | 1, the authoring session | 0 | 1 | none later |

| native skill | sessions where the situation arose | reuse offers | invoked |
|-|-|-|-|
| a citation-filling skill | 2 projects | 4 in 3 sessions, 3 of them not fitting | 2 sessions, 8 calls |
| a duplicate-entry check skill | 3 | 0 | 2 |
| a skill about shortening a slow build or test loop | 2 | 1 | 0 |

`events.jsonl` holds 2 `use` events, not 6 (the citation-filling skill on 10-05, six seconds
after a reuse message named it; an unrelated skill on 10-10). Nine more Skill calls of the
first two skills in the table are in transcripts from before the log began: 5 unprompted by the model, 4 in
subagents whose prompt said to invoke the skill. No typed `/name`.

| plain lesson | sessions | surfaced | followed | by hand |
|-|-|-|-|-|
| verify-push-with-ls-remote | 10 (143 pushes) | 0 | 3 (12 pushes) | 7 sessions, 131 pushes |
| gh-actions-full-job-log | 3 | 1, after it had complied | 1 | 2 |
| kill-script-leaves-children | 2 (11 kills) | 1 | 3 kills | 8 kills |
| a project-level lesson about a release verification pipeline | 1 | 0 | n/a | the script was rewritten twice, the session noting that the earlier copy was gone |

The one lesson in this data that did get acted on mid-task is the one the user moved out
of the lesson system: four minutes after end-of-turn-inflight-check was recorded, the same
session made it a Stop hook, on the grounds that nothing in the lesson system forced it to run.

The native skills agree with the experiment: the two with a prompt-shaped trigger (a request
to add or cite a reference) are invoked unprompted; the one whose trigger is a moment inside
the work (a slow loop about to be run again) was never invoked.

## Red team

- **Do the prompts leak the lesson's words?** Measured with the CLI's own ranking
  (`find --request`): the target lesson is a candidate at the default floor for 2 of the
  5 tasks (ci-checks, weight 3.1 on "commit", "github", "push"; docs, 3.8 on "docs",
  "sphinx", "page", "contents") and not for the other 3. So the prompts favour A on those
  two, and A still surfaced them 3 of 6 times (the judge answered "not-substantial" twice
  for ci-checks and "nothing" once for docs). No prompt uses a lesson's name or its
  script's name.
- **Does it hold at 100+ entries?** No, and this is the main result: see the table. The
  5-entry cells overstate B and C. Between 25 and 55 entries C held (4/6 each) and B
  did not improve (2/6, 3/6).
- **Does always-listed text crowd out or mis-trigger?** Crowding: yes for B on the small
  model (3/9 to 0/12) and partly on the larger (6/9 to 4/9). Mis-trigger: rare for B
  and C (controls 0 of 20). D is the noisy one.
- **A leak in B.** In one B session the checker script was found by listing the project's
  `.claude/skills` directory without the skill being invoked; it is counted as used and
  not surfaced.
- **The plugin moved during the runs.** `bin/compound` and `hooks/register.ts` in this
  checkout were being edited by another worker (last changes 16:49 and 16:52) while
  sessions loaded them. No session logged a mod error (0 of 247), but condition A was
  measured against a moving reuse check.
- **Markers.** "Used" is a command pattern. A lesson printed in a shell loop was missed by
  the driver and is recounted in `analyze.py` (2 rows). The end-of-turn "told" measure is
  a regex on the final message.

## Uncertain

- Cells hold 2 to 4 sessions (9 to 12 when pooled over three lessons). Differences of one
  session mean nothing; the pooled contrasts (0/12 against 8/9; 0/21 against 10/15; D's
  0/6 against 6/6 by lesson type) are the ones to rely on.
- The user's sessions run a larger model than either tested here. The second model
  already behaved differently (native skills held up better at 122 entries; it never ran
  the end-of-turn script under any route). Opus was not run.
- Every session was one short prompt. Whether an index read at session start still acts
  on call 200 of a long session, or after a compaction, was not tested.
- D's triggers were written by hand from five lessons' text. Triggers derived from
  recorded evidence for 100+ lessons, and how often they fire wrongly, were not run. D
  before the call instead of beside its result (which could fix the 0/6) was not run.
- C from the mod (context on the first `prompt.submit`) was not run; the prototype is a
  standard SessionStart hook passed with `--settings`. Whether the mod route has the same
  10,000-character cap is unknown.
- B plus the reuse check together (today's real configuration for a promoted skill) was
  not run; B was measured alone.
- Three lessons carry the result. Two of the five chosen turned out to be things these
  models do unaided.

## Left behind by the runs

- One directory in the home directory: a first smoke session, told the clone would be deleted,
  copied the temporary project's `.claude` directory there (copies of five lessons and a
  settings.json). The prompt was changed afterwards. Removing it was refused by the
  permission system, so it is still there.
- Build output of the docs sessions, in directories under `/tmp`. Not removed, because
  some entries with similar names may be older and not from this study.
- About 200 directories under `~/.claude/projects/` named
  `-private-var-folders-...-compound-journey-surf-*`: the sessions' own transcripts, as
  every journey leaves them.
- Nothing was written to the real store or `~/.claude/skills`, nothing was committed.
