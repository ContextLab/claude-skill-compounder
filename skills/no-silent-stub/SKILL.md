---
name: no-silent-stub
description: "Use when about to hand back a value you did not actually compute: a hardcoded result, an empty collection standing in for logic, an `except: pass`, a mock on a live path, a TODO that returns, a test scored against its own input, or a fallback a caller cannot tell apart from a real answer, usually because a key, dependency, or service is out of reach. Do NOT use for documented default parameters, typed-optional returns the caller must check, or test doubles a project has deliberately chosen."
---

# Fail loudly, never plausibly

The dangerous failure is not the one that crashes. It is the one that returns something
shaped exactly like an answer. In `anthropics/claude-code#54682` an evaluation was
backfilled with `expected_answer AS claude_answer`, a literal column copy, and
`is_correct` set programmatically. It reported a perfect score. Nobody was lied to by a
crash; they were lied to by a green number. `#6142` records the same failure from the
other side: a user with an explicit, repeatedly-stated zero-tolerance policy against stubs
still got them, and named the result **silent corruption**, code that compiles and
produces wrong results.

This skill is about the moment just before that happens: the real thing is out of reach,
and there is a value-shaped hole to fill.

## Iron Law

```
IF IT CANNOT DO THE REAL THING, IT MUST FAIL IN A WAY THE CALLER CANNOT MISS.
```

## The distinguishing question

Not every default is a defect. Defaults, optional returns, and test doubles are ordinary
engineering. The single question that separates them:

> **Can a caller tell this apart from success?**

|Fine|Defect|
|-|-|
|`def fetch(url, timeout=30)`: the default is in the signature, so passing nothing is a choice|`return 30` from inside `fetch` when the config read failed|
|`-> Optional[User]`, documented, and callers check for `None`|`return User()` with blank fields when the row is missing|
|`get(key, default)` returning the caller's own `default`|`get(key)` returning a module-level `DEFAULT_PREFS` on a cache miss|
|`...` in an `@abstractmethod`: a declaration, not a value|`return 0.0` in a method that was supposed to compute the tax|
|A hand-written `FakeClock` in `tests/`, obvious at the call site|`MagicMock()` imported by a module in `services/`|
|`raise NotImplementedError("pyarrow is not installed")`|`# TODO: wire this up` above `return []`|

The right column is not worse code. It is code that reports success it did not achieve.

## Taxonomy: eight shapes, and how each one hides

|Shape|Signature in the source|How it passes review|Scan|
|-|-|-|-|
|Hardcoded return|parameters accepted, none read, a literal handed back|the type is right and the call site works|diff only|
|Swallowed exception|`except: pass`, or a handler with no log and no re-raise|the happy path is untouched, so tests stay green|bare `except:` only|
|Indistinguishable fallback|`if not api_key: return 1.0`|1.0 is a legal exchange rate; totals still look sane|yes|
|Mock on a live path|`MagicMock` outside `tests/`|it returns whatever the demo needed|yes|
|TODO that returns|a marker comment directly above `return []`|the marker reads as a plan, not as a live defect|yes|
|Self-scoring check|`actual = row["expected"]`, `is_correct = True`|the score is 100%, which nobody investigates|yes|
|Retry exhaustion|a loop of attempts, then `return []` after the last one|"no incidents" and "could not reach the incident service" print identically|yes|
|Cache-miss default|`hit = cache.get(k)`, `if hit is None: return DEFAULT`|every miss looks like a hit with boring data|yes|

The `Scan` column is what phase 4's script actually detects, measured rather than hoped.
Two shapes are wider than any mechanical rule can safely be; see "What this scan is worth".

## Phase 1: recognize the moment

You are in it when any of these is true:

- The real call needs a key, a service, a dataset, or a package that is not available here.
- A branch is genuinely underdetermined and you are about to pick a value to move on.
- A test is red and the fastest green is to change the test.
- You are writing a return value you cannot trace back to an input.

## Phase 2: ask the distinguishing question

Ask it out loud, about the specific line: *can a caller tell this apart from success?*

If the answer is yes, name the mechanism that makes it so: the parameter in the signature,
the `Optional` in the annotation, the exception in the docstring, the `tests/` in the path.
No mechanism means the answer is no, whatever the intention was.

### Two cases where the answer is not "raise"

Both of these were answered wrongly, and confidently, before they were written down here.

- **A designed cold-start path.** A recommender with no history for a new user returning
  popular items is not a stub. The absence of history is an expected input, the behaviour
  is specified, and the caller wanted a list. Raising here breaks working software. The
  tell that separates it from a fallback: the empty case was designed for, not discovered
  when the real thing turned out to be unreachable. If it is documented and tested, it is a
  feature.
- **Genuinely best-effort work.** A telemetry post inside `except Exception: pass` swallows
  a real error, but making it raise takes down the caller for something nobody consumes.
  The fix is rung 5 of phase 3, not rung 1: log at error level with the exception attached.
  Silent is still wrong; fatal is also wrong.

