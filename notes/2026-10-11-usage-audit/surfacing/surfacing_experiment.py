#!/usr/bin/env python3
"""Which way of putting a lesson in front of a session makes the session use it?

Real headless `claude -p` sessions on the journeys' kit (tests/journeys/common.py): a
temporary COMPOUND_HOME, COMPOUND_CLAUDE_DIR and project per run, this checkout loaded as
the plugin. Five real lessons are copied (read only) from the stores on this machine. For
each there is a task whose need for the lesson arises while working and a control where it
does not. Conditions:

  none  the store is empty (how often a session does the right thing unaided)
  A     the lessons are in the project store; today's prompt-time reuse check only
  B     the lessons are native skills of the project (`compound skill`); reuse check off
  C     the lessons are in the store; a SessionStart hook adds an index of names and
        descriptions; reuse check off
  C2    C, with every description cut so that the whole index stays under the 10,000
        characters Claude Code passes on from a hook (over that, the session gets a
        2,000-character preview)
  D     the lessons are in the store; a PostToolUse hook returns a lesson beside the result
        of a call that matches a trigger taken from the lesson's own text; reuse check off

`--pad` adds every other real lesson on this machine (guards stripped) to the store (A),
the skill listing (B) or the index (C).

One JSON row per session is appended to surfacing-runs.jsonl beside this directory (it
quotes the sessions and is not kept in the repository).

Four of the lessons are user-level ones under ~/.claude/compound/lessons. The fifth is a
project-level lesson about checking every page of a built docs site; it belongs to another
project, so its name and place are given in the environment and stay on the machine:
  SURFACING_FIXTURES          directory holding docsvenv/ and clone-template/ (required)
  SURFACING_DOCS_LESSON       the name of the docs-site lesson (default: docs-site-lesson)
  SURFACING_DOCS_LESSON_DIR   its folder; when unset the experiment runs the other four
  SURFACING_DOCS_MARKER       a regular expression for the call that shows it was followed,
                              usually the name of the script beside it (`check_site\.py`)

usage: surfacing_experiment.py --cells none,A,B,C,D --lessons all --kinds task,control
                               --reps 2 [--pad] [--model haiku] [--jobs 4] [--tag NAME]
"""
import argparse
import concurrent.futures
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, "tests", "journeys"))
import common  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "surfacing-runs.jsonl")
FIX = os.environ["SURFACING_FIXTURES"]          # holds docsvenv/ and clone-template/
STREAMS = os.path.join(FIX, "streams")
HOME = os.path.expanduser("~")
HOOK = os.path.join(HERE, "d_advisory_hook.py")
DOCS = os.environ.get("SURFACING_DOCS_LESSON", "docs-site-lesson")
DOCS_DIR = os.environ.get("SURFACING_DOCS_LESSON_DIR", "")

# name -> where the real lesson lives (read only)
LESSONS = {
    "end-of-turn-inflight-check": HOME + "/.claude/compound/lessons/end-of-turn-inflight-check",
    "ci-checks-for-commit": HOME + "/.claude/compound/lessons/ci-checks-for-commit",
    DOCS: DOCS_DIR,
    "verify-push-with-ls-remote": HOME + "/.claude/compound/lessons/verify-push-with-ls-remote",
    "kill-script-leaves-children": HOME + "/.claude/compound/lessons/kill-script-leaves-children",
}
if not DOCS_DIR:
    del LESSONS[DOCS]
