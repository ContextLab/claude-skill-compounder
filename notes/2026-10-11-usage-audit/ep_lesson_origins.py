"""For every learn event written by a working session, find the `compound add` call in
the transcript and print what led to it. Usage: python3 ep_lesson_origins.py > out.txt
The output quotes private transcripts: write it outside the repository.
Sessions named in EP_SKIP_SESSIONS (see ep_common.py) are left out."""
import json, os, re, sys, datetime
from ep_common import *
S = load()
ev = [json.loads(l) for l in open(os.path.expanduser('~/.claude/compound/events.jsonl'))]
L = [e for e in ev if e['type'] == 'learn' and not skip_session(e['session'])]
seen = set()
for le in L:
    name = le['lesson']; sid = le['session']
    hits = []
    for s in S:
        if s['session'] != sid: continue
        for j, e in enumerate(s['ev']):
            if e['k'] == 'call' and e['name'] == 'Bash':
                c = e['inp'].get('command', '')
                if 'compound' in c and re.search(r'\badd\b', c) and name in c and not e['err']:
                    hits.append((s, j, e))
    print('=' * 100); print('LESSON', name, le['ts'], sid[:8], 'level', le.get('level'), 'settles', le.get('settles'), 'update', le.get('update'), 'hits', len(hits))
    if not hits: print('  NO add CALL FOUND'); continue
    stamp = lambda x: datetime.datetime.fromisoformat(x.replace('Z', '+00:00')).timestamp()
    best = min(hits, key=lambda h: abs(stamp(h[2]['ts']) - stamp(le['ts'])))   # the add call nearest the learn event in time
    s, j, e = best
    if (s['file'], j) in seen: print('  (same add call as above)'); continue
    seen.add((s['file'], j))
    print('  transcript', s['file'].replace(os.path.expanduser('~'), '~'), 'event', j, 'sub' if s['sub'] else 'main')
    print('  ADD CALL:', e['inp'].get('command', '')[:1500])
    # walk back to the previous typed prompt, at most 60 events; print prompts, text, errors, [compound] messages
    a = j - 1; n = 0
    lines = []
    while a >= 0 and n < 50:
        x = s['ev'][a]
        if x['k'] == 'prompt':
            lines.append('  [%d] USER(%s): %s' % (a, x['src'], x['text'][:700].replace('\n', ' ')))
            if x['src'] in ('typed', 'queued', 'human', '') and not x['text'].startswith('<') and '[compound]' not in x['text'] and len(lines) > 3: break
        elif x['k'] == 'text': lines.append('  [%d] ASSISTANT: %s' % (a, x['text'][:300].replace('\n', ' ')))
        else:
            r = x['res'] or ''
            if x['err'] or '[compound]' in r:
                lines.append('  [%d] %s%s: %s\n        -> %s' % (a, x['name'], ' ERR' if x['err'] else '', inp_s(x, 250).replace('\n', ' '), (r[:350] + ' ... ' + r[-200:] if len(r) > 600 else r).replace('\n', ' | ')))
            elif x['name'] in ('Read','Grep','Glob','TodoWrite','ToolSearch'): pass
            else: lines.append('  [%d] %s ok: %s' % (a, x['name'], inp_s(x, 90).replace('\n', ' ')))
        a -= 1; n += 1
    print('\n'.join(reversed(lines)))
