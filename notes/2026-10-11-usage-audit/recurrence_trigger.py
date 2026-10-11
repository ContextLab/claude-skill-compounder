"""What a trigger on RECURRENCE would fire on: a failed call whose error signature was
already met in an earlier session, followed by a pass of the same tool within six calls.
Fires once for a signature (after that it is a lesson or a decline).

Usage: python3 recurrence_trigger.py [N to print]
Counts per week, per project, and prints a random sample to read."""
import re, sys, collections, random, datetime
from ep_common import *
from ep_recurrence import signature
GENERIC = re.compile(r'^(?:E\s+)?(?:AssertionError|KeyError|Traceback|TypeError|ValueError|IndexError|AttributeError|RuntimeError|NameError|json\.decoder|Found N error|### Error|<PATH>$|Exit code|E  |FAILED|N failed|error: N|Error: N)|^(?:<Q>|N|<PATH>|\W)*$')
REFUSED = re.compile(r"\[compound\]|doesn't want to proceed|was rejected|Request interrupted|InputValidationError|String to replace not found|File has not been read|modified since read|classifier gave no verdict")
S = [s for s in load() if not is_tmp(s)]
rows = []
for s in S:
    ev = s['ev']
    for j, e in enumerate(ev):
        if e['k'] != 'call' or not e['err']: continue
        r = e['res'] or ''
        if REFUSED.search(r[:1200]): continue
        g = signature(r)
        if not g or GENERIC.search(g) or len(g) < 12: continue
        later = [x for x in ev[j + 1:j + 40] if x['k'] == 'call'][:6]
        fixed = next((x for x in later if x['name'] == e['name'] and not x['err']), None)
        rows.append(dict(sig=g, ts=e['ts'] or '', session=s['session'], sub=s['sub'], project=proj(s).replace('(wt)', ''), fixed=fixed is not None, s=s, j=j))
rows.sort(key=lambda r: r['ts'])
seen = collections.defaultdict(set); fired = {}; meetings = collections.Counter()
for r in rows:
    g = r['sig']; meetings[g] += 1
    if g not in fired and r['fixed'] and (seen[g] - {r['session']}):
        fired[g] = dict(r, earlier=len(seen[g] - {r['session']}))
    seen[g].add(r['session'])
F = list(fired.values())
wk = collections.Counter(datetime.date.fromisoformat(f['ts'][:10]).isocalendar()[1] for f in F if f['ts'])
print('signed failures (not generic, not refused):', len(rows), '| distinct signatures:', len(seen), '| met in 2+ sessions:', sum(len(v) > 1 for v in seen.values()))
print('trigger firings (once a signature):', len(F), '| per ISO week:', sorted(wk.items()))
print('by project:', collections.Counter(f['project'] for f in F).most_common(8))
print('in a subagent:', sum(bool(f['sub']) for f in F))
print('meetings of a fired signature AFTER it fired (what a lesson would have met):', sum(meetings[g] for g in fired) - sum(1 + 0 for g in fired) - sum(f['earlier'] for f in F))
random.seed(11)
for f in random.sample(F, min(int(sys.argv[1]) if len(sys.argv) > 1 else 30, len(F))):
    e = f['s']['ev'][f['j']]
    print('--', f['ts'][:10], f['project'][:22], '| earlier sessions', f['earlier'], '| met in all', meetings[f['sig']])
    print('   SIG ', f['sig'])
    print('   CALL', inp_s(e, 150).replace('\n', ' '))
