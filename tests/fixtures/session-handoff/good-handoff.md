# 2026-08-25 handoff: lease-expiry off-by-one in the admission controller

## Resume command

```bash
cd ./scratch-repo && git checkout f882c1ac93d08b780caba472786173d2fdd45b78 && git status --short
```

## State

branch: fix/lease-expiry
commit: f882c1ac93d08b780caba472786173d2fdd45b78

```
$ git status --porcelain
 M admission.py
```

```
$ git log --oneline -1
f882c1a Widen the lease window to a half-open interval
```

## Done and verified

- `is_expired` now treats the lease window as half-open. Proved by
  `git show --stat HEAD`, which printed `admission.py | 2 +-`.
- The committed form uses `>` rather than `>=`. Proved by
  `git show HEAD:admission.py`, which printed `    return now > lease_end`.

## Done but NOT verified

- The uncommitted edit in the working tree adds a `renew()` path that reuses the same
  comparison. Nothing covers it, and no test file exists yet in this repository.

## Broken

- test_admission_rejects_expired_lease

```
$ python3 -m pytest tests/test_scheduler.py::test_admission_rejects_expired_lease -q
FAILED tests/test_scheduler.py::test_admission_rejects_expired_lease
E       AssertionError: assert 'admitted' == 'rejected'
E         - rejected
E         + admitted
tests/test_scheduler.py:212: AssertionError
1 failed in 0.52s
```

repro: python3 -m pytest tests/test_scheduler.py::test_admission_rejects_expired_lease -q

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

1. Inject a `Clock` into `Scheduler` so the boundary case is testable without sleeping.
2. Write a test covering the `renew()` path at the boundary.
3. Run the full suite before committing.

## Watch out for

- The scheduler test starts a real worker thread. A failure there can leave the thread
  alive, and the next test then hangs. Run it alone when it fails.
- `Clock.now()` returns a naive datetime. Comparing it to anything timezone-aware raises
  rather than returning False, so the failure looks like a crash, not an off-by-one.
