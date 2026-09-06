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


# ==================================================================== the lesson tier
#
# A fail-then-fix is worth nothing unless the fix arrives BEFORE the same call is made
# again. `--lesson <sig>` is the one command that writes both halves, so these tests drive
# both: the store hooks/repeat-gate.sh writes, and the hook hooks/remind.sh reads.
#
# THE STORE ROWS ARE THE REAL SHAPE, field for field, copied off
# ~/.claude/skill-compounder/repeats/index.jsonl (read-only, never written by the suite).
# Only `norm` is computed rather than transcribed, by running the real normaliser: a
# hand-typed signature would keep this file passing on the day production stopped matching,
# which is exactly how the "Bash\n" prefix defect survived its own tests on 2026-09-02.

REMIND = REPO / "hooks" / "remind.sh"

FAIL_SIG = "c1273399358x407-e728136712x48"
FAIL_CMD = "cd /tmp/forge && python3 setup.py install 2>&1 | tail -20"
RECOVER_CMD = "cd /tmp/forge && python3 -m pip install -e ."


def norm_of(command):
    """What `hooks/repeat-gate.sh --norm-of Bash` prints for a command. Run, not guessed."""
    r = subprocess.run([str(GATE), "--norm-of", "Bash"], input=command,
                       capture_output=True, text=True, timeout=60,
                       env={"PATH": PATH, "HOME": "/tmp"})
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class LessonCase(SkillnoteCase):
    """Adds a real repeat store to the temp world, plus a way to drive the real hook."""

    def setUp(self):
        super().setUp()
        self.repeats = self.state / "repeats" / "index.jsonl"
        self.repeats.parent.mkdir(parents=True, exist_ok=True)

    # The two row shapes, verbatim from the live store: a `fail` carries
    # ck/ec/err/norm/cmd/tool/session/tuid, a `recover` the same minus ec and err.
    def fail_row(self, sig=FAIL_SIG, cmd=FAIL_CMD, tool="Bash", ts=1787780622, norm=None,
                 session="s-aaa"):
        return {"t": "fail", "ts": ts, "sig": sig, "ck": sig.split("-")[0],
                "ec": "Exit code <N> ModuleNotFoundError: No module named setuptools",
                "tool": tool, "norm": norm if norm is not None else norm_of(cmd),
                "cmd": cmd,
                "err": "Exit code 1\nModuleNotFoundError: No module named setuptools",
                "session": session, "tuid": "toolu_01Apwx6o1ykGxLBuVrsoi9Dq"}

    def recover_row(self, sig=FAIL_SIG, cmd=RECOVER_CMD, ts=1787780627, session="s-aaa"):
        return {"t": "recover", "ts": ts, "sig": sig, "ck": sig.split("-")[0],
                "tool": "Bash", "norm": norm_of(cmd), "cmd": cmd,
                "session": session, "tuid": "toolu_01LCF4N6NKptBXEWoEEwZEcs"}

    def write_store(self, *rows):
        with self.repeats.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def seed(self, **kw):
        """The ordinary case: one fail and its recovery, the pair the design describes."""
        self.write_store(self.fail_row(**kw), self.recover_row())

    def reminder_rows(self):
        if not self.reminders.exists():
            return []
        return [json.loads(l) for l in self.reminders.read_text(encoding="utf-8").splitlines()
                if l.strip()]

    # ------------------------------------------------------------------ the real hook
    def run_remind(self, command, cwd=None, session="s-live"):
        """Drive hooks/remind.sh for real, on a PreToolUse Bash payload. `input=` is not
        optional: the script reads its payload with `payload="$(cat)"` and hangs without
        stdin."""
        payload = {"hook_event_name": "PreToolUse", "session_id": session,
                   "tool_use_id": "toolu_%s" % session,
                   "cwd": str(cwd or self.proj),
                   "transcript_path": str(self.root / "t.jsonl"),
                   "permission_mode": "acceptEdits", "tool_name": "Bash",
                   "tool_input": {"command": command, "description": "d"}}
        env = {"PATH": PATH, "HOME": str(self.home),
               "SKILL_COMPOUNDER_STATE": str(self.state), "REMIND_NOW": str(NOW + 100)}
        return subprocess.run(["bash", str(REMIND)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=180)

    def delivered(self, r):
        self.assertEqual(r.returncode, 0, "a hook must never exit non-zero: " + r.stderr)
        self.assertTrue(r.stdout.strip(), "expected a reminder, got silence")
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


@unittest.skipUnless(HAVE_NORM_OF,
                     "hooks/repeat-gate.sh does not answer --norm-of in this checkout")
class LessonTest(LessonCase):

    TEXT = "setup.py install needs setuptools here; pip install -e . is the one that works."

    def test_one_command_writes_the_line_the_reminder_and_one_ledger_row(self):
        self.seed()
        r = self.ok("add", "--lesson", FAIL_SIG, self.TEXT, "--source", "session")
        line = self.block_lines()[0]
        self.assertIn("- **2026-08-29**", line)
        self.assertIn(self.TEXT, line)
        self.assertIn("lesson:%s" % FAIL_SIG, line)

        rows = self.reminder_rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["match"]["commands"], [norm_of(FAIL_CMD)],
                         "keyed on the FAILING call, exactly as the store spells it")
        self.assertEqual(rows[0]["text"], self.TEXT)
        self.assertEqual(rows[0]["scope"], str(self.proj))
        self.assertEqual(rows[0]["lesson_sig"], FAIL_SIG)

        led = [x for x in self.ledger_rows() if x.get("id") != rows[0]["id"]]
        led = [x for x in led if x.get("text") == self.TEXT]
        self.assertEqual(len(led), 1, "one ledger row for the pair, not two: %r" % led)
        self.assertEqual(led[0]["lesson_sig"], FAIL_SIG)
        self.assertEqual(led[0]["reminder_id"], rows[0]["id"])
        self.assertEqual(led[0]["action"], "add")
        self.assertIn("reminder", r.stdout)

    def test_the_hook_actually_delivers_it_before_that_command_runs_again(self):
        """The whole point, and the half a hand-written fixture cannot prove: the real
        writer into the real reader. A signature stored in any other spelling matches
        nothing and says nothing about it."""
        self.seed()
        self.ok("add", "--lesson", FAIL_SIG, self.TEXT)
        ctx = self.delivered(self.run_remind(FAIL_CMD))
        self.assertIn("pip install -e .", ctx)

    def test_a_different_command_is_silent(self):
        self.seed()
        self.ok("add", "--lesson", FAIL_SIG, self.TEXT)
        r = self.run_remind("git status --porcelain")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "", r.stdout)

    def test_the_recovery_is_not_what_it_is_keyed_on(self):
        """Keying on the fix would state the lesson only once the session had already
        found it. The reminder has to arrive before the failure, not after."""
        self.seed()
        self.ok("add", "--lesson", FAIL_SIG, self.TEXT)
        self.assertNotEqual(norm_of(RECOVER_CMD), norm_of(FAIL_CMD))
        r = self.run_remind(RECOVER_CMD)
        self.assertEqual(r.stdout.strip(), "", "keyed on the recovery, not the failure")

    def test_the_newest_fail_row_wins(self):
        """A signature that failed again after a recovery failed for a reason the older
        row does not describe."""
        later = "cd /tmp/forge && python3 setup.py bdist_wheel 2>&1 | tail -5"
        self.write_store(self.fail_row(ts=1787780622),
                         self.recover_row(),
                         self.fail_row(cmd=later, ts=1787790000, session="s-bbb"))
        self.ok("add", "--lesson", FAIL_SIG, self.TEXT)
        self.assertEqual(self.reminder_rows()[0]["match"]["commands"], [norm_of(later)])

    def test_an_unknown_signature_is_refused_and_writes_nothing(self):
        self.seed()
        r = self.note("add", "--lesson", "c1x1-e2x2", self.TEXT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("skillrepeat list", r.stderr)
        self.assertIn("c1x1-e2x2", r.stderr)
        self.assertFalse(self.claude_md.exists(), "a refusal must not write a CLAUDE.md")
        self.assertFalse(self.reminders.exists(), "a refusal must not write a reminder")
        self.assertEqual([x for x in self.ledger_rows() if x.get("text")], [])

    def test_an_absent_store_is_the_same_refusal(self):
        r = self.note("add", "--lesson", FAIL_SIG, self.TEXT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("skillrepeat list", r.stderr)
        self.assertFalse(self.claude_md.exists())

    def test_a_signature_with_only_a_recover_row_is_refused(self):
        """`recover` is the fix. Keying a reminder on it would fire after the fix and
        never before the failure, so a signature with no `fail` row is not a lesson."""
        self.write_store(self.recover_row())
        r = self.note("add", "--lesson", FAIL_SIG, self.TEXT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("skillrepeat list", r.stderr)

    def test_a_fail_row_on_another_tool_is_refused_by_name(self):
        """hooks/remind.sh's command arm reads .tool_input.command, so nothing but a Bash
        call can ever match a command signature. Writing the row anyway would build a
        reminder that is silent forever -- the failure --remind's own refusal prevents."""
        self.write_store(self.fail_row(tool="Skill", norm="Skill(gh-pr)"))
        r = self.note("add", "--lesson", FAIL_SIG, self.TEXT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Skill", r.stderr)
        self.assertIn("--keyword", r.stderr, "the refusal must name the way through")
        self.assertFalse(self.claude_md.exists())
        self.assertFalse(self.reminders.exists())

    def test_lesson_with_remind_is_refused(self):
        self.seed()
        r = self.note("add", "--lesson", FAIL_SIG, "--remind", "--keyword", "k", self.TEXT)
        self.assertEqual(r.returncode, 2)
        self.assertIn("drop --remind", r.stderr)

    def test_lesson_into_the_memory_scope_is_refused(self):
        self.seed()
        r = self.note("add", "--lesson", FAIL_SIG, "--scope", "memory", self.TEXT)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--scope project", r.stderr)

    def test_a_global_lesson_is_scoped_global_and_fires_in_another_project(self):
        self.seed()
        self.ok("add", "--lesson", FAIL_SIG, "--scope", "global", self.TEXT)
        self.assertEqual(self.reminder_rows()[0]["scope"], "global")
        elsewhere = self.root / "somewhere-else"
        elsewhere.mkdir()
        ctx = self.delivered(self.run_remind(FAIL_CMD, cwd=elsewhere))
        self.assertIn("pip install -e .", ctx)

    def test_a_project_lesson_does_not_fire_in_a_sibling_project(self):
        self.seed()
        self.ok("add", "--lesson", FAIL_SIG, self.TEXT)
        sibling = self.root / "other"
        sibling.mkdir()
        r = self.run_remind(FAIL_CMD, cwd=sibling)
        self.assertEqual(r.stdout.strip(), "", r.stdout)

    def test_list_marks_it_as_a_lesson(self):
        self.seed()
        self.ok("add", "--lesson", FAIL_SIG, self.TEXT)
        rows = json.loads(self.ok("list", "--scope", "project", "--json").stdout)
        self.assertEqual(rows[0]["lesson"], FAIL_SIG)
        self.assertIn("[lesson %s]" % FAIL_SIG, self.ok("list", "--scope", "project").stdout)

    def test_a_plain_note_has_no_lesson_marker(self):
        self.ok("add", "--scope", "project", "an ordinary note")
        rows = json.loads(self.ok("list", "--scope", "project", "--json").stdout)
        self.assertIsNone(rows[0]["lesson"])

    def test_a_why_mentioning_lesson_is_not_read_as_the_field(self):
        """`why` is written last so the token fields are read out of what precedes it."""
        self.ok("add", "--scope", "project", "tricky",
                "--why", "the log said lesson:none and source:none")
        rows = json.loads(self.ok("list", "--scope", "project", "--json").stdout)
        self.assertIsNone(rows[0]["lesson"])
        self.assertIsNone(rows[0]["source"])
        self.assertEqual(rows[0]["why"], "the log said lesson:none and source:none")


# ==================================================================== attachments

class AttachTest(LessonCase):

    def setUp(self):
        super().setUp()
        self.script = self.proj / "fix.sh"
        self.script.write_text("#!/bin/sh\necho fixed\n", encoding="utf-8")
        self.script.chmod(0o755)

    def lessons_dir(self, note_id, root=None):
        return (root or (self.proj / ".claude")) / "lessons" / note_id

    def test_the_file_is_copied_and_the_line_links_it(self):
        r = self.ok("add", "--scope", "project", "the script that worked",
                    "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        dest = self.lessons_dir(nid) / "fix.sh"
        self.assertTrue(dest.is_file(), r.stdout)
        self.assertEqual(dest.read_text(encoding="utf-8"), "#!/bin/sh\necho fixed\n")
        self.assertIn("(attached: .claude/lessons/%s/fix.sh)" % nid, self.block_lines()[0])
        self.assertTrue(self.script.is_file(), "a copy, never a move")

    def test_the_executable_bit_survives(self):
        """A lesson whose script arrives without its mode is a lesson whose one command
        does not run."""
        r = self.ok("add", "--scope", "project", "keeps its mode", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        self.assertTrue(os.access(str(self.lessons_dir(nid) / "fix.sh"), os.X_OK))

    def test_a_non_executable_file_stays_non_executable(self):
        data = self.proj / "notes.txt"
        data.write_text("plain\n", encoding="utf-8")
        data.chmod(0o644)
        r = self.ok("add", "--scope", "project", "a data file", "--attach", "notes.txt")
        nid = r.stdout.split("(")[1].split(")")[0]
        self.assertFalse(os.access(str(self.lessons_dir(nid) / "notes.txt"), os.X_OK))

    def test_two_attachments_both_land_and_both_appear_on_the_line(self):
        other = self.proj / "probe.py"
        other.write_text("print(1)\n", encoding="utf-8")
        r = self.ok("add", "--scope", "project", "two files",
                    "--attach", "fix.sh", "--attach", "probe.py")
        nid = r.stdout.split("(")[1].split(")")[0]
        self.assertTrue((self.lessons_dir(nid) / "fix.sh").is_file())
        self.assertTrue((self.lessons_dir(nid) / "probe.py").is_file())
        line = self.block_lines()[0]
        self.assertIn("lessons/%s/fix.sh)" % nid, line)
        self.assertIn("lessons/%s/probe.py)" % nid, line)

    def test_a_path_outside_the_tree_and_home_is_refused(self):
        outside = self.root / "outside.txt"
        outside.write_text("x\n", encoding="utf-8")
        r = self.note("add", "--scope", "project", "nope", "--attach", str(outside))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("outside both the working tree", r.stderr)
        self.assertFalse(self.claude_md.exists(), "nothing written")
        self.assertFalse((self.proj / ".claude" / "lessons").exists())

    def test_a_path_under_home_is_allowed(self):
        keep = self.home / "keep.sh"
        keep.write_text("#!/bin/sh\n", encoding="utf-8")
        r = self.ok("add", "--scope", "project", "from home", "--attach", str(keep))
        nid = r.stdout.split("(")[1].split(")")[0]
        self.assertTrue((self.lessons_dir(nid) / "keep.sh").is_file())

    def test_a_missing_file_is_refused(self):
        r = self.note("add", "--scope", "project", "nope", "--attach", "no-such.sh")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("not a regular file", r.stderr)
        self.assertFalse(self.claude_md.exists())

    def test_a_directory_is_refused(self):
        (self.proj / "adir").mkdir()
        r = self.note("add", "--scope", "project", "nope", "--attach", "adir")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("not a regular file", r.stderr)

    def test_an_existing_attachment_is_never_overwritten(self):
        r = self.ok("add", "--scope", "project", "first", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        dest = self.lessons_dir(nid) / "fix.sh"
        before = dest.read_text(encoding="utf-8")
        # A second note whose id happens to be the same directory can only be produced by
        # attaching under the same id, so the collision is forced directly.
        self.script.write_text("#!/bin/sh\necho different\n", encoding="utf-8")
        r2 = self.note("add", "--scope", "project", "first", "--attach", "fix.sh")
        self.assertEqual(r2.returncode, 0, "the same text is a no-op, not a refusal")
        self.assertIn("attachments were NOT copied", r2.stdout)
        self.assertEqual(dest.read_text(encoding="utf-8"), before)

    def test_a_forced_destination_collision_refuses_before_copying(self):
        """The refusal is decided in pass one, so `--attach a --attach b` with b already
        present leaves a uncopied: a partial copy plus an exit 2 is the state that makes
        the retry refuse on its own leftovers."""
        nid = None
        r = self.ok("add", "--scope", "project", "seed", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        # Pre-plant the SECOND file's destination under the id the next note will get.
        second = self.proj / "second.py"
        second.write_text("print(2)\n", encoding="utf-8")
        third = self.proj / "third.py"
        third.write_text("print(3)\n", encoding="utf-8")
        nid2 = None
        probe = self.note("list", "--scope", "project", "--json")
        del probe, nid
        # Work out the id the new text will take by writing it once, then undoing it.
        r2 = self.ok("add", "--scope", "project", "collides")
        nid2 = [x["id"] for x in json.loads(
            self.ok("list", "--scope", "project", "--json").stdout)
            if x["text"] == "collides"][0]
        self.ok("remove", nid2)
        planted = self.lessons_dir(nid2)
        planted.mkdir(parents=True)
        (planted / "second.py").write_text("already here\n", encoding="utf-8")
        r3 = self.note("add", "--scope", "project", "collides",
                       "--attach", "third.py", "--attach", "second.py")
        self.assertEqual(r3.returncode, 2, r3.stdout + r3.stderr)
        self.assertIn("already exists", r3.stderr)
        self.assertFalse((planted / "third.py").exists(),
                         "the first file was copied before the second was checked")
        self.assertEqual((planted / "second.py").read_text(encoding="utf-8"),
                         "already here\n")
        del r2

    def test_the_ledger_row_lists_the_relative_paths(self):
        r = self.ok("add", "--scope", "project", "with a file", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        row = [x for x in self.ledger_rows() if x.get("id") == nid][0]
        self.assertEqual(row["attachments"], [".claude/lessons/%s/fix.sh" % nid])

    def test_a_note_with_no_attachment_has_no_attachments_field(self):
        self.ok("add", "--scope", "project", "bare note")
        row = [x for x in self.ledger_rows() if x.get("text") == "bare note"][0]
        self.assertNotIn("attachments", row)

    def test_list_counts_them(self):
        other = self.proj / "probe.py"
        other.write_text("print(1)\n", encoding="utf-8")
        self.ok("add", "--scope", "project", "counted",
                "--attach", "fix.sh", "--attach", "probe.py")
        rows = json.loads(self.ok("list", "--scope", "project", "--json").stdout)
        self.assertEqual(rows[0]["attachments"], 2)
        self.assertIn("[2 attached]", self.ok("list", "--scope", "project").stdout)

    def test_a_global_attachment_is_named_home_anchored_not_relative(self):
        """A GLOBAL line is read from every repository on the machine, so a relative
        `.claude/lessons/...` names a directory in whichever project happens to be open --
        which does not exist. Measured 2026-09-05: a session in another project was handed
        exactly that line and had to run `find ~/.claude` for the file."""
        r = self.ok("add", "--scope", "global", "global lesson", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        self.assertTrue((self.home / ".claude" / "lessons" / nid / "fix.sh").is_file())
        line = self.block_lines(self.home / ".claude" / "CLAUDE.md")[0]
        self.assertIn("(attached: ~/.claude/lessons/%s/fix.sh)" % nid, line)
        self.assertNotIn("(attached: .claude/lessons/", line,
                         "the relative form is the one that does not resolve")

    def test_the_home_anchored_path_really_resolves_to_the_file(self):
        """The point of the form, driven rather than asserted: expand the `~` against
        $HOME the way a reader would and open what it names."""
        r = self.ok("add", "--scope", "global", "resolvable", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        line = self.block_lines(self.home / ".claude" / "CLAUDE.md")[0]
        ref = line.split("(attached: ")[1].split(")")[0]
        self.assertTrue(ref.startswith("~/"), ref)
        dest = self.home / ref[2:]
        self.assertTrue(dest.is_file(), "%s does not name a file" % ref)
        self.assertEqual(dest.read_text(encoding="utf-8"), "#!/bin/sh\necho fixed\n")
        del nid

    def test_the_global_ledger_row_carries_the_same_form_as_the_line(self):
        """Two records of one location that disagree is the drift this repo is built
        around avoiding. They come from one function, and this is what says so."""
        r = self.ok("add", "--scope", "global", "one form", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        row = [x for x in self.ledger_rows() if x.get("id") == nid][0]
        self.assertEqual(row["attachments"], ["~/.claude/lessons/%s/fix.sh" % nid])
        line = self.block_lines(self.home / ".claude" / "CLAUDE.md")[0]
        self.assertIn("(attached: %s)" % row["attachments"][0], line)

    def test_a_claude_dir_outside_home_gets_the_absolute_path(self):
        """No `~` can name it, and this refuses to guess: the absolute path resolves from
        anywhere too, which is the property the form exists for."""
        elsewhere = self.root / "elsewhere-claude"
        r = self.ok("add", "--scope", "global", "outside home", "--attach", "fix.sh",
                    SKILLNOTE_CLAUDE_DIR=str(elsewhere))
        nid = r.stdout.split("(")[1].split(")")[0]
        line = self.block_lines(elsewhere / "CLAUDE.md")[0]
        self.assertIn("(attached: %s/lessons/%s/fix.sh)" % (elsewhere, nid), line)
        self.assertNotIn("~", line)

    def test_a_memory_attachment_is_anchored_too(self):
        """The memory file lives under the transcripts root, which no session's working
        directory is ever inside, so a path relative to its own directory names a base the
        reader has no way to know. Here the transcripts root is outside $HOME, so the
        answer is the absolute path; the test below drives the ordinary case."""
        slug = str(self.proj).replace("/", "-")
        (self.transcripts / slug).mkdir(parents=True)
        r = self.ok("add", "--scope", "memory", "memory lesson", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        mdir = self.transcripts / slug / "memory"
        self.assertTrue((mdir / "lessons" / nid / "fix.sh").is_file())
        body = (mdir / "memory-lesson.md").read_text(encoding="utf-8")
        self.assertIn("(attached: %s/lessons/%s/fix.sh)" % (mdir, nid), body)
        self.assertNotIn("(attached: lessons/", body)

    def test_a_memory_attachment_under_home_is_written_with_a_tilde(self):
        """The ordinary machine: the transcripts root IS `~/.claude/projects`."""
        transcripts = self.home / ".claude" / "projects"
        slug = str(self.proj).replace("/", "-")
        (transcripts / slug).mkdir(parents=True)
        r = self.ok("add", "--scope", "memory", "memory lesson", "--attach", "fix.sh",
                    SKILL_COMPOUNDER_TRANSCRIPTS=str(transcripts))
        nid = r.stdout.split("(")[1].split(")")[0]
        body = (transcripts / slug / "memory" / "memory-lesson.md").read_text(encoding="utf-8")
        self.assertIn("(attached: ~/.claude/projects/%s/memory/lessons/%s/fix.sh)"
                      % (slug, nid), body)

    def test_a_project_attachment_is_still_relative(self):
        """The half that was already right, pinned so the fix cannot swing past it: a
        project note IS read from the repository root, and `.claude/lessons/...` is what a
        reader sitting there would type."""
        r = self.ok("add", "--scope", "project", "project lesson", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        line = self.block_lines()[0]
        self.assertIn("(attached: .claude/lessons/%s/fix.sh)" % nid, line)
        self.assertNotIn("~", line)

    def test_remind_with_attach_is_refused(self):
        r = self.note("add", "--remind", "--scope", "project", "r", "--keyword", "k",
                      "--attach", "fix.sh")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no line to link an attachment from", r.stderr)
        self.assertFalse(self.reminders.exists())

    @unittest.skipUnless(HAVE_NORM_OF, "repeat-gate does not answer --norm-of")
    def test_a_lesson_carries_its_attachment_and_still_fires(self):
        self.seed()
        r = self.ok("add", "--lesson", FAIL_SIG, "the fix is in the script",
                    "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        self.assertTrue((self.lessons_dir(nid) / "fix.sh").is_file())
        row = [x for x in self.ledger_rows() if x.get("id") == nid][0]
        self.assertEqual(row["lesson_sig"], FAIL_SIG)
        self.assertEqual(row["attachments"], [".claude/lessons/%s/fix.sh" % nid])
        self.assertIn("the fix is in the script", self.delivered(self.run_remind(FAIL_CMD)))


# ==================================================================== promote

class PromoteTest(LessonCase):

    # LONGER THAN SIXTY CHARACTERS ON PURPOSE. The tombstone keeps only the first 60, so
    # a shorter sentence would make `assertNotIn(TEXT, the project file)` pass whether the
    # note moved or not -- the assertion that says this is a move and not a copy.
    TEXT = ("the runner has to be killed before the suite is re-run, or a "
            "cross-file failure hides")

    def global_md(self):
        return self.home / ".claude" / "CLAUDE.md"

    def add_project_note(self, text=None, attach=None):
        args = ["add", "--scope", "project", text or self.TEXT]
        if attach:
            args += ["--attach", attach]
        r = self.ok(*args)
        return r.stdout.split("(")[1].split(")")[0]

    def promote(self, nid, to="global", **kw):
        return self.note("promote", nid, "--to", to, now=LATER, **kw)

    def test_the_line_moves_and_the_project_keeps_a_one_line_tombstone(self):
        nid = self.add_project_note()
        before = self.block_lines()[0]
        r = self.promote(nid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        moved = self.block_lines(self.global_md())
        self.assertEqual(len(moved), 1, moved)
        self.assertEqual(moved[0], before, "same line, same id, same date")

        tomb = self.block_lines()
        self.assertEqual(len(tomb), 1, tomb)
        self.assertEqual(tomb[0],
                         "- **2026-08-29** moved to global: %s <!-- id:%s moved:global -->"
                         % (self.TEXT[:60].rstrip(), nid))
        self.assertNotIn(self.TEXT, self.claude_md.read_text(encoding="utf-8"))

    def test_the_tombstone_is_truncated_at_sixty_characters(self):
        long = ("a lesson whose sentence runs on well past sixty characters so the "
                "tombstone has to cut it")
        nid = self.add_project_note(long)
        self.promote(nid)
        tomb = self.block_lines()[0]
        head = tomb.split("moved to global: ")[1].split(" <!-- id:")[0]
        self.assertEqual(head, long[:60].rstrip())
        self.assertIn(long, self.block_lines(self.global_md())[0],
                      "the full sentence lives at the destination")

    def test_it_is_a_move_and_never_a_copy(self):
        nid = self.add_project_note()
        self.promote(nid)
        proj_text = self.claude_md.read_text(encoding="utf-8")
        self.assertNotIn(self.TEXT, proj_text,
                         "a copy left behind is two records that will disagree")

    def test_the_attachments_directory_moves_with_it(self):
        script = self.proj / "fix.sh"
        script.write_text("#!/bin/sh\necho fixed\n", encoding="utf-8")
        script.chmod(0o755)
        nid = self.add_project_note(attach="fix.sh")
        self.assertTrue((self.proj / ".claude" / "lessons" / nid / "fix.sh").is_file())
        self.promote(nid)
        dest = self.home / ".claude" / "lessons" / nid / "fix.sh"
        self.assertTrue(dest.is_file())
        self.assertTrue(os.access(str(dest), os.X_OK), "the mode travels too")
        self.assertFalse((self.proj / ".claude" / "lessons" / nid).exists(),
                         "moved, not copied")

    def test_a_destination_directory_already_there_refuses_before_anything_moves(self):
        script = self.proj / "fix.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        nid = self.add_project_note(attach="fix.sh")
        planted = self.home / ".claude" / "lessons" / nid
        planted.mkdir(parents=True)
        (planted / "other.txt").write_text("mine\n", encoding="utf-8")
        r = self.promote(nid)
        # Exit 2, the same code --attach uses for the same refusal: a destination that is
        # already occupied is fixed by moving it, not by a different environment.
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("already exists", r.stderr)
        self.assertIn(self.TEXT, self.claude_md.read_text(encoding="utf-8"),
                      "the note stays put when the move cannot complete")
        self.assertFalse(self.global_md().exists())
        self.assertTrue((self.proj / ".claude" / "lessons" / nid / "fix.sh").is_file())

    @unittest.skipUnless(HAVE_NORM_OF, "repeat-gate does not answer --norm-of")
    def test_the_reminder_becomes_global_and_the_old_row_is_tombstoned(self):
        self.seed()
        r = self.ok("add", "--lesson", FAIL_SIG, self.TEXT)
        nid = r.stdout.split("(")[1].split(")")[0]
        old = self.reminder_rows()[0]["id"]
        self.assertEqual(self.reminder_rows()[0]["scope"], str(self.proj))

        p = self.promote(nid)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rows = self.reminder_rows()
        self.assertEqual(rows[1], {"id": old, "t": "remove", "ts": LATER},
                         "append-only: a tombstone, never a rewrite")
        self.assertEqual(rows[2]["scope"], "global")
        self.assertNotEqual(rows[2]["id"], old, "the id is a hash OVER the scope")
        self.assertEqual(rows[2]["match"]["commands"], [norm_of(FAIL_CMD)])
        self.assertEqual(rows[2]["lesson_sig"], FAIL_SIG)

        # And the real hook now delivers it from a project it was never recorded in.
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.assertIn(self.TEXT, self.delivered(self.run_remind(FAIL_CMD, cwd=elsewhere)))

    @unittest.skipUnless(HAVE_NORM_OF, "repeat-gate does not answer --norm-of")
    def test_exactly_one_reminder_is_live_after_the_move(self):
        """hooks/remind.sh does not de-duplicate by id, so a promotion that left both rows
        live would state the same lesson twice."""
        self.seed()
        r = self.ok("add", "--lesson", FAIL_SIG, self.TEXT)
        self.promote(r.stdout.split("(")[1].split(")")[0])
        live = json.loads(self.ok("list", "--scope", "remind", "--json").stdout)
        self.assertEqual(len(live), 1, live)
        self.assertEqual(live[0]["scope"], "global")

    def test_the_attachment_path_is_rewritten_to_the_home_anchored_form(self):
        """The line is about to be read from a file every repository sees, so the one
        thing rewritten on the way across is the attachment path. Left alone it would say
        `.claude/lessons/...`, which from any project but this one names nothing."""
        script = self.proj / "fix.sh"
        script.write_text("#!/bin/sh\necho fixed\n", encoding="utf-8")
        r = self.ok("add", "--scope", "project", "movable with a file", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        self.assertIn("(attached: .claude/lessons/%s/fix.sh)" % nid, self.block_lines()[0])
        self.ok("promote", nid, "--to", "global")
        line = [l for l in self.block_lines(self.home / ".claude" / "CLAUDE.md")
                if nid in l][0]
        self.assertIn("(attached: ~/.claude/lessons/%s/fix.sh)" % nid, line)
        self.assertNotIn("(attached: .claude/lessons/", line)
        dest = self.home / ".claude" / "lessons" / nid / "fix.sh"
        self.assertTrue(dest.is_file(), "the rewritten path must name the moved file")

    def test_a_promoted_line_with_no_attachment_is_carried_across_untouched(self):
        """Non-vacuity for the rewrite: it must fire on the suffix and on nothing else."""
        r = self.ok("add", "--scope", "project", "movable, no file")
        nid = r.stdout.split("(")[1].split(")")[0]
        before = self.block_lines()[0]
        self.ok("promote", nid, "--to", "global")
        after = [l for l in self.block_lines(self.home / ".claude" / "CLAUDE.md")
                 if nid in l][0]
        self.assertEqual(before, after)

    def test_a_ledger_row_records_the_promotion(self):
        nid = self.add_project_note()
        self.promote(nid)
        rows = [x for x in self.ledger_rows() if x.get("action") == "promote"]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["event"], "note")
        self.assertEqual(rows[0]["id"], nid)
        self.assertEqual(rows[0]["scope"], "global")
        self.assertEqual(rows[0]["from_scope"], "project")
        self.assertEqual(rows[0]["from_target"], str(self.claude_md))
        self.assertEqual(rows[0]["target"], str(self.global_md()))
        self.assertEqual(rows[0]["ts"], LATER)

    def test_to_project_is_refused(self):
        nid = self.add_project_note()
        r = self.promote(nid, to="project")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("the hierarchy only goes up", r.stderr)
        self.assertIn(self.TEXT, self.claude_md.read_text(encoding="utf-8"))
        self.assertFalse(self.global_md().exists())

    def test_an_unknown_level_is_refused(self):
        nid = self.add_project_note()
        r = self.promote(nid, to="sideways")
        self.assertEqual(r.returncode, 2)
        self.assertIn("global", r.stderr)

    def test_no_level_at_all_is_refused(self):
        nid = self.add_project_note()
        r = self.note("promote", nid, now=LATER)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--to global", r.stderr)

    def test_promoting_a_moved_note_again_is_a_no_op(self):
        nid = self.add_project_note()
        self.promote(nid)
        before_p = self.claude_md.read_text(encoding="utf-8")
        before_g = self.global_md().read_text(encoding="utf-8")
        again = self.promote(nid)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("already promoted", again.stdout)
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), before_p)
        self.assertEqual(self.global_md().read_text(encoding="utf-8"), before_g)
        self.assertEqual(len([x for x in self.ledger_rows()
                              if x.get("action") == "promote"]), 1)

    def test_an_unknown_id_is_refused(self):
        self.add_project_note()
        r = self.promote("n404x404")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("skillnote list", r.stderr)

    def test_with_no_project_file_at_all_it_refuses(self):
        r = self.promote("n404x404")
        self.assertEqual(r.returncode, 2)
        self.assertIn("nothing to promote", r.stderr)

    def test_the_users_other_notes_and_prose_survive(self):
        self.claude_md.parent.mkdir(parents=True, exist_ok=True)
        self.claude_md.write_text("# Project\n\nMy own rules.\n", encoding="utf-8")
        keep = self.add_project_note("a note that stays")
        nid = self.add_project_note()
        self.promote(nid)
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertIn("My own rules.", text)
        self.assertIn("a note that stays", text)
        self.assertIn("id:%s " % keep, text)

    def test_it_joins_an_existing_global_block_rather_than_opening_a_second(self):
        self.ok("add", "--scope", "global", "an older global note")
        nid = self.add_project_note()
        self.promote(nid)
        text = self.global_md().read_text(encoding="utf-8")
        self.assertEqual(text.count("<!-- skillnote:begin -->"), 1, text)
        self.assertEqual(len(self.block_lines(self.global_md())), 2)

    def test_the_flag_chooses_the_project(self):
        other = self.root / "other-proj"
        other.mkdir()
        r = self.ok("add", "--scope", "project", "elsewhere", "--project", str(other))
        nid = r.stdout.split("(")[1].split(")")[0]
        p = self.note("promote", nid, "--to", "global", "--project", str(other), now=LATER)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("elsewhere", self.global_md().read_text(encoding="utf-8"))
        self.assertIn("moved:global",
                      (other / ".claude" / "CLAUDE.md").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------- symlinks
    def test_both_symlinked_files_are_written_through_and_backed_up(self):
        """The four rules apply to a promotion exactly as they apply to an add: two files
        are rewritten, and either one of them can be a link into a dotfiles repo."""
        dots = self.root / "dotfiles"
        dots.mkdir()
        psrc = dots / "project.md"
        gsrc = dots / "global.md"
        psrc.write_text("# project\n", encoding="utf-8")
        gsrc.write_text("# global\n", encoding="utf-8")
        self.claude_md.parent.mkdir(parents=True, exist_ok=True)
        self.claude_md.symlink_to(psrc)
        (self.home / ".claude").mkdir(parents=True, exist_ok=True)
        self.global_md().symlink_to(gsrc)

        nid = self.add_project_note()
        r = self.promote(nid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        self.assertTrue(self.claude_md.is_symlink(), "the link must survive")
        self.assertTrue(self.global_md().is_symlink(), "the link must survive")
        self.assertIn("moved:global", psrc.read_text(encoding="utf-8"))
        self.assertIn(self.TEXT, gsrc.read_text(encoding="utf-8"))
        self.assertIn("# global", gsrc.read_text(encoding="utf-8"))

        # Backups land beside the CONFIGURED path, never inside the dotfiles repo.
        self.assertEqual(sorted(p.name for p in dots.iterdir()),
                         ["global.md", "project.md"], "dotfiles must stay clean")
        self.assertTrue(any(p.name.startswith("CLAUDE.md.bak-skill-compounder-")
                            for p in self.claude_md.parent.iterdir()),
                        sorted(p.name for p in self.claude_md.parent.iterdir()))
        self.assertTrue(any(p.name.startswith("CLAUDE.md.bak-skill-compounder-")
                            for p in self.global_md().parent.iterdir()),
                        sorted(p.name for p in self.global_md().parent.iterdir()))


# ==================================================================== the help text

@unittest.skipUnless(HAVE_NORM_OF, "repeat-gate does not answer --norm-of")
class RemoveTakesTheReminderTooTest(LessonCase):
    """`--lesson` writes TWO things under TWO ids, and `remove` used to take one of them.

    The note id is a hash over "<scope>|<text>"; the reminder id is a hash over
    "remind|<scope>|<text>", so they differ, and `remove <note id>` deleted the line and
    left the reminder live. Measured 2026-09-05 on this machine: the note was gone and
    hooks/remind.sh went on stating it before every matching call -- a lesson still being
    delivered that nobody could read any more.

    Every test here drives the REAL hook after the real CLI, because that is the only pair
    that can show it: the store says nothing about what the hook does with it, and a hook
    driven against a hand-written store says nothing about what the CLI wrote.
    """

    TEXT = "setup.py install needs setuptools here; pip install -e . is the one that works."

    def add_lesson(self, text=None, **kw):
        self.seed()
        r = self.ok("add", "--lesson", FAIL_SIG, text or self.TEXT, **kw)
        return r.stdout.split("(")[1].split(")")[0]

    def reminder_id_of(self, note_id):
        rows = [x for x in self.ledger_rows()
                if x.get("id") == note_id and x.get("reminder_id")]
        self.assertTrue(rows, "no ledger row joined the note to its reminder")
        return rows[-1]["reminder_id"]

    def test_it_delivers_before_the_remove(self):
        """Non-vacuity for every test below: silence afterwards proves nothing unless the
        reminder was really arriving beforehand."""
        self.add_lesson()
        self.assertIn("pip install -e .",
                      self.delivered(self.run_remind(FAIL_CMD, session="s-before")))

    def test_removing_the_note_silences_the_reminder(self):
        nid = self.add_lesson()
        self.delivered(self.run_remind(FAIL_CMD, session="s-before"))
        self.ok("remove", nid)
        r = self.run_remind(FAIL_CMD, session="s-after")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "",
                         "the note is gone and the reminder is still being delivered")

    def test_it_says_which_reminder_it_withdrew(self):
        nid = self.add_lesson()
        rid = self.reminder_id_of(nid)
        out = self.ok("remove", nid).stdout
        self.assertIn("tombstoned reminder %s" % rid, out)
        self.assertIn(str(self.reminders), out)

    def test_the_remove_ledger_row_names_the_reminder(self):
        nid = self.add_lesson()
        rid = self.reminder_id_of(nid)
        removals = [x for x in self.ledger_rows() if x.get("action") == "remove"]
        self.assertEqual([x["id"] for x in removals], [], "nothing removed yet")
        self.ok("remove", nid)
        removals = [x for x in self.ledger_rows() if x.get("action") == "remove"]
        note_rows = [x for x in removals if x["kind"] == "note"]
        rem_rows = [x for x in removals if x["kind"] == "reminder"]
        self.assertEqual(len(note_rows), 1, removals)
        self.assertEqual(note_rows[0]["reminder_id"], rid,
                         "the note's own remove row must record what went with it")
        self.assertEqual(len(rem_rows), 1, removals)
        self.assertEqual(rem_rows[0]["id"], rid)
        self.assertEqual(rem_rows[0]["note_id"], nid)

    def test_the_store_is_tombstoned_and_never_rewritten(self):
        """Append-only, the doctrine `skillrepeat forget` follows: the row stays in the
        file and a tombstone is appended after it. The store is written by a hook nobody
        watches, and one bad expression would erase an hour of it."""
        nid = self.add_lesson()
        rid = self.reminder_id_of(nid)
        before = self.reminders.read_text(encoding="utf-8")
        self.ok("remove", nid)
        after = self.reminders.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before), "the store was rewritten, not appended to")
        rows = self.reminder_rows()
        self.assertEqual(rows[-1], {"id": rid, "t": "remove", "ts": NOW})

    def test_keep_reminder_leaves_it_live_and_says_so(self):
        nid = self.add_lesson()
        rid = self.reminder_id_of(nid)
        out = self.ok("remove", nid, "--keep-reminder").stdout
        self.assertIn("removed %s" % nid, out)
        self.assertIn(rid, out)
        self.assertIn("--keep-reminder", out)
        self.assertNotIn("tombstoned", out)
        self.assertIn("pip install -e .",
                      self.delivered(self.run_remind(FAIL_CMD, session="s-kept")))
        removals = [x for x in self.ledger_rows() if x.get("action") == "remove"]
        self.assertEqual([x["kind"] for x in removals], ["note"])
        self.assertNotIn("reminder_id", removals[0],
                         "nothing was withdrawn, so nothing may be recorded as withdrawn")

    def test_a_promoted_lesson_is_withdrawn_at_its_new_scope(self):
        """`promote` tombstones the project reminder and writes a new row with a new id at
        global scope, recording that id on its own ledger row. `remove` reads the LAST row
        carrying this note's reminder_id, so it withdraws the one that is actually live --
        the project id it superseded is already tombstoned and is not the answer."""
        nid = self.add_lesson()
        old_rid = self.reminder_id_of(nid)
        self.ok("promote", nid, "--to", "global")
        new_rid = self.reminder_id_of(nid)
        self.assertNotEqual(new_rid, old_rid)
        self.assertIn("pip install -e .",
                      self.delivered(self.run_remind(FAIL_CMD, session="s-promoted")))
        out = self.ok("remove", nid).stdout
        self.assertIn("tombstoned reminder %s" % new_rid, out)
        r = self.run_remind(FAIL_CMD, session="s-gone")
        self.assertEqual(r.stdout.strip(), "", "the promoted reminder is still firing")

    def test_a_note_with_no_reminder_removes_exactly_as_before(self):
        r = self.ok("add", "--scope", "project", "a plain note")
        nid = r.stdout.split("(")[1].split(")")[0]
        out = self.ok("remove", nid).stdout
        self.assertNotIn("reminder", out)
        removals = [x for x in self.ledger_rows() if x.get("action") == "remove"]
        self.assertEqual(len(removals), 1, removals)
        self.assertNotIn("reminder_id", removals[0])

    def test_a_reminder_removed_by_its_own_id_still_works(self):
        """The older arm, unchanged: `add --remind` writes a reminder whose id IS the id
        the user is handed, and `remove` on it tombstones that one directly."""
        r = self.ok("add", "--remind", "--scope", "project", "a bare reminder",
                    "--keyword", "widget")
        rid = r.stdout.split("(")[1].split(")")[0]
        out = self.ok("remove", rid).stdout
        self.assertIn("tombstoned reminder %s" % rid, out)
        self.assertEqual(out.count("tombstoned reminder"), 1,
                         "the direct arm and the lesson arm both fired on one id")

    def test_removing_twice_is_not_an_error_and_withdraws_nothing_twice(self):
        nid = self.add_lesson()
        rid = self.reminder_id_of(nid)
        self.ok("remove", nid)
        second = self.note("remove", nid)
        self.assertEqual(second.returncode, 2, second.stdout + second.stderr)
        self.assertEqual(self.reminder_rows()[-1], {"id": rid, "t": "remove", "ts": NOW},
                         "a second tombstone was appended for a reminder already gone")

    def test_an_unknown_option_to_remove_names_the_help(self):
        r = self.note("remove", "n0x0", "--keep-reminders")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--help", r.stderr)


class HelpDocumentsTheNewFlagsTest(SkillnoteCase):

    def test_help_names_every_flag_and_subcommand(self):
        out = self.ok("--help").stdout
        for token in ("--lesson", "--attach", "promote", "--to global",
                      "skillrepeat list", "lessons/", "hierarchy only goes up",
                      "--keep-reminder", "remove <id>"):
            self.assertIn(token, out, "the help must document %s" % token)


class CandidateIdIsNotAPathTest(SkillnoteCase):
    """`--candidate` took `.` and `..`, because both are inside `[A-Za-z0-9._-]`.

    The lineage id is written onto the ledger note row and onto the reminder row, and
    bin/skillreport joins on it; `bin/skillforge start --from` refuses the same two names
    for the same reason. A space was already refused -- these are the two that were not.
    """

    def test_dot_and_dotdot_are_refused(self):
        for bad in (".", ".."):
            r = self.note("add", "--candidate", bad, "--", "a line")
            self.assertEqual(r.returncode, 2,
                             "--candidate %r was accepted:\n%s" % (bad, r.stdout))
            self.assertIn("--candidate", r.stderr)
            self.assertFalse(self.claude_md.exists(),
                             "a refused --candidate still wrote the note")
            self.assertEqual(self.ledger_rows(), [], "it still wrote a ledger row")

    def test_a_real_lineage_id_is_still_taken(self):
        r = self.ok("add", "--candidate", "c1a2b3c4", "--", "a line")
        del r
        rows = self.ledger_rows()
        self.assertTrue(rows)
        self.assertEqual(rows[-1].get("candidate"), "c1a2b3c4")

    def test_a_space_is_still_refused(self):
        r = self.note("add", "--candidate", "c1 c2", "--", "a line")
        self.assertEqual(r.returncode, 2, r.stdout)


class WhereTest(SkillnoteCase):
    """`skillnote where` exists so bin/skillinsight can SAY where a promote will write.

    It promotes into the candidate's own project, which is very often not the caller's
    cwd, and it used to say nothing at all -- a promote run from a scratch directory
    appended a note to a repository the caller was not in. Reimplementing the four scope
    resolutions in that CLI would be the second copy .claude/CLAUDE.md warns about, so it
    asks this. Read-only: it must create nothing.
    """

    def test_project_scope_is_the_cwd_by_default(self):
        r = self.ok("where", "--scope", "project")
        self.assertEqual(r.stdout.strip(), str(self.claude_md))

    def test_project_option_overrides_the_cwd(self):
        other = self.root / "other"
        other.mkdir()
        r = self.ok("where", "--scope", "project", "--project", str(other))
        self.assertEqual(r.stdout.strip(), str(other / ".claude" / "CLAUDE.md"))

    def test_it_agrees_with_where_add_actually_writes(self):
        """The point of the command: the two must be the same path, driven both ways."""
        said = self.ok("where", "--scope", "project").stdout.strip()
        self.ok("add", "--scope", "project", "--", "a line")
        self.assertTrue(self.claude_md.exists())
        self.assertEqual(said, str(self.claude_md))

    def test_global_and_remind_scopes_resolve(self):
        g = self.ok("where", "--scope", "global").stdout.strip()
        self.assertTrue(g.endswith("/CLAUDE.md"), g)
        rem = self.ok("where", "--scope", "remind").stdout.strip()
        self.assertEqual(rem, str(self.reminders))

    def test_it_names_the_directory_a_global_attachment_is_written_under(self):
        """`where --scope global` and the `~`-anchored path on a global note both come off
        claude_dir(), and this drives the pair: expand the tilde the way a reader would and
        the file has to sit under the directory `where` printed."""
        script = self.proj / "fix.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        said = self.ok("where", "--scope", "global").stdout.strip()
        r = self.ok("add", "--scope", "global", "with a file", "--attach", "fix.sh")
        nid = r.stdout.split("(")[1].split(")")[0]
        line = self.block_lines(Path(said))[0]
        ref = line.split("(attached: ")[1].split(")")[0]
        self.assertTrue(ref.startswith("~/"), ref)
        resolved = self.home / ref[2:]
        self.assertTrue(resolved.is_file())
        self.assertEqual(str(resolved.parent.parent.parent), str(Path(said).parent),
                         "the attachment landed outside the directory `where` named")
        del nid

    def test_it_creates_nothing(self):
        before = sorted(p.name for p in self.root.iterdir())
        for scope in ("project", "global", "memory", "remind"):
            self.ok("where", "--scope", scope)
        self.assertFalse((self.proj / ".claude").exists(),
                         "`where` created the directory it only described")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)

    def test_an_unknown_scope_is_refused(self):
        r = self.note("where", "--scope", "nowhere")
        self.assertEqual(r.returncode, 2, r.stdout)


# ------------------------------------------------------------------- the fourth tier
#
# `skillnote skill` turns a note that already exists into a routable skill directory. It
# is the tier the other three could not reach: a note waits to be read, a reminder arrives
# when its rule matches, and NEITHER is a tool a router can choose. The requirement it
# answers is that a write-down be "a combination of notes and code that is searchable,
# findable as a tool in the appropriate future contexts, and callable by agents", and the
# only artifact Claude Code routes on is a SKILL.md.
#
# WHAT THESE TESTS ARE PARTICULARLY FOR, each a defect that ships green:
#
# * The description is the whole product. A file whose frontmatter does not parse, or
#   whose description is over the cap and gets truncated, is a skill that lists and never
#   fires -- the six silent defects `skills/skill-authoring/SKILL.md` tabulates. So the
#   description is read back with THIS REPOSITORY'S OWN parser (`routing_claims.
#   _frontmatter_description`, the one `tests/test_routing_claims.py` judges every shipped
#   skill with) rather than with a regex written here that could agree with the writer and
#   disagree with the router.
# * The scripts have to arrive EXECUTABLE. A lesson whose script comes without its mode is
#   a lesson whose one command does not run.
# * The caps are read out of `skills/skill-authoring/SKILL.md`, never typed here, so a
#   budget changed there fails this file rather than silently outranking the CLI.

def frontmatter_description(text):
    """The description, read back by the parser this repository already judges skills
    with. Importing it rather than re-deriving it is the point: a second reader would
    drift from the first, and both halves would still print something."""
    import sys as _sys
    scripts = str(REPO / "scripts")
    if scripts not in _sys.path:
        _sys.path.insert(0, scripts)
    from routing_claims import _frontmatter_description
    return _frontmatter_description(text)


def documented_budgets():
    """(description cap, frontmatter cap) as `skill-authoring` states them."""
    import re
    text = (REPO / "skills" / "skill-authoring" / "SKILL.md").read_text(encoding="utf-8")
    desc = re.search(r"[Dd]escription at most (\d+) characters", text)
    front = re.search(r"frontmatter block at most (\d+)", text)
    assert desc and front, ("skills/skill-authoring/SKILL.md no longer states its budgets "
                            "in a parseable form, so nothing here knows the ceiling")
    return int(desc.group(1)), int(front.group(1))


class SkillCase(LessonCase):
    """A note with a real attached script, and the two directories a skill can land in."""

    NOTE = ("python3 setup.py install fails on a modern setuptools; install the package "
            "editable with pip instead.")

    def setUp(self):
        super().setUp()
        self.script = self.proj / "unwedge.sh"
        self.script.write_text(
            "#!/bin/sh\n"
            "# Reinstall the package editable, which is what actually worked.\n"
            "python3 -m pip install -e .\n", encoding="utf-8")
        self.script.chmod(0o755)

    def add_note(self, *extra, text=None, scope="project"):
        r = self.ok("add", "--scope", scope, text or self.NOTE, *extra)
        return r.stdout.split("(", 1)[1].split(")", 1)[0]

    def lesson_note(self):
        self.seed()
        return self.add_note("--lesson", FAIL_SIG, "--attach", "unwedge.sh")

    def skills(self, scope="project"):
        if scope == "global":
            return self.home / ".claude" / "skills"
        return self.proj / ".claude" / "skills"


class SkillFromALessonTest(SkillCase):

    def setUp(self):
        super().setUp()
        self.nid = self.lesson_note()
        self.r = self.ok("skill", self.nid, "--name", "editable-install")
        self.dir = self.skills() / "editable-install"

    def test_the_skill_md_parses_with_the_repositorys_own_reader(self):
        text = (self.dir / "SKILL.md").read_text(encoding="utf-8")
        desc = frontmatter_description(text)
        self.assertTrue(desc.startswith("Use when "), desc)
        self.assertIn(". Do NOT use for ", desc)
        self.assertTrue(text.startswith("---\nname: editable-install\ndescription: \""),
                        text[:120])

    def test_the_description_is_inside_the_cap_skill_authoring_states(self):
        desc_max, front_max = documented_budgets()
        text = (self.dir / "SKILL.md").read_text(encoding="utf-8")
        desc = frontmatter_description(text)
        self.assertLessEqual(len(desc), desc_max, desc)
        front = text.split("---\n", 2)[1]
        self.assertLessEqual(len(front), front_max)

    def test_the_trigger_names_the_program_that_failed_and_not_the_cd_in_front_of_it(self):
        """`cd /tmp/forge && python3 setup.py install` fails at `python3`. A trigger
        saying "about to run `cd`" describes every command anyone has ever typed."""
        desc = frontmatter_description((self.dir / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("python3", desc)
        self.assertNotIn("`cd`", desc)

    def test_the_note_is_the_body_verbatim_under_a_heading(self):
        text = (self.dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## The lesson", text)
        self.assertIn(self.NOTE, text)

    def test_the_provenance_names_the_note_the_signature_and_the_date(self):
        text = (self.dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Provenance", text)
        self.assertIn(self.nid, text)
        self.assertIn(FAIL_SIG, text)
        self.assertIn("2026-08-29", text)

    def test_the_script_is_copied_beside_it_and_is_still_executable(self):
        s = self.dir / "scripts" / "unwedge.sh"
        self.assertTrue(s.is_file(), sorted(p.name for p in self.dir.iterdir()))
        self.assertTrue(os.access(str(s), os.X_OK),
                        "a lesson whose script arrives without its mode is a lesson whose "
                        "one command does not run")
        self.assertEqual(s.read_text(encoding="utf-8"),
                         self.script.read_text(encoding="utf-8"))

    def test_the_scripts_section_carries_each_ones_first_comment_line(self):
        text = (self.dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Scripts", text)
        self.assertIn("`scripts/unwedge.sh`", text)
        self.assertIn("Reinstall the package editable, which is what actually worked.", text)

    def test_the_note_keeps_its_own_copy_and_its_line_is_not_rewritten(self):
        """A COPY, not a move: the note and the skill are two artifacts with two readers,
        and moving the file would break the line that points at it."""
        self.assertTrue((self.proj / ".claude" / "lessons" / self.nid / "unwedge.sh").is_file())
        line = self.block_lines()[0]
        self.assertIn("(attached: .claude/lessons/%s/unwedge.sh)" % self.nid, line)

    def test_one_ledger_row_carries_from_and_the_lesson_signature(self):
        rows = self.ledger_rows(event="skill")
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual(row["from"], self.nid)
        self.assertEqual(row["lesson_sig"], FAIL_SIG)
        self.assertEqual(row["name"], "editable-install")
        self.assertEqual(row["scope"], "project")
        self.assertEqual(row["path"], str(self.dir))
        self.assertEqual(row["attachments"], ["scripts/unwedge.sh"])
        self.assertEqual(row["ts"], NOW)
        self.assertTrue(row["id"].startswith("n"), row["id"])

    def test_the_new_event_is_invisible_to_the_note_reader(self):
        """Every reader here selects its events BY NAME, so a new type is invisible rather
        than miscounted. `skillnote list` and the note rows must not see this one."""
        self.assertEqual([r["event"] for r in self.ledger_rows(event="skill")], ["skill"])
        for row in self.ledger_rows(event="note"):
            self.assertNotEqual(row.get("action"), "skill")

    def test_it_says_the_path_and_that_the_skill_is_callable_now(self):
        self.assertIn("skillnote: skill editable-install written to %s" % self.dir,
                      self.r.stdout)
        self.assertIn("callable now in this session", self.r.stdout)
        self.assertIn("without a restart", self.r.stdout)
        self.assertIn("writes a use row", self.r.stdout)


class SkillFromAPlainNoteTest(SkillCase):
    """No lesson signature and no attachments: the note's own first sentence is the
    trigger, and there is no `## Scripts` section to write."""

    def setUp(self):
        super().setUp()
        self.nid = self.add_note(text="The dev server refuses to start while port 8080 is "
                                      "held by a dead process; free the port first.")
        self.ok("skill", self.nid, "--name", "free-the-port")
        self.dir = self.skills() / "free-the-port"

    def test_the_trigger_is_the_notes_own_sentence(self):
        desc = frontmatter_description((self.dir / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("dev server refuses to start", desc)
        self.assertTrue(desc.startswith("Use when the dev server"), desc)

    def test_there_is_no_scripts_section_and_no_scripts_directory(self):
        text = (self.dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("## Scripts", text)
        self.assertFalse((self.dir / "scripts").exists())

    def test_the_row_carries_no_lesson_signature_and_an_empty_attachment_list(self):
        row = self.ledger_rows(event="skill")[0]
        self.assertNotIn("lesson_sig", row)
        self.assertEqual(row["attachments"], [])


class SkillScopeTest(SkillCase):

    def test_global_scope_lands_under_the_claude_directory(self):
        nid = self.add_note("--attach", "unwedge.sh", scope="global")
        self.ok("skill", nid, "--name", "editable-install", "--scope", "global")
        d = self.skills("global") / "editable-install"
        self.assertTrue((d / "SKILL.md").is_file())
        self.assertTrue((d / "scripts" / "unwedge.sh").is_file())
        self.assertFalse(self.skills("project").exists(),
                         "a global skill was written into the project as well")
        self.assertEqual(self.ledger_rows(event="skill")[0]["scope"], "global")

    def test_a_global_note_can_be_found_from_a_project_that_has_notes_of_its_own(self):
        self.add_note(text="a project note")
        nid = self.add_note(text="a global note about tar", scope="global")
        self.ok("skill", nid, "--name", "tar-lesson")
        self.assertIn("a global note about tar",
                      (self.skills() / "tar-lesson" / "SKILL.md").read_text(encoding="utf-8"))

    def test_a_memory_note_is_refused_with_the_reason(self):
        (self.transcripts / str(self.proj).replace("/", "-")).mkdir(parents=True)
        r = self.ok("add", "--scope", "memory", "a memory note about the runner")
        nid = r.stdout.split("(", 1)[1].split(")", 1)[0]
        r2 = self.note("skill", nid, "--name", "runner-lesson")
        self.assertEqual(r2.returncode, 2, r2.stdout + r2.stderr)
        self.assertIn("memory note", r2.stderr)
        self.assertIn("MEMORY.md", r2.stderr)
        self.assertFalse(self.skills().exists())


class SkillRefusalTest(SkillCase):

    def test_an_over_cap_description_refuses_with_the_count_and_leaves_no_directory(self):
        nid = self.add_note()
        long = "x" * 480
        r = self.note("skill", nid, "--name", "too-long", "--use-when", long)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("the cap is %d" % documented_budgets()[0], r.stderr)
        self.assertRegex(r.stderr, r"description is \d\d\d+ characters")
        self.assertFalse((self.skills() / "too-long").exists())
        self.assertEqual(self.ledger_rows(event="skill"), [])

    def test_gate_a_fires_on_a_frontmatter_the_pre_check_cannot_see_and_removes_it(self):
        """The pre-write check counts the DECODED description; the frontmatter cap is
        measured on the line as written, and a description of quote characters is twice
        its own length once jq has escaped it. So this is the one input that passes the
        first check and fails the gate -- and the gate has to leave nothing behind."""
        nid = self.add_note()
        r = self.note("skill", nid, "--name", "q" * 200, "--use-when", '"' * 425)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("GATE A FAIL", r.stderr)
        self.assertIn("frontmatter is", r.stderr)
        self.assertIn("Nothing was written", r.stderr)
        self.assertEqual(sorted(p.name for p in self.skills().iterdir()), [],
                         "the staging directory survived a gate failure")

    def test_an_uppercase_slug_is_refused(self):
        """A `case` range is matched in COLLATION order, so under LANG=en_US.UTF-8 a
        `[a-z0-9]*` pattern MATCHES `Foo`. The guard is written as an explicit character
        set for that reason, and this is what says so."""
        nid = self.add_note()
        r = self.note("skill", nid, "--name", "FreePort",
                      LANG="en_US.UTF-8")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("[a-z0-9][a-z0-9-]*", r.stderr)
        self.assertFalse(self.skills().exists())

    def test_dot_and_dotdot_are_refused_by_name(self):
        nid = self.add_note()
        for slug in (".", ".."):
            r = self.note("skill", nid, "--name", slug)
            self.assertEqual(r.returncode, 2, slug)
            self.assertIn("names a directory, not a skill", r.stderr)

    def test_a_slug_with_a_slash_or_a_space_is_refused(self):
        nid = self.add_note()
        for slug in ("a/b", "two words", "under_score"):
            r = self.note("skill", nid, "--name", slug)
            self.assertEqual(r.returncode, 2, slug)
            self.assertFalse((self.skills() / slug).exists())

    def test_an_unknown_note_id_is_refused_and_names_both_files_it_looked_in(self):
        r = self.note("skill", "n0x0", "--name", "nowhere")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn(str(self.claude_md), r.stderr)
        self.assertIn(str(self.home / ".claude" / "CLAUDE.md"), r.stderr)

    def test_an_existing_directory_refuses_unless_force_and_force_never_deletes(self):
        nid = self.add_note()
        self.ok("skill", nid, "--name", "keeper")
        first = (self.skills() / "keeper" / "SKILL.md").read_text(encoding="utf-8")
        r = self.note("skill", nid, "--name", "keeper")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--force", r.stderr)
        r2 = self.ok("skill", nid, "--name", "keeper", "--force",
                     "--use-when", "the runner is wedged", now=LATER)
        self.assertIn("moved to", r2.stdout)
        kept = [p for p in self.skills().iterdir() if p.name.startswith("keeper.bak-")]
        self.assertEqual(len(kept), 1, sorted(p.name for p in self.skills().iterdir()))
        self.assertEqual((kept[0] / "SKILL.md").read_text(encoding="utf-8"), first,
                         "--force removed the previous skill instead of moving it aside")
        self.assertIn("the runner is wedged",
                      (self.skills() / "keeper" / "SKILL.md").read_text(encoding="utf-8"))

    def test_a_note_id_that_looks_like_a_flag_is_refused(self):
        r = self.note("skill", "--name", "x")
        self.assertEqual(r.returncode, 2, r.stdout)


class SkillDryRunTest(SkillCase):

    def test_it_prints_the_file_and_writes_nothing_at_all(self):
        nid = self.lesson_note()
        before = sorted(p.name for p in (self.proj / ".claude").iterdir())
        r = self.ok("skill", nid, "--name", "editable-install", "--dry-run")
        self.assertTrue(r.stdout.startswith("---\nname: editable-install\n"), r.stdout[:80])
        self.assertIn("## Provenance", r.stdout)
        self.assertIn("scripts/unwedge.sh", r.stdout)
        self.assertFalse(self.skills().exists(),
                         "--dry-run created the skills directory it only described")
        self.assertEqual(sorted(p.name for p in (self.proj / ".claude").iterdir()), before)
        self.assertEqual(self.ledger_rows(event="skill"), [])

    def test_what_it_prints_is_what_a_real_run_writes(self):
        nid = self.add_note()
        shown = self.ok("skill", nid, "--name", "same-thing", "--dry-run").stdout
        self.ok("skill", nid, "--name", "same-thing")
        self.assertEqual((self.skills() / "same-thing" / "SKILL.md").read_text(encoding="utf-8"),
                         shown)


class SkillWhereTest(SkillCase):

    def test_where_scope_skill_is_the_directory_a_skill_lands_in(self):
        said = self.ok("where", "--scope", "skill").stdout.strip()
        self.assertEqual(said, str(self.skills()))
        nid = self.add_note()
        self.ok("skill", nid, "--name", "somewhere")
        self.assertTrue((Path(said) / "somewhere" / "SKILL.md").is_file(),
                        "the skill landed somewhere other than the path `where` named")

    def test_where_scope_skill_global_answers_the_claude_directory(self):
        said = self.ok("where", "--scope", "skill-global").stdout.strip()
        self.assertEqual(said, str(self.skills("global")))

    def test_neither_skill_scope_creates_anything(self):
        for scope in ("skill", "skill-global"):
            self.ok("where", "--scope", scope)
        self.assertFalse((self.proj / ".claude").exists())
        self.assertFalse((self.home / ".claude").exists())


class SkillBudgetsAgreeTest(unittest.TestCase):
    """The two caps are hardcoded in `bin/skillnote` because that CLI is installed on its
    own and cannot read a repository it is not in. This is the ratchet that stops the copy
    drifting from `skills/skill-authoring/SKILL.md`, which is where the numbers come from
    and which `tests/test_doctrine_sync.py::SkillBudgetTest` reads for every shipped
    skill."""

    def test_the_cli_hardcodes_the_numbers_skill_authoring_states(self):
        import re
        desc_max, front_max = documented_budgets()
        text = NOTE.read_text(encoding="utf-8")
        for name, want in (("SKILL_DESC_MAX", desc_max), ("SKILL_FRONT_MAX", front_max)):
            m = re.search(r"^%s=(\d+)$" % name, text, re.M)
            self.assertIsNotNone(m, "bin/skillnote no longer sets %s" % name)
            self.assertEqual(int(m.group(1)), want,
                             "%s is %s in bin/skillnote and %s in skills/skill-authoring/"
                             "SKILL.md" % (name, m.group(1), want))


class SkillHelpTest(SkillnoteCase):

    def test_the_help_documents_the_subcommand_and_its_flags(self):
        out = self.ok("--help").stdout
        for token in ("skillnote skill", "--name <slug>", "--use-when", "--not-for",
                      "--dry-run", "Use when ... Do NOT use for ...", "skill-global"):
            self.assertIn(token, out, "the help must document %s" % token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
