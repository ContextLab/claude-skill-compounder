#!/usr/bin/env python3
"""Guard study, step 3: precision and recall per lesson per candidate text.

Usage: guard_analyze.py CORPUS.pkl HITS.pkl [--all-projects]

A call counts when it ran (it was not stopped by a guard, refused a permission or
interrupted). True positive: the pattern matches and the result shows the lesson's own
error. False positive: it matches and the result does not. Miss: the result shows the
error and the pattern does not match. Only lessons whose failure prints a recognisable
error have a signature; the others are judged by reading (see guard-study.md)."""
import os, pickle, re, sys

# how Claude Code names a project directory under the home directory
HOME_KEY = re.sub(r"[^A-Za-z0-9]", "-", os.path.expanduser("~"))

PRE = r"(?m)^(?:\(eval\):\d+: |zsh:(?:\d+:)? |bash: (?:line \d+: )?|sh: (?:\d+: )?)"
SIG = {
    "zsh-nomatch-glob": PRE + r"no matches found",
    "zsh-equals-word": PRE + r"=\S* not found",
    "zsh-equals-not-found": PRE + r"=\S* not found",
    "zsh-status-path-variables": PRE + r"read-only variable: status",
    "macos-no-timeout": PRE + r"command not found: timeout",
    "zsh-function-name-is-alias": PRE + r"(?:defining function based on alias|parse error near `\(\)')",
    # sed quotes the start of its script, and with -i that is the file name and a newline
    "sed-in-place-bsd": r"(?m)^sed: \d+: \"[^\"]{0,60}\"?: (?:invalid command code|undefined label|unterminated substitute"
                        r"|expects \\ followed by text|extra characters at the end|unescaped newline inside)",
}
SIG = {k: re.compile(v) for k, v in SIG.items()}
CANDS = ["A_raw", "B_no_heredoc", "C_no_heredoc_sq", "D_no_quotes", "E_per_simple_command", "P_proposed"]


def load(corpus, hits, every=False):
    rows = pickle.load(open(corpus, "rb"))
    H = pickle.load(open(hits, "rb"))
    keep = set(i for i, r in enumerate(rows)
               if (every or r["project"].startswith(HOME_KEY)) and r["outcome"] in ("ok", "error")
               # a call sent to the background shows its output in a later call, not here
               and not r["result"].startswith("Command running in background"))
    return rows, H, keep


def cells(rows, H, keep, name, cand):
    sig = SIG[name]
    failing = set(i for i in keep if sig.search(rows[i]["result"]))
    matched = set(H["hits"][name][cand]) & keep
    return matched & failing, matched - failing, failing - matched, failing


def main():
    every = "--all-projects" in sys.argv
    rows, H, keep = load(sys.argv[1], sys.argv[2], every)
    print("calls that ran: %d" % len(keep))
    print("| lesson | failures in corpus | candidate | matched | TP | FP | precision | missed | recall |")
    print("|-|-|-|-|-|-|-|-|-|")
    total = {c: [0, 0, 0] for c in CANDS}
    for name in sorted(SIG):
        for cand in CANDS:
            tp, fp, miss, failing = cells(rows, H, keep, name, cand)
            n = len(tp) + len(fp)
            total[cand][0] += len(tp); total[cand][1] += len(fp); total[cand][2] += len(miss)
            print("| %s | %d | %s | %d | %d | %d | %s | %d | %s |" % (
                name, len(failing), cand.split("_")[0], n, len(tp), len(fp),
                "%.0f%%" % (100.0 * len(tp) / n) if n else "-", len(miss),
                "%.0f%%" % (100.0 * len(tp) / len(failing)) if failing else "-"))
    print()
    for cand in CANDS:
        tp, fp, miss = total[cand]
        print("ALL  %-22s matched %4d TP %4d FP %4d precision %.1f%% missed %4d recall %.1f%%" % (
            cand, tp + fp, tp, fp, 100.0 * tp / (tp + fp), miss, 100.0 * tp / (tp + miss)))


if __name__ == "__main__":
    main()
