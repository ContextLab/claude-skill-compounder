#!/usr/bin/env python3
"""Threshold study, step 6: join the blind hand verdicts to the strata and estimate each rule's
precision and recall on the TARGET population (stratum-weighted).
argv[1] = cache dir. argv[2] (or the environment variable TS_VERDICTS) = the hand verdicts, a local
JSON file that is not kept in the repository: the verdicts were given on private scripts and, like the
sample keys in the cache, stay on the machine. Its form:
    {"sample1": "K P B ...", "sample2": "B K ...", "sample3": "P K ..."}
one letter for each script of the sample, in the order the sampler printed them (70, 26 and 32 letters).
Verdicts were written before `ts_sample.py --reveal` was run.
K = a reusable tool (takes input, or a re-runnable check/build procedure not bound to one datum)
B = borderline (general logic, but bound to one batch / temp directory / commit)
P = probe, repro, one-off patcher or generated data
TS_FOCUS_PROJECT (environment, optional): a substring of the name of project A, the project most of
the first two samples came from."""
import os, re, sys, json, pickle, subprocess, collections, hashlib
C = sys.argv[1]
HOME_KEY = re.sub(r'[^A-Za-z0-9]', '-', os.path.expanduser('~')) + '-'      # how a project directory under the home directory is named
short = lambda p: p[len(HOME_KEY):] if p.startswith(HOME_KEY) else p
VERDICTS = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('TS_VERDICTS', '')
if not VERDICTS: sys.exit('ts_hand.py: give the verdict file as the second argument or in TS_VERDICTS (see the docstring)')
HAND = json.load(open(VERDICTS))
FOCUS = os.environ.get('TS_FOCUS_PROJECT', '')
in_focus = lambda e: bool(FOCUS) and FOCUS in e['project']
V = dict(zip(range(1, 71), HAND['sample1'].split()))
assert len(V) == 70
key = pickle.load(open(os.path.join(C, 'sample_key.pkl'), 'rb'))
P = pickle.load(open(os.path.join(C, 'table.pkl'), 'rb'))
by = {(e['session'], e['path']): e for e in P}
def n_ok(e): return len([r for r in e['runs'] if not r['err'] and not r['soft'] and not r['intr']])
def argsets(e): return len({r['args'] for r in e['runs'] if not r['err'] and not r['soft'] and not r['intr']})
TGT = [e for e in P if not (e['tracked'] or e['wt_copy'] or e['loc'] == 'worktree') and not e['is_test'] and e['loc'] in ('scratchpad', 'tmp')]
def stratum(e):
    k, a = n_ok(e), argsets(e)
    return 'A' if a >= 2 else 'B' if k >= 3 else 'C' if k == 2 else 'D' if k == 1 else 'E'
size = collections.Counter(stratum(e) for e in TGT)
tab = collections.defaultdict(collections.Counter); rows = []
for i, (s, p, k) in sorted(key.items()):
    e = by[(s, p)]; tab[k][V[i]] += 1
    rows.append((i, k, V[i], e['base'], n_ok(e), argsets(e), e['lines'], int(e['takes_args']), int(e['sub_writer']),
                 int(max(e['j_a'][0], e['j_x'][0]) >= .5), int(e['used_a'] or e['used_x']), int(e['brief']), int(e['copied_home'] or e['git_exact'] or e['git_near'])))
names = dict(A='args varied between ok runs', B='ok>=3, same args', C='ok==2, same args', D='ok==1', E='no ok run')
print('stratum                         size  read   K   B   P   K share   K+B share')
est = {}
for k in 'ABCDE':
    n = sum(tab[k].values()); K, B = tab[k]['K'], tab[k]['B']
    est[k] = (K / n, (K + B) / n)
    print('%s %-28s %5d  %4d  %2d  %2d  %2d   %5.0f%%    %5.0f%%' % (k, names[k], size[k], n, K, B, tab[k]['P'], 100 * K / n, 100 * (K + B) / n))
