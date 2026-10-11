#!/usr/bin/env python3
"""Guard study: the tables of guard-study.md that guard_analyze.py and guard_pairs.py do
not print. Usage: guard_tables.py CORPUS.pkl HITS.pkl

Read-only: the event log and the lessons are read, nothing is written."""
import collections, json, os, re, sys
import guard_analyze as a, guard_lab as L, guard_measure as M, guard_pairs as GP, guard_text as g


def first_kind(rx, text, kinds):
    m = rx.search(text)
    if not m:
        return None
    pos = m.start()
    while pos < m.end() and text[pos].isspace():
        pos += 1
    return kinds[pos] if pos < len(kinds) else "c"


def events():
    return [json.loads(l) for l in open(os.path.expanduser("~/.claude/compound/events.jsonl"))]


def t_stops(ev, less):
    print("\n## T2 recorded stops (`guard` events), by where the match begins, and the `retry` after it")
    tab = collections.Counter()
    cut = 0
    for idx, e in enumerate(ev):
        if e["type"] != "guard" or e["lesson"] not in less:
            continue
        text = e["text"]
        cut += len(text) >= 4000
        regs = [re.compile(p, re.M) for p in less[e["lesson"]]["match"]]
        kinds = g.classify(text)
        where = next((k for k in (first_kind(rx, text, kinds) for rx in regs) if k), None)
        if where is None:
            where = "beyond the 4000-character cut (the text kept begins a here-document)" if "<<" in text[:200] else "no match in kept text"
        rt = next((f for f in ev[idx + 1:idx + 40] if f["type"] == "retry" and f["session"] == e["session"]
                   and e["lesson"] in f["lessons"]), None)
        still = rt is not None and any(rx.search(rt["text"]) for rx in regs)
        tab[({"c": "command text", "h": "here-document body", "s": "single-quoted", "d": "double-quoted"}.get(where, where),
             "no retry logged" if rt is None else ("same call sent again" if rt["same"] else
                                                   ("changed, pattern still matches" if still else "changed, pattern no longer matches")))] += 1
    for k, v in sorted(tab.items()):
        print("| %s | %s | %d |" % (k[0], k[1], v))
    print("guard events: %d, texts at the 4000 cut: %d" % (sum(tab.values()), cut))


def t_recalls(ev, less):
    print("\n## T3 `recall` events of lessons that are guards: does the pattern match the failing call?")
    tab = collections.Counter()
    for e in ev:
        if e["type"] != "recall" or e["lesson"] not in less:
            continue
        call = e.get("call", "")
        regs = [re.compile(p, re.M) for p in less[e["lesson"]]["match"]]
        raw = any(rx.search(call) for rx in regs)
        prop = any(g.guard_search(rx, call) for rx in regs)
        tab[(e["lesson"], "guard had already refused once in the session" if e.get("after_guard") else "no refusal yet in the session",
             "matches" if raw else "does not match", "matches" if prop else "does not match")] += 1
    print("| lesson | when | raw | proposed | recalls |\n|-|-|-|-|-|")
    for k, v in sorted(tab.items()):
        print("| %s | %s | %s | %s | %d |" % (k + (v,)))


def t_all(rows, H, keep):
    print("\n## T4 every Bash guard: calls matched per candidate (calls that ran, real projects), and where the calls lost under P began")
    cands = ["A_raw", "B_no_heredoc", "C_no_heredoc_sq", "D_no_quotes", "E_per_simple_command", "P_proposed", "P_no_shell_aware"]
    print("| lesson | A | B | C | D | E | P | P without shell rule | lost A->P: heredoc | dq | sq | command | gained |\n" + "|-" * 13 + "|")
    total = collections.Counter()
    for n in sorted(H["hits"]):
        sets = {c: set(H["hits"][n][c]) & keep for c in cands}
        regs = [re.compile(p, re.M) for p in H["lessons"][n]["match"]]
        pos = collections.Counter()
        for i in sets["A_raw"] - sets["P_proposed"]:
            cmd = rows[i]["command"][:20000]
            kinds = g.classify(cmd)
            pos[next((k for k in (first_kind(rx, cmd, kinds) for rx in regs) if k), "?")] += 1
        for c in cands:
            total[c] += len(sets[c])
        total.update({"lost_" + k: v for k, v in pos.items()})
        total["gained"] += len(sets["P_proposed"] - sets["A_raw"])
        print("| %s | %s | %d | %d | %d | %d | %d |" % (n, " | ".join(str(len(sets[c])) for c in cands), pos["h"], pos["d"], pos["s"],
                                                      pos["c"], len(sets["P_proposed"] - sets["A_raw"])))
    print("| ALL | %s | %d | %d | %d | %d | %d |" % (" | ".join(str(total[c]) for c in cands), total["lost_h"], total["lost_d"],
                                                 total["lost_s"], total["lost_c"], total["gained"]))


