"""Checks of the labelled set against things that do not depend on the labeller.
Usage: python3 ep_label_checks.py
1. recurrence: does a failure inside the labelled window carry a signature met in two or more
   parent sessions?  (label x recurs table)
2. failing tests: pytest node ids that failed in two or more sessions on different days."""
import json, re, collections
from ep_common import *
from ep_recurrence import signature
from ep_detect import check_key, cmd, red

S = load(); L = [json.loads(l) for l in open('episode-study-labels.jsonl')]
by = {(s['session'], s['agent']): s for s in S}
sig = collections.defaultdict(set); sigp = collections.defaultdict(set)
for s in S:
    if is_tmp(s): continue
    for e in s['ev']:
        if e['k'] == 'call' and e['err']:
            g = signature(e['res'])
            if g: sig[g].add(s['session']); sigp[g].add(proj(s).replace('(wt)', ''))
GENERIC = re.compile(r'^(?:AssertionError|KeyError|Traceback|TypeError|ValueError|IndexError|AttributeError|FileNotFoundError|json\.decoder|Found N error|ls: |cat: |cp: |### Error|<PATH>$|Exit code)')
tab = collections.defaultdict(collections.Counter)
for d in L:
    s = by[(d['session'], d['agent'])]; a, b = d['first_event'], d['last_event']
    if d['shape'] in ('UC', 'SCR', 'DX'): continue
    gs = [signature(e['res']) for e in s['ev'][a:min(b, a + 40) + 1] if e['k'] == 'call' and e['err']]
    gs = [g for g in gs if g and not GENERIC.match(g)]
    rec = any(len(sig[g]) >= 2 for g in gs); rec3 = any(len(sig[g]) >= 3 for g in gs)
    lab = 'reusable' if d['label'].startswith('reusable') else d['label']
    tab[lab]['recurs in >=2 sessions' if rec else ('has a failure signature, met once' if gs else 'no failed call with a signature')] += 1
    d['_rec'] = rec
print('label x whether a specific failure in the window is met in another session (RG, RGE, MA, ENV rows):')
for lab, c in tab.items(): print('  %-16s %s' % (lab, dict(c)))
r = [d for d in L if d.get('_rec')]
print('  of %d windows holding a recurring failure: %d labelled reusable' % (len(r), sum(d['label'].startswith('reusable') for d in r)))

# 2. failing pytest node ids across sessions
node = collections.defaultdict(set)
for s in S:
    if is_tmp(s): continue
    for e in s['ev']:
        if e['k'] == 'call' and e['name'] == 'Bash' and e['res']:
            for m in re.finditer(r'FAILED (tests?/[\w/.-]+\.py::[\w\[\]. -]+?)(?: - |\s*$|\s*\|)', e['res'], re.M):
                node[m.group(1).strip()].add((s['session'], (e['ts'] or '')[:10]))
multi = {k: v for k, v in node.items() if len({x[0] for x in v}) >= 2 and len({x[1] for x in v}) >= 2}
print('\npytest node ids seen FAILED:', len(node), '| in >=2 sessions on >=2 days:', len(multi))
for k, v in sorted(multi.items(), key=lambda kv: -len({x[0] for x in kv[1]}))[:14]:
    print('  %d sessions, days %s  %s' % (len({x[0] for x in v}), sorted({x[1] for x in v})[:4], k[:110]))
