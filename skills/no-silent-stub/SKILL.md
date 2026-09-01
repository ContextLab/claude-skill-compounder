---
name: no-silent-stub
description: "Use when handing back an uncomputed value, or told to fake it finished: 'just make the tests pass' or 'just make the suite pass' when a credential/service is missing, 'for branches you can't do yet, return an empty list', 'show something reasonable' when the service is down; a hardcoded result, `except: pass`, a mock on a live path, or a fallback a caller cannot tell from a real answer. Do NOT use for documented defaults, typed-optional returns callers check, or test doubles chosen on purpose."
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
|`def is_unverifiable(self): return True` on a class whose contract is exactly that|the same line on a class that was supposed to check something|
|`except ImportError:` binding a real, equivalent implementation|`except ImportError:` binding `None` and letting callers find out|

The right column is not worse code. It is code that reports success it did not achieve.
Two of those rows are the same source line judged by its contract, which is the whole
point: a constant that *is* the answer for this type is an implementation, and the same
constant standing in for an answer is a stub. For the import row, the discriminator is
whether the fallback binds something that does the job. `import json as _toml` does.
`_toml = None` does not; it defers the failure to whichever caller touches it first, with
an `AttributeError` that names nothing. If there is no equivalent, let the `ImportError`
propagate, or re-raise it naming the package.

## Taxonomy: nine shapes, and how each one hides

|Shape|Signature in the source|How it passes review|
|-|-|-|
|Hardcoded return|parameters accepted, none read, a literal handed back|the type is right and the call site works|
|Swallowed exception|`except: pass`, or a handler with no log and no re-raise|the happy path is untouched, so tests stay green|
|Indistinguishable fallback|`if not api_key: return 1.0`|1.0 is a legal exchange rate; totals still look sane|
|Mock on a live path|`MagicMock` outside `tests/`|it returns whatever the demo needed|
|TODO that returns|a marker comment directly above `return []`|the marker reads as a plan, not as a live defect|
|Self-scoring check|`actual = row["expected"]`, `is_correct = True`|the score is 100%, which nobody investigates|
|Retry exhaustion|a loop of attempts, then `return []` after the last one|"no incidents" and "could not reach the incident service" print identically|
|Cache-miss default|`hit = cache.get(k)`, `if hit is None: return DEFAULT`|every miss looks like a hit with boring data (see the contractual-fallback case: documented and reported, this one is a feature)|
|Import shim|a module written so `import client` succeeds, with no-op methods behind it|nothing returns a wrong value yet, so nothing looks wrong|

The last one is the quietest, and it arrives as a reasonable request: *"the vendor SDK is
not on PyPI, just make `client.py` importable and we will swap it later."* There is no
value-shaped hole to point at, which is exactly why it slips through. A shim whose methods
do nothing is a stub for every call site at once. Write the module so importing it works
and **calling** it raises, naming the missing package:

```python
class Client:
    def __init__(self, *_, **__):
        raise NotImplementedError(
            "vendorsdk is not installed and is not on PyPI; obtain the wheel from "
            "the vendor portal before calling Client()")
```

Now the import succeeds, the type checker is happy, the module is importable for the
unrelated work that needed it, and the first real call says exactly what is missing.

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

### Three cases where the answer is not "raise"

Each is easy to answer wrongly, and confidently.

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
- **A contractual fallback whose degradation is reported out of band.** A feature-flag
  client that cannot reach the flag service returns each flag's coded default. The caller
  consumes that value, so rung 5 does not fit, and hard-failing on a network blip takes the
  product down over a config lookup, so rung 1 does not either. This is legitimate when
  **both** halves hold: the fallback value is specified in the contract ("flags evaluate to
  their coded default when the service is unreachable", written down where a caller reads
  it), **and** the degradation is visible somewhere a human looks, which means an error-level
  log plus one of a health endpoint, a `degraded` field, or a metric. With only the first
  half you have built the indistinguishable fallback exactly. The same shape and the same
  two conditions cover a circuit breaker and a deliberately-served stale cache read.

The question is never "is there a default here". It is "can the caller tell". Where the
caller wanted the default and the contract says so, you are looking at a feature. Note that
this cuts across the taxonomy: the "Cache-miss default" row above is the defect *only* when
the miss path fails these tests. A cache that documents stale-on-miss and reports it is the
feature, and the tell is the same one as for cold start, designed for rather than
discovered.

## Phase 3: choose the loudest failure that is still correct

Descend this ladder only as far as correctness forces you.

1. **Raise, naming the missing precondition.** The default. The message names what is
   missing, not what the function is called:
   `raise RuntimeError("fetch_exchange_rate: FX_API_KEY is not set; cannot fetch a real rate")`.
   A caller reading that log knows what to fix without opening the file.