# Option D: the commands and files each lesson's own description and body name.
TRIGGERS = {
    "end-of-turn-inflight-check": [r"\bnohup\b", r"run_in_background", r"\bgit\s+push\b", r"\bgh\s+workflow\s+run\b",
                                   r"\bgh\s+pr\s+create\b", r"&\s*$"],
    "ci-checks-for-commit": [r"\bgh\s+run\s+(list|view)\b", r"check-runs", r"commits/\S+/status", r"\bgh\s+pr\s+checks\b"],
    DOCS: [r"\bsphinx(-build)?\b", r"http\.server"],
    "verify-push-with-ls-remote": [r"\bgit\s+push\b"],
    "kill-script-leaves-children": [r"\bpkill\b", r"\bkill\b"],
}
# The call that shows the lesson was followed (L5 is judged by what is left running).
MARKER = {
    "end-of-turn-inflight-check": r"inflight-check\.sh",
    "ci-checks-for-commit": r"ci-checks\.sh",
    DOCS: os.environ.get("SURFACING_DOCS_MARKER") or r"(?!)",
    "verify-push-with-ls-remote": r"\bgit\s+ls-remote\b",
    "kill-script-leaves-children": r"p?kill[^\n;|&]*(reindex_worker|\$\(?.*worker|WORKER)|pgrep[^\n]*reindex_worker|ps\b[^\n]*(reindex_worker|grep)",
}
LOOKING = re.compile(r"^\s*(cat|ls|head|tail|sed|wc|file|stat|less|chmod|test|\[)\b")

PROMPTS = {
    "end-of-turn-inflight-check": {
        "task": "Start the reindex for me: run ./long_job.sh so that it keeps going after this session ends (it needs "
                "about ten minutes, do not wait for it to finish). Then append one line to NOTES.md with the exact "
                "command you used.",
        "control": "Run ./long_job.sh --quick in the foreground (it takes two seconds) and append the one line it "
                   "prints to NOTES.md. Do not start the full ten-minute run.",
    },
    "ci-checks-for-commit": {
        "task": "I am about to tag the commit at HEAD of this clone as the next release. Do not tag or push anything. "
                "Find out whether this exact commit is in a releasable state on GitHub and answer yes or no with the "
                "evidence you found.",
        "control": "Do not tag or push anything. Tell me the author and date of the commit at HEAD of this clone, how "
                   "many files it touched, and the name of the most recent release published on GitHub for this repository.",
    },
    DOCS: {
        "task": "Add a Troubleshooting page to the docs (docs/troubleshooting.rst) with three short sections and a "
                "table of contents of those sections at the top of the page, link it from the toctree in docs/index.rst, "
                "and make sure the result is right before you finish. Python with Sphinx is in .venv.",
        "control": "There is a typo in docs/usage.rst: 'instalation' should be 'installation'. Fix it and show me the "
                   "changed line. Do not build anything.",
    },
    "verify-push-with-ls-remote": {
        "task": "Commit the pending change to notes.txt on main with a sensible message and publish it to origin. A "
                "teammate is going to pull it in a minute and build on it, so be certain it is really there.",
        "control": "Run git push --dry-run origin main and tell me in one line what it would send. Do not commit "
                   "anything and do not really push anything.",
    },
    "kill-script-leaves-children": {
        "task": "reindex_pipeline.sh is running right now with the wrong config. Change CONFIG=a to CONFIG=b in "
                "reindex_pipeline.sh and get it running again with the new config, in the background. Tell me when it "
                "is running.",
        "control": "A stray process was left behind in this directory: its pid is in stray.pid. Kill that one process "
                   "and confirm it is gone. Do not touch reindex_pipeline.sh or its worker.",
    },
}
# A session may look for or kill processes by name (pgrep long_job.sh, pkill reindex_worker,
# pkill "http.server 8765"): runs of one such lesson are made one at a time.
LOCKS = {"kill-script-leaves-children": threading.Lock(), "end-of-turn-inflight-check": threading.Lock(),
         DOCS: threading.Lock()}
