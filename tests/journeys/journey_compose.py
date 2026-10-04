#!/usr/bin/env python3
"""The two shipped skills that call other skills, and a used skill being seen. Real
`claude -p` sessions on small real projects; run by hand.

  finish    a project with an uncommitted change that fails a test, a stale README and a
            check script whose plain invocation fails. Told only that the change is done
            and to finish the task (and not to read the check script, only to invoke it),
            the session invokes compound:finish-task and follows
            it: the code is fixed and the test is not touched, every check passes at the
            end, the README no longer says what the change made false, the work is
            committed and nothing is pushed. The failed check invocation that was fixed
            is settled as a lesson (compound:learn) or declined.
  quiet     a question about the same project: finish-task is not invoked, nothing is
            committed.
  verify    a large build whose brief states two things about the input file that are
            false. The session invokes compound:verify-assumptions-first, which calls
            compound:reuse, reads the real file before it writes anything, says which
            assumption was false, runs the first thing it writes before it writes the
            next, and what it builds reads the real file.
  small     a one-line fix in the same project: verify-assumptions-first is not invoked.
  made      a lesson made a skill with `compound skill` is invoked through the Skill tool
            and as a typed `/name`: one `use` event each, at the project level.
  seen      across all of it: a `use` event for each of the two pool skills that ran, none
            for compound:learn or compound:reuse, and no `error` event.

  --baseline runs `finish` and `verify` against a copy of the package without the two
  skills and prints what the session did, with no checks: what the skills are for.

usage: journey_compose.py [--model sonnet] [--keep] [--baseline] [--only STEP]
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess

import common

TEXTUTIL = '''import re


def slugify(text):
    """Lowercase, with every run of other characters turned into one dash."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower())
'''

# The uncommitted change: it strips the dashes, and it lost `.lower()` on the way.
TEXTUTIL_CHANGED = '''import re


def slugify(text):
    """Lowercase, with every run of other characters turned into one dash, and no dash at either end."""
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")
'''

TESTS = '''import unittest

from textutil import slugify


class SlugifyTest(unittest.TestCase):
    def test_words_are_joined_by_one_dash(self):
        self.assertEqual(slugify("Hello World"), "hello-world")
        self.assertEqual(slugify("a  b"), "a-b")
%s

if __name__ == "__main__":
    unittest.main()
'''

NEW_TEST = '''
    def test_no_dash_at_either_end(self):
        self.assertEqual(slugify("!Hi there!"), "hi-there")
