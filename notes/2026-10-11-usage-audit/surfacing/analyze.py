#!/usr/bin/env python3
"""Tables from surfacing-runs.jsonl. usage: analyze.py [--tag main] [--model haiku]
SURFACING_DOCS_LESSON (environment): the name the docs-site lesson has in the rows; see
surfacing_experiment.py."""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = [json.loads(l) for l in open(os.path.join(os.path.dirname(HERE), "surfacing-runs.jsonl"))]
# A lesson printed inside a shell loop (`for n in a b; do compound show $n; done`) was read too:
# the driver's pattern wanted the name right after `show`. Counted here from the kept commands.
for _r in ROWS:
    if not _r["surfaced"] and any("compound show" in b and _r["lesson"] in b for b in _r["bash"]):
        _r["surfaced"] = True
        _r["via"] = ["read"]
HOME = os.path.expanduser("~")
DOCS = os.environ.get("SURFACING_DOCS_LESSON", "docs-site-lesson")
SHORT = {"end-of-turn-inflight-check": "inflight", "ci-checks-for-commit": "ci-checks", DOCS: "docs-site",
         "verify-push-with-ls-remote": "ls-remote", "kill-script-leaves-children": "kill-children"}
BODY = {}
for f in glob.glob(HOME + "/.claude/compound/lessons/*/SKILL.md") + glob.glob(HOME + "/*/.claude/compound/lessons/*/SKILL.md"):
    BODY[os.path.basename(os.path.dirname(f))] = len(open(f).read().split("\n---\n", 1)[-1])


def reuse_chars(sid):
    """The characters the reuse check added to the prompt, read from the session's transcript."""
    total = 0
    for path in glob.glob(HOME + "/.claude/projects/*/%s.jsonl" % sid):
        for line in open(path):
            if "Reuse before building" not in line:
                continue
            for m in re.finditer(r'\[compound\] Reuse before building.*?compound CLI: [^"\\]*', json.dumps(json.loads(line))):
                total = max(total, len(m.group(0).encode().decode("unicode_escape", "ignore")))
    return total


def context(r):
    seen = dict(r["other_surfaced"])
    if r["via"]:
        seen[r["lesson"]] = r["via"]
    if r["cond"] == "A":
        return reuse_chars(r["session"]) + r["read_chars"]
    if r["cond"] == "B":
        return r["listing_chars"] + sum(BODY.get(n, 0) for n, v in seen.items() if "skill" in v)
    if r["cond"] in ("C", "C2"):
        return r["listing_chars"] + r["read_chars"]
    if r["cond"] == "D":
        return r["advisory_chars"] + r["read_chars"]
    return 0


def table(rows, title):
    print("\n## %s (%d sessions, $%.2f)" % (title, len(rows), sum(r["cost"] or 0 for r in rows)))
    cells = collections.defaultdict(list)
    for r in rows:
        cells[(r["cond"], r["lesson"])].append(r)
    conds = [c for c in ("none", "A", "B", "C", "C2", "D") if any(k[0] == c for k in cells)]
    print("| lesson | " + " | ".join(conds) + " |\n|-|" + "-|" * len(conds))
    for lesson in SHORT:
        out = []
        for c in conds:
            rs = cells.get((c, lesson), [])
            out.append("%d/%d surf, %d/%d used" % (sum(r["surfaced"] for r in rs), len(rs), sum(r["followed"] for r in rs), len(rs)) if rs else "-")
        print("| %s | %s |" % (SHORT[lesson], " | ".join(out)))
    tot = []
    for c in conds:
        rs = [r for r in rows if r["cond"] == c]
        tot.append("%d/%d surf, %d/%d used" % (sum(r["surfaced"] for r in rs), len(rs), sum(r["followed"] for r in rs), len(rs)))
    print("| all | %s |" % " | ".join(tot))
    for c in conds:
        rs = [r for r in rows if r["cond"] == c]
        other = sum(1 for r in rs if r["other_surfaced"])
        ctx = [context(r) for r in rs]
        print("  %s: another lesson's text reached %d/%d sessions; added context chars mean %d (min %d, max %d); mean calls %.1f; mean s %.0f; mean $ %.4f" % (
            c, other, len(rs), sum(ctx) / max(1, len(ctx)), min(ctx or [0]), max(ctx or [0]), sum(r["calls"] for r in rs) / max(1, len(rs)),
            sum(r["seconds"] for r in rs) / max(1, len(rs)), sum(r["cost"] or 0 for r in rs) / max(1, len(rs))))


def main():
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else None
    for tag, kind, pad in (("main", "task", False), ("main", "control", False), ("pad", "task", True), ("model", "task", False), ("model", "task", True)):
        rows = [r for r in ROWS if r["tag"] == tag and r["kind"] == kind and r["pad"] == pad and (model is None or tag == "model" or r["model"] == model)]
        if rows:
            table(rows, "%s / %s%s / %s" % (tag, kind, " padded" if pad else "", ",".join(sorted(set(r["model"] for r in rows)))))
    docs = [r for r in ROWS if r["lesson"] == DOCS and r["kind"] == "task" and r["tag"] != "smoke"]
    print("\n## docs task: the page still carries `.. contents::` (the defect) at the end")
    for key in sorted(set((r["tag"], r["cond"], r["pad"], r["model"]) for r in docs)):
        rs = [r for r in docs if (r["tag"], r["cond"], r["pad"], r["model"]) == key]
        print("  %s: defect left %d/%d; checker run %d/%d" % (key, sum(bool(r.get("contents_directive_left")) for r in rs), len(rs), sum(r["followed"] for r in rs), len(rs)))
    print("\ntotal: %d sessions, $%.2f" % (len(ROWS), sum(r["cost"] or 0 for r in ROWS)))


if __name__ == "__main__":
    main()


def dose():
    """The three lessons a session does not follow unaided, by model, listing size and condition."""
    three = ("end-of-turn-inflight-check", "ci-checks-for-commit", DOCS)
    cells = collections.defaultdict(list)
    for r in ROWS:
        if r["kind"] == "task" and r["tag"] != "smoke" and r["lesson"] in three:
            cells[(r["model"], (r.get("pad_n") or 117) if r["pad"] else 0, r["cond"])].append(r)
    print("\n## three lessons not followed unaided: by model, other lessons added, condition")
    print("| model | others | cond | surfaced | used | per lesson surfaced (inflight, ci-checks, docs) | context chars mean |\n|-|-|-|-|-|-|-|")
    for key in sorted(cells):
        rs = cells[key]
        per = ", ".join("%d/%d" % (sum(r["surfaced"] for r in rs if r["lesson"] == l), sum(1 for r in rs if r["lesson"] == l)) for l in three)
        print("| %s | %d | %s | %d/%d | %d/%d | %s | %d |" % (key[0], key[1], key[2], sum(r["surfaced"] for r in rs), len(rs),
              sum(r["followed"] for r in rs), len(rs), per, sum(context(r) for r in rs) / len(rs)))
    by = collections.Counter()
    for r in ROWS:
        by[(r["tag"], r["model"])] += 1
    print("\nsessions by tag and model:", dict(by))
    print("cost by model:", {m: round(sum(r["cost"] or 0 for r in ROWS if r["model"] == m), 2) for m in set(r["model"] for r in ROWS)})


if __name__ == "__main__" and "--dose" in sys.argv:
    dose()
