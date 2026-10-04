---
name: merge-in-a-scratch-worktree
description: Use when merging a branch into main in this repository's main checkout while a Claude Code session has the compound mod loaded from it.
created: 2026-10-04
origin: project claude-skill-compounder, session 09f47a44
---
Merge in a scratch worktree and fast-forward main afterwards: `git worktree add <dir> -b merge-x main`, merge and resolve there, run the checks there, then `git merge --ff-only merge-x` in the main checkout.
The wrong way is `git merge <branch>` in the main checkout: a conflict leaves `<<<<<<< HEAD` markers in `bin/compound` and `hooks/*.ts`, and the live mod loads from that checkout, so every guard check, event read and log write fails with "SyntaxError: invalid syntax" and calls run unguarded until the conflict is resolved.
