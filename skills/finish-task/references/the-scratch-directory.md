# The scratch directory

Phase 0 step 4 makes one directory per finish. **Nothing in this skill removes it**, and this file
is the record of why — four consecutive rounds of cold review against four successive designs for
an ownership check, and two directories of real evidence destroyed along the way. Nothing here is a
step; the steps are in the body, and after 2026-09-01 there is no removal step to describe.

## What the creation side had to fix, and did

Until 2026-08-28 the body said `mktemp -d /tmp/finish-XXXXXX`. The reasoning was entirely about
*creation*: `mktemp` cannot hand two runs the same name, so two finishes cannot collide. Nothing in
it was about *destruction*, and destruction is where the shape failed.

`/tmp` is world-writable and shared by every process on the machine, and under that shape every
finish this machine had ever run left a directory named `finish-` plus six random characters.
Nothing in a name said which run owned it, how old it was, or whether the session that made it was
still running. So the only cleanup anyone could write from outside a single run was a cleanup on
the *prefix* — and that is what happened. While cold agents were running this skill, a live scratch
directory matching the prefix was deleted out from under a running session, destroying a full-suite
log, three routing-probe result files and three script backups. None of it was recoverable: nothing
under `/tmp` is tracked, stashed, or in any reflog.

It happened a second time while that repair was being built. The first version of the reproduction
ran `rm -rf /tmp/finish-*` against the real `/tmp` to *show* the hazard, and took a third directory
with it — one belonging to neither of the two finishes the script had created. That is the defect in
one line: the glob is the natural way to write the cleanup, and the glob cannot tell the difference.

Two of the three creation-side changes survive in the body and have produced no finding since:

- **`${TMPDIR:-/tmp}` rather than `/tmp`.** On macOS `TMPDIR` is a per-user directory under
  `/var/folders/`, so another user's sweeper does not reach it. Where `TMPDIR` is unset this falls
  back to `/tmp` and buys nothing. macOS `TMPDIR` ends in a slash, so `"${TMPDIR:-/tmp}/finish-…"`
  builds `…/T//finish-…`; the block strips it with `t="${t%/}"` first.
- **A timestamp and the PID in the name.** `finish-20260831-235459-20445-QbOTjb` says when it was
  made and by which process, so a human or an agent reading a directory listing can tell an
  hour-old abandoned run from a live one — the judgement the old names made impossible.

The third, a `FINISH-RECORD-PATH` ownership stamp, is the one that was cut.

## The stamp, and the four rounds it did not survive

Each round patched the previous design; the next round found the same defect at a new site. The
shape never changed: **the value that authorised deletion was satisfiable by a value this document
ships, so two runs could stamp the same string and one would be told it owned the other's
evidence.**

|round|the design|how a reader defeated it|
|-|-|-|
|1|a shared guessable `/tmp/finish-XXXXXX` prefix, removed with `rm -rf`|the glob matched a third directory|
|2|per-run name plus a `FINISH-RECORD-PATH` stamp; Phase 6 compared it|only `$d` was marked for retyping, so the check misdiagnosed the reader's **own** directory|
|3|both literals marked, and the refusal printed the stamp it found|the stamp was the example record path the document ships in four places, so two runs stamped the same string and one printed `OWN` over the other's evidence|
|4|`record=RETYPE-notes/…` behind a `case` refusing the literal|step 4 told the reader to delete the `RETYPE-` prefix, which restores the shipped literal exactly; two finishes did it and A's check printed `OWN: this finish's directory` on B's directory|

Round 4's instance is worth stating in full, because it is the one that closed the argument. The
round-3 text asserted, in this file, that **"no run can stamp a string this document ships"** — and
the block above it instructed the reader to produce exactly that string by deleting a prefix. The
document contradicted itself across two adjacent blocks, and following both as written reached the
`rm -rf` authorisation over another run's sweep log.

The structural reason is the same disease that killed the base ladder and the tree fingerprint
before it: **a self-issued stamp cannot prove ownership, because every scheme the document
describes is a scheme the document ships, and a reader who copy-pastes it satisfies the scheme.**
Enumerating the ways a reader might copy-paste is the same unclosable list as enumerating candidate
refs.

## The decision, and what it costs

**The skill stops deleting the scratch directory at all**: no stamp, no `OWN`/`REFUSE` check, no
`rm -rf`, and no `destructive-op-preflight` invocation at that site, because there is no longer a
destructive operation there to preflight. Phase 6 and Phase 7 end by *naming* where the directory
is, in the record and in the reply. Creation stays as it is.

The whole cost: **scratch directories accumulate under `$TMPDIR` until the OS reclaims them.** That
is it. Set against four review rounds in which a check authorised destroying another run's evidence
and two occasions on which it actually did, it is not a close call. A reader who wants the space
back deletes a directory themselves, outside this skill, where `destructive-op-preflight` fires on
its own trigger and enumerates what dies before anything does — which is also why that skill keeps
its citation in the body's "when this is the wrong skill" section while being invoked nowhere.

There is a second, quieter benefit. Everything in the directory is evidence: the sweep log Phase 3
redirects there, the two dispatch snapshots, the review packets. Phase 5 now writes its absolute
path into the record, so a person reading the record months later can still open the thing it
quotes. Under the old shape the directory was deleted in Phase 6, i.e. before anyone had read the
record at all.

## What this leaves unanswered, stated plainly

Nothing now tells you which of several `finish-*` directories under `$TMPDIR` is yours except its
timestamp and PID, and nothing stops the pile growing. That is deliberate: the alternative was a
check that has to be right about ownership, and four rounds say this document cannot write one that
is. If you need yours, it is the one whose absolute path is in the record.
