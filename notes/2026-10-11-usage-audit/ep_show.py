"""Render candidates for reading. Usage:
  python3 ep_show.py CAND.jsonl --sample SHAPE N [--seed K] [--per-project M]   stratified random sample
  python3 ep_show.py CAND.jsonl --id ID [ID...]                                  named candidates
Writes text to stdout; candidates are re-read from the cache, nothing is invented."""
import json, sys, random, collections, re
from ep_common import *
from ep_detect import is_edit, cmd, check_key, red

def show(S, c, ctx=1, mid=14, k=1.0):
    s = S[c['si']]; ev = s['ev']; a, b = c['a'], c['b']
    feats = {k: v for k, v in c.items() if k not in ('si', 'project', 'session', 'sub', 'agent', 'entry', 'id', 'shape', 'a', 'b', 'ts')}
    out = ['#' * 110, 'ID %s | %s | %s | %s%s | events %d-%d of %d' % (c['id'], c['project'], (c['ts'] or '')[:16], 'SUB ' if c['sub'] else 'main', '', a, b, len(ev)), 'features ' + json.dumps(feats)]
    # the prompt that started the turn
    p = next((j for j in range(a, -1, -1) if ev[j]['k'] == 'prompt' and not ev[j]['text'].startswith('<task-notification')), None)
    if p is not None and p < a - ctx: out.append('  (turn prompt [%d]) %s' % (p, ev[p]['text'][:350].replace('\n', ' ')))
    idx = list(range(max(0, a - ctx), min(len(ev), b + ctx + 2)))
    inner = [j for j in idx if a < j < b]
    drop = set(inner[mid // 2: len(inner) - mid // 2]) if len(inner) > mid else set()
    cut = False
    for j in idx:
        if j in drop:
            if not cut: out.append('      ... %d events not shown ...' % len(drop)); cut = True
            continue
        e = ev[j]; big = j in (a, b)
        m = '>>' if big else '  '
        if e['k'] == 'prompt': out.append('%s[%d] USER(%s): %s' % (m, j, e['src'], e['text'][:1200 if big else 500].replace('\n', ' ')))
        elif e['k'] == 'text': out.append('%s[%d] ASSISTANT: %s' % (m, j, e['text'][:int(k * (800 if big else 380))].replace('\n', ' ')))
        else:
            r = (e['res'] or '')
            rn = int(k * (600 if big else (220 if (e['err'] or (e['name'] == 'Bash' and check_key(cmd(e)))) else 80)))
            r = r if len(r) <= rn else (r[:rn // 3] + ' ...[cut]... ' + r[-2 * rn // 3:])
            tag = ' ERR' if e['err'] else ''
            if is_edit(e): tag += ' (edit)'
            out.append('%s[%d] %s%s: %s\n        -> %s' % (m, j, e['name'], tag, inp_s(e, int(k * (520 if big else 200))).replace('\n', ' ⏎ '), r.replace('\n', ' | ')))
    return '\n'.join(out)

if __name__ == '__main__':
    C = [json.loads(l) for l in open(sys.argv[1])]; S = load()
    K = float(sys.argv[sys.argv.index('--k') + 1]) if '--k' in sys.argv else 1.0
    MID = int(sys.argv[sys.argv.index('--mid') + 1]) if '--mid' in sys.argv else 14
    _show = show
    show = lambda S, c: _show(S, c, mid=MID, k=K)
    if '--id' in sys.argv:
        ids = set(x for x in sys.argv[3:] if x.startswith(('RG', 'MA', 'DX', 'UC', 'ENV', 'SCR'))); [print(show(S, c)) for c in C if c['id'] in ids]
    else:
        shape, n = sys.argv[3], int(sys.argv[4])
        seed = int(sys.argv[sys.argv.index('--seed') + 1]) if '--seed' in sys.argv else 1
        cap = int(sys.argv[sys.argv.index('--per-project') + 1]) if '--per-project' in sys.argv else 10 ** 9
        skip = set(l.strip() for l in open(sys.argv[sys.argv.index('--skip') + 1])) if '--skip' in sys.argv else set()
        rng = random.Random(seed); pool = [c for c in C if c['shape'] == shape and c['id'] not in skip]; rng.shuffle(pool)
        per = collections.Counter(); pick = []
        for c in pool:
            if per[c['project']] >= cap: continue
            per[c['project']] += 1; pick.append(c)
            if len(pick) >= n: break
        for c in pick: print(show(S, c))
