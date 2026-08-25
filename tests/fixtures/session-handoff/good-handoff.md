# 2026-08-25 handoff: lease-expiry off-by-one in the admission controller

## Resume command

```bash
cd /srv/checkouts/admission && git checkout fix/lease-expiry && git rev-parse HEAD
```

## State

branch: fix/lease-expiry
commit: 4f2c1ab9d0e3775c8b6a2149ee0c53f18d7ab204

```
$ git status --porcelain
 M src/admission.py
 M tests/test_admission.py
?? notes/2026-08-25-lease-expiry.md
```

```
$ git log --oneline -3
4f2c1ab Widen the lease window to a half-open interval
9be0713 Add a regression test for a lease expiring on the boundary
1a55d2e Extract clock reads behind Clock.now()
```

## Done and verified

- `Lease.is_expired` now treats the window as half-open. Proved by
  `python3 -m pytest tests/test_admission.py::test_boundary_lease -q`, which printed
  `1 passed in 0.31s`.
- The clock is injectable, so the boundary case is testable without sleeping. Proved by
  `python3 -m pytest tests/test_admission.py -q -k clock`, which printed `3 passed in 0.44s`.

## Done but NOT verified

- `Lease.renew()` was changed to use the same half-open comparison for symmetry. Nothing
  covers it. `pytest tests/test_admission.py -k renew` collects zero tests; a test needs
  writing before this is believed.

## Broken

- `tests/test_scheduler.py::test_admission_rejects_expired_lease`

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
  retry it; inject `Clock` into `Scheduler.__init__` instead.
- Tried widening the comparison in `Scheduler` rather than `Lease`. Failed because two
  other callers then disagreed with `Lease.is_expired` about the same instant. The
  comparison must live in exactly one place.

## Corrections to earlier notes

- `notes/2026-08-22-admission.md` says "the lease window is closed on both ends by
  design". That is no longer true: the closed upper bound was the bug, and the window is
  now half-open.

## Open decisions

- Should a lease that expires exactly at the scheduling instant be renewed automatically,
  or rejected and retried by the caller? This changes observable behaviour for the
  batch importer, so it needs the user.

## Next

1. Fix `test_admission_rejects_expired_lease` by injecting `Clock` into `Scheduler`.
2. Write a test covering `Lease.renew()` at the boundary.
3. Run the full suite before committing.

## Watch out for

- `tests/test_scheduler.py` starts a real worker thread. A failure there can leave the
  thread alive and the next test hangs. Run it alone when it fails.
- `Clock.now()` returns a naive datetime. Comparing it to anything tz-aware raises rather
  than returning False, so the failure looks like a crash, not an off-by-one.