tot = [sum(size[k] * est[k][j] for k in 'ABCDE') for j in (0, 1)]
print('estimated tools in TARGET: K %.0f (%.1f%%), K+B %.0f (%.1f%%) of %d' % (tot[0], 100 * tot[0] / len(TGT), tot[1], 100 * tot[1] / len(TGT), len(TGT)))
for name, ks in (('args varied (A)', 'A'), ('ok>=3 (A-part + B)', None), ('args varied OR ok>=3 (A+B)', 'AB'), ('ok>=2 (A+B+C)', 'ABC'), ('ok>=1 (A+B+C+D)', 'ABCD')):
    if ks is None: continue
    hits = sum(size[k] for k in ks)
    for j, lab in ((0, 'K'), (1, 'K+B')):
        tp = sum(size[k] * est[k][j] for k in ks)
        print('  rule %-28s hits %4d  est. %-3s precision %4.0f%%  recall %4.0f%%' % (name, hits, lab, 100 * tp / hits, 100 * tp / tot[j]))
print('\nper-item (id stratum verdict name ok argsets lines reads_args sub redo reused brief to_repo):')
for r in rows: print('  ' + ' '.join(str(x) for x in r))
# ---- second sample (ts_sample2.py): 12 more of stratum A, 14 of "same args, ok in >= 2 turns"
V2 = dict(zip(range(101, 127), HAND['sample2'].split()))
assert len(V2) == 26
key2 = pickle.load(open(os.path.join(C, 'sample2_key.pkl'), 'rb'))
t2 = collections.defaultdict(collections.Counter)
for i, (s_, p, k) in key2.items(): t2[k][V2[i]] += 1
print('\nsecond sample: A (args varied) %s ; T (same args, ok in >=2 turns) %s' % (dict(t2['A']), dict(t2['T'])))
allA = tab['A'] + t2['A']; nA = sum(allA.values())
print('stratum A, both samples: read %d, K %d (%.0f%%), B %d, P %d; K+B %.0f%%' % (nA, allA['K'], 100 * allA['K'] / nA, allA['B'], allA['P'], 100 * (allA['K'] + allA['B']) / nA))
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** .5
    return (c - h) / d, (c + h) / d
print('  95%% Wilson interval for K: %.0f%%..%.0f%%; for K+B: %.0f%%..%.0f%%' % tuple(100 * x for x in wilson(allA['K'], nA) + wilson(allA['K'] + allA['B'], nA)))
print('  stratum A by project (both samples):', dict(collections.Counter((short(by[(s_, p)]['project'])[:16], V[i] if i < 100 else V2[i]) for i, (s_, p, k) in list(key.items()) + list(key2.items()) if k == 'A')))

# ---- stratum-weighted estimates for rules that cut across strata (first, blind sample; A pooled with the second)
items = []
for i, (s_, p, k) in list(key.items()) + [(i, v) for i, v in key2.items() if v[2] == 'A']:
    e = by[(s_, p)]; items.append((k, V[i] if i < 100 else V2[i], e))
nk = collections.Counter(k for k, _, _ in items)
def west(f, lab):
    hit = tp = allpos = 0.0
    for k, v, e in items:
        w = size[k] / nk[k]; pos = v in lab
        allpos += w * pos
        if f(e): hit += w; tp += w * pos
    return hit, tp, allpos
RULES = [('args varied between ok runs', lambda e: argsets(e) >= 2),
         ('ok >= 3', lambda e: n_ok(e) >= 3),
         ('ok >= 2', lambda e: n_ok(e) >= 2),
         ('ok >= 3, same args', lambda e: n_ok(e) >= 3 and argsets(e) <= 1),
         ('reads its arguments (static), ok >= 1', lambda e: e['takes_args'] and n_ok(e) >= 1),
         ('reads its arguments (static), ok >= 2', lambda e: e['takes_args'] and n_ok(e) >= 2),
         ('args varied OR (reads args, ok >= 2)', lambda e: argsets(e) >= 2 or (e['takes_args'] and n_ok(e) >= 2)),
         ('args varied AND reads args', lambda e: argsets(e) >= 2 and e['takes_args']),
         ('reads args, ok >= 1, lines < 80', lambda e: e['takes_args'] and n_ok(e) >= 1 and e['lines'] < 80),
         ('proxy redo (later near-copy)', lambda e: max(e['j_a'][0], e['j_x'][0]) >= .5),
         ('proxy named in a later brief', lambda e: e['brief']),
         ('proxy run by another agent', lambda e: e['used_a']),
         ('rewritten after a run', lambda e: e['mods_after_run'] >= 1),
         ('failure before first success', lambda e: e['fail_before_ok']),
         ('lines >= 40, ok >= 1', lambda e: e['lines'] >= 40 and n_ok(e) >= 1)]
