#!/usr/bin/env python3
"""How the fix judge rules on pairs of calls. Real model calls; run by hand. A measurement, not a test.

After a failed call that no lesson describes, each later success of the same tool is put to
a model: is this success the fix of that failure, and is it worth a lesson? This script puts
that question for real, many times, about pairs whose answer is known, and prints the counts.

The question is the mod's own: `fix_probe/` is a plugin of one hook that builds the prompt
with `hooks/judge.ts` (`fixPrompt`), sends it through `$.model.complete` with the request
the mod sends, and reads the reply with `parseFix`. The lessons the judge is shown are the
general pool's, as `compound list` prints them in a throwaway store.

The pairs. FIX is the wanted answer for the first three, KNOWN for the fourth, NONE for the rest:

  interpreter   `import tomllib` fails under python3 (3.9), the same script runs under python3.12
  module        the same failure, and the script runs with `tomli` in its place
  program       `docker-compose` is not found, `docker compose` works
  shipped       `grep -P` fails on macOS, `grep -E` works: the pool's macos-gnu-only-commands covers it
  unrelated     the tomllib failure, then `ls -la`
  diagnostic    the tomllib failure, then a look at which interpreters there are
  other-task    the tomllib failure, then a python call that does another job
  flake         a download times out, and the very same call sent again works, nothing between
  flake-after   the same, with an unrelated `ls` and a look at the working tree between the two
  work-bug      a test fails on an assert, the code is edited, the tests are run again and pass
  search        a grep finds nothing, and a wider grep finds it
  own-module    a script fails on an import of the project's own module, the script is edited, and the same call works

And one whose call is the same text both times, where what ran between is the fix (FIX wanted):

  installed     `jq` is not found, `brew install jq` runs, and the very same call works

`flake` is never put to the judge by the mod: a held failure whose call passes when sent
again unchanged, with no call between the two, is dropped without a question
(`bareRetry` in hooks/render.ts). It is asked here to see what the prompt alone says.

usage: measure_fix.py [--model haiku] [--runs 10] [--negative-runs 3] [--only NAME,NAME] [--hooks DIR] [--keep]

One run is one session, and the answers of one run agree with each other more than the
answers of two runs do: a pair that is accepted ten times of ten in one run has been
accepted two times of ten in the next. Run it several times before believing a count.

--hooks names another directory to take judge.ts, safe.ts and store.ts from (an older
commit's, exported with `git archive`), so two prompts can be measured the same way.
"""
import argparse
import json
import os
import shutil
import subprocess

import common

TOMLLIB = ("python3 -c \"\nimport tomllib, json\nwith open('config.toml','rb') as f:\n    d = tomllib.load(f)\n"
           "with open('config.json','w') as f:\n    json.dump(d, f, indent=2, default=str)\n\" && cat config.json")
# The error text as the demo sessions logged it (their `capture` events).
NO_MODULE = ("Exit code 1\nTraceback (most recent call last):\n  File \"<string>\", line 2, in <module>\n"
             "ModuleNotFoundError: No module named 'tomllib'")
PYTEST = "python3 -m pytest tests/test_orders.py -q"
ASSERT = ("Exit code 1\nF.                                                                       [100%]\n"
          "=================================== FAILURES ===================================\n"
          "_______________________________ test_order_total _______________________________\n\n"
          "    def test_order_total():\n>       assert order_total([2, 3]) == 5\nE       assert 6 == 5\n"
          "E        +  where 6 = order_total([2, 3])\n\ntests/test_orders.py:5: AssertionError\n"
          "=========================== short test summary info ============================\n"
          "FAILED tests/test_orders.py::test_order_total - assert 6 == 5\n1 failed, 1 passed in 0.03s")
CURL = "curl -fsS --max-time 10 https://registry.npmjs.org/left-pad/latest | head -c 200"
TIMED_OUT = "Exit code 28\ncurl: (28) Operation timed out after 10002 milliseconds with 0 bytes received"
JQ = "jq -r '.version' package.json"

