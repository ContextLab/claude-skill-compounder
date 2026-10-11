#!/usr/bin/env python3
"""Threshold study, step 3: signals and ground-truth labels for every script a real session created.

argv[1] = cache dir (events.pkl, episodes.pkl). Writes table.pkl there. Read-only on every repo
(git rev-parse, ls-files, log --name-only, cat-file --batch-check, show).

Population: stratum home:interactive (cwd under ~, entrypoint cli/vscode/desktop),
created in the session, the session running this study left out (its id prefix is given in the
environment variable TS_SELF_SESSION).
Labels never use the creating agent's own runs of the file:
  redone_x     near-identical script (line-level difflib ratio >= .6 against the later script's FIRST version,
               both >= 5 significant lines, different path) created after this one's last activity
               in a different session
  redone_a     same, by a different agent of the same session (fan-out)
  redo2_x/_a   same, measured by shared vocabulary instead of shared lines (threshold calibrated on a
               cross-project null; see the code), same project only
  name_x/_a    same basename created later in the same project by another session / agent (weak)
  used_x       the same path run in a later session that did not create it
  used_a       run by an agent of the same session other than the one that wrote it
  brief        named (basename) in an Agent/SendMessage brief sent after its creation
  prompt       named (basename) in a person's prompt after its creation (same or later session)
  copied_home  cp/mv from scratch to a path under the home directory
  copied_any   cp/mv anywhere
  git_exact    blob of some version exists in a repository's object store
  git_near     scratch script: a file of the same basename in the project's repository history,
               ratio >= .6 with it
  tracked      in-repo path that is in the repository's history
"""
import os, sys, pickle, re, collections, hashlib, subprocess, difflib, datetime

C = sys.argv[1]
SELF = os.environ.get('TS_SELF_SESSION', '')      # id prefix of the session running this study, left out
D = pickle.load(open(os.path.join(C, 'episodes.pkl'), 'rb'))
EV = pickle.load(open(os.path.join(C, 'events.pkl'), 'rb'))
HOME = os.path.expanduser('~')

def T(ts):
    try: return datetime.datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
    except Exception: return 0.0

def loc(p):
    if 'scratchpad' in p: return 'scratchpad'
    if p.startswith(('/private/tmp', '/private/var/folders')) or '<dyn' in p or '$' in p: return 'tmp'
    if '/.claude/worktrees/' in p: return 'worktree'
    return 'home'

def sig_lines(txt):
    out = []
    for l in txt.split('\n'):
        l = l.strip()
        if len(l) >= 12 and not l.startswith(('#', '//')) and not re.match(r'^(import|from)\s', l): out.append(l)
    return out

def sim(a, b):
    """line-level similarity: difflib ratio over the stripped, non-empty lines"""
    la = [l.strip() for l in a.split('\n') if l.strip()]; lb = [l.strip() for l in b.split('\n') if l.strip()]
    if len(la) > 3000 or len(lb) > 3000: return 0.0
    return difflib.SequenceMatcher(None, la, lb, autojunk=False).ratio()

ALL = [e for e in D['episodes'] if e['stratum'] == 'home:interactive' and not (SELF and e['session'].startswith(SELF))]
POP = [e for e in ALL if e['created']]
for i, e in enumerate(POP):
    e['id'] = i
    e['final'] = e['versions'][-1][1] if e['versions'] else ''
    e['first'] = e['versions'][0][1] if e['versions'] else ''
    e['sl_final'] = set(sig_lines(e['final'])); e['sl_first'] = set(sig_lines(e['first']))
    ts = [r['ts'] for r in e['runs']] + [m[0] for m in e['mods']] + [e['t_first']]
    e['t_last'] = max(ts)
    e['writer'] = e['agents'][0] if e['agents'] else ''
    e['base'] = os.path.basename(e['path']); e['loc'] = loc(e['path'])

# ---------- redone: later near-identical script, other context
inv = collections.defaultdict(set)
for e in POP:
    for l in e['sl_first']: inv[l].add(e['id'])
