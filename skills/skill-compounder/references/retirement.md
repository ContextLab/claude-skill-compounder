# Retiring or quarantining a skill

Two situations, one convention: a skill that has been superseded or cannot be fixed, and a
skill whose forge failed. Neither is ever deleted.

## Before retiring: independent concurrence

Write the case — what was attempted, why it cannot be fixed, what supersedes it — and hand
it to a second fresh agent with the neutral question, *"should this be kept, fixed, or
retired?"* Never "confirm this deletion". A leading prompt tells the reviewer what the
answer should be and it will oblige, which is the same defect as handing a red-teamer a list
of what not to flag.

Retire only if the second agent independently reaches "retire". If it says keep or fix, do
that.

## Archiving: resolve the link first

Most skills are symlinks into a checkout. `mv ~/.claude/skills/<name> ...` moves the *link*,
leaves the real directory where the next install resurrects it, and — worse — writing
`WHY-ARCHIVED.md` into the moved directory writes into live source.

```bash
src="$(realpath ~/.claude/skills/<name>)"          # follow the link
mkdir -p ~/.claude/skills-archive
mv "$src" ~/.claude/skills-archive/<name>          # move the real directory
rm -f ~/.claude/skills/<name>                      # then drop the dangling link
```

Write `WHY-ARCHIVED.md` inside the archived copy afterwards, recording the date, the case,
and the concurring verdict. If the source lives in a git repo, remove it there too, or the
next `git pull` brings it back.

**Never `rm -rf` a skill.** A retirement decision can be wrong, so it has to be
recoverable.

## The plugin-cache case

A skill inside a plugin cache cannot be archived this way at all — the cache is restored by
the plugin, not by you. Disable the plugin, or narrow the skill's `description` so it stops
firing, and record which you did and why. Do not delete cache contents; the next plugin
update undoes it silently.

## Quarantining a failed forge

Same destination, different contents. The skill and its failure report go together into
`~/.claude/skills-archive/<name>/`, with the report as that directory's `WHY-ARCHIVED.md`.
The report's four signed sections are described in
`skills/skill-compounder/references/pipeline-stages.md`; the rule that matters at archive
time is that nobody rewrites anyone else's section on the way in, and contradictions between
them are kept.

A quarantined skill is not installed and does not fire. It is kept because the next session
to hit the same trigger needs to know the attempt was made and why it failed — otherwise the
same forge is run again from scratch, which is the failure this whole package exists to
prevent.
