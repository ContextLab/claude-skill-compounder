#!/usr/bin/env python3
"""A request that keeps coming back. Real `claude -p` sessions and real judge calls; run by
hand.

Each case seeds a prompt log of its own with earlier requests from other sessions, then
types one request and reads the event log: a `repeat` event is the offer to make the
request a skill, and the session is asked what it was told.

  Offered (the same kind of request, made in at least three sessions, nothing recorded):
    digest     the weekly digest of merged pull requests, asked in two other sessions in
               other words.
    routine    red-team, run the tests, update the notes, commit: asked for three other
               changes in three other sessions.
    report     the monthly usage report, asked in the same words in two other sessions of
               another project.
  Not offered:
    topic      two earlier requests about the same module that asked for other work.
    twice      the same kind of request, made in one other session only.
    covered    asked in two other sessions, and a recorded lesson covers it: the lesson
               is offered for reuse and no new skill.
    words      two earlier requests that share the rare words and ask for other things.

usage: journey_repeat.py [--model haiku] [--keep] [--runs N]
"""
import argparse

import common

# The request is typed as it is, with one line that keeps the session from starting on it;
# a second, short turn asks what the mod's note said. Neither puts words about earlier
# requests into the request the judge reads.
TAIL = " Do not start on it yet: reply with the single word READY and nothing else."
ASK = "What did the [compound] note on my last message say and offer? Two sentences."

CASES = [
    ("digest", True, "Write the weekly digest of merged pull requests for the team again and post it to the team channel.",
     [("wk-1", "write the weekly digest of merged pull requests for the team and post it in the channel"),
      ("wk-2", "can you put together this week's digest of merged pull requests and post it to the team channel")], None),
    ("routine", True, "Red-team the export change, then run the full test suite, update the notes and commit it.",
     [("rt-1", "red-team the parser change, run the full test suite, update the notes and commit"),
      ("rt-2", "red-team the cache change, then run the full test suite, update the notes and commit it"),
      ("rt-3", "red-team the login fix, run the full test suite, update the notes, then commit")], None),
    ("report", True, "Generate the monthly usage report from the billing database as a spreadsheet with one tab per customer.",
     [("mo-1", "generate the monthly usage report from the billing database as a spreadsheet with one tab per customer"),
      ("mo-2", "generate the monthly usage report from the billing database as a spreadsheet with one tab per customer")], None),
    ("topic", False, "Write documentation for the csv parser module: a usage guide with examples for quoted fields and "
                     "custom delimiters.",
     [("tp-1", "fix the crash in the csv parser module when a quoted field holds a newline"),
      ("tp-2", "add a benchmark for the csv parser module with quoted fields and custom delimiters")], None),
    ("twice", False, "Translate the onboarding guide for new contributors into French and open it for review.",
     [("tw-1", "translate the onboarding guide for new contributors into Spanish and open it for review")], None),
    ("covered", False, "Write the release notes for version 2.4 of this project from the merged changes since the last tag.",
     [("cv-1", "write the release notes for version 2.2 of this project from the merged changes since the last tag"),
      ("cv-2", "write the release notes for version 2.3 from the merged changes since the last tag")],
     ("release-notes-format", "Use when writing the release notes of this project for a new version.",
      "Run scripts/release_notes.sh <version>: it lists the merged changes since the last tag, one line each, "
      "newest first, with the issue number.\n")),
    ("words", False, "Write a migration that adds an index to the orders table of the staging database, with a rollback.",
     [("wd-1", "rotate the credentials of the staging database and update the orders service config"),
      ("wd-2", "back up the orders table of the staging database before the weekend")], None),
]


def one(w, name, offered, request, earlier, lesson, model):
    project = w.project(name)
    other = "/Users/someone/older-%s" % name
    for n, (session, prompt) in enumerate(earlier):
        # The first earlier request was made in this project, the others elsewhere.
        w.seed_prompt(project if n == 0 else other, session, prompt, ts="2026-09-%02dT12:00:00Z" % (7 * n + 1))
    if lesson:
        w.add(project, *lesson)
    s = w.session(project, [request + TAIL, ASK], model)
    events = w.events(project, session=s.sid)
    w.show("event", [e for e in events if e["type"] in ("judge", "repeat", "reuse", "error")])
    repeats = [e for e in events if e["type"] == "repeat"]
    answer = (w.turns(s) or [""])[-1]
    said = "skill" in answer.lower() and any(mark in answer.lower() for mark in ("offer", "sessions", "lesson"))
    print("      %s: repeat events %d; asked what the note said, the session said: %s" % (
        name, len(repeats), answer[:300].replace("\n", " ")))
    if offered:
        w.check(name, "a repeat event was written: the offer was made", len(repeats) == 1, [e["type"] for e in events])
        w.check(name, "it counts at least three sessions", bool(repeats) and repeats[0].get("times", 0) >= 3,
                repeats[0].get("times") if repeats else "")
        w.check(name, "the session was told of the offer", said, answer[:300])
    else:
        w.check(name, "no repeat event was written: nothing was offered", repeats == [], repeats)
        if lesson:
            reuse = [e for e in events if e["type"] == "reuse"]
            w.check(name, "the recorded lesson was offered for reuse instead", bool(reuse) and lesson[0] in reuse[0].get("lessons", []),
                    reuse)
    w.check(name, "nothing in the mod failed", [e for e in events if e["type"] == "error"] == [],
            [e for e in events if e["type"] == "error"])
    return bool(repeats)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="haiku", help="the session's model (the judge is COMPOUND_MODEL)")
    ap.add_argument("--keep", action="store_true", help="keep the throwaway roots even when everything passes")
    ap.add_argument("--runs", type=int, default=1, help="how many times each case is run, each in a world of its own")
    args = ap.parse_args()
    tally = {}
    worlds = []
    for run in range(args.runs):
        for name, offered, request, earlier, lesson in CASES:
            # A prompt log and a store of its own: no case finds another's requests.
            w = common.World("repeat-%s" % name)
            worlds.append(w)
            made = one(w, name, offered, request, earlier, lesson, args.model)
            row = tally.setdefault(name, [offered, 0, 0])
            row[1] += 1
            row[2] += 1 if made else 0
    print("\ncase       should offer   offered / runs")
    for name, (offered, runs, made) in tally.items():
        print("%-10s %-14s %d / %d" % (name, "yes" if offered else "no", made, runs))
    right = sum(made if offered else runs - made for offered, runs, made in tally.values())
    wrong = sum(made for offered, _runs, made in tally.values() if not offered)
    total = sum(runs for _offered, runs, _made in tally.values())
    print("right %d of %d; offered wrongly %d" % (right, total, wrong))
    results = [ok for w in worlds for ok in w.results]
    last = worlds[-1]
    last.results = results
    if all(results) and not args.keep:
        import shutil
        for w in worlds[:-1]:
            shutil.rmtree(w.root, ignore_errors=True)
    last.finish(args.keep)


if __name__ == "__main__":
    main()
