# Four cold reviews, and the defect they all had

2026-09-01. Triggered by: *"build up the core skill pool to include at least 4 tried and
tested (and red-teamed via subagents) skills that are genuinely useful."*

## What was measured first, because it changed the plan

Before reviewing anything, an evidence audit asked which of the twelve shipped skills clear
"tried and tested AND red-teamed" today. **Strictly, none of them do.** Every skill fails at
least one of: a clean cold red-team round, genuine post-forge usage, a clean routing pin, a
test of its own.

Genuine usage, counted from the ledger with harness rows, unflagged probe directories
(`routing-probe-*`, `synthetic-probe-*`, `dgc-gate`) and forge-window tails all excluded:

|Skill|Genuine uses|Where|
|-|-|-|
|`skill-authoring`|15|claude-skill-compounder|
|`claim-provenance`|10|claude-skill-compounder|
|`ai-tell-audit`|5|claude-skill-compounder|
|`stale-artifact-check`|5|claude-skill-compounder|
|`skill-compounder`|4|**+ writing-style-guide**|
|`destructive-op-preflight`|2|claude-skill-compounder|
|`session-handoff`, `no-silent-stub`|1 each|claude-skill-compounder|
|`contribute-skill`, `parallel-agents-one-codebase`, `dead-guard-detection`, `finish-task`|**0**|—|

Two caveats that belong next to that table rather than under it. All four leaders are used
**only inside this package's own development**, so this is dogfooding rather than adoption;
`skill-compounder` holds the only cross-project invocation in the corpus. And a burst of
seven skills in nine minutes on 2026-08-26 traces to issue #15, a demo project built to
trigger each skill, where only two of nine routed on their own.

**The forge-tail pattern is systemic.** `finish-task`'s single non-harness invocation is 13
seconds after its own `done`; `dead-guard-detection`'s is 28. Both are the forging session
running what it had just built.

So the four with the most genuine use were reviewed, since they are the four with any claim
to "tried and tested" at all.

## The reviews

Four fresh agents, one per skill, each given **only its own skill file** and told to infer
the scenario, build a throwaway project, and execute the procedure end to end. None saw a
brief, a round record, this repository's history, or each other.

|Skill|Blocking|Reviewer verdict|
|-|-|-|
|`claim-provenance`|2|ship after fixing the sweep|
|`stale-artifact-check`|3|**would not ship as-is**|
|`skill-authoring`|2|**would not ship as-is**|
|`ai-tell-audit`|1, already disclosed|ship with `--skip=` fixed|

### The defect all four had

Six of the eight blocking findings are one shape: **a guard that reassures when it could not
actually make its check.**

- `stale-artifact-check` printed `CLEAN: your canary is gone` while the token was live.
- `stale-artifact-check` printed `CURRENT` where its own prose promised `UNDECIDABLE`.
- `stale-artifact-check` printed `ABSENT` for a live canary, whose documented reading is
  "discard every conclusion from previous runs".
- `skill-authoring` printed `not live` about a draft that was installed and reachable.
- `claim-provenance` hid a real claim and attributed a bogus one to the wrong file.
- Earlier the same day, `finish-task` did it twice more, in two different phases.

That is six instances across five skills in one day. The pool contains a skill whose entire
subject is this defect, `dead-guard-detection`, and the pool is full of them. A guard is not
verified by being read; it is verified by being watched to fire.

### The finding that reaches past these skills

**In an agent shell, `grep` is ugrep, and ugrep honours `.gitignore`.**

```
$ grep --version | head -1
ugrep 7.8.4 ...
$ grep -rn CANARY-... .        # dist/ is gitignored
$                              # nothing
$ /usr/bin/grep -rn CANARY-... .
./dist/built.js:1:CANARY-...
```

A gitignored build directory is exactly where a stale artifact survives a rebuild, so this
defeats the check precisely where it matters. `--no-ignore` is not a ugrep option. The
portable repair is to let `find` drive the walk so `grep` never recurses, plus `-H` because
a single-file batch otherwise prints no filename.

## What was fixed, and how each was verified

Every fix was verified by running the failure first and the repair after, never by reading.

|Fix|Verification|
|-|-|
|`claim-provenance` untracked sweep: `-z` / `xargs -0`|a claim in `docs notes/notes.md` went from silently dropped to reported|
|`claim-provenance` diff sweep carries the filename|two claims in two files went from bare `+` lines to `a.md:` / `b.md:`|
|`stale-artifact-check` Phase 4: `find` drives, `grep -H`|canary in gitignored `dist/` went from `CLEAN` to `YOUR CANARY IS STILL HERE`, exit 1; still `CLEAN` when genuinely gone|
|`stale-artifact-check` Phase 1: tree search, not `test -e`|`OBSERVED` where `test -e` said `ABSENT`|
|`stale-artifact-check` Phase 2 prose|now states the real behaviour and says to check `sys.prefix` first|
|`skill-authoring` Phase 5: all three roots|a draft in `./.claude/skills` went from `not live` to `cleared`|
|`skill-authoring` Phase 6: `python3 -B`|measured: `unittest discover` leaves two artifacts, `-B` leaves none|
|`ai-tell-audit` step 3|a bare `--skip=` is refused; the text now says to pass none when there are none|

