#!/usr/bin/env python3
"""One id, followed across every store it descends through (issue #37).

NO MOCKS, AND NOTHING HAND-WRITTEN THAT A SCRIPT WOULD HAVE WRITTEN. The whole point of
this file is that the six stores agree on one string, and a fixture is exactly where two
stores stop agreeing without anybody noticing: `.claude/CLAUDE.md` records that twice in
one day, a hook's counter file and the CLI reading it, and a CLI's stored signature
against the hook comparing it. So every hop below is driven by the REAL script that owns
that store, through subprocess, and the id is read back off disk:

    hooks/insight-capture.sh   ->  the weekly queue        (`hash`)
    hooks/compound-improvement.sh -> the delivery log      (`id`)
    bin/skillinsight promote   ->  the promote record      (`candidate`)
    bin/skillnote (through it) ->  reminders.jsonl         (`candidate`)
                               ->  the ledger `note` row   (`candidate`)
    hooks/remind.sh            ->  remind/hits.jsonl       (`candidate`)
    bin/skillforge start/apply/verdict -> the ledger       (`from`)
    bin/skillreport            ->  the FUNNEL block

THE ID IS DERIVED, NOT MINTED. A queue record already carries the only stable name it
will ever have: `hash`, the digest of its normalised text, which hooks/insight-capture.sh
and hooks/precompact.sh compute identically so that whichever hook sees a sentence first,
both look it up under the same name. The lineage id is `c` plus the first eight characters
of that digest -- the length this package already prints and accepts everywhere -- so
hooks/precompact.sh needed no change and no record queued before any of this existed has
to be backfilled.

EVERY subprocess call passes `input=` or `stdin=DEVNULL`. A hook script reads its payload
with `payload="$(cat)"`; without stdin it hangs forever.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CAPTURE = REPO / "hooks" / "insight-capture.sh"
REMIND = REPO / "hooks" / "remind.sh"
CI_HOOK = REPO / "hooks" / "compound-improvement.sh"
INSIGHT = REPO / "bin" / "skillinsight"
FORGE = REPO / "bin" / "skillforge"
REPORT = REPO / "bin" / "skillreport"

PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
TIMEOUT = 180

# 2025-08-24T00:00:00Z, ISO week 2025-W34. Every clock in this file is pinned to it or
# to an offset from it, and each script gets ITS OWN pin: pinning another script's clock
# does nothing to it, which is the whole reason there are fourteen of them.
NOW = 1755993600

CANDIDATE_TEXT = (
    "★ Skill candidate: a reader that joins two stores on a session id has to know "
    "which of the two session ids each store carries.\nThey are different, and matching "
    "the wrong pair silently reports zero."
)


class AttributionCase(unittest.TestCase):
    """One temp state root, one temp project, the real scripts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.project = self.root / "proj"
        for d in (self.home, self.state, self.project / ".claude"):
            d.mkdir(parents=True)
        self.transcripts = self.root / "projects"
        self.transcripts.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    # --------------------------------------------------------------------- plumbing
    def env(self, **extra):
        e = {"PATH": PATH, "HOME": str(self.home),
             "SKILL_COMPOUNDER_STATE": str(self.state),
             "SKILL_COMPOUNDER_TRANSCRIPTS": str(self.transcripts),
             "SKILLFORGE_NO_INSTALL": "1"}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def sh(self, argv, stdin=None, cwd=None, **env_extra):
        # NOT named `run`: that is unittest.TestCase.run, and shadowing it
        # makes every test in the class fail inside the runner.
        kw = {"capture_output": True, "text": True, "timeout": TIMEOUT,
              "cwd": str(cwd or self.project), "env": self.env(**env_extra)}
        if stdin is None:
            kw["stdin"] = subprocess.DEVNULL
        else:
            kw["input"] = stdin
        return subprocess.run([str(a) for a in argv], **kw)

    @property
    def ledger(self):
        return self.state / "ledger.jsonl"

    def ledger_rows(self, event=None):
        if not self.ledger.exists():
            return []
        rows = []
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if event is None or row.get("event") == event:
                rows.append(row)
        return rows

    def jsonl(self, path):
        p = Path(path)
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
                if l.strip()]

    # --------------------------------------------------------------------- the hops
    def capture(self, text=CANDIDATE_TEXT, session="cap-1"):
        """Hop 1: the real capture hook writes a queue record, and we read its hash."""
        payload = {"hook_event_name": "Stop", "session_id": session,
                   "cwd": str(self.project),
                   "transcript_path": str(self.root / "t.jsonl"),
                   "last_assistant_message": text}
        r = self.sh(["bash", CAPTURE], stdin=json.dumps(payload),
                     INSIGHT_NOW=NOW, INSIGHT_AUDIT_MIN_EDITS=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.jsonl(self.state / "insights" / "2025-W34.jsonl")
        self.assertEqual(len(rows), 1, "the capture hook queued %d records" % len(rows))
        return rows[0]["hash"]

    def promote(self, h, to, *extra):
        argv = [str(INSIGHT), "promote", h, "--to", to, "--scope", "project",
                "--project", str(self.project)] + list(extra)
        r = self.sh(argv, SKILLNOTE_NOW=NOW + 10, INSIGHT_NOW=NOW + 10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def deliver(self, prompt, session="deliver-1", clock=NOW + 20):
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": session,
                   "prompt_id": "p-%s" % session, "cwd": str(self.project),
                   "transcript_path": str(self.root / "t.jsonl"), "prompt": prompt}
        r = self.sh(["bash", REMIND], stdin=json.dumps(payload), REMIND_NOW=clock)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def forge(self, *argv, **env_extra):
        r = self.sh([str(FORGE)] + list(argv), **env_extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def report(self, *argv):
        r = self.sh([str(REPORT)] + list(argv))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "", r.stderr)
        return r.stdout

    def funnel_row(self, out, lineage):
        for line in out.splitlines():
            if line.strip().startswith(lineage + " "):
                return line.split()
        self.fail("no funnel row for %s in:\n%s" % (lineage, out))

    def unattributed(self, out):
        line = [l for l in out.splitlines() if "UNATTRIBUTED:" in l]
        self.assertTrue(line, "the report has no UNATTRIBUTED line:\n" + out)
        return int(line[0].split("UNATTRIBUTED:")[1].split()[0])

    def check_line(self, out):
        """The funnel's own self-consistency line, as three integers.

        The block prints `CHECK FAILED` instead when they do not add up, so a report that
        lost a row says so on its own surface; this reads the passing form and the caller
        asserts the arithmetic against the ledger on disk."""
        line = [l for l in out.splitlines() if "CHECK:" in l]
        self.assertTrue(line, "the funnel prints no CHECK line:\n" + out)
        self.assertNotIn("CHECK FAILED", out, out)
        text = line[0]
        intable = int(text.split("CHECK:")[1].split()[0])
        unattr = int(text.split("+")[1].split()[0])
        total = int(text.split("=")[1].split()[0])
        return intable, unattr, total

    def assert_every_row_lands_once(self, out):
        """rows in the table + unattributed = every note/start/use/apply/verdict row the
        ledger holds, counted off disk rather than off the report."""
        intable, unattr, total = self.check_line(out)
        self.assertEqual(intable + unattr, total,
                         "the funnel does not add up: %d + %d != %d" %
                         (intable, unattr, total))
        on_disk = len([r for r in self.ledger_rows()
                       if r.get("event") in ("note", "start", "use", "apply", "verdict")])
        self.assertEqual(total, on_disk,
                         "the funnel counted %d rows; the ledger holds %d" %
                         (total, on_disk))
        return intable, unattr, total


class TheWholeChainCarriesOneId(AttributionCase):
    """The acceptance criterion of issue #37, end to end, in one test.

    A candidate is captured, announced, promoted, delivered, forged, applied and judged,
    and ONE id is read back out of every store on the way. Before this, three of the six
    hops were unjoinable and the package's only conversion figure was reconstructed by
    dividing an edit counter.
    """

    def test_one_id_is_readable_from_every_store_the_lineage_passes_through(self):
        # HOP 1 -- the queue. The digest is the name both capture hooks agree on.
        digest = self.capture()
        lineage = "c" + digest[:8]

        # HOP 2 -- the queue announcement. hooks/compound-improvement.sh logs the delivery
        # under the announced candidate's OWN lineage id, not under a name of its own, so
        # the nudge and everything downstream of it join.
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "nudge-1",
                   "prompt_id": "p1", "cwd": str(self.project),
                   "prompt": "x" * 100}
        r = self.sh(["bash", CI_HOOK, "prompt"], stdin=json.dumps(payload), CI_NOW=NOW + 5)
        self.assertEqual(r.returncode, 0, r.stderr)
        nudges = self.jsonl(self.state / "reminders" / "nudges.jsonl")
        self.assertTrue(nudges, "the nudge hook logged no delivery:\n" + r.stdout)
        self.assertIn(lineage, [n["id"] for n in nudges],
                      "the queue announcement was logged under no lineage: %r" % nudges)
        queue_row = [n for n in nudges if n["id"] == lineage][0]
        self.assertEqual(queue_row["kind"], "queue")
        self.assertEqual(queue_row["session"], "nudge-1")

        # HOP 3 -- the promote record and the reminder, both written through the real
        # bin/skillnote by the real bin/skillinsight.
        out = self.promote(digest, "reminder", "--keyword", "sessionid")
        self.assertIn("lineage %s" % lineage, out, out)
        promoted = self.jsonl(self.state / "insights" / ".promoted.jsonl")
        self.assertEqual([p.get("candidate") for p in promoted], [lineage])

        reminders = self.jsonl(self.state / "reminders.jsonl")
        self.assertEqual(len(reminders), 1, reminders)
        self.assertEqual(reminders[0].get("candidate"), lineage)
        reminder_id = reminders[0]["id"]

        # HOP 4 -- the ledger `note` row for that reminder.
        notes = [n for n in self.ledger_rows("note") if n.get("id") == reminder_id]
        self.assertEqual(len(notes), 1, self.ledger_rows("note"))
        self.assertEqual(notes[0].get("candidate"), lineage)

        # And a note in the CLAUDE.md as well, so the lineage covers both cheap tiers.
        self.promote(digest, "note")
        note_rows = [n for n in self.ledger_rows("note") if n.get("kind") == "note"]
        self.assertEqual(len(note_rows), 1, note_rows)
        self.assertEqual(note_rows[0].get("candidate"), lineage)

        # HOP 5 -- the delivery. hooks/remind.sh states the reminder back and writes a
        # hits row carrying the lineage, not only the reminder's own id.
        emitted = self.deliver("what about the sessionid mismatch here")
        self.assertIn("Reminder recorded", emitted, emitted)
        hits = self.jsonl(self.state / "remind" / "hits.jsonl")
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0]["id"], reminder_id)
        self.assertEqual(hits[0].get("candidate"), lineage)
        self.assertEqual(hits[0]["session"], "deliver-1")

        # HOP 6 -- the forge. `--from` carries the lineage onto the start row; `done`
        # carries it onto the origin row; `apply` and `verdict` read it back off those.
        skill_dir = self.root / "skills" / "sessionids"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: sessionids\ndescription: x\n---\nbody\n", encoding="utf-8")
        self.forge("start", "sessionids", "4", "join two stores on the right id",
                   "--trigger", "the reminder fired", "--trigger-kind", "hook-checkpoint",
                   "--from", lineage, "--session", "deliver-1",
                   SKILLFORGE_NOW=NOW + 30)
        self.forge("done", "--name", "sessionids", "--skill-dir", str(skill_dir), "ok",
                   SKILLFORGE_NOW=NOW + 40)
        self.forge("apply", "--name", "sessionids", "--outcome", "used",
                   "--evidence", "used it on the join that caused it",
                   SKILLFORGE_NOW=NOW + 50)
        self.forge("verdict", "--name", "sessionids", "--verdict", "WORKED",
                   "--evidence", "the funnel printed a row", SKILLFORGE_NOW=NOW + 60)

        for event in ("start", "origin", "apply", "verdict"):
            rows = self.ledger_rows(event)
            self.assertEqual(len(rows), 1, "%s rows: %r" % (event, rows))
            self.assertEqual(rows[0].get("from"), lineage,
                             "the %s row carries no lineage: %r" % (event, rows[0]))

        # THE READ-BACK, STATED AS ONE ASSERTION. Six stores, one string.
        self.assertEqual(
            {"queue": "c" + digest[:8],
             "nudges": queue_row["id"],
             "promoted": promoted[0]["candidate"],
             "reminders": reminders[0]["candidate"],
             "hits": hits[0]["candidate"],
             "ledger-note": notes[0]["candidate"],
             "ledger-start": self.ledger_rows("start")[0]["from"],
             "ledger-origin": self.ledger_rows("origin")[0]["from"],
             "ledger-apply": self.ledger_rows("apply")[0]["from"],
             "ledger-verdict": self.ledger_rows("verdict")[0]["from"]},
            dict.fromkeys(
                ["queue", "nudges", "promoted", "reminders", "hits", "ledger-note",
                 "ledger-start", "ledger-origin", "ledger-apply", "ledger-verdict"],
                lineage))

        # HOP 7 -- the report. The funnel is a join, and this is the line that proves it.
        out = self.report()
        self.assertIn("FUNNEL", out, out)
        row = self.funnel_row(out, lineage)
        # LINEAGE, DELIVERED, ACTED ON, OUTCOME. Two deliveries (the queue announcement
        # and the reminder), and the acted-on count covers the two note rows, the start
        # and the apply -- all four carrying the id or sitting in a delivered session.
        self.assertEqual(row[0], lineage)
        self.assertEqual(row[1], "2", "delivered count: " + " ".join(row))
        self.assertEqual(row[2], "4", "acted-on count: " + " ".join(row))
        self.assertEqual(row[3], "1", "outcome count: " + " ".join(row))
        self.assertIn("no estimate anywhere in this block", out)


