#!/usr/bin/env python3
"""Findings from Claude Code's /insights, end to end, started the way a user's machine starts
them: by the first typed prompt of a real session. Real `claude -p` sessions and ONE real
`claude -p /insights`; run by hand.

THIS JOURNEY SPENDS MONEY: the one `/insights` run costs about $2 at list price (it was
$1.73 in the measured run), on top of the short sessions. It needs `--config fresh`, so the
run reads and writes only the throwaway configuration directory, never `~/.claude`. Every
session runs with COMPOUND_CLAUDE_DIR naming that same directory, so the CLI hands it to the
child `claude` and harvests from it.

  seed      three sessions in a scratch project, each a few turns long, two of which meet a
            failing build and work around it. They run with COMPOUND_INSIGHTS_DAYS=0 and
            COMPOUND_INSIGHTS_MIN_SESSIONS=1, so only the days setting keeps them from
            starting a run.
  f         no seed session started a run (no state file), and `compound insights --start
            --json` under the same environment answers `disabled`. The log holds events of a
            seeded session, or the paid leg would not be due: checked before it.
  a         the starting session: one typed prompt, with COMPOUND_INSIGHTS_MIN_SESSIONS=1, the
            mod loaded through CLAUDE_CODE_PLUGIN_DIRS (so the child `claude` the worker starts
            loads it too, and its COMPOUND_OFF=1 is what keeps it quiet). After that session
            has exited, the state says a run started (`started` set) and the worker still
            holds the lock: it outlived the session. The state is then polled, with a
            deadline, until it leaves `running`; it must reach `ok`.
  b         a second session's first prompt, made while the run is under way, does not start
            another: `started` unchanged, and exactly one new `report-*.html`.
  c         `report.html`, newer than the start, is under the fresh configuration only (not
            under the journey's COMPOUND_CLAUDE_DIR default nor under COMPOUND_HOME), and every
            file under the real `~/.claude/usage-data` (if there is one) kept its mtime.
  d         no event in the log is of a session other than the ones run here and the run's
            own `insights`; the transcript directory the child left is printed.
  e         a finding harvested for the scratch project is shown at a later session's first
            prompt as a RECORDED-INSIGHT block, and its `remind` names it. When `/insights`
            harvested none for sessions this short, the leg is printed as UNPROVEN, not
            passed, and the journey still exits 0 when every other check held.
  g         the wall time of the run, and what any output says of cost.

Whatever happens, the `finally` stops a worker still running for this world (its whole
process group and the child's) so no `claude` is left behind.

`--dry` runs only what needs no model call: the helpers, the `disabled` answer, the snapshot
of the real usage-data, the cleanup. It starts no `claude` and needs no credential.

usage: journey_insights.py [--model haiku] [--keep] [--deadline SECONDS] [--dry]
"""
import argparse
import calendar
import fcntl
import json
import os
import pwd
import signal
import subprocess
import time

import common

QUIET = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}
# The seeding sessions could start a run but for the days setting: f.
SEED = dict(QUIET, COMPOUND_INSIGHTS_DAYS="0", COMPOUND_INSIGHTS_MIN_SESSIONS="1")
BUILD_AGAIN = "Now build it once more with the profile prod, the same way, and tell me the line it prints."
BUILD_LAST = "Build it a third time with the profile test and tell me the line it prints."
NOTE = ("Create a file named todo.txt in this directory holding the single line 'water the plants', using one Bash "
        "call. Then reply with the single word DONE.")
NOTE_AGAIN = "Print todo.txt with one Bash call and tell me the line it holds."
NOTE_LAST = "Append the line 'call the plumber' to todo.txt with one Bash call, then print the file."
READY = "Do not run any tool and do not invoke a skill. Reply with the single word READY."
REAL_USAGE = os.path.join(os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir), ".claude", "usage-data")


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def snapshot(top):
    """{path: mtime} of every file and directory under `top`; {} when there is no `top`."""
    out = {}
    if not os.path.isdir(top):
        return out
    for base, dirs, files in os.walk(top):
        for name in dirs + files:
            path = os.path.join(base, name)
            out[path] = mtime(path)
    out[top] = mtime(top)
    return out


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
    """The pids that hold this world's insights.lock open: the worker, whose argv does not
    name the home (it is `python3 .../compound insights --run`), is found by the file it
    holds. [] when lsof is missing or nothing holds it."""
    path = os.path.join(home, "insights.lock")
    if not os.path.exists(path):
        return []
    try:
        done = subprocess.run(["lsof", "-t", path], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return sorted(int(pid) for pid in done.stdout.split() if pid.strip().isdigit() and int(pid) != os.getpid())


def children(pid):
    try:
        done = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(one) for one in done.stdout.split() if one.strip().isdigit()]