**The `-B` fix caught its own author.** Running `shortlist.py` while fixing these left a
`__pycache__` inside `skills/ai-tell-audit/`, and that skill's own no-build-artifacts test
failed on it, minutes after the identical defect was written up in `skill-authoring`.

## What is still owed

- **A second cold read.** Under this repository's own protocol a fixed skill re-enters the
  loop and may not be called clean until a reviewer who saw the fixed version says so. These
  four have one documented cold round each and repairs; they do not yet have the confirming
  round.
- **Routing pins.** `ai-tell-audit` and `claim-provenance` are `partial`. Their descriptions
  were not touched here, so the pins remain valid as measurements and remain partial.
- **Usage outside this repository.** Nothing here changes that. Four skills with real use,
  all of it dogfooding, is what the ledger supports and all it supports.

---

# Round two: the confirming read, and what it caught in the repairs

Four more fresh agents, none a fork of round one, each given only the **fixed** skill and
told to exercise the paths that had failed. The protocol requires this: a repaired skill may
not be called clean until a reviewer who saw the repair says so.

**It found new blocking findings in all four, and three of them were introduced by the
round-one repairs.** That is the result worth recording, more than any individual bug.

|Skill|New blocking|Whose|
|-|-|-|
|`claim-provenance`|diff sweep named `docs/release` for `docs/release notes.md`|**mine** -- `substr($2,3)` splits on the space, the exact class I was repairing|
|`stale-artifact-check`|Phase 4 loop dies under zsh; `rm -f` clears the wrong directory|one pre-existing, one **mine** -- I moved the observe check to a tree search and left the clear shell-relative|
|`skill-authoring`|recovery block aborts on an unmatched glob under zsh; **empty `NAME` moved the skill roots themselves**|**both mine**|
|`ai-tell-audit`|indented-code exclusion misses RST literal blocks (16% denominator inflation); Unsourced precision would delete real measurements from good human prose|both pre-existing|

The `skill-authoring` one is the serious one. My round-one repair added a loop over three
roots and no guard on `NAME`, so `NAME=` made it `mv` `~/.claude/skills` itself into
`$TMPDIR`. A guard whose job is safe removal, made unsafe by the repair that was fixing a
different unsafety in it.

## What round two changed

|Fix|Verified by running|
|-|-|
|`claim-provenance` diff sweep: `substr($0,7)` + strip the trailing tab|`docs/release notes.md` now named whole; the path exists|
|`stale-artifact-check` Phase 4: `printf ... \| while read` instead of `for t in $others`|zsh ran 1 iteration and aborted before printing anything; now bash and zsh both print three orphans and `CLEAN`, exit 0|
|`stale-artifact-check` step 3: `find . -name TOKEN -delete`|clears the tree, not just the shell's directory|
|`skill-authoring` Phase 5: `[ -n "$NAME" ]` guard, two writable roots, no glob|empty NAME refuses with roots intact, under bash AND zsh; a draft in `./.claude/skills` is cleared; nothing live says `not live`|

The plugin cache was dropped from the recovery block deliberately: a draft you just wrote is
never in it, it is restored by the plugin manager, and globbing it is what aborted under zsh.
Phase 1 still sweeps it for discovery, which is a different question.

## Where this leaves the goal

**Not met, on the strict reading.** No skill here is clean after two rounds. What exists is
four skills with two documented cold rounds each, every blocking finding from round one
fixed and verified by running it, and round two's own findings fixed for three of the four.

Still open, and not fixed here:

- `ai-tell-audit`: the RST indented-code exclusion, and the Unsourced-precision family
  firing on real measurements in good human prose. Both need catalogue changes rather than a
  command fix, and both were reproduced against numpy's README.
- `skill-authoring`: `test_seed_<name>.py` is unrunnable for hyphenated names, so its own
  documented `discover` command reports `Ran 0 tests ... OK` -- coverage that reads green;
  and `create-agent-skills` in the plugin cache is a **full** overlap its own Phase 1 calls
  blocking, unnamed in its decline clause.

**The lesson worth keeping is the ratio.** Round one fixed eight blocking findings. Round two
found seven more, three of them created by round one. A repair is a change, and a change to a
guard is exactly the thing this repository's own doctrine says must be watched firing rather
than read. Every fix here was run; three were still wrong in a way only a cold reader
executing them could see.