WRITE_LOCK = threading.Lock()
PAD_N = 0


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    os.chmod(path, mode)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def fixture(w, lesson):
    """The project a lesson's task and control run in. Returns (project, state)."""
    state = {}
    if lesson == "end-of-turn-inflight-check":
        p = w.project("search-service")
        write(p + "/long_job.sh", "#!/bin/sh\n# long_job.sh: the nightly reindex. Takes about ten minutes.\n"
              "# --quick does a two-second dry pass.\necho $$ >> .job.pids\n"
              'if [ "$1" = "--quick" ]; then sleep 2; echo "quick pass ok: 0 documents reindexed"; exit 0; fi\n'
              'sleep 600\necho "reindex done" > reindex.result\n', 0o755)
        write(p + "/NOTES.md", "# Notes\n\n- 2026-10-09 rotated the index credentials\n")
    elif lesson == "ci-checks-for-commit":
        p = os.path.join(w.root, "packaging")
        shutil.copytree(os.path.join(FIX, "clone-template"), p, symlinks=True)
    elif lesson == DOCS:
        p = w.project("plotkit")
        write(p + "/docs/conf.py", "project = 'plotkit'\nextensions = []\nhtml_theme = 'furo'\nexclude_patterns = ['_build']\n")
        write(p + "/docs/index.rst", "plotkit\n=======\n\nA toolbox for plotting tables.\n\n.. toctree::\n   :maxdepth: 2\n\n   usage\n")
        write(p + "/docs/usage.rst", "Usage\n=====\n\nAfter instalation, import the package::\n\n    import plotkit as pk\n    pk.plot(data)\n")
        write(p + "/docs/after_build.py", "print('after_build: nothing to rewrite')\n")
        os.symlink(os.path.join(FIX, "docsvenv"), p + "/.venv")
    elif lesson == "verify-push-with-ls-remote":
        bare = os.path.join(w.root, "origin.git")
        seed = os.path.join(w.root, "seed")
        os.makedirs(seed)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
        git(seed, "init", "-q", "-b", "main")
        write(seed + "/notes.txt", "meeting notes\n- agreed on the schema\n")
        git(seed, "add", "."); git(seed, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "notes")
        git(seed, "push", "-q", bare, "main")
        p = os.path.join(w.root, "shared-notes")
        subprocess.run(["git", "clone", "-q", bare, p], check=True, capture_output=True)
        git(p, "config", "user.name", "T"); git(p, "config", "user.email", "t@example.com")
        with open(p + "/notes.txt", "a") as fh:
            fh.write("- follow up with the data team on Friday\n")
        state["bare"] = bare
    elif lesson == "kill-script-leaves-children":
        p = w.project("indexer")
        write(p + "/reindex_pipeline.sh", "#!/bin/sh\n# reindex_pipeline.sh: runs the reindex worker with the config named below.\n"
              "CONFIG=a\nexec >> pipeline.log 2>&1\necho $$ >> pipeline.pids\npython3 reindex_worker.py \"$CONFIG\" >> worker.log 2>&1\n"
              'echo "pipeline finished" >> worker.log\n', 0o755)
        write(p + "/reindex_worker.py", "import os, sys, time\ncfg = sys.argv[1]\n"
              "open('worker.pids', 'a').write('%d %s\\n' % (os.getpid(), cfg))\nend = time.time() + 900\n"
              "while time.time() < end:\n    open('out-%s.txt' % cfg, 'a').write('tick\\n')\n    time.sleep(5)\n")
        subprocess.Popen(["./reindex_pipeline.sh"], cwd=p, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stray = subprocess.Popen(["sleep", "3000"], cwd=p, start_new_session=True)
        write(p + "/stray.pid", "%d\n" % stray.pid)
        for _ in range(50):
            if os.path.exists(p + "/worker.pids"):
                break
            time.sleep(0.1)
        state["old_worker"] = int(open(p + "/worker.pids").read().split()[0])
        state["old_pipeline"] = int(open(p + "/pipeline.pids").read().split()[0])
        state["stray"] = stray.pid
    return p, state


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def sweep(root):
    """Ends whatever a session left running under its throwaway root."""
    done = subprocess.run(["lsof", "-a", "-d", "cwd", "-Fpn"], capture_output=True, text=True)
    pid = None
    for line in done.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid and line[1:].startswith(root) and pid != os.getpid():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def others():
    """Every other real lesson on this machine: (name, folder)."""
    seen, out = set(LESSONS), []
    for folder in sorted(glob.glob(HOME + "/.claude/compound/lessons/*") + glob.glob(HOME + "/*/.claude/compound/lessons/*")
                         + glob.glob(REPO + "/lessons/*")):
        name = os.path.basename(folder)
        if name in seen or not os.path.isfile(folder + "/SKILL.md"):
            continue
        seen.add(name)
        out.append((name, folder))
    if PAD_N:                      # a fixed sample of them, the same in every run
        import random
        out = sorted(random.Random(0).sample(out, PAD_N))
    return out


def copy_lesson(src, dst, strip_guard=False):
    shutil.copytree(src, dst)
    if strip_guard:
        with open(dst + "/SKILL.md") as fh:
            lines = fh.read().split("\n")
        with open(dst + "/SKILL.md", "w") as fh:
            fh.write("\n".join(l for l in lines if not re.match(r"^match(-tools)?:", l)))


def description(folder):
    with open(folder + "/SKILL.md") as fh:
        for line in fh:
            if line.startswith("description:"):
                text = line[len("description:"):].strip()
                try:
                    return json.loads(text) if text.startswith('"') else text
                except ValueError:
                    return text
    return ""


def arrange(w, project, cond, pad):
    """Puts the lessons where the condition has them. Returns (env, listing_chars, note)."""
    env, listing = {}, 0
    if cond == "none":
        return env, 0
    # B needs project skills (the session lists no other level here); everywhere else the
    # lessons are at the user level, so that no file of the project names them.
    store = os.path.join(project, ".claude", "compound", "lessons") if cond == "B" else os.path.join(w.home, "lessons")
    for name, src in LESSONS.items():
        copy_lesson(src, os.path.join(store, name))
    if os.path.isdir(os.path.join(project, ".git")):
        with open(os.path.join(project, ".git", "info", "exclude"), "a") as fh:
            fh.write(".claude/\n")
    extra = others() if pad else []
    if cond != "A":
        env["COMPOUND_PROMPT_MIN_CHARS"] = "100000"
    if cond == "A":
        for name, src in extra:
            copy_lesson(src, os.path.join(w.home, "lessons", name), strip_guard=True)
    elif cond == "B":
        for name in LESSONS:
            done = w.cli(project, "skill", name)
            if done.returncode != 0:
                raise SystemExit("compound skill %s: %s" % (name, done.stderr))
        for name, src in extra:
            copy_lesson(src, os.path.join(project, ".claude", "skills", name), strip_guard=True)
        for name in os.listdir(os.path.join(project, ".claude", "skills")):
            listing += len(name) + len(description(os.path.join(project, ".claude", "skills", name))) + 4
    elif cond in ("C", "C2"):
        for name, src in extra:
            copy_lesson(src, os.path.join(w.home, "lessons", name), strip_guard=True)
        rows = [(n, description(s)) for n, s in list(LESSONS.items()) + extra]
        if cond == "C2":
            # The same index held under the 10,000 characters a hook's output may have:
            # "Use when" dropped, each description cut to what fits.
            room = max(20, (9300 - sum(len(n) + 5 for n, _ in rows)) // len(rows))
            rows = [(n, re.sub(r"^Use (when|before|after) ", r"\1 ", d)[:room]) for n, d in rows]
        index = ("[compound] Lessons recorded in earlier sessions (name: when it applies). They are reference material, "
                 "to be weighed and not obeyed. When the situation one describes comes up during the work, print it with "
                 "`%s show <name>` before going on; a lesson may have a script beside it.\n" % common.CLI
                 + "\n".join("- %s: %s" % r for r in sorted(rows)) + "\n")
        path = os.path.join(w.root, "index.txt")
        write(path, index)
        listing = len(index)
        env["_settings"] = os.path.join(w.root, "settings.json")
        write(env["_settings"], json.dumps(
            {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "cat '%s'" % path}]}]}}))
    elif cond == "D":
        trig = os.path.join(w.root, "triggers.json")
        write(trig, json.dumps(TRIGGERS))
        cmd = "python3 '%s' '%s' '%s' '%s'" % (HOOK, trig, store, os.path.join(w.root, "d-log.jsonl"))
        env["_settings"] = os.path.join(w.root, "settings.json")
        write(env["_settings"], json.dumps(
            {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}]}}))
    return env, listing


