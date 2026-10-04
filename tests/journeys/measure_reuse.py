#!/usr/bin/env python3
"""How noisy the reuse check is. Real `claude -p` sessions; run by hand. A measurement, not a test.

A store of nine lessons, a prompt log with earlier requests (some like a request below,
most not), and fourteen ordinary prompts of which five are covered by a lesson (two of
those by an earlier request as well). Three of the uncovered ones ask only to RUN a named
command and report its output, with a lesson or an earlier request about that very command
in reach: running something that exists is not a build task, so nothing is added. For each
prompt it prints what the mod added and what the judge was asked, and at the end: how many
prompts got an injection, how many injections were relevant, how many covered prompts got
nothing, the confusion counts, and the milliseconds the judge took. The first prompt is
then sent once more: its verdict is in the memo, so no model is asked for it again.

usage: measure_reuse.py [--model haiku] [--keep]
"""
import common

OTHERS = [
    ("zsh-equals-word", "Use when a zsh command line has a bare word starting with = (a ===== separator after ;).",
     "zsh expands a bare word starting with = as a command lookup. Quote it or use printf.\n"),
    ("docker-compose-v2", "Use when a command runs docker-compose with a hyphen and fails with command not found.",
     "Compose v2 is a plugin: run `docker compose`, with a space.\n"),
    ("pytest-tmp-path", "Use when a pytest test writes into the working directory and leaves files behind.",
     "Take the tmp_path fixture and write there.\n"),
    ("latex-undefined-citations", "Use when a LaTeX build reports undefined citations after the bibliography changed.",
     "Run pdflatex, bibtex, then pdflatex twice. Grep the last pass of the log only.\n"),
    ("git-rev-parse-origin", "Use when git rev-parse origin/<branch> fails with 'Needed a single revision' after a push.",
     "The remote-tracking ref was never fetched. Verify a push with git ls-remote origin <branch>.\n"),
    ("brew-doctor-exit", "Use when a compound shell command ends in brew doctor and reports failure.",
     "brew doctor exits 1 on any warning. Run it as its own call.\n"),
    ("build-needs-profile", "Use when ./build.sh fails with 'a profile is required'.",
     "Run ./build.sh --profile dev. A bare ./build.sh fails with 'error: a profile is required'.\n"),
]
BUILT = [
    ("release-tagging", "Use when cutting, tagging or publishing a release of this project.",
     "Run scripts/release.sh <version>. It tags the release, updates the changelog and pushes the tag.\n"),
    ("csv-dedupe", "Use when removing duplicate rows from a CSV export.",
     "scripts/dedupe_csv.py <file> --key <column> keeps the first row per key and writes <file>.deduped.csv.\n"),
]
# (session, prompt) rows of the prompt log; the first two are like a request below.
LOG = [
    ("older-1", "write a release script that tags the version, updates the changelog and pushes the tag"),
    ("older-2", "write a python script to remove duplicate rows from the customers csv export keyed on email"),
    ("older-3", "centre the login button on the settings page"),
    ("older-4", "why is the docker image for the web app so large"),
    ("older-5", "write unit tests for the payment handlers"),
    ("older-6", "write a script that resizes the photos in the directory to thumbnails"),
    ("older-7", "update the README with install instructions for the project"),
    ("older-8", "run ./run_tests.sh and tell me which tests failed"),
]
# (covered by, prompt). `None` is a prompt nothing in the store or the log covers.
PROMPTS = [
    ("docker", "Write a Makefile target for this project that brings the stack up with docker-compose up -d and then "
               "waits until the database accepts connections."),
    ("pytest", "Write pytest tests for the exporter module. Each test writes its output files, so make sure they go "
               "to a temporary directory and nothing is left behind in the working directory."),
    ("latex", "Write a build script for the paper that runs the LaTeX build and exits non-zero when the log reports "
              "undefined citations after the bibliography changed."),
] + [
    ("release", "Please write a shell script for this project that tags a new release, updates the changelog and "
                "pushes the tag to the remote."),
    (None, "Add a dark mode toggle to the settings page of the web app and remember the user's choice in local storage."),
    (None, "Write a function that parses ISO 8601 durations like PT1H30M into a number of seconds, with unit tests for "
           "the edge cases."),
    ("csv", "I need a Python script that removes the duplicate rows from our orders CSV export, keeping the first row "
            "for each order id."),
    (None, "Refactor the user service so that the database queries go through a repository class instead of being "
           "inlined in the handlers."),
    (None, "Can you explain how the retry logic in the HTTP client works and whether it backs off exponentially "
           "between attempts?"),
    (None, "Set up a GitHub Actions workflow that runs the linter and the unit tests on every pull request to the "
           "main branch."),
    (None, "Write a script that walks the photos directory and renames every image file by the date in its EXIF data."),
    # Running a named command and reporting its output: not a build task, whatever is in reach.
    (None, common.BUILD_TASK),
    (None, "Run the test suite with ./run_tests.sh and tell me how many tests failed and which ones. Do not change any "
           "file, only report what it prints."),
    (None, "Please execute scripts/release.sh --dry-run 2.0.0 for me and paste the last ten lines of its output here."),
]
RIGHT = {"release": ({"release-tagging"}, {"older-1:1"}), "csv": ({"csv-dedupe"}, {"older-2:1"}),
         "docker": ({"docker-compose-v2"}, set()), "pytest": ({"pytest-tmp-path"}, set()),
         "latex": ({"latex-undefined-citations"}, set())}