The question is never "is there a default here". It is "can the caller tell". Where the
caller wanted the default and the contract says so, you are looking at a feature.

## Phase 3: choose the loudest failure that is still correct

Descend this ladder only as far as correctness forces you.

1. **Raise, naming the missing precondition.** The default. The message names what is
   missing, not what the function is called:
   `raise RuntimeError("fetch_exchange_rate: FX_API_KEY is not set; cannot fetch a real rate")`.
   A caller reading that log knows what to fix without opening the file.
2. **Fail the test.** If a test is red because the implementation is incomplete, the test
   is correct and the implementation is not. Never widen an assertion, add `skip`/`xfail`,
   loosen a tolerance, or catch-and-continue to turn red green. A test that cannot reach
   the real service should fail as unreachable, not pass against a substitute.
3. **Return an explicit sentinel the type system forces callers to handle.** Legitimate
   only when the absent value is a normal outcome the caller has something to do about,
   and the signature says so: `Optional[T]`, a `Result` type, an enum member such as
   `Rate.UNAVAILABLE`. Add it to the annotation and update every caller in the same change,
   or you have just built a quieter stub.
4. **Escalate to the user.** When the missing thing is a decision rather than a value, stop
   and ask. Guessing a decision is the most expensive stub of all.
5. **Log at error level and continue.** The bottom rung, and correct in exactly one case:
   the work is genuinely best-effort and its failure must not stop the caller (telemetry,
   a cache warm, an optional cleanup). Conditions: the caller never consumes a return
   value, the log carries the exception, and the level is `error` or `warning`, never
   `debug`. If any of those is false, go back up the ladder.

Whichever rung you land on, put the blocker in the code and in the reply, not only one.

**Then check that your raise survives.** A raise three frames below an unchanged
`except Exception: pass` is a stub with extra steps. Walk the call chain to the nearest
caller that reports to a human and confirm nothing eats it on the way:

```bash
grep -rnE 'except (Exception|BaseException)?\s*:' <callers> | grep -v raise
```

Verified case: a fixed `fetch_exchange_rate` raised correctly, and the caller still
printed `TOTAL 0.00`, because an outer handler swallowed it. The fix is not done until
the failure reaches a human.

## Phase 4: scan what you wrote

Locate the script (it moves with the install; do not guess a relative path):

```bash
SCAN=$(ls ~/.claude/skills/no-silent-stub/scripts/stub-scan.py \
          ~/.claude/plugins/cache/*/*/*/skills/no-silent-stub/scripts/stub-scan.py \
          2>/dev/null | head -1)
python3 "$SCAN" --diff            # what this branch added, against HEAD
python3 "$SCAN" --diff --base main
```

`--diff` is the posture that works: it reads only the lines you added, untracked new files
included (a brand-new module is invisible to plain `git diff`, which is how the commonest
case of all used to scan clean), so its volume is
bounded by your own change, and the shapes it confuses with stubs (a base-class default, an
always-constant implementation) are pre-existing architecture rather than something you
wrote in the last hour. Non-Python added lines get the grep floor applied to them
automatically. Exit 1 means findings, 0 means clean, 2 means it could not run.

Triage of an existing tree is the other mode, `python3 "$SCAN" <dir>`, and it is much
weaker. Read on before trusting it.

### What this scan is worth

Measured against 308,000 lines of third-party libraries (`requests`, `click`, `jinja2`,
`urllib3`, `dateutil`, `pyyaml`, `numpy`), code neither this skill nor its fixtures ever
saw:

|Corpus|Mode|Findings|True|
|-|-|-|-|
|308 kLOC of third-party libraries|triage, first cut|413|~1%|
|308 kLOC of third-party libraries|triage, as shipped|2|1|
|36 kLOC of the standard library|triage, as shipped|3|3 (all real bare `except:`)|
|4 kLOC of unplanted real diff|`--diff`|0|n/a, nothing was wrong in it|
|7 planted stubs in a scratch repo|`--diff`|7|7, and nothing extra|

All 18 first-cut findings in `requests` were read individually and every one was false:
`except OSError: return False` inside `is_ipv4_address`, where the boolean is the answer,
and a documented no-op override hook. That reading is what cut the rule set down. Note the
last two rows measure different things: the unplanted diff is a precision check, the
planted one is only a recall check, since those stubs were written to be found.

The rules were cut until that held. `constant-stub` scored 0 of 6 on that corpus and is
suppressed in triage mode entirely, because "ignores its parameters and returns a literal"
describes a deliberate base-class default (`click`'s `list_commands`, `dateutil`'s
`tzname`) exactly as well as it describes a stub. That difference is semantic, and no AST
pass reaches it. `except SpecificError: pass` was dropped from the rule set for the same
reason: on real code it is an optional-import probe or a candidate-file loop far more often
than a swallowed failure. Both are still in the taxonomy above, because you can tell the
difference and a grep cannot.

