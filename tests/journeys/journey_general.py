#!/usr/bin/env python3
"""The general pool: the lessons this package ships, met in real `claude -p` sessions. Run
by hand, on macOS with zsh as the login shell: that is where the shipped guards apply.

  guards    one session sends the three wrong forms the shipped guards are about (a bare
            ===== after echo, an assignment to `status`, GNU `sed -i`) and then `timeout`.
            Each of the three is refused once, with the general lesson of the package
            quoted as the reason, and one `guard` event names each lesson. `timeout` is
            refused by no guard: `macos-gnu-only-commands` is recalled when it fails, and
            where this Mac has a `timeout` (Homebrew's coreutils) it simply runs.
  glob      a session runs `rm -f` on a glob that matches nothing. zsh refuses it, and the
            failure is given the shipped recall lesson `zsh-no-matches-found`.
  pip       a session runs `pip install --dry-run` against a Python its package manager
            owns, and is told to run nothing else. The failure is given
            `pip-externally-managed`. The commands the session says it would run next are
            printed and not judged; nothing is installed anywhere. Skipped, and said so,
            when no such Python is found.
  twice     three sessions in a row meet the glob failure with COMPOUND_RECUR_LIMIT=2. The
            lesson is recalled each time, no recall is marked ineffective, no stop is
            refused for a strengthening, and `compound status` lists the lesson as
            recurring with `compound disable`.
  off       with `zsh-equals-not-found` disabled and COMPOUND_PLATFORM=linux, the same wrong
            forms are refused by no guard and recalled as neither lesson.

The user level, the event log and the project are a throwaway world; the general level is
this checkout's `lessons/`. The switch file of the `off` step is in the throwaway home.

usage: journey_general.py [--model haiku] [--keep]
"""
import json
import os
import subprocess
import sys

import common

QUIET = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}
WRONG = [
    ("zsh-equals-not-found", "echo ===== ; echo JOURNEY_EQUALS"),
    ("zsh-status-path-variables", "status=$(echo 7); echo \"JOURNEY_STATUS $status\""),
    ("sed-in-place-bsd", "sed -i 's/alpha/beta/' notes.txt"),
    ("macos-gnu-only-commands", "timeout 5 echo JOURNEY_TIMEOUT"),
]
GUARDS_PROMPT = (
    "Run these four Bash commands, one Bash call each, in this order. Send each one exactly as written first, "
    "even if you expect it to be refused or to fail:\n%s\n"
    "When a call is refused, read the reason, then do the same job the way the reason says works here, and go on "
    "to the next command. Finally tell me in one line each what happened to the four commands."
    % "\n".join("%d. %s" % (index + 1, command) for index, (_name, command) in enumerate(WRONG)))
GLOB = "rm -f build/*.journeyobj && echo JOURNEY_CLEANED"
GLOB_PROMPT = ("Run exactly this Bash command first, as written: %s\nIf it fails, read what comes back with the "
               "error, make it work, and tell me what you ran." % GLOB)
OFF_PROMPT = ("Run these two Bash commands, one Bash call each, exactly as written: first\necho ===== ; echo JOURNEY_EQUALS\n"
              "then\ntimeout 5 echo JOURNEY_TIMEOUT\nBoth may fail, and that is expected: do not retry or fix them. "
              "Then tell me what each printed.")


def managed_python():
    """A Python that refuses `pip install` as externally managed (PEP 668), or None."""
    for path in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"):
        if not os.path.exists(path):
            continue
        done = subprocess.run([path, "-m", "pip", "install", "--dry-run", "cowsay"], capture_output=True, text=True,
                              timeout=120, env=dict(os.environ, PIP_DRY_RUN="1", PIP_DISABLE_PIP_VERSION_CHECK="1"))
        if "externally-managed-environment" in done.stderr:
            return path
    return None