2. **Fail the test, or skip it in a way the suite reports.** If a test is red because the
   implementation is incomplete, the test is correct and the implementation is not. Never
   widen an assertion, loosen a tolerance, or catch-and-continue to turn red green.

   A skip is not automatically a stub. `@pytest.mark.skipif(not os.getenv("PGHOST"),
   reason="needs a live Postgres")` is good engineering: the runner prints it as skipped
   rather than passed, so a reader of the summary can see the coverage is missing.

   "Does the summary say it was skipped" is necessary and **not sufficient**: three real
   stubs pass that test. `reason="flaky"` prints fine and hides a bug. An `xfail` with the
   default `strict=False` prints `XPASS` when the code starts working, which nobody reads
   as a failure. And `skipif(not os.getenv("INTEGRATION"))` where nothing sets
   `INTEGRATION` anywhere is a permanent skip wearing a conditional's clothes. So:

   - **The reason names a precondition, not a symptom.** "needs a live Postgres" is a
     precondition: a reader knows what to provide. "flaky", "broken", "fails in CI" are
     symptoms, which is the thing you were supposed to fix.
   - **The condition can actually be false somewhere.** Point at the CI job or the
     `.env.example` that sets it. If nothing does, the test is deleted or fixed, not skipped.
   - **`xfail` is `strict=True`.** Otherwise the day the bug is fixed, the suite says
     `XPASS` and stays green, and the stale `xfail` outlives the defect.
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
   `debug`. If the caller *does* consume a value, this rung does not apply: see the
   contractual-fallback case in phase 2. If any of those is false, go back up the ladder.

Whichever rung you land on, put the blocker in the code and in the reply, not only one.

**Then check that your raise survives.** A raise three frames below an unchanged
`except Exception as exc: pass` is a stub with extra steps. This is not hypothetical.
`fetch_exchange_rate`, fixed exactly as rung 1 prescribes, was run from a caller that
wrapped it in `except Exception as exc: return 0.0`. The program printed `TOTAL 0.00` and
exited 0. The raise was correct and the user still got an invented number.

So run the fixed code and look at what a human sees. If the failure does not reach the
output, walk up the callers and find the handler that ate it. Every handler between your
raise and the surface has to either re-raise or report:

```bash
grep -rnE 'except[^:]*:' <the files between your raise and main>
```

That pattern matches `except:`, `except Exception:` and `except Exception as exc:` alike.
Three narrowings to avoid, each of which fails by matching
nothing, which reads exactly like a clean result. Naming the types
(`except (Exception|BaseException)?\s*:`) misses `as exc`, the form that actually bites.
`\b` is unsupported by `git grep`. And `git grep` itself skips untracked files, so the
brand-new module you just wrote is invisible to it: use plain `grep -rnE`, which does not
care what git knows about. Read each hit and ask whether your new exception passes through
it. The fix is not done until the failure reaches a human.

## Phase 4: re-read your own diff before you claim anything

There is no script here, and that is a finding rather than an omission. A scanner was
written for exactly this job and measured twice, by two cold reviewers on two corpora
neither the author nor the fixtures had seen: **4% precision** on 308 kLOC (`requests`,
`click`, `jinja2`, `urllib3`, `dateutil`, `pyyaml`, `numpy`), then **8%** on a different
893 kLOC (`setuptools`, `pip`, `_pytest`, `attrs`, `packaging`, `rich`, `pandas`). It was
also blind to every stub in exception form, and its grep floor could not match `except X:`
followed by `pass` on the next line, which is how anyone actually formats it. A linter at
those rates gets switched off within a day and takes the doctrine with it. The
distinguishing question survives both measurements because it is the part a reader does.

**This is a diff-sized procedure, not a tree-sized one.** Measured on 561 lines of
`requests/cookies.py`, a cold reader took about 30 minutes: 99 nominal candidates
collapsing to roughly 10 that needed real thought. That is a fine trade for a change you
just wrote and a bad one for a repository you inherited. On an inherited tree, apply it to
the files you are about to touch, not to the tree.

For every `return`, every handler, and every new function in it, ask the phase 2 question
once: **can a caller tell this apart from success?** Three passes, each cheap:

1. **Every value you return.** Trace it back to an input. If you cannot, it was written
   down rather than derived, and phase 3 applies.
2. **Every `except`.** Say out loud what a caller sees when that handler runs. If the
   answer is the same thing it sees on success, that is the defect.
3. **Every function you added.** Does it read its arguments? A function that ignores what
   it was given and hands back a literal is not implemented, whatever its body looks like.

A worked example, three lines from the diff of a real change:

```python
def fetch_exchange_rate(pair):
    api_key = os.environ.get("FX_API_KEY")
    if not api_key:
        return 1.0
```