def stop_workers(home):
    """Stops every worker of this world and the process group of each of its children (the
    child `claude` runs in a group of its own). Returns what it stopped."""
    stopped = []
    for pid in workers(home):
        for child in children(pid):
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(child, sig)
                except OSError:
                    break
                time.sleep(2)
            stopped.append(child)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except OSError:
                break
            time.sleep(1)
        stopped.append(pid)
    return stopped


def read_state(home):
    try:
        with open(os.path.join(home, "insights.json")) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def finished_after(saved, moment):
    """Whether the state `saved` says the run finished after `moment` (epoch seconds)."""
    try:
        at = calendar.timegm(time.strptime(str(saved.get("finished")), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return False
    return saved.get("outcome") not in (None, "running") and at >= moment


def state(w, project):
    done = w.cli(project, "insights", "--json", COMPOUND_CLAUDE_DIR=w.config)
    return json.loads(done.stdout) if done.returncode == 0 else {}


def reports(config):
    folder = os.path.join(config, "usage-data")
    try:
        return sorted(name for name in os.listdir(folder) if name.startswith("report-") and name.endswith(".html"))
    except OSError:
        return []


def slug(path):
    return "".join(ch if ch.isalnum() else "-" for ch in path)


def costs(stream):
    """The total_cost_usd of each result message of a session's stream."""
    out = []
    with open(stream) as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "result" and msg.get("total_cost_usd") is not None:
                out.append(msg["total_cost_usd"])
    return out


def dry(w, project):
    """What needs no model call. No `claude` is started: the days setting is 0."""
    answer = w.cli(project, "insights", "--start", "--json", COMPOUND_CLAUDE_DIR=w.config, **SEED)
    w.check("dry", "insights --start under the seed environment answers disabled",
            answer.returncode == 0 and json.loads(answer.stdout or "{}").get("why") == "disabled", answer.stdout)
    w.check("dry", "it wrote no state", not os.path.exists(os.path.join(w.home, "insights.json")))
    w.check("dry", "the lock is free and no worker holds it", lock_is_free(w.home) and workers(w.home) == [])
    # A lock held by this process is seen as held, and its holder is found by the file.
    os.makedirs(w.home, exist_ok=True)
    fd = os.open(os.path.join(w.home, "insights.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        holder = subprocess.Popen(["sleep", "30"], pass_fds=(fd,), start_new_session=True)
        try:
            time.sleep(0.5)
            found = workers(w.home)
            w.check("dry", "a process holding the lock file is found by it", holder.pid in found, found)
            w.check("dry", "stop_workers stops it", holder.pid in stop_workers(w.home) and holder.wait(timeout=10) is not None)
        finally:
            if holder.poll() is None:
                holder.kill()
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    w.check("dry", "the lock is free again", lock_is_free(w.home))
    before = snapshot(REAL_USAGE)
    w.check("dry", "the real usage-data snapshot is stable", snapshot(REAL_USAGE) == before,
            "%d entries under %s" % (len(before), REAL_USAGE))
    w.check("dry", "no report under the fresh configuration yet", reports(w.config) == [])
    print("      the child would leave its transcript under %s" % os.path.join(w.config, "projects", slug(w.home)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="haiku", help="the sessions' model (the judge is COMPOUND_MODEL)")
    ap.add_argument("--keep", action="store_true", help="keep the throwaway root even when everything passes")
    ap.add_argument("--deadline", type=int, default=1100,
                    help="seconds to wait for the run to leave `running` (the CLI kills it at 900)")
    ap.add_argument("--dry", action="store_true", help="only what needs no model call; starts no claude")
    args = common.parse(ap)
    if args.dry:
        w = common.World("insights-dry", config="ambient")
        project = w.project("alpha", build=True)
        try:
            dry(w, project)
        finally:
            stop_workers(w.home)
        w.finish(args.keep)
    if common.CONFIG != "fresh":
        raise SystemExit("journey_insights.py runs only with --config fresh: /insights must not see ~/.claude")
    w = common.World("insights")
    project = w.project("alpha", build=True)
    # Every session and every CLI call of this journey names the fresh configuration as the
    # Claude directory: the one the sessions write their transcripts to and /insights reads.
    here = dict(COMPOUND_CLAUDE_DIR=w.config)
    try:
        run(w, project, args, here)
    finally:
        left = stop_workers(w.home)
        if left:
            print("      cleanup: stopped %s, still running for this world" % left)
    w.finish(args.keep)


def run(w, project, args, here):
    real_before = snapshot(REAL_USAGE)

    # ---- seed, and f ----
    first = w.session(project, [common.BUILD_TASK, BUILD_AGAIN, BUILD_LAST], args.model, tools=("Bash", "Skill"),
                      **here, **SEED)
    second = w.session(project, [NOTE, NOTE_AGAIN, NOTE_LAST], args.model, **here, **SEED)
    third = w.session(project, [common.BUILD_TASK, BUILD_AGAIN], args.model, tools=("Bash", "Skill"), **here, **SEED)
    seeded = {first.sid, second.sid, third.sid}
    failed = [c for c in first.bash() + third.bash() if c[1]]
    w.check("seed", "the build sessions met the failing build and worked around it",
            bool(failed) and "build ok" in first.result and "build ok" in third.result,
            (first.result[-160:], third.result[-160:]))
    w.check("seed", "the note session finished", second.returncode == 0, second.result[-200:])
    w.check("f", "no seed session started a run (COMPOUND_INSIGHTS_DAYS=0): no state file",
            not os.path.exists(os.path.join(w.home, "insights.json")))
    answer = w.cli(project, "insights", "--start", "--json", **here, **SEED)
    w.check("f", "insights --start under the same environment answers disabled",
            answer.returncode == 0 and json.loads(answer.stdout or "{}").get("why") == "disabled", answer.stdout)
    logged = {e.get("session") for e in w.events(project)} & seeded
    w.check("f", "the log holds events of a seeded session, so one run is due at MIN_SESSIONS=1", bool(logged),
            sorted(logged))
    if not all(w.results):
        print("      stopping before the paid leg: a check above failed")
        return

    # ---- a: the run started by a real session's first typed prompt ----
    reports_before = reports(w.config)
    starting = dict(QUIET, COMPOUND_INSIGHTS_MIN_SESSIONS="1", CLAUDE_CODE_PLUGIN_DIRS=common.PLUGIN)
    began = time.time()
    starter = w.session(project, READY, args.model, tools=("Skill",), installed=True, **here, **starting)
    ended = time.time()
    after_start = read_state(w.home)
    held = not lock_is_free(w.home)
    w.show("state", [after_start])
    w.check("a", "the starting session answered", "READY" in starter.result, starter.result[:200])
    w.check("a", "after its first prompt the state says a run started",
            isinstance(after_start.get("started"), (int, float)) and after_start["started"] >= int(began) - 1,
            after_start)
    w.check("a", "the worker outlived the session: the lock is held after the session exited, or the run "
            "finished after it", held or finished_after(after_start, ended),
            "lock held: %s; workers %s; state %s" % (held, workers(w.home), after_start))

    # ---- b: a second session during the run ----
    during = w.session(project, READY, args.model, tools=("Skill",), installed=True, **here, **starting)
    w.check("b", "a second session's first prompt during the run did not start another: started unchanged",
            read_state(w.home).get("started") == after_start.get("started"),
            (after_start.get("started"), read_state(w.home).get("started")))
    w.check("b", "that session answered", "READY" in during.result, during.result[:200])

    # ---- poll ----
    seen = ["running"] if after_start.get("outcome") == "running" else []
    deadline = time.time() + args.deadline
    last = read_state(w.home)
    while time.time() < deadline:
        last = read_state(w.home)
        if last.get("outcome") not in (None, "running") and lock_is_free(w.home):
            break
        if not seen or seen[-1] != last.get("outcome"):
            seen.append(last.get("outcome"))
        print("      %4.0f s: outcome %s, lock %s" % (time.time() - began, last.get("outcome"),
                                                      "free" if lock_is_free(w.home) else "held"))
        time.sleep(15)
    if not seen or seen[-1] != last.get("outcome"):
        seen.append(last.get("outcome"))
    took = time.time() - began
    w.show("state", [last])
    w.check("a", "the state went from running to ok", seen[:1] == ["running"] and last.get("outcome") == "ok",
            "%s; message %r" % (" -> ".join(str(s) for s in seen), last.get("message")))
    w.check("a", "the lock is free and no worker is left", lock_is_free(w.home) and workers(w.home) == [],
            workers(w.home))
    new_reports = [name for name in reports(w.config) if name not in reports_before]
    w.check("b", "exactly one /insights ran: one new report-*.html", len(new_reports) == 1, new_reports)
    print("      the second session's own events: %s" % sorted(
        {e.get("type") for e in w.events(project, session=during.sid)}))

    # ---- c ----
    report = os.path.join(w.config, "usage-data", "report.html")
    w.check("c", "a report.html newer than the start is under the fresh configuration",
            (mtime(report) or 0) >= int(after_start.get("started") or began), report)
    w.check("c", "none under the world's default Claude directory or under COMPOUND_HOME",
            not os.path.exists(os.path.join(w.claude, "usage-data"))
            and not os.path.exists(os.path.join(w.home, "usage-data")))
    real_after = snapshot(REAL_USAGE)
    changed = sorted(path for path in set(real_before) | set(real_after) if real_before.get(path) != real_after.get(path))
    w.check("c", "every entry under the real %s kept its mtime (%d entries)" % (REAL_USAGE, len(real_before)),
            changed == [], changed[:5])

    # ---- d ----
    sessions = {e.get("session") for e in w.events(project)}
    ours = seeded | {starter.sid, during.sid, "insights"}
    w.check("d", "the log holds no event of the child session (it ran with COMPOUND_OFF=1)", sessions <= ours,
            sorted(sessions - ours))
    projects = os.path.join(w.config, "projects")
    listed = sorted(os.listdir(projects)) if os.path.isdir(projects) else []
    child = [name for name in listed if name == slug(w.home)]
    print("      transcript directories under %s: %s" % (projects, listed))
    print("      the child's (cwd COMPOUND_HOME %s): %s" % (
        w.home, os.path.join(projects, child[0]) if child else "none found under that name"))

    # ---- e ----
    now = state(w, project)
    findings = now.get("findings") or []
    mine = [f for f in findings if f.get("source") == "facet" and f.get("project") == project and f.get("state") == "open"]
    print("      harvested: %s" % json.dumps(now.get("harvested")))
    for f in findings:
        print("      finding %s %s %s %s" % (f.get("id"), f.get("source"), f.get("state"), (f.get("text") or "")[:160]))
    if mine:
        later = w.session(project, READY, args.model, tools=("Skill",), **here, **QUIET)
        rows = w.events(project, session=later.sid, kind="remind")
        w.show("remind", rows)
        named = [i for e in rows for i in (e.get("insights") or [])]
        with open(later.stream) as fh:
            stream = fh.read()
        ids = [f["id"] for f in mine]
        w.check("e", "a later session's first prompt holds a RECORDED-INSIGHT block naming a finding of this project",
                any(("RECORDED-INSIGHT id=%s" % i) in stream for i in ids), ids)
        w.check("e", "its remind event names it", bool(set(named) & set(ids)), named)
    else:
        print("UNPROVEN e        /insights harvested no finding for this project from sessions this short: the "
              "reminder leg was not exercised (not a pass)")

    # ---- g ----
    finished = last.get("finished")
    print("      g: the run took %.0f s of wall time from the starting prompt to a free lock; state started %s, "
          "finished %s" % (took, after_start.get("started"), finished))
    print("      g: cost: the child's output is discarded, so no output reports what /insights cost; the sessions "
          "reported %s USD (starting session %s, second %s)" % (
              sum(sum(costs(s.stream)) for s in (first, second, third, starter, during)),
              costs(starter.stream), costs(during.stream)))


if __name__ == "__main__":
    main()
