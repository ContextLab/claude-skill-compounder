#!/usr/bin/env python3
"""Prints every command docs/guide.md and the README show, with what it prints now.

    python3 dev/guide_examples.py            every part
    python3 dev/guide_examples.py report     one part: install, guide, status or report

Each command is run by the real CLI of this checkout in a throwaway world: a home for a
user named `me`, a project named `proj`, a Claude directory the package is installed into
with `--claude-dir` and `--bin-dir`. The real `~/.claude` is never named. In what is
printed the world's directory reads `/Users/me` and this checkout reads
`/Users/me/.claude/compound/app`, which is where an install puts it.

No session runs here. The events a session would have written (a guard's refusal, a
recall, a capture) are written with `compound log`, which is what the mod itself calls.
The log of the `report` part is built the same way, with the clock pinned (COMPOUND_NOW),
so its figures are the same on every run. Standard library only, Python 3.9.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ANCHOR = r"(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)"


class World(object):
    def __init__(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="compound-guide-"))
        self.me = os.path.join(self.root, "me")
        self.claude = os.path.join(self.me, ".claude")
        self.bin = os.path.join(self.me, ".local", "bin")
        self.project = os.path.join(self.me, "proj")
        for path in (self.claude, self.project):
            os.makedirs(path)
        self.surfer = shutil.which("surfer")

    def env(self, **extra):
        path = [self.bin, "/usr/bin", "/bin", "/usr/sbin", "/sbin", "/opt/homebrew/bin", "/usr/local/bin"]
        for tool in (self.surfer, shutil.which("claude")):
            if tool and os.path.dirname(tool) not in path:
                path.append(os.path.dirname(tool))
        env = {"HOME": self.me, "PATH": ":".join(path), "SHELL": "/bin/zsh", "LANG": "en_US.UTF-8",
               "COMPOUND_HOME": os.path.join(self.claude, "compound"), "COMPOUND_CLAUDE_DIR": self.claude,
               "COMPOUND_PROJECT": self.project}
        env.update(extra)
        return env

    def shown(self, text):
        text = text.replace(self.me, "/Users/me").replace(REPO, "/Users/me/.claude/compound/app")
        if self.surfer:
            text = text.replace(self.surfer, "/Users/me/.local/bin/surfer")
        return text

    def run(self, args, stdin="", quiet=False, **extra):
        """Run `compound ARGS`; print the command and what it printed."""
        proc = subprocess.run([os.path.join(REPO, "bin", "compound")] + list(args), input=stdin, cwd=self.project,
                              env=self.env(**extra), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True, timeout=300)
        if not quiet:
            sets = "".join("%s=%s " % (key, shlex.quote(value)) for key, value in sorted(extra.items())
                           if key not in ("COMPOUND_NOW", "CLAUDE_CODE_SESSION_ID"))
            print(self.shown("$ %scompound %s" % (sets, " ".join(shlex.quote(arg) for arg in args))))
            if stdin:
                print(stdin.rstrip("\n"))
                print("^D")
            print(self.shown(proc.stdout).rstrip("\n"))
            print("[exit %d]\n" % proc.returncode)
        return proc

    def log(self, event, **extra):
        proc = self.run(["log"], stdin=json.dumps(event), quiet=True, **extra)
        if proc.returncode != 0:
            raise SystemExit("compound log failed: %s" % proc.stdout)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def heading(text):
    print("=" * 78)
    print(text)
    print("=" * 78)


def install(world):
    heading("README, Install: the installer's last step, then `compound status`")
    world.run(["install", "--claude-dir", world.claude, "--bin-dir", world.bin])
    world.run(["status"])


def guide(world):
    heading("guide: Record a lesson yourself")
    world.run(["add", "--name", "build-needs-profile", "--when", "Use when running ./build.sh in this repository."],
              stdin='Run `./build.sh --profile dev`. A bare `./build.sh` fails with\n"error: a profile is required".\n')
    world.run(["add", "--name", "python3-no-tomllib-use-tomli",
               "--when", "Use when reading a TOML file with Python older than 3.11."],
              stdin='Python before 3.11 has no `tomllib`. `import tomllib` fails with "ModuleNotFoundError".\n'
                    'Run the script with `python3.11` or later, or `pip install tomli` and `import tomli as tomllib`.\n')

    heading("guide: The four forms of a lesson")
    world.run(["add", "--name", "zsh-equals-word", "--level", "user",
               "--when", 'Use when a zsh command line has a bare word starting with "=".',
               "--match", ANCHOR + r"echo\s+=+"],
              stdin='zsh expands a bare word starting with "=" as a command lookup and fails with "not found".\n'
                    "Quote it or use printf '%s\\n' '====='.\n")
    world.run(["add", "--name", "no-env-edit", "--when", "Use when editing a .env file.",
               "--match", r'"file_path": "[^"]*\.env"', "--tool", "Edit", "--tool", "Write",
               "--body", "Never edit .env; change .env.example."])

    heading("guide: Find and read what is recorded")
    world.run(["find", "toml", "python"])
    world.run(["list"])
    world.run(["show", "python3-no-tomllib-use-tomli"])

    heading("guide: A lesson for one platform or shell")
    world.run(["add", "--name", "zsh-function-name-is-alias", "--level", "user", "--shell", "zsh",
               "--when", 'Use when defining a function in zsh fails with "defining function based on alias".',
               "--body", "Name the function something that is not an alias, or write `function name {`."])
    world.run(["show", "zsh-equals-not-found"], COMPOUND_SHELL="bash")

    heading("guide: Change a lesson")
    world.run(["add", "--update", "--name", "build-needs-profile", "--match", ANCHOR + r"\./build\.sh\s*($|[;&|)])"])
    world.run(["add", "--update", "--name", "build-needs-profile", "--no-match"])
    world.run(["add", "--update", "--name", "build-needs-profile", "--body", "-"],
              stdin="Run `./build.sh --profile dev` (or `make build PROFILE=dev`). Without a profile\n"
                    'both fail with "error: a profile is required".\n')

    heading("guide: Turn a lesson into a skill")
    world.run(["skill", "zsh-equals-word"])

    heading("guide: Move a lesson up a level")
    world.run(["promote", "python3-no-tomllib-use-tomli", "--to", "user"])

    heading("guide: Propose a lesson to the general pool")
    world.run(["promote", "python3-no-tomllib-use-tomli", "--to", "general"])

    heading("guide: Switch off a lesson that ships with compound")
    world.run(["rm", "sed-in-place-bsd"])
    world.run(["disable", "sed-in-place-bsd"])
    world.run(["list", "--level", "general"])
    world.run(["enable", "sed-in-place-bsd"])


def status(world):
    """What two sessions would have left: the events are written with `compound log`."""
    heading("guide: Decline a lesson; Settle a lesson an earlier session left open")
    first, second = "1f0c2a9e-0000-4000-8000-000000000001", "7b3d5e42-0000-4000-8000-000000000002"
    world.log({"type": "reuse", "lessons": ["python3-no-tomllib-use-tomli"], "prompts": [], "ms": 1210,
               "gather_ms": 420, "judge_ms": 790}, CLAUDE_CODE_SESSION_ID=first)
    world.log({"type": "guard", "lesson": "zsh-equals-not-found", "tool": "Bash", "text": "echo ===== && ./build.sh",
               "ms": 68, "watched": True}, CLAUDE_CODE_SESSION_ID=first)
    for session in (first, second):
        world.log({"type": "recall", "lesson": "pip-externally-managed", "tool": "Bash", "call": "pip install tomli",
                   "error": "error: externally-managed-environment", "at": "failure", "ms": 700},
                  CLAUDE_CODE_SESSION_ID=session)
    world.log({"type": "capture", "tool": "Bash", "failed": "./deploy.sh", "error": "error: no target given",
               "fixed": "./deploy.sh --target staging", "ms": 810}, CLAUDE_CODE_SESSION_ID=first)
    world.log({"type": "capture", "tool": "Bash", "failed": "make dcos", "error": "make: *** No rule to make target",
               "fixed": "make docs", "ms": 790}, CLAUDE_CODE_SESSION_ID=second)
    world.run(["use", "zsh-equals-word"], CLAUDE_CODE_SESSION_ID=second)
    world.run(["events", "--unsettled"])
    listed = json.loads(world.run(["events", "--unsettled", "--json"], quiet=True).stdout)
    typo = [row["id"] for row in listed if row.get("fixed") == "make docs"][0]
    world.run(["skip", "--why", "a one-off typo"])
    world.run(["skip", "--settles", typo, "--why", "a one-off typo"])

    heading("guide: Read `compound status`")
    world.run(["status"])

    heading("guide: Remove a lesson")
    world.run(["rm", "build-needs-profile"])

    heading("guide: When a request keeps coming back; Read the event log")
    world.run(["events", "--type", "repeat"])
    world.run(["events", "--limit", "5"])


NOW = 1791000000  # 2026-10-03T03:20:00Z


def report(world):
    """A log of two weeks, written with `compound log` at pinned times."""
    heading("guide: Read `compound report`")
    home = os.path.join(world.claude, "report-store")
    pinned = {"COMPOUND_HOME": home, "COMPOUND_NOW": str(NOW)}

    def at(hours_ago):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - int(hours_ago * 3600)))

    def ev(type_, hours_ago, session, **fields):
        fields.update(type=type_, ts=at(hours_ago), session=session)
        world.log(fields, **pinned)

    # Twelve refusals: eight followed by a different call, two by the same call, two by none.
    for index in range(12):
        lesson = "zsh-equals-not-found" if index < 8 else "sed-in-place-bsd"
        text = "echo ===== && make test" if index < 8 else "sed -i 's/a/b/' notes.txt"
        session, hours = "guard-%02d" % index, 300 - index * 20
        ev("guard", hours, session, lesson=lesson, tool="Bash", text=text, ms=62 + index * 2, watched=True)
        if index not in (5, 11):
            same = index in (3, 6)
            ev("retry", hours - 0.01, session, lessons=[lesson], tool="Bash", same=same,
               text=text if same else "printf '%s\\n' '=====' && make test")
    # Eleven captures: six recorded, three declined, two left.
    for index in range(11):
        session, hours = "learn-%02d" % index, 280 - index * 24
        ident = "c%07d" % index
        ev("judge", hours + 0.02, session, moment="fix", verdict="fix", ms=640 + index * 35, tool="Bash")
        ev("capture", hours, session, id=ident, tool="Bash", failed="./build.sh", error="error: a profile is required",
           fixed="./build.sh --profile dev", ms=640 + index * 35)
        if index < 6:
            ev("learn", hours - 0.05 - index * 0.01, session, lesson="lesson-%02d" % index, level="project", kind="lesson",
               settles=ident)
        elif index < 9:
            ev("skip", hours - 0.03, session, why="a one-off: the path was mistyped", settles=ident)
    # Twelve recalls of three lessons; three of them marked ineffective, each debt ending another way.
    recalls = [("pip-externally-managed", 5), ("build-needs-profile", 4), ("python3-no-tomllib-use-tomli", 3)]
    count = 0
    for lesson, times in recalls:
        for turn in range(times):
            session, hours = "recall-%02d" % count, 260 - count * 20
            weak = lesson != "pip-externally-managed" and turn == times - 1
            ev("judge", hours + 0.01, session, moment="recall", verdict="named", ms=600 + count * 22, tool="Bash",
               named=[lesson])
            ev("recall", hours, session, lesson=lesson, tool="Bash", call="the failed call", error="its error",
               at="failure", ms=600 + count * 22, ineffective=weak)
            if weak and lesson == "build-needs-profile":
                ev("learn", hours - 0.1, session, lesson=lesson, level="project", kind="lesson", update=True)
            elif weak:
                ev("skip", hours - 0.1, session, why="the lesson does not describe the failure: this was a YAML file")
            count += 1
    ev("recall", 9, "recall-99", lesson="lesson-03", tool="Bash", call="the failed call", error="its error",
       at="failure", ms=655, ineffective=True)
    ev("judge", 9.01, "recall-99", moment="recall", verdict="named", ms=655, tool="Bash", named=["lesson-03"])
    # Fourteen reuse checks that had a candidate: thirteen judged, one answered from the memo.
    verdicts = ["named"] * 3 + ["nothing"] * 6 + ["not-substantial"] * 3 + ["unanswered"]
    for index, verdict in enumerate(verdicts):
        session, hours = "reuse-%02d" % index, 240 - index * 17
        more = {"reason": "no reply in 10000 ms"} if verdict == "unanswered" else {}
        ev("judge", hours, session, moment="reuse", verdict=verdict, ms=10000 if verdict == "unanswered" else 700 + index * 45,
           prompt_id="p%02d" % index, **more)
        if verdict == "named":
            ev("reuse", hours - 0.001, session, lessons=["release-notes-format"] + (["scripts/notes.py"] if index == 0 else []),
               prompts=["0d5c9f1e:4"] if index == 1 else [], ms=1150 + index * 60, gather_ms=420, judge_ms=700 + index * 45)
        if verdict == "unanswered":
            ev("error", hours - 0.001, session, where="reuse.judge", message="no reply in 10000 ms")
    ev("judge", 23, "reuse-98", moment="reuse", verdict="named", ms=0, memo=True, prompt_id="p00")
    ev("reuse", 22.999, "reuse-98", lessons=["release-notes-format"], prompts=[], ms=410, gather_ms=410, judge_ms=0, memo=True)
    world.run(["report"], **pinned)


PARTS = {"install": install, "guide": guide, "status": status, "report": report}


def main(argv):
    wanted = argv[1:] or ["install", "guide", "status", "report"]
    for name in wanted:
        if name not in PARTS:
            sys.stderr.write(__doc__)
            return 2
    world = World()
    try:
        # Every part reads the store the earlier ones left, so they run in order up to the last one asked for.
        order = ["install", "guide", "status", "report"]
        last = max(order.index(name) for name in wanted)
        for name in order[:last + 1]:
            if name in wanted or name != "report":
                if name not in wanted:
                    with open(os.devnull, "w") as null:
                        keep, sys.stdout = sys.stdout, null
                        try:
                            PARTS[name](world)
                        finally:
                            sys.stdout = keep
                else:
                    PARTS[name](world)
    finally:
        world.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
