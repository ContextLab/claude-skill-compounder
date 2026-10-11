"""Detect candidate problem-solving episodes of six shapes in every cached transcript.

Usage: python3 ep_detect.py OUT.jsonl      (needs the cache from ep_parse.py)
Shapes:
  RG   a check is red, files are edited, the same check is green
  RGE  a check is red, NO file is edited, the same check is green, and the passing call is
       not the failing call word for word (the invocation or the environment changed)
  MA   three or more failed calls inside twelve calls, at least two different programs or
       rewordings, then a call that passes (several approaches to one goal)
  DX   a diagnostic chain: six or more look-only calls with no edit, ending in assistant
       prose that names a cause
  UC   a typed prompt that corrects the approach
  ENV  a failed call whose error names the machine, the shell or the harness, then a pass
Every candidate carries the indexes of its first and last event so it can be re-read.

EP_EXTRA_CHECKS (environment, optional): comma-separated regular expressions for check
programs of the projects being read that the list below does not name, for example
`lint_docs\.py,mytool\s+verify` (write \s for a space: the pattern is compiled verbose).
"""
import json, re, sys, collections
from ep_common import *

RUN = re.compile(r'''(?x)(?:^|[;&|(]\s*|/|\s)(
   pytest|run_tests\.sh|bun\s+test|npm\s+(?:run\s+)?test|npx\s+tsc|latexmk|pdflatex|xelatex|sphinx-build|sphinx\s+-|make(?=\s|$)|ruff(?:\s+check)?|mypy|eslint|actionlint|
   check_\w+\.(?:sh|py)|verify_\w+\.(?:sh|py)|validate\w*\.(?:sh|py)|build_\w+\.(?:sh|py)|claude\s+plugin\s+(?:validate|test)|
   cargo\s+(?:test|build)|go\s+test|twine\s+check|gh\s+pr\s+checks|gh\s+run\s+(?:view|watch)|unittest|promptfoo|tests?/test_\w+\.py|test_\w+\.py|tsc(?=\s)|vhs|quarto\s+render|jupyter\s+nbconvert|nbconvert|marp''' + ''.join('|' + x for x in env_list('EP_EXTRA_CHECKS')) + r'''
   )''')
RED = re.compile(r'\b[1-9]\d* (?:failed|errors?|failures?)\b|FAILED|Traceback \(most recent|^E   |error TS\d+|\berror:|✗|\bFAIL\b|Exit code [1-9]|! LaTeX Error|Undefined control sequence|Overfull \\\\hbox|^not ok|AssertionError|SyntaxError|ModuleNotFoundError', re.M)
BASH_EDIT = re.compile(r"sed\s+-i|perl\s+-p?i|cat\s*>+\s*[^\s|;&]+|tee\s+\S|open\([^)]*['\"]w['\"]\)|\.write\(|write_text\(|git\s+apply|\bpatch\s+-|git\s+(?:checkout|restore|stash|revert|merge|cherry-pick|reset)\b")
ENVCHG = re.compile(r"\b(?:pip3?|uv|brew|npm|conda|apt(?:-get)?|gem|cargo|bun)\s+(?:pip\s+)?(?:install|add|sync|upgrade)\b|\bexport\s+\w+=|git\s+config|git\s+sparse-checkout|git\s+worktree|git\s+fetch|chmod|ln\s+-s|open\s+-ga|docker\s+(?:run|start|pull)|source\s+\S+activate|uv\s+venv|python3?\s+-m\s+venv")
CAUSE = re.compile(r"root cause|the cause\b|cause (?:is|was)|caused by|turns out|turned out|the reason (?:is|was)|the culprit|that explains|found it|found the (?:bug|problem|issue|cause)|the (?:bug|problem|issue) (?:is|was)|which is why|is why\b", re.I)
ENVERR = re.compile(r"command not found|Cannot find module|MODULE_NOT_FOUND|No module named|not installed|[Pp]ermission denied|Operation not permitted|no matches found|bad substitution|unrecognized arguments?|unknown (?:option|flag|command)|invalid option|illegal option|externally-managed|No such file or directory|outside allowed roots|not a git repository|rate limit|timed out|Blocked:|was denied|This call was stopped|cannot be statically|not supported|unsupported|requires? (?:Python|node|version)|ENOENT|EACCES|certificate|could not resolve host|Connection refused|Killed|out of memory|not a tty|no such (?:option|command)|usage: ", re.I)
HARNESS = re.compile(r"\[compound\]|This agent is isolated|worktree-isolated|Blocked: sleep|auto mode classifier|Dangerous rm|tool_use_error|permission (?:for this action )?was denied|requires approval|was rejected|doesn't want to proceed|InputValidationError|File has not been read|exceeds maximum allowed|Output too large", re.I)
CORRECT = re.compile(r"^\s*no[,.! ]|\bdon'?t\b|\bdo not\b|\bstop\b|\binstead\b|why (?:did|are|is|do|does|didn'?t|isn'?t|aren'?t) |\bi (?:said|told|asked|meant)\b|that'?s (?:not|wrong)|\bwrong\b|\byou (?:should|need to|must|forgot|missed|didn'?t|haven'?t|keep)\b|\bstill (?:not|broken|wrong|failing|see|shows?|at)\b|not what\b|rather than|\bnever\b|\balways\b|\bagain\b|supposed to|shouldn'?t|isn'?t (?:working|right|correct)|doesn'?t (?:work|look)|/compound:learn|\bremember\b", re.I)
PLANNED = re.compile(r"\bRED\b|fail(?:s|ing)? first|failing test|watch it fail|should fail|expect(?:ed)? (?:it )?to fail|tests? first|confirm (?:it|they) fails?|before the fix", re.I)
LOOK = ('Read', 'Grep', 'Glob', 'WebFetch', 'WebSearch', 'ToolSearch', 'TodoWrite')

