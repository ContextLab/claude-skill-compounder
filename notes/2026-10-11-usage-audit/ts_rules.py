#!/usr/bin/env python3
"""Threshold study, step 4: measure candidate rules against the labels.
argv[1] = cache dir (table.pkl). Options: --drop SESSIONPREFIX (leave a session out), --j 0.5 (redo threshold).
Prints every table the report quotes."""
import os, sys, pickle, re, collections, datetime, argparse
HOME_KEY = re.sub(r'[^A-Za-z0-9]', '-', os.path.expanduser('~')) + '-'      # how a project directory under the home directory is named
short = lambda p: p[len(HOME_KEY):] if p.startswith(HOME_KEY) else p
ap = argparse.ArgumentParser(); ap.add_argument('cache'); ap.add_argument('--drop', default=''); ap.add_argument('--j', type=float, default=0.5)
ap.add_argument('--section', default='all')
A = ap.parse_args()
P = pickle.load(open(os.path.join(A.cache, 'table.pkl'), 'rb'))
if A.drop: P = [e for e in P if not e['session'].startswith(A.drop)]
PROBE = re.compile(r'^(probe|dbg|debug|tmp|temp|repro|scratch|try|t\d|x\d|foo|a|b|q|h|peek|show|look|see|diag|inspect|patch|fix|edit|apply|chk|check|test|smoke|verify)[\w-]*\.\w+$|^[a-z]{1,2}\d*\.\w+$', re.I)

def sig(e, own):
    """signals from all the session's runs (own=False) or only the writing agent's (own=True)"""
    R = [r for r in e['runs'] if (not own or r['sub'] == e['writer'])]
    ok = [r for r in R if not r['err'] and not r['soft'] and not r['intr']]
    s = {}
    s['n_runs'] = len(R); s['n_ok'] = len(ok)
    f = min((r['ts'] for r in ok), default=None)
    s['fail_first'] = bool(ok) and any(r['ts'] < f and (r['err'] or r['soft']) for r in R)
    s['turns'] = len({r['turn'] for r in ok})
    s['span'] = ok[-1]['ts'] - ok[0]['ts'] if ok else 0
    s['argsets'] = len({r['args'] for r in ok})
    last_mod = max((m[0] for m in e['mods'] if (not own or m[3] == e['writer'])), default=0)
    s['ok_final'] = len([r for r in ok if r['ts'] >= last_mod])
    M = [m for m in e['mods'] if (not own or m[3] == e['writer'])]
    s['mods'] = max(0, len(M) - 1); s['mods_after_run'] = len([m for m in M if R and m[0] > R[0]['ts']]); s['lines'] = e['lines']
    s['takes_args'] = e['takes_args']; s['probe_name'] = bool(PROBE.match(e['base'])); s['sub_writer'] = e['sub_writer']
    s['removed'] = e['removed_flag']; s['chmod'] = e['chmod']
    s['mutator'] = bool(re.search(r'\.write_text\(|open\([^)]*[\'"]w[\'"]\)[^\n]*\n?[^\n]*replace\(|\.replace\([^\n]*\n[^\n]*write', e['final'])) and 'argv' not in e['final']
    return s

for e in P:
    e['S'] = sig(e, False); e['W'] = sig(e, True)
    e['redo'] = max(e['j_a'][0], e['j_x'][0]) >= A.j
    e['redo_x'] = e['j_x'][0] >= A.j
    e['redo_loose'] = max(e['j_a'][0], e['j_x'][0]) >= 0.4
    e['to_repo'] = e['copied_home'] or ((e['git_exact'] or e['git_near']) and e['loc'] in ('scratchpad', 'tmp'))
    e['reused'] = e['used_a'] or e['used_x']
    e['named'] = e['brief'] or e['prompt']
    e['KEEP'] = e['redo'] or e['reused'] or e['named'] or e['to_repo']
    e['KEEP_noleak'] = e['redo'] or e['to_repo'] or e['prompt']      # nothing that another agent's run or brief can cause
    e['kept_by_git'] = e['tracked'] or e['wt_copy'] or e['loc'] == 'worktree' or (e['loc'] == 'home' and e['git_exact'])

LABELS = ['KEEP', 'KEEP_noleak', 'redo', 'redo_x', 'redo_loose', 'reused', 'named', 'to_repo']
print('== population ==')
print('created scripts:', len(P), ' sessions:', len({e['session'] for e in P}), ' projects:', len({e['project'] for e in P}))
print('never run:', sum(not e['runs'] for e in P))
c = collections.Counter((e['loc'], 'kept by git' if e['kept_by_git'] else 'not in git', 'test' if e['is_test'] else 'script') for e in P)
for k, v in sorted(c.items()): print('  ', k, v)
TGT = [e for e in P if not e['kept_by_git'] and not e['is_test'] and e['loc'] in ('scratchpad', 'tmp')]
OUT = [e for e in P if e not in TGT]
print('TARGET = scratch or tmp, not a checkout of the repository, not a test file:', len(TGT), ' of which run at least once:', sum(bool(e['runs']) for e in TGT))
print('  in-repo/home scripts left out:', len(OUT), ' of which tracked/in git now:', sum(e['kept_by_git'] for e in OUT),
      ' home, not in git:', sum(e['loc'] == 'home' and not e['kept_by_git'] for e in OUT))
