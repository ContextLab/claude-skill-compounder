#!/usr/bin/env python3
"""Guard study, step 2: every guard pattern against every Bash call of the corpus, under
each candidate text. Usage: guard_measure.py CORPUS.pkl OUT.pkl

Reads the lessons (read-only) from ~/.claude/compound/lessons, ~/*/.claude/compound/lessons
and this repository's lessons/. Writes, for each lesson and candidate, the indexes of the
calls it matches, and for each call what happened to it."""
import glob, json, os, pickle, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guard_text as g  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
CAP = 20000  # CHECK_TEXT_CAP in bin/compound


def lessons():
    out = {}
    paths = (glob.glob(os.path.expanduser("~/.claude/compound/lessons/*/SKILL.md"))
             + glob.glob(os.path.expanduser("~/*/.claude/compound/lessons/*/SKILL.md"))
             + glob.glob(os.path.join(REPO, "lessons/*/SKILL.md")))
    for path in paths:
        head = open(path).read().split("\n---", 1)[0]
        fields = dict(line.split(": ", 1) for line in head.split("\n") if ": " in line)
        if "match" not in fields or "match-tools" in fields:
            continue
        out[fields["name"]] = {"path": path, "match": json.loads(fields["match"]),
                               "shell": fields.get("shell"), "platform": fields.get("platform"),
                               "created": fields.get("created"), "updated": fields.get("updated")}
    return out


CANDIDATES = ["A_raw", "B_no_heredoc", "C_no_heredoc_sq", "D_no_quotes", "E_per_simple_command",
              "P_proposed", "P_no_shell_aware", "B_no_shell_aware"]


def texts(command):
    command = command[:CAP]
    kinds = g.classify(command)
    view, view_kinds = g.guard_view(command, kinds)
    g.SHELL_AWARE = False
    plain = g.classify(command)
    plain_view, plain_kinds = g.guard_view(command, plain)
    g.SHELL_AWARE = True
    return {"A_raw": command,
            "B_no_heredoc": g.view(command, kinds, "h"),
            "C_no_heredoc_sq": g.view(command, kinds, "hs"),
            "D_no_quotes": g.view(command, kinds, "hsd"),
            "E_per_simple_command": g.simple_commands(command, kinds),
            "P_proposed": (view, view_kinds),
            "P_no_shell_aware": (plain_view, plain_kinds),
            "B_no_shell_aware": g.view(command, plain, "h")}, kinds


def hit(regexes, candidate, text):
    for rx in regexes:
        if candidate == "E_per_simple_command":
            if any(rx.search(part) for part in text):
                return True
        elif candidate.startswith("P_"):
            if any(g.starts_in_command(m, text[1]) for m in rx.finditer(text[0])):
                return True
        elif rx.search(text):
            return True
    return False


STOPPED = re.compile(r"\[compound\] This call was stopped before it ran")
REFUSED = re.compile(r"^(?:<tool_use_error>|Permission to use Bash|The user doesn't want to proceed|"
                     r"Claude requested permissions|This command requires approval|\[Request interrupted)")


def outcome(row):
    r = row["result"]
    if STOPPED.search(r[:400]):
        return "stopped"
    if row["is_error"] and REFUSED.search(r) and not r.startswith("Exit code"):
        return "refused"
    return "error" if row["is_error"] else "ok"


def main(corpus, out):
    rows = pickle.load(open(corpus, "rb"))
    less = lessons()
    compiled = {name: [re.compile(p, re.MULTILINE) for p in item["match"]] for name, item in less.items()}
    hits = {name: {c: [] for c in CANDIDATES} for name in less}
    kinds_count = {k: 0 for k in "csdh#"}
    began = time.time()
    feat = {"heredoc": 0, "heredoc_shell": 0, "shell_string": 0, "calls": len(rows), "over_cap": 0}
    for index, row in enumerate(rows):
        command = row["command"]
        feat["over_cap"] += len(command) > CAP
        t, kinds = texts(command)
        for k in set(kinds):
            kinds_count[k] += kinds.count(k)
        g.SHELL_AWARE = False
        plain = g.classify(command[:CAP])
        g.SHELL_AWARE = True
        feat["heredoc"] += "h" in plain
        if plain != kinds:
            # the shell-aware scan placed something differently: a body or a string fed to a shell
            feat["heredoc_shell" if plain.count("h") != kinds.count("h") else "shell_string"] += 1
            row["shell_fed"] = True
        row["outcome"] = outcome(row)
        for name, regexes in compiled.items():
            for c in CANDIDATES:
                if hit(regexes, c, t[c]):
                    hits[name][c].append(index)
    pickle.dump({"hits": hits, "lessons": less, "features": feat, "kinds": kinds_count}, open(out, "wb"))
    pickle.dump(rows, open(corpus, "wb"))
    print("seconds", round(time.time() - began, 1), feat, kinds_count)
    print("%-36s" % "lesson" + "".join("%8s" % c.split("_")[0] for c in CANDIDATES[:6]) + "   P0   B0")
    for name in sorted(hits):
        print("%-36s" % name + "".join("%8d" % len(hits[name][c]) for c in CANDIDATES))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
