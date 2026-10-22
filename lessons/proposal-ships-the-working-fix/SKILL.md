---
name: proposal-ships-the-working-fix
description: Use when proposing a fix upstream or to a shared pool (compound promote --to general, a pull request to a tool's repository) after solving the problem locally, and when asked to generalize, package or share something that works on this machine.
created: 2026-10-10
---
Propose the thing that works, in the form that works. Before opening the upstream pull
request, put the local fix and the proposal side by side and name every difference; each
one is either removed or justified in the pull request.

The wrong way: the local fix is a hook that refuses a stop, and the upstream proposal is a
lesson that says to run a script by hand. The advice form depends on the reader remembering
it, which is the failure the hook existed to remove, so the proposal does not solve the
problem it describes. The same drift shows up as a guard proposed as a plain lesson, an
enforced check proposed as documentation, or a narrowed, tested script proposed in its
earlier, looser draft.

If the working form cannot ship as it is (the host has no hook mechanism, the script is
specific to one machine), say so in the pull request and propose the nearest enforced
form, not a reminder. When the local fix changes after the proposal is open, update the
proposal in the same sitting: the shipped file should be byte-identical to the one in use
(`cmp local upstream`).
