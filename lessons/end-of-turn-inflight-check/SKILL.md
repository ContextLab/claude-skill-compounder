---
name: end-of-turn-inflight-check
description: Use before ending a turn, giving a final answer or a status report, when the turn started background processes, pushed a branch, dispatched a workflow run, or opened a pull request whose checks are still running.
created: 2026-10-10
---
Before ending a turn, run inflight-check.sh (beside this lesson). It lists detached
processes, hosted runs in progress and open pull requests with pending checks, and exits 1
when anything is still in flight.

For each thing it lists, one of three must be true before the turn ends: a background
waiter is running that exits on that thing's completion (with a deadline), or the thing
notifies on its own (a command started in the background by the harness), or the final
message says plainly that nobody is watching it and when to look. A started job with no
waiter is not being monitored, however alive its process is.

The wrong way: start a three-hour run, dispatch a workflow, open pull requests, write a
status summary and stop. Nothing fails. The work finishes or stalls unseen, and the next
anyone hears of it is the user asking for status and pointing out that the monitors are
gone. A detached `nohup ... &` process in particular sends no completion notice, unlike a
harness background command.
