#!/usr/bin/env python3
"""Threshold study, step 7: spot checks quoted in the report. argv[1] = cache dir.
(1) where the scripts the usage audit named fall; (2) every TARGET script with the same arguments
and OK runs in >= 3 user turns; (3) what the shipped rule fires on outside TARGET; (4) weekly yield;
(5) leave-one-session / one-project-out for the proxy 'redo' label.

Environment, all optional (the names belong to the projects that were read and are not kept here):
  TS_NAMED_SCRIPTS    comma-separated basenames of the scripts the usage audit named, for check (1)
  TS_DROP_SESSION     id prefix of the one session to leave out in (4) and (5)
  TS_FOCUS_PROJECT    a substring of the name of project A, left out in (5)
  TS_SECOND_PROJECT   a substring of the name of project B, taken alone in (5)"""
import os, sys, pickle, collections, re
HOME_KEY = re.sub(r'[^A-Za-z0-9]', '-', os.path.expanduser('~')) + '-'      # how a project directory under the home directory is named
short = lambda p: p[len(HOME_KEY):] if p.startswith(HOME_KEY) else p
NAMED = [x.strip() for x in os.environ.get('TS_NAMED_SCRIPTS', '').split(',') if x.strip()]
DROP = os.environ.get('TS_DROP_SESSION', ''); FOCUS = os.environ.get('TS_FOCUS_PROJECT', ''); SECOND = os.environ.get('TS_SECOND_PROJECT', '')
dropped = lambda e: bool(DROP) and e['session'].startswith(DROP)
C = sys.argv[1]
P = pickle.load(open(os.path.join(C, 'table.pkl'), 'rb'))
ok = lambda e: [r for r in e['runs'] if not r['err'] and not r['soft'] and not r['intr']]
for e in P:
    o = ok(e); e['k'] = len(o); e['a'] = len({r['args'] for r in o}); e['t'] = len({r['turn'] for r in o})
    e['git'] = e['tracked'] or e['wt_copy'] or e['loc'] == 'worktree' or (e['loc'] == 'home' and e['git_exact'])
    e['redo'] = max(e['j_a'][0], e['j_x'][0]) >= .5
ship = lambda e: e['k'] >= 2 and (e['a'] >= 2 or e['takes_args'])
shipA = lambda e: e['a'] >= 2
TGT = [e for e in P if not e['git'] and not e['is_test'] and e['loc'] in ('scratchpad', 'tmp')]
print('(1) scripts named in the usage audit')
for nm in NAMED:
    for e in P:
        if e['base'] == nm:
            print('   %-22s %-10s ok %3d argsets %2d turns %2d reads_args %d lines %3d in TARGET %d  rule %s' % (nm, e['loc'], e['k'], e['a'], e['t'], e['takes_args'], e['lines'], e in TGT, 'FIRES' if ship(e) else 'silent'))
    if not any(e['base'] == nm for e in P): print('   %-22s not among created scripts (written before the first kept transcript, or not by Write/here-document)' % nm)
print('(2) TARGET, same arguments, ok runs in >= 3 user turns')
for e in sorted([e for e in TGT if e['a'] == 1 and e['t'] >= 3], key=lambda e: -e['t']):
    print('   ok %3d turns %2d agents %d %s lines %3d reads_args %d  %s/%s' % (e['k'], e['t'], e['run_agents'], 'sub ' if e['sub_writer'] else 'MAIN', e['lines'], e['takes_args'], short(e['project'])[:14], '/'.join(e['path'].split('/')[-2:])))
print('(3) what the rule fires on')
cats = [('TARGET (scratch/tmp, not git, not test)', TGT),
        ('home dir, in git history now', [e for e in P if e['loc'] in ('home', 'worktree') and e['git'] and not e['is_test']]),
        ('home dir, not in git', [e for e in P if e['loc'] == 'home' and not e['git'] and not e['is_test']]),
        ('test files (name, tests/ dir, or run by pytest)', [e for e in P if e['is_test']]),
        ('scratch checkout of the repository, not test', [e for e in P if e['wt_copy'] and not e['is_test']])]
for nm, pop in cats:
    print('   %-48s n %4d  rule %4d  args-varied only %4d  ok>=3 %4d' % (nm, len(pop), sum(ship(e) for e in pop), sum(shipA(e) for e in pop), sum(e['k'] >= 3 for e in pop)))
