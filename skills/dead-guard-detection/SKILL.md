---
name: dead-guard-detection
description: "Use when a cap, limit, validation, early exit, or safety check is relied on but has never been OBSERVED firing; when changing a guard's threshold or condition produced no change ('lowered the cap and nothing happened', 'added a check, output identical'); or before trusting a guard at a shell/platform/tool boundary. Do NOT use for writing a new guard from scratch, for a guard already seen firing on a real input, or when a symptom already points at a specific bug elsewhere."
---

# Dead Guard Detection

A guard whose firing has never been observed is **unverified, not verified**. Reading
the code cannot settle it: a dead guard is usually correct in isolation, and what
defeats it lives at a boundary — the format of an upstream command's output, a regex
dialect, a quoting rule, a type coercion. The program behaves plausibly either way,
so no symptom points at the guard. The only proof of life is an observed firing.

**The seed observation:** if changing a guard's threshold or condition changes
nothing observable, the guard is not running. That observation — "I lowered the cap
and nothing happened" — is not noise to shrug off; it is a positive detection.
Turn it into a deliberate experiment:

## When to run this

- You are about to depend on a limit/cap/validation/precondition for correctness or
  safety, and you have never seen its fire-branch execute on a real input.
- You changed a guard (added it, tightened it, loosened it) and observed **no
  difference** in behavior.
- A guard sits downstream of another program's output (command substitution, a pipe,
  a parsed file), or its condition is a regex/pattern handed to an external tool.
- A "did anything happen?" check that always answers the same way.

Not needed when the guard's fire branch already shows up in real logs or a test
asserts on the fired behavior with real inputs.

## The procedure

The command fragments inside Steps 1-5 are illustrative: they show the shape of
each probe and how to read its result, but they reference programs you do not have.
The **Worked example (runnable)** after Step 5 is the reproducible fixture — it
builds everything it runs, and every command and output line in it was executed
verbatim in a fresh directory.

### Step 0 — Name the observable fire-effect

Before probing, write down what the world looks like when the guard fires: exact
message, exit code, file created, request refused. If the guard has no observable
fire-effect at all, the order is explicit: **instrument first, then mutate** — add
tracer-style markers to both branches (the technique of Step 2), and only then run
the Step 1 mutation probe, watching the marker instead of a message. An effect-free
guard can never be verified, and a mutation probe with nothing observable has
nothing to measure.

### Step 1 — Mutation probe: force the guard to a state that MUST change behavior

Change the guard's threshold or condition to a value that **cannot fail to alter
behavior on an input you control**, run the real program, and watch.

- **Threshold guard** (cap, limit, size, count): tighten to absurdity. A cap of `0`
  must refuse *every* input.

  ```
  $ CAP=0 ./capcheck.sh data/small.txt     # 3-line file, cap 0: MUST refuse
  processing data/small.txt                # exit 0 -- it did not. GUARD IS DEAD.
  ```

- **Condition guard** (pattern, match, predicate): swap the condition for one that
  must be true on a known input. For a grep-based guard, the pattern `.` matches any
  nonempty line:

  ```
  $ # original: if grep -q 'ERROR|CRITICAL' "$LOG" -- never fires on a log
  $ #           that visibly contains "ERROR: undefined symbol"
  $ # probe:    if grep -q '.' "$LOG"
  $ ./deploy.probe.sh build.log
  REFUSED: errors present in build.log     # exit 1 -- fires with '.'
  ```

Interpretation:

| Probe result | Meaning |
|-|-|
| Absurd threshold changes nothing | Guard is dead. Go to Step 3/4. |
| Always-true condition fires, real condition never does on a should-fire input | Wiring is live; the **condition** is dead. Go to Step 3/4. |
| Probe fires as forced | Guard is reachable. Still confirm both branches (Step 2). |

**Never leave the mutation behind — probe so that nothing needs reverting.** When
the threshold is externally settable (env var, flag, config), mutate through that
knob for one run (`CAP=0 ./capcheck.sh ...` above) and the original is never
touched. When the condition lives in the code, copy the program, edit the copy, and
run the copy (`deploy.probe.sh` above) — the original stays untouched and there is
nothing to revert. Only edit the real file in place as a last resort, and revert it
immediately after reading the result. The probe is a measurement, not a fix.

### Step 2 — Tracer probe: observe both branches

Put an unmissable side effect (a stderr line or a marker file) inside the guard's
**fire branch AND its pass branch** — a fall-through pass branch counts as a branch
and gets a marker too. Run real inputs and confirm which marker appears.

```
TRACER: guard PASSED (fell through)      # on a should-pass input
TRACER: guard FIRED                      # on a should-fire input
```

