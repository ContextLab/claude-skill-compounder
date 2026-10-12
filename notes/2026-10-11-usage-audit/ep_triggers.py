"""The trigger rules the study proposes, run over every transcript, with what they would cost.

Usage: python3 ep_triggers.py
Rules (each is computed from calls the mod already sees; none reads prose):
  T1 tool-or-machine failure, new signature   a failed call whose error names the machine, the shell, a tool or the
                                              harness (T1CLASS, matched on the error line itself), then a pass of the same tool
                                              within six calls; kept only the FIRST time its signature is met (later meetings
                                              are recalls, not debts)
  T2 several approaches                       three or more failed calls of one tool inside twelve calls, two or more
                                              different texts, then a pass; at least one failure is not a check's own red
  T3 differential red                         (a) a hosted check (gh run view / gh pr checks / gh run watch) reports a
                                              failure after this session saw a local test runner pass, or
                                              (b) a check goes red then green with no file edited in between, the passing
                                              call is not the failing one word for word or an install/config call ran
                                              between, at most 15 events apart, and neither call is a deliberate baseline
  T4 the user said so                         /compound:learn typed by the user
  T5 a helper written a second time           a script whose text overlaps (Jaccard >= 0.30 on 3-token shingles) a script that
                                              another agent or session already ran three or more times; once per helper
Not rules: RG (red, edits, green), DX (prose names a cause), keyword-matched corrections, any script run three times.
EP_BASELINE_EXTRA (environment, optional): comma-separated regular expressions naming a project's own
baseline copies (for example `attempt\d\.py`), added to BASELINE."""
import json, re, collections, datetime
from ep_common import *
from ep_detect import check_key, cmd, nohere, is_edit, ENVCHG, HARNESS, ENVERR
from ep_recurrence import signature

BASELINE = re.compile(r"git\s+show\s+\S+:\S+\s*>|git\s+stash|git\s+checkout\s+\S+\s+--|\.bak\b|MUTAT|mutat|\.before\b|\.orig\b" + ''.join('|' + x for x in env_list('EP_BASELINE_EXTRA')))
TRANSIENT = re.compile(r"auto mode classifier gave no verdict|\[compound\]|doesn't want to proceed|was rejected|Request interrupted|InputValidationError|String to replace not found|File has not been read|modified since read")
T1CLASS = re.compile(r"command not found|No module named|Cannot find module|MODULE_NOT_FOUND|no matches found|bad substitution|parse error near|unrecognized arguments|unknown option|invalid option|illegal option|externally-managed|outside allowed roots|certificate|not supported|unsupported|requires? (?:Python|node)|partially initialized module|f-string expression|command line cannot be assembled|ugrep: error|=+ not found|not a git repository|Operation not permitted|[Pp]ermission denied|This agent is isolated|Blocked: sleep|Cannot create agent worktree|can't be checked before it runs|cannot be statically|Subagents should return|classifier\. Reason: \[|Dangerous rm|Too Many Requests")
RUNNER = re.compile(r"pytest|unittest|sphinx|latexmk|make\b|ruff|tsc\b|vhs\b|playwright|chromium|claude\s+(?:-p|plugin)|gh\s+(?:run|pr)|curl\s|until\s|while\s|docker|tmux|screencapture|cargo|npm|bun\b|check|verify|validate|build")
GENERIC = re.compile(r'^(?:AssertionError|KeyError|Traceback|TypeError|ValueError|IndexError|AttributeError|json\.decoder|Found N error|### Error|<PATH>$|Exit code|E  )')

def week(ts): return datetime.date.fromisoformat(ts[:10]).isocalendar()[1] if ts else None

def run():
    S = load(); C = [json.loads(l) for l in open('ep_candidates.jsonl')]
    by = {(s['session'], s['agent']): s for s in S}
    out = []
    # ---- T1: first meeting of a signature, in time order over the whole corpus
    env = sorted([c for c in C if c['shape'] == 'ENV' and c['ts']], key=lambda c: c['ts']); seen = {}
    t1_all = 0
    for c in env:
        s = by[(c['session'], c['agent'])]; e = s['ev'][c['a']]; r = e['res'] or ''
        if TRANSIENT.search(r): continue
        g = signature(r)
        if not g or not T1CLASS.search(g): continue          # the error line itself must name the machine, the shell, a tool or the harness
        g = re.sub(r'no matches found: .*', 'no matches found', g); g = re.sub(r'(This agent is isolated in the worktree).*', r'\1', g); g = re.sub(r'(Blocked: sleep).*', r'\1', g)
        m = re.search(r"No module named '([\w.]+)'|Cannot find module '([^']+)'|command not found: (\S+)", r)
        if m: g = re.sub(r'<Q>', next(x for x in m.groups() if x), g, 1) if '<Q>' in g else g
        t1_all += 1
        if g in seen: seen[g].append(c); continue
        seen[g] = [c]; out.append(dict(c, rule='T1', sig=g))
    # ---- T2
    for c in C:
        if c['shape'] != 'MA': continue
        s = by[(c['session'], c['agent'])]
        fails = [e for e in s['ev'][c['a']:c['b'] + 1] if e['k'] == 'call' and e['err'] and not HARNESS.search(e['res'] or '')]
        if all(e['name'] == 'Bash' and check_key(cmd(e)) and not ENVERR.search((e['res'] or '')[-600:]) for e in fails): continue
        out.append(dict(c, rule='T2'))
    # ---- T3
    for c in C:
        if c['shape'] not in ('RG', 'RGE'): continue
        s = by[(c['session'], c['agent'])]; ev = s['ev']
        hosted = c['check'].startswith('gh ')
        if hosted:
            local_green = any(e['k'] == 'call' and e['name'] == 'Bash' and (check_key(cmd(e)) or ('x',))[0] in ('pytest', 'run_tests.sh', 'claude plugin test', 'cargo test', 'bun test', 'npm test', 'unittest') and not e['err'] and re.search(r'\d+ passed|\bOK\b|0 fail', e['res'] or '') for e in ev[:c['a']])
            if local_green and c['span'] <= 80: out.append(dict(c, rule='T3a'))
            continue
        if c['shape'] == 'RGE' and not c['planned'] and c['span'] <= 15:
            texts = ' '.join(cmd(e) for e in ev[c['a']:c['b'] + 1] if e['k'] == 'call' and e['name'] == 'Bash')
            if BASELINE.search(texts): continue
            if is_edit(ev[c['a']]): continue                      # the failing call itself wrote files: the work, mid-edit
            out.append(dict(c, rule='T3b'))
    # ---- T4
    for s in S:
        if is_tmp(s) or s['sub']: continue
        for j, e in enumerate(s['ev']):
            if e['k'] == 'prompt' and e['src'] in ('human', 'typed', 'queued') and '<command-name>/compound:learn' in e['text']:
                out.append(dict(rule='T4', shape='UC', session=s['session'], agent=None, sub=False, project=proj(s), ts=e['ts'], a=j, b=j, id='UC-%s-main-%d' % (s['session'][:8], j)))
    # ---- T5: the second time a helper is written (content overlap >= 0.30 with a script another agent ran 3+ times)
    from ep_script_clusters import clusters
    X, big, _text = clusters()
    for v in big:
        v = sorted(v, key=lambda c: c['ts'] or '')
        out.append(dict(v[1], rule='T5', cluster=len(v)))
    return S, C, out, t1_all, seen

