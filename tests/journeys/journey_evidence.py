#!/usr/bin/env python3
"""A script that ran, and a call checked against the files. Real `claude -p` sessions; run by hand.

  keep      the session writes a script outside any repository and runs it on two inputs,
            and is told the script will be needed again. The CLI holds a copy of the
            script as it ran, with both runs. The stop is refused once, with the script
            named (`refuse`, why `evidence`), and the session records it (or declines
            it: either settles it). A lesson recorded from it holds the bytes that ran,
            and says so.
  probe     in zsh, a call with a glob that matches no file is refused before it runs by
            the shipped lesson's probe, with the word at fault named; the same mistake
            written a new way is refused again.

usage: journey_evidence.py [--model haiku] [--keep]
"""
import json
import os

import common


def main():
    args = common.arguments(__doc__)
    w = common.World("evidence")

    # ---- keep
    project = w.project("alpha")
    for name, text in (("first.txt", "one two three\n"), ("second.txt", "one two three four five\n")):
        with open(os.path.join(project, name), "w") as fh:
            fh.write(text)
    script = os.path.join(w.tmp, "wordcount.py")
    prompt = ("Write a small Python script at %s that prints the number of words in the file named by its first "
              "command-line argument. Then run it once on first.txt and once on second.txt, each as its own Bash "
              "call of the form: python3 %s <file>. Tell me the two counts. I will need this script again in other "
              "projects: if you are asked to record it or decline it, record it." % (script, script))
    s = w.session(project, prompt, args.model, tools=("Bash", "Write"), COMPOUND_PROMPT_MIN_CHARS="100000")
    runs = [c for c in s.bash() if c[0].lstrip().startswith("python3") and "wordcount.py" in c[0]]
    w.check("keep", "the session ran the script at least twice", len([c for c in runs if c[1] is False]) >= 2,
            [c[0][:80] for c in s.bash()])
    listed = json.loads(w.cli(project, "evidence", "list", "--json").stdout or "[]")
    rows = [row for row in listed if row.get("name") == "wordcount.py"]
    w.check("keep", "the CLI holds the script, with its passing runs", bool(rows) and rows[0]["ok"] >= 2, rows[:1])
    w.check("keep", "the runs were given different arguments, and the script is outside a repository",
            bool(rows) and rows[0]["varied"] is True and rows[0]["in_repo"] is False, rows[:1])
    refusals = [e for e in w.events(project, session=s.sid, kind="refuse") if e.get("why") == "evidence"]
    w.show("refuse", refusals)
    w.check("keep", "the stop was refused once for the script", len(refusals) == 1
            and bool(rows) and rows[0]["id"] in (refusals[0].get("evidence") or []), refusals)
    w.check("keep", "the claim is on record", any(c.startswith("evidence-") for c in w.claims(s.sid)), w.claims(s.sid))
    learned = [e for e in w.events(project, session=s.sid, kind="learn") if e.get("evidence")]
    declined = [e for e in w.events(project, session=s.sid, kind="skip") if e.get("evidence")]
    w.show("learn", learned)
    w.show("skip", declined)
    w.check("keep", "the session recorded the script or declined it", len(learned) + len(declined) == 1,
            "%d recorded, %d declined" % (len(learned), len(declined)))
    if learned:
        directory = learned[0]["path"]
        shown = json.loads(w.cli(project, "evidence", "show", learned[0]["evidence"][0], "--json").stdout)
        kept = os.path.join(directory, "wordcount.py")
        same = os.path.isfile(kept) and open(kept).read() == shown["text"]
        w.check("keep", "the lesson holds the bytes that ran", same, directory)
        proof = json.load(open(os.path.join(directory, ".evidence.json")))
        w.check("keep", "and says which run they are", proof["attachments"][0]["id"] == learned[0]["evidence"][0]
                and "wordcount.py" in proof["attachments"][0]["command"], proof["attachments"][:1])
        after = [row for row in json.loads(w.cli(project, "evidence", "list", "--due", "--json").stdout)]
        w.check("keep", "nothing is owed any more", after == [], after)
    w.check("keep", "no error was logged", w.events(project, session=s.sid, kind="error") == [],
            w.events(project, session=s.sid, kind="error"))

    # ---- probe
    beta = w.project("beta")
    with open(os.path.join(beta, "notes.txt"), "w") as fh:
        fh.write("x\n")
    prompt = ("Run exactly this Bash command first, unchanged: ls *.journeyabsent\n"
              "If the call is refused, read the reason and do not send it again. "
              "Then run exactly this one, unchanged: wc -l *.journeymissing\n"
              "If that is refused too, do not send it again. Then run: ls *.txt\nTell me what happened to each.")
    s = w.session(beta, prompt, args.model, COMPOUND_PROMPT_MIN_CHARS="100000", COMPOUND_SHELL="zsh")
    guards = w.events(beta, session=s.sid, kind="guard")
    w.show("guard", guards)
    first = [c for c in s.bash() if "journeyabsent" in c[0]]
    second = [c for c in s.bash() if "journeymissing" in c[0]]
    w.check("probe", "the call with a glob that matches nothing was refused before it ran, the word named",
            bool(first) and first[0][1] is True and "cannot run as it is written" in first[0][2]
            and "*.journeyabsent" in first[0][2], first[0][2][:300] if first else "no such call")
    w.check("probe", "the same mistake written a new way was refused again",
            bool(second) and second[0][1] is True and "*.journeymissing" in second[0][2],
            second[0][2][:300] if second else "no such call")
    w.check("probe", "a glob that matches ran", any("*.txt" in c[0] and c[1] is False for c in s.bash()),
            [(c[0][:40], c[1]) for c in s.bash()])
    w.check("probe", "two guard events, both the shipped lesson's",
            [e.get("lesson") for e in guards] == ["zsh-no-matches-found"] * 2, [e.get("lesson") for e in guards])
    w.finish(args.keep)


if __name__ == "__main__":
    main()
