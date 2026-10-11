"""Tables for episode-study.md. Usage: python3 ep_stats.py
EP_FOCUS_PROJECT (environment, optional): the start of the name of the one project that
holds most of the corpus (project A in the report); its rows are set against the rest."""
import json, collections, datetime, os
from ep_common import *
C = [json.loads(l) for l in open('ep_candidates.jsonl')]
L = [json.loads(l) for l in open('episode-study-labels.jsonl')]
T = json.load(open(os.path.join(CACHE, 'triggers.json')))
wk = lambda ts: datetime.date.fromisoformat(ts[:10]).isocalendar()[1]
print('== detector candidates per shape (corpus 2026-09-02..2026-10-11; ISO weeks 39-41 = Sep 21..Oct 11)')
for sh in ('RG', 'RGE', 'MA', 'ENV', 'DX', 'UC', 'SCR'):
    x = [c for c in C if c['shape'] == sh and c['ts']]; w = collections.Counter(wk(c['ts']) for c in x)
    print('  %-4s total %-4d  wk39 %-4d wk40 %-4d wk41 %-4d  mean/wk(39-41) %-6.1f main %-4d sub %-4d sessions %-3d projects %d' % (sh, len(x), w[39], w[40], w[41], (w[39] + w[40] + w[41]) / 3, sum(not c['sub'] for c in x), sum(c['sub'] for c in x), len({c['session'] for c in x}), len({c['project'].replace('(wt)', '') for c in x})))
rg = [c for c in C if c['shape'] == 'RG']
print('  RG: planned red (test written first) %d of %d; hosted check %d; >=3 reds %d' % (sum(c['planned'] for c in rg), len(rg), sum(c['check'].startswith('gh ') for c in rg), sum(c['reds'] >= 3 for c in rg)))
def share(rows):
    n = len(rows); r = sum(d['label'].startswith('reusable') for d in rows); o = sum(d['label'] == 'one-off-fix' for d in rows); x = n - r - o
    return '%2d/%-2d reusable (%3.0f%%), %2d one-off, %2d not-an-episode; of real episodes %3.0f%%' % (r, n, 100 * r / n if n else 0, o, x, 100 * r / (r + o) if r + o else 0)
print('\n== labelled set: %d episodes' % len(L))
groups = [('RG random', ['RG']), ('RG, hard subset (>=3 reds, a cause in prose, or >=10 look-only calls)', ['RGH']), ('RG, a cause named in prose', ['RGC']), ('RG/RGE on a hosted check', ['RGCI']),
          ('RGE random (two draws)', ['RGE', 'RGE2']), ('MA random', ['MA']), ('ENV random (5 harness + 10 machine)', ['ENV']), ('DX random', ['DX']), ('UC random', ['UC']), ('SCR random', ['SCR']),
          ('held out: T1 as first tested', ['HOLD-T1']), ('held out: T2', ['HOLD-T2']), ('held out: T3a', ['HOLD-T3a']), ('held out: T3b', ['HOLD-T3b']), ('held out: T5', ['HOLD-T5'])]
for name, ss in groups: print('  %-70s %s' % (name, share([d for d in L if d['sample'] in ss])))
FOCUS = os.environ.get('EP_FOCUS_PROJECT', '')
in_focus = lambda d: bool(FOCUS) and d['project'].startswith(FOCUS)
print('\n== one project? reusable share of real episodes, project A (EP_FOCUS_PROJECT) vs every other project')
for name, ss in (('RG (all RG samples)', ['RG', 'RGH', 'RGC']), ('hosted check + RGE', ['RGCI', 'RGE', 'RGE2', 'HOLD-T3a', 'HOLD-T3b']), ('MA', ['MA', 'HOLD-T2']), ('ENV', ['ENV', 'HOLD-T1'])):
    for lab, f in (('project A', in_focus), ('other projects', lambda d: not in_focus(d))):
        print('  %-22s %-18s %s' % (name, lab, share([d for d in L if d['sample'] in ss and f(d)])))
print('\n== features inside the RG/RGE family (real episodes only)')
fam = [d for d in L if d['shape'] in ('RG', 'RGE') and d['label'] != 'not-an-episode']
def tab(name, f):
    a = [d for d in fam if f(d)]; b = [d for d in fam if not f(d)]
    ra = sum(d['label'].startswith('reusable') for d in a); rb = sum(d['label'].startswith('reusable') for d in b)
    print('  %-58s yes: %2d/%-2d reusable   no: %2d/%-2d reusable' % (name, ra, len(a), rb, len(b)))
tab('the check is hosted (gh run view / gh pr checks)', lambda d: d['features']['check'].startswith('gh '))
tab('no file edited between red and green', lambda d: d['features']['edits'] == 0)
tab('hosted, or no file edited', lambda d: d['features']['check'].startswith('gh ') or d['features']['edits'] == 0)
tab('an install or config call between red and green', lambda d: d['features']['envchg'] > 0)
tab('planned red (a test written just before)', lambda d: d['features']['planned'])
tab('three or more reds before green', lambda d: d['features']['reds'] >= 3)
tab('prose names a cause between red and green', lambda d: d['features']['cause'] > 0)
tab('ten or more edits between red and green', lambda d: d['features']['edits'] >= 10)
print('\n== features inside MA (real episodes only)')
ma = [d for d in L if d['shape'] == 'MA' and d['label'] != 'not-an-episode']
for name, f in (('a failure names the machine or a tool (enverr > 0)', lambda d: d['features']['enverr'] > 0), ('three or more edits inside the window', lambda d: d['features']['edits'] >= 3), ('failed tool is not Bash', lambda d: d['features']['tool'] != 'Bash')):
    a = [d for d in ma if f(d)]; b = [d for d in ma if not f(d)]
    print('  %-58s yes: %2d/%-2d reusable   no: %2d/%-2d reusable' % (name, sum(d['label'].startswith('reusable') for d in a), len(a), sum(d['label'].startswith('reusable') for d in b), len(b)))
print('\n== T3b by whether an install/config call sits between red and green (labelled firings)')
tid = collections.defaultdict(set)
for t in T: tid[t['id']].add(t['rule'])
for name, f in (('envchg > 0', lambda d: d['features']['envchg'] > 0), ('envchg = 0', lambda d: d['features']['envchg'] == 0)):
    print('  %-12s %s' % (name, share([d for d in L if 'T3b' in tid.get(d['id'], ()) and f(d)])))
print('\n== rule firings on every labelled episode (in-sample for the first eleven samples, held out for HOLD-*)')
for r in ('T1', 'T2', 'T3a', 'T3b', 'T4', 'T5'):
    ins = [d for d in L if r in tid.get(d['id'], ()) and not d['sample'].startswith('HOLD')]; ho = [d for d in L if d['sample'] == 'HOLD-' + r]
    print('  %-4s in-sample %s' % (r, share(ins))); print('       held-out  %s' % share(ho))
turn_w = collections.Counter()
print('\n== cost: rule firings per week', {r: round(sum(1 for t in T if t['rule'] == r and t['ts'] and wk(t['ts']) in (39, 40, 41)) / 3, 1) for r in ('T1', 'T2', 'T3a', 'T3b', 'T4', 'T5')})
