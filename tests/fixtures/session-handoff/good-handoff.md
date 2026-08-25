# 2026-08-25 handoff: lease-expiry off-by-one in the admission controller

## Resume command

```bash
cd "/srv/checkouts/admission"
git stash push --message "before resuming 2026-08-25" || true
git checkout -B resume/lease-expiry f882c1ac93d08b780caba472786173d2fdd45b78
```

## State

branch: fix/lease-expiry
commit: f882c1ac93d08b780caba472786173d2fdd45b78
uncommitted work: left in the working tree at the path above; see ## Next step 1

```
$ git status --porcelain
 M admission.py
?? notes/
```

```
$ git log --oneline -1
f882c1a Widen the lease window to a half-open interval
```

## Done and verified

- `is_expired` now treats the lease window as half-open. Proved by
  `git show HEAD:admission.py`, which printed `    return now > lease_end`.
- The change is committed, not just in the tree. Proved by `git show --stat HEAD`, which
  printed `admission.py | 2 +-`.

## Done but NOT verified

- The stashed `renew()` reuses the same comparison. Nothing covers it, and this
  repository has no test file yet.

## Broken

- test_handoff_has_state, in the notes linter

```
$ python3 -m pytest tests/test_notes.py -q
FAILED tests/test_notes.py::test_handoff_has_state
  File "/usr/lib/python3.11/etc.py", line 41, in _render
    return template.render(**fields)
E       AssertionError: the rendered note is missing its State heading
E       rendered note was:
## Tree
## Resume command
E       and the linter expected:
## State
tests/test_notes.py:88: AssertionError
1 failed in 0.30s
```

repro: python3 -m pytest tests/test_notes.py::test_handoff_has_state -q

## Dead ends

- Tried freezing the clock with `freezegun` inside the scheduler test. Failed because the
  scheduler reads the clock in a worker thread that `freezegun` does not patch. Do not
  retry it; inject a `Clock` into `Scheduler.__init__` instead.
- Tried widening the comparison in `Scheduler` rather than in `is_expired`. Failed because
  two other callers then disagreed about the same instant. The comparison must live in
  exactly one place.

## Corrections to earlier notes

- `notes/2026-08-22-admission.md` says "the lease window is closed on both ends by
  design". That is no longer true: the closed upper bound was the bug, and the window is
  now half-open.

## Open decisions

- Should a lease expiring exactly at the scheduling instant renew automatically, or be
  rejected so the caller retries? This changes observable behaviour for the batch
  importer, so it needs the user.

## Next

1. The tree still holds the uncommitted `renew()`, which no part of this handoff carries.
   Commit it to `wip/lease-renew` or stash it before touching anything else.
2. Inject a `Clock` into `Scheduler` so the boundary case is testable without sleeping.
3. Write a test covering the `renew()` path at the boundary.

## Watch out for

- The scheduler test starts a real worker thread. A failure there can leave the thread
  alive, and the next test then hangs. Run it alone when it fails.
- `Clock.now()` returns a naive datetime. Comparing it to anything timezone-aware raises
  rather than returning False, so the failure looks like a crash, not an off-by-one.
