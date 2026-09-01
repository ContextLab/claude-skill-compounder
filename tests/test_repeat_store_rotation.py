#!/usr/bin/env python3
"""The repeat gate's store must not grow into its own read budget.

`repeats/index.jsonl` is append-only by design, and the read path fails OPEN above
`REPEAT_GATE_MAX_BYTES`. Failing open is right for a transient over-budget. It is wrong
as a PERMANENT terminal state, which is what an append-only file guarantees it becomes:
measured at 32,702 bytes a day on one machine, the store crosses the 4 MB default in
about four months, after which the gate stops matching history for good, silently, with
nothing on any surface to say why.

So the store rotates by RENAME at half the read budget. These tests pin that it rotates,
that it does not rotate early, that nothing is lost when it does, and that the threshold
follows the budget it protects rather than being a second number that can drift.

Real hook, real store, real files. The clock is REPEAT_GATE_NOW.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = str(REPO / "hooks" / "repeat-gate.sh")
BASE_PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
GH_ERR = "fatal: could not read Username for 'https://github.com': terminal prompts disabled"


class RotationCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.state = os.path.join(self.tmp.name, "state")
        self.repeats = Path(self.state) / "repeats"
        self.repeats.mkdir(parents=True)
        self.store = self.repeats / "index.jsonl"
        self.archive = self.repeats / "archive"
        self.clock = 1000000000

    def tearDown(self):
        self.tmp.cleanup()

    def fire_failure(self, command="gh pr list", session="s-new", max_bytes=None):
        """One real PostToolUseFailure through the real hook."""
        payload = {"hook_event_name": "PostToolUseFailure", "session_id": session,
                   "transcript_path": os.path.join(self.tmp.name, "t.jsonl"),
                   "cwd": "/repo", "prompt_id": "p1", "permission_mode": "acceptEdits",
                   "tool_name": "Bash", "tool_use_id": "toolu_%d" % self.clock,
                   "tool_input": {"command": command, "description": "d"},
                   "error": GH_ERR, "is_interrupt": False, "duration_ms": 12}
        env = {"PATH": BASE_PATH, "HOME": self.home,
               "SKILL_COMPOUNDER_STATE": self.state,
               "REPEAT_GATE_NOW": str(self.clock)}
        if max_bytes is not None:
            env["REPEAT_GATE_MAX_BYTES"] = str(max_bytes)
        self.clock += 1
        return subprocess.run(["bash", HOOK], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=180)

    def fill_store(self, nbytes):
        """Real rows, not padding: rotation must be driven by the same file the gate reads."""
        rows, size, i = [], 0, 0
        while size < nbytes:
            r = json.dumps({"t": "fail", "ts": 900000000 + i, "sig": "sig%d" % i,
                            "ck": "ck%d" % i, "ec": 1, "tool": "Bash",
                            "norm": "gh pr list", "cmd": "gh pr list",
                            "err": GH_ERR, "session": "old-%d" % i,
                            "tuid": "toolu_old_%d" % i})
            rows.append(r)
            size += len(r) + 1
            i += 1
        self.store.write_text("\n".join(rows) + "\n")
        return len(rows)

    def archives(self):
        return sorted(self.archive.glob("index-*.jsonl")) if self.archive.is_dir() else []

    def rows_in(self, path):
        return [l for l in path.read_text().splitlines() if l.strip()]


class ItRotates(RotationCase):
    def test_a_store_over_half_the_budget_is_rotated_on_the_next_write(self):
        self.fill_store(1200)                      # over 1000 = 2000/2
        r = self.fire_failure(max_bytes=2000)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.archives()), 1,
                         "the oversized store was not archived: %s" % self.archives())
        self.assertTrue(self.store.is_file(), "no live store after rotation")
        self.assertLess(self.store.stat().st_size, 1000,
                        "the live store is still over the rotation point")

    def test_a_store_under_the_threshold_is_left_alone(self):
        """Non-vacuity. A rotation that always fires is a store that never accumulates,
        and the gate's whole function is accumulating across sessions."""
        self.fill_store(200)                       # well under 1000
        r = self.fire_failure(max_bytes=2000)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.archives(), [], "rotated a store that was under budget")

    def test_the_threshold_follows_the_budget_it_protects(self):
        """It is derived, not a second knob. The same store rotates or does not purely
        on the budget, which is what stops the two drifting apart."""
        self.fill_store(1200)
        self.assertEqual(self.archives(), [])
        r = self.fire_failure(max_bytes=100000)    # half is 50000; 1200 is far under
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.archives(), [], "rotated although the budget was raised")


class NothingIsLost(RotationCase):
    def test_every_archived_row_survives_and_the_new_row_is_live(self):
        """`mv`, never a rewrite: a rewrite would have to read and write the file back,
        and a racing append between those steps is gone with no error anywhere."""
        n = self.fill_store(1200)
        before = self.rows_in(self.store)
        self.assertEqual(len(before), n)

        r = self.fire_failure(max_bytes=2000)
        self.assertEqual(r.returncode, 0, r.stderr)

        arch = self.archives()
        self.assertEqual(len(arch), 1)
        archived = self.rows_in(arch[0])
        self.assertEqual(archived, before,
                         "the archive is not byte-for-byte the store that was rotated")

        live = self.rows_in(self.store)
        self.assertEqual(len(live), 1, "the triggering row did not start the fresh store")
        self.assertEqual(json.loads(live[0])["t"], "fail")
        self.assertEqual(len(archived) + len(live), n + 1, "a row went missing")

    def test_the_archive_is_still_valid_jsonl(self):
        self.fill_store(1200)
        self.fire_failure(max_bytes=2000)
        for line in self.rows_in(self.archives()[0]):
            json.loads(line)          # raises if rotation corrupted anything


class TheGateStillWorksAfterRotation(RotationCase):
    def test_a_rotated_store_leaves_the_hook_healthy(self):
        """The point of rotating is that the gate keeps working. A rotation that left the
        next invocation erroring would have traded a silent stop for a loud one."""
        self.fill_store(1200)
        self.fire_failure(max_bytes=2000)
        r = self.fire_failure(command="gh pr list", session="s-later", max_bytes=2000)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("integer expected", r.stderr)
        self.assertNotIn("No such file", r.stderr)
        self.assertEqual(len(self.rows_in(self.store)), 2,
                         "the store stopped accumulating after a rotation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
