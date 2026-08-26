# The routing gate: what the measurement is worth

`SKILL.md` step 7 carries the gate itself — the probe command, the hand-run, the cost, the
model rule, and what to change when a prompt loses. This file carries what would not fit
there: the evidence behind those rules, and this skill's own history as a worked example.

## Why the description is the lever

Routing is decided by the `description` alone. The body is not loaded when the router
chooses, so every rule about winning a prompt is a rule about that one field.

**Measured, 2026-08-25.** Changing `"Use before debugging logic"` to `"Use before any other
debugging step"` flipped a losing must-fire prompt to a winning one. Four words. That is the
whole reason a re-run after the last description edit is mandatory rather than advisory: an
edit that small moved a verdict, so any edit can.

## Why a pass expires

The same `"Use before debugging logic"` wording that *lost* must-fire 1 in the full
installed router on 2026-08-25 *wins* that prompt in a router holding only it and
`systematic-debugging`. One run each, so the number is not the point — the point is that the
verdict moved with the environment rather than with the sentence.

`stale-artifact-check` lost two of three must-fire prompts to
`superpowers:systematic-debugging`, a skill in a *different package*, including its own
verbatim example, to the very skill its prose carves out as the thing it hands off to.
Installing a plugin, or an upstream editing its own description, falsifies a claim here with
no commit here. Nothing static detects that day; only re-running the probe does.

## The pin, and how to mend it

`python3 scripts/routing_claims.py lint` fails until the recorded sha256 of the description
and of the prompt list match what is on disk. `python3 scripts/routing_claims.py pin <skill>`
prints the two hashes for a section as it currently stands — but printing them is not
measuring them. The repair for a broken pin is always to run
`scripts/probe_routing_claims.py` again and write the date, CLI version and result it
reports. Pasting a fresh hash into a pin re-certifies nothing and is the one move the pin
exists to make visible.

## This skill's own history, as a worked example

Two of `skill-compounder`'s three must-fire prompts were won by editing the description
rather than the prompt, both measured 2026-08-25:

- *"Before I write this deploy script, is there already something for it?"* fired nothing
  while the description said only "when starting a major implementation (to check for an
  existing skill first)". Quoting the question a user actually types — "is there already
  something for this?" — flipped it.
- *"The skill I just used told me to run it from the wrong directory."* fired nothing until
  the description named the situation as a user reports it ("told you the wrong thing", "to
  run from the wrong directory") instead of the abstract "a skill you invoked misfired".

The third direction is worth keeping too. *"That took four attempts to get the ordering
right, and we hit it last week too."*, with no subject named, produces clarifying questions
and no skill. That is correct behaviour rather than a miss: the threshold in section 2 wants
a concrete referent for both of its conditions, and a prompt supplying neither cannot be
assessed against it. The shipped must-fire prompt therefore names one.

**Shortening the description invalidates all of this.** On 2026-08-26 the description was cut
from 655 characters to 491 to bring it inside the 500-character budget `skill-authoring`
states, and the six prompts were re-run at `--runs 3`: 9/9 must-fire draws and 9/9
must-not-fire, sonnet, CLI 2.1.245.

**And then that same section, unedited, was probed twice more the same day.** Pass 2 scored
8/9 must-fire — *"The skill I just used told me to run it from the wrong directory."* fired
nothing at all on one of its three draws. Pass 3 scored 9/9 again. Nothing was installed,
edited or committed between the three passes; the description sha256 in the pin is the same
one for all of them. That prompt is therefore 8/9 over nine draws, and the pin says `partial`
and names it. Pass 3 coming back clean is not a repair, and pinning it alone would have been
the re-roll this file forbids two sections down.

## What the shipped prompt list does not try to catch

Habit 1 (check before implementing) has no reliable lexical hook in the general case:
"let's build the ingestion pipeline" contains nothing a `description` can match, so that
habit is carried by the `UserPromptSubmit` reminder hook and the `CLAUDE.md` stanza rather
than by routing. The second must-fire prompt is the exception, not a refutation — it voices
the check out loud, and the description quotes that situation language. It and the
misfire-repair prompt both fired nothing until the description named the situation in the
words a user types; the section above records what each edit changed.

## What one passing run establishes, and what it does not

**It establishes that the router chose this skill on that draw, on that machine, at that
moment. It establishes nothing about the next draw.** Routing has been measured
stochastic here: one unchanged description, probed three times, gave 3/3, then 1/3, then
2/3 — no edit anywhere between the runs. So a pin that records a binary `3/3` from a single
sample is reporting one draw as though it were a property, and the next session cannot tell
a real regression from the same variance coming up differently.

That is why the pin carries `runs: N` and a k/N count per prompt:

- `verified` — every prompt won every draw, over at least three runs. **Three runs is the
  floor for *detecting* variance, not the threshold that earns the word.** It is set there
  because two draws can disagree but cannot say which way, and because the observed spread
  (3/3, 1/3, 2/3) is wide enough that one draw is close to uninformative — three is the
  smallest N that can show a claim wobbling at all, which is a different job from proving
  it steady. Reaching N=3 clean licenses `verified` for that pass and nothing more; three
  passes at N=3 on this skill's own section, one unedited day, went 9/9, 8/9, 9/9.
- **A prompt at 2/3 has not passed. It has been shown unreliable.** A k/N below N is a
  positive finding about the claim, not a shortfall in the sampling, and it does not expire
  when a later pass comes back clean: the loss happened, on that description, on that
  machine. The section is `partial` from then until the *description* changes and the whole
  section is measured again.
- `partial` — some prompt won some draws and lost others. This is a real, reportable state
  and the honest one for a flaky claim; it is not a failure to be re-run until it passes.
  Name the prompt and its k/N, because *which* prompt is flaky is the finding.
- `unmeasured` — the probe could not run at all (`runs: 0`, `measured: never`).

**A `partial` pin is not licence to re-roll.** Re-running until a green appears and pinning
that is the same move as pasting a fresh hash into a broken pin: it certifies the draw, not
the claim. If a prompt splits, the description is what changes — the lever is the same one
the rest of this file is about — and then the whole section is measured again.