byid = {e['id']: e for e in POP}
for e in POP:
    e['redone_x'] = e['redone_a'] = False; e['redone_best'] = (0, None)
    if len(e['sl_final']) < 5: continue
    cand = collections.Counter()
    for l in e['sl_final']:
        ids = inv[l]
        if len(ids) > 400: continue   # boilerplate line
        for j in ids: cand[j] += 1
    for j, n in cand.most_common(40):
        y = byid[j]
        if j == e['id'] or y['path'] == e['path'] or y['t_first'] <= e['t_last'] or len(y['sl_first']) < 5: continue
        same_s = y['session'] == e['session']
        if same_s and y['writer'] == e['writer']: continue
        if n / min(len(e['sl_final']), len(y['sl_first'])) < 0.4: continue
        r = sim(e['final'], y['first'])
        if r >= 0.6:
            if same_s: e['redone_a'] = True
            else: e['redone_x'] = True
        if r > e['redone_best'][0]: e['redone_best'] = (round(r, 2), y['path'], 'agent' if same_s else 'session')

# ---------- redone, second measure: shared vocabulary (the same job re-coded differently)
# tokens = identifiers and dotted names of 4+ chars, minus any token found in > 10% of scripts.
# Threshold = the 99.5th percentile of Jaccard between scripts of DIFFERENT projects (the null).
import random
def toks(t): return set(re.findall(r'[A-Za-z_][\w.]{3,}', t))
df = collections.Counter()
for e in POP:
    e['tk_final'] = toks(e['final']); e['tk_first'] = toks(e['first'])
    for t in e['tk_final']: df[t] += 1
common = {t for t, n in df.items() if n > 0.10 * len(POP)}
for e in POP: e['tk_final'] -= common; e['tk_first'] -= common
def jac(a, b):
    i = len(a & b); return i / (len(a) + len(b) - i) if i else 0.0
rng = random.Random(7); big = [e for e in POP if len(e['tk_final']) >= 8 and len(e['tk_first']) >= 8]
null = []
while len(null) < 200000:
    x, y = rng.choice(big), rng.choice(big)
    if x['project'] != y['project']: null.append(jac(x['tk_final'], y['tk_first']))
