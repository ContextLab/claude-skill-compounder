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
states, and the six prompts were re-run: 3/3 must-fire and 3/3 must-not-fire, sonnet, CLI
2.1.245. The pin in `SKILL.md` records that run, not the one before it.
