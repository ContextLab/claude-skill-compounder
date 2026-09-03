#!/usr/bin/env python3
"""bin/skillnote -- the cheapest tier: one line, in a file something will read.

NO MOCKS, the same as everywhere else here. Every test runs the real script through
``subprocess`` against a real temp HOME and a real state directory on a minimal PATH,
pins the clock with ``SKILLNOTE_NOW``, and reads the results back off disk. Nothing is
asserted from the script's own stdout that is not also checked against a file.

THREE THINGS THIS FILE IS PARTICULARLY FOR, because each is a defect that was cheap to
write and expensive to notice:

* The four file-writing rules are a SHELL TWIN of skill_compounder/installer.py. Two
  implementations of "back up, resolve the link, write atomically" will drift, and the
  drift is silent -- a backup beside the resolved path lands inside somebody's dotfiles
  git repo and nothing says so. ``SymlinkTest`` and ``BackupTest`` pin each rule against
  a real symlink into a real second directory.
* The memory scope's read-back is MEASURED, not assumed (docs/CLAUDE-CODE-BEHAVIOR.md, "A
  memory file written by another tool is read back, but only if MEMORY.md indexes it").
  What that measurement makes load-bearing is the index line, so a memory note that wrote
  a body file and no index line would be a note nothing will ever read. ``MemoryTest``
  asserts both halves and the exit-3 refusal that stands in for the unmeasured slug.
* The reminder store is JSONL and every reader takes one row per line. A pretty-printed
  row parses as eleven unparseable lines, so the reminder simply vanishes with no error
  at all -- which is what the first draft did. ``ReminderTest`` reads the raw bytes.

The ``--command`` arm depends on ``hooks/repeat-gate.sh --norm-of``, which is another
script's door. Those tests SKIP with a message when the checkout's repeat-gate does not
answer it, rather than failing: the flag arriving is a separate change, and a test that
goes red on its absence would report someone else's sequencing as this CLI's bug. The
skip is decided by RUNNING the gate, not by grepping it, so a flag that parses and does
not work is caught rather than assumed.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NOTE = REPO / "bin" / "skillnote"
FORGE = REPO / "bin" / "skillforge"
GATE = REPO / "hooks" / "repeat-gate.sh"

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
NOW = 1788000000          # 2026-08-29T10:40:00Z
LATER = NOW + 86400


# A stand-in for GNU coreutils' `stat` on a machine that ships the BSD one. It is not a
# mock of anything in this package: it is the OTHER PLATFORM'S TOOL, so an ordering that
# only works against BSD stat fails here the way it fails on ubuntu.
#
#   `-c FMT`  answers, which is the GNU spelling and the one BSD stat rejects outright.
#   `-f FMT`  is --file-system on GNU: the format is applied to a STATFS, `%m` is not a
#             directive it knows, and what comes out is filesystem prose on stdout with a
#             non-zero status. A caller that writes `stat -f %m f || stat -c %Y f` never
#             reaches the second form, captures the prose, and falls back to NOW.
#
# The answer itself is delegated to the REAL stat through whichever spelling that stat
# understands, so the shim never invents a value; only the interface is swapped.
# Duplicated verbatim in tests/test_insights.py and tests/test_session_review.py --
# these files shell out and share no imports, and this is the platform, not a helper.
SHIM_STAT = r"""#!/bin/bash
# An optional argv log, so a test can assert WHICH spelling was tried and in what order.
[ -n "${SHIM_STAT_LOG-}" ] && printf '%%s\n' "$*" >> "$SHIM_STAT_LOG"
_real_field() {   # $1 GNU format, $2 BSD format, $3 file
  _v="$("%(real)s" -c "$1" "$3" 2>/dev/null)"
  case "$_v" in ''|*[!0-9]*) _v="$("%(real)s" -f "$2" "$3" 2>/dev/null)" ;; esac
  printf '%%s' "$_v"
}
if [ "${1-}" = "-c" ]; then
  case "${2-}" in
    '%%Y') _out="$(_real_field %%Y %%m "${3-}")" ;;
    '%%a') _out="$(_real_field %%a %%OLp "${3-}")" ;;
    *) exit 1 ;;
  esac
  [ -n "$_out" ] || exit 1
  printf '%%s\n' "$_out"
  exit 0
fi
if [ "${1-}" = "-f" ]; then
  printf '  File: "%%s"\n  ID: 0 Namelen: 255 Type: ext2/ext3\n' "${3-}"
  exit 1
fi
exit 1
"""


def write_stat_shim(directory):
    """Put the GNU-mimicking `stat` first on a PATH built from `directory`."""
    real = shutil.which("stat", path=PATH)
    if real is None:                      # nothing in this repo can run without stat
        raise AssertionError("no stat on the test PATH")
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "stat"
    shim.write_text(SHIM_STAT % {"real": real})
    shim.chmod(0o755)
    return "%s:%s" % (directory, PATH)


def norm_of_available():
    """Does this checkout's repeat-gate actually answer `--norm-of`? Run it and see."""
    if not os.access(str(GATE), os.X_OK):
        return False
    try:
        r = subprocess.run([str(GATE), "--norm-of", "Bash"], input="./run_tests.sh\n",
                           capture_output=True, text=True, timeout=30,
                           env={"PATH": PATH, "HOME": "/tmp"})
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() != ""


HAVE_NORM_OF = norm_of_available()