class PrecompactNeedsNoChangeToShareTheLineage(AttributionCase):
    """The design constraint the id scheme was chosen for, proved rather than argued.

    `hooks/precompact.sh` writes into the same weekly queue `hooks/insight-capture.sh`
    does, under a digest the two compute identically -- that shared digest is "the shared
    name the two scripts look one record up under". So the lineage id is DERIVED from it
    in the reader, and a random id minted at capture would have had to be minted in both
    hooks and would still have given one sentence two names depending on which hook won
    the race. Nothing in `hooks/precompact.sh` changed for issue #37, and this is the test
    that says so: a record only that hook ever saw promotes to a lineage id of the same
    shape and joins the same way.
    """

    PRECOMPACT = REPO / "hooks" / "precompact.sh"

    def test_a_record_queued_only_by_precompact_carries_the_same_lineage(self):
        transcript = self.root / "t.jsonl"
        transcript.write_text(json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text":
             "\u2605 Skill candidate: precompact and Stop must agree on the digest.\n\n"
             "They do, and the lineage id is derived from it."}]}}) + "\n",
            encoding="utf-8")
        payload = {"hook_event_name": "PreCompact", "session_id": "pc-1",
                   "cwd": str(self.project), "transcript_path": str(transcript),
                   "trigger": "manual"}
        r = self.sh(["bash", self.PRECOMPACT], stdin=json.dumps(payload),
                    PRECOMPACT_NOW=NOW)
        self.assertEqual(r.returncode, 0, r.stderr)

        rows = self.jsonl(self.state / "insights" / "2025-W34.jsonl")
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["source"], "precompact")
        digest = rows[0]["hash"]
        lineage = "c" + digest[:8]

        out = self.promote(digest, "note")
        self.assertIn("lineage %s" % lineage, out, out)
        note = [n for n in self.ledger_rows("note") if n.get("kind") == "note"]
        self.assertEqual(len(note), 1, note)
        self.assertEqual(note[0].get("candidate"), lineage)