print('label sizes in TARGET:', {l: sum(e[l] for e in TGT) for l in LABELS})
print('  parts: used_a %d used_x %d brief %d prompt %d copied_home %d git_exact %d git_near %d redone(line-level .6) %d' % (tuple(
    sum(bool(e[k]) for e in TGT) for k in ('used_a', 'used_x', 'brief', 'prompt', 'copied_home', 'git_exact', 'git_near')) + (sum(e['redone_a'] or e['redone_x'] for e in TGT),)))
print('TARGET by session:'); cs = collections.Counter(short(e['project'])[:24] + ' ' + e['session'][:8] for e in TGT)
ck = collections.Counter(short(e['project'])[:24] + ' ' + e['session'][:8] for e in TGT if e['KEEP'])
for k, v in cs.most_common(12): print('   %-36s %5d  KEEP %4d (%.0f%%)' % (k, v, ck[k], 100 * ck[k] / v))

RULES = collections.OrderedDict()
def rule(name, f): RULES[name] = f
rule('any created script', lambda s: True)
for n in (1, 2, 3, 4, 5, 8): rule('ok runs >= %d' % n, lambda s, n=n: s['n_ok'] >= n)
rule('failure before first success', lambda s: s['fail_first'])
rule('ok>=1, no failure before', lambda s: s['n_ok'] >= 1 and not s['fail_first'])
for n in (1, 2, 3): rule('rewrites >= %d' % n, lambda s, n=n: s['mods'] >= n and s['n_ok'] >= 1)
rule('rewritten after a run', lambda s: s['mods_after_run'] >= 1 and s['n_ok'] >= 1)
for n in (20, 40, 80, 150): rule('lines >= %d (and ok>=1)' % n, lambda s, n=n: s['lines'] >= n and s['n_ok'] >= 1)
rule('lines < 20 (and ok>=1)', lambda s: s['lines'] < 20 and s['n_ok'] >= 1)
rule('ok in >= 2 turns', lambda s: s['turns'] >= 2)
for n, lab in ((60, '1 min'), (600, '10 min'), (3600, '1 h')): rule('span first..last ok >= %s' % lab, lambda s, n=n: s['span'] >= n)
for n in (2, 3, 5): rule('distinct arg sets >= %d' % n, lambda s, n=n: s['argsets'] >= n)
rule('reads its arguments (static) & ok>=1', lambda s: s['takes_args'] and s['n_ok'] >= 1)
rule('reads arguments & ok>=2', lambda s: s['takes_args'] and s['n_ok'] >= 2)
rule('final version ok >= 2', lambda s: s['ok_final'] >= 2)
rule('final version ok >= 3', lambda s: s['ok_final'] >= 3)
rule('probe-like name & ok>=1', lambda s: s['probe_name'] and s['n_ok'] >= 1)
rule('not probe-like name & ok>=1', lambda s: not s['probe_name'] and s['n_ok'] >= 1)
rule('chmod +x', lambda s: s['chmod'])
rule('written by main agent & ok>=1', lambda s: not s['sub_writer'] and s['n_ok'] >= 1)
rule('ok>=3 OR argsets>=2', lambda s: s['n_ok'] >= 3 or s['argsets'] >= 2)
rule('ok>=2 AND argsets>=2 (same thing)', lambda s: s['n_ok'] >= 2 and s['argsets'] >= 2)
rule('ok>=3 AND argsets==1', lambda s: s['n_ok'] >= 3 and s['argsets'] == 1)
rule('ok>=2 AND argsets==1', lambda s: s['n_ok'] >= 2 and s['argsets'] == 1)
rule('argsets>=2 AND reads arguments', lambda s: s['argsets'] >= 2 and s['takes_args'])
rule('argsets>=2 OR (ok>=3 AND not probe name)', lambda s: s['argsets'] >= 2 or (s['n_ok'] >= 3 and not s['probe_name']))
rule('argsets>=2 OR ok>=5', lambda s: s['argsets'] >= 2 or s['n_ok'] >= 5)
rule('argsets>=2 OR ok in >=2 turns', lambda s: s['argsets'] >= 2 or s['turns'] >= 2)
rule('argsets>=2 OR final ok>=3', lambda s: s['argsets'] >= 2 or s['ok_final'] >= 3)
rule('(argsets>=2 OR final ok>=3) AND not mutator', lambda s: (s['argsets'] >= 2 or s['ok_final'] >= 3) and not s['mutator'])
rule('mutator (rewrites other files, no argv) & ok>=1', lambda s: s['mutator'] and s['n_ok'] >= 1)

