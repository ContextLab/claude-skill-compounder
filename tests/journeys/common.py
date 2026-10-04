"""Shared by the journeys: a throwaway world, real `claude -p` sessions, and the event log.

Every journey runs real headless sessions with this repository loaded as a plugin
(`--plugin-dir`). They spend model calls, so they are run by hand and never by
run_tests.sh.

Nothing here touches the real store or the real settings:

  COMPOUND_HOME, COMPOUND_CLAUDE_DIR     a temporary user level and Claude directory
  COMPOUND_PROJECT                       the temporary project of each session
  CLAUDE_HISTORY_SURFER_DIR              a temporary prompt log, seeded by the journey
  TMPDIR                                 a temporary directory of the session's own
  CLAUDE_CODE_PLUGIN_DIRS=""             so no installed copy of the mod loads as well
  --setting-sources project              so the user's own hooks stay out

The mod's once-per-session claims are under COMPOUND_HOME, in claims/<session id>/.

COMPOUND_JOURNEY_PLUGIN names another copy of the package to load in place of this
checkout (an installed copy, an older one); the CLI the journeys call stays this one.

The event log is read through `bin/compound events --json`, the same way the mod reads it.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.join(REPO, "bin", "compound")
PLUGIN = os.environ.get("COMPOUND_JOURNEY_PLUGIN") or REPO

BUILD_SH = """#!/bin/sh
# The build needs a profile; there is no default.
if [ "$1" != "--profile" ] || [ -z "$2" ]; then
  echo "build.sh: error: a profile is required, e.g. ./build.sh --profile dev" >&2
  exit 2