A guard is verified only when you have seen the fire marker on a should-fire input
**and** the pass marker on a should-pass input. One branch observed = half verified.
If the fire marker is absent on a should-fire input, the guard is dead: proceed to
Step 3 to localise the defect and the Step 4 taxonomy to classify it.
Remove the tracers when done, or keep the fire-branch line permanently — a guard
that logs when it fires stays verifiable forever.

### Step 3 — Boundary-input realism: feed the guard what upstream REALLY produces

Never test a guard with a hand-typed stand-in for its input. The defect lives in the
difference between what you would type and what the real upstream command emits **on
this platform**. Capture the real value and diff it against your mental model:

```
$ hand="500"
$ real="$(wc -l < data/big.txt)"
$ printf 'hand-typed: [%s]\nreal wc:    [%s]\n' "$hand" "$real"
hand-typed: [500]
real wc:    [     500]                   # BSD wc pads with leading spaces
$ [[ "$real" =~ ^[0-9]+$ ]] || echo 'real output FAILS the validation'
real output FAILS the validation
```

Inspect the actual bytes when in doubt. `od -c` is portable; BSD `cat` rejects
`-A` (`cat: illegal option -- A`, verified here) and spells it `cat -vet`, which
printed `     500$` on the same input:

```
$ wc -l < data/big.txt | od -c | head -2
0000000                        5   0   0  \n
```

Same rule for the tools themselves: probe the **exact binary the program resolves**,
not the one you assume. (`grep` on PATH here was ugrep 7.8.4; `/usr/bin/grep` was
BSD grep 2.6.0 — both treated `|` as literal in this probe, but only running them
proves it.) Test a suspect condition directly against that tool:

```
$ printf 'ERROR: undefined symbol\n' | grep -c 'ERROR|CRITICAL'
0                                        # | is a LITERAL in BRE: never matches
$ printf 'weird line ERROR|CRITICAL literally\n' | grep -c 'ERROR|CRITICAL'
1                                        # what does match: the literal 12 chars
$ printf 'ERROR: undefined symbol\n' | grep -Ec 'ERROR|CRITICAL'
1                                        # same pattern, ERE: matches
```

### Step 4 — Boundary defect taxonomy

Once the mutation probe says "dead", check these boundaries — as a checklist of
where to look, **never** as a substitute for probing. Each item below was reproduced
on macOS/BSD before being listed:

1. **Whitespace / format drift across platforms.** BSD `wc -l` left-pads
   (`[     500]`); GNU does not. Strict validations (`^[0-9]+$`) then reject valid
   numbers. Normalize at the boundary — e.g. `n=$((n))` strips padding — rather than
   loosening the validation.
2. **Regex dialect.** In BRE (default `grep`, default `sed`), `|` is a literal
   character, so `grep 'foo|bar'` matches only the literal string `foo|bar`.
   Verified the same for `sed`: `sed -n '/ERROR|CRITICAL/p'` printed 0 lines on an
   ERROR line, `sed -nE` printed 1. Also: bash `[[ =~ ]]` is ERE, not PCRE —
   `[[ "5" =~ ^\d+$ ]]` does NOT match on macOS; `^[0-9]+$` does.
3. **Type coercion in comparisons.** `bash -c '[ "9" \> "10" ]'` is TRUE (string
   compare); `[ "9" -gt "10" ]` is false (numeric). A guard using the wrong operator
   fires on the wrong inputs. (zsh's `[` rejects `\>` outright — the same guard line
   can be dead in one shell and a syntax error in another.)
4. **Exit code vs output confusion.** `v=$(grep -c zzz log)` sets `v=0` AND exits
   nonzero — `grep -c` prints a count but its exit status reflects match/no-match,
   so `if v=$(grep -c ...)` takes the else branch even though `v` holds a usable 0.
   Decide whether the guard keys on output or on status, and test that one.
5. **Quoting and word-splitting.** An unquoted expansion inside the condition can
   glob or split before the test runs. Probe with an input containing spaces and `*`.

### Step 5 — Fix at the boundary, then RE-PROBE

A fix is verified the same way the defect was found. After fixing, re-run the
mutation probe (absurd threshold must now refuse) and the real inputs:

```
$ CAP=0 ./capcheck.fixed.sh data/small.txt
REFUSED: data/small.txt has 3 lines (cap 0)   # guard observed firing
$ ./capcheck.fixed.sh data/big.txt            # real config, cap 100
REFUSED: data/big.txt has 500 lines (cap 100)
$ ./capcheck.fixed.sh data/small.txt
processing data/small.txt                     # pass branch still passes
```

Both directions, both branches, real inputs. Anything less and you have replaced an
unverified guard with a different unverified guard.

### Worked example (runnable)

Every line below runs as printed, in an empty directory, on macOS/BSD with bash on
PATH. Outputs shown are real.

