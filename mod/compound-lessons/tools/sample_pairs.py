#!/usr/bin/env python3
"""Sample stored fail/recover pairs for labelling.

Reads the repeat store hooks/repeat-gate.sh writes (archive and live index), joins each
recover row to its fail row on the signature, and writes N pairs to OUT as JSON lines.
The rows carry commands from every project on the machine, so OUT belongs in the state
directory and never in a repository.

usage: sample_pairs.py OUT [N] [SEED] [LABELLED]

With LABELLED, a file an earlier run wrote and someone labelled, the same pairs are
re-extracted by id, in that order, with their labels carried over. The store grows, so
a seed alone does not reproduce a sample.
"""
import glob
import json
import os
import random
import sys

state = os.environ.get("SKILL_COMPOUNDER_STATE", os.path.expanduser("~/.claude/skill-compounder"))
out = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20261003

rows = []
for path in sorted(glob.glob(os.path.join(state, "repeats", "archive", "*.jsonl"))) + [
    os.path.join(state, "repeats", "index.jsonl")
]:
    with open(path) as fh:
        rows += [json.loads(line) for line in fh if line.strip()]

fails = {}
for r in rows:
    if r.get("t") == "fail":
        fails.setdefault(r["sig"], r)

pairs, seen = [], set()
for r in rows:
    if r.get("t") == "recover" and r["sig"] in fails and r["sig"] not in seen:
        seen.add(r["sig"])
        f = fails[r["sig"]]
        pairs.append({
            "id": r["sig"],
            "tool": f.get("tool"),
            "failed": f.get("cmd", "")[:6000],
            "error": (f.get("err") or f.get("ec") or "")[:4000],
            "worked": r.get("cmd", "")[:6000],
            "worked_tool": r.get("tool"),
            "agent": bool(r.get("agent_id")),
        })

if len(sys.argv) > 4:
    by_id = {p["id"]: p for p in pairs}
    sample = []
    for line in open(sys.argv[4]):
        was = json.loads(line)
        p = by_id[was["id"]]
        p.update({k: was[k] for k in ("label", "gist") if k in was})
        sample.append(p)
else:
    random.seed(seed)
    random.shuffle(pairs)
    sample = pairs[:n]
with open(out, "w") as fh:
    fh.writelines(json.dumps(p) + "\n" for p in sample)

print(len(pairs), "pairs; sampled", len(sample))
for i, p in enumerate(sample):
    tag = " agent" if p["agent"] else ""
    print("\n#%d [%s->%s%s]" % (i, p["tool"], p["worked_tool"], tag))
    print("F:", p["failed"][:330])
    print("E:", p["error"][:230])
    print("W:", p["worked"][:330])
