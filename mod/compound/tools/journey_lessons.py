#!/usr/bin/env python3
"""The outcome journey for the lessons half of the compound mod. Real `claude -p` sessions; run by hand, never in CI.

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
  N         a check that legitimately FAILS, and is fixed by changing the work, writes NO note.
  X         a command carrying a secret: the secret is in no note, log or ledger afterwards.
  D         the shell has `cd`'d into a subdirectory of a repository: the note still lands
            at the repository root.
  G         a lesson removed by hand is not stated back in a second project, and that
            project gets a note of its own.
  W         both install paths load the mod at once (the repository as a plugin, and the mod
            folder): one fail-then-fix still writes ONE lesson.

S, N, X, D, G and W each run in a state of their own, so nothing one wrote is recalled in another.

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
# Every session is held to INVOKING the script: reading it first would hand an uninformed
# session the answer, and then neither the control's failure nor step B's lack of one would
# say anything about the note. The read tools are withheld for the same reason.
TASK = ("Build this project by running its build script, ./build.sh, and tell me the one line it prints on "
        "success. Do not read, print or inspect build.sh and do not list the directory: only invoke the script.")
NO_READ = ("--disallowed-tools", "Read,Grep,Glob")
SUBAGENT_TASK = ("Use the Agent tool to dispatch one general-purpose subagent. Its task: get this project's build to "
                 "succeed by invoking ./build.sh, correcting the invocation if it fails, and report the one line it prints "
                 "on success. It must not read or inspect build.sh, only invoke it. Do not run the build yourself. Wait "
                 "for the subagent to finish, and only then reply with what it reported.")
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


def session(cwd, env, model, with_mod, save, task=TASK, tools=("Bash",), extra=(), twice=False):
    """Run one headless session; return its Bash calls as [(command, errored, result text)].

    The raw stream is kept at SAVE, so a failed check can be read back rather than re-run.
    """
    argv = ["claude", "-p", "--model", model, "--setting-sources", "project",
            "--output-format", "stream-json", "--verbose", *NO_READ, *extra, "--allowedTools", *tools]
    # THE MOD MAY BE ENABLED ON THIS MACHINE through CLAUDE_CODE_PLUGIN_DIRS in the user's
    # settings.json, which --setting-sources does not switch off: the first run after it
    # was enabled had its CONTROL session write the lesson. So the variable is emptied for
    # every session here, and the control also carries the mod's own off switch.
    # The mission half is switched off: this journey is about the lessons half alone.
    env = dict(env, CLAUDE_CODE_PLUGIN_DIRS="", COMPOUND_MISSION="0")
    if with_mod:
        argv += ["--plugin-dir", MOD]
        if twice:
            # The repository root is a plugin whose hooks.json names the same module.
            argv += ["--plugin-dir", REPO]
    else:
        env["COMPOUND_LESSONS"] = "0"
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
        if not isinstance(msg, dict) or not isinstance(msg.get("message"), dict):
            continue
        content = msg["message"].get("content")
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
    check("control", "the control session wrote nothing", events(state) == [] and notes(env, "project", control) == [])

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
    # The premise is the subagent's own fail-then-fix. A headless parent can launch the
    # subagent in the background and end before it retries (seen once in three runs on
    # 2026-10-03: one failure logged, no fix, so nothing to judge). That is this step not
    # having happened, so it is tried once more before it is called a failure.
    for attempt in (1, 2):
        calls, _ = session(proj_s, env_s, args.model, True, os.path.join(root, "S%d.stream" % attempt),
                           task=SUBAGENT_TASK, tools=("Bash", "Agent"))
        if any(c[1] is False for c in builds(calls)):
            break
    check("S", "the subagent's build failed and was then fixed",
          any(c[1] is True for c in builds(calls)) and any(c[1] is False for c in builds(calls)), "attempt %d" % attempt)
    fails = [e for e in events(state_s) if e["ev"] == "fail"]
    check("S", "the build failed inside a subagent", bool(fails) and all(e["agent"] for e in fails))
    sub_notes = notes(env_s, "project", proj_s)
    check("S", "one project note was written by the mod", len(sub_notes) == 1 and "--profile" in sub_notes[0]["text"],
          sub_notes[0]["text"][:160] if sub_notes else "no note")

    def world(name):
        """A state and a global notes directory nothing else in this run has written to."""
        st, gd = os.path.join(root, "state-" + name), os.path.join(root, "claude-" + name)
        os.makedirs(st)
        os.makedirs(gd)
        return st, dict(env, SKILL_COMPOUNDER_STATE=st, SKILLNOTE_CLAUDE_DIR=gd)

    # N: a legitimate failure, fixed in the work
    state_n, env_n = world("n")
    proj_n = os.path.join(root, "delta")
    os.makedirs(proj_n)
    with open(os.path.join(proj_n, "version.txt"), "w") as fh:
        fh.write("1.0\n")
    check_sh = os.path.join(proj_n, "check.sh")
    with open(check_sh, "w") as fh:
        fh.write('#!/bin/sh\n[ "$(cat version.txt)" = "2.0" ] || { echo "check failed: version.txt says $(cat version.txt), expected 2.0" >&2; exit 1; }\necho "check ok"\n')
    os.chmod(check_sh, 0o755)
    calls, _ = session(proj_n, env_n, args.model, True, os.path.join(root, "N.stream"), tools=("Bash", "Edit", "Write"),
                       task="Run ./check.sh. If it fails, fix the project so that it passes (do not change check.sh), "
                            "run it again, and tell me the line it prints.")
    checks = [c for c in calls if "check.sh" in c[0]]
    failed_at = next((i for i, c in enumerate(checks) if c[1] is True), None)
    check("N", "the check failed and then passed",
          failed_at is not None and any(c[1] is False and c[0].strip().endswith("check.sh") for c in checks[failed_at + 1:]),
          " | ".join(c[0] for c in checks))
    check("N", "no note was written for a failure that was the check doing its job",
          notes(env_n, "project", proj_n) == [] and not any(e["ev"] == "lesson" for e in events(state_n)),
          "; ".join(e.get("reason", "") for e in events(state_n) if e["ev"] == "judged"))

    # X: a secret in the command
    state_x, env_x = world("x")
    proj_x = os.path.join(root, "epsilon")
    make_project(proj_x)
    secret = "sk-live-9f8e7d6c5b4a3210JOURNEY"
    # Reading the script first would skip the failure this step needs, so the read tools are
    # withheld and the first call is dictated.
    calls, _ = session(proj_x, env_x, args.model, True, os.path.join(root, "X.stream"),
                       task="Build this project. The build needs our deploy token in the environment. Your FIRST Bash "
                            "call must be exactly this and nothing else: DEPLOY_TOKEN=%s ./build.sh   If it fails, fix "
                            "the invocation, keeping the token in the command, and tell me the one line it prints on "
                            "success. Do not inspect build.sh." % secret)
    bx = builds(calls)
    check("X", "the command carrying the secret failed and was then fixed",
          len(bx) >= 2 and bx[0][1] is True and secret in bx[0][0] and any(c[1] is False for c in bx[1:]))
    wrote_x = notes(env_x, "project", proj_x)
    check("X", "the fix was written down", len(wrote_x) == 1, wrote_x[0]["text"][:160] if wrote_x else "no note")
    leaks = []
    for base, _, files in os.walk(root):
        if os.sep + "state-x" in base or os.sep + "claude-x" in base or base.startswith(proj_x):
            for name in files:
                with open(os.path.join(base, name), errors="replace") as fh:
                    if secret in fh.read():
                        leaks.append(os.path.join(base, name))
    check("X", "the secret is in no note, log or ledger", leaks == [], ", ".join(leaks))

    # D: the shell is in a subdirectory of a repository
    state_d, env_d = world("d")
    proj_d = os.path.join(root, "zeta")
    make_project(os.path.join(proj_d, "services", "api"))
    subprocess.run(["git", "init", "-q", proj_d], check=True, capture_output=True)
    session(proj_d, env_d, args.model, True, os.path.join(root, "D.stream"),
            task="The build script is in services/api. First run `cd services/api` as its own separate Bash "
                 "command. Then, as a second separate command, run ./build.sh and tell me the one line it prints "
                 "on success (fix the invocation if it fails).")
    found = []
    for base, _, files in os.walk(proj_d):
        if "CLAUDE.md" in files:
            found.append(os.path.relpath(os.path.join(base, "CLAUDE.md"), proj_d))
    check("D", "the note is at the repository root and nowhere else", found == [os.path.join(".claude", "CLAUDE.md")],
          ", ".join(found) or "no note")

    # G: a lesson removed by hand
    state_g, env_g = world("g")
    proj_g1, proj_g2 = os.path.join(root, "eta"), os.path.join(root, "theta")
    make_project(proj_g1)
    make_project(proj_g2)
    session(proj_g1, env_g, args.model, True, os.path.join(root, "G1.stream"))
    first = notes(env_g, "project", proj_g1)
    if first:
        subprocess.run([os.path.join(REPO, "bin", "skillnote"), "remove", first[0]["id"], "--project", proj_g1],
                       cwd=proj_g1, env=env_g, capture_output=True, text=True, timeout=60)
    before_g = len(events(state_g))
    session(proj_g2, env_g, args.model, True, os.path.join(root, "G2.stream"))
    new_g = events(state_g)[before_g:]
    check("G", "the first project's lesson was written and then removed",
          bool(first) and notes(env_g, "project", proj_g1) == [])
    check("G", "the removed lesson was not stated back", not any(e["ev"] == "fail" and e.get("recalled") for e in new_g),
          ", ".join(e["ev"] for e in new_g))
    check("G", "the second project got a note of its own", len(notes(env_g, "project", proj_g2)) == 1)

    # W: the mod loaded twice
    state_w, env_w = world("w")
    proj_w = os.path.join(root, "iota")
    make_project(proj_w)
    calls, _ = session(proj_w, env_w, args.model, True, os.path.join(root, "W.stream"), twice=True)
    bw = builds(calls)
    check("W", "the session failed and then fixed the build", len(bw) >= 2 and bw[0][1] is True and any(c[1] is False for c in bw[1:]))
    rows_w = [e["ev"] for e in events(state_w)]
    check("W", "loaded twice, the mod logged one failure and wrote one lesson",
          rows_w.count("fail") == 1 and rows_w.count("lesson") == 1 and len(notes(env_w, "project", proj_w)) == 1,
          ", ".join(rows_w))

    print("\n%d of %d checks passed; root %s" % (sum(results), len(results), root))
    if not args.keep and all(results):
        shutil.rmtree(root)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