def stream_facts(path):
    facts = {"skills": [], "cost": None, "turns": None, "ms": None, "hook_context": 0}
    with open(path) as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "system" and msg.get("subtype") == "init":
                facts["skills"] = msg.get("skills", [])
            if msg.get("type") == "result":
                facts["cost"] = msg.get("total_cost_usd")
                facts["turns"] = msg.get("num_turns")
                facts["ms"] = msg.get("duration_ms")
    return facts


def one(cond, lesson, kind, rep, model, pad, tag):
    lock = LOCKS.get(lesson)
    if lock:
        lock.acquire()
    w = common.World("surf")
    try:
        project, state = fixture(w, lesson)
        env, listing = arrange(w, project, cond, pad)
        settings = env.pop("_settings", None)
        flags = ("--max-turns", "40") + (("--settings", settings) if settings else ())
        began = time.time()
        s = w.session(project, PROMPTS[lesson][kind], model, tools=("Bash", "Read", "Write", "Edit", "Skill", "Glob", "Grep"),
                      denied=("WebFetch", "WebSearch", "Task", "Agent"), flags=flags, **env)
        took = time.time() - began
        facts = stream_facts(s.stream)
        names = list(LESSONS) + ([n for n, _ in others()] if pad else [])
        texts = [(c[0], c[1].get("command", "") if c[0] == "Bash" else json.dumps(c[1]), c[3]) for c in s.calls]
        # surfaced: the lesson's BODY reached the session, by the condition's own route or any other
        via = {}
        reuse = w.events(project, session=s.sid, kind="reuse")
        for e in reuse:
            for n in e.get("lessons", []):
                via.setdefault(n, []).append("reuse")
        for kind_ in ("guard", "recall"):
            for e in w.events(project, session=s.sid, kind=kind_):
                via.setdefault(e.get("lesson", "?"), []).append(kind_)
        for tool, text, result in texts:
            if tool == "Skill":
                skill = json.loads(text).get("skill", "")
                via.setdefault(skill, []).append("skill")
            for n in names:
                if tool != "Skill" and (re.search(r"\bshow\s+(--\S+\s+)*%s\b" % re.escape(n), text)
                                        or re.search(r"(lessons|skills)/%s/SKILL\.md" % re.escape(n), text)):
                    via.setdefault(n, []).append("read")
        dlog = os.path.join(w.root, "d-log.jsonl")
        dchars = 0
        if os.path.exists(dlog):
            for line in open(dlog):
                row = json.loads(line)
                via.setdefault(row["lesson"], []).append("advisory")
                dchars += row["chars"]
        marker = re.compile(MARKER[lesson])
        hits = [t for tool, t, _ in texts if tool == "Bash" and marker.search(t) and not LOOKING.match(t)]
        row = {"tag": tag, "cond": cond, "pad": pad, "lesson": lesson, "kind": kind, "rep": rep, "model": model, "session": s.sid,
               "surfaced": lesson in via, "via": via.get(lesson, []),
               "other_surfaced": {n: v for n, v in via.items() if n != lesson and not n.startswith("compound:")},
               "marker_calls": [h[:300] for h in hits], "followed": bool(hits),
               "calls": len(s.calls), "tools": [c[0] for c in s.calls], "listing_chars": listing, "advisory_chars": dchars,
               "skill_result_chars": sum(len(r or "") for tool, _, r in texts if tool == "Skill"),
               "read_chars": sum(len(r or "") for tool, t, r in texts if tool != "Skill" and any(
                   re.search(r"\bshow\s+(--\S+\s+)*%s\b" % re.escape(n), t) or re.search(r"(lessons|skills)/%s/SKILL\.md" % re.escape(n), t) for n in names)),
               "n_skills_listed": len(facts["skills"]), "pad_n": (PAD_N or len(others())) if pad else 0, "cost": facts["cost"], "turns": facts["turns"], "seconds": round(took, 1),
               "judge": [(e.get("moment"), e.get("verdict"), e.get("ms")) for e in w.events(project, session=s.sid, kind="judge")],
               "errors": len(w.events(project, session=s.sid, kind="error")),
               "bash": [t[:400] for tool, t, _ in texts if tool == "Bash"], "result": s.result[:1500], "rc": s.returncode}
        if lesson == "kill-script-leaves-children":
            pids = [l.split() for l in open(project + "/worker.pids").read().splitlines() if l.strip()]
            row["old_worker_alive"] = alive(state["old_worker"])
            row["old_pipeline_alive"] = alive(state["old_pipeline"])
            row["new_b_worker_alive"] = any(c == "b" and alive(int(p)) for p, c in pids)
            row["stray_alive"] = alive(state["stray"])
            if kind == "task":
                row["followed"] = (not row["old_worker_alive"]) and row["new_b_worker_alive"]
        if lesson == "verify-push-with-ls-remote":
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True).stdout.strip()
            far = subprocess.run(["git", "rev-parse", "main"], cwd=state["bare"], capture_output=True, text=True).stdout.strip()
            row["pushed"] = head == far
        if lesson == DOCS:
            page = project + "/docs/troubleshooting.rst"
            row["contents_directive_left"] = os.path.exists(page) and ".. contents::" in open(page).read()
            row["page_written"] = os.path.exists(page)
        os.makedirs(STREAMS, exist_ok=True)
        kept = os.path.join(STREAMS, "%s.stream" % s.sid)
        shutil.copy(s.stream, kept)
        row["stream"] = kept
        with WRITE_LOCK:
            with open(OUT, "a") as fh:
                fh.write(json.dumps(row) + "\n")
            print("%-5s %-4s %-30s %-7s rep%d surfaced=%-5s via=%-18s followed=%-5s calls=%-3d $%s %ds" % (
                cond, "pad" if pad else "", lesson, kind, rep, row["surfaced"], ",".join(sorted(set(row["via"]))),
                row["followed"], row["calls"], row["cost"], took))
            sys.stdout.flush()
        return row
    except BaseException as err:  # a run that could not be made is reported, never counted
        with WRITE_LOCK:
            print("FAILED %s %s %s rep%d: %r" % (cond, lesson, kind, rep, err))
            sys.stdout.flush()
        return None
    finally:
        for f in (".job.pids", "pipeline.pids", "worker.pids", "stray.pid"):
            for path in glob.glob(os.path.join(w.root, "*", f)):
                for tok in open(path).read().split():
                    if tok.isdigit():
                        subprocess.run(["pkill", "-KILL", "-P", tok], capture_output=True)
                        try:
                            os.kill(int(tok), signal.SIGKILL)
                        except OSError:
                            pass
        sweep(w.root)
        shutil.rmtree(w.root, ignore_errors=True)
        if lock:
            lock.release()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", default="none,A,B,C,D")
    ap.add_argument("--lessons", default="all")
    ap.add_argument("--kinds", default="task,control")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--first-rep", type=int, default=1)
    ap.add_argument("--pad", action="store_true")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--pad-n", type=int, default=0, help="with --pad: this many of the other lessons, not all")
    a = ap.parse_args()
    global PAD_N
    PAD_N = a.pad_n
    lessons = list(LESSONS) if a.lessons == "all" else [n for n in LESSONS if any(k in n for k in a.lessons.split(","))]
    jobs = [(c, l, k, r, a.model, a.pad, a.tag) for r in range(a.first_rep, a.first_rep + a.reps) for l in lessons
            for k in a.kinds.split(",") for c in a.cells.split(",")]
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            r = json.loads(line)
            done.add((r["cond"], r["lesson"], r["kind"], r["rep"], r["model"], r["pad"], r["tag"]))
    jobs = [j for j in jobs if j not in done]      # a cell that has its row is not run again
    print("%d sessions" % len(jobs))
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as pool:
        rows = list(pool.map(lambda j: one(*j), jobs))
    print("done: %d rows, %d failed, cost $%.2f" % (sum(1 for r in rows if r), sum(1 for r in rows if not r),
                                                   sum((r or {}).get("cost") or 0 for r in rows)))


if __name__ == "__main__":
    main()