null.sort(); THETA = max(null[int(0.995 * len(null))], 0.2)
print('vocabulary-overlap threshold (99.5th pct of cross-project null, floor .2): %.3f; null median %.3f; scripts with >= 8 tokens: %d' % (THETA, null[len(null) // 2], len(big)))
order = sorted(big, key=lambda e: e['t_first'])
for e in POP: e['redo2_x'] = e['redo2_a'] = e['name_x'] = e['name_a'] = False; e['redo2_n'] = 0; e['redo2_ex'] = None; e['j_a'] = (0, None); e['j_x'] = (0, None)
byproj = collections.defaultdict(list)
for e in order: byproj[e['project']].append(e)
for lst in byproj.values():
    for i, x in enumerate(lst):
        for y in lst[i + 1:]:
            if y['t_first'] <= x['t_last'] or y['path'] == x['path']: continue
            same_s = y['session'] == x['session']
            if same_s and y['writer'] == x['writer']: continue
            j_ = jac(x['tk_final'], y['tk_first'])
            k_ = 'j_a' if same_s else 'j_x'
            if j_ > x[k_][0]: x[k_] = (round(j_, 3), y['id'])
            if j_ >= THETA:
                x['redo2_n'] += 1
                if x['redo2_ex'] is None: x['redo2_ex'] = y['path']
                if same_s: x['redo2_a'] = True
                else: x['redo2_x'] = True
# same basename, same project, later, other agent or session (weak: generic names collide)
byname = collections.defaultdict(list)
for e in POP: byname[(e['project'], e['base'])].append(e)
for lst in byname.values():
    for x in lst:
        for y in lst:
            if y is x or y['t_first'] <= x['t_last'] or y['path'] == x['path']: continue
            if y['session'] != x['session']: x['name_x'] = True
            elif y['writer'] != x['writer']: x['name_a'] = True
for e in POP: e.pop('tk_final'); e.pop('tk_first')

# ---------- used by another session / agent
bypath = collections.defaultdict(list)
for e in ALL: bypath[e['path']].append(e)
for e in POP:
    e['used_x'] = any(o['session'] != e['session'] and not o['created'] and o['runs'] and o['runs'][0]['ts'] > e['t_first'] for o in bypath[e['path']])
    runners = set()
    for r in e['runs']:
        a = r['sub'] if isinstance(r['sub'], str) else ''
        runners.add(a)
    e['run_agents'] = len(runners)
    e['used_a'] = bool(runners - {e['writer']})
    e['copied_home'] = any(loc(d) == 'home' for _, d, _ in e['copies']) and e['loc'] != 'home'
    e['copied_any'] = bool(e['copies'])

# ---------- named in a brief or a person's prompt after creation
briefs = collections.defaultdict(list)   # (project, session) -> [(ts, text)]
for meta, recs in EV:
    for r in recs:
        if r[0] == 'call' and r[3] in ('Agent', 'Task', 'SendMessage'):
            i = r[4]; txt = ' '.join(str(i.get(k) or '') for k in ('prompt', 'content', 'message'))
            briefs[(meta['project'], meta['session'])].append((T(r[1]), txt))
prompts = collections.defaultdict(list)
for project, sid, strat, ts, turn, src, text in D['prompts']:
    if strat == 'home:interactive' and not text.lstrip().startswith('<'): prompts[project].append((ts, sid, text))
for e in POP:
    pat = re.compile(r'(?<![\w.-])' + re.escape(e['base']) + r'(?![\w])')
    e['brief'] = any(ts > e['t_first'] and pat.search(tx) for ts, tx in briefs[(e['project'], e['session'])])
    hit = [(ts, sid) for ts, sid, tx in prompts[e['project']] if ts > e['t_first'] and pat.search(tx)]
    e['prompt'] = bool(hit); e['prompt_x'] = any(sid != e['session'] for _, sid in hit)

# ---------- git
def git(repo, *a, inp=None):
    try:
        return subprocess.run(['git', '-C', repo] + list(a), input=inp, capture_output=True, text=True, timeout=120).stdout
    except Exception:
        return ''
tops = {}
def top(d):
    while d and d != '/' and not os.path.isdir(d): d = os.path.dirname(d)
    if d not in tops:
        t = git(d, 'rev-parse', '--show-toplevel').strip() if d.startswith(HOME) else ''
        tops[d] = t or None
    return tops[d]
repos = set()
for e in POP:
    e['repo'] = top(os.path.dirname(e['path'])) if e['loc'] in ('home', 'worktree') else None
    e['proj_repo'] = top(e['cwd0']) if e.get('cwd0') else None
    for r in (e['repo'], e['proj_repo']):
        if r: repos.add(r)
hist = {}; blobs = collections.defaultdict(set)
def blob(txt):
    b = txt.encode('utf-8', 'surrogatepass'); return hashlib.sha1(b'blob %d\0' % len(b) + b).hexdigest()
for e in POP:
    e['shas'] = sorted({blob(v) for _, v in e['versions']})
allsha = sorted({s for e in POP for s in e['shas']})
for r in sorted(repos):
    hist[r] = set(x for x in git(r, 'log', '--all', '--format=', '--name-only').split('\n') if x) | set(git(r, 'ls-files').split('\n'))
    out = git(r, 'cat-file', '--batch-check', inp='\n'.join(allsha) + '\n')
    for ln in out.split('\n'):
        p = ln.split()
        if len(p) >= 2 and p[1] == 'blob': blobs[p[0]].add(r)
print('repositories checked', len(repos), 'script blobs found in a repository', len(blobs), 'of', len(allsha))
bybase = {r: collections.defaultdict(list) for r in hist}
for r, ps in hist.items():
    for p in ps: bybase[r][os.path.basename(p)].append(p)
showc = {}
def show(r, p):
    if (r, p) not in showc:
        h = git(r, 'log', '--all', '-1', '--format=%H', '--', p).strip()
        showc[(r, p)] = git(r, 'show', '%s:%s' % (h, p)) if h else ''
    return showc[(r, p)]
for e in POP:
    e['git_exact'] = any(s in blobs for s in e['shas'])
    e['tracked'] = False; e['git_near'] = False; e['wt_copy'] = False
    if e['repo']:
        rel = os.path.relpath(e['path'], e['repo'])
        e['tracked'] = rel in hist[e['repo']]
    elif e['proj_repo']:
        r = e['proj_repo']; parts = e['path'].split('/')
        # a scratch checkout of the project: the path ends in a repository path of 2+ components
        for k in range(2, 7):
            if len(parts) > k and '/'.join(parts[-k:]) in hist[r]: e['wt_copy'] = True
        for p in bybase[r].get(e['base'], [])[:6]:
            c = show(r, p)
            if c and e['final'] and sim(e['final'], c) >= 0.6: e['git_near'] = True; break

# ---------- signals (creating session only)
for e in POP:
    R = e['runs']; ok = [r for r in R if not r['err'] and not r['soft'] and not r['intr']]
    e['n_runs'] = len(R); e['n_ok'] = len(ok)
    e['n_ok_nobg'] = len([r for r in ok if not r['bg']])
    first_ok = min((r['ts'] for r in ok), default=None)
    e['fail_before_ok'] = bool(ok) and any(r['ts'] < first_ok and (r['err'] or r['soft']) for r in R)
    e['any_fail'] = any(r['err'] or r['soft'] for r in R)
    e['n_mods'] = max(0, len(e['mods']) - 1)
    e['mods_after_run'] = len([m for m in e['mods'] if R and m[0] > R[0]['ts']])
    e['lines'] = e['final'].count('\n'); e['bytes'] = len(e['final'])
    e['run_turns'] = len({r['turn'] for r in R}); e['ok_turns'] = len({r['turn'] for r in ok})
    e['span'] = (R[-1]['ts'] - R[0]['ts']) if R else 0
    e['ok_span'] = (ok[-1]['ts'] - ok[0]['ts']) if ok else 0
    e['arg_sets'] = len({r['args'] for r in R}); e['ok_arg_sets'] = len({r['args'] for r in ok})
    e['takes_args'] = bool(re.search(r'sys\.argv|argparse|\$1\b|\$@|"\$\{?1|process\.argv|getopts|click\.', e['final']))
    last_mod = e['mods'][-1][0] if e['mods'] else 0
    e['ok_final'] = len([r for r in ok if r['ts'] >= last_mod])
    e['last_ok'] = bool(R) and R[-1] in ok
    e['sub_writer'] = e['writer'] != ''
    b = e['base']
    e['is_test'] = bool(re.match(r'^(test_.*|.*_test|.*\.test|conftest)\.\w+$', b)) or '/tests/' in e['path'] or '/test/' in e['path'] or any(r['kind'] == 'pytest' for r in R)
    e['removed_flag'] = e['removed'] is not None
    e['week'] = datetime.datetime.utcfromtimestamp(e['t_first']).strftime('%G-W%V')
    e['day'] = datetime.datetime.utcfromtimestamp(e['t_first']).strftime('%Y-%m-%d')
    for k in ('sl_final', 'sl_first'): e.pop(k)
pickle.dump(POP, open(os.path.join(C, 'table.pkl'), 'wb'))
print('population (created scripts, real interactive sessions, this session left out):', len(POP))
print('by location:', dict(collections.Counter(e['loc'] for e in POP)))
for k in ('redone_x', 'redone_a', 'redo2_x', 'redo2_a', 'name_x', 'name_a', 'used_x', 'used_a', 'brief', 'prompt', 'prompt_x', 'copied_home', 'copied_any', 'git_exact', 'git_near', 'tracked', 'wt_copy', 'is_test'):
    print(f'{k:12s}', sum(bool(e[k]) for e in POP), dict(collections.Counter(e['loc'] for e in POP if e[k])))
