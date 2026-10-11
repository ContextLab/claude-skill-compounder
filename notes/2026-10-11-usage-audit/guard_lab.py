#!/usr/bin/env python3
"""Try patterns for one lesson against the corpus. Used as a module by the study:
lab(rows, keep, sig, patterns) -> {"A": (tp, fp, miss), "P": (tp, fp, miss)} as sets.
A is the raw command (today); P is guard_text.guard_search (proposed)."""
import os, pickle, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_text as g

_cache = {}


def prepared(rows, i):
    if i not in _cache:
        command = rows[i]["command"][:20000]
        _cache[i] = (command,) + g.guard_view(command)
    return _cache[i]


def lab(rows, keep, sig, patterns, only=("A", "P")):
    regs = [re.compile(p, re.MULTILINE) for p in patterns]
    failing = set(i for i in keep if sig.search(rows[i]["result"]))
    out = {}
    hitA, hitP = set(), set()
    for i in keep:
        raw, text, kinds = prepared(rows, i)
        if "A" in only and any(rx.search(raw) for rx in regs):
            hitA.add(i)
        if "P" in only and any(g.starts_in_command(m, kinds) for rx in regs for m in rx.finditer(text)):
            hitP.add(i)
    for key, hit in (("A", hitA), ("P", hitP)):
        if key in only:
            out[key] = (hit & failing, hit - failing, failing - hit)
    return out


def line(label, res):
    parts = []
    for key, (tp, fp, miss) in res.items():
        n = len(tp) + len(fp)
        parts.append("%s: matched %d TP %d FP %d prec %s missed %d recall %s" % (
            key, n, len(tp), len(fp), "%.0f%%" % (100.0 * len(tp) / n) if n else "-", len(miss),
            "%.0f%%" % (100.0 * len(tp) / (len(tp) + len(miss))) if tp or miss else "-"))
    print("%-34s %s" % (label, " | ".join(parts)))