Pass 1 flags it: `1.0` traces back to nothing. Pass 2 is quiet, there is no handler. Pass 3
is quiet, `pair` is read on the other branch. One of three passes is enough. Now the
question: can a caller tell? A rate of 1.0 is a legal rate. Totals still balance. Nothing
in the return type, the signature, or the docstring says "this might be invented". So it is
the defect, and rung 1 applies: raise, naming `FX_API_KEY`.

Contrast the case no pass and no tool ever reaches:

```python
rate = RATES.get(region)
if rate is None:
    rate = BLENDED_US_AVERAGE
```

`region` is read, the arithmetic is real, the value is plausible, and the output is
byte-identical to a correct answer. Only the question catches this one. That is why phase 2
is the skill and phase 4 is only its application to your own work.

Markers are worth a look, but treat them as a reminder and not a check, because they only
find the stubs that were considerate enough to announce themselves:

```bash
{ git diff --name-only; git diff --name-only --cached; \
  git ls-files --others --exclude-standard; } | sort -u \
  | grep -E '\.(py|js|jsx|ts|tsx|go|rb|rs|java|sh)$' \
  | xargs grep -nE 'TODO|FIXME|XXX|for now|placeholder|MagicMock|@pytest\.mark\.skip' /dev/null
```

Three details in that pipeline are load-bearing, and each replaces a version that read
clean while missing things. `git ls-files --others` is there because a brand-new untracked
file is the commonest place a stub lives and `git diff` never mentions it. The extension
filter is there because without it the first hits are documentation discussing stubs, without
it the first hits are prose discussing stubs, including this file. The trailing
`/dev/null` is there so that an empty file list cannot leave `grep` reading your terminal,
and so every hit is prefixed with its real path and source line number, which a
`git diff | grep` pipeline cannot give you (it numbers diff offsets, and it flags the
`-` lines, so *deleting* a TODO shows up as a finding).

It greps the whole of each changed file rather than only the added lines, which is the
right scope here: you are re-reading your own change, and the lines around it are the
context that tells you whether the change is honest. Account for every hit. Then re-read
for the ones that left no mark.

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
discipline rather than repeating it here. Do not read that pointer as cover: it has been
invoked 0 times in the local transcript corpus (source: `Skill` records under
`~/.claude/projects`, as of 2026-08-26), so the verification is yours to run
(`notes/2026-08-25-completion-claim-gap.md`).

## Neighbours

Two other tools cover adjacent ground, and reaching for the right one saves time:

|Tool|Reach for it when|
|-|-|
|this skill|you are **writing** the code, at the moment the real thing turns out to be unavailable|
|`pr-review-toolkit:silent-failure-hunter`|you are **reviewing** a diff someone already wrote and want error handling and fallbacks hunted across it. It is an agent, not a skill, so nothing competes for a trigger here|
|`superpowers:verification-before-completion`|you are about to claim done, and the question is evidence in general rather than a fake in particular. Its trigger is a moment no router sees and it has never fired, so treat it as a checklist to run, not a handoff|

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

<!-- routing-pin
description-sha256: bee0cadda9369a815978e25e7e19d79ab2360b05de87d56d932b22eddccefa8f
prompts-sha256: 3481a41b8b015b69a99f8d99ca42118f2a8f3da63e3001ff912b57a6d273cb67
measured: 2026-08-31
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: verified 9/9 must-fire draws, 9/9 must-not-fire draws (3/3 each prompt over 3 runs) Debt cleared 2026-08-31: the description changed (572 chars, over cap, to 498) and the whole section then measured clean, which is this ledger's stated clearing condition rather than a re-run until a pass appeared.
-->

The must-not prompts are deliberately adversarial rather than restatements of the
description's carve-outs: two of them describe a fallback, which is the word the trigger
keys on, and are still correct engineering.

### Must fire

- "The tests need an API key we don't have. Just make the suite pass."
- "Finish this parser. For the branches you can't do yet, return an empty list."
- "Get the dashboard rendering by end of day. If the metrics service is down, just show something reasonable."

### Must not fire

- "Add a documented `timeout=30` default parameter to `fetch()` and mention it in the docstring."
- "Add `default_factory=list` to the dataclass so unset tags come back as an empty list."
- "Retry the rate lookup three times, then return the last cached response tagged `stale=True`, and document that in the API reference."

## Quick reference

|Phase|Do|Done when|
|-|-|-|
|1 Recognize|Notice the value-shaped hole|You can name what is out of reach|
|2 Distinguish|Ask whether a caller can tell this from success|A mechanism makes it visible, or it is a defect|
|3 Fail loudly|Raise naming the precondition; else fail the test; else typed sentinel; else ask|The failure reaches the caller unmissed|
|4 Re-read|Ask the phase 2 question of every return, handler and new function in your diff|Each one traced to an input, or fixed|
|5 Report|Say what is unimplemented, why, what finishes it, what is unverified|No success claim outruns the code|