def t_rewrites(rows, H, keep):
    print("\n## T6 existing and rewritten patterns, raw text (A) and proposed rule (P)")
    CS = GP.CS
    sets = [
        ("zsh-nomatch-glob", [
            ("existing", H["lessons"]["zsh-nomatch-glob"]["match"]),
            ("existing alt 1 alone: --include=*", [r"--(include|exclude)=\*"]),
            ("existing alt 3 alone: glob then 2>/dev/null", [r"(?<![\x27\"])\b[\w./-]*\*[\w./*-]*\s+2>\s*/dev/null"]),
            ("new alt alone: a URL with ?", [r"\bhttps?://[^\s'\"<>|;&)]*\?"]),
            ("REWRITE: --include/--exclude glob, URL with ?, gh api ?", GP.REWRITES["zsh-nomatch-glob"]),
            ("any * (upper bound on recall from text)", [r"\*"]),
        ]),
        ("macos-no-timeout", [
            ("existing", H["lessons"]["macos-no-timeout"]["match"]),
            ("REWRITE: the word timeout and a number", GP.REWRITES["macos-no-timeout"]),
        ]),
        ("zsh-function-name-is-alias", [
            ("existing", H["lessons"]["zsh-function-name-is-alias"]["match"]),
            ("REWRITE: only names that are aliases here (c e g h l u)", GP.REWRITES["zsh-function-name-is-alias"]),
        ]),
        ("zsh-equals-word", [
            ("existing (user lesson)", H["lessons"]["zsh-equals-word"]["match"]),
            ("existing (general lesson zsh-equals-not-found)", H["lessons"]["zsh-equals-not-found"]["match"]),
            ("a word of two or more = anywhere", [r"(?<=\s)={2,}(?=\s|$|[;&|)])"]),
        ]),
        ("sed-in-place-bsd", [("existing", H["lessons"]["sed-in-place-bsd"]["match"])]),
        ("zsh-status-path-variables", [("existing", H["lessons"]["zsh-status-path-variables"]["match"])]),
    ]
    print("| lesson | pattern | text | matched | TP | FP | precision | missed | recall |\n|-|-|-|-|-|-|-|-|-|")
    for name, pats in sets:
        for label, p in pats:
            res = L.lab(rows, keep, a.SIG[name], p)
            for key in ("A", "P"):
                tp, fp, miss = res[key]
                n = len(tp) + len(fp)
                print("| %s | %s | %s | %d | %d | %d | %s | %d | %s |" % (
                    name, label, key, n, len(tp), len(fp), "%.0f%%" % (100.0 * len(tp) / n) if n else "-", len(miss),
                    "%.0f%%" % (100.0 * len(tp) / (len(tp) + len(miss))) if tp or miss else "-"))


def t_sensitivity(rows, H, keep):
    print("\n## T5b totals over the seven signature lessons, by subset")

    def totals(subset, skip=()):
        out = {}
        for c in a.CANDS:
            tp = fp = ms = 0
            for n in a.SIG:
                if n in skip:
                    continue
                t, f, m, _ = a.cells(rows, H, subset, n, c)
                tp += len(t); fp += len(f); ms += len(m)
            out[c] = (tp, fp, ms)
        return out

    pre = set(i for i in keep if rows[i]["ts"] < "2026-10-04")
    print("| subset | candidate | matched | TP | FP | precision | missed | recall |\n|-|-|-|-|-|-|-|-|")
    for label, t in (("all", totals(keep)), ("without zsh-nomatch-glob", totals(keep, ("zsh-nomatch-glob",))),
                     ("without zsh-status-path-variables", totals(keep, ("zsh-status-path-variables",))),
                     ("without either", totals(keep, ("zsh-nomatch-glob", "zsh-status-path-variables"))),
                     ("before 2026-10-04, no guard existed (%d calls)" % len(pre), totals(pre)),
                     ("from 2026-10-04 (%d calls)" % len(keep - pre), totals(keep - pre))):
        for c, (tp, fp, ms) in t.items():
            print("| %s | %s | %d | %d | %d | %.1f%% | %d | %.1f%% |" % (label, c.split("_")[0], tp + fp, tp, fp,
                                                                     100.0 * tp / max(1, tp + fp), ms, 100.0 * tp / max(1, tp + ms)))


def t_heredocs(rows, keep):
    print("\n## T7 what receives a here-document (calls that ran, real projects)")
    recv = collections.Counter()
    op = re.compile(r"<<-?\s*['\"\\]?\w")
    shell_strings = bodies = 0
    for i in keep:
        c = rows[i]["command"][:20000]
        k = g.classify(c)
        shell_strings += bool(rows[i].get("shell_fed"))
        bodies += "h" in k
        for m in op.finditer(c):
            if k[m.start()] != "c" or c[m.start():m.start() + 3] == "<<<":
                continue
            j = max(c.rfind(x, 0, m.start()) for x in ";&|\n(")
            words = [w for w in c[j + 1:m.start()].split() if not re.match(r"^\w+=", w)]
            w = words[0].rsplit("/", 1)[-1] if words else "(none)"
            w = "python" if re.match(r"python[\d.]*$", w) or w in ("$P", "$PY", "uv") else w
            recv[w if w in ("python", "cat", "git", "bash", "sh", "zsh", "ssh", "tee", "node", "compound") else "other"] += 1
    print("calls with a here-document body: %d of %d; calls where a string or body is fed to a shell (bash -c, eval, bash <<): %d"
          % (bodies, len(keep), shell_strings))
    print(sum(recv.values()), "here-documents:", recv.most_common())


def main():
    rows, H, keep = a.load(sys.argv[1], sys.argv[2])
    less = M.lessons()
    ev = events()
    print("## T1 corpus\ncalls with a result: %d; in real projects (under the home directory): %d; of those ran (not stopped, refused, "
          "interrupted or sent to the background): %d" % (len(rows), sum(r["project"].startswith(a.HOME_KEY) for r in rows), len(keep)))
    print("outcomes, all projects:", dict(collections.Counter(r["outcome"] for r in rows)))
    print("events:", len(ev), ev[0]["ts"], ev[-1]["ts"], "guard lessons for Bash:", len(less))
    t_stops(ev, less)
    t_recalls(ev, less)
    t_all(rows, H, keep)
    t_sensitivity(rows, H, keep)
    t_rewrites(rows, H, keep)
    t_heredocs(rows, keep)


if __name__ == "__main__":
    main()