```
$ mkdir dead-guard-demo && cd dead-guard-demo
$ seq 1 500 > big.txt
$ printf 'a\nb\nc\n' > small.txt
$ cat > capcheck.sh <<'EOF'
#!/bin/bash
# refuse files longer than CAP lines
CAP="${CAP:-100}"
n=$(wc -l < "$1")
if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -gt "$CAP" ]; then
  echo "REFUSED: $1 has $n lines (cap $CAP)" >&2
  exit 1
fi
echo "processing $1"
EOF
$ chmod +x capcheck.sh
$ ./capcheck.sh big.txt              # 500 lines, cap 100: expect REFUSED
processing big.txt                   # it did not refuse -- suspicious
$ CAP=0 ./capcheck.sh small.txt      # mutation probe: cap 0 must refuse everything
processing small.txt                 # no change: GUARD IS DEAD
$ wc -l < big.txt | od -c | head -1  # inspect the real boundary bytes
0000000                        5   0   0  \n
$ sed -i.bak 's|n=$(wc -l < "$1")|n=$(wc -l < "$1"); n=$((n))|' capcheck.sh
$ CAP=0 ./capcheck.sh small.txt      # re-probe the fix
REFUSED: small.txt has 3 lines (cap 0)
$ ./capcheck.sh big.txt              # real config, both branches
REFUSED: big.txt has 500 lines (cap 100)
$ ./capcheck.sh small.txt
processing small.txt
```

## Habits that prevent the defect

- When you **write** a guard, fire it once on purpose before trusting it: run one
  input that must trip it and watch it trip. Thirty seconds now, or an autopsy later.
- Prefer guards that **announce themselves** when they fire (one stderr line). A
  silent guard cannot be distinguished from a dead one without re-probing.
- Treat "my change had no effect" as data, never as reassurance. Something you
  believe is connected is not.

## Limitations

What this procedure cannot reach, stated as measured or logically bounded:

- **A guard with no observable fire-effect** is outside both probes until one is
  added (Step 0's instrument-first rule). The procedure verifies effects; it cannot
  conjure one.
- **A guard you cannot vary** — no external knob, and source you may not edit or
  copy (a sealed binary) — is outside the mutation probe. What remains is
  input-side probing: feed an input that must trip the guard (the dirty build.log
  above is one). A no-fire result then proves the guard dead but not *why*;
  localizing the defect still needs the boundary inspection, which needs access to
  the code or its exact tools.
- **Every result is scoped to the platform and inputs probed.** The same `wc`-fed
  guard is dead where `wc` pads its output and would be live where it does not; a
  guard proven live here is not proven live elsewhere. All measurements in this
  skill were made on macOS/BSD (BSD wc, BSD grep, ugrep, bash 5.3); the GNU
  contrast ("GNU wc does not pad") is stated from GNU documentation and was NOT
  measured here.
- **Liveness is not correctness.** The probes prove the guard executes and its
  branches are reachable; a live cap set to the wrong number, or a live pattern
  matching the wrong lines, passes every probe here. Choosing the right threshold
  is a separate judgement.

## Trigger precision

<!-- routing-pin
description-sha256: 3653799e857cc471a782f1812e844d47c1bbc2515c9827316d52e370c75c28f1
prompts-sha256: fba35e85ddc6307c0ba79ef39191ead958c2eea7f2c7d3829a3d6086f232e3a1
measured: 2026-09-01
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: partial 8/9 must-fire draws, 9/9 must-not-fire draws over 3 runs; not clean: 'Before we ship, check that this size limit actually fires — I've never seen it reject anything.' 2/3 First measurement since promotion from ~/.claude/skills on 2026-09-01, where it was the only copy of a completed five-round forge. Same losing prompt as its 2026-08-28 measurement at CLI 2.1.250, so the split is reproducible rather than a one-day draw.
-->

Routing fixture: the router reads ONLY the frontmatter description, so judge each
prompt against the description alone — the body is not loaded at routing time.

Prompts that MUST fire this skill:

1. "I lowered the cap from 100 to 10 and nothing changed — the output is the same
   either way."
2. "Before we ship, check that this size limit actually fires — I've never seen it
   reject anything."
3. "This upload script has a max-file-size check that is supposed to reject huge
   files, but we have never once seen it reject anything — can you prove it
   actually runs?"

Prompts that must NOT fire this skill:

1. "The deploy check fired and blocked my release — help me get past it."
   (declined: the guard has already been seen firing on a real input)
2. "Write a rate limiter that caps requests to 100 per minute."
   (declined: writing a new guard from scratch — nothing existing is relied on)
3. "My tests crash with a NullPointerException in the JSON parser — help me track
   it down." (documented overlap: the symptom already points at a specific bug
   elsewhere; that territory belongs to a generic systematic-debugging skill)

Ordering note: the reading "my edit seems to have had no effect" belongs to
whatever skill verifies that the artifact you ran actually contains your edit (a
stale-artifact check), and that check runs FIRST — only once the artifact is known
current does the dead-guard question arise.
