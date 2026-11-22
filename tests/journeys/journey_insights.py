#!/usr/bin/env python3
"""Findings from Claude Code's /insights, end to end, started the way a user's machine starts
them: by the first typed prompt of a real session. Real `claude -p` sessions and ONE real
`claude -p /insights`; run by hand.

THIS JOURNEY SPENDS MONEY OR USAGE: one `/insights` run (it cost $1.73 at list price in the
measured run) on top of a few short sessions on the cheapest model.

Two ways to run it (`--config`, see common.py):

  ambient   (how it is meant to be run) every `claude` the journey starts, the worker and
            the child `claude -p /insights` use the user's own configuration and login
            (`~/.claude`, no CLAUDE_CONFIG_DIR). `/insights` then reads the user's real
            sessions and writes its report and caches under the real `~/.claude/usage-data`,
            as it does when typed. COMPOUND_CLAUDE_DIR is left unset, so the CLI reads that
            same directory. COMPOUND_HOME stays a temporary directory in every process: the
            real `~/.claude/compound` (log, lessons, state, lock) is never read or written,
            which the journey asserts. Because the harvest reads real output, the journey
            prints counts, sources, kinds and states only: no finding text, goal, project path
            or session id. The temporary root holds findings derived from real sessions, so
            it is always removed at the end, whatever happened.
  fresh     every `claude` runs under an empty configuration in the throwaway root and needs
            a credential in the environment (common.py); `/insights` sees only the journey's
            own sessions, and COMPOUND_CLAUDE_DIR names that configuration.

  load      before anything paid: the first seed session's init message lists exactly one
            `compound` plugin, this working copy; an event of that session is in the
            temporary log; and the real event log gained no line naming it.
  seed      three sessions in a scratch project, each a few turns long, two of which meet a
            failing build and work around it. They run with COMPOUND_INSIGHTS_DAYS=0 and
            COMPOUND_INSIGHTS_MIN_SESSIONS=1, so only the days setting keeps them from
            starting a run.
  f         no seed session started a run (no state file), and `compound insights --start
            --json` under the same environment answers `disabled`. The log holds events of a
            seeded session, or the paid leg would not be due: checked before it.
  a         the starting session: one typed prompt, with COMPOUND_INSIGHTS_MIN_SESSIONS=1.
            After that session has exited, the state says a run started (`started` set) and
            the worker still holds the lock: it outlived the session. The state is then
            polled, with a deadline, until it leaves `running`; it must reach `ok`. When no
            run started, the journey prints what it saw and stops there (non-zero).
  b         a second session's first prompt, made while the run is under way, does not start
            another: `started` unchanged, and exactly one new `report-*.html` in the
            usage-data the run wrote to.
  c         fresh: `report.html`, newer than the start, is under the fresh configuration only,
            and every entry under the real `~/.claude/usage-data` kept its mtime. ambient: the
            report under the real usage-data is newer than the start, and nothing was written
            to the temporary root's configuration directories.
  d         no event in the temporary log is of a session other than the ones run here and
            the run's own `insights`; the child's transcripts are found and counted, and no
            line of the real event log names the child or a journey session.
  e         a finding listed for the scratch project (one about its sessions, or a report
            finding, which is listed in every project) is shown at a later session's first
            prompt as a RECORDED-INSIGHT block with its `in-` id (read from that session's
            transcript: what a hook adds to a prompt is not in the -p stream), and that
            session's `remind` names the id and carries `headless: true` (a `-p` session has
            no one at its prompt, so the showing is not counted toward the finding's three).
            With none listed the leg is printed as UNPROVEN, not passed.
  g         the wall time of the run, and what any output says of cost.

`--leg timeout` runs one leg on its own, in place of all of the above: one real `compound
insights --run` in a temporary COMPOUND_HOME with COMPOUND_INSIGHTS_TIMEOUT set to a few
seconds (`--timeout`, default 8), so the real `claude -p /insights` is killed early. It checks
that the outcome is `timeout`, that one `error` event has `where` `insights.run`, that no
process of the child's process group is left (checked by group, not by name), that the lock
is free, that nothing was harvested, and that the next `insights --start` under the default
days answers `too soon`. Under ambient it prints how many entries under the real
usage-data the killed run added or changed (counts only).

Whatever happens, the `finally` stops a worker still running for this world (its whole
process group and the child's) so no `claude` is left behind. The real
`~/.claude/compound/insights.json` (the user's own, when a run has happened there) must be
as it was before: its size and modification time are compared, never its contents.

What has been run for real: the whole journey under `--config ambient` (26 of 26 checks on
21 Nov 2026, the `headless` check of e included), and `--leg timeout` under
`--config ambient`. `--config fresh` has only been checked with `--dry`: it needs
CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY in the environment, and has never run for real.

`--dry` runs only what needs no model call, for the configuration given: the helpers, the
`disabled` answer, the snapshots, the cleanup. It starts no `claude` and needs no credential.

usage: journey_insights.py [--config ambient|fresh] [--model haiku] [--keep] [--deadline SECONDS] [--dry]
                           [--leg all|timeout] [--timeout SECONDS]
"""
import argparse
import calendar
import collections
import fcntl
import json
import os
import pwd
import shutil
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
REAL_CLAUDE = os.path.join(os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir), ".claude")
REAL_USAGE = os.path.join(REAL_CLAUDE, "usage-data")
REAL_LOG = os.path.join(REAL_CLAUDE, "compound", "events.jsonl")
REAL_STATE = os.path.join(REAL_CLAUDE, "compound", "insights.json")


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def size(path):
    try:
        return os.stat(path).st_size
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