'''

README = """# textutil

`slugify(text)` lowercases the text and turns every run of other characters into one dash.
Punctuation at either end becomes a dash too: `slugify("!Hi there!")` is `-hi-there-`.

## Checks

    python3 -m unittest
    ./check.sh
"""

CHECK_SH = """#!/bin/sh
# Lints the project. There is no default: name the files, or say --all.
if [ "$#" -eq 0 ]; then
  echo "check.sh: error: nothing to check; name files or pass --all, e.g. ./check.sh --all" >&2
  exit 2
fi
[ "$1" = "--all" ] && set -- *.py
for file in "$@"; do
  python3 -m py_compile "$file" || exit 1
  if awk 'length > 100 { found = 1 } END { exit !found }' "$file"; then
    echo "check.sh: $file has a line longer than 100 characters" >&2
    exit 1
  fi
done
echo "check ok ($# files)"
"""

# The check script may be invoked and not read: its plain invocation fails, which is the
# failed-then-corrected command the routine's `compound:learn` step is for.
FINISH = ("The slugify change in the working tree is done, I think. Finish the task. One rule: check.sh is vendored, "
          "so do not read, print or edit it; only invoke it.")
QUIET = "What does slugify('A  B') return in this project as it is now? Answer in one line and change nothing."

# One object per line, `ts` in epoch seconds: not what the brief says.
EVENTS = [(1788220800 + day * 86400 + n * 600, user, kind)
          for day in range(3) for n, (user, kind) in enumerate((("ana", "open"), ("ben", "open"), ("ana", "close")))]
VERIFY = ("This is a big job: build the whole reporting pipeline for this project. data/events.json is one JSON array "
          "of objects, each with an ISO-format `timestamp`, a `user` and a `kind`. Write a shared loader module and a "
          "script per report that writes a CSV under reports/: events per day, events per user, and events per kind "
          "per day. Add tests for all of it. Do not ask me anything; go ahead.")
SMALL = "Fix the typo in README.md: 'pipline' should be 'pipeline'. Nothing else."

MADE = "Use the Skill tool to invoke the skill deploy-region, then tell me in one line what it says to run."


def git(cwd, *args):
    done = subprocess.run(["git", "-c", "user.name=Journey", "-c", "user.email=journey@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                          cwd=cwd, capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise SystemExit("git %s: %s" % (" ".join(args), done.stderr))
    return done.stdout


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    if mode:
        os.chmod(path, mode)


def finish_project(w, name):
    project = w.project(name)
    write(os.path.join(project, "textutil.py"), TEXTUTIL)
    write(os.path.join(project, "test_textutil.py"), TESTS % "")
    write(os.path.join(project, "README.md"), README)
    write(os.path.join(project, "check.sh"), CHECK_SH, 0o755)
    write(os.path.join(project, ".gitignore"), "__pycache__/\n.claude/\n")
    git(project, "init", "-q")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "textutil: slugify")
    write(os.path.join(project, "textutil.py"), TEXTUTIL_CHANGED)
    write(os.path.join(project, "test_textutil.py"), TESTS % NEW_TEST)
    return project


def verify_project(w, name):
    project = w.project(name)
    write(os.path.join(project, "data", "events.json"),
          "".join(json.dumps({"ts": ts, "user": user, "kind": kind}) + "\n" for ts, user, kind in EVENTS))
    write(os.path.join(project, "README.md"), "# reports\n\nThe reporting pipline for the event export in data/.\n")
    git(project, "init", "-q")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "the export")
    return project


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def bash_writes(command, suffix):
    """Whether a Bash command writes a file whose name ends in `suffix`: a redirection into
    it, `tee`, `sed -i`, or a script that opens it for writing. A commit that names the
    file writes nothing."""
    if re.match(r"\s*git\s", command) or "compound add" in command:
        return False
    name = r"[\w./-]*" + re.escape(suffix)
    return bool(re.search(r">\s*%s\b|tee\s+(-a\s+)?%s\b|sed\s+-i[^;|&]*%s\b" % (name, name, name), command)
                or (re.search(name, command) and re.search(r"open\([^)]*['\"]w|write_text\(", command)))


def texts_before(s, call):
    """[(index of the next tool call, text)] for each message the session wrote before its
    `call`-th tool call."""
    out, seen = [], 0
    with open(s.stream) as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            content = msg.get("message", {}).get("content") if isinstance(msg, dict) and isinstance(msg.get("message"), dict) else None
            if not isinstance(content, list) or msg.get("type") != "assistant":
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    seen += 1
                elif isinstance(block, dict) and block.get("type") == "text" and seen <= call:
                    out.append((seen, block.get("text", "")))
    return out


def skills_invoked(s):
    return [str(c[1].get("skill", "")) for c in s.calls if c[0] == "Skill"]


def run(cwd, *argv):
    return subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, timeout=120)


def without_the_two(w):
    target = os.path.join(w.root, "no-compose")
    shutil.copytree(common.PLUGIN, target, ignore=shutil.ignore_patterns(".git", "notes", "docs", "tests", "dev", "__pycache__"))
    for name in ("finish-task", "verify-assumptions-first"):
        shutil.rmtree(os.path.join(target, "skills", name), ignore_errors=True)
    return target


def describe(s, project):
    print("      skills invoked: %s" % (skills_invoked(s) or "none"))
    for c in s.calls:
        text = c[1].get("command") or c[1].get("file_path") or json.dumps(c[1])[:120]
        print("      %-6s %s%s" % (c[0], str(text).replace("\n", " ")[:150], "  -> error" if c[2] else ""))
    print("      final: %s" % s.result[-600:].replace("\n", " "))
    print("      git log: %s" % git(project, "log", "--oneline").strip().replace("\n", " | "))


TOOLS = ("Bash", "Skill", "Read", "Edit", "Write")
DENIED = ("Grep", "Glob")


def step_finish(w, model, plugin=None):
    project = finish_project(w, "finish-baseline" if plugin else "finish")
    before = digest(os.path.join(project, "test_textutil.py"))
    s = w.session(project, FINISH, model, tools=TOOLS, denied=DENIED, plugin=plugin, COMPOUND_PROMPT_MIN_CHARS="100000")
    describe(s, project)
    if plugin:
        tests = run(project, "python3", "-m", "unittest")
        print("      BASELINE: tests %s; test file %s; README %s; commits %s; pushed %s" % (
            "pass" if tests.returncode == 0 else "FAIL",
            "unchanged" if digest(os.path.join(project, "test_textutil.py")) == before else "CHANGED",
            "still says -hi-there-" if "-hi-there-" in open(os.path.join(project, "README.md")).read() else "updated",
            git(project, "rev-list", "--count", "HEAD").strip(),
            any("git push" in c[0] for c in s.bash())))
        return s, project
    invoked = skills_invoked(s)
    w.check("finish", "told only to finish the task, the session invoked compound:finish-task",
            any(name.endswith("finish-task") for name in invoked), invoked)
    w.check("finish", "the test file is what it was: no test was weakened",
            digest(os.path.join(project, "test_textutil.py")) == before)
    tests = run(project, "python3", "-m", "unittest")
    w.check("finish", "the tests pass now", tests.returncode == 0, tests.stderr[-300:])
    lint = run(project, "./check.sh", "--all")
    w.check("finish", "and so does the other check", lint.returncode == 0, lint.stderr[-200:])
    ran = s.bash()
    w.check("finish", "the session ran both checks itself, and each succeeded at least once",
            any("unittest" in c[0] and not c[1] for c in ran) and any("check.sh" in c[0] and not c[1] for c in ran),
            " | ".join("%s -> %s" % (c[0][:50], "error" if c[1] else "ok") for c in ran if "unittest" in c[0] or "check.sh" in c[0]))
    # Every check again after the last change to the code: the last write to textutil.py is
    # followed by a passing run of each.
    order = [(n, c) for n, c in enumerate(s.calls)]
    last_edit = max([n for n, c in order if (c[0] in ("Edit", "Write") and "textutil.py" in str(c[1].get("file_path", ""))
                                             and "test_" not in str(c[1].get("file_path", "")))
                     or (c[0] == "Bash" and bash_writes(c[1].get("command", ""), "textutil.py"))] or [-1])
    # A call that changes the code and runs the checks behind the change counts as after it.
    after = [c for n, c in order if n >= last_edit and c[0] == "Bash" and c[2] is False]
    w.check("finish", "after its last change to the code it ran every check again",
            any("unittest" in c[1].get("command", "") for c in after) and any("check.sh" in c[1].get("command", "") for c in after),
            "last edit at call %d of %d" % (last_edit, len(s.calls)))
    committed = git(project, "show", "HEAD:textutil.py")
    w.check("finish", "the fix is committed: the code lowercases again and still strips the dashes",
            ".lower()" in committed and "strip(" in committed and int(git(project, "rev-list", "--count", "HEAD")) >= 2, committed[-200:])
    readme = git(project, "show", "HEAD:README.md")
    w.check("finish", "the README no longer says what the change made false", "`-hi-there-`" not in readme, readme[:300])
    status = git(project, "status", "--porcelain")
    w.check("finish", "nothing tracked is left uncommitted", not [l for l in status.splitlines() if not l.startswith("??")], status)
    w.check("finish", "nothing was pushed and no pull request was opened",
            not any(mark in c[0] for c in ran for mark in ("git push", "gh pr", "gh release")),
            [c[0][:80] for c in ran if "push" in c[0] or "gh " in c[0]])
    events = w.events(project, session=s.sid)
    w.show("event", [e for e in events if e["type"] not in ("judge",)])
    captures = [e for e in events if e["type"] == "capture"]
    settled = [e for e in events if e["type"] in ("learn", "skip")]
    print("      captures %d, settled by %s; compound:learn invoked: %s" % (
        len(captures), [e["type"] for e in settled] or "nothing", any(n.endswith("learn") for n in invoked)))
    failed_first = any("check.sh" in c[0] and c[1] for c in ran)
    w.check("finish", "a check invocation that failed and was fixed was settled as a lesson or declined",
            (not captures) or len(settled) >= len(captures),
            "check.sh failed first: %s; captures %d; settled %d" % (failed_first, len(captures), len(settled)))
    return s, project


def step_quiet(w, model, project):
    commits = git(project, "rev-list", "--count", "HEAD").strip()
    s = w.session(project, QUIET, model, tools=TOOLS, denied=DENIED, COMPOUND_PROMPT_MIN_CHARS="100000")
    invoked = skills_invoked(s)
    w.check("quiet", "a question did not invoke finish-task", not any(n.endswith("finish-task") for n in invoked), invoked)
    w.check("quiet", "and committed nothing", git(project, "rev-list", "--count", "HEAD").strip() == commits)
    return s


def step_verify(w, model, plugin=None):
    project = verify_project(w, "verify-baseline" if plugin else "verify")
    s = w.session(project, VERIFY, model, tools=TOOLS, denied=DENIED, plugin=plugin, COMPOUND_PROMPT_MIN_CHARS="100000")
    describe(s, project)
    # A call that writes a Python file is a write; any other call that names the export read it.
    writes = [n for n, c in enumerate(s.calls) if c[0] in ("Write", "Edit") or (
        c[0] == "Bash" and bash_writes(c[1].get("command", ""), ".py"))]
    reads = [n for n, c in enumerate(s.calls) if n not in writes and c[0] in ("Read", "Bash") and "events.json" in json.dumps(c[1])]
    said = s.result.lower()
    told = ("ts" in said and any(word in said for word in ("epoch", "json lines", "jsonl", "one object per line", "ndjson",
                                                           "newline-delimited", "not an array", "not a json array",
                                                           "unix")))
    csvs = glob.glob(os.path.join(project, "reports", "*.csv"))
    dated = [path for path in csvs if "2026-09-0" in open(path).read()]
    if plugin:
        print("      BASELINE: read the real file before writing: %s (first read %s, first write %s); said the "
              "assumption was false: %s; reports with real dates: %d of %d" % (
                  bool(reads) and (not writes or reads[0] < writes[0]), reads[:1], writes[:1], told, len(dated), len(csvs)))
        return s, project
    invoked = skills_invoked(s)
    w.check("verify", "given a large build, the session invoked compound:verify-assumptions-first",
            any(n.endswith("verify-assumptions-first") for n in invoked), invoked)
    w.check("verify", "which called compound:reuse (the Skill tool, or `compound find`)",
            any(n.endswith("reuse") for n in invoked) or any("compound" in c[0] and " find" in c[0] for c in s.bash()), invoked)
    w.check("verify", "it read the real file before it wrote anything",
            bool(reads) and (not writes or reads[0] < writes[0]), "first read %s, first write %s" % (reads[:1], writes[:1]))
    w.check("verify", "it said which assumption was false: one object per line, `ts` in epoch seconds", told, s.result[-500:])
    w.check("verify", "what it built reads the real file: a report holds the real days", bool(dated),
            "%d csv files, %d with a 2026-09 date" % (len(csvs), len(dated)))
    # The smallest thing first: what the first writing call wrote was run, in that call or
    # in one before the next writing call, and the rest was written afterwards.
    first = s.calls[writes[0]] if writes else None
    ran_in_it = bool(first) and first[0] == "Bash" and bool(
        re.search(r"(?:^|\n|&&|;)\s*(?:python3?|pytest|\./)\S*[^\n]*$", first[1].get("command", "").rstrip()))
    ran_between = len(writes) >= 2 and any(c[0] == "Bash" and n not in writes for n, c in enumerate(s.calls)
                                           if writes[0] < n < writes[1])
    w.check("verify", "it ran the first thing it wrote before it wrote the rest", len(writes) >= 2 and (ran_in_it or ran_between),
            "writes at calls %s of %d; ran in the first writing call: %s" % (writes[:4], len(s.calls), ran_in_it))
    # What it said before it wrote anything: the assumptions, stated.
    stated = [t for n, t in texts_before(s, writes[0] if writes else len(s.calls)) if "assum" in t.lower()]
    print("      it stated its assumptions in a message before writing: %s" % bool(stated))
    print("      it went on to compound:finish-task: %s" % any(n.endswith("finish-task") for n in invoked))
    return s, project


def step_small(w, model, project):
    s = w.session(project, SMALL, model, tools=TOOLS, denied=DENIED, COMPOUND_PROMPT_MIN_CHARS="100000")
    invoked = skills_invoked(s)
    w.check("small", "a one-line fix did not invoke verify-assumptions-first",
            not any(n.endswith("verify-assumptions-first") for n in invoked), invoked)
    w.check("small", "and the typo is fixed", "pipline" not in open(os.path.join(project, "README.md")).read())
    return s


def step_made(w, model):
    project = w.project("made")
    w.add(project, "deploy-region", "Use when deploying this project.", "Run ./deploy.sh --region us-east-1.\n")
    done = w.cli(project, "skill", "deploy-region")
    if done.returncode != 0:
        raise SystemExit("could not make the skill: %s" % done.stderr)
    s = w.session(project, MADE, model, tools=("Bash", "Skill"), COMPOUND_PROMPT_MIN_CHARS="100000")
    uses = w.events(project, session=s.sid, kind="use")
    w.show("use", uses)
    w.check("made", "the session invoked the skill made from a lesson", "deploy-region" in skills_invoked(s), skills_invoked(s))
    w.check("made", "and one use event names it, at the project level",
            [(e.get("lesson"), e.get("level")) for e in uses] == [("deploy-region", "project")], uses)
    s2 = w.session(project, "/deploy-region", model, tools=("Bash", "Skill"), COMPOUND_PROMPT_MIN_CHARS="100000")
    uses = w.events(project, session=s2.sid, kind="use")
    w.show("use", uses)
    w.check("made", "typed as /deploy-region it is counted too, once",
            [(e.get("lesson"), e.get("level")) for e in uses] == [("deploy-region", "project")], uses)
    row = [r for r in w.items(project) if r["name"] == "deploy-region"]
    w.check("made", "the skill's counter says two uses", bool(row) and row[0]["counts"].get("use") == 2, row[0]["counts"] if row else "")
    # The totals are of the whole log, which the other steps of a full run wrote to as well.
    status = w.cli(project, "status").stdout
    total = len(w.events(project, kind="use"))
    w.check("made", "and `compound status` totals the uses in the log", "%d skills used" % total in status and total >= 2,
            status.split("Compound interest")[1][:200] if "Compound interest" in status else status[:200])
    return [s, s2], project


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="sonnet", help="the session's model (the judge is COMPOUND_MODEL)")
    ap.add_argument("--keep", action="store_true", help="keep the throwaway root even when everything passes")
    ap.add_argument("--baseline", action="store_true", help="run finish and verify without the two skills; no checks")
    ap.add_argument("--only", choices=("finish", "verify", "made"), help="run one group of steps")
    args = ap.parse_args()
    w = common.World("compose")
    if args.baseline:
        bare = without_the_two(w)
        if args.only in (None, "finish"):
            step_finish(w, args.model, plugin=bare)
        if args.only in (None, "verify"):
            step_verify(w, args.model, plugin=bare)
        print("\nbaseline only; root %s" % w.root)
        return
    seen = []
    if args.only in (None, "finish"):
        s, project = step_finish(w, args.model)
        seen.append((project, s, "finish-task"))
        seen.append((project, step_quiet(w, args.model, project), None))
    if args.only in (None, "verify"):
        s, project = step_verify(w, args.model)
        seen.append((project, s, "verify-assumptions-first"))
        # A project of its own: the large build may have fixed the typo on its way.
        small = verify_project(w, "small")
        seen.append((small, step_small(w, args.model, small), None))
    if args.only in (None, "made"):
        sessions, project = step_made(w, args.model)
        seen.extend((project, s, None) for s in sessions)
    for project, s, skill in seen:
        events = w.events(project, session=s.sid)
        used = [e.get("lesson") for e in events if e["type"] == "use"]
        if skill and any(n.endswith(skill) for n in skills_invoked(s)):
            w.check("seen", "a use event was written for %s, at the general level" % skill,
                    any(e.get("lesson") == skill and e.get("level") == "general" for e in events if e["type"] == "use"), used)
        w.check("seen", "no use event counts compound:learn or compound:reuse (session %s)" % s.sid[:8],
                not any(name in ("learn", "reuse") for name in used), used)
        errors = [e for e in events if e["type"] == "error"]
        w.check("seen", "and nothing in the mod failed", errors == [], errors)
    w.finish(args.keep)


if __name__ == "__main__":
    main()