fi
echo "build ok ($2)"
"""

# Held to INVOKING the script: reading it first would hand the session the answer.
BUILD_TASK = ("Build this project by running its build script, ./build.sh, and tell me the one line it prints on "
              "success. Do not read, print or inspect build.sh and do not list the directory: only invoke the script.")


class Session:
    def __init__(self, sid, calls, result, returncode, stream):
        self.sid = sid
        self.calls = calls          # [(tool, input dict, errored, result text)]
        self.result = result        # the final message
        self.returncode = returncode
        self.stream = stream        # where the raw stream-json was kept

    def bash(self):
        return [(c[1].get("command", ""), c[2], c[3]) for c in self.calls if c[0] == "Bash"]


class World:
    def __init__(self, name):
        if not os.path.isfile(CLI):
            raise SystemExit("bin/compound is not there; the journeys drive the real CLI")
        # realpath: on macOS the temporary directory is a symlink, and the CLI, git and the
        # session must all name one project by one path.
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="compound-journey-%s-" % name))
        self.home = os.path.join(self.root, "home")
        self.claude = os.path.join(self.root, "claude")
        self.tmp = os.path.join(self.root, "tmp")
        self.surfer = os.path.join(self.root, "surfer")
        for d in (self.home, self.claude, self.tmp, self.surfer):
            os.makedirs(d)
        self.results = []
        self.count = 0

    def env(self, project, **extra):
        env = dict(os.environ)
        for name in list(env):
            if name.startswith("COMPOUND_"):
                del env[name]
        env.update(COMPOUND_HOME=self.home, COMPOUND_CLAUDE_DIR=self.claude, COMPOUND_PROJECT=project,
                   CLAUDE_HISTORY_SURFER_DIR=self.surfer, TMPDIR=self.tmp, CLAUDE_CODE_PLUGIN_DIRS="")
        env.update(extra)
        return env

    def project(self, name, build=False):
        path = os.path.join(self.root, name)
        os.makedirs(path)
        if build:
            script = os.path.join(path, "build.sh")
            with open(script, "w") as fh:
                fh.write(BUILD_SH)
            os.chmod(script, 0o755)
        return path

    def cli(self, project, *args, stdin=None, **extra):
        return subprocess.run([CLI, *args], input=stdin, cwd=project, env=self.env(project, **extra),
                              capture_output=True, text=True, timeout=60)

    def add(self, project, name, when, body, *more):
        done = self.cli(project, "add", "--name", name, "--when", when, *more, stdin=body)
        if done.returncode != 0:
            raise SystemExit("could not seed lesson %s: %s" % (name, done.stderr))

    def events(self, project, session=None, kind=None):
        args = ["events", "--json"]
        if session:
            args += ["--session", session]
        if kind:
            args += ["--type", kind]
        done = self.cli(project, *args)
        if done.returncode != 0:
            raise SystemExit("compound events failed: %s" % done.stderr)
        return json.loads(done.stdout)

    def items(self, project):
        done = self.cli(project, "list", "--json")
        return json.loads(done.stdout) if done.returncode == 0 else []

    def seed_prompt(self, cwd, session, prompt, ts="2026-09-01T12:00:00Z", seq=1):
        """One row in the temporary prompt log, as history-surfer stores it."""
        slug = "".join(ch if ch.isalnum() else "-" for ch in cwd)
        folder = os.path.join(self.surfer, "projects", slug)
        os.makedirs(folder, exist_ok=True)
        row = {"ts": ts, "session_id": session, "cwd": cwd, "project_slug": slug, "seq": seq, "prompt": prompt,
               "source": "stdin", "is_command": False}
        with open(os.path.join(folder, "prompts.jsonl"), "a") as fh:
            fh.write(json.dumps(row) + "\n")

    def copy_of_package(self):
        """A second copy of this package, as an installed clone beside a checkout would be."""
        target = os.path.join(self.root, "second-copy")
        shutil.copytree(PLUGIN, target, ignore=shutil.ignore_patterns(".git", "notes", "docs", "tests", "dev", "__pycache__"))
        return target

    def claims(self, sid):
        """The names of what the mod did once in a session (guard-<lesson>, stop-<call>, ...)."""
        folder = os.path.join(self.home, "claims", sid)
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def block_claims(self):
        """Puts a regular file wherever a claims directory would be made, so none can be."""
        for path in (os.path.join(self.home, "claims"), os.path.join(self.tmp, "compound-claims")):
            with open(path, "w") as fh:
                fh.write("not a directory\n")

    def slow_copy(self, verbs, seconds, name="slow-copy"):
        """A copy of the package whose CLI sleeps before each of `verbs` (one name, or
        several) and is otherwise this one. Every call it gets is noted, one verb per
        line, in the file `slow_calls` names."""
        if isinstance(verbs, str):
            verbs = (verbs,)
        target = os.path.join(self.root, name)
        shutil.copytree(PLUGIN, target, ignore=shutil.ignore_patterns(".git", "notes", "docs", "tests", "dev", "__pycache__", "bin"))
        os.makedirs(os.path.join(target, "bin"))
        wrapper = os.path.join(target, "bin", "compound")
        with open(wrapper, "w") as fh:
            # The sleep holds none of the wrapper's pipes, so killing the wrapper ends the call.
            fh.write('#!/bin/sh\necho "$1" >> "%s"\ncase "$1" in %s) sleep %d >/dev/null 2>&1 </dev/null ;; esac\nexec "%s" "$@"\n'
                     % (os.path.join(target, "calls.log"), "|".join(verbs), seconds, CLI))
        os.chmod(wrapper, 0o755)
        return target

    def slow_calls(self, target):
        """The verbs a slow copy's CLI was called with, in order."""
        path = os.path.join(target, "calls.log")
        if not os.path.isfile(path):
            return []
        with open(path) as fh:
            return [line.strip() for line in fh if line.strip()]

    def session(self, project, prompts, model, tools=("Bash",), also=(), plugin=None, flags=(), **extra):
        """One headless session. `prompts` is one prompt, or a list sent as turns of one process,
        each one typed when the turn before it has ended. `also` names further plugin
        directories to load beside the package; `plugin` names a copy to load in its place;
        `flags` are further arguments for `claude`."""
        self.count += 1
        argv = ["claude", "-p", "--model", model, "--setting-sources", "project", "--output-format", "stream-json",
                "--verbose", "--plugin-dir", plugin or PLUGIN, "--disallowed-tools", "Read,Grep,Glob", *flags]
        for folder in also:
            argv += ["--plugin-dir", folder]
        if not isinstance(prompts, str):
            argv += ["--input-format", "stream-json"]
        # --allowedTools is variadic and would swallow a prompt argument: the prompt is on stdin.
        argv += ["--allowedTools", *tools]
        if isinstance(prompts, str):
            done = subprocess.run(argv, input=prompts, cwd=project, env=self.env(project, **extra),
                                  capture_output=True, text=True, timeout=900)
        else:
            done = self._turns(argv, prompts, project, self.env(project, **extra))
        stream = os.path.join(self.root, "session-%d.stream" % self.count)
        with open(stream, "w") as fh:
            fh.write(done.stdout + "\n--- stderr ---\n" + done.stderr)
        sid, result, calls, order = "", "", {}, []
        for line in done.stdout.splitlines():
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "system" and msg.get("subtype") == "init":
                sid = msg.get("session_id", sid)
            if msg.get("type") == "result":
                result = (result + "\n" + str(msg.get("result") or "")).strip()
            content = msg.get("message", {}).get("content") if isinstance(msg.get("message"), dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    calls[block["id"]] = [block.get("name"), block.get("input") or {}, None, ""]
                    order.append(block["id"])
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                    text = block.get("content")
                    if isinstance(text, list):
                        text = " ".join(b.get("text", "") for b in text if isinstance(b, dict))
                    calls[block["tool_use_id"]][2] = bool(block.get("is_error"))
                    calls[block["tool_use_id"]][3] = text or ""
        if not sid:
            raise SystemExit("the session did not start: rc=%d\n%s" % (done.returncode, done.stderr[-2000:]))
        return Session(sid, [tuple(calls[i]) for i in order], result, done.returncode, stream)

    def _turns(self, argv, prompts, project, env):
        """Several turns of one process: a prompt is written only once the turn before it
        has reported its result, so none is typed over a running turn."""
        errors = os.path.join(self.root, "session-%d.stderr" % self.count)
        with open(errors, "w") as err:
            proc = subprocess.Popen(argv, cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True)
            timer = threading.Timer(900, proc.kill)
            timer.start()
            try:
                waiting = list(prompts)
                lines = []

                def send():
                    proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": waiting.pop(0)}}) + "\n")
                    proc.stdin.flush()

                send()
                for line in proc.stdout:
                    lines.append(line)
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(msg, dict) and msg.get("type") == "result":
                        if waiting:
                            send()
                        else:
                            proc.stdin.close()
                proc.wait()
            finally:
                timer.cancel()
        with open(errors) as fh:
            return subprocess.CompletedProcess(argv, proc.returncode, "".join(lines), fh.read())

    def turns(self, s):
        """The final message of each turn of a session, in order."""
        out = []
        with open(s.stream) as fh:
            for line in fh:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("type") == "result":
                    out.append(str(msg.get("result") or ""))
        return out

    def check(self, step, what, ok, detail=""):
        self.results.append(bool(ok))
        print("%s  %-8s %s%s" % ("PASS" if ok else "FAIL", step, what, ("  [" + str(detail)[:400] + "]") if detail else ""))
        sys.stdout.flush()

    def show(self, label, rows):
        """Print the event rows a step rested on, so a report can quote them."""
        for row in rows:
            slim = {k: (v if not isinstance(v, str) or len(v) <= 160 else v[:160] + "...") for k, v in row.items()
                    if k not in ("project",)}
            print("      %s %s" % (label, json.dumps(slim, ensure_ascii=False)))
        sys.stdout.flush()

    def finish(self, keep):
        ok = all(self.results) and bool(self.results)
        print("\n%d of %d checks passed; root %s" % (sum(self.results), len(self.results), self.root))
        if ok and not keep:
            shutil.rmtree(self.root)
        sys.exit(0 if ok else 1)


def arguments(doc):
    ap = argparse.ArgumentParser(description=doc)
    ap.add_argument("--model", default="haiku", help="the session's model (the judge is COMPOUND_MODEL)")
    ap.add_argument("--keep", action="store_true", help="keep the throwaway root even when everything passes")
    return ap.parse_args()