def table(pop, key, labels, title):
    print('\n== %s (n=%d; signals from %s) ==' % (title, len(pop), 'the writing agent only' if key == 'W' else 'every run in the session'))
    base = {l: sum(e[l] for e in pop) for l in labels}
    print('%-46s %5s' % ('rule', 'hits') + ''.join('  %-22s' % (l + ' P / R') for l in labels))
    for name, f in RULES.items():
        H = [e for e in pop if f(e[key])]
        row = '%-46s %5d' % (name, len(H))
        for l in labels:
            tp = sum(e[l] for e in H)
            row += '  %4d %5.1f%% / %5.1f%% ' % (tp, 100 * tp / len(H) if H else 0, 100 * tp / base[l] if base[l] else 0)
        print(row)
    return base

if A.section in ('all', 'rules'):
    table(TGT, 'S', ['KEEP', 'redo', 'reused', 'named', 'to_repo'], 'TARGET, all labels')
    table(TGT, 'W', ['KEEP', 'KEEP_noleak', 'redo', 'redo_x', 'redo_loose', 'to_repo'], 'TARGET, leak-free signals')
    HM = [e for e in P if e['loc'] == 'home' and not e['is_test']]
    table(HM, 'S', ['kept_by_git', 'KEEP'], 'scripts created under the home directory (repositories), not tests')

if A.section in ('all', 'main'):
    MA = [e for e in TGT if not e['sub_writer']]
    table(MA, 'W', ['KEEP', 'to_repo', 'named', 'reused', 'redo'], 'TARGET scripts written by the main agent')
    SA = [e for e in TGT if e['sub_writer']]
    print('TARGET scripts written by a subagent: %d; label sizes %s' % (len(SA), {l: sum(e[l] for e in SA) for l in LABELS}))

if A.section in ('all', 'dose'):
    print('\n== dose-response in TARGET (writing agent only): share with each label ==')
    def bins(name, f, edges):
        print(name)
        for lo, hi in zip(edges, edges[1:]):
            H = [e for e in TGT if lo <= f(e) < hi]
            if H: print('   [%s,%s) n=%4d  KEEP %5.1f%%  noleak %5.1f%%  redo %5.1f%%  to_repo %5.1f%%' % (lo, hi, len(H), *(100 * sum(e[l] for e in H) / len(H) for l in ('KEEP', 'KEEP_noleak', 'redo', 'to_repo'))))
    inf = 10 ** 9
    bins('ok runs', lambda e: e['W']['n_ok'], [0, 1, 2, 3, 4, 5, 8, inf])
    bins('distinct arg sets among ok runs', lambda e: e['W']['argsets'], [0, 1, 2, 3, 5, inf])
    bins('rewrites', lambda e: e['W']['mods'], [0, 1, 2, 3, inf])
    bins('lines', lambda e: e['lines'], [0, 10, 20, 40, 80, 150, inf])
    bins('turns with an ok run', lambda e: e['W']['turns'], [0, 1, 2, 3, inf])
    bins('span seconds', lambda e: e['W']['span'], [0, 1, 60, 600, 3600, inf])

if A.section in ('all', 'ship'):
    SHIP = RULES['argsets>=2 OR final ok>=3']
    print('\n== shipped-rule detail ==')
    H = [e for e in TGT if SHIP(e['S'])]
    print('hits in TARGET (all session runs):', len(H), ' KEEP', sum(e['KEEP'] for e in H))
    wk = collections.Counter(e['week'] for e in H); wa = collections.Counter(e['week'] for e in TGT)
    days = collections.Counter(e['day'] for e in TGT)
    print('per ISO week (hits / target scripts):', [(w, wk[w], wa[w]) for w in sorted(wa)])
    print('active days with a target script:', len(days))
    print('hits by session:', collections.Counter(short(e['project'])[:20] + ' ' + e['session'][:8] for e in H).most_common(12))
    print('hits by basename (top):', collections.Counter(e['base'] for e in H).most_common(15))
    # the same rule on what git already keeps
    for nm, pop in (('home, kept by git', [e for e in P if e['loc'] in ('home', 'worktree') and e['kept_by_git']]),
                    ('home, not in git', [e for e in P if e['loc'] == 'home' and not e['kept_by_git']]),
                    ('test files anywhere', [e for e in P if e['is_test']]),
                    ('scratch checkout of the repository', [e for e in P if e['wt_copy']])):
        print('  rule fires on %-36s %4d of %4d' % (nm, sum(SHIP(e['S']) for e in pop), len(pop)))