def real_log_naming(offset, needles):
    """Which of `needles` (session ids) a line appended to the real event log after byte
    `offset` names. Other sessions of the user write to it meanwhile, so growth alone says
    nothing; a line naming a journey's session would."""
    needles = [n for n in needles if n]
    try:
        with open(REAL_LOG, "rb") as fh:
            fh.seek(offset or 0)
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    return [n for n in needles if n in text]


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
    holds. [] when nothing holds it; None when lsof could not be asked (missing, failed or
    timed out), so the caller can say it does not know."""
    path = os.path.join(home, "insights.lock")
    if not os.path.exists(path):
        return []
    try:
        done = subprocess.run(["lsof", "-t", path], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    # lsof exits 1 when no process has the file open, with nothing on stdout.
    if done.returncode not in (0, 1) or (done.returncode == 1 and done.stderr.strip()):
        return None
    return sorted(int(pid) for pid in done.stdout.split() if pid.strip().isdigit() and int(pid) != os.getpid())


def children(pid):
    try:
        done = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(one) for one in done.stdout.split() if one.strip().isdigit()]


def stop_workers(home):
    """Stops every worker of this world and the process group of each of its children (the
    child `claude` runs in a group of its own). Returns what it stopped. When lsof cannot say
    who holds the lock, it says so and how to look by hand, and stops nothing."""
    stopped = []
    found = workers(home)
    if found is None:
        path = os.path.join(home, "insights.lock")
        print("      cleanup: lsof could not be asked who holds %s, so no worker was stopped. Check by hand: "
              "`lsof %s` lists the worker; stop its group and its child's with `kill -TERM -<pid>` "
              "(the child is `pgrep -P <pid>`)" % (path, path))
        return stopped
    for pid in found:
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


def shown_state(saved, private):
    """The state as the journey prints it: under ambient its message, which can name a file
    of a real session, is replaced by its length."""
    if not private:
        return saved
    out = {k: saved.get(k) for k in ("started", "finished", "outcome", "harvested")}
    out["message_chars"] = len(str(saved.get("message") or ""))
    return out


def finished_after(saved, moment):
    """Whether the state `saved` says the run finished after `moment` (epoch seconds)."""
    try:
        at = calendar.timegm(time.strptime(str(saved.get("finished")), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return False
    return saved.get("outcome") not in (None, "running") and at >= moment


def reports(usage):
    try:
        return sorted(name for name in os.listdir(usage) if name.startswith("report-") and name.endswith(".html"))
    except OSError:
        return []


def slug(path):
    return "".join(ch if ch.isalnum() else "-" for ch in path)


def transcripts(config, home):
    """The transcript files (*.jsonl) Claude Code keeps for sessions whose working directory
    was `home`, under <config>/projects/<slug>/: the child's."""
    folder = os.path.join(config, "projects", slug(home))
    try:
        return folder, sorted(name for name in os.listdir(folder) if name.endswith(".jsonl"))
    except OSError:
        return folder, []


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


