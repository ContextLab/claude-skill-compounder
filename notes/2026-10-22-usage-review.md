# 2026-10-22: usage review and evidence-driven fixes

Asked: look at how the tool has been used, what works, what is broken, what can improve;
fix from the data, update the local install, push when tested.

## Sources
- ~/.claude/compound/events.jsonl: 5342 events, 951 sessions, 3 to 22 Oct.
- ~/.claude/compound/evidence: 1178 snapshots.
- Transcripts under ~/.claude/projects, to rebuild the fix judge's call pairs (1013 of 1053
  Bash fix-judge events paired; the pairing is a heuristic).
- `compound status`, `compound report`.

## What works
- Guards: 262 refusals, 91% followed by a different call (the session took the advice).
- The index is shown to 497 sessions; reuse offers 62, with 35 earlier requests.
- Errors are rare (35) and mostly a judge outage on one day and a loaded machine on another.

## What is broken (measured)
1. Pattern guards refuse once per session per lesson. 124 of 206 recalls after a lesson's own
   refusal were calls its pattern matches (zsh-equals-word 54/57, macos-no-timeout 21/25,
   zsh-nomatch-glob 34/86). A refused call sent again unchanged: 16/256 (6.2%).
2. The glob probe stops reading at a cd it cannot follow and reads only the cwd and project.
   29 glob failures since the probe shipped; 8 option-shaped (`--include=*.py`) after such a
   cd, several in the harness's per-user temp directory.
3. Subagent scripts owe decisions at the main loop's stop. 112 of 125 declined scripts were
   subagent-only (107 from one subagent); 1 of 5 recorded scripts was subagent-only (6 passes).
   84 of the 112 passed fewer than 6 times.
4. Recall repeats. 233 of 430 recalls repeat lesson and error line in the same session (one
   session in project S: 115 for one lesson, mostly refusals that do not mention git, i.e. a
   loose match). Each costs a judge call and three CLI calls before the result returns.
5. The fix judge blocks results. 1121 calls, median 2443 ms, p90 4250 ms, 96% "none".
   A word-overlap prefilter (`resembles`) would drop 40% of the "none" calls but also 8 of 24
   "fix" answers in the reconstructed pairs, so it was not used; the judge moves off the path.

## Not acted on
- Reuse judge at each prompt: 1021 calls, 5.6% named; whether an offer was used is not logged.
- Eight lessons flagged ineffective (status, Open): user data, for the learn loop.

## Work
- CLI agent: fixes 2 and 3. Mod agent: fixes 1, 4, 5 (in that order).

## Resumed (same day)
- A fresh reviewer read the diff and found four bugs, all fixed:
  1. a failure whose own call passed stayed held until its judge answered, so later
     successes each started a judge (test added; it fails without the fix);
  2. the stop handed out finished judges of the main loop only; now of every loop;
  3. `errorKey` folded every path, so different failures shared a key; paths are kept,
     digits folded, and the word after `no matches found:` dropped as the CLI's signature does;
  4. the probe followed nothing about `pushd`, `builtin cd`, `command cd` and bare `cd`; they
     are now unfollowable (`command cd` runs /usr/bin/cd in a child, so it is a left-alone case).
- design.md passages that still said "once per session per lesson" now describe the override.
- Left as it was, open for the user: `recall_verdict` still leaves every recall after a
  refusal out of the ineffective count. Counting the ones the pattern missed would flag
  lessons whose misses the pattern cannot reach (zsh-nomatch-glob's are outside the probe's
  roots), which would ask for rewrites that cannot help.

## Pull requests and issues (same day)
- PR 45 (`proposal-ships-the-working-fix` into the general pool): merged into main from a
  scratch worktree; it applied cleanly, all checks green. Never recalled or offered since
  10 Oct, but sound and small.
- PR 44 (in-flight check as a mod Stop hook): closed. The script has a 45 s budget and makes
  `gh` network calls at every stop (the rule is 2 s); its waiter test sees only `sleep N`
  loops, so `wait-for-ci.py` does not count; 35 commits behind; the same script is already a
  Stop hook in the user's settings.
- Issue 19: closed. Repeat offer, skill, and `use` events form the whole loop (one project,
  13 Oct: repeat, then learn + skill; 6 uses since), and the shipped skills chain three deep.
- Issue 42: still blocked (fresh config dir: "Not logged in"; no credential in env).
  Status comment added; left open.
- Found on the way: `seed_event` accepted a log inside the checkout when the checkout itself
  is under /tmp (a scratch worktree), so a test wrote REPO/events.jsonl. Fixed (b18f954).
- CI for 9f3044c: green on ubuntu and macos, 7m35s wall.
