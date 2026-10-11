#!/usr/bin/env python3
"""Threshold study, step 5b: a second hand-read sample, not blind to stratum (the reader knows the
two buckets but sees no labels): 12 more scripts whose arguments varied (stratum A, not in the
first sample), and 14 whose arguments never varied but which ran OK in two or more user turns.
argv[1] = cache dir. What it prints quotes private scripts: read it on the machine, do not keep it in the repository. Writes sample2_key.pkl."""
import os, sys, pickle, random, re
HOME_KEY = re.sub(r'[^A-Za-z0-9]', '-', os.path.expanduser('~')) + '-'      # how a project directory under the home directory is named
short = lambda p: p[len(HOME_KEY):] if p.startswith(HOME_KEY) else p
C = sys.argv[1]
P = pickle.load(open(os.path.join(C, 'table.pkl'), 'rb'))
key1 = {(s, p) for s, p, k in pickle.load(open(os.path.join(C, 'sample_key.pkl'), 'rb')).values()}
ok = lambda e: [r for r in e['runs'] if not r['err'] and not r['soft'] and not r['intr']]
TGT = [e for e in P if not (e['tracked'] or e['wt_copy'] or e['loc'] == 'worktree') and not e['is_test'] and e['loc'] in ('scratchpad', 'tmp')]
TGT.sort(key=lambda e: (e['session'], e['path']))
A = [e for e in TGT if len({r['args'] for r in ok(e)}) >= 2 and (e['session'], e['path']) not in key1]
Tn = [e for e in TGT if len({r['args'] for r in ok(e)}) == 1 and len({r['turn'] for r in ok(e)}) >= 2 and (e['session'], e['path']) not in key1]
rng = random.Random(42)
pick = [('A', e) for e in rng.sample(A, 12)] + [('T', e) for e in rng.sample(Tn, 14)]
print('bucket sizes: A (not yet read) %d, T same args and ok in >=2 turns %d' % (len(A), len(Tn)))
pickle.dump({i: (e['session'], e['path'], k) for i, (k, e) in enumerate(pick, 101)}, open(os.path.join(C, 'sample2_key.pkl'), 'wb'))
for i, (k, e) in enumerate(pick, 101):
    o = ok(e)
    print('#%d %s %s/%s [%s; %d lines; ok %d, turns %d, agents %d, %s]' % (i, k, e['path'].split('/')[-2], e['base'], short(e['project'])[:16], e['lines'], len(o),
          len({r['turn'] for r in o}), len({r['sub'] for r in o}), 'sub' if e['sub_writer'] else 'MAIN'))
    for l in [l for l in e['final'].split('\n') if l.strip()][:7]: print('    ' + l[:118])
