---
name: verify-assumptions-first
description: Use when starting a large effort, such as a build of several files, a pipeline, a migration, an integration with an API, a tool or a data file not yet looked at, or any plan that rests on what a file, a service or the brief is said to be. Not for a small change, a one-line fix, or a question.
---

# Verify the assumptions first

A large build that rests on one false assumption is rebuilt. Find the false one before
anything is written, prove the approach on the smallest thing that can prove it, and only
then build the rest.

Do the steps in this order, each as an act of its own that the user can see. A step that
was merged into another, done in silence, or left out because the plan already looked
clear was not done. The first thing after reading this is the Skill call of step 1; the
second is the message of step 2. No other tool call comes before them.

## 1. Look for existing work

Invoke the `compound:reuse` skill with the Skill tool, before any other tool call. What
already exists changes the plan. A new or empty project is no reason to skip this: the
skill also looks at the user's other projects and earlier requests.

## 2. State the base assumptions

Write a message to the user that lists, before any of it is checked, everything the plan
takes for granted: what the inputs are
(their format, their fields, their size), what each API, tool or command does and that it
is there, what the environment allows, and every fact the request itself states. What the
user said about a file or a system is an assumption too, not a finding.

## 3. Check each one with a real call

The real file, the real API, the real command. Not memory, and not documentation alone.
Open the file and look at its first records. Call the endpoint once. Run the tool with its
version or help flag. Write one line for each assumption: it holds, it is false, or it
could not be checked and why.

## 4. Say what was false

Tell the user at once which assumptions were false and how the plan changes. If a false
one changes what was asked for, and not only how to build it, ask before building.

## 5. Build the smallest thing that proves the approach

One path, end to end, on the real input: the fewest lines that read the real data and
produce one real result. The first call that writes a file writes this and nothing else.
Run it. If it does not work, the approach is wrong, and that was cheap to learn.

Do not write the rest of the build in the same call, or before this has run, however
clear the whole plan is by now. Having checked the assumptions is not having proved the
approach.

## 6. Build out, one addition at a time

Add one part in one call, then run everything that exists so far. Go on only when nothing
broke. A failure now points at the part just added. Writing every remaining file at once
and testing at the end is not this step.

## 7. Finish

When the build is done, invoke the `compound:finish-task` skill (Skill tool) for the
end-of-task routine.
