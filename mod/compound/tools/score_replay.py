#!/usr/bin/env python3
"""Score a replay: the judge's verdicts against the labels on the same pairs.

usage: score_replay.py LABELLED.jsonl.results.jsonl

A pair labelled "unsure" is left out. LESSON and KNOWN both count as "the judge saw a
lesson"; NONE and UNANSWERED as "it did not".
"""
import json
import sys

rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
scored = [r for r in rows if r["label"] in ("yes", "no")]
saw = lambda r: r["verdict"] in ("LESSON", "KNOWN")
tp = sum(1 for r in scored if r["label"] == "yes" and saw(r))
fn = sum(1 for r in scored if r["label"] == "yes" and not saw(r))
fp = sum(1 for r in scored if r["label"] == "no" and saw(r))
tn = sum(1 for r in scored if r["label"] == "no" and not saw(r))
print("pairs scored %d (unsure left out: %d, unanswered: %d)" % (
    len(scored), len(rows) - len(scored), sum(1 for r in rows if r["verdict"] == "UNANSWERED")))
print("real lessons found   %d of %d" % (tp, tp + fn))
print("false lessons        %d of %d" % (fp, fp + tn))
for r in scored:
    if r["label"] == "no" and saw(r):
        print("  FALSE  %s  %s" % (r["id"], (r.get("lesson") or r.get("id"))[:150]))
    if r["label"] == "yes" and not saw(r):
        print("  MISSED %s  %s" % (r["id"], r.get("reason", "")[:150]))
