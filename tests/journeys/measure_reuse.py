#!/usr/bin/env python3
"""How noisy the reuse check is. Real `claude -p` sessions; run by hand. A measurement, not a test.

A store of eight lessons (six about other things, two that cover a request below), a
prompt log with earlier requests (some like a request below, most not), and eight ordinary
prompts of which two are covered. For each prompt it prints what the mod added, and at the
end: how many prompts got an injection, how many injections were relevant, and how many
covered prompts got nothing.

usage: measure_reuse.py [--model haiku] [--keep]
"""
import common

UNRELATED = [
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
]
RELEVANT = [
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
]
# (covered by, prompt). `None` is a prompt nothing in the store or the log covers.
PROMPTS = [
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
]
RIGHT = {"release": ({"release-tagging"}, {"older-1:1"}), "csv": ({"csv-dedupe"}, {"older-2:1"})}


def main():
    args = common.arguments(__doc__)
    w = common.World("measure")
    project = w.project("alpha")
    for name, when, body in UNRELATED + RELEVANT:
        w.add(project, name, when, body)
    for session, prompt in LOG:
        w.seed_prompt("/Users/someone/older-project", session, prompt)

    injected = relevant = missed = 0
    took = []
    for covered, prompt in PROMPTS:
        # One model turn: what is measured happens before the model reads the prompt.
        s = w.session(project, prompt, args.model, flags=("--max-turns", "1"))
        rows = w.events(project, session=s.sid, kind="reuse")
        errors = w.events(project, session=s.sid, kind="error")
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
        print("%-8s %-14s %s%s\n         %s" % (covered or "-", verdict, sorted(named) or "", "  errors: %s" % errors if errors else "",
                                               prompt[:100]))
    print("\n%d prompts, %d covered. Injections: %d. Wholly relevant: %d. Covered prompts missed: %d. "
          "Check time when it injected, ms: %s" % (len(PROMPTS), sum(1 for c, _ in PROMPTS if c), injected, relevant, missed, took))
    w.check("ran", "every session started", True)
    w.finish(args.keep)


if __name__ == "__main__":
    main()