def cmd(e): return e['inp'].get('command', '') if e['name'] == 'Bash' else ''
def nohere(c):
    """The command without here-document bodies (their text is data, not the command)."""
    return re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n\1\b", '<<HEREDOC', c, flags=re.S)
def is_edit(e):
    if e['name'] in ('Edit', 'Write', 'NotebookEdit', 'MultiEdit'): return True
    return e['name'] == 'Bash' and bool(BASH_EDIT.search(cmd(e)))
READERS = re.compile(r'^(?:sed|grep|rg|cat|head|tail|wc|ls|git|cp|mv|rm|echo|printf|awk|cut|sort|diff|find|chmod|touch|mkdir|open|less|file|stat|tee|which|command|type|test|cd|export|for|do|done|if|then|fi|while|until|sleep|kill|pkill|ps|tar|curl)\b')
def simple_commands(c):
    c = re.sub(r"'[^']*'", "''", nohere(c))                    # quoted text is data: a grep pattern is not a command
    c = re.sub(r'"(?:[^"\\]|\\.)*"', '""', c)
    return [x.strip() for x in re.split(r'&&|\|\||;|\||\n|\$\(|`', c) if x.strip()]
def check_key(c):
    """The check a command runs, or None. The runner must be the program of one of the
    command's simple commands: `sed -n 1,9p check_things.py` reads a file and runs nothing."""
    for sc in simple_commands(c):
        sc = re.sub(r'''^(?:\(|\{|!|do\s|then\s|time\s|\w+=(?:"[^"]*"|'[^']*'|\S*)\s+)+''', '', sc).strip()
        if not sc or READERS.match(sc): continue
        m = RUN.search(sc)
        if not m: continue
        if len(sc[:m.start(1)].split()) > 6: continue      # far from command position: an argument, not the program
        r = re.sub(r'\s+', ' ', m.group(1)); r = re.sub(r'^tests?/', '', r)
        tg = ()
        if r == 'pytest':
            tg = tuple(sorted(set(re.findall(r'(tests?/[\w/.-]+\.py)', sc))))[:4]
        return (r, tg)
    return None
def red(e):
    r = e['res'] or ''
    return bool(e['err']) or bool(RED.search(r))
def prog(c):
    c = nohere(c).strip()
    c = re.sub(r'^(?:cd\s+\S+\s*(?:&&|;)\s*)+', '', c)
    c = re.sub(r'^(?:\w+=(?:"[^"]*"|\'[^\']*\'|\S*)\s*;?\s*)+', '', c)
    w = c.split()
    if not w: return ''
    p = w[0].split('/')[-1]
    if p in ('python', 'python3', 'uv', 'npx', 'bash', 'sh', 'zsh', 'git', 'gh', 'claude', 'docker', 'npm', 'bun') and len(w) > 1:
        nxt = [x for x in w[1:4] if not x.startswith('-')]
        p += ' ' + (nxt[0].split('/')[-1] if nxt else '')
    return p[:40]