def main():
    args = common.arguments(__doc__)
    w = common.World("general")
    project = w.project("alpha")
    shell = os.path.basename(os.environ.get("CLAUDE_CODE_SHELL") or os.environ.get("SHELL") or "")
    print("      platform %s, shell %s" % (sys.platform, shell or "unknown"))
    pool = {row["name"]: row for row in w.items(project) if row["level"] == "general" and row["kind"] == "lesson"}
    w.check("pool", "the package ships its six lessons and every one applies here",
            len(pool) == 6 and all(row["applies"] and not row["disabled"] for row in pool.values()),
            {name: (row["applies"], row["platform"], row["shell"]) for name, row in pool.items()})
    w.check("pool", "the user level of this world is empty: what fires is the package's own",
            [row["name"] for row in w.items(project) if row["level"] != "general"] == [])

    with open(os.path.join(project, "notes.txt"), "w") as fh:
        fh.write("alpha one\nalpha two\n")
    s = w.session(project, GUARDS_PROMPT, args.model, **QUIET)
    rows = w.events(project, session=s.sid, kind="guard")
    w.show("guard", rows)
    print("      calls: %s" % " | ".join("%s -> %s" % (c[0][:60], "refused/error" if c[1] else "ok") for c in s.bash()))
    for name, command in WRONG[:3]:
        sent = [c for c in s.bash() if c[0].strip() == command]
        w.check("guards", "%s: the wrong form was sent and refused" % name, bool(sent) and sent[0][1] is True,
                sent[0][2][:200] if sent else "the session did not send %r" % command)
        w.check("guards", "%s: the refusal quoted the general lesson of the package" % name,
                bool(sent) and ("<<<RECORDED-NOTE lesson=%s level=general path=%s" % (
                    name, os.path.join(common.PLUGIN, "lessons", name))) in sent[0][2])
        w.check("guards", "%s: exactly one guard event names it" % name,
                len([e for e in rows if e.get("lesson") == name]) == 1, [e.get("lesson") for e in rows])
    name, command = WRONG[3]
    sent = [c for c in s.bash() if c[0].strip() == command]
    w.check("guards", "%s: `timeout` was sent and no guard refused it" % name,
            bool(sent) and "RECORDED-NOTE lesson=%s" % name not in sent[0][2] and "stopped before it ran" not in sent[0][2],
            sent[0][2][:200] if sent else "the session did not send %r" % command)
    w.check("guards", "%s: no guard event names it" % name, not any(e.get("lesson") == name for e in rows),
            [e.get("lesson") for e in rows])
    if sent and sent[0][1] is True:
        recalled = [e.get("lesson") for e in w.events(project, session=s.sid, kind="recall")]
        w.check("guards", "%s: this Mac has no `timeout`, the call failed, and the lesson was recalled" % name,
                name in recalled, recalled)
    else:
        print("      this Mac has a `timeout`: the call ran (%s)" % (sent[0][2][:80] if sent else "not sent"))
    w.check("guards", "the pre-call path wrote no error", w.events(project, session=s.sid, kind="error") == [],
            w.events(project, session=s.sid, kind="error"))
    with open(os.path.join(project, "notes.txt")) as fh:
        text = fh.read()
    print("      notes.txt after the session: %r; files: %s" % (text, sorted(os.listdir(project))))
    w.check("guards", "the sed job was then done a way that works here", "beta one" in text, text)
    print("      final message: %s" % s.result[:600].replace("\n", " / "))

    s = w.session(project, GLOB_PROMPT, args.model, **QUIET)
    rows = w.events(project, session=s.sid)
    w.show("event", [e for e in rows if e["type"] in ("recall", "guard", "capture", "judge")])
    sent = [c for c in s.bash() if "journeyobj" in c[0]]
    recalls = [e for e in rows if e["type"] == "recall"]
    w.check("glob", "the glob that matches nothing failed in zsh", bool(sent) and "no matches found" in sent[0][2],
            sent[0][2][:200] if sent else "no such call")
    w.check("glob", "the failure was given the shipped lesson zsh-no-matches-found",
            any(e.get("lesson") == "zsh-no-matches-found" for e in recalls), [e.get("lesson") for e in recalls])
    # What the mod adds beside a result is not in the stream: the event is its record.
    w.check("glob", "a later call then did the job", any(c[1] is False and "JOURNEY_CLEANED" in c[2] for c in s.bash()[1:]))
    w.check("glob", "a recalled failure is not captured as a new lesson", not any(e["type"] == "capture" for e in rows))
    print("      calls: %s" % " | ".join("%s -> %s" % (c[0][:70], "error" if c[1] else "ok") for c in s.bash()))

    python = managed_python()
    if python is None:
        print("SKIP  pip      no Python here refuses pip as externally managed; the lesson was not met")
    else:
        prompt = ("A script in this project needs the Python package cowsay, for the interpreter %s. Run exactly this "
                  "Bash command, as written, and no other: %s -m pip install --dry-run cowsay\nIf it fails, read what "
                  "comes back with the error. Do not run anything else. Reply with the exact commands you would run "
                  "next to get the package installed, one per line, and nothing more." % (python, python))
        s = w.session(project, prompt, args.model, PIP_DISABLE_PIP_VERSION_CHECK="1", **QUIET)
        rows = w.events(project, session=s.sid)
        w.show("event", [e for e in rows if e["type"] in ("recall", "capture", "judge")])
        sent = [c for c in s.bash() if "pip install" in c[0]]
        recalls = [e for e in rows if e["type"] == "recall"]
        w.check("pip", "pip refused the install as externally managed",
                bool(sent) and "externally-managed-environment" in sent[0][2], sent[0][2][:200] if sent else "no such call")
        w.check("pip", "the failure was given the shipped lesson pip-externally-managed",
                any(e.get("lesson") == "pip-externally-managed" for e in recalls), [e.get("lesson") for e in recalls])
        later = [c[0] for c in s.bash()[1:]]
        said = s.result + "\n" + "\n".join(later)
        print("      what the session said it would run next (observed, not judged): %s" % s.result[:500].replace("\n", " / "))
        print("      Bash calls after the refusal: %s" % (later or "none"))
        print("      names --break-system-packages: %s; names a virtual environment: %s" % (
            "--break-system-packages" in said, "venv" in said))

    # The glob lesson was recalled once above. Twice more, past COMPOUND_RECUR_LIMIT=2.
    limit = {"COMPOUND_RECUR_LIMIT": "2"}
    for _ in range(2):
        s = w.session(project, GLOB_PROMPT, args.model, **dict(QUIET, **limit))
    rows = w.events(project, session=s.sid)
    recalls = [e for e in w.events(project, kind="recall") if e.get("lesson") == "zsh-no-matches-found"]
    w.show("recall", [{k: e.get(k) for k in ("ts", "session", "lesson", "ineffective")} for e in recalls])
    w.check("twice", "the lesson was recalled in three sessions", len(set(e.get("session") for e in recalls)) >= 3,
            len(recalls))
    w.check("twice", "no recall of it is marked ineffective", not any(e.get("ineffective") for e in recalls))
    w.check("twice", "no stop was refused for a strengthening",
            not any(e.get("why") == "strengthen" for e in w.events(project, kind="refuse")),
            w.events(project, kind="refuse"))
    w.check("twice", "the last session owes nothing",
            json.loads(w.cli(project, "events", "--unsettled", "--session", s.sid, "--json").stdout) == [])
    status = w.cli(project, "status", **limit)
    line = [text for text in status.stdout.splitlines() if text.strip().startswith("recurring")]
    w.check("twice", "status lists it as recurring and names the switch",
            len(line) == 1 and "compound disable zsh-no-matches-found" in line[0], line or status.stdout[-600:])
    w.check("twice", "status prints no command that rewrites it", "add --update --name zsh-no-matches-found" not in status.stdout)

    done = w.cli(project, "disable", "zsh-equals-not-found")
    w.check("off", "`compound disable` switched the lesson off in the throwaway home",
            done.returncode == 0 and os.path.isfile(os.path.join(w.home, "disabled.json")), done.stderr)
    s = w.session(project, OFF_PROMPT, args.model, COMPOUND_PLATFORM="linux", **QUIET)
    rows = w.events(project, session=s.sid)
    w.show("event", [e for e in rows if e["type"] in ("recall", "guard", "capture")])
    print("      calls: %s" % " | ".join("%s -> %s" % (c[0][:60], "error" if c[1] else "ok") for c in s.bash()))
    equals = [c for c in s.bash() if c[0].strip() == WRONG[0][1]]
    timeout = [c for c in s.bash() if c[0].strip() == WRONG[3][1]]
    w.check("off", "the disabled lesson's wrong form ran, and failed in zsh itself",
            bool(equals) and "RECORDED-NOTE lesson=zsh-equals-not-found" not in equals[0][2] and "not found" in equals[0][2],
            equals[0][2][:200] if equals else "no such call")
    w.check("off", "the macOS lesson's wrong form ran where the platform is said to be linux",
            bool(timeout) and "RECORDED-NOTE lesson=macos-gnu-only-commands" not in timeout[0][2],
            timeout[0][2][:200] if timeout else "no such call")
    w.check("off", "no guard event was written", [e for e in rows if e["type"] == "guard"] == [])
    w.check("off", "neither lesson was recalled",
            not any(e["type"] == "recall" and e.get("lesson") in ("zsh-equals-not-found", "macos-gnu-only-commands")
                    for e in rows), [e.get("lesson") for e in rows if e["type"] == "recall"])
    w.finish(args.keep)


if __name__ == "__main__":
    main()
