#!/usr/bin/env python3
"""Findings from Claude Code's /insights, end to end. Real `claude -p` sessions and one real
`claude -p /insights`; run by hand.

THIS JOURNEY SPENDS MONEY: the one `/insights` run costs about $2 at list price (it was
$1.73 in the measured run), on top of the short sessions. It needs `--config fresh`, so the
run reads and writes only the throwaway configuration directory, never `~/.claude`.

  seed      two short sessions in a scratch project, under the fresh configuration: one
            meets a failing build and works around it, the other is plain.
  run       `compound insights --run`, with COMPOUND_INSIGHTS_MIN_SESSIONS=1, COMPOUND_CLAUDE_DIR
            naming the fresh configuration and CLAUDE_CONFIG_DIR naming an empty decoy, so the
            report lands in the fresh configuration only if the CLI passed that directory to
            the child itself. The child is given the mod (CLAUDE_CODE_PLUGIN_DIRS) and the CLI
            adds COMPOUND_OFF=1. Checked: exit 0; outcome `ok`; a `usage-data/report.html`
            newer than the start under the fresh configuration and none under the decoy; the
            real `~/.claude/usage-data/report.html` as it was; every event the run wrote is an
            `insight` of the session `insights` (nothing from the child session); the state
            file written with `started` and `finished`; the lock free; no worker left.
  findings  what the harvest recorded is printed. `/insights` skips sessions it finds too
            short, so it may record none: that is printed as a result, not a failure.
  told      a new session in the project: when a finding is open for it, its first prompt
            is given a RECORDED-INSIGHT block naming it (the stream holds the block, and the
            `remind` event names the id); when none is, it is given none. Its own
            `insights --start` does not start a second run (`started` is unchanged).

usage: journey_insights.py [--model haiku] [--keep]
"""
import fcntl
import json
import os
import subprocess
import time

import common

QUIET = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}
# The seeding sessions never start a run of their own: the run below is the only one.
NO_RUN = dict(QUIET, COMPOUND_INSIGHTS_DAYS="0")
BUILD_AGAIN = "Now build it once more with the profile prod, the same way, and tell me the line it prints."
NOTE = ("Create a file named todo.txt in this directory holding the single line 'water the plants', using one Bash "
        "call. Then reply with the single word DONE.")
NOTE_AGAIN = "Print todo.txt with one Bash call and tell me the line it holds."
READY = "Do not run any tool and do not invoke a skill. Reply with the single word READY."
REAL_REPORT = os.path.expanduser(os.path.join("~", ".claude", "usage-data", "report.html"))


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def lock_is_free(home):
    path = os.path.join(home, "insights.lock")
    if not os.path.exists(path):
        return True
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def workers(home):
    """Processes still running `compound insights --run` for this world's home."""
    done = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True)
    return [line.strip() for line in done.stdout.splitlines() if "insights --run" in line and home in line]


def state(w, project):
    done = w.cli(project, "insights", "--json")
    return json.loads(done.stdout) if done.returncode == 0 else {}


