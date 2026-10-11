"""Scripts written again by another agent or session: clusters of run-three-times scripts by content.
Usage: python3 ep_script_clusters.py
Two scripts are linked when the Jaccard overlap of their 3-token shingles is >= 0.30 and they
were written by different agents (or sessions). A cluster of three or more agents is a helper
that was re-invented."""
import json, re, collections
from ep_common import *
def clusters():
    S = load(); C = [json.loads(l) for l in open('ep_candidates.jsonl') if '"SCR"' in l]
    by = {(s['session'], s['agent']): s for s in S}
    def text(c):
        s = by[(c['session'], c['agent'])]; e = s['ev'][c['a']]
        body = (e['inp'].get('content') or '') if e['name'] == 'Write' else e['inp'].get('command', '')
        m = re.search(r"cat\s*>\s*\S*" + re.escape(c['script']) + r"\s*<<-?\s*['\"]?(\w+)['\"]?\n(.*?)\n\1\b", body, re.S)
        return m.group(2) if m else body
    def sh(t):
        t = re.sub(r'/private/tmp/\S+|/Users/\S+|agent-\w+', 'P', t)
        w = re.findall(r'[A-Za-z_]{2,}', t); return {' '.join(w[i:i + 3]) for i in range(max(0, len(w) - 2))}
    X = [(c, sh(text(c))) for c in C if not re.match(r'patch\d*\.py|edit\d*\.py', c['script'])]
    X = [(c, s) for c, s in X if len(s) >= 12]
    par = list(range(len(X)))
    def find(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for i in range(len(X)):
        for j in range(i + 1, len(X)):
            a, b = X[i], X[j]
            if (a[0]['session'], a[0]['agent']) == (b[0]['session'], b[0]['agent']): continue
            u = len(a[1] | b[1])
            if u and len(a[1] & b[1]) / u >= 0.30: par[find(i)] = find(j)
    cl = collections.defaultdict(list)
    for i in range(len(X)): cl[find(i)].append(X[i][0])
    big = [v for v in cl.values() if len({(c['session'], c['agent']) for c in v}) >= 2]
    big.sort(key=lambda v: -len({(c['session'], c['agent']) for c in v}))
    return X, big, text

if __name__ == '__main__':
    X, big, text = clusters()
    print('run-three-times scripts considered:', len(X), '| clusters written by >=2 agents:', len(big), '| by >=3 agents:', sum(len({(c['session'], c['agent']) for c in v}) >= 3 for v in big), '| scripts inside a cluster:', sum(len(v) for v in big))
    for v in big[:14]:
        ag = {(c['session'], c['agent']) for c in v}; ses = {c['session'] for c in v}
        print('\n%d agents, %d parent sessions, %d runs in all, %s, days %s..%s' % (len(ag), len(ses), sum(c['runs'] for c in v), v[0]['project'], min(c['ts'][:10] for c in v), max(c['ts'][:10] for c in v)))
        print('   names:', ', '.join(sorted({c['script'] for c in v}))[:200])
        print('   first lines:', ' / '.join(l.strip() for l in text(v[0]).split('\n')[:3])[:240])