# (name, wanted verdict, failed call, its error, later successful call, the calls between the two)
CASES = [
    ("interpreter", "FIX", TOMLLIB, NO_MODULE, TOMLLIB.replace("python3 -c", "/opt/homebrew/bin/python3.12 -c", 1), []),
    ("module", "FIX", TOMLLIB, NO_MODULE, TOMLLIB.replace("tomllib", "tomli"), []),
    ("program", "FIX", "docker-compose up -d db", "Exit code 127\n(eval):1: command not found: docker-compose", "docker compose up -d db", []),
    ("shipped", "KNOWN", "grep -P '\\d+ms' build.log | head -5",
     "Exit code 2\ngrep: invalid option -- P\nusage: grep [-abcdDEFGHhIiJLlMmnOopqRSsUVvwXxZz] [-A num] [-B num] [-C[num]]\n"
     "\t[-e pattern] [-f file] [--binary-files=value] [--color=when]", "grep -E '[0-9]+ms' build.log | head -5", []),
    ("installed", "FIX", JQ, "Exit code 127\n(eval):1: command not found: jq", JQ, ["Bash: brew install jq"]),
    ("unrelated", "NONE", TOMLLIB, NO_MODULE, "ls -la", []),
    ("diagnostic", "NONE", TOMLLIB, NO_MODULE, "python3 --version; which -a python3 python3.11 python3.12 python3.13 2>/dev/null", []),
    ("other-task", "NONE", TOMLLIB, NO_MODULE, "python3 -m json.tool package.json > /dev/null && echo 'package.json is valid'", []),
    ("flake", "NONE", CURL, TIMED_OUT, CURL, []),
    ("flake-after", "NONE", CURL, TIMED_OUT, CURL, ["Bash: ls -la", "Bash: git status --short"]),
    ("work-bug", "NONE", PYTEST, ASSERT, PYTEST + " -x", ["Edit: src/orders.py"]),
    ("search", "NONE", "grep -rn 'def load_config' src/", "Exit code 1", "grep -rn 'load_config' .", []),
    ("own-module", "NONE", "python3 scripts/report.py --week 40",
     "Exit code 1\nTraceback (most recent call last):\n  File \"scripts/report.py\", line 3, in <module>\n    from helpers import weekly\n"
     "ModuleNotFoundError: No module named 'helpers'", "python3 scripts/report.py --week 40",
     ["Edit: {\"file_path\":\"scripts/report.py\",\"old_string\":\"from helpers import weekly\",\"new_string\":\"from scripts.helpers import weekly\"}"]),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="haiku", help="the judge's model")
    ap.add_argument("--runs", type=int, default=10, help="how often each FIX or KNOWN pair is asked")
    ap.add_argument("--negative-runs", type=int, default=3, help="how often each NONE pair is asked")
    ap.add_argument("--hooks", default=os.path.join(common.REPO, "hooks"), help="where judge.ts, safe.ts and store.ts are taken from")
    ap.add_argument("--timeout-ms", type=int, default=10000, help="the judge's time limit, as COMPOUND_JUDGE_TIMEOUT")
    ap.add_argument("--only", default="", help="the pairs to ask, by name, with commas between; all of them without it")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    only = [name for name in args.only.split(",") if name]
    unknown = [name for name in only if name not in [case[0] for case in CASES]]
    if unknown:
        raise SystemExit("no such pair: %s" % ", ".join(unknown))
    cases = [case for case in CASES if not only or case[0] in only]

    w = common.World("fix")
    project = w.project("empty")
    probe = os.path.join(w.root, "probe")
    shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fix_probe"), probe)
    for name in ("judge.ts", "safe.ts", "store.ts"):
        shutil.copy(os.path.join(args.hooks, name), os.path.join(probe, "hooks", name))
    # The probe imports the mod's files where they are in the repository; here they are beside it.
    hook = os.path.join(probe, "hooks", "probe.ts")
    with open(hook) as fh:
        text = fh.read()
    with open(hook, "w") as fh:
        fh.write(text.replace("'../../../../hooks/", "'./"))
    work = os.path.join(w.root, "asks")
    os.makedirs(work)
    listing = w.cli(project, "list", "--scripts", "--json")
    if listing.returncode != 0:
        raise SystemExit("compound list failed: %s" % listing.stderr)
    with open(os.path.join(work, "lessons.json"), "w") as fh:
        fh.write(listing.stdout)
    asks = []
    for name, wanted, failed, error, worked, between in cases:
        for run in range(args.negative_runs if wanted == "NONE" else args.runs):
            asks.append({"id": "%s#%d" % (name, run + 1), "failed": failed, "error": error, "worked": worked, "between": between})
    with open(os.path.join(work, "asks.json"), "w") as fh:
        json.dump({"model": args.model, "timeoutMs": args.timeout_ms, "asks": asks}, fh)

    # One headless session whose only job is to fire the probe's prompt hook. The mod itself is not loaded.
    argv = ["claude", "-p", "--model", "haiku", "--setting-sources", "project", "--plugin-dir", probe, "--max-turns", "1",
            "--disallowed-tools", "Bash,Read,Write,Edit,Grep,Glob"]
    done = subprocess.run(argv, input="Reply with the one word: done", cwd=project, capture_output=True, text=True, timeout=1800,
                          env=w.env(project, COMPOUND_FIX_PROBE=work, COMPOUND_OFF="1"))
    replies = os.path.join(work, "replies.json")
    if not os.path.isfile(replies):
        raise SystemExit("the probe wrote nothing: rc=%d\n%s\n%s" % (done.returncode, done.stdout[-1000:], done.stderr[-2000:]))
    with open(replies) as fh:
        told = json.load(fh)
    if "problem" in told:
        raise SystemExit("the probe failed: %s" % told["problem"])
    rows = told["rows"]
    print("judge %s, %d questions, lessons shown: %s" % (args.model, len(rows), ", ".join(told["lessons"]) or "(none)"))
    print("prompt from %s\n" % args.hooks)
    counts = {"FIX": [0, 0], "KNOWN": [0, 0], "NONE": [0, 0]}
    for name, wanted, _failed, _error, _worked, _between in cases:
        mine = [r for r in rows if r["id"].split("#")[0] == name]
        verdicts = {}
        for r in mine:
            verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        right = verdicts.get(wanted, 0)
        counts[wanted][0] += right
        counts[wanted][1] += len(mine)
        print("%-12s wanted %-4s  right %2d of %2d   %s" % (name, wanted, right, len(mine), json.dumps(verdicts, sort_keys=True)))
        reasons = sorted({r.get("reason", "") for r in mine if r["verdict"] != wanted and r.get("reason")})
        for reason in reasons[:4]:
            print("             wrong: %s" % reason[:160])
        if wanted == "NONE":
            for r in [r for r in mine if r["verdict"] != "NONE"][:2]:
                print("             said:  %s" % str(r.get("text", ""))[:300].replace("\n", " "))
    took = sorted(r["ms"] for r in rows)
    late = [r for r in rows if r["verdict"] == "unanswered"]
    print("\na fix accepted:      %d of %d" % tuple(counts["FIX"]))
    print("a known one named:   %d of %d" % tuple(counts["KNOWN"]))
    print("a non-fix rejected:  %d of %d" % tuple(counts["NONE"]))
    print("judge ms: median %d, max %d; unanswered %d of %d (limit %d ms)" % (
        took[len(took) // 2], took[-1], len(late), len(rows), args.timeout_ms))
    print("root %s" % w.root)
    if not args.keep:
        shutil.rmtree(w.root)


if __name__ == "__main__":
    main()
