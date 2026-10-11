#!/usr/bin/env python3
"""Guard study, the validation rule: "a pattern must match the failing calls recorded for
its lesson and must not match the recorded working calls", tried on the pairs the
transcripts hold. A pair is a call whose result shows the lesson's error and the next
Bash call of the same transcript that ran without it (the fix, or simply the next step).

Usage: guard_pairs.py CORPUS.pkl HITS.pkl"""
import collections, re, sys
import guard_analyze as a, guard_lab as L, guard_text as g

CS = r"(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)"
REWRITES = {
    "zsh-nomatch-glob": [r"--(include|exclude)=[^\s'\"]*[*?\[]", r"\bhttps?://[^\s'\"<>|;&)]*\?",
                         r"gh api [^\s'\"]*\?"],
    "macos-no-timeout": [r"(?<![\w=./-])timeout\s+(?:-\w+\s+\S+\s+)*\d"],
    "zsh-function-name-is-alias": [CS + r"(?:c|e|g|h|l|u)\s*\(\)"],
}


def pairs(rows, keep, sig):
    by_file = collections.defaultdict(list)
    for i in sorted(keep):
        by_file[rows[i]["file"]].append(i)
    out = []
    for seq in by_file.values():
        for a_, b_ in zip(seq, seq[1:]):
            if sig.search(rows[a_]["result"]) and not sig.search(rows[b_]["result"]):
                out.append((a_, b_))
    return out


def hits(patterns, command):
    regs = [re.compile(p, re.MULTILINE) for p in patterns]
    command = command[:20000]
    return (any(rx.search(command) for rx in regs), any(g.guard_search(rx, command) for rx in regs))


def main():
    rows, H, keep = a.load(sys.argv[1], sys.argv[2])
    print("| lesson | pattern | pairs | failing call matched (raw / proposed) | next working call matched (raw / proposed) | "
          "both: failing matched and working not (raw / proposed) |")
    print("|-|-|-|-|-|-|")
    for name in sorted(a.SIG):
        ps = pairs(rows, keep, a.SIG[name])
        for label, pats in (("existing", H["lessons"][name]["match"]), ("rewritten", REWRITES.get(name))):
            if not pats or not ps:
                continue
            fa = fp = wa = wp = ba = bp = 0
            for x, y in ps:
                f, w = hits(pats, rows[x]["command"]), hits(pats, rows[y]["command"])
                fa += f[0]; fp += f[1]; wa += w[0]; wp += w[1]
                ba += f[0] and not w[0]; bp += f[1] and not w[1]
            print("| %s | %s | %d | %d / %d | %d / %d | %d / %d |" % (name, label, len(ps), fa, fp, wa, wp, ba, bp))


if __name__ == "__main__":
    main()