def main():
    args = common.arguments(__doc__)
    if common.CONFIG != "fresh":
        raise SystemExit("journey_insights.py runs only with --config fresh: /insights must not see ~/.claude")
    w = common.World("insights")
    project = w.project("alpha", build=True)
    decoy = os.path.join(w.root, "decoy-config")
    os.makedirs(decoy)

    first = w.session(project, [common.BUILD_TASK, BUILD_AGAIN], args.model, tools=("Bash", "Skill"), **NO_RUN)
    second = w.session(project, [NOTE, NOTE_AGAIN], args.model, **NO_RUN)
    seeded = {first.sid, second.sid}
    failed = [c for c in first.bash() if c[1]]
    w.check("seed", "the first session met the failing build and finished",
            bool(failed) and first.returncode == 0 and "build ok" in first.result, first.result[-200:])
    w.check("seed", "the second session finished", second.returncode == 0, second.result[-200:])
    w.check("seed", "no run of /insights was started yet", not os.path.exists(os.path.join(w.home, "insights.json")))

    before = w.events(project)
    real_before = mtime(REAL_REPORT)
    env = w.env(project, COMPOUND_CLAUDE_DIR=w.config, CLAUDE_CONFIG_DIR=decoy, CLAUDE_CODE_PLUGIN_DIRS=common.PLUGIN,
                COMPOUND_INSIGHTS_MIN_SESSIONS="1")
    began = time.time()
    run = subprocess.run([common.CLI, "insights", "--run"], cwd=project, env=env, capture_output=True, text=True,
                         timeout=1000)
    took = time.time() - began
    print("      the run took %.0f s; exit %d; stderr %r" % (took, run.returncode, run.stderr.strip()[:300]))
    after = state(w, project)
    w.show("state", [{k: after.get(k) for k in ("started", "finished", "outcome", "message", "harvested")}])
    w.check("run", "compound insights --run exited 0", run.returncode == 0, run.stderr[-300:])
    w.check("run", "the outcome is ok", after.get("outcome") == "ok", after.get("message"))
    report = os.path.join(w.config, "usage-data", "report.html")
    w.check("run", "a report.html newer than the start is under the fresh configuration",
            (mtime(report) or 0) >= int(began), report)
    w.check("run", "the decoy CLAUDE_CONFIG_DIR got no usage-data (the CLI passed the directory itself)",
            not os.path.exists(os.path.join(decoy, "usage-data")), os.listdir(decoy))
    w.check("run", "the real ~/.claude/usage-data/report.html is as it was", mtime(REAL_REPORT) == real_before,
            "%s -> %s" % (real_before, mtime(REAL_REPORT)))
    known = set(json.dumps(e, sort_keys=True) for e in before)
    new = [e for e in w.events(project) if json.dumps(e, sort_keys=True) not in known]
    w.check("run", "every event the run wrote is an insight of the session `insights`: none from the child",
            all(e.get("type") == "insight" and e.get("session") == "insights" for e in new),
            [(e.get("type"), e.get("session")) for e in new if e.get("type") != "insight"])
    on_disk = {}
    try:
        with open(os.path.join(w.home, "insights.json")) as fh:
            on_disk = json.load(fh)
    except (OSError, ValueError):
        pass
    w.check("run", "the state file holds started and finished",
            isinstance(on_disk.get("started"), (int, float)) and bool(on_disk.get("finished")), on_disk)
    w.check("run", "the lock is free", lock_is_free(w.home))
    w.check("run", "no worker is left running", workers(w.home) == [], workers(w.home))

    findings = after.get("findings") or []
    mine = [f for f in findings if f.get("source") == "facet" and f.get("project") == project]
    report_items = [f for f in findings if f.get("source") == "report"]
    print("      facets read: %s; findings: %d for this project, %d from the report, %d in all" % (
        (after.get("harvested") or {}).get("facets"), len(mine), len(report_items), len(findings)))
    for f in findings:
        print("      finding %s %s %s %s" % (f.get("id"), f.get("source"), f.get("state"), (f.get("text") or "")[:160]))
    if not findings:
        print("      /insights produced no finding for these sessions: a result, not a failure")

    told_ids = [f["id"] for f in mine + report_items if f.get("state") == "open"]
    s = w.session(project, READY, args.model, tools=("Skill",), **QUIET)
    rows = w.events(project, session=s.sid, kind="remind")
    w.show("remind", rows)
    named = [i for e in rows for i in (e.get("insights") or [])]
    with open(s.stream) as fh:
        stream = fh.read()
    if told_ids:
        w.check("told", "the first prompt was given a RECORDED-INSIGHT block naming an open finding",
                any(("RECORDED-INSIGHT id=%s" % i) in stream for i in told_ids), told_ids)
        w.check("told", "its remind event names the findings shown", bool(named) and set(named) <= set(told_ids),
                named)
    else:
        w.check("told", "with no finding open, the first prompt was given none",
                "RECORDED-INSIGHT" not in stream and named == [], named)
    w.check("told", "the session's own start did not begin a second run",
            state(w, project).get("started") == after.get("started"), state(w, project).get("started"))
    w.check("told", "the session answered", "READY" in s.result, s.result[:200])
    w.check("told", "no event came from a session other than the three run here and the harvest",
            {e.get("session") for e in w.events(project)} <= seeded | {s.sid, "insights"},
            sorted({e.get("session") for e in w.events(project)} - seeded - {s.sid, "insights"}))
    w.finish(args.keep)


if __name__ == "__main__":
    main()