class LegacyRowsAreUnattributedNotDropped(AttributionCase):
    """The third acceptance clause: a row from before any of this is REPORTED as having
    no lineage, the way a forge with no `--trigger` is recorded as
    `trigger_kind:"unrecorded"` rather than left out of the count."""

    def legacy_ledger(self):
        rows = [
            {"event": "horizon", "ts": NOW - 1, "known_from": NOW - 1,
             "confidence": "measured", "backfilled": False},
            {"event": "start", "name": "old", "ts": NOW, "steps": 4, "summary": "s",
             "project": str(self.project)},
            {"event": "done", "name": "old", "ts": NOW + 100, "steps": 4, "summary": "s",
             "project": str(self.project), "step": 4, "phase": "ok", "duration": 100},
            {"event": "use", "ts": NOW + 200, "name": "old", "ok": True,
             "recorded": "live", "session": "some-old-session"},
            {"event": "verdict", "ts": NOW + 300, "name": "old", "verdict": "UNKNOWN"},
        ]
        with open(str(self.ledger), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def test_rows_with_no_lineage_are_counted_and_named_rather_than_dropped(self):
        self.legacy_ledger()
        out = self.report()
        # start, use, verdict -- the three of the five that the funnel's named selectors
        # cover. `horizon` and `done` are neither counted nor claimed to be.
        self.assertEqual(self.unattributed(out), 3, out)
        self.assertIn("out of 3 note/start/use/apply/verdict row(s) in all", out, out)
        self.assertIn("nowhere dropped, guessed at, or folded into a rate", out, out)

    def test_with_no_delivery_log_at_all_the_funnel_says_so_rather_than_printing_zero(self):
        self.legacy_ledger()
        out = self.report()
        self.assertIn("no deliveries logged yet", out, out)
        self.assertIn("absence of data, not an absence of compounding", out, out)

    def test_a_lineage_row_and_a_legacy_row_are_counted_apart(self):
        """Both halves in one report: the attributed lineage on its own line, and the
        rows that predate it counted as unattributed rather than folded in."""
        self.legacy_ledger()
        digest = self.capture()
        lineage = "c" + digest[:8]
        self.promote(digest, "note")
        out = self.report()
        self.assertEqual(self.unattributed(out), 3,
                         "a promoted note changed the legacy count:\n" + out)
        self.assertIn("out of 4 note/start/use/apply/verdict row(s) in all", out, out)


class TheFunnelCountsEveryRowExactlyOnce(AttributionCase):
    """A row lands in the lineage table or in UNATTRIBUTED, and never in neither or both.

    IT DID BOTH, AND A RED TEAM FOUND BOTH ON THE LIVE STORE. UNATTRIBUTED excluded any
    row carrying a `from` or a `candidate`, but the table listed only lineages a DELIVERY
    LOG knew -- so a ledger lineage nothing had delivered was counted NOWHERE. And ACTED
    ON counted a row once for EVERY lineage delivered to its session, so the column summed
    to 104 against 69 deliveries and totalled nothing a reader could act on.

    Every row below is written by the real CLI or the real hook, and the arithmetic is
    checked against the ledger read off disk.
    """

    def skill_dir(self, name):
        d = self.root / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            "---\nname: %s\ndescription: x\n---\nbody\n" % name, encoding="utf-8")
        return d

    def test_a_lineage_no_delivery_log_knows_still_gets_a_row(self):
        """The repro, exactly: a forge started `--from` a lineage with no delivery behind
        it, judged at the end. Two rows carrying an id nothing delivered."""
        lineage = "cdeadbeef"
        d = self.skill_dir("orphan")
        self.forge("start", "orphan", "4", "s", "--trigger", "t",
                   "--trigger-kind", "agent-decision", "--from", lineage,
                   "--session", "sess-orphan", SKILLFORGE_NOW=NOW)
        self.forge("done", "--name", "orphan", "--skill-dir", str(d), "ok",
                   SKILLFORGE_NOW=NOW + 10)
        # --force: verdict refuses without an apply row since 2026-09-05, and an apply
        # row would be a third attributed row; this test is about the partition, not
        # the apply rule, which tests/test_ledger_v2.py::VerdictTest pins.
        self.forge("verdict", "--name", "orphan", "--verdict", "WORKED",
                   "--evidence", "e", "--force", SKILLFORGE_NOW=NOW + 20)

        out = self.report()
        row = self.funnel_row(out, lineage)
        self.assertEqual(row[1], "0", "DELIVERED is not 0: " + " ".join(row))
        self.assertEqual(row[2], "1", "ACTED ON missed the start row: " + " ".join(row))
        self.assertEqual(row[3], "1", "OUTCOME missed the verdict row: " + " ".join(row))
        self.assertEqual(self.unattributed(out), 0,
                         "a row carrying a lineage was also called unattributed:\n" + out)
        self.assert_every_row_lands_once(out)

    def test_a_verdict_row_is_counted_in_exactly_one_column(self):
        """A verdict was the sharpest case of counted-nowhere: excluded from ACTED ON by
        construction, and excluded from UNATTRIBUTED whenever its session had received
        anything at all."""
        d = self.skill_dir("judged")
        self.forge("start", "judged", "4", "s", "--trigger", "t",
                   "--trigger-kind", "agent-decision", "--from", "cfeedface",
                   "--session", "sess-j", SKILLFORGE_NOW=NOW)
        self.forge("done", "--name", "judged", "--skill-dir", str(d), "ok",
                   SKILLFORGE_NOW=NOW + 10)
        self.forge("verdict", "--name", "judged", "--verdict", "UNKNOWN",
                   "--evidence", "e", "--force", SKILLFORGE_NOW=NOW + 20)
        out = self.report()
        intable, unattr, total = self.assert_every_row_lands_once(out)
        self.assertEqual((intable, unattr, total), (2, 0, 2),
                         "start and verdict did not land once each:\n" + out)

    def test_a_legacy_ledger_still_adds_up(self):
        """The other end: rows from before any of this, which must all be unattributed and
        must still satisfy the same equation."""
        rows = [
            {"event": "start", "name": "old", "ts": NOW, "steps": 4, "summary": "s",
             "project": str(self.project)},
            {"event": "use", "ts": NOW + 200, "name": "old", "ok": True,
             "recorded": "live", "session": "some-old-session"},
            {"event": "verdict", "ts": NOW + 300, "name": "old", "verdict": "UNKNOWN"},
        ]
        with open(str(self.ledger), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        out = self.report()
        intable, unattr, total = self.assert_every_row_lands_once(out)
        self.assertEqual((intable, unattr, total), (0, 3, 3), out)


class ARowBelongsToOneLineageOnly(AttributionCase):
    """ACTED ON summed to 104 against 69 DELIVERED because a row in a session that had
    received two lineages was counted for both. It is now attributed to the one delivered
    to that session FIRST, ties by id, and the block prints that rule.

    Both deliveries here are written by the REAL hooks/remind.sh from real payloads, so
    what is under test is the join and not a fixture of it.
    """

    SECOND_TEXT = (
        "\u2605 Skill candidate: a funnel that counts one row under two lineages reports "
        "a column that sums past its own denominator.\nCount each row once, or say which "
        "one it was given to."
    )

    def capture_more(self, text, session):
        """A SECOND candidate into the same weekly queue. `capture` asserts the queue
        holds exactly one record, which is right for the tests that use it and wrong
        here, so this reads the digest of whatever the hook just added."""
        weekly = self.state / "insights" / "2025-W34.jsonl"
        before = {r["hash"] for r in self.jsonl(weekly)}
        payload = {"hook_event_name": "Stop", "session_id": session,
                   "cwd": str(self.project),
                   "transcript_path": str(self.root / "t.jsonl"),
                   "last_assistant_message": text}
        r = self.sh(["bash", CAPTURE], stdin=json.dumps(payload),
                    INSIGHT_NOW=NOW + 1, INSIGHT_AUDIT_MIN_EDITS=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        new = [x["hash"] for x in self.jsonl(weekly) if x["hash"] not in before]
        self.assertEqual(len(new), 1, "the capture hook queued %r" % new)
        return new[0]

    def test_one_row_in_a_twice_delivered_session_is_counted_once(self):
        first = self.capture()
        self.promote(first, "reminder", "--keyword", "sessionid")
        second = self.capture_more(self.SECOND_TEXT, "cap-2")
        self.promote(second, "reminder", "--keyword", "denominator")
        lin_a, lin_b = "c" + first[:8], "c" + second[:8]
        self.assertNotEqual(lin_a, lin_b)

        # ONE session, BOTH reminders delivered into it, by the real hook.
        self.deliver("the sessionid and the denominator are both wrong here",
                     session="two-lineages")
        hits = self.jsonl(self.state / "remind" / "hits.jsonl")
        self.assertEqual({h.get("candidate") for h in hits}, {lin_a, lin_b},
                         "the fixture did not deliver two lineages: %r" % hits)
        self.assertEqual({h["session"] for h in hits}, {"two-lineages"})

        # ONE ledger row in that session, carrying no lineage of its own.
        self.forge("start", "ambiguous", "4", "s", "--trigger", "t",
                   "--trigger-kind", "agent-decision", "--session", "two-lineages",
                   SKILLFORGE_NOW=NOW + 40)
        starts = self.ledger_rows("start")
        self.assertEqual(len(starts), 1, starts)
        self.assertNotIn("from", starts[0], starts[0])

        out = self.report()
        acted = {}
        for lin in (lin_a, lin_b):
            row = self.funnel_row(out, lin)
            acted[lin] = int(row[2])
        self.assertEqual(sum(acted.values()) - 2, 1,
                         "the start row was counted %d times over the two lineages "
                         "(each lineage also owns its own note row):\n%s"
                         % (sum(acted.values()) - 2, out))
        self.assert_every_row_lands_once(out)

    def test_the_block_states_the_rule_it_used(self):
        """A tie-break nobody can read is a number nobody can check."""
        digest = self.capture()
        self.promote(digest, "note")
        # The report exits before this block when the ledger holds no `start` row at all,
        # so the fixture needs a forge for the funnel to be reached.
        self.forge("start", "anything", "4", "s", "--trigger", "t",
                   "--trigger-kind", "agent-decision", "--session", "sess-r",
                   SKILLFORGE_NOW=NOW + 40)
        out = self.report()
        self.assertIn("attributed to AT MOST ONE lineage", out, out)
        self.assertIn("delivered FIRST to the session", out, out)
        self.assertIn("floor rather than a total", out, out)


class TheConversionIsCountedNotEstimated(AttributionCase):
    """Acceptance clause 2: the nudge hook logs what it delivers, so REMINDER CONVERSION
    is a join and the caveat paragraph that stood in for one is gone."""

    def edits(self, session, n, cc_session=None):
        for i in range(n):
            payload = {"session_id": session, "tool_name": "Edit",
                       "tool_use_id": "toolu-%s-%d" % (session, i),
                       "tool_input": {"file_path": "/p/f%d.py" % i}}
            extra = {"CI_NOW": NOW}
            if cc_session:
                extra["CLAUDE_CODE_SESSION_ID"] = cc_session
            r = self.sh(["bash", CI_HOOK, "edit"], stdin=json.dumps(payload), **extra)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_checkpoint_logs_a_delivery_with_a_stable_id(self):
        self.edits("sess-a", 24)
        rows = self.jsonl(self.state / "reminders" / "nudges.jsonl")
        self.assertEqual([r["id"] for r in rows], ["ci-checkpoint", "ci-checkpoint"],
                         "the checkpoint nudge is not logged under one stable id: %r" % rows)
        self.assertEqual({r["session"] for r in rows}, {"sess-a"})
        self.assertEqual({r["kind"] for r in rows}, {"checkpoint"})

    def test_a_duplicate_delivery_of_one_event_is_logged_once(self):
        """Both wirings deliver every event, so the same payload arrives twice. The log
        is inside the claim_once guard that already covers the emit."""
        payload = json.dumps({"session_id": "sess-b", "tool_name": "Edit",
                              "tool_use_id": "toolu-repeat",
                              "tool_input": {"file_path": "/p/f.py"}})
        for _ in range(24):
            # The SAME tool_use_id every time: eleven of these are duplicates of one
            # event and must be claimed, not counted.
            self.sh(["bash", CI_HOOK, "edit"], stdin=payload, CI_NOW=NOW)
        rows = self.jsonl(self.state / "reminders" / "nudges.jsonl")
        self.assertEqual(rows, [], "a duplicated event was logged as a delivery: %r" % rows)

    def test_the_conversion_is_a_join_on_the_session_and_the_order(self):
        # Two nudged sessions; only one of them goes on to start a forge, and the forge
        # that started BEFORE its nudge does not count.
        self.edits("did-forge", 12, cc_session="cc-forged")
        self.edits("did-not", 12, cc_session="cc-idle")
        self.forge("start", "after", "4", "started after the nudge",
                   "--trigger", "t", "--trigger-kind", "agent-decision",
                   "--session", "cc-forged", SKILLFORGE_NOW=NOW + 10)
        out = self.report()
        self.assertIn("counted rows", out, out)
        self.assertIn("nudge deliveries logged:    2 in 2 session(s)", out, out)
        self.assertIn("of those sessions, forged:  1", out, out)
        self.assertIn("conversion:                 50%", out, out)
        self.assertNotIn("rough conversion", out, out)
        self.assertNotIn("loose upper bound", out, out)

    def test_a_forge_that_started_before_the_nudge_is_not_a_conversion_of_it(self):
        self.forge("start", "before", "4", "started first",
                   "--trigger", "t", "--trigger-kind", "agent-decision",
                   "--session", "cc-early", SKILLFORGE_NOW=NOW - 100)
        self.edits("nudged", 12, cc_session="cc-early")
        out = self.report()
        self.assertIn("nudge deliveries logged:    1 in 1 session(s)", out, out)
        self.assertIn("of those sessions, forged:  0", out, out)

    def test_one_delivery_recorded_under_two_session_ids_is_one_session(self):
        """The hook records both the payload session id and $CLAUDE_CODE_SESSION_ID,
        because the stores it must join against use different ones. Counting them as two
        sessions would halve every conversion this block prints."""
        self.edits("payload-sid", 12, cc_session="claude-sid")
        rows = self.jsonl(self.state / "reminders" / "nudges.jsonl")
        self.assertEqual(rows[0]["session"], "payload-sid")
        self.assertEqual(rows[0]["cc_session"], "claude-sid")
        # A forge in a THIRD session, only so the report gets past its "no forges
        # recorded yet" exit; it shares neither session id, so it cannot convert this
        # delivery and the denominator below is the one under test.
        self.forge("start", "unrelated", "4", "s",
                   "--trigger", "t", "--trigger-kind", "agent-decision",
                   "--session", "somebody-else", SKILLFORGE_NOW=NOW + 10)
        out = self.report()
        self.assertIn("of those sessions, forged:  0", out, out)
        self.assertIn("nudge deliveries logged:    1 in 1 session(s)", out, out)


class TheFromFlagWarnsAndDoesNotRefuse(AttributionCase):
    """`--from` follows `--trigger`: refusing does not produce a lineage id, it produces
    no forge record at all, and the cheapest way past a CLI that refuses is to stop
    calling it."""

    def test_a_start_with_no_from_still_starts_and_says_what_was_lost(self):
        r = self.sh([str(FORGE), "start", "nolineage", "4", "s",
                      "--trigger", "t", "--trigger-kind", "user-prompt"],
                     SKILLFORGE_NOW=NOW)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("UNATTRIBUTED", r.stderr, r.stderr)
        rows = self.ledger_rows("start")
        self.assertEqual(len(rows), 1, rows)
        self.assertNotIn("from", rows[0],
                         "an absent lineage was written as an empty one: %r" % rows[0])

    def test_a_lineage_id_with_a_space_in_it_is_refused_before_anything_is_written(self):
        r = self.sh([str(FORGE), "start", "bad", "4", "s", "--from", "c1 c2"],
                     SKILLFORGE_NOW=NOW)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("--from takes a lineage id", r.stderr, r.stderr)
        self.assertEqual(self.ledger_rows("start"), [])


class NoteAndReminderCarryTheCandidateOnlyWhenGivenOne(AttributionCase):
    """bin/skillnote DERIVES nothing. A note added by hand has no lineage, and saying so
    is the point: a guessed lineage is a join that reports a number nobody can act on."""

    def note(self, *extra):
        argv = [str(REPO / "bin" / "skillnote"), "add", "--scope", "project",
                "--project", str(self.project)] + list(extra) + ["--", "one line"]
        r = self.sh(argv, SKILLNOTE_NOW=NOW)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_a_hand_written_note_carries_no_candidate_field_at_all(self):
        self.note()
        rows = self.ledger_rows("note")
        self.assertEqual(len(rows), 1, rows)
        self.assertNotIn("candidate", rows[0], rows[0])

    def test_the_flag_is_carried_verbatim_onto_the_row(self):
        self.note("--candidate", "cdeadbeef")
        rows = self.ledger_rows("note")
        self.assertEqual(rows[0].get("candidate"), "cdeadbeef")

    def test_a_candidate_that_could_not_be_joined_is_refused(self):
        r = self.sh([str(REPO / "bin" / "skillnote"), "add", "--scope", "project",
                      "--project", str(self.project), "--candidate", 'c" or true',
                      "--", "one line"], SKILLNOTE_NOW=NOW)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("--candidate takes a lineage id", r.stderr, r.stderr)
        self.assertEqual(self.ledger_rows("note"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
