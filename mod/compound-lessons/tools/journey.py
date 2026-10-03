#!/usr/bin/env python3
"""The outcome journey for compound-lessons. Real `claude -p` sessions; run by hand, never in CI.

Every step passes or fails on what happened, read from the session's own stream-json
(which tool calls ran and which errored) and from the files on disk. Nothing passes on
the mod having merely fired.

  control   a fresh session with no mod and no note runs the task: it FAILS first.
            Without this the later "did not fail" proves nothing.
  A         a session with the mod fails, then fixes it. Afterwards a project note
            exists that the agent never ran a command to write.
  B         a fresh session in the same project runs the same task: no failed call.
  C         a second project carrying the same script fails once: the lesson recorded
            in the first project comes back beside the error and moves to the global notes.
  S         the failure and the fix both happen inside a SUBAGENT, in a state of its own:
            the note is written all the same.

usage: journey.py [--model haiku] [--keep]

Everything is written under a throwaway root: state (SKILL_COMPOUNDER_STATE), the global
notes directory (SKILLNOTE_CLAUDE_DIR) and both projects. Sessions run with
--setting-sources project, so the hooks in the user's own settings.json stay out of it.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(MOD))
TASK = "Build this project by running its build script, ./build.sh, and tell me the one line it prints on success."
SUBAGENT_TASK = ("Use the Agent tool to dispatch one general-purpose subagent. Its task: build this project by running "
                 "./build.sh and report the one line it prints on success. Do not run the build yourself.")
BUILD_SH = """#!/bin/sh
# The build needs a profile; there is no default.
if [ "$1" != "--profile" ] || [ -z "$2" ]; then
  echo "build.sh: error: a profile is required, e.g. ./build.sh --profile dev" >&2
  exit 2
