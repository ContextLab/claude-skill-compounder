#!/usr/bin/env python3
"""Builds the six shipped lessons of the general pool with the real CLI.

Each lesson is added at the user level of a throwaway store (never ~/.claude), and the
file that goes into `lessons/` is the `skill_md` of `compound promote <name> --to general
--json`: the text a pull request to the pool would carry (the lesson without its origin).

    python3 notes/2026-10-04-audit/general-pool/build_shipped.py          # writes lessons/
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CLI = os.path.join(REPO, "bin", "compound")

# The anchor the learn skill teaches for "a command starts here".
A = r"(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)"
# Where an assignment starts. Narrower than A on purpose: a single `&` and a `(` are left
# out, because `curl 'https://h/x?path=1&status=2'` and `python3 -c "open(path='x')"` are
# ordinary calls; `{ ` is added for a function body.
ASSIGN = r"(^\s*|(?:;|&&|\|\|)\s*|\b(?:do|then|else)\s+|\{\s+)"

LESSONS = [
    {
        "name": "zsh-no-matches-found",
        "when": 'Use when a command fails in zsh with "no matches found:" (an unquoted glob or bracket that matched no file: rm -f build/*.o, grep --include=*.py, pip install pkg[extra], a URL with "?").',
        "shell": ["zsh"],
    },
    {
        "name": "zsh-equals-not-found",
        "when": 'Use when a command fails in zsh with "==== not found" or "=word not found" (a bare word starting with "=", such as echo ===== printed as a separator).',
        "shell": ["zsh"],
        "match": [A + r"echo\s+(-[neE]+\s+)?={2,}(\s|$|[;&|)])"],
    },
    {
        "name": "zsh-status-path-variables",
        "when": 'Use when a command fails in zsh with "read-only variable: status", or when ls, git and other ordinary commands fail with "command not found" after a variable named path was assigned.',
        "shell": ["zsh"],
        "match": [
            ASSIGN + r"((local|export|typeset|readonly|declare)\s+)?(status|path)=",
            A + r"for\s+(status|path)\s+in\b",
            r"(^\s*|[;&|(]\s*|\b(?:do|then|else|while|until)\s+)(IFS=\S*\s+)?read\s+(-\w+\s+)*(status|path)\b",
        ],
    },
    {
        "name": "sed-in-place-bsd",
        "when": 'Use when sed -i fails on macOS or BSD with an error that quotes the file name ("invalid command code", "undefined label", "unterminated substitute pattern", "expects \\ followed by text", "extra characters at the end of"), or leaves a stray file ending in -e.',
        "platform": ["darwin"],
        "match": [
            r"(?:(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)|\b(?:xargs|exec|sudo)\s(?:[^;&|\n]*?\s)?)"
            r"sed\s+(-[A-Za-hj-z]+\s+)*-[A-Za-hj-z]*i\s+(-[A-Za-z]+\s+)*['\"]?(s[/|#,@:]|\d|/|\$)",
        ],
    },
    {
        "name": "pip-externally-managed",
        "when": 'Use when pip install fails with "error: externally-managed-environment" (PEP 668: the Python of Homebrew, Debian, Ubuntu or Fedora).',
    },
    {
        "name": "macos-gnu-only-commands",
        "when": 'Use when a command fails on macOS with "command not found: timeout", "date: illegal option -- d", "grep: invalid option -- P", "stat: illegal option -- c", or another GNU-only command or flag.',
        "platform": ["darwin"],
        "match": [A + r"timeout\s+(-\S+\s+)*\d"],
    },
]


def main():
    box = tempfile.mkdtemp(prefix="compound-pool-")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("COMPOUND_") and key != "CLAUDE_CODE_SESSION_ID"}
    env.update(COMPOUND_HOME=os.path.join(box, "home"), COMPOUND_CLAUDE_DIR=os.path.join(box, "claude"),
               COMPOUND_PROJECT=os.path.join(box, "proj"))
    os.makedirs(env["COMPOUND_PROJECT"])
    # The names must be free: the build reads this checkout's pool, so it is emptied first.
    for lesson in LESSONS:
        shutil.rmtree(os.path.join(REPO, "lessons", lesson["name"]), ignore_errors=True)

    def run(*args):
        proc = subprocess.run([sys.executable, CLI] + list(args), cwd=env["COMPOUND_PROJECT"], env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=120)
        if proc.returncode != 0:
            raise SystemExit("compound %s exited %d: %s" % (" ".join(args[:3]), proc.returncode, proc.stderr))
        return proc.stdout

    texts = {}
    for lesson in LESSONS:
        args = ["add", "--level", "user", "--name", lesson["name"], "--when", lesson["when"],
                "--body-file", os.path.join(HERE, "bodies", lesson["name"] + ".md")]
        for key in ("platform", "shell", "match"):
            for value in lesson.get(key, []):
                args += ["--" + key, value]
        print(run(*args).strip())
        texts[lesson["name"]] = json.loads(run("promote", lesson["name"], "--to", "general", "--json"))["skill_md"]
    for name, text in texts.items():
        target = os.path.join(REPO, "lessons", name)
        os.makedirs(target)
        with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write(text)
    shutil.rmtree(box, ignore_errors=True)
    print("wrote %d lessons to %s" % (len(texts), os.path.join(REPO, "lessons")))


if __name__ == "__main__":
    main()
