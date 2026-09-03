# Gate checks, copy-paste

The canonical Gate A block lives in `../SKILL.md`, Phase 3, for a single draft. This file
holds the two things that do not fit in an always-loaded body: a sweep over a whole tree of
skills, and the worksheet for Gate B.

Enforcement is not restated here: `SkillFrontmatterTest` in `tests/test_plugin.py` gates
every skill shipped from this repository, and `skill-compounder` step 2 parses as it forges.
Neither watches a skill written directly into `~/.claude/skills/`.

## Sweep an existing tree

Gate A over every skill under one or more roots, one line each; exit status is the failure
count, so it works as a gate in a loop.

```bash
python3 - ~/.claude/skills ~/.claude/plugins/cache <<'PY'
import os, pathlib, sys, yaml
PORTABLE = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
bad = 0
seen = set()
for root in sys.argv[1:]:
    base = pathlib.Path(root).expanduser()
    for dirpath, dirnames, filenames in os.walk(str(base), followlinks=True):
        real = os.path.realpath(dirpath)
        if real in seen:                      # followlinks=True can revisit and loop
            dirnames[:] = []
            continue
        seen.add(real)
        if "SKILL.md" not in filenames:
            continue
        d = pathlib.Path(dirpath)
        try:
            raw = (d / "SKILL.md").read_text()
            if not raw.startswith("---\n"):
                raise ValueError("no frontmatter block")
            front = raw.split("---\n", 2)[1]
            meta = yaml.safe_load(front)
            if not isinstance(meta, dict):
                raise ValueError("frontmatter is not a mapping")
            desc = meta.get("description")
            if not isinstance(desc, str) or not desc.strip():
                raise ValueError("description is %r, listing falls back to the H1" % (desc,))
            if meta.get("name") != d.name:
                raise ValueError("name %r != directory %r" % (meta.get("name"), d.name))
            extra = sorted(set(meta) - PORTABLE)
            if extra:
                raise ValueError("non-portable keys %s" % extra)
            ln = next((l for l in front.splitlines() if l.startswith("description:")), "")
            bare = ln[12:].lstrip()[:1] not in ('"', "'", ">", "|")   # `#` truncates it
            print("%s %-40s desc %4d  front %4d" %
                  ("warn" if bare else "ok  ", d.name, len(desc), len(front)))
        except Exception as exc:
            bad += 1
            print("FAIL %-40s %s: %s" % (d.name, type(exc).__name__, exc))
print("%d failing" % bad)
sys.exit(min(bad, 125))
PY
```

`os.walk(..., followlinks=True)`, not a fixed-shape glob: `rglob("skills/*/SKILL.md")` fits
the plugin-cache layout but returned 0 under `~/.claude/skills` (python 3.9.13), and
`pathlib` never descends a symlink, so every installer-symlinked skill is invisible without
it. `warn` is not counted: a bare scalar parses today, and is flagged only because adding a
`#` or a `: ` to it later truncates it with no error.

## Gate B worksheet

Fill this in before judging, and judge from the printed description alone.

```
Description under test (printed, not remembered):
  <paste the output of the Phase 4 command>

MUST fire
  1. <prompt>                          -> fires? <yes|no>  because <clause it matched>
  2. <prompt>                          -> fires? <yes|no>  because <clause it matched>
  3. <prompt>                          -> fires? <yes|no>  because <clause it matched>
MUST NOT fire
  1. <prompt>  (owner: <skill>)        -> fires? <yes|no>  because <clause that excluded it>
  2. <prompt>                          -> fires? <yes|no>  because <clause that excluded it>
  3. <prompt>                          -> fires? <yes|no>  because <clause that excluded it>
Vocabulary check: <n> of 3 must-fire prompts use words from the description   (need >= 2)
  counts only if 5+ letters, from the `Use when` half, whole word, case-insensitive
Overlap check:    <n> of 3 must-NOT prompts sit in a documented overlap       (need exactly 1)
  counts when the prompt names a skill, a `SKILL.md`, or a neighbour by name
Verdict: <pass | back to Phase 2, because ...>
```
A "because" cell that cites the body rather than a clause of the description means the gate
was not run. A cell that says "it feels like it would" means the same thing.
