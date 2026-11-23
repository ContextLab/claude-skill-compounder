# 2026-11-23: a lesson is proposed with its pins

## What was wrong

Both open pull requests (#46 `verify-transient-before-waiting`, #47 `gemini-via-agy-cli`)
failed CI on both runners with the same three tests, and `main` was green. Each pull
request added one file, `lessons/<name>/SKILL.md`, which is all `compound promote --to
general --yes` committed. The suite held the shipped pool to four things a proposal did
not touch:

- the lessons table in `README.md` and the one in `docs/design.md` (`tests/test_docs.py`);
- the `SHIPPED` dict in `tests/test_general_pool.py`, with counts of 7 lessons and 3 guards;
- the `GUARDS` dict there (at least 5 commands a guard stops and 8 it passes);
- the assertion that on bash and Linux exactly two named lessons apply and no guard does.

So every proposal made through compound failed by construction. #47 is also a guard with
no platform or shell condition, which the last assertion had no room for.

## What changed

- The pins moved out of the test file into data, one file a lesson:
  `tests/pool/lessons/<name>.json` (`kind`, `platform`, `shell`, `stops`, `passes`), and
  `tests/pool/ordinary.json` (the everyday commands no shipped pattern may stop). The
  files were generated from the dicts, so the seven lessons carry the values they had.
- `tests/test_general_pool.py` reads its expectations from those files. Every assertion
  stayed. The counts are the number of pin files and of guard pins. The bash/Linux test
  asks, per lesson, whether the pins say it applies there. A new test checks each pin
  file's shape and still names the first seven lessons with the kind and condition they
  were written with.
- `compound promote --to general` takes `--pins FILE` and `--summary TEXT` for a lesson
  and refuses `--yes` without them (the plan says `NOT PROPOSABLE as it is`). It checks the
  pins against the lesson, scans them for credentials, and after the clone checks the
  lesson against the pool: `ordinary.json`, the other lessons' pins, the other guards'
  patterns. The pool's files are read as data; nothing of the clone is run. It commits
  the lesson, the pin file and a row in each table.
- `tests/test_pins.py` covers it against real bare repositories. Its last test proposes a
  guard with no condition into a copy of this checkout and runs that copy's
  `test_general_pool.py` and `test_docs.py` on the branch.
- Older tests that publish (`test_boundaries.py`, `test_decisions.py`, `test_promote.py`)
  pass pins through `pin_flags` and `echo_pin_flags` in `tests/test_support.py`.
- Documents: `docs/design.md`, `docs/guide.md`, `README.md`, `CONTRIBUTING.md`,
  `skills/learn/SKILL.md`, `.claude/CLAUDE.md`.

## Decisions

- Running the cloned pool's tests from `promote` was considered and dropped: it would
  execute a repository's code on the proposer's machine. The checks the suite makes of a
  new lesson are made in the CLI from the pool's data files.
- The pins of a new lesson are written by whoever proposes it, so they are less
  independent than hand-written ones. They are separate arguments, shown in the pull
  request body, and reviewed at merge.

## Not done

- A proposed skill still gets no table rows; the skills tables have two free-text cells.
- A proposed lesson with an attached file fails the pool's
  `test_a_shipped_lesson_carries_no_origin_and_is_as_the_cli_writes_it`, which holds a
  shipped lesson's directory to `SKILL.md` alone. `promote` does not refuse it.
- A lesson with a `probe` and no `match` is pinned as `lesson`.

## After the first push

The automated review of the first commit found that `promote` called `os.makedirs` on
`tests/pool/lessons` in the clone before checking for a link, so a pool whose `tests` was
a symbolic link got empty directories made where the link led. `_clone_dir` now looks at
each part before it is entered or made, and `pool_problems` reads the pool's pins only
through it. Two tests in `tests/test_pins.py` cover it.

## State

- `main`: the change and the link fix are pushed.
- #46 and #47 were completed in place on their branches: `main` merged in, the pin file
  added under `tests/pool/lessons/`, and a row added to each table. Both passed
  `test_general_pool.py` and `test_docs.py` locally before the push; the pull requests
  show what CI said.
- #47 is a guard with no platform or shell condition: it stops every call to `gemini`
  for every user. Whether that belongs in the general pool is a question for the merge.
- Both pull requests add a row after the last row of the same two tables, so the second
  one merged will conflict there and needs its rows moved.
