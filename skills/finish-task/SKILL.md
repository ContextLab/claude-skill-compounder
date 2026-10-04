---
name: finish-task
description: Use when a change is done, or thought to be done, and has to be wrapped up, as when the user says to finish, wrap up, finalize or commit the work, or the implementation has just ended and nothing has been checked or committed yet. Not for work still in progress, a question, or a request only to review.
---

# Finish the task

A change is finished when it was reviewed, every check the project has passes, what it
made stale was updated, and it is committed. Do the steps in this order. Do not stop after
the first check that passes.

## 1. Review the change

Read the whole diff, untracked files included. Does it do what was asked, and only that?
Take out what does not belong: debugging output, stray files, anything secret.

## 2. Find every check the project has

Look; do not answer from memory. A project says how it is checked in its README or
contributing guide, its CI configuration, its task runner or build file, and the
configuration files of its test runner, linters, type checker, documentation build and
validators. Write the list down before running anything. One test command is rarely the
whole list.

## 3. Run every check

Run each one on the list. A check that fails because of how it was called (a missing
argument, a wrong directory) was not run: correct the call and run it.

## 4. Fix what fails, in the code

When a check reports a problem, fix the work. Never make a check pass by weakening it: do
not delete, skip, loosen or rewrite a test or a rule to fit the code. If a check is itself
wrong about what was asked for, say so and ask the user before changing it.

After any fix, run ALL the checks again, not only the one that failed. Repeat until one
pass over the whole list is clean.

## 5. Update what the change made stale

Search the documentation, the examples, the comments and the project's notes or changelog
for the names and the behaviour the change touched. Correct every statement that is no
longer true. Add notes only where the project keeps them.

## 6. Record what was learned

If a command failed along the way and was then corrected, or a `[compound]` message says
a lesson is owed, invoke the `compound:learn` skill (Skill tool) now. A check that
correctly reported a problem in the work is not a lesson.

## 7. Commit

Commit the files of this change and no others, with a message in the project's own style
(read the log) that says what changed and why. If steps 4 to 6 changed files, they are
part of the commit. Where there is no version control, say so.

Do not push, open a pull request, tag, release or publish anything unless the user asked
for exactly that.

## 8. Report

Say what the review found, each check that was run and its result, what was updated, and
the commit. Say plainly what was not done and why.
