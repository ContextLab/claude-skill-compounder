#!/usr/bin/env python3
"""Threshold study, step 5: a stratified random sample of TARGET scripts for hand reading.
argv[1] = cache dir. What it prints quotes private scripts: read it on the machine, do not keep it in the repository. Prints the scripts shuffled and BLIND (no run counts, no labels, no stratum):
directory tail, name, line count, first lines. Writes sample_key.pkl (id -> session, path, stratum)
to the cache. `--reveal` prints the key as TSV instead (used to build ts_handlabels.tsv)."""
import os, sys, pickle, random, re, hashlib
HOME_KEY = re.sub(r'[^A-Za-z0-9]', '-', os.path.expanduser('~')) + '-'      # how a project directory under the home directory is named
short = lambda p: p[len(HOME_KEY):] if p.startswith(HOME_KEY) else p
C = sys.argv[1]
P = pickle.load(open(os.path.join(C, 'table.pkl'), 'rb'))
def n_ok(e): return len([r for r in e['runs'] if not r['err'] and not r['soft'] and not r['intr']])
def argsets(e): return len({r['args'] for r in e['runs'] if not r['err'] and not r['soft'] and not r['intr']})
TGT = [e for e in P if not (e['tracked'] or e['wt_copy'] or e['loc'] == 'worktree') and not e['is_test'] and e['loc'] in ('scratchpad', 'tmp')]
def stratum(e):
    k, a = n_ok(e), argsets(e)
    if a >= 2: return 'A'
    if k >= 3: return 'B'
    if k == 2: return 'C'
    if k == 1: return 'D'
    return 'E'
N = dict(A=20, B=15, C=10, D=20, E=5)
rng = random.Random(20261011)
TGT.sort(key=lambda e: (e['session'], e['path']))
S = {}
for e in TGT: S.setdefault(stratum(e), []).append(e)
pick = []
for k in 'ABCDE': pick += [(k, e) for e in rng.sample(S[k], N[k])]
rng.shuffle(pick)
key = {}
for i, (k, e) in enumerate(pick, 1):
    key[i] = (e['session'], e['path'], k)
pickle.dump(key, open(os.path.join(C, 'sample_key.pkl'), 'wb'))
if '--reveal' in sys.argv:
    print('strata sizes', {k: len(v) for k, v in sorted(S.items())})
    for i, (s, p, k) in key.items(): print('%d\t%s\t%s\t%s' % (i, k, s[:8], hashlib.sha1(p.encode()).hexdigest()[:10]))
    sys.exit()
for i, (k, e) in enumerate(pick, 1):
    d = '/'.join(e['path'].split('/')[-3:-1]); d = re.sub(r'[0-9a-f]{8}-[0-9a-f-]{27}', '<sid>', d)
    print('#%d  %s/%s  [%s; %d lines]' % (i, d, e['base'], short(e['project'])[:20], e['lines']))
    ls = [l for l in e['final'].split('\n') if l.strip()]
    for l in ls[:int(sys.argv[2]) if len(sys.argv) > 2 else 14]: print('    ' + l[:130])
