"""Cross-session recurrence: the same failure text met again in a later session.

Usage: python3 ep_recurrence.py [N]     prints the N most widely recurring failure signatures
A signature is the last line of a failed call's result that reads like an error, with
paths, numbers, hex and quoted names folded. Sessions are parent sessions (a subagent's
failures count for the session that spawned it). Temporary test projects are left out."""
import re, sys, collections, json
from ep_common import *

KEY = re.compile(r"(?i)error|not found|no such|denied|refus|failed|cannot|can't|unable|invalid|unrecognized|no matches|not a |blocked|isolated|outside allowed|exceeds|traceback|unknown|missing|timed out|not permitted|bad substitution")
def signature(res):
    lines = [l.strip() for l in (res or '').split('\n') if l.strip()]
    cand = [l for l in lines if KEY.search(l) and not l.startswith(('File "', 'at ', '^'))]
    if not cand: return None
    # prefer the python exception line, else the first error-like line (the harness and the shell lead with it)
    exc = [l for l in cand if re.match(r'^(?:E\s+)?[A-Za-z_.]*(?:Error|Exception)\b', l)]
    l = (exc[-1] if exc else cand[0])
    l = re.sub(r'^Exit code \d+\s*', '', l) or (cand[1] if len(cand) > 1 else l)
    l = re.sub(r'(?:/[\w.@%+=:,~-]+){2,}/?', '<PATH>', l)
    l = re.sub(r"'[^']{1,80}'|\"[^\"]{1,80}\"|`[^`]{1,80}`", '<Q>', l)
    l = re.sub(r'\b[0-9a-f]{7,}\b', '<HEX>', l); l = re.sub(r'\d+', 'N', l)
    l = re.sub(r'\(eval\):N: ', '', l)
    return l[:110]

def main(n):
    S = load(); sig = collections.defaultdict(list)
    for s in S:
        if is_tmp(s): continue
        for j, e in enumerate(s['ev']):
            if e['k'] == 'call' and e['err']:
                g = signature(e['res'])
                if g: sig[g].append((s['session'], proj(s).replace('(wt)', ''), (e['ts'] or '')[:10], s['file'], j))
    rows = []
    for g, v in sig.items():
        ses = {x[0] for x in v}; pr = {x[1] for x in v}; days = sorted({x[2] for x in v})
        rows.append((len(ses), len(pr), len(v), len(days), days[0], days[-1], g))
    rows.sort(reverse=True)
    tot = sum(len(v) for v in sig.values())
    rec = [r for r in rows if r[0] >= 2]
    print('failed calls with a signature:', tot, '| distinct signatures:', len(rows))
    print('signatures met in >=2 sessions:', len(rec), 'covering', sum(r[2] for r in rec), 'failed calls (%.0f%%)' % (100 * sum(r[2] for r in rec) / tot))
    print('signatures met in >=2 projects:', sum(r[1] >= 2 for r in rows), 'covering', sum(r[2] for r in rows if r[1] >= 2), 'failed calls')
    print('signatures met in >=3 sessions:', sum(r[0] >= 3 for r in rows), 'covering', sum(r[2] for r in rows if r[0] >= 3))
    print('\nsessions projects calls days first last signature')
    for r in rows[:n]: print('%3d %2d %4d %3d %s %s  %s' % r)
    json.dump({g: v for g, v in sig.items() if len({x[0] for x in v}) >= 2}, write_private(os.path.join(CACHE, 'recurrence.json'), 'w'))

if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