def main():
    args = common.arguments(__doc__)
    w = common.World("measure")
    project = w.project("alpha", build=True)
    for name, when, body in OTHERS + BUILT:
        w.add(project, name, when, body)
    for session, prompt in LOG:
        w.seed_prompt("/Users/someone/older-project", session, prompt)

    injected = relevant = missed = 0
    # Per prompt: was something right added (tp), something wrong (fp), nothing where
    # something covers it (fn), nothing where nothing does (tn).
    confusion = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    took = []
    judged = []
    for covered, prompt in PROMPTS:
        # One model turn: what is measured happens before the model reads the prompt.
        s = w.session(project, prompt, args.model, flags=("--max-turns", "1"))
        rows = w.events(project, session=s.sid, kind="reuse")
        errors = w.events(project, session=s.sid, kind="error")
        asked = [e for e in w.events(project, session=s.sid, kind="judge") if e.get("moment") == "reuse"]
        judged += [e.get("ms", 0) for e in asked if not e.get("memo")]
        named = set(rows[0].get("lessons", [])) | set(rows[0].get("prompts", [])) if rows else set()
        right = RIGHT[covered][0] | RIGHT[covered][1] if covered else set()
        verdict = "nothing added"
        if rows:
            injected += 1
            took.append(rows[0].get("ms", 0))
            if named and named <= right:
                relevant += 1
                verdict = "relevant"
            elif named & right:
                verdict = "mixed: %s" % ", ".join(sorted(named - right))
            else:
                verdict = "IRRELEVANT"
        if covered and not (named & right):
            missed += 1
            verdict += " (MISSED)"
        if named - right:
            confusion["fp"] += 1
        elif covered:
            confusion["tp" if named & right else "fn"] += 1
        else:
            confusion["tn"] += 1
        how = ", ".join("%s%s %sms" % (e.get("verdict"), " unquoted=%d" % e["unquoted"] if e.get("unquoted") else "",
                                       e.get("ms")) for e in asked) or "no model asked"
        print("%-8s %-14s %s%s\n         judge: %s\n         %s" % (
            covered or "-", verdict, sorted(named) or "", "  errors: %s" % errors if errors else "", how, prompt[:100]))
    print("\n%d prompts, %d covered. Injections: %d. Wholly relevant: %d. Covered prompts missed: %d. "
          "Check time when it injected, ms: %s" % (len(PROMPTS), sum(1 for c, _ in PROMPTS if c), injected, relevant, missed, took))
    print("Per prompt: right thing added %(tp)d, a wrong thing added %(fp)d, covered and nothing added %(fn)d, "
          "uncovered and nothing added %(tn)d." % confusion)
    print("Judge calls: %d of %d prompts. ms each: %s. median %s" % (
        len(judged), len(PROMPTS), judged, sorted(judged)[len(judged) // 2] if judged else "-"))

    # The same prompt, project and store again: the verdict comes from the memo.
    covered, prompt = PROMPTS[0]
    s = w.session(project, prompt, args.model, flags=("--max-turns", "1"))
    again = [e for e in w.events(project, session=s.sid, kind="judge") if e.get("moment") == "reuse"]
    rows = w.events(project, session=s.sid, kind="reuse")
    print("Repeated %r: judge events %s; added %s" % (
        prompt[:40], [(e.get("verdict"), e.get("ms"), bool(e.get("memo"))) for e in again],
        sorted(set(rows[0].get("lessons", [])) | set(rows[0].get("prompts", []))) if rows else "nothing"))
    w.check("memo", "a repeated prompt asked no model", bool(again) and all(e.get("memo") for e in again), again)
    w.check("ran", "every session started", True)
    w.finish(args.keep)


if __name__ == "__main__":
    main()
