#!/usr/bin/env python3
"""Threshold study, step 5c: third hand-read sample, OUTSIDE project A (the first two were
29/32 project A in the hit stratum; the project is named by the environment variable TS_FOCUS_PROJECT): 22 random hits of the shipped rule and 10 random scripts with
>= 3 ok runs on the same arguments. argv[1] = cache dir. What it prints quotes private scripts: read it on the machine, do not keep it in the repository. Writes sample3_key.pkl."""
import os, sys, pickle, random, re
HOME_KEY = re.sub(r'[^A-Za-z0-9]', '-', os.path.expanduser('~')) + '-'      # how a project directory under the home directory is named
short = lambda p: p[len(HOME_KEY):] if p.startswith(HOME_KEY) else p
FOCUS = os.environ.get('TS_FOCUS_PROJECT', '')      # a substring of the name of project A
C = sys.argv[1]
P = pickle.load(open(os.path.join(C, 'table.pkl'), 'rb'))
ok = lambda e: [r for r in e['runs'] if not r['err'] and not r['soft'] and not r['intr']]
TGT = [e for e in P if not (e['tracked'] or e['wt_copy'] or e['loc'] == 'worktree') and not e['is_test'] and e['loc'] in ('scratchpad', 'tmp') and not (FOCUS and FOCUS in e['project'])]
TGT.sort(key=lambda e: (e['session'], e['path']))
for e in TGT: o = ok(e); e['k'] = len(o); e['a'] = len({r['args'] for r in o})
H = [e for e in TGT if e['k'] >= 2 and (e['a'] >= 2 or e['takes_args'])]
M = [e for e in TGT if e['k'] >= 3 and e['a'] <= 1 and not e['takes_args']]
rng = random.Random(99)
pick = [('H', e) for e in rng.sample(H, 22)] + [('M', e) for e in rng.sample(M, 10)]
print('outside project A: target %d, rule hits %d, ok>=3 same args and no argv %d' % (len(TGT), len(H), len(M)))
pickle.dump({i: (e['session'], e['path'], k) for i, (k, e) in enumerate(pick, 201)}, open(os.path.join(C, 'sample3_key.pkl'), 'wb'))
for i, (k, e) in enumerate(pick, 201):
    ex = sorted({' '.join(r['args'])[:60] for r in ok(e)})[:3]
    print('#%d %s %s/%s [%s; %d lines; ok %d, argsets %d, %s] args: %s' % (i, k, e['path'].split('/')[-2], e['base'], short(e['project'])[:16], e['lines'], e['k'], e['a'], 'sub' if e['sub_writer'] else 'MAIN', ' | '.join(ex)))
    for l in [l for l in e['final'].split('\n') if l.strip()][:6]: print('    ' + l[:112])
