"""Positive set: the lessons a working session recorded. For each, find the episode in the
origin session and say which detector shapes had a candidate there.

Usage: python3 ep_positive_recall.py
The episode is located by the lesson's own literal text: every `backticked` or "quoted" span
of the lesson body (8+ characters) is searched for in the session's calls and results before
the `compound add` call; the events that hold a span are the episode's footprint. A detector
"covers" the lesson when one of its candidates in the same transcript overlaps the footprint
(or, with no footprint, ends within 60 events before the add call).
Sessions named in EP_SKIP_SESSIONS (see ep_common.py) are left out."""
import json, os, re, glob, collections
from ep_common import *
S = load(); C = [json.loads(l) for l in open('ep_candidates.jsonl')]
cand = collections.defaultdict(list)
for c in C: cand[(c['session'], c['agent'])].append(c)
ev = [json.loads(l) for l in open(os.path.expanduser('~/.claude/compound/events.jsonl'))]
learn = [e for e in ev if e['type'] == 'learn' and not skip_session(e['session']) and not e.get('update')]
allev = sorted(ev, key=lambda e: e['ts'])
def body_of(name):
    for f in glob.glob(os.path.expanduser('~/.claude/compound/lessons/%s/SKILL.md' % name)) + glob.glob(os.path.expanduser('~/*/.claude/compound/lessons/%s/SKILL.md' % name)):
        return open(f).read().split('---', 2)[-1]
    return ''
def text_of(e):
    if e['k'] == 'call': return (json.dumps(e['inp']) if e['name'] != 'Bash' else e['inp'].get('command', '')) + '\n' + (e['res'] or '')
    return e['text']
rows = []; cover = collections.Counter(); trig = collections.Counter()
for le in learn:
    name = le['lesson']; body = body_of(name)
    spans = set(x.strip() for x in re.findall(r'`([^`\n]{8,120})`', body)) | set(x.strip() for x in re.findall(r'"([^"\n]{8,120})"', body))
    spans = {x for x in spans if not re.search(r'<[A-Za-z ]+>|OWNER|REPO\b|FILE\b', x)}
    # the add call
    best = None
    for s in S:
        if s['session'] != le['session']: continue
        for j, e in enumerate(s['ev']):
            if e['k'] == 'call' and e['name'] == 'Bash' and name in e['inp'].get('command', '') and 'compound' in e['inp'].get('command', '') and re.search(r'\badd\b', e['inp'].get('command', '')):
                best = (s, j)
    # what the log held just before the learn, in that session: the trigger that produced it
    prior = [e for e in allev if e['session'] == le['session'] and e['ts'] <= le['ts'] and e['type'] in ('capture', 'refuse', 'recall', 'nudge')]
    last = prior[-1] if prior else None
    how = 'settles a capture' if le.get('settles') else None
    foot = collections.defaultdict(list)
    for s in S:
        if s['session'] != le['session']: continue
        lim = best[1] if best and best[0] is s else len(s['ev'])
        for j, e in enumerate(s['ev'][:lim]):
            t = text_of(e)
            if 'compound' in t and ' add ' in t: continue
            n = sum(1 for sp in spans if sp in t)
            if n: foot[(s['session'], s['agent'])].append(j)
    typed = False
    if best:
        s, j = best
        for x in s['ev'][max(0, j - 12):j]:
            if x['k'] == 'prompt' and '/compound:learn' in x['text'] and x['src'] in ('human', 'typed', 'queued'): typed = True
    how = how or ('user typed /compound:learn' if typed else ('after a %s' % (last['type'] + (':' + last.get('why', '') if last['type'] == 'refuse' else '')) if last and (le['ts'] >= last['ts']) else 'unprompted'))
    shapes = set()
    for key, idxs in foot.items():
        for c in cand.get(key, []):
            if any(c['a'] - 3 <= j <= c['b'] + 3 for j in idxs): shapes.add(c['shape'])
    if not foot and best:
        s, j = best
        for c in cand.get((s['session'], s['agent']), []):
            if j - 60 <= c['b'] <= j: shapes.add(c['shape'] + '?')
    rows.append((name, le['ts'][:10], how, len(spans), sum(len(v) for v in foot.values()), sorted(shapes)))
    trig[how.split(':')[0] if how.startswith('after') else how] += 1
    for sh in shapes: cover[sh] += 1
    if not shapes: cover['(none)'] += 1
for r in rows: print('%-44s %s %-28s spans=%-2d footprint=%-3d %s' % r)
print('\nlessons:', len(rows)); print('what produced the add:', dict(trig)); print('lessons whose episode a detector overlaps:', dict(cover))