def detect(s):
    ev = s['ev']; out = []
    def add(shape, a, b, **f):
        out.append(dict(shape=shape, a=a, b=b, ts=ev[a].get('ts'), **f))
    # ---- RG / RGE
    open_red = {}   # key -> dict(first, reds, edits, files, envchg, looks, redtexts, redcmds)
    for j, e in enumerate(ev):
        if e['k'] == 'text':
            for v in open_red.values():
                if CAUSE.search(e['text']): v['cause'] += 1
            continue
        if e['k'] != 'call' or e['res'] is None: continue
        if HARNESS.search(e['res'] or '') and e['err']: continue
        k = check_key(cmd(e)) if e['name'] == 'Bash' else None
        ed = is_edit(e)
        for kk, v in open_red.items():
            if ed:
                v['edits'] += 1
                fp = e['inp'].get('file_path') or ''
                if fp: v['files'].add(fp)
            elif e['name'] in LOOK or (e['name'] == 'Bash' and not k): v['looks'] += 1
            if e['name'] == 'Bash' and ENVCHG.search(nohere(cmd(e))): v['envchg'] += 1
        if not k: continue
        if red(e):
            if k not in open_red:
                prev = ' '.join(x['text'] for x in ev[max(0, j - 4):j] if x['k'] == 'text')
                wrote_test = bool(re.search(r"cat\s*>+\s*\S*tests?/\S+|cat\s*>+\s*\S*test_\w+\.py|\.test\.ts", nohere(cmd(e)))) or any(
                    x['k'] == 'call' and x['name'] in ('Write', 'Edit') and re.search(r'(^|/)tests?/|test_|\.test\.', x['inp'].get('file_path') or '') for x in ev[max(0, j - 3):j])
                planned = bool(PLANNED.search(prev)) or wrote_test
            v = open_red.setdefault(k, dict(first=j, reds=0, edits=0, files=set(), envchg=0, looks=0, cause=0, redtexts=set(), redcmds=[], planned=planned))
            v['reds'] += 1; v['redcmds'].append(cmd(e))
            m = re.findall(r'(?m)^(?:E   .*|.*(?:Error|error:|FAILED|failed).*)$', e['res'] or '')
            v['redtexts'].add(re.sub(r'\d+', 'N', m[-1])[:160] if m else '')
        else:
            hits = [kk for kk in open_red if kk == k or (kk[0] == k[0] and (not k[1] or not kk[1] or set(kk[1]) <= set(k[1])))]
            for kk in hits:
                v = open_red.pop(kk)
                same = cmd(e) in v['redcmds']
                feats = dict(check=kk[0], reds=v['reds'], edits=v['edits'], files=len(v['files']), envchg=v['envchg'], looks=v['looks'],
                             planned=v['planned'], cause=v['cause'], distinct_errors=len(v['redtexts']), span=j - v['first'], same_cmd=same,
                             test_only=bool(v['files']) and all(re.search(r'(^|/)tests?/|test_|\.test\.', f) for f in v['files']))
                if v['edits']: add('RG', v['first'], j, **feats)
                elif not same or v['envchg']: add('RGE', v['first'], j, **feats)
    # ---- MA and ENV : walk Bash/tool failures
    cs = [(j, e) for j, e in enumerate(ev) if e['k'] == 'call' and e['res'] is not None]
    i = 0; last_ma_end = -1
    while i < len(cs):
        j, e = cs[i]
        if e['err'] and not HARNESS.search(e['res'] or '') and j > last_ma_end:
            win = cs[i:i + 12]
            fails = [(jj, x) for jj, x in win if x['err'] and not HARNESS.search(x['res'] or '') and x['name'] == e['name']]
            if len(fails) >= 3:
                lastfail = fails[-1][0]
                succ = next(((jj, x) for jj, x in cs[i:i + 30] if jj > lastfail and not x['err'] and x['name'] == e['name'] and not is_lookonly(x)), None)
                progs = set(prog(cmd(x)) if x['name'] == 'Bash' else x['name'] for _, x in fails)
                texts = set(cmd(x)[:200] if x['name'] == 'Bash' else json.dumps(x['inp'])[:200] for _, x in fails)
                if succ and len(texts) >= 2:
                    edits = sum(is_edit(x) for jj, x in cs if j <= jj <= succ[0])
                    add('MA', j, succ[0], fails=len(fails), progs=len(progs), tool=e['name'], edits=edits,
                        check=bool(check_key(cmd(e))) if e['name'] == 'Bash' else False,
                        enverr=sum(bool(ENVERR.search(x['res'] or '')) for _, x in fails), span=succ[0] - j)
                    last_ma_end = succ[0]
        i += 1
    for i, (j, e) in enumerate(cs):
        r = e['res'] or ''
        if not e['err']: continue
        harness = bool(HARNESS.search(r))
        if not harness and not ENVERR.search(r[-1500:]): continue
        if not harness and e['name'] == 'Bash' and check_key(cmd(e)) and RED.search(r) and not ENVERR.search(r[-400:]): continue
        succ = next(((jj, x) for jj, x in cs[i + 1:i + 7] if not x['err'] and x['name'] == e['name']), None)
        if not succ: continue
        m = ENVERR.search(r[-1500:]) or HARNESS.search(r)
        add('ENV', j, succ[0], harness=harness, sig=m.group(0).lower()[:30], tool=e['name'], same_cmd=(cmd(e) == cmd(succ[1])) if e['name'] == 'Bash' else False, span=succ[0] - j)
    # ---- DX
    look = 0; start = None; hadfail = False
    for j, e in enumerate(ev):
        if e['k'] == 'prompt':
            if e['src'] != 'system' and not e['text'].startswith('<task-notification'): look = 0; start = None; hadfail = False
        elif e['k'] == 'call':
            if is_edit(e): look = 0; start = None; hadfail = False
            else:
                if look == 0: start = j
                look += 1; hadfail = hadfail or bool(e['err']) or (e['name'] == 'Bash' and bool(check_key(cmd(e))) and red(e))
        elif e['k'] == 'text' and look >= 5 and CAUSE.search(e['text']):
            add('DX', start, j, looks=look, hadfail=hadfail, marker=CAUSE.search(e['text']).group(0).lower())
            look = 0; start = None; hadfail = False
    # ---- UC
    if not s['sub']:
        for j, e in enumerate(ev):
            if e['k'] != 'prompt' or e['src'] not in ('typed', 'queued', 'human', 'suggestion_accepted'): continue
            t = e['text']
            if t.startswith('<') and '/compound:learn' not in t and 'command-name' not in t: continue
            if t.startswith('<task-notification') or t.startswith('<system-reminder') or '[Request interrupted' in t: continue
            if j == 0 or not any(x['k'] == 'call' for x in ev[:j]): continue   # first prompt corrects nothing
            m = CORRECT.search(t[:1500])
            if not m: continue
            b = next((jj for jj in range(j + 1, len(ev)) if ev[jj]['k'] == 'prompt' and ev[jj]['src'] in ('typed', 'queued', 'human')), min(len(ev) - 1, j + 60))
            add('UC', j, min(b, j + 60), marker=m.group(0).lower().strip()[:20], learn='/compound:learn' in t, length=len(t))
    # ---- SCR: a script written in the session and then run successfully three or more times
    made = {}
    for j, e in enumerate(ev):
        if e['k'] != 'call' or e['res'] is None: continue
        names = []
        if e['name'] == 'Write' and re.search(r'\.(py|sh|mjs|js|zsh|bash)$', e['inp'].get('file_path') or ''):
            names.append((e['inp']['file_path'], len((e['inp'].get('content') or '').splitlines())))
        if e['name'] == 'Bash':
            for m in re.finditer(r"cat\s*>\s*([^\s<|;&]+\.(?:py|sh|mjs|js|zsh|bash))\s*<<-?\s*['\"]?(\w+)['\"]?\n(.*?)\n\2\b", cmd(e), re.S):
                names.append((m.group(1), len(m.group(3).splitlines())))
        for path, nl in names:
            base = path.split('/')[-1]
            scratch = bool(re.search(r'scratchpad|/tmp/|^\$\w+/|JOB_DIR|/T/', path))
            v = made.setdefault(base, dict(a=j, runs=0, writes=0, lines=nl, scratch=scratch, last=j, path=path))
            v['writes'] += 1; v['lines'] = nl
        if e['name'] == 'Bash' and not e['err']:
            c2 = nohere(cmd(e))
            for base, v in made.items():
                if v['a'] <= j and re.search(r'(?:python3?|bash|sh|zsh|node|bun|uv run|/|\s)[^\n;|&]*' + re.escape(base) + r'(?=[\s;|&)]|$)', c2) and not re.search(r'cat\s*>\s*\S*' + re.escape(base), c2[:c2.find(base) + 1] if base in c2 else ''):
                    if re.search(r'(?:^|[\s/\'"=])' + re.escape(base) + r'(?=[\s;|&)\'"]|$)', c2) and not re.search(r'(?:cat|sed|head|tail|grep|wc|ls|rm|cp|mv|chmod|git add|py_compile)\s[^;|&\n]*' + re.escape(base), c2):
                        v['runs'] += 1; v['last'] = j
    for base, v in made.items():
        if v['runs'] >= 3 and not re.match(r'test_|conftest', base):
            add('SCR', v['a'], v['last'], script=base, runs=v['runs'], writes=v['writes'], lines=v['lines'], scratch=v['scratch'], path=v['path'][-90:])
    return out

def is_lookonly(x):
    return x['name'] in LOOK

if __name__ == '__main__':
    S = load(); n = 0
    with open(sys.argv[1], 'w') as f:
        for si, s in enumerate(S):
            if is_tmp(s): continue
            for c in detect(s):
                c.update(si=si, project=proj(s), session=s['session'], sub=s['sub'], agent=s['agent'], entry=s['entry'])
                c['id'] = '%s-%s-%s-%d' % (c['shape'], s['session'][:8], (s['agent'] or 'main')[-6:], c['a'])
                f.write(json.dumps(c) + '\n'); n += 1
    print(n, 'candidates')