hn = [e for e in P if e['loc'] == 'home' and not e['git'] and not e['is_test'] and ship(e)]
print('   home, not in git, rule fires:', collections.Counter('/'.join(e['path'].split('/')[3:6]) for e in hn).most_common(8))
print('(4) yield of the rule in TARGET')
H = [e for e in TGT if ship(e)]
wk = collections.Counter(e['week'] for e in H); wa = collections.Counter(e['week'] for e in TGT)
print('   hits %d of %d; per ISO week (hits/target):' % (len(H), len(TGT)), [(w, wk[w], wa[w]) for w in sorted(wa)])
print('   by session:', collections.Counter(short(e['project'])[:16] + ' ' + e['session'][:8] for e in H).most_common(8))
print('   hits written by the main agent: %d; by subagents: %d' % (sum(not e['sub_writer'] for e in H), sum(e['sub_writer'] for e in H)))
dn = collections.Counter((e['week'], e['project'], e['base']) for e in H)
wd = collections.Counter(w for (w, p, b) in dn)
print('   distinct (project, basename) per week:', sorted(wd.items()))
days = collections.Counter(e['day'] for e in H); print('   days with a hit: %d; median hits on such a day: %d; max %d' % (len(days), sorted(days.values())[len(days) // 2], max(days.values())))
no = [e for e in H if not dropped(e)]
wk2 = collections.Counter(e['week'] for e in no); print('   without the session named in TS_DROP_SESSION: hits %d; per week %s' % (len(no), sorted(wk2.items())))
print('(5) proxy label redo vs the rule, leaving sessions out')
def pr(pop, f, lab):
    Hh = [e for e in pop if f(e)]; tp = sum(e[lab] for e in Hh); base = sum(e[lab] for e in pop)
    return '%4d hits, %3d redo, precision %4.1f%%, recall %4.1f%% (base rate %4.1f%%, n %d)' % (len(Hh), tp, 100 * tp / max(1, len(Hh)), 100 * tp / max(1, base), 100 * base / max(1, len(pop)), len(pop))
for nm, pop in (('all', TGT), ('without one session', [e for e in TGT if not dropped(e)]),
                ('without project A', [e for e in TGT if not (FOCUS and FOCUS in e['project'])]),
                ('only project B', [e for e in TGT if SECOND and SECOND in e['project']])):
    print('   %-26s rule: %s' % (nm, pr(pop, ship, 'redo')))
    print('   %-26s ok>=3: %s' % ('', pr(pop, lambda e: e['k'] >= 3, 'redo')))
    print('   %-26s ok>=3 same args: %s' % ('', pr(pop, lambda e: e['k'] >= 3 and e['a'] <= 1, 'redo')))
print('(6) distinct jobs among the rule hits: connected components of vocabulary overlap >= .5 (same project)')
import re as _re
def toks(t): return set(_re.findall(r'[A-Za-z_][\w.]{3,}', t))
for e in H: e['tk'] = toks(e['final'])
par = {id(e): id(e) for e in H}
def find(x):
    while par[x] != x: par[x] = par[par[x]]; x = par[x]
    return x
for i, x in enumerate(H):
    for y in H[i + 1:]:
        if x['project'] != y['project'] or not x['tk'] or not y['tk']: continue
        n = len(x['tk'] & y['tk'])
        if n / (len(x['tk']) + len(y['tk']) - n) >= .5: par[find(id(x))] = find(id(y))
comp = collections.Counter(find(id(e)) for e in H)
print('   hits %d -> components %d; largest %s' % (len(H), len(comp), sorted(comp.values(), reverse=True)[:8]))
cw = collections.defaultdict(set)
for e in H: cw[e['week']].add(find(id(e)))
first_week = {}
for e in sorted(H, key=lambda e: e['t_first']): first_week.setdefault(find(id(e)), e['week'])
print('   components first seen per week:', sorted(collections.Counter(first_week.values()).items()))
print('(7) TARGET scripts written by the main agent with >= 3 ok runs (all of them)')
for e in sorted([e for e in TGT if not e['sub_writer'] and e['k'] >= 3], key=lambda e: -e['k']):
    hd = [l for l in e['final'].split('\n') if l.strip() and not l.startswith('#!')][:1]
    print('   ok %3d args %2d turns %2d lines %3d rule %-6s %s/%s | %s' % (e['k'], e['a'], e['t'], e['lines'], 'FIRES' if ship(e) else 'silent', short(e['project'])[:12], e['base'], (hd[0] if hd else '')[:80]))
print('   main-agent TARGET scripts: %d; ok>=1 %d; ok>=2 %d; ok>=3 %d; rule fires %d' % (sum(not e['sub_writer'] for e in TGT), sum(not e['sub_writer'] and e['k'] >= 1 for e in TGT),
      sum(not e['sub_writer'] and e['k'] >= 2 for e in TGT), sum(not e['sub_writer'] and e['k'] >= 3 for e in TGT), sum(not e['sub_writer'] and ship(e) for e in TGT)))
print('(8) misc counts quoted in the report')
print('   created scripts %d, of which every touch came from a subagent: %d; TARGET written by a subagent: %d of %d' % (len(P), sum(e['sub_only'] for e in P), sum(e['sub_writer'] for e in TGT), len(TGT)))
tr = [e for e in TGT if e['copied_home'] or e['git_exact'] or e['git_near']]
print('   to_repo in TARGET: %d; rule fires on %d; written by the main agent %d; one ok run or none %d; median lines %d' % (len(tr), sum(ship(e) for e in tr), sum(not e['sub_writer'] for e in tr), sum(e['k'] <= 1 for e in tr), sorted(e['lines'] for e in tr)[len(tr) // 2]))
