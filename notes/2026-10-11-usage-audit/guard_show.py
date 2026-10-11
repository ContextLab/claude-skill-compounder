#!/usr/bin/env python3
"""Print the calls of one cell for reading. guard_show.py CORPUS HITS LESSON CAND CELL [N] [WIDTH]
CELL: tp | fp | miss | lost (A matches, CAND does not) | gained"""
import pickle, random, re, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
import guard_analyze as a, guard_text as g

def main():
    corpus, hits, name, cand, cell = sys.argv[1:6]
    n = int(sys.argv[6]) if len(sys.argv) > 6 else 10
    width = int(sys.argv[7]) if len(sys.argv) > 7 else 300
    rows, H, keep = a.load(corpus, hits)
    if cell in ("lost", "gained"):
        A = set(H["hits"][name]["A_raw"]) & keep; C = set(H["hits"][name][cand]) & keep
        pick = A - C if cell == "lost" else C - A
    else:
        tp, fp, miss, _ = a.cells(rows, H, keep, name, cand)
        pick = {"tp": tp, "fp": fp, "miss": miss}[cell]
    pick = sorted(pick)
    print(len(pick), "calls")
    random.seed(1)
    regs = [re.compile(p, re.M) for p in H["lessons"][name]["match"]]
    for i in (pick if len(pick) <= n else random.sample(pick, n)):
        r = rows[i]; cmd = r["command"]
        spans = []
        for rx in regs:
            m = rx.search(cmd)
            if m: spans.append((m.start(), cmd[max(0, m.start() - 60):m.end() + 60].replace("\n", "\\n")))
        k = g.classify(cmd)
        print("=== #%d %s %s %s len=%d kinds@match=%s" % (i, r["ts"][:10], r["project"][-28:], r["outcome"], len(cmd),
              ",".join(k[s] for s, _ in spans if s < len(k))))
        for _, s in spans: print("   MATCH: ..." + s[:width])
        if not spans or cell == "miss": print("   CMD: " + cmd[:width].replace("\n", "\\n"))
        sig = a.SIG.get(name)
        m = sig.search(r["result"]) if sig else None
        print("   RES: " + (r["result"][max(0, m.start() - 0):m.start() + 160] if m else r["result"][:160]).replace("\n", "\\n"))

main()