class SkillnoteCase(unittest.TestCase):
    """A real temp world: HOME, state, a project with a git-less root, transcripts."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        # REALPATH, not the name tempfile handed back. On macOS /var is a symlink to
        # /private/var, so the script's own `pwd` reports the resolved form while Python
        # holds the unresolved one -- and every assertion comparing a recorded project
        # root against str(self.proj) fails on a difference that is not a defect.
        self.root = Path(os.path.realpath(self.tmpdir.name))
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.proj = self.root / "proj"
        self.transcripts = self.root / "projects"
        for d in (self.home, self.state, self.proj, self.transcripts):
            d.mkdir(parents=True)
        self.claude_md = self.proj / ".claude" / "CLAUDE.md"
        self.ledger = self.state / "ledger.jsonl"
        self.reminders = self.state / "reminders.jsonl"

    def tearDown(self):
        self.tmpdir.cleanup()

    def env(self, now=NOW, **extra):
        e = {"PATH": PATH, "HOME": str(self.home),
             "SKILL_COMPOUNDER_STATE": str(self.state),
             "SKILL_COMPOUNDER_TRANSCRIPTS": str(self.transcripts),
             "SKILLNOTE_NOW": str(now)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def note(self, *args, now=NOW, cwd=None, **extra):
        return subprocess.run([str(NOTE), *args], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60,
                              cwd=str(cwd or self.proj), env=self.env(now, **extra))

    def ok(self, *args, **kw):
        r = self.note(*args, **kw)
        self.assertEqual(r.returncode, 0,
                         "expected success, got %d:\n%s\n%s" % (r.returncode, r.stdout, r.stderr))
        return r

    def ledger_rows(self, event="note"):
        if not self.ledger.exists():
            return []
        out = []
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if event is None or row.get("event") == event:
                out.append(row)
        return out

    def block_lines(self, path=None):
        """The note lines inside the marker block, as written."""
        p = Path(path or self.claude_md)
        if not p.exists():
            return []
        keep, inside = [], False
        for line in p.read_text(encoding="utf-8").splitlines():
            if "skillnote:begin" in line:
                inside = True
                continue
            if "skillnote:end" in line:
                inside = False
                continue
            if inside and "<!-- id:" in line:
                keep.append(line)
        return keep


# --------------------------------------------------------------------- the marker block

class MarkerBlockTest(SkillnoteCase):

    def test_a_note_lands_in_one_block_with_the_date_and_the_id(self):
        r = self.ok("add", "--scope", "project", "Kill the runner and re-run the suite.",
                    "--why", "a filtered re-run hides a cross-file failure",
                    "--source", "verdict")
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertEqual(text.count("<!-- skillnote:begin -->"), 1)
        self.assertEqual(text.count("<!-- skillnote:end -->"), 1)
        self.assertIn("## Notes (skill-compounder)", text)
        lines = self.block_lines()
        self.assertEqual(len(lines), 1, text)
        self.assertIn("- **2026-08-29**", lines[0])
        self.assertIn("Kill the runner and re-run the suite.", lines[0])
        self.assertIn("source:verdict", lines[0])
        # --why goes in the comment, NOT in the visible sentence.
        visible = lines[0].split("<!-- id:")[0]
        self.assertNotIn("filtered re-run", visible)
        self.assertIn('why:"a filtered re-run hides a cross-file failure"', lines[0])
        self.assertIn("skillnote: recorded", r.stdout)

    def test_a_second_note_joins_the_same_block_and_never_opens_another(self):
        self.ok("add", "--scope", "project", "first lesson")
        self.ok("add", "--scope", "project", "second lesson")
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertEqual(text.count("<!-- skillnote:begin -->"), 1, text)
        self.assertEqual(len(self.block_lines()), 2, text)

    def test_the_block_is_appended_after_a_users_existing_prose(self):
        self.claude_md.parent.mkdir(parents=True, exist_ok=True)
        self.claude_md.write_text("# My project\n\nSome rules I wrote myself.\n",
                                  encoding="utf-8")
        self.ok("add", "--scope", "project", "a lesson")
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# My project\n"), text)
        self.assertIn("Some rules I wrote myself.", text)
        self.assertLess(text.index("Some rules I wrote myself."),
                        text.index("<!-- skillnote:begin -->"))

    def test_a_second_block_is_refused_by_name_and_line_number(self):
        """A file with two blocks is a merge accident. Guessing which one to append to
        loses notes into a block nobody reads, so it refuses and names both."""
        self.ok("add", "--scope", "project", "a lesson")
        before = self.claude_md.read_text(encoding="utf-8")
        with self.claude_md.open("a", encoding="utf-8") as fh:
            fh.write("\n<!-- skillnote:begin -->\n<!-- skillnote:end -->\n")
        after_tamper = self.claude_md.read_text(encoding="utf-8")
        r = self.note("add", "--scope", "project", "another lesson")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("2 '<!-- skillnote:begin -->' markers", r.stderr)
        self.assertIn("at lines 1, ", r.stderr)
        self.assertIn("Nothing was written", r.stderr)
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), after_tamper,
                         "a refusal must not have written anything")
        self.assertIn("a lesson", before)

    def test_a_prose_mention_of_the_marker_is_not_a_second_block(self):
        """Found live on 2026-09-02: .claude/CLAUDE.md MENTIONS `<!-- skillnote:begin -->`
        inside a sentence, and a substring grep counted that sentence as a block, so the
        first add succeeded and every later one refused for good. A marker is a line."""
        self.claude_md.parent.mkdir(parents=True, exist_ok=True)
        self.claude_md.write_text(
            "Prose that mentions the `<!-- skillnote:begin -->` marker inline, and also\n"
            "the `<!-- skillnote:end -->` one, without either being a block.\n",
            encoding="utf-8")
        self.ok("add", "--scope", "project", "first lesson")
        r = self.note("add", "--scope", "project", "second lesson")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertEqual(len(self.block_lines()), 2, text)
        # And the note went under the real block, not into the prose line.
        real_end = [i for i, l in enumerate(text.splitlines()) if l == "<!-- skillnote:end -->"]
        self.assertEqual(len(real_end), 1, text)
        self.assertIn("second lesson", text.splitlines()[real_end[0] - 1])

    def test_a_users_own_prose_inside_the_block_survives_a_remove(self):
        self.ok("add", "--scope", "project", "keep me")
        r = self.ok("add", "--scope", "project", "drop me")
        line = [l for l in self.block_lines() if "drop me" in l][0]
        drop_id = line.split("<!-- id:")[1].split()[0]
        self.assertEqual(drop_id, r.stdout.split("(")[1].split(")")[0],
                         "the id printed and the id written must be the same string")
        text = self.claude_md.read_text(encoding="utf-8")
        text = text.replace("<!-- skillnote:end -->",
                            "A sentence a human typed in here.\n<!-- skillnote:end -->")
        self.claude_md.write_text(text, encoding="utf-8")
        self.ok("remove", drop_id)
        after = self.claude_md.read_text(encoding="utf-8")
        self.assertIn("A sentence a human typed in here.", after,
                      "remove touched prose it did not write")
        self.assertIn("keep me", after)
        self.assertNotIn("drop me", after)
        self.assertIn("<!-- skillnote:begin -->", after,
                      "the block markers must survive a removal")


# ------------------------------------------------------------------------ the id

class IdTest(SkillnoteCase):

    def test_the_same_text_twice_writes_one_line_and_one_ledger_row(self):
        first = self.ok("add", "--scope", "project", "one lesson", "--source", "forge")
        rows_before = len(self.ledger_rows())
        second = self.ok("add", "--scope", "project", "one lesson", "--source", "forge")
        self.assertIn("already recorded", second.stdout)
        self.assertEqual(len(self.block_lines()), 1,
                         "the note was written twice:\n"
                         + self.claude_md.read_text(encoding="utf-8"))
        self.assertEqual(len(self.ledger_rows()), rows_before,
                         "a no-op add wrote a second ledger row")
        self.assertEqual(first.stdout.split("(")[1].split(")")[0],
                         second.stdout.split("(")[1].split(")")[0])

    def test_the_id_does_not_depend_on_the_machine_or_the_clock(self):
        """Stable across checkouts is the whole point: a note committed into a repo's
        .claude/CLAUDE.md has to be removable from any clone."""
        a = self.ok("add", "--scope", "project", "portable lesson", now=NOW)
        first = a.stdout.split("(")[1].split(")")[0]
        second_root = self.root / "elsewhere"
        (second_root / ".claude").mkdir(parents=True)
        b = self.ok("add", "--scope", "project", "portable lesson",
                    "--project", str(second_root), now=LATER)
        self.assertEqual(first, b.stdout.split("(")[1].split(")")[0])

    def test_the_scope_is_part_of_the_id(self):
        a = self.ok("add", "--scope", "project", "same words")
        (self.home / ".claude").mkdir(parents=True, exist_ok=True)
        b = self.ok("add", "--scope", "global", "same words")
        self.assertNotEqual(a.stdout.split("(")[1].split(")")[0],
                            b.stdout.split("(")[1].split(")")[0])

    def test_remove_deletes_exactly_one_line(self):
        self.ok("add", "--scope", "project", "alpha")
        self.ok("add", "--scope", "project", "beta")
        self.ok("add", "--scope", "project", "gamma")
        target = [l for l in self.block_lines() if "beta" in l][0]
        rid = target.split("<!-- id:")[1].split()[0]
        r = self.ok("remove", rid)
        self.assertIn("removed %s" % rid, r.stdout)
        remaining = self.block_lines()
        self.assertEqual(len(remaining), 2)
        self.assertTrue(any("alpha" in l for l in remaining))
        self.assertTrue(any("gamma" in l for l in remaining))
        self.assertFalse(any("beta" in l for l in remaining))
        removals = [r for r in self.ledger_rows() if r.get("action") == "remove"]
        self.assertEqual(len(removals), 1)
        self.assertEqual(removals[0]["id"], rid)

    def test_removing_an_unknown_id_refuses_and_says_where_it_looked(self):
        r = self.note("remove", "n0x0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no note or reminder with id 'n0x0'", r.stderr)
        self.assertIn(".claude/CLAUDE.md", r.stderr)
        self.assertIn("reminders.jsonl", r.stderr)


# ------------------------------------------------------------------------- the clock

class ClockTest(SkillnoteCase):

    def test_skillnote_now_pins_both_the_visible_date_and_the_ledger_ts(self):
        self.ok("add", "--scope", "project", "pinned", now=NOW)
        self.assertIn("- **2026-08-29**", self.block_lines()[0])
        row = [r for r in self.ledger_rows() if r.get("text") == "pinned"][0]
        self.assertEqual(row["ts"], NOW)

    def test_a_different_pin_moves_the_date(self):
        self.ok("add", "--scope", "project", "later", now=LATER)
        self.assertIn("- **2026-08-30**", self.block_lines()[0])

    def test_a_junk_clock_is_refused_by_name_rather_than_reaching_jq(self):
        r = self.note("add", "--scope", "project", "x", now="not-a-number")
        self.assertEqual(r.returncode, 2)
        self.assertIn("SKILLNOTE_NOW must be epoch seconds", r.stderr)
        self.assertFalse(self.claude_md.exists())

    def test_this_script_reads_its_own_clock_and_nobody_elses(self):
        """A new script needs its OWN clock: pinning someone else's does nothing to it,
        and a test that pinned the wrong one would silently measure the wall clock."""
        r = self.note("add", "--scope", "project", "not pinned by CI_NOW", now=NOW,
                      CI_NOW="1", SKILLFORGE_NOW="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = [r for r in self.ledger_rows() if "not pinned" in r.get("text", "")][0]
        self.assertEqual(row["ts"], NOW)


# ------------------------------------------------------------------------- refusals

class RefusalTest(SkillnoteCase):

    def test_empty_text_is_refused(self):
        r = self.note("add", "--scope", "project", "")
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs the note text", r.stderr)

    def test_an_unknown_scope_names_the_three(self):
        r = self.note("add", "--scope", "sideways", "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown --scope 'sideways'", r.stderr)
        for name in ("project", "global", "memory"):
            self.assertIn(name, r.stderr)

    def test_remind_with_no_match_rule_is_refused(self):
        r = self.note("add", "--remind", "--scope", "project", "a reminder")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--keyword", r.stderr)
        self.assertIn("never fires and is invisible", r.stderr)
        self.assertFalse(self.reminders.exists())

    def test_remind_into_the_memory_scope_is_refused(self):
        r = self.note("add", "--remind", "--scope", "memory", "x", "--keyword", "k")
        self.assertEqual(r.returncode, 2)
        self.assertIn("a memory file is not a reminder store", r.stderr)

    def test_an_unknown_option_names_the_help(self):
        r = self.note("add", "--scope", "project", "--nonsense", "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown option '--nonsense'", r.stderr)

    def test_an_unknown_subcommand_exits_two(self):
        r = self.note("frobnicate")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown subcommand", r.stderr)

    def test_help_exits_zero_and_states_the_measured_read_back(self):
        r = self.note("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("skillnote add", r.stdout)
        self.assertIn("readback", r.stdout)
        self.assertIn("0 of 3", r.stdout,
                      "the help must carry the measurement, not a promise")


# ---------------------------------------------------------------- backup / atomic write

class BackupTest(SkillnoteCase):

    def backups(self, path=None):
        p = Path(path or self.claude_md)
        return sorted(q.name for q in p.parent.glob(p.name + ".bak-skill-compounder-*"))

    def test_the_first_write_of_a_new_file_backs_up_nothing(self):
        self.ok("add", "--scope", "project", "first")
        self.assertEqual(self.backups(), [],
                         "there was no prior content to preserve")

    def test_a_change_to_an_existing_file_is_backed_up_with_the_installers_prefix(self):
        self.ok("add", "--scope", "project", "first")
        self.ok("add", "--scope", "project", "second")
        b = self.backups()
        self.assertEqual(len(b), 1, b)
        self.assertTrue(b[0].startswith("CLAUDE.md.bak-skill-compounder-"), b)
        self.assertIn("20260829-", b[0], "the backup stamp must follow the pinned clock")
        # The backup holds the PRE-change content.
        saved = (self.claude_md.parent / b[0]).read_text(encoding="utf-8")
        self.assertIn("first", saved)
        self.assertNotIn("second", saved)

    def test_an_identical_backup_is_never_written_twice(self):
        """A no-op `add` must not accumulate copies; repeated adds of the same text are
        the common case for a hook that fires on every CANDIDATE."""
        self.ok("add", "--scope", "project", "first")
        self.ok("add", "--scope", "project", "second")
        self.assertEqual(len(self.backups()), 1)
        for _ in range(4):
            self.ok("add", "--scope", "project", "second")   # already recorded
        self.assertEqual(len(self.backups()), 1,
                         "a no-op add wrote another identical backup")

    def test_a_same_second_collision_suffixes_rather_than_clobbering(self):
        """The stamp has second resolution and the clock here is frozen, so every backup
        in this test would otherwise be written to one name -- and the one overwritten is
        the pre-change copy, the only one worth keeping."""
        self.ok("add", "--scope", "project", "n0")
        for i in range(1, 4):
            self.ok("add", "--scope", "project", "n%d" % i)
        b = self.backups()
        self.assertEqual(len(b), 3, b)
        self.assertEqual(len(set(b)), 3)
        # The oldest still holds the oldest content.
        oldest = (self.claude_md.parent / b[0]).read_text(encoding="utf-8")
        self.assertIn("n0", oldest)
        self.assertNotIn("n1", oldest)

    def test_backups_are_pruned_to_ten_and_only_our_own_are_touched(self):
        theirs = self.claude_md.parent
        theirs.mkdir(parents=True, exist_ok=True)
        self.ok("add", "--scope", "project", "n0")
        foreign = theirs / "CLAUDE.md.bak-someone-else-20200101"
        foreign.write_text("not ours\n", encoding="utf-8")
        older = theirs / "CLAUDE.md.backup"
        older.write_text("also not ours\n", encoding="utf-8")
        for i in range(1, 16):
            self.ok("add", "--scope", "project", "n%d" % i)
        self.assertEqual(len(self.backups()), 10,
                         "backups were not pruned to MAX_BACKUPS: %r" % self.backups())
        self.assertTrue(foreign.exists(), "a foreign backup was pruned")
        self.assertTrue(older.exists(), "an unrelated file was pruned")

    def test_no_temp_file_is_left_behind_on_the_happy_path(self):
        self.ok("add", "--scope", "project", "clean")
        leftovers = [p.name for p in self.claude_md.parent.iterdir()
                     if p.name.startswith(".skillnote.")]
        self.assertEqual(leftovers, [], leftovers)

    def test_an_unwritable_directory_refuses_and_leaves_nothing_behind(self):
        d = self.claude_md.parent
        d.mkdir(parents=True, exist_ok=True)
        self.ok("add", "--scope", "project", "before")
        before = self.claude_md.read_text(encoding="utf-8")
        # try/finally rather than addCleanup: cleanups run AFTER tearDown, by which time
        # the temp tree is gone and the restore raises FileNotFoundError -- and a
        # directory left at 0o500 would take out tearDown's own cleanup first.
        os.chmod(d, 0o500)
        try:
            r = self.note("add", "--scope", "project", "after")
        finally:
            os.chmod(d, 0o700)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), before,
                         "the original must be intact, never truncated")
        leftovers = [p.name for p in d.iterdir() if p.name.startswith(".skillnote.")]
        self.assertEqual(leftovers, [], "a temp file survived a failed write: %r" % leftovers)


class ModePreservationTest(SkillnoteCase):
    """`write_atomic` writes a NEW file and renames it over the old one, so the old
    file's permissions have to be read and re-applied or every note silently widens or
    narrows the user's CLAUDE.md. `mode_of` is what reads them, and it had never been
    exercised against GNU coreutils -- the platform where `stat -f` means
    --file-system rather than "use this format".

    Nothing was actually wrong with the answer: mode_of validates its RESULT against an
    octal shape instead of trusting the exit status, so GNU's filesystem prose fell
    through to the `-c '%a'` form and the right mode came back. What was wrong is that
    nothing tested it, and the call order asked GNU stat for a filesystem report on every
    single write. These two tests pin the answer AND the order, so the ordering that is
    correct on both platforms is the one the next author copies.
    """

    def test_an_existing_files_mode_survives_a_note_under_a_gnu_stat(self):
        self.claude_md.parent.mkdir(parents=True, exist_ok=True)
        self.claude_md.write_text("# My project\n", encoding="utf-8")
        os.chmod(str(self.claude_md), 0o640)
        shim_path = write_stat_shim(self.root / "gnu-stat")
        self.ok("add", "--scope", "project", "a lesson", PATH=shim_path)
        self.assertIn("a lesson", self.claude_md.read_text(encoding="utf-8"))
        self.assertEqual(oct(os.stat(str(self.claude_md)).st_mode & 0o7777), oct(0o640),
                         "the mode was lost across the atomic write")

    def test_the_gnu_spelling_is_tried_first_and_the_bsd_one_is_never_reached(self):
        """The ordering, observed rather than asserted from the source. On GNU the `-f`
        form can only ever be a doomed process whose stdout happens not to look octal;
        asking for it first is the shape that broke bin/skillinsight and
        hooks/session-review.sh outright."""
        self.claude_md.parent.mkdir(parents=True, exist_ok=True)
        self.claude_md.write_text("# My project\n", encoding="utf-8")
        os.chmod(str(self.claude_md), 0o640)
        shim_path = write_stat_shim(self.root / "gnu-stat")
        log = self.root / "stat-calls.log"
        self.ok("add", "--scope", "project", "a lesson",
                PATH=shim_path, SHIM_STAT_LOG=str(log))
        calls = [l for l in log.read_text().splitlines() if l.strip()]
        self.assertTrue(calls, "the shim was never called; this test proved nothing")
        self.assertTrue(calls[0].startswith("-c "),
                        "the first stat spelling tried was %r" % calls[0])
        self.assertEqual([c for c in calls if c.startswith("-f ")], [],
                         "GNU stat was asked for a filesystem report: %s" % calls)


class SymlinkTest(SkillnoteCase):
    """stow and chezmoi present CLAUDE.md as a symlink into a dotfiles repo. Renaming
    ONTO the link deletes it and orphans the source, with exit 0 and no warning."""

    def setUp(self):
        super().setUp()
        self.dotfiles = self.root / "dotfiles"
        self.dotfiles.mkdir()
        self.source = self.dotfiles / "CLAUDE.md"
        self.source.write_text("# my dotfiles copy\n", encoding="utf-8")
        self.claude_md.parent.mkdir(parents=True, exist_ok=True)
        self.claude_md.symlink_to(self.source)

    def test_the_link_survives_and_the_source_gets_the_block(self):
        self.ok("add", "--scope", "project", "through the link")
        self.assertTrue(self.claude_md.is_symlink(), "the symlink was replaced by a file")
        self.assertEqual(os.path.realpath(str(self.claude_md)),
                         os.path.realpath(str(self.source)))
        body = self.source.read_text(encoding="utf-8")
        self.assertIn("# my dotfiles copy", body)
        self.assertIn("through the link", body)

    def test_the_backup_lands_beside_the_link_not_inside_the_dotfiles_repo(self):
        self.ok("add", "--scope", "project", "one")
        self.ok("add", "--scope", "project", "two")
        here = sorted(p.name for p in self.claude_md.parent.iterdir())
        there = sorted(p.name for p in self.dotfiles.iterdir())
        self.assertTrue(any(n.startswith("CLAUDE.md.bak-skill-compounder-") for n in here),
                        here)
        self.assertEqual(there, ["CLAUDE.md"],
                         "a backup was sprinkled into the dotfiles repo: %r" % there)

    def test_a_relative_link_is_followed_too(self):
        self.claude_md.unlink()
        os.symlink(os.path.relpath(str(self.source), str(self.claude_md.parent)),
                   str(self.claude_md))
        self.ok("add", "--scope", "project", "relative")
        self.assertTrue(self.claude_md.is_symlink())
        self.assertIn("relative", self.source.read_text(encoding="utf-8"))

    def test_a_symlink_loop_does_not_hang(self):
        """The 40-iteration cap. A loop with no cap is a CLI that never returns and
        prints nothing at all, which is worse than any error."""
        self.claude_md.unlink()
        a = self.claude_md
        b = self.claude_md.parent / "OTHER.md"
        os.symlink(str(b), str(a))
        os.symlink(str(a), str(b))
        r = self.note("add", "--scope", "project", "looped")   # timeout=60 in self.note
        self.assertIn(r.returncode, (0, 2, 3), r.stdout + r.stderr)


# ---------------------------------------------------------------------- global scope

class GlobalScopeTest(SkillnoteCase):
    """The claude directory is resolved in ONE order, shared with claude_dir() in
    bin/skillforge. Two resolutions that disagree is the drift that function prevents."""

    def test_the_override_wins_over_everything(self):
        elsewhere = self.root / "override"
        elsewhere.mkdir()
        manifest = self.state / "install-manifest.json"
        manifest.write_text(json.dumps({"claude_dir": str(self.root / "manifested")}),
                            encoding="utf-8")
        (self.root / "manifested").mkdir()
        self.ok("add", "--scope", "global", "an override",
                SKILLNOTE_CLAUDE_DIR=str(elsewhere))
        self.assertTrue((elsewhere / "CLAUDE.md").exists())
        self.assertFalse((self.root / "manifested" / "CLAUDE.md").exists())

    def test_the_manifest_wins_over_the_home_default(self):
        manifested = self.root / "manifested"
        manifested.mkdir()
        (self.state / "install-manifest.json").write_text(
            json.dumps({"claude_dir": str(manifested)}), encoding="utf-8")
        self.ok("add", "--scope", "global", "from the manifest")
        self.assertIn("from the manifest",
                      (manifested / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".claude" / "CLAUDE.md").exists())

    def test_the_home_default_is_the_last_resort(self):
        self.ok("add", "--scope", "global", "from home")
        self.assertIn("from home",
                      (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_claude_config_dir_is_honoured_when_no_manifest_exists(self):
        cfg = self.root / "cfg"
        cfg.mkdir()
        self.ok("add", "--scope", "global", "from the env", CLAUDE_CONFIG_DIR=str(cfg))
        self.assertIn("from the env", (cfg / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_the_global_scope_never_writes_into_the_project(self):
        self.ok("add", "--scope", "global", "global only")
        self.assertFalse(self.claude_md.exists())


# ---------------------------------------------------------------------- memory scope

class MemoryTest(SkillnoteCase):

    def slug(self, path=None):
        return str(path or self.proj).replace("/", "-")

    def memdir(self, path=None):
        return self.transcripts / self.slug(path) / "memory"

    def test_an_absent_slug_directory_refuses_with_three_and_writes_nothing(self):
        """The slug transform is measured only for paths with no dot and no space in
        them. A directory built from a guessed slug is one Claude Code will never read,
        which is worse than a refusal because it looks like it worked."""
        r = self.note("add", "--scope", "memory", "a memory note")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("no such project directory", r.stderr)
        self.assertIn(self.slug(), r.stderr, "the refusal must name the slug it computed")
        self.assertEqual(list(self.transcripts.iterdir()), [],
                         "a refusal created a directory anyway")

    def test_the_frontmatter_is_the_shape_read_off_a_real_memory_file(self):
        (self.transcripts / self.slug()).mkdir(parents=True)
        self.ok("add", "--scope", "memory", "Move fast, everything on main",
                "--why", "no PR ceremony until the prototype has outside users",
                "--source", "session", CLAUDE_CODE_SESSION_ID="abc-123")
        f = self.memdir() / "move-fast-everything-on-main.md"
        self.assertTrue(f.exists(), sorted(p.name for p in self.memdir().iterdir()))
        body = f.read_text(encoding="utf-8")
        self.assertTrue(body.startswith("---\n"), body[:40])
        self.assertIn("name: move-fast-everything-on-main\n", body)
        self.assertIn('description: "no PR ceremony until the prototype has outside users"\n',
                      body)
        self.assertIn("  node_type: memory\n", body)
        self.assertIn("  type: project\n", body)
        self.assertIn("  originSessionId: abc-123\n", body)
        self.assertIn("  modified: 2026-08-29T", body)
        self.assertIn(".000Z\n", body)
        self.assertIn("Move fast, everything on main", body)

    def test_the_session_id_is_omitted_rather_than_written_empty(self):
        (self.transcripts / self.slug()).mkdir(parents=True)
        self.ok("add", "--scope", "memory", "no session here")
        body = (self.memdir() / "no-session-here.md").read_text(encoding="utf-8")
        self.assertNotIn("originSessionId", body)

    def test_exactly_one_index_line_is_appended_in_claude_codes_shape(self):
        """The index line is the load-bearing half. Measured 2026-09-02: a memory file
        MEMORY.md does not list is never seen -- 0 of 3 runs."""
        (self.transcripts / self.slug()).mkdir(parents=True)
        self.ok("add", "--scope", "memory", "Move fast, everything on main",
                "--why", "no PR ceremony until the prototype has outside users")
        index = (self.memdir() / "MEMORY.md").read_text(encoding="utf-8")
        lines = [l for l in index.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, index)
        self.assertEqual(
            lines[0],
            "- [Move fast, everything on main](move-fast-everything-on-main.md) "
            "\u2014 no PR ceremony until the prototype has outside users")
        self.assertIn("\u2014", lines[0], "an em dash, not a hyphen")

    def test_a_second_memory_note_appends_one_more_index_line(self):
        (self.transcripts / self.slug()).mkdir(parents=True)
        self.ok("add", "--scope", "memory", "first memory")
        self.ok("add", "--scope", "memory", "second memory")
        index = (self.memdir() / "MEMORY.md").read_text(encoding="utf-8")
        self.assertEqual(len([l for l in index.splitlines() if l.strip()]), 2, index)
        self.assertIn("(first-memory.md)", index)
        self.assertIn("(second-memory.md)", index)

    def test_the_same_memory_note_twice_is_a_no_op(self):
        (self.transcripts / self.slug()).mkdir(parents=True)
        self.ok("add", "--scope", "memory", "just once")
        r = self.ok("add", "--scope", "memory", "just once")
        self.assertIn("already recorded", r.stdout)
        index = (self.memdir() / "MEMORY.md").read_text(encoding="utf-8")
        self.assertEqual(len([l for l in index.splitlines() if l.strip()]), 1, index)

    def test_the_ledger_row_records_the_measured_read_back(self):
        (self.transcripts / self.slug()).mkdir(parents=True)
        self.ok("add", "--scope", "memory", "measured, not promised")
        row = [r for r in self.ledger_rows() if r.get("scope") == "memory"][0]
        self.assertEqual(row["readback"], "via-index")
        self.assertEqual(row["kind"], "note")

    def test_removing_a_memory_note_takes_its_index_line_and_keeps_a_copy(self):
        (self.transcripts / self.slug()).mkdir(parents=True)
        r = self.ok("add", "--scope", "memory", "goes away")
        rid = r.stdout.split("(")[1].split(")")[0]
        self.ok("add", "--scope", "memory", "stays put")
        self.ok("remove", rid)
        self.assertFalse((self.memdir() / "goes-away.md").exists())
        index = (self.memdir() / "MEMORY.md").read_text(encoding="utf-8")
        self.assertNotIn("(goes-away.md)", index)
        self.assertIn("(stays-put.md)", index)
        kept = list(self.memdir().glob("goes-away.md.bak-skill-compounder-*"))
        self.assertEqual(len(kept), 1,
                         "nothing is ever destructively removed: %r"
                         % sorted(p.name for p in self.memdir().iterdir()))
        self.assertIn("goes away", kept[0].read_text(encoding="utf-8"))


# ------------------------------------------------------------------- the reminder store

class ReminderTest(SkillnoteCase):

    def rows(self):
        if not self.reminders.exists():
            return []
        out = []
        for line in self.reminders.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def test_a_reminder_is_one_json_object_on_one_line(self):
        """JSONL, and every reader takes one row per line. A pretty-printed row parses as
        eleven unparseable lines and the reminder vanishes with no error at all."""
        self.ok("add", "--remind", "--scope", "project", "Kill the runner",
                "--keyword", "TEST", "--keyword", "Fail", "--path", "tests/*.py",
                "--source", "verdict")
        raw = self.reminders.read_text(encoding="utf-8")
        self.assertEqual(len(raw.strip().splitlines()), 1, raw)
        row = json.loads(raw.strip())
        self.assertEqual(row["text"], "Kill the runner")
        self.assertEqual(row["match"]["keywords"], ["test", "fail"],
                         "keywords are lowercased at write time")
        self.assertEqual(row["match"]["paths"], ["tests/*.py"])
        self.assertEqual(row["match"]["commands"], [])
        self.assertEqual(row["scope"], str(self.proj))
        self.assertEqual(row["created"], NOW)
        self.assertEqual(row["hits"], 0)
        self.assertEqual(row["source"], "verdict")

    def test_a_global_reminder_records_the_literal_word(self):
        self.ok("add", "--remind", "--scope", "global", "everywhere", "--keyword", "k")
        self.assertEqual(self.rows()[0]["scope"], "global")

    def test_a_reminder_writes_no_claude_md(self):
        """--remind writes a reminder INSTEAD of a note. A reminder arrives; a note waits
        to be read. Writing both would double every promoted candidate."""
        self.ok("add", "--remind", "--scope", "project", "arriving", "--keyword", "k")
        self.assertFalse(self.claude_md.exists())

    def test_a_reminder_and_a_note_with_the_same_words_coexist(self):
        a = self.ok("add", "--scope", "project", "one sentence")
        b = self.ok("add", "--remind", "--scope", "project", "one sentence",
                    "--keyword", "k")
        self.assertNotEqual(a.stdout.split("(")[1].split(")")[0],
                            b.stdout.split("(")[1].split(")")[0])
        self.assertEqual(len(self.block_lines()), 1)
        self.assertEqual(len(self.rows()), 1)

    def test_the_same_reminder_twice_is_a_no_op(self):
        self.ok("add", "--remind", "--scope", "project", "once", "--keyword", "k")
        r = self.ok("add", "--remind", "--scope", "project", "once", "--keyword", "k")
        self.assertIn("already recorded", r.stdout)
        self.assertEqual(len(self.rows()), 1)

    def test_removal_is_a_tombstone_and_never_a_rewrite(self):
        """Same doctrine as `skillrepeat forget`: the store is written by a hook nobody
        watches, and one bad expression rewriting it could erase an hour of observation."""
        r = self.ok("add", "--remind", "--scope", "project", "tombstone me",
                    "--keyword", "k")
        rid = r.stdout.split("(")[1].split(")")[0]
        original = self.reminders.read_text(encoding="utf-8")
        self.ok("remove", rid)
        after = self.reminders.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(original),
                        "the original row was rewritten rather than tombstoned")
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1], {"id": rid, "t": "remove", "ts": NOW})

    def test_a_tombstoned_reminder_is_gone_from_list(self):
        r = self.ok("add", "--remind", "--scope", "project", "vanishes", "--keyword", "k")
        rid = r.stdout.split("(")[1].split(")")[0]
        self.ok("add", "--remind", "--scope", "project", "survives", "--keyword", "k")
        self.ok("remove", rid)
        out = self.ok("list", "--scope", "remind").stdout
        self.assertNotIn("vanishes", out)
        self.assertIn("survives", out)

    def test_the_store_is_a_sibling_of_the_reminders_directory_not_inside_it(self):
        """<state>/reminders/ is where hooks/compound-improvement.sh keeps per-session
        counters, and its prune_stale_state() sweeps INSIDE that directory. A store
        placed under it would be swept away by an unrelated hook."""
        self.ok("add", "--remind", "--scope", "project", "sibling", "--keyword", "k")
        self.assertEqual(self.reminders.parent, self.state)
        self.assertFalse((self.state / "reminders").is_file())
        self.assertNotIn("reminders/", str(self.reminders.relative_to(self.state)))

    @unittest.skipUnless(HAVE_NORM_OF,
                         "hooks/repeat-gate.sh in this checkout does not answer "
                         "--norm-of; the --command arm cannot be exercised")
    def test_a_command_is_stored_as_a_shared_signature_not_a_literal(self):
        self.ok("add", "--remind", "--scope", "project", "use the runner",
                "--command", "./run_tests.sh")
        cmds = self.rows()[0]["match"]["commands"]
        self.assertEqual(len(cmds), 1, cmds)
        # Stored BARE, exactly as --norm-of prints it. This test used to pin a "Bash\n"
        # prefix, and that pin was the bug: hooks/remind.sh compares the bare signature, so
        # every --command reminder was silent in a real session (found 2026-09-02).
        self.assertNotIn("\n", cmds[0], "no tool prefix, no newline: %r" % cmds[0])
        expected = subprocess.run([str(GATE), "--norm-of", "Bash"],
                                  input="./run_tests.sh", capture_output=True, text=True,
                                  timeout=30, env={"PATH": PATH, "HOME": str(self.home)})
        self.assertEqual(cmds[0], expected.stdout.strip(),
                         "the CLI must store what the gate's own normaliser returns, so "
                         "the two can never disagree about what a call is")

    @unittest.skipUnless(HAVE_NORM_OF, "repeat-gate does not answer --norm-of")
    def test_two_commands_differing_only_in_masked_parts_share_one_signature(self):
        """Non-vacuity for the test above: if the normaliser were the identity, storing
        a signature and storing the literal would be indistinguishable."""
        def sig(cmd):
            return subprocess.run([str(GATE), "--norm-of", "Bash"], input=cmd,
                                  capture_output=True, text=True, timeout=30,
                                  env={"PATH": PATH, "HOME": str(self.home)}).stdout.strip()
        a, b = sig('gh issue comment 19 --body "x"'), sig('gh issue comment 4271 --body "y"')
        self.assertEqual(a, b, "the gate's normaliser does not mask what it claims to")
        self.assertNotEqual(a, sig("gh pr list"))

    def test_the_command_flag_refuses_with_three_when_the_normaliser_is_missing(self):
        """A literal command stored as if it were a signature builds a reminder that
        silently never fires -- the failure the no-match-rule refusal exists to prevent.
        Proved by putting a copy of the CLI where ../hooks/repeat-gate.sh does not exist,
        which is also what an installed-without-the-hooks checkout looks like."""
        lonely = self.root / "lonelybin"
        lonely.mkdir()
        shutil.copy2(str(NOTE), str(lonely / "skillnote"))
        r = subprocess.run([str(lonely / "skillnote"), "add", "--remind", "--scope",
                            "project", "x", "--command", "./run_tests.sh"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=60, cwd=str(self.proj), env=self.env())
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("--norm-of", r.stderr)
        self.assertFalse(self.reminders.exists(),
                         "a refusal wrote a reminder that could never fire")


# ------------------------------------------------------------------------------ list

class ListTest(SkillnoteCase):

    def test_list_reads_back_what_add_wrote(self):
        self.ok("add", "--scope", "project", "a project lesson", "--source", "forge",
                "--why", "because of a dead end")
        rows = json.loads(self.ok("list", "--scope", "project", "--json").stdout)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["text"], "a project lesson")
        self.assertEqual(rows[0]["date"], "2026-08-29")
        self.assertEqual(rows[0]["source"], "forge")
        self.assertEqual(rows[0]["why"], "because of a dead end")
        self.assertEqual(rows[0]["kind"], "note")
        self.assertEqual(rows[0]["scope"], "project")

    def test_a_why_holding_a_quote_survives_the_round_trip(self):
        self.ok("add", "--scope", "project", "quoting",
                "--why", 'the runner said "no such file" and meant it')
        rows = json.loads(self.ok("list", "--scope", "project", "--json").stdout)
        self.assertEqual(rows[0]["why"], 'the runner said "no such file" and meant it')

    def test_every_scope_shows_up_in_a_bare_list(self):
        (self.transcripts / str(self.proj).replace("/", "-")).mkdir(parents=True)
        self.ok("add", "--scope", "project", "p note")
        self.ok("add", "--scope", "global", "g note")
        self.ok("add", "--scope", "memory", "m note")
        self.ok("add", "--remind", "--scope", "project", "r note", "--keyword", "k")
        rows = json.loads(self.ok("list", "--json").stdout)
        kinds = sorted((r["kind"], r["scope"]) for r in rows)
        self.assertEqual(len(rows), 4, rows)
        self.assertIn(("note", "project"), kinds)
        self.assertIn(("note", "global"), kinds)
        self.assertIn(("note", "memory"), kinds)
        self.assertIn(("reminder", str(self.proj)), kinds)

    def test_an_empty_world_lists_nothing_and_exits_zero(self):
        r = self.ok("list")
        self.assertIn("No notes or reminders recorded", r.stdout)
        self.assertIn(str(self.claude_md), r.stdout)

    def test_hits_are_derived_from_the_hit_log_and_never_stored(self):
        """The hook that records a hit must never rewrite the append-only store, so the
        count is derived. A stored counter would need a rewrite per hit."""
        r = self.ok("add", "--remind", "--scope", "project", "counted", "--keyword", "k")
        rid = r.stdout.split("(")[1].split(")")[0]
        (self.state / "remind").mkdir(parents=True, exist_ok=True)
        with (self.state / "remind" / "hits.jsonl").open("w", encoding="utf-8") as fh:
            for i in range(3):
                fh.write(json.dumps({"id": rid, "ts": NOW + i, "session": "s%d" % i,
                                     "event": "UserPromptSubmit"}) + "\n")
        rows = json.loads(self.ok("list", "--scope", "remind", "--json").stdout)
        self.assertEqual(rows[0]["hits"], 3)
        self.assertEqual(json.loads(self.reminders.read_text().strip())["hits"], 0,
                         "the store itself must be untouched")

    def test_an_unknown_list_scope_names_the_four(self):
        r = self.note("list", "--scope", "sideways")
        self.assertEqual(r.returncode, 2)
        for name in ("project", "global", "memory", "remind"):
            self.assertIn(name, r.stderr)

    def test_a_foreign_line_in_the_store_does_not_take_out_the_reader(self):
        self.ok("add", "--remind", "--scope", "project", "good row", "--keyword", "k")
        with self.reminders.open("a", encoding="utf-8") as fh:
            fh.write("this is not json at all\n")
            fh.write('{"half":\n')
        r = self.ok("list", "--scope", "remind")
        self.assertIn("good row", r.stdout)


# ---------------------------------------------------------------------------- ledger

class LedgerTest(SkillnoteCase):

    def test_a_note_row_carries_the_fields_the_design_names(self):
        self.ok("add", "--scope", "project", "recorded properly", "--why", "a reason",
                "--source", "verdict", CLAUDE_CODE_SESSION_ID="sess-9")
        row = [r for r in self.ledger_rows() if r.get("text") == "recorded properly"][0]
        self.assertEqual(row["event"], "note")
        self.assertEqual(row["action"], "add")
        self.assertEqual(row["kind"], "note")
        self.assertEqual(row["scope"], "project")
        self.assertEqual(row["target"], str(self.claude_md))
        self.assertEqual(row["why"], "a reason")
        self.assertEqual(row["source"], "verdict")
        self.assertEqual(row["project"], str(self.proj))
        self.assertEqual(row["session"], "sess-9")
        self.assertEqual(row["confidence"], "measured")
        self.assertIs(row["backfilled"], False)
        self.assertEqual(row["ts"], NOW)

    def test_empty_optional_fields_are_omitted_rather_than_written_blank(self):
        self.ok("add", "--scope", "project", "bare")
        row = [r for r in self.ledger_rows() if r.get("text") == "bare"][0]
        for absent in ("why", "source", "session", "readback"):
            self.assertNotIn(absent, row, "%s was written empty" % absent)

    def test_a_reminder_row_says_reminder(self):
        self.ok("add", "--remind", "--scope", "project", "a reminder", "--keyword", "k")
        row = [r for r in self.ledger_rows() if r.get("text") == "a reminder"][0]
        self.assertEqual(row["kind"], "reminder")
        self.assertEqual(row["target"], str(self.reminders))

    def test_the_ledger_gets_a_horizon_row_before_the_first_note(self):
        """A ledger whose FIRST row is a note with no horizon reads as "complete from
        here", which is false. skillforge owns that function; this calls it."""
        self.ok("add", "--scope", "project", "first ever")
        rows = self.ledger_rows(event=None)
        self.assertTrue(rows, "nothing was written to the ledger at all")
        self.assertEqual(rows[0]["event"], "horizon",
                         "the horizon row must come first:\n%r" % rows)
        self.assertEqual(rows[1]["event"], "note")

    def test_a_note_is_still_recorded_when_skillforge_is_too_old_to_answer(self):
        """The third branch, and the one a version skew actually produces.

        `skillforge horizon` is newer than `skillforge`. Measured 2026-09-02 against the
        real build at commit 03773ad -- the last one before the subcommand landed -- the
        older CLI exits **2** on `skillforge horizon` and writes nothing. The sibling here
        reproduces that exit code rather than that whole build: what the branch turns on
        is the status, and pinning it to a 3000-line file frozen at one commit would pin
        the wrong thing. A note must still be recorded, because a CLI that recorded
        nothing when a sibling was out of date teaches its callers to stop calling it.
        """
        lonely = self.root / "oldbin"
        lonely.mkdir()
        shutil.copy2(str(NOTE), str(lonely / "skillnote"))
        old = lonely / "skillforge"
        old.write_text("#!/bin/sh\necho 'skillforge: unknown subcommand' >&2\nexit 2\n",
                       encoding="utf-8")
        old.chmod(0o755)
        r = subprocess.run([str(lonely / "skillnote"), "add", "--scope", "project",
                            "old forge beside me"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=60, cwd=str(self.proj), env=self.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = self.ledger_rows(event=None)
        self.assertEqual([x["event"] for x in rows], ["note"],
                         "no horizon row is expected, and the note must still be there")
        self.assertIn("old forge beside me", self.claude_md.read_text(encoding="utf-8"))

    def test_a_note_is_still_recorded_when_skillforge_cannot_be_found(self):
        """Best-effort in both directions: a note is worth more than a horizon row, and a
        CLI that recorded nothing because a sibling was missing teaches its callers to
        stop calling it."""
        lonely = self.root / "lonelybin"
        lonely.mkdir()
        shutil.copy2(str(NOTE), str(lonely / "skillnote"))
        r = subprocess.run([str(lonely / "skillnote"), "add", "--scope", "project",
                            "no forge here"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=60, cwd=str(self.proj), env=self.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = self.ledger_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "no forge here")
        self.assertIn("no forge here", self.claude_md.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the detached caller

class ProjectFlagTest(SkillnoteCase):
    """hooks/session-review.sh runs DETACHED, after its session ended, from a working
    directory that means nothing. --project is the only reason it can write anywhere
    useful, so it is tested from a cwd that is deliberately somewhere else."""

    def test_project_overrides_the_working_directory(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.ok("add", "--scope", "project", "--project", str(self.proj),
                "from far away", cwd=elsewhere)
        self.assertIn("from far away", self.claude_md.read_text(encoding="utf-8"))
        self.assertFalse((elsewhere / ".claude" / "CLAUDE.md").exists())

    def test_the_ledger_project_field_follows_the_flag(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.ok("add", "--scope", "project", "--project", str(self.proj), "tagged",
                cwd=elsewhere)
        row = [r for r in self.ledger_rows() if r.get("text") == "tagged"][0]
        self.assertEqual(row["project"], str(self.proj))

    def test_remove_honours_the_flag_too(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        r = self.ok("add", "--scope", "project", "--project", str(self.proj),
                    "removable", cwd=elsewhere)
        rid = r.stdout.split("(")[1].split(")")[0]
        self.ok("remove", rid, "--project", str(self.proj), cwd=elsewhere)
        self.assertNotIn("removable", self.claude_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