print('\nstratum-weighted hand estimates on TARGET (weights = stratum size / scripts read); true hits from the table')
print('%-42s %9s %9s  %-18s %-18s' % ('rule', 'true hits', 'est hits', 'K  prec / recall', 'K+B prec / recall'))
for nm, f in RULES:
    true_hits = sum(1 for e in TGT if f(e)); row = '%-42s %9d' % (nm, true_hits)
    for lab in ('K', 'KB'):
        h, tp, ap = west(f, lab)
        if lab == 'K': row += ' %9.0f ' % h
        row += ' %5.0f%% / %4.0f%%     ' % (100 * tp / h if h else 0, 100 * tp / ap)
    print(row)

# agreement of the hand verdict with the proxy labels and static signal, inside the sample
for nm, f in (('reads its arguments (static)', lambda r: r[7]), ('proxy KEEP (redo|reused|brief|to_repo)', lambda r: r[9] or r[10] or r[11] or r[12]), ('redo', lambda r: r[9]), ('lines<40 & reads args', lambda r: r[7] and r[6] < 40)):
    a = [r for r in rows if f(r)]; b = [r for r in rows if not f(r)]
    print('%-40s yes: %2d of which K %2d, B %2d | no: %2d of which K %2d, B %2d' % (nm, len(a), sum(r[2] == 'K' for r in a), sum(r[2] == 'B' for r in a), len(b), sum(r[2] == 'K' for r in b), sum(r[2] == 'B' for r in b)))

# ---- third sample (ts_sample3.py), outside project A: 22 rule hits, 10 with ok>=3 on the same args and no argv
V3 = dict(zip(range(201, 233), HAND['sample3'].split()))
assert len(V3) == 32
key3 = pickle.load(open(os.path.join(C, 'sample3_key.pkl'), 'rb'))
ship = lambda e: n_ok(e) >= 2 and (argsets(e) >= 2 or e['takes_args'])
pool = collections.defaultdict(collections.Counter); seen = set()
for kk, VV in ((key, V), (key2, V2), (key3, V3)):
    for i, (s_, p, k) in kk.items():
        if (s_, p) in seen: continue
        seen.add((s_, p)); e = by[(s_, p)]
        pool[('hit' if ship(e) else 'miss', 'project A' if in_focus(e) else 'other projects')][VV[i]] += 1
print('\nall three samples pooled, by the shipped rule (ok >= 2 and (args varied or reads its arguments)):')
tot = collections.defaultdict(collections.Counter)
for (hm, pj), c in sorted(pool.items()):
    n = sum(c.values()); tot[hm] += c
    print('   %-5s %-17s read %3d  K %2d  B %2d  P %2d   K %3.0f%%  K+B %3.0f%%' % (hm, pj, n, c['K'], c['B'], c['P'], 100 * c['K'] / n, 100 * (c['K'] + c['B']) / n))
for hm, c in tot.items():
    n = sum(c.values()); print('   %-5s %-17s read %3d  K %2d  B %2d  P %2d   K %3.0f%%  K+B %3.0f%%' % (hm, 'all', n, c['K'], c['B'], c['P'], 100 * c['K'] / n, 100 * (c['K'] + c['B']) / n))
nh = {'project A': sum(1 for e in TGT if ship(e) and in_focus(e)), 'other projects': sum(1 for e in TGT if ship(e) and not in_focus(e))}
wK = sum(nh[pj] * pool[('hit', pj)]['K'] / sum(pool[('hit', pj)].values()) for pj in nh) / sum(nh.values())
wP = sum(nh[pj] * pool[('hit', pj)]['P'] / sum(pool[('hit', pj)].values()) for pj in nh) / sum(nh.values())
print('   hits in TARGET: %s; project-weighted K precision %.0f%%, probe (P) share of hits %.0f%%' % (nh, 100 * wK, 100 * wP))
c = tot['hit']; n = sum(c.values())
print('   Wilson 95%% for P share of hits (unweighted %d/%d): %.0f%%..%.0f%%' % ((c['P'], n) + tuple(100 * x for x in wilson(c['P'], n))))
t3 = collections.Counter(V3[i] for i, v in key3.items() if v[2] == 'M'); print('   sample 3, ok>=3 same args no argv, other projects:', dict(t3))