if __name__ == '__main__':
    S, C, T, t1_all, seen = run()
    json.dump(T, write_private(os.path.join(CACHE, 'triggers.json'), 'w'))
    cnt = collections.Counter(t['rule'] for t in T); print('triggers over the corpus (2026-09-02 to 2026-10-11):', dict(cnt), 'total', len(T))
    print('T1 before first-meeting-only:', t1_all, '-> distinct signatures:', len(seen))
    wk = collections.defaultdict(collections.Counter)
    for t in T: wk[t['rule']][week(t['ts'])] += 1
    print('per ISO week (39 = Sep 21-27, 40 = Sep 28-Oct 4, 41 = Oct 5-11):')
    for r in sorted(wk): print('  %-4s %s  mean of weeks 39-41: %.1f' % (r, dict(sorted(wk[r].items())), sum(wk[r][w] for w in (39, 40, 41)) / 3))
    allw = collections.Counter(week(t['ts']) for t in T); print('  all  %s  mean of weeks 39-41: %.1f' % (dict(sorted(allw.items())), sum(allw[w] for w in (39, 40, 41)) / 3))
    print('main loop vs subagent:', dict(collections.Counter((t['rule'], 'sub' if t['sub'] else 'main') for t in T)))
    print('by project:', collections.Counter(t['project'].replace('(wt)', '') for t in T).most_common(8))
    # ---- flood: triggers per session and per turn of the main loop
    ps = collections.Counter(t['session'] for t in T)
    sess = {s['session'] for s in S if not is_tmp(s) and not s['sub'] and sum(1 for e in s['ev'] if e['k'] == 'call') >= 10}
    print('working sessions (main loop, >=10 calls):', len(sess), '| with >=1 trigger:', sum(1 for x in sess if ps[x]), '| triggers per such session: median %d, max %d' % (sorted(ps[x] for x in sess if ps[x])[len([x for x in sess if ps[x]]) // 2], max(ps.values())))
    turns = 0; hit = collections.Counter()
    main = {s['session']: s for s in S if not is_tmp(s) and not s['sub']}
    bounds = {}
    for sid, s in main.items():
        b = [j for j, e in enumerate(s['ev']) if e['k'] == 'prompt' and e['src'] in ('typed', 'human', 'queued', 'suggestion_accepted')]
        bounds[sid] = b; turns += len(b)
    import bisect
    for t in T:
        if t['sub']:
            # a subagent's trigger lands in the turn of the main loop that was running when it happened
            s = main.get(t['session'])
            if not s: continue
            j = next((k for k, e in enumerate(s['ev']) if (e.get('ts') or '') >= (t['ts'] or '')), len(s['ev']) - 1)
        else: j = t['a']
        b = bounds.get(t['session'], []); k = bisect.bisect_right(b, j) - 1
        hit[(t['session'], k)] += 1
    v = sorted(hit.values())
    print('typed turns in main sessions:', turns, '| turns with >=1 trigger:', len(hit), '(%.0f%%)' % (100 * len(hit) / turns), '| triggers in such a turn: median %d, p90 %d, max %d' % (v[len(v) // 2], v[int(len(v) * .9)], v[-1]))
    # ---- precision on the labelled set
    L = {json.loads(l)['id']: json.loads(l) for l in open('episode-study-labels.jsonl')}
    tid = collections.defaultdict(set)
    for t in T: tid[t['id']].add(t['rule'])
    print('\nlabelled candidates each rule would fire on (T1 counted without the first-meeting filter, see below):')
    res = collections.defaultdict(collections.Counter)
    for i, d in L.items():
        lab = 'reusable' if d['label'].startswith('reusable') else d['label']
        for r in tid.get(i, ()): res[r][lab] += 1
        if not tid.get(i): res['(no rule) ' + d['shape']][lab] += 1
    for r in sorted(res): print('  %-16s %s' % (r, dict(res[r])))
