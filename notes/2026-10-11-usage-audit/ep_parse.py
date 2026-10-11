"""Parse every Claude Code transcript into a normalised event list and cache it.

Usage: python3 ep_parse.py CACHE_DIR
Reads ~/.claude/projects/**/*.jsonl (read-only). Writes CACHE_DIR/sessions.pkl:
a list of dicts {file, project, session, sub, entry, start, end, ev:[...]}.
Events, in file order:
  {'k':'prompt','ts','text','src'}            a typed (or sdk) prompt
  {'k':'text','ts','text'}                    assistant prose
  {'k':'call','ts','id','name','inp','err','res'}  a tool call joined to its result
"""
import json, os, glob, sys, pickle, re

ROOT = os.path.expanduser('~/.claude/projects')

def clip(s, n=2500):
    return s if len(s) <= 2 * n else s[:n] + '\n...[%d chars cut]...\n' % (len(s) - 2 * n) + s[-n:]

def flat(r):
    if isinstance(r, str): return r
    if isinstance(r, list):
        return '\n'.join(x.get('text', '') if isinstance(x, dict) and x.get('type') == 'text' else ('[%s]' % x.get('type') if isinstance(x, dict) else str(x)) for x in r)
    return '' if r is None else json.dumps(r)

def parse(f):
    ev = []; calls = {}; entry = None; start = end = None; cwd = None
    for l in open(f, errors='ignore'):
        try: d = json.loads(l)
        except Exception: continue
        t = d.get('type')
        if t not in ('user', 'assistant'): continue
        ts = d.get('timestamp'); entry = entry or d.get('entrypoint'); cwd = cwd or d.get('cwd')
        if ts: start = start or ts; end = ts
        c = (d.get('message') or {}).get('content')
        if t == 'user' and isinstance(c, str):
            if d.get('isMeta') or d.get('isCompactSummary'): continue
            ev.append({'k': 'prompt', 'ts': ts, 'text': c, 'src': d.get('promptSource') or d.get('turnOrigin') or ''})
            continue
        if not isinstance(c, list): continue
        for b in c:
            if not isinstance(b, dict): continue
            bt = b.get('type')
            if bt == 'text' and t == 'assistant':
                if b.get('text', '').strip(): ev.append({'k': 'text', 'ts': ts, 'text': b['text']})
            elif bt == 'text' and t == 'user':
                if d.get('isMeta') or d.get('isCompactSummary'): continue
                tx = b.get('text', '')
                if tx.strip(): ev.append({'k': 'prompt', 'ts': ts, 'text': tx, 'src': d.get('promptSource') or ''})
            elif bt == 'tool_use':
                e = {'k': 'call', 'ts': ts, 'id': b.get('id'), 'name': b.get('name'), 'inp': b.get('input') or {}, 'err': None, 'res': None}
                calls[b.get('id')] = e; ev.append(e)
            elif bt == 'tool_result':
                e = calls.get(b.get('tool_use_id'))
                if e is not None:
                    e['err'] = bool(b.get('is_error')); e['res'] = clip(flat(b.get('content'))); e['rts'] = ts
    return entry, cwd, start, end, ev

def main(out):
    files = glob.glob(ROOT + '/*/*.jsonl') + glob.glob(ROOT + '/*/*/subagents/*.jsonl')
    S = []
    for i, f in enumerate(sorted(files)):
        rel = os.path.relpath(f, ROOT).split(os.sep)
        entry, cwd, start, end, ev = parse(f)
        if not ev: continue
        S.append({'file': f, 'project': rel[0], 'session': rel[1].replace('.jsonl', ''), 'sub': len(rel) > 2,
                  'agent': rel[-1].replace('.jsonl', '') if len(rel) > 2 else None,
                  'entry': entry, 'cwd': cwd, 'start': start, 'end': end, 'ev': ev})
    pickle.dump(S, open(os.path.join(out, 'sessions.pkl'), 'wb'))
    print(len(files), 'files', len(S), 'with events', sum(len(s['ev']) for s in S), 'events')

if __name__ == '__main__':
    main(sys.argv[1])
