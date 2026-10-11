#!/usr/bin/env python3
"""Threshold study, step 1: reduce every Claude Code transcript to the records the study needs.

Reads ~/.claude/projects/**/*.jsonl (read-only). Writes one pickle to the cache directory
given as argv[1] (kept OUT of the repository: it holds script bodies and prompts).

Per transcript file it keeps, in file order:
  ('prompt', ts, text, source)            a typed/sdk user prompt (not a tool result, not meta)
  ('call', ts, id, name, input, is_error, result_text (first and last 1500 chars), cwd, extra)
A subagent transcript (<project>/<session>/subagents/*.jsonl) is attributed to its parent
session. Tool-use ids are de-duplicated across files (a resumed session copies history):
the copy with the earliest timestamp wins, ties broken by file path.
"""
import json, os, sys, glob, pickle, multiprocessing as mp
ROOT = os.path.expanduser('~/.claude/projects')
KEEP = {'Bash', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Agent', 'Task', 'SendMessage'}

def one(path):
    rel = os.path.relpath(path, ROOT).split(os.sep)
    project = rel[0]
    session = rel[1][:-6] if len(rel) == 2 else rel[1]
    sub = len(rel) > 2
    calls, order, recs = {}, [], []
    meta = {'project': project, 'session': session, 'sub': sub, 'path': path, 'entry': None, 'cwd0': None,
            'n_tool': 0, 'first': None, 'last': None}
    try:
        fh = open(path, errors='ignore')
    except OSError:
        return meta, []
    for line in fh:
        if '"type":"user"' not in line and '"type":"assistant"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get('type')
        if t not in ('user', 'assistant'):
            continue
        ts = d.get('timestamp') or ''
        if ts:
            meta['first'] = meta['first'] or ts; meta['last'] = ts
        meta['entry'] = meta['entry'] or d.get('entrypoint')
        meta['cwd0'] = meta['cwd0'] or d.get('cwd')
        c = (d.get('message') or {}).get('content')
        if t == 'user' and isinstance(c, str):
            if not d.get('isMeta') and not d.get('isCompactSummary'):
                recs.append(['prompt', ts, c[:6000], d.get('promptSource') or d.get('userType')])
            continue
        if not isinstance(c, list):
            continue
        texts = []
        for b in c:
            if not isinstance(b, dict):
                continue
            bt = b.get('type')
            if bt == 'tool_use':
                meta['n_tool'] += 1
                if b.get('name') in KEEP:
                    r = ['call', ts, b.get('id'), b.get('name'), b.get('input') or {}, None, '', d.get('cwd'), {}]
                    calls[b.get('id')] = r; recs.append(r)
            elif bt == 'tool_result':
                r = calls.get(b.get('tool_use_id'))
                if r is not None:
                    rc = b.get('content')
                    rc = rc if isinstance(rc, str) else json.dumps(rc)
                    rc = rc or ''
                    r[5] = bool(b.get('is_error')); r[6] = rc if len(rc) <= 3000 else rc[:1500] + '\n...\n' + rc[-1500:]
                    tur = d.get('toolUseResult')
                    if isinstance(tur, dict):
                        r[8] = {k: tur.get(k) for k in ('interrupted', 'backgroundTaskId', 'type') if tur.get(k)}
                    r[8]['rts'] = ts
            elif bt == 'text' and t == 'user':
                texts.append(b.get('text') or '')
        if t == 'user' and texts and not d.get('isMeta') and not d.get('isCompactSummary'):
            recs.append(['prompt', ts, '\n'.join(texts)[:6000], d.get('promptSource') or d.get('userType')])
    return meta, recs

if __name__ == '__main__':
    out = sys.argv[1]
    files = sorted(glob.glob(ROOT + '/*/*.jsonl') + glob.glob(ROOT + '/*/*/subagents/**/*.jsonl', recursive=True))
    with mp.Pool(8) as p:
        res = p.map(one, files, chunksize=8)
    # de-duplicate tool ids across files
    seen = {}
    for fi, (meta, recs) in enumerate(res):
        for r in recs:
            if r[0] == 'call':
                k = r[2]; cur = seen.get(k)
                if cur is None or (r[1], meta['path']) < cur[0]:
                    seen[k] = ((r[1], meta['path']), fi)
    dup = 0
    for fi, (meta, recs) in enumerate(res):
        keep = []
        for r in recs:
            if r[0] == 'call' and seen[r[2]][1] != fi:
                dup += 1; continue
            keep.append(r)
        recs[:] = keep
    pickle.dump(res, open(os.path.join(out, 'events.pkl'), 'wb'))
    print('transcript files', len(files), 'of which subagent', sum(m['sub'] for m, _ in res))
    print('kept calls', sum(sum(r[0] == 'call' for r in recs) for _, recs in res), 'duplicate calls dropped', dup)
    print('prompts', sum(sum(r[0] == 'prompt' for r in recs) for _, recs in res))
    fs = [m['first'] for m, _ in res if m['first']]
    print('first timestamp', min(fs), 'last', max(m['last'] for m, _ in res if m['last']))