def loaded(stream):
    """The paths of the `compound` plugins the session's init message lists, or None when it
    has no init message with a plugin list."""
    with open(stream) as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "system" and msg.get("subtype") == "init":
                plugins = msg.get("plugins")
                if not isinstance(plugins, list):
                    return None
                return [p.get("path") for p in plugins if isinstance(p, dict) and p.get("name") == "compound"]
    return None


def real_guard(w):
    """What the real store holds before the journey: the log's size and mtime, and the size
    and mtime of the real state file (None when there is none; it is the user's own once a
    run has happened on this machine, and its contents are never read). Checked again at the
    end."""
    before = {"size": size(REAL_LOG), "mtime": mtime(REAL_LOG), "state": (size(REAL_STATE), mtime(REAL_STATE))}
    print("      the real event log: %s bytes before; the real insights.json: %s" % (
        before["size"], "absent" if before["state"][0] is None else "present (left as it is)"))
    return before


def real_after(w, before, sids):
    named = real_log_naming(before["size"], sids)
    w.check("real", "the real ~/.claude/compound/insights.json is as it was (size and mtime)",
            (size(REAL_STATE), mtime(REAL_STATE)) == before["state"])
    w.check("real", "no line the real event log gained names a session of this journey (%d sessions)" % len(sids),
            named == [], "%d named" % len(named))
    print("      the real event log: %s bytes after (other sessions of the user write to it too)" % size(REAL_LOG))