fi
echo "build ok ($2)"
"""


def make_project(path):
    os.makedirs(path)
    script = os.path.join(path, "build.sh")
    with open(script, "w") as fh:
        fh.write(BUILD_SH)
    os.chmod(script, 0o755)


def session(cwd, env, model, with_mod, save, task=TASK, tools=("Bash",)):
    """Run one headless session; return its Bash calls as [(command, errored, result text)].

    The raw stream is kept at SAVE, so a failed check can be read back rather than re-run.
    """
    argv = ["claude", "-p", "--model", model, "--setting-sources", "project",
            "--output-format", "stream-json", "--verbose", "--allowedTools", *tools]
    if with_mod:
        argv += ["--plugin-dir", MOD]
    done = subprocess.run(argv, input=task, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    with open(save, "w") as fh:
        fh.write(done.stdout)
        fh.write("\n--- stderr ---\n" + done.stderr)
    calls, order = {}, []
    for line in done.stdout.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        content = (msg.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                calls[block["id"]] = [block["input"].get("command", ""), None, ""]
                order.append(block["id"])
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                text = block.get("content")
                if isinstance(text, list):
                    text = " ".join(b.get("text", "") for b in text if isinstance(b, dict))
                calls[block["tool_use_id"]][1] = bool(block.get("is_error"))
                calls[block["tool_use_id"]][2] = text or ""
    if done.returncode != 0 and not order:
        raise SystemExit("session failed to run: rc=%d\n%s" % (done.returncode, done.stderr[-2000:]))
    return [tuple(calls[i]) for i in order], done.stdout


def builds(calls):
    return [c for c in calls if "build.sh" in c[0]]


def events(state):
    path = os.path.join(state, "mod", "events.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def notes(env, scope, project):
    done = subprocess.run([os.path.join(REPO, "bin", "skillnote"), "list", "--scope", scope,
                           "--project", project, "--json"],
                          cwd=project, env=env, capture_output=True, text=True, timeout=60)
    return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    root = tempfile.mkdtemp(prefix="compound-journey-")
    state, gdir = os.path.join(root, "state"), os.path.join(root, "claude")
    os.makedirs(state)
    os.makedirs(gdir)
    control, proj_a, proj_b = (os.path.join(root, n) for n in ("control", "alpha", "beta"))
    for p in (control, proj_a, proj_b):
        make_project(p)
    env = dict(os.environ, SKILL_COMPOUNDER_STATE=state, SKILLNOTE_CLAUDE_DIR=gdir,
               COMPOUND_SKILLNOTE=os.path.join(REPO, "bin", "skillnote"))

    results = []

    def check(step, what, ok, detail=""):
        results.append(ok)
        print("%s  %-8s %s%s" % ("PASS" if ok else "FAIL", step, what, ("  [" + detail + "]") if detail else ""))

    # control: the trap is real
    calls, _ = session(control, env, args.model, False, os.path.join(root, "control.stream"))
    b = builds(calls)
    check("control", "an uninformed session fails the build first", bool(b) and b[0][1] is True, b[0][0] if b else "no build call")

    # A: fail, fix, and the note exists without the agent writing it
    calls, _ = session(proj_a, env, args.model, True, os.path.join(root, "A.stream"))
    b = builds(calls)
    check("A", "the session failed and then fixed the build",
          len(b) >= 2 and b[0][1] is True and any(c[1] is False for c in b[1:]))
    check("A", "the agent ran no skillnote command itself", not any("skillnote" in c[0] for c in calls))
    project_notes = notes(env, "project", proj_a)
    lesson_rows = [e for e in events(state) if e["ev"] == "lesson"]
    check("A", "one project note was written by the mod",
          len(project_notes) == 1 and len(lesson_rows) == 1,
          project_notes[0]["text"][:160] if project_notes else "no note")
    check("A", "the note names the working form", bool(project_notes) and "--profile" in project_notes[0]["text"])
    note_id = project_notes[0]["id"] if project_notes else None

    # B: a fresh session does not repeat it
    calls, _ = session(proj_a, env, args.model, True, os.path.join(root, "B.stream"))
    b = builds(calls)
    check("B", "a fresh session in the project runs the build without a failed call",
          bool(b) and not any(c[1] for c in b), " | ".join(c[0] for c in calls) or "no Bash call")
    check("B", "no second note was written", len(notes(env, "project", proj_a)) == 1)

    # C: the same mistake in a second project
    before = len(events(state))
    calls, _ = session(proj_b, env, args.model, True, os.path.join(root, "C.stream"))
    b = builds(calls)
    new = events(state)[before:]
    check("C", "the second project failed once", bool(b) and b[0][1] is True, " | ".join(c[0] for c in calls) or "no Bash call")
    check("C", "the recorded lesson came back with the failure", any(e["ev"] == "recur" and e["id"] == note_id for e in new))
    global_notes = notes(env, "global", proj_b)
    check("C", "the lesson moved to the global notes", any(n["id"] == note_id for n in global_notes))
    check("C", "it was moved, not copied",
          not any(n["id"] == note_id and not n["text"].startswith("moved to global") for n in notes(env, "project", proj_a)))
    check("C", "no duplicate note was written in the second project", notes(env, "project", proj_b) == [])
    check("C", "the build then succeeded", any(c[1] is False for c in b[1:]))

    # S: the same journey's first half, inside a subagent, with nothing recorded beforehand
    state_s, gdir_s, proj_s = (os.path.join(root, n) for n in ("state-s", "claude-s", "gamma"))
    os.makedirs(state_s)
    os.makedirs(gdir_s)
    make_project(proj_s)
    env_s = dict(env, SKILL_COMPOUNDER_STATE=state_s, SKILLNOTE_CLAUDE_DIR=gdir_s)
    calls, _ = session(proj_s, env_s, args.model, True, os.path.join(root, "S.stream"), task=SUBAGENT_TASK, tools=("Bash", "Agent"))
    fails = [e for e in events(state_s) if e["ev"] == "fail"]
    check("S", "the build failed inside a subagent", bool(fails) and all(e["agent"] for e in fails))
    sub_notes = notes(env_s, "project", proj_s)
    check("S", "one project note was written by the mod", len(sub_notes) == 1 and "--profile" in sub_notes[0]["text"],
          sub_notes[0]["text"][:160] if sub_notes else "no note")

    print("\n%d of %d checks passed; root %s" % (sum(results), len(results), root))
    if not args.keep and all(results):
        shutil.rmtree(root)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
