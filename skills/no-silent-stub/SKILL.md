---
name: no-silent-stub
description: Use when about to hand back a value you did not actually compute: a hardcoded result, an empty collection standing in for logic, an `except: pass`, a mock on a live path, a TODO that returns, a test scored against its own input, or a fallback a caller cannot tell apart from a real answer, usually because a key, dependency, or service is out of reach. Do NOT use for documented default parameters, typed-optional returns the caller must check, or test doubles a project has deliberately chosen.
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

|Shape|Signature in the source|How it passes review|
|-|-|-|
|Hardcoded return|parameters accepted, none read, a literal handed back|the type is right and the call site works|
|Swallowed exception|`except: pass`, or a handler with no log and no re-raise|the happy path is untouched, so tests stay green|
|Indistinguishable fallback|`if not api_key: return 1.0`|1.0 is a legal exchange rate; totals still look sane|
|Mock on a live path|`MagicMock` imported outside `tests/`|it returns whatever the demo needed|
|TODO that returns|a marker comment directly above `return []`|the marker reads as a plan, not as a live defect|
|Self-scoring check|`actual = row["expected"]`, `is_correct = True`|the score is 100%, which nobody investigates|
|Retry exhaustion|a loop of attempts, then `return []` after the last one|"no incidents" and "could not reach the incident service" print identically|
|Cache-miss default|`hit = cache.get(k)`, `if hit is None: return DEFAULT`|every miss looks like a hit with boring data|

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

Whichever rung you land on, put the blocker in the code and in the reply, not only one.

## Phase 4: scan the diff before you claim anything

Mechanical first pass over changed files:

```bash
python3 skills/no-silent-stub/scripts/stub-scan.py path/to/changed/dir
```

It exits 1 with one finding per line (`path:line: rule: message`) across eight rules:
`constant-stub`, `swallowed-exception`, `marker-return`, `mock-outside-tests`,
`self-scoring-eval`, `retry-exhaustion-empty`, `cache-miss-default`, `credential-fallback`.
Without the script, the grep floor:

```bash
git diff -U0 | grep -nE 'TODO|FIXME|for now|placeholder|return \[\]|return \{\}|except[^:]*:\s*pass|MagicMock|pytest\.mark\.(skip|xfail)'
```

Account for every hit, one by one. Then read the diff for what the scan cannot see: **an
unmarked fallback with no guard is invisible to any grep.** A function that reads its
arguments, does real arithmetic, and returns a plausible average for the unknown branch
passes every mechanical check ever written. That is why phase 2 is a question and phase 4
is only a floor.

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
