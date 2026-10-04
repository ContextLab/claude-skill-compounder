---
name: reuse
description: Use when starting a substantial task (building a script, tool, skill, pipeline or procedure), or when a "[compound] Reuse before building" message appears. Checks for existing lessons, skills, scripts and earlier requests to reuse or broaden before writing anything new.
---

# Reuse before building

Before building something, find out whether it, or most of it, already exists. Work that
exists is used. Work that nearly fits is broadened. Only what nothing covers is built new.

**Which `compound` to run.** A `[compound]` message ends with a line
`compound CLI: <absolute path>`. Run that path. If there is no such message, run `compound`
from PATH. Below, `compound` stands for whichever applies.

## 1. Look in four places

Do all four. Each one finds things the others miss.

1. **Recorded lessons, skills and scripts**, ranked by how well they match:

   ```bash
   compound find "<keywords from the request>"
   ```

   It also prints earlier requests like this one from the prompt log.

2. **Everything recorded, and the project's scripts**, when the keywords may not match the
   words the thing was described with:

   ```bash
   compound list --scripts
   ```

   `compound show <name>` prints one lesson or skill in full, with its path and attached files.

3. **The skills this session already has.** Read the list of available skills in your
   context. A skill that covers the task is invoked with the Skill tool, not rebuilt.

4. **The user's earlier requests**, across projects, when `surfer` (history-surfer) is installed:

   ```bash
   surfer search "<keywords>" --all
   ```

   An earlier request like this one means the work may already exist in that project, and
   it shows what the user asked for last time in their own words.

If a `[compound] Reuse before building` message listed items, start with those: open each
one it names before deciding anything.

## 2. Decide, in this order

1. **It exists and fits.** Use it. Say which one you used.
2. **It exists and nearly fits.** Broaden it so that it keeps its old use and gains the
   new one: add a flag, a parameter or a case to the existing script or skill. Do not copy
   it and change the copy; two near-copies drift apart. Check that the old use still works
   after the change.
3. **Parts exist.** Build only the missing part, and call the existing parts from it.
4. **Nothing covers it.** Build it new. Put a script under the project's `scripts/` with a
   first-line comment saying what it does, so the next search finds it.

When it is not clear whether an existing thing may be changed (it belongs to another
project, or another use depends on it), ask the user before changing it.

## 3. Say what you found

Tell the user in one or two lines what you reused, what you broadened, and what you built
new and why nothing existing covered it.

## 4. Afterwards

If the work taught something a later session would otherwise have to work out again, record
it with the `compound:learn` skill.
