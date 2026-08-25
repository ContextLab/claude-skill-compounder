# 2026-08-25 handoff: admission controller work

## Resume command

Just pick up where we left off in the admission repo. Everything is on the feature branch.

## State

branch: fix/lease-expiry

Working tree has a few uncommitted changes.

## Done and verified

- Fixed the lease expiry logic. Tests look good.

## Done but NOT verified

- Some cleanup in the renew path.

## Broken

- A couple of the scheduler tests are still failing with an assertion error about the
  admission state. Should be straightforward to sort out.

## Dead ends

- Tried a few things with the clock that did not pan out.

## Corrections to earlier notes

None.

## Open decisions

None.

## Next

1. Finish the scheduler tests.

## Watch out for

- The scheduler tests are a bit flaky.
