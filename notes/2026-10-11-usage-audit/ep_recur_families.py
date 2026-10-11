"""Named failure families that recur across sessions, with what the lesson store holds for each.
Usage: python3 ep_recur_families.py"""
import re, os, glob, collections
from ep_common import *
FAM = [
 ('worktree-isolated agent refused', r'This agent is isolated in the worktree', r'isolated in the worktree|worktree-isolated'),
 ('compound guard stopped the call', r'\[compound\] This call was stopped before it ran', None),
 ('Blocked: sleep N followed by', r'Blocked: sleep', r'Blocked: sleep|standalone sleep|sleep followed'),
 ('zsh: no matches found', r'no matches found', r'no matches found'),
 ('Playwright MCP outside allowed roots', r'outside allowed roots', r'outside allowed roots'),
 ('Read: exceeds maximum allowed tokens/size', r'exceeds maximum allowed', r'exceeds maximum allowed'),
 ('safety check: cannot be checked before it runs', r"can't be checked before it runs|cannot be statically", r"can't be checked before it runs|cannot be statically"),
 ('auto mode classifier denied or gave no verdict', r'auto mode classifier', r'auto mode classifier'),
 ('command not found: timeout', r'command not found: timeout', r'\btimeout\b.*(?:not found|macOS)|gtimeout'),
 ('command not found (any other)', r'command not found: (?!timeout)', None),
 ('ModuleNotFoundError / No module named', r'No module named', None),
 ('subagents should not write report files', r'Subagents should return findings as text', r'return findings as text|report files'),
 ('f-string expression part cannot include a backslash', r'f-string expression part cannot include a backslash', r'f-string'),
 ('zsh parse error near', r'parse error near', r'parse error near'),
 ('zsh bad substitution', r'bad substitution', r'bad substitution'),
 ('Edit: String to replace not found', r'String to replace not found', None),
 ('Edit/Write: file not read or modified since read', r'File has not been read yet|modified since read', None),
 ('pytest: unrecognized arguments: -n', r'unrecognized arguments: -n', r'unrecognized arguments: -n'),
 ('Cannot create agent worktree', r'Cannot create agent worktree', r'Cannot create agent worktree'),
 ('HTTP 429 Too Many Requests', r'429|Too Many Requests', None),
 ('certificate verify / local issuer', r'CERTIFICATE_VERIFY_FAILED|local issuer certificate', r'CERTIFICATE_VERIFY|local issuer'),
 ('macOS screenshot name (U+202F)', r"Screenshot 20\d\d-\d\d-\d\d at [^\n]*No such file|No such file[^\n]*Screenshot 20\d\d", r'U\+202F|no-break space'),
 ('xargs: command line cannot be assembled', r'xargs: command line cannot be assembled', r'xargs'),
 ('partially initialized module (script shadows stdlib)', r'partially initialized module', r'partially initialized module'),
 ('externally-managed-environment', r'externally-managed', r'externally-managed'),
 ('No module named pip', r'No module named pip', r'No module named pip'),
]
def lessons():
    out = []
    for f in glob.glob(os.path.expanduser('~/.claude/compound/lessons/*/SKILL.md')) + glob.glob(os.path.expanduser('~/*/.claude/compound/lessons/*/SKILL.md')) + glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'lessons', '*', 'SKILL.md')):
        t = open(f).read(); m = re.search(r'^created:\s*(\S+)', t, re.M)
        out.append((os.path.basename(os.path.dirname(f)), m.group(1) if m else '?', t))
    return out
S = load(); L = lessons()
print('%-52s %5s %4s %4s %-10s %-10s  lesson (created) | calls after it' % ('family', 'calls', 'sess', 'proj', 'first', 'last'))
for name, pat, lpat in FAM:
    rx = re.compile(pat); hits = []
    for s in S:
        if is_tmp(s): continue
        for e in s['ev']:
            if e['k'] == 'call' and e['err'] and rx.search(e['res'] or ''): hits.append((s['session'], proj(s).replace('(wt)', ''), (e['ts'] or '')[:10]))
    if not hits: print('%-52s %5d' % (name, 0)); continue
    les = [(n, c) for n, c, t in L if lpat and re.search(lpat, t)]
    les.sort(key=lambda x: x[1]); first = les[0] if les else None
    after = sum(1 for h in hits if first and h[2] > first[1]) if first else ''
    sa = len({h[0] for h in hits if first and h[2] > first[1]}) if first else ''
    print('%-52s %5d %4d %4d %-10s %-10s  %s | %s calls, %s sessions' % (name, len(hits), len({h[0] for h in hits}), len({h[1] for h in hits}), min(h[2] for h in hits), max(h[2] for h in hits),
          ('%s (%s)%s' % (first[0], first[1], ' +%d' % (len(les) - 1) if len(les) > 1 else '')) if first else 'NONE', after, sa))