def dry(w, project, here, ambient):
    """What needs no model call. No `claude` can be started, by construction as in the Python
    tests: the days setting is 0, and the call gets a HOME in the throwaway root (so there is
    no ~/.local/bin/claude) and PATH=/usr/bin:/bin (where there is no claude)."""
    before = real_guard(w)
    sandbox_home = os.path.join(w.root, "dry-home")
    os.makedirs(sandbox_home, exist_ok=True)
    w.check("dry", "no claude in the call's PATH or its HOME's .local/bin",
            not any(os.path.exists(os.path.join(d, "claude")) for d in ("/usr/bin", "/bin",
                                                                       os.path.join(sandbox_home, ".local", "bin"))))
    answer = w.cli(project, "insights", "--start", "--json", HOME=sandbox_home, PATH="/usr/bin:/bin", **here, **SEED)
    w.check("dry", "insights --start under the seed environment answers disabled",
            answer.returncode == 0 and json.loads(answer.stdout or "{}").get("why") == "disabled", answer.stdout)
    w.check("dry", "it wrote no state", not os.path.exists(os.path.join(w.home, "insights.json")))
    state = w.cli(project, "insights", "--json", HOME=sandbox_home, PATH="/usr/bin:/bin", **here)
    data = json.loads(state.stdout or "{}") if state.returncode == 0 else {}
    w.check("dry", "the CLI reads the Claude directory this configuration means",
            data.get("claude_dir") == (os.path.join(sandbox_home, ".claude") if ambient else w.config),
            data.get("claude_dir"))
    w.check("dry", "the lock is free and no worker holds it", lock_is_free(w.home) and workers(w.home) == [])
    # A lock held by another process is seen as held, and its holder is found by the file.
    os.makedirs(w.home, exist_ok=True)
    fd = os.open(os.path.join(w.home, "insights.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        holder = subprocess.Popen(["sleep", "30"], pass_fds=(fd,), start_new_session=True)
        try:
            time.sleep(0.5)
            found = workers(w.home)
            w.check("dry", "a process holding the lock file is found by it", holder.pid in (found or []), found)
            w.check("dry", "stop_workers stops it", holder.pid in stop_workers(w.home) and holder.wait(timeout=10) is not None)
        finally:
            if holder.poll() is None:
                holder.kill()
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    w.check("dry", "the lock is free again", lock_is_free(w.home))
    usage = snapshot(REAL_USAGE)
    w.check("dry", "the real usage-data snapshot is stable", snapshot(REAL_USAGE) == usage,
            "%d entries" % len(usage))
    config = REAL_CLAUDE if ambient else w.config
    print("      the child would leave its transcripts under %s" % transcripts(config, w.home)[0])
    real_after(w, before, [])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="haiku", help="the sessions' model (the judge is COMPOUND_MODEL)")
    ap.add_argument("--keep", action="store_true",
                    help="keep the throwaway root when everything passes (fresh only: under ambient it is always removed)")
    ap.add_argument("--deadline", type=int, default=1100,
                    help="seconds to wait for the run to leave `running` (the CLI kills it at 900)")
    ap.add_argument("--dry", action="store_true", help="only what needs no model call; starts no claude")
    ap.add_argument("--leg", choices=("all", "timeout"), default="all",
                    help="timeout: only the leg that kills a real run at COMPOUND_INSIGHTS_TIMEOUT")
    ap.add_argument("--timeout", type=int, default=8, help="the timeout leg's COMPOUND_INSIGHTS_TIMEOUT, in seconds")
    args = common.parse(ap)
    ambient = common.CONFIG == "ambient"
    if args.dry:
        # No claude runs, so no credential is needed: the world is made as an ambient one,
        # and the fresh configuration, when asked for, is its `config` directory.
        w = common.World("insights-dry", config="ambient")
        project = w.project("alpha", build=True)
        here = dict(COMPOUND_CLAUDE_DIR=None) if ambient else dict(COMPOUND_CLAUDE_DIR=w.config)
        try:
            dry(w, project, here, ambient)
        finally:
            stop_workers(w.home)
            if ambient:
                shutil.rmtree(w.root, ignore_errors=True)
        w.finish(True if ambient else args.keep)
    if os.environ.get("COMPOUND_JOURNEY_PLUGIN"):
        raise SystemExit("journey_insights.py loads this working copy only: unset COMPOUND_JOURNEY_PLUGIN")
    if args.leg == "timeout":
        w = common.World("insights-timeout")
        project = w.project("alpha")
        here = dict(COMPOUND_CLAUDE_DIR=None) if ambient else dict(COMPOUND_CLAUDE_DIR=w.config)
        try:
            timeout_leg(w, project, args, here, ambient)
        finally:
            left = stop_workers(w.home)
            if left:
                print("      cleanup: stopped %d processes still running for this world" % len(left))
            if ambient:
                shutil.rmtree(w.root, ignore_errors=True)
        w.finish(True if ambient else args.keep)
    w = common.World("insights")
    project = w.project("alpha", build=True)
    # ambient: no COMPOUND_CLAUDE_DIR, so the CLI reads ~/.claude, which `claude` writes to, and
    # the child gets no CLAUDE_CONFIG_DIR. fresh: the fresh configuration, named for both.
    here = dict(COMPOUND_CLAUDE_DIR=None) if ambient else dict(COMPOUND_CLAUDE_DIR=w.config)
    try:
        run(w, project, args, here, ambient)
    finally:
        left = stop_workers(w.home)
        if left:
            print("      cleanup: stopped %d processes still running for this world" % len(left))
        if ambient:
            print("      cleanup: removing the temporary root (it holds findings from real sessions)")
            shutil.rmtree(w.root, ignore_errors=True)
    w.finish(True if ambient else args.keep)


def group_left(pgid):
    """The pids still in process group `pgid`: [] when the group is gone. Asked of the kernel
    (kill 0) and of pgrep -g, so no process is found by its name."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return []
    except PermissionError:
        pass
    done = subprocess.run(["pgrep", "-g", str(pgid)], capture_output=True, text=True, timeout=30)
    found = [int(one) for one in done.stdout.split() if one.strip().isdigit()]
    return found or [pgid]


def timeout_leg(w, project, args, here, ambient):
    """One real `compound insights --run` killed at COMPOUND_INSIGHTS_TIMEOUT=args.timeout."""
    before = real_guard(w)
    config = REAL_CLAUDE if ambient else w.config
    usage = os.path.join(config, "usage-data")
    usage_before = snapshot(usage)
    env = w.env(project, COMPOUND_INSIGHTS_TIMEOUT=str(args.timeout), **here)
    if ambient:
        keys = [n for n in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN") if env.get(n)]
        w.check("timeout", "no API key or token in the environment: the child uses the Claude CLI's own login",
                keys == [], keys)
        if keys:
            print("      stopping before the run: unset %s" % ", ".join(keys))
            real_after(w, before, [])
            return
    # Typed by hand, as a user would: not as a call of this session's.
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    began = time.time()
    worker = subprocess.Popen([common.CLI, "insights", "--run"], cwd=project, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    groups, members = set(), set()
    try:
        # Every child of the worker leads a group of its own (the worker starts `claude` in a
        # new session); what each group holds is noted while the run lasts.
        while worker.poll() is None and time.time() - began < args.timeout + 60:
            for child in children(worker.pid):
                groups.add(child)
            for pgid in list(groups):
                members.update(group_left(pgid))
            time.sleep(0.2)
        out, err = worker.communicate(timeout=60)
    finally:
        if worker.poll() is None:
            worker.kill()
    took = time.time() - began
    print("      the run took %.1f s; the child's process groups seen: %d, holding %d processes in all" % (
        took, len(groups), len(members)))
    w.check("timeout", "compound insights --run exited 1", worker.returncode == 1, (worker.returncode, err[-300:]))
    w.check("timeout", "it ran a real claude for the whole timeout and stopped soon after (%d s, then up to 5 s "
            "and the SIGKILL)" % args.timeout, args.timeout <= took <= args.timeout + 20, "%.1f s" % took)
    state = read_state(w.home)
    w.show("state", [shown_state(state, ambient)])
    w.check("timeout", "the outcome is timeout", state.get("outcome") == "timeout", state.get("outcome"))
    w.check("timeout", "its message says the timeout", "within %d seconds" % args.timeout in str(state.get("message")))
    errors = [e for e in w.events(project, kind="error")]
    w.check("timeout", "one error event, where insights.run, of the session insights",
            [(e.get("where"), e.get("session")) for e in errors] == [("insights.run", "insights")],
            [(e.get("where"), e.get("session")) for e in errors])
    w.check("timeout", "a child process group was seen while the run lasted", bool(groups), len(groups))
    alive = {pgid: group_left(pgid) for pgid in groups}
    w.check("timeout", "no process of the child's process group is left (by group, not by name)",
            all(found == [] for found in alive.values()), {k: len(v) for k, v in alive.items()})
    w.check("timeout", "no worker of this world is left: nothing holds the lock file", workers(w.home) == [],
            workers(w.home))
    w.check("timeout", "the lock is free", lock_is_free(w.home))
    w.check("timeout", "nothing was harvested: no insight event, no harvested counts",
            w.events(project, kind="insight") == [] and not state.get("harvested"),
            (len(w.events(project, kind="insight")), state.get("harvested")))
    answer = w.cli(project, "insights", "--start", "--json", COMPOUND_INSIGHTS_DAYS=None,
                   COMPOUND_INSIGHTS_MIN_SESSIONS=None, COMPOUND_INSIGHTS_TIMEOUT=None, **here)
    w.check("timeout", "the next insights --start under the default days answers too soon",
            answer.returncode == 0 and json.loads(answer.stdout or "{}").get("why") == "too soon", answer.stdout)
    w.check("timeout", "that answer started nothing: the state still says timeout",
            read_state(w.home).get("outcome") == "timeout" and lock_is_free(w.home))
    usage_after = snapshot(usage)
    added = [p for p in usage_after if p not in usage_before]
    changed = [p for p in usage_after if p in usage_before and usage_before[p] != usage_after[p]]
    print("      what the killed run left under %s: %d entries added, %d changed, %d removed (Claude Code's own "
          "caches; left in place)" % ("the real ~/.claude/usage-data" if ambient else "the fresh usage-data",
                                       len(added), len(changed), len([p for p in usage_before if p not in usage_after])))
    folder, child = transcripts(config, w.home)
    print("      the child's transcripts: %d under %s (left in place)" % (len(child), folder))
    real_after(w, before, [name[:-len(".jsonl")] for name in child])


def run(w, project, args, here, ambient):
    private = ambient
    config = REAL_CLAUDE if ambient else w.config
    usage = os.path.join(config, "usage-data")
    before = real_guard(w)
    real_usage_before = snapshot(REAL_USAGE)
    sids = []

    # ---- load and seed, and f ----
    first = w.session(project, [common.BUILD_TASK, BUILD_AGAIN, BUILD_LAST], args.model, tools=("Bash", "Skill"),
                      **here, **SEED)
    sids.append(first.sid)
    paths = loaded(first.stream)
    w.check("load", "the first session lists exactly one compound plugin, this working copy",
            paths is not None and [os.path.realpath(p or "") for p in paths] == [os.path.realpath(common.PLUGIN)],
            "%s (want %s)" % (paths, common.PLUGIN))
    w.check("load", "an event of that session is in the temporary log",
            any(e.get("session") == first.sid for e in w.events(project)))
    w.check("load", "no line the real event log gained names it", real_log_naming(before["size"], [first.sid]) == [])
    if not all(w.results):
        print("      BLOCKED before anything paid: the working copy's mod and the temporary store are not proven")
        return
    second = w.session(project, [NOTE, NOTE_AGAIN, NOTE_LAST], args.model, **here, **SEED)
    third = w.session(project, [common.BUILD_TASK, BUILD_AGAIN], args.model, tools=("Bash", "Skill"), **here, **SEED)
    sids += [second.sid, third.sid]
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
            "%d seeded sessions logged" % len(logged))
    if not all(w.results):
        print("      stopping before the paid leg: a check above failed")
        real_after(w, before, sids)
        return

    # ---- a: the run started by a real session's first typed prompt ----
    reports_before = reports(usage)
    # fresh: the mod comes through CLAUDE_CODE_PLUGIN_DIRS with the user settings of the fresh
    # configuration, so the child loads it too. ambient: --plugin-dir, as for every session
    # here; the child reads the user's own settings and loads what they name.
    if ambient:
        starting = dict(QUIET, COMPOUND_INSIGHTS_MIN_SESSIONS="1")
        flags = {}
    else:
        starting = dict(QUIET, COMPOUND_INSIGHTS_MIN_SESSIONS="1", CLAUDE_CODE_PLUGIN_DIRS=common.PLUGIN)
        flags = {"installed": True}
    began = time.time()
    starter = w.session(project, READY, args.model, tools=("Skill",), **flags, **here, **starting)
    sids.append(starter.sid)
    ended = time.time()
    after_start = read_state(w.home)
    held = not lock_is_free(w.home)
    w.show("state", [shown_state(after_start, private)])
    w.check("a", "the starting session answered", "READY" in starter.result, starter.result[:200])
    started = isinstance(after_start.get("started"), (int, float)) and after_start["started"] >= int(began) - 1
    w.check("a", "after its first prompt the state says a run started", started)
    if not started:
        # Nothing to wait for: say what was seen, and stop (the caller's `finally` cleans up).
        with open(starter.stream) as fh:
            stream = fh.read()
        print("      NO RUN STARTED after the starting session's first prompt; not polling.")
        print("      state file: %s" % (json.dumps(shown_state(after_start, private)) if after_start
                                        else "absent or unreadable"))
        print("      the mod's context in the session's stream: %s; its claims for the session: %d" % (
            "present ([compound] seen)" if "[compound]" in stream else "absent (no [compound] in the stream)",
            len(w.claims(starter.sid))))
        print("      the session's events: %s" % sorted({e.get("type") for e in w.events(project, session=starter.sid)}))
        real_after(w, before, sids)
        return
    w.check("a", "the worker outlived the session: the lock is held after the session exited, or the run "
            "finished after it", held or finished_after(after_start, ended),
            "lock held: %s; workers %s" % (held, workers(w.home)))

    # ---- b: a second session during the run ----
    during = w.session(project, READY, args.model, tools=("Skill",), **flags, **here, **starting)
    sids.append(during.sid)
    w.check("b", "a second session's first prompt during the run did not start another: started unchanged",
            read_state(w.home).get("started") == after_start.get("started"))
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
    w.show("state", [shown_state(last, private)])
    w.check("a", "the state went from running to ok", seen[:1] == ["running"] and last.get("outcome") == "ok",
            " -> ".join(str(s) for s in seen))
    w.check("a", "the lock is free and no worker is left", lock_is_free(w.home) and workers(w.home) == [],
            workers(w.home))
    new_reports = [name for name in reports(usage) if name not in reports_before]
    w.check("b", "exactly one /insights ran: one new report-*.html", len(new_reports) == 1,
            "%d new" % len(new_reports))
    print("      the second session's own events: %s" % sorted(
        {e.get("type") for e in w.events(project, session=during.sid)}))

    # ---- c ----
    report = os.path.join(usage, "report.html")
    w.check("c", "a report.html newer than the start is in the usage-data the child wrote (%s)" % (
        "the real ~/.claude" if ambient else "the fresh configuration"),
            (mtime(report) or 0) >= int(after_start.get("started") or began))
    if ambient:
        w.check("c", "nothing was written to the temporary root's configuration directories",
                os.listdir(w.config) == [] and not os.path.exists(os.path.join(w.claude, "usage-data"))
                and not os.path.exists(os.path.join(w.home, "usage-data")))
    else:
        w.check("c", "none under the world's default Claude directory or under COMPOUND_HOME",
                not os.path.exists(os.path.join(w.claude, "usage-data"))
                and not os.path.exists(os.path.join(w.home, "usage-data")))
        real_usage_after = snapshot(REAL_USAGE)
        changed = [p for p in set(real_usage_before) | set(real_usage_after)
                   if real_usage_before.get(p) != real_usage_after.get(p)]
        w.check("c", "every entry under the real usage-data kept its mtime (%d entries)" % len(real_usage_before),
                changed == [], "%d changed" % len(changed))

    # ---- d ----
    sessions = {e.get("session") for e in w.events(project)}
    ours = seeded | {starter.sid, during.sid, "insights"}
    w.check("d", "the temporary log holds no event of the child session (it ran with COMPOUND_OFF=1)",
            sessions <= ours, "%d other sessions" % len(sessions - ours))
    folder, child = transcripts(config, w.home)
    child_sids = [name[:-len(".jsonl")] for name in child]
    print("      the child's transcripts: %d under %s (Claude Code's own; left in place)" % (len(child), folder))
    w.check("d", "the child's session wrote nothing to the temporary log",
            not (set(child_sids) & sessions), "%d" % len(set(child_sids) & sessions))
    sids += child_sids

    # ---- e ----
    now = json.loads(w.cli(project, "insights", "--json", **here).stdout or "{}")
    findings = now.get("findings") or []
    print("      harvested: %s" % json.dumps((now.get("harvested") or {})))
    print("      findings by source and state: %s" % json.dumps(
        collections.Counter("%s/%s" % (f.get("source"), f.get("state")) for f in findings)))
    insight_events = [e for e in w.events(project, kind="insight")]
    print("      kinds named by the facet findings: %s" % json.dumps(
        collections.Counter(k for e in insight_events for k in (e.get("kinds") or []))))
    listed = [f for f in findings if f.get("state") == "open"
              and (f.get("source") == "report" or (f.get("source") == "facet" and f.get("project") == project))]
    print("      open findings listed for the scratch project: %d (%d about its sessions)" % (
        len(listed), sum(1 for f in listed if f.get("source") == "facet")))
    if listed:
        later = w.session(project, READY, args.model, tools=("Skill",), **here, **QUIET)
        sids.append(later.sid)
        rows = w.events(project, session=later.sid, kind="remind")
        named = [i for e in rows for i in (e.get("insights") or [])]
        # What a hook adds to a typed prompt is not in the -p stream; Claude Code keeps it in
        # the session's transcript, <config>/projects/<slug of the project>/<session id>.jsonl.
        transcript = os.path.join(config, "projects", slug(project), later.sid + ".jsonl")
        try:
            with open(transcript, encoding="utf-8", errors="replace") as fh:
                added = fh.read()
        except OSError:
            added = ""
        with open(later.stream) as fh:
            added += fh.read()
        ids = [f["id"] for f in listed]
        shown = [i for i in ids if ("RECORDED-INSIGHT id=%s" % i) in added]
        w.check("e", "a later session's first prompt holds a RECORDED-INSIGHT block with an in- id of a listed finding "
                "(read from its transcript)", bool(shown) and all(i.startswith("in-") for i in shown),
                "%d shown; transcript %s" % (len(shown), "found" if os.path.exists(transcript) else "missing"))
        w.check("e", "its remind event names that id", bool(set(named) & set(shown)),
                "%d remind events, %d ids named" % (len(rows), len(named)))
        w.check("e", "its remind carries headless: true (a -p session: the showing is not counted)",
                bool(rows) and all(e.get("headless") is True for e in rows), [e.get("headless") for e in rows])
        w.check("e", "the later session answered", "READY" in later.result, later.result[:200])
    else:
        print("UNPROVEN e        no finding is listed for the scratch project: the reminder leg was not exercised "
              "(not a pass)")

    # ---- g ----
    print("      g: the run took %.0f s of wall time from the starting prompt to a free lock" % took)
    spent = [s for s in (first, second, third, starter, during)]
    print("      g: cost: the child's output is discarded, so no output reports what /insights cost; the journey's "
          "sessions reported %.4f USD in all (starting session %s, second %s)" % (
              sum(sum(costs(s.stream)) for s in spent), costs(starter.stream), costs(during.stream)))
    print("      the journey's own session transcripts are Claude Code's, under %s (left in place)" % os.path.join(
        config, "projects", slug(project)))
    real_after(w, before, sids)


if __name__ == "__main__":
    main()
