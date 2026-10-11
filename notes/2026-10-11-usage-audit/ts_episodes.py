#!/usr/bin/env python3
"""Threshold study, step 2: build one record per (session, script file).

argv[1] = cache dir holding events.pkl; writes episodes.pkl there and prints population counts.
A "script" is a file with a script extension. An episode exists when the session touched the
file by Write, here-document, Edit, or a run. `created` says the session made the file new.
Signals are computed ONLY from the creating session (its subagents included).
"""
import os, sys, pickle, re, collections, datetime
import ts_shell as sh

HOME_KEY = re.sub(r'[^A-Za-z0-9]', '-', os.path.expanduser('~'))      # how a project directory under the home directory is named

C = sys.argv[1]
res = pickle.load(open(os.path.join(C, 'events.pkl'), 'rb'))

def T(ts):
    try: return datetime.datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
    except Exception: return 0.0

FAIL_TXT = re.compile(r'Traceback \(most recent call last\)|command not found|No such file or directory|SyntaxError|: line \d+: .*(error|not found)|ModuleNotFoundError|Permission denied|can\'t open file')

sessions = collections.defaultdict(lambda: dict(recs=[], meta=None, subs=0))
for meta, recs in res:
    s = sessions[(meta['project'], meta['session'])]
    if meta['sub']: s['subs'] += 1
    else: s['meta'] = meta
    for r in recs:
        if r[0] == 'prompt' and meta['sub']: continue
        s['recs'].append((r[1], os.path.basename(meta['path'])[:-6] if meta['sub'] else '', r))

def stratum(project, entry):
    real_dir = project.startswith(HOME_KEY)
    inter = entry in ('cli', 'claude-vscode', 'claude-desktop')
    return ('home' if real_dir else 'tmp') + ':' + ('interactive' if inter else 'sdk')

episodes = []; sess_info = {}; prompts_all = []
for (project, sid), s in sessions.items():
    meta = s['meta'] or {}
    recs = sorted(s['recs'], key=lambda x: x[0])  # stable
    if not recs: continue
    strat = stratum(project, meta.get('entry'))
    env = {}; turn = 0; files = {}; n_calls = 0
    t0, t1 = T(recs[0][0]), T(recs[-1][0])
    def ep(path):
        e = files.get(path)
        if e is None:
            e = files[path] = dict(project=project, session=sid, stratum=strat, path=path, created=None, how=None,
                                   versions=[], mods=[], runs=[], copies=[], removed=None, chmod=False, t_first=None, sub_only=True, agents=[])
        return e
    def touch(e, ts, sub):
        if e['t_first'] is None: e['t_first'] = ts
        if not sub: e['sub_only'] = False
        if sub not in e['agents']: e['agents'].append(sub)
    for ts_s, sub, r in recs:
        ts = T(ts_s)
        if r[0] == 'prompt':
            # a turn starts at a prompt a person sent: not a task notification, hook text or slash-command echo
            if r[3] != 'system' and not r[2].lstrip().startswith('<'):
                turn += 1; prompts_all.append((project, sid, strat, ts, turn, r[3], r[2]))
            continue
        _, _, cid, name, inp, err, out, cwd, extra = r
        n_calls += 1
        if name in ('Write', 'Edit', 'MultiEdit'):
            p = inp.get('file_path') or ''
            if not sh.is_script(p): continue
            p = sh.norm(p, cwd)
            if err: continue
            e = ep(p); touch(e, ts, sub)
            if name == 'Write':
                if e['created'] is None and not e['versions'] and not e['runs']:
                    e['created'] = extra.get('type') != 'update'; e['how'] = 'Write'
                elif e['created'] is None: e['created'] = False
                e['versions'].append((ts, inp.get('content') or ''))
                e['mods'].append((ts, 'write', turn, sub))
            else:
                if e['created'] is None: e['created'] = False
                cur = e['versions'][-1][1] if e['versions'] else None
                eds = inp.get('edits') or [inp]
                if cur is not None:
                    for ed in eds:
                        o, n = ed.get('old_string') or '', ed.get('new_string') or ''
                        cur = cur.replace(o, n) if ed.get('replace_all') else cur.replace(o, n, 1)
                    e['versions'].append((ts, cur))
                e['mods'].append((ts, 'edit', turn, sub))
            continue
        if name != 'Bash': continue
        cmd = inp.get('command') or ''
        try:
            pr = sh.parse(cmd, cwd, env)
        except Exception as ex:
            continue
        bg = bool(inp.get('run_in_background') or extra.get('backgroundTaskId'))
        soft_fail = bool(FAIL_TXT.search(out or ''))
        for p, body, app in pr['writes']:
            if not sh.is_script(p): continue
            e = ep(p); touch(e, ts, sub)
            if err and not pr['runs']: continue
            if e['created'] is None and not e['versions'] and not e['runs']:
                e['created'] = not app; e['how'] = 'heredoc'
            elif e['created'] is None: e['created'] = False
            prev = e['versions'][-1][1] if (app and e['versions']) else ''
            e['versions'].append((ts, prev + body)); e['mods'].append((ts, 'heredoc', turn, sub))
        for p in pr['sed']:
            if p in files: files[p]['mods'].append((ts, 'sed', turn, sub))
        byb = None
        for p, args, kind in pr['runs']:
            e = files.get(p)
            if e is None:
                # fall back: unique basename among this session's scripts
                if byb is None:
                    byb = collections.defaultdict(list)
                    for q in files: byb[os.path.basename(q)].append(q)
                c = byb.get(os.path.basename(p), [])
                if len(c) == 1 and ('<dyn' in p or '$' in p): e = files[c[0]]
                elif sh.is_script(p): e = ep(p)
                else: continue
            touch(e, ts, sub)
            if e['created'] is None and not e['versions']: e['created'] = False
            e['runs'].append(dict(ts=ts, turn=turn, err=bool(err), soft=soft_fail, bg=bg, intr=bool(extra.get('interrupted')),
                                  args=args, kind=kind, ver=len(e['versions']), nmods=len(e['mods']), sub=sub, cmd=cmd[:600], out=(out or '')[-400:]))
        for src, dst, op in pr['copies']:
            if src in files: files[src]['copies'].append((ts, dst, op))
        for p in pr['removes']:
            if p in files: files[p]['removed'] = ts
            else:
                for q in files:
                    if q.startswith(p.rstrip('/') + '/') and p.count('/') > 2: files[q]['removed'] = ts
        for p in pr['chmods']:
            if p in files: files[p]['chmod'] = True
    sess_info[(project, sid)] = dict(stratum=strat, t0=t0, t1=t1, turns=turn, calls=n_calls, entry=meta.get('entry'), cwd0=meta.get('cwd0'), subs=s['subs'])
    for e in files.values():
        e['cwd0'] = meta.get('cwd0'); e['s_t0'] = t0; e['s_t1'] = t1; e['s_turns'] = turn
        episodes.append(e)

pickle.dump(dict(episodes=episodes, sessions=sess_info, prompts=prompts_all), open(os.path.join(C, 'episodes.pkl'), 'wb'))
cnt = collections.Counter()
for e in episodes:
    cnt[(e['stratum'], 'created' if e['created'] else 'pre-existing', 'run' if e['runs'] else 'never run')] += 1
print('sessions', len(sess_info), collections.Counter(v['stratum'] for v in sess_info.values()))
for k, v in sorted(cnt.items()): print(k, v)
print('user prompts (non-system, parent transcripts)', len(prompts_all))