Findings name one of eight rules, so you can tell what was matched:
`constant-stub`, `swallowed-exception`, `marker-return`, `mock-outside-tests`,
`self-scoring-eval`, `retry-exhaustion-empty`, `cache-miss-default`, `credential-fallback`,
plus `test-widening` and `floor-match` on a diff, and `unscanned-language` for what it
could not parse.

**The scan is Python only.** Anything else is reported as `unscanned-language` rather than
passed over. For those files, and any time the script is not to hand, the floor is:

```bash
git diff -U0 | grep -nE 'TODO|FIXME|for now|placeholder|return \[\]|return \{\}|except[^:]*:\s*pass|catch\s*\([^)]*\)\s*\{\s*\}|MagicMock|pytest\.mark\.(skip|xfail)'
```

Account for every hit, one by one. Then read the diff for what no scan reaches: **an
unmarked fallback with no guard has no syntactic tell.** A function that reads its
arguments, does real arithmetic, and returns a plausible average for the unknown branch
passes every mechanical check ever written, and prints a number identical to the real one.
A clean report is a floor. Phase 2 is the part that actually works.

## Phase 5: the reporting duty

If the session could not do the real thing, the final message says so. This is not
optional politeness; a status report that claims what the code does not deliver is the
same defect one layer up, and it is the layer the user actually reads.

State, in the reply:

- **What is not implemented**, by name.
- **Why**: the specific missing precondition.
- **What would finish it**: the key, the package, the decision, the access.
- **What was not verified**: every path that never ran here.

Never write "done", "working", or "tests pass" for a path whose real implementation never
executed. "The parser is complete except the CSV branch, which raises because the spec for
quoted newlines is undecided" is a good report. "Parser done" is not.

This phase is narrow on purpose. It covers one thing: naming the fake you were about to
ship, or did ship. Verifying a completion claim in general belongs to
`superpowers:verification-before-completion`; invoke that for the evidence-before-assertion
discipline rather than repeating it here.

## Red flags

Each of these thoughts means stop and return to phase 2:

- "Just for now, I will return a sensible value."
- "The test needs something to return."
- "The real API costs money, so I will fake the response."
- "I will wire it up next."
- "It is only the fallback path, it will rarely run."
- "An empty list is a reasonable default here."
- "I will make the test pass first and fix the code after."
- "It is close enough to the real answer."
- "Nobody will call this with a missing key."
- "The user asked for a working demo, not a correct one."

## Common rationalizations

|Excuse|Reality|
|-|-|
|"Just for now"|Nothing marks it as temporary except a comment nobody greps. It ships.|
|"The test needs something to return"|A test whose dependency is unreachable should fail as unreachable. That failure is the information.|
|"The real API costs money"|Then the code path raises without the key. A free wrong answer costs more than a paid right one.|
|"I'll wire it up next"|The next session sees working code and no reason to look. Only a raise survives a context reset.|
|"It's only the fallback path"|The fallback path runs on exactly the day the real one breaks, which is the day you need the truth.|
|"An empty list is a reasonable default"|Only if the caller can tell "none found" from "never looked". Otherwise it is a lie with a plausible shape.|
|"Returning zero is safer than crashing"|Zero propagates into totals, invoices, and dashboards. A crash stops at the caller.|
|"I'll note it in my summary"|A note in a summary is not in the code path. Raise, then also note it.|
|"The user wants progress, not blockers"|The user wants working software. A named blocker is progress; an invented value is a debt with interest.|

## Trigger precision

### Must fire

- "The tests need an API key we don't have. Just make the suite pass."
- "Finish this parser. For the branches you can't do yet, return an empty list."
- "Wire up `get_exchange_rate()`, and if the provider is unreachable, fall back to something sensible."

### Must not fire

- "Add a documented `timeout=30` default parameter to `fetch()` and mention it in the docstring."
- "Change `find_user` to return `Optional[User]` instead of defaulting to a blank user, and update the callers to check for `None`."
- "Our suite uses a hand-written `FakeClock` everywhere by design. Add one more case that uses it."

## Quick reference

|Phase|Do|Done when|
|-|-|-|
|1 Recognize|Notice the value-shaped hole|You can name what is out of reach|
|2 Distinguish|Ask whether a caller can tell this from success|A mechanism makes it visible, or it is a defect|
|3 Fail loudly|Raise naming the precondition; else fail the test; else typed sentinel; else ask|The failure reaches the caller unmissed|
|4 Scan|Run `stub-scan.py` on the diff, then read for the unmarked fallback|Every finding accounted for, one by one|
|5 Report|Say what is unimplemented, why, what finishes it, what is unverified|No success claim outruns the code|
