"""Threshold study: a small shell reader. Given one Bash command, the cwd and a variable map,
it returns the files written by here-document, the scripts run, and cp/mv/rm of files.
Heuristic, but it expands $VAR/${VAR} assigned earlier in the command or session, follows
`cd`, and never looks inside a here-document body for a run."""
import os, re, shlex

SCRIPT_EXT = ('.py', '.sh', '.zsh', '.bash', '.js', '.mjs', '.cjs', '.ts', '.rb', '.pl', '.R', '.r', '.awk', '.swift', '.applescript')
HOME = os.path.expanduser('~')
HD = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_]\w*)\2")
WRAP = {'time', 'nohup', 'command', 'exec', 'sudo', 'nice', 'caffeinate', 'stdbuf', 'env', 'timeout', 'gtimeout', 'arch'}
PY = re.compile(r'^(python|pypy)[\d.]*$')
SH = {'bash', 'sh', 'zsh', 'dash', 'ksh'}
JS = {'node', 'bun', 'deno', 'tsx', 'ts-node', 'nodejs'}
OTHER = {'Rscript', 'perl', 'ruby', 'osascript', 'swift', 'source', '.'}
REDIR = {'>', '>>', '<', '>&', '<&', '&>', '&>>', '>|', '<<<'}
SEP = {'&&', '||', ';', '|', '|&', '&', '(', ')', ';;'}

def norm(p, cwd):
    if p.startswith('~'):
        p = HOME + p[1:]
    if not p.startswith('/'):
        p = os.path.join(cwd or '/', p)
    p = os.path.normpath(p)
    for a, b in (('/tmp/', '/private/tmp/'), ('/var/folders/', '/private/var/folders/')):
        if p.startswith(a):
            p = b + p[len(a):]
    return p

def expand(tok, env):
    def sub(m):
        k = m.group(1) or m.group(2)
        return env.get(k, m.group(0))
    return re.sub(r'\$\{(\w+)\}|\$(\w+)', sub, tok)

def strip_heredocs(cmd):
    """-> (command without bodies, [(header_line, body, delimiter_quoted)])"""
    lines = cmd.split('\n'); out = []; docs = []; i = 0
    while i < len(lines):
        ln = lines[i]; ms = list(HD.finditer(ln))
        if ms and not re.search(r'<<<', ln[ms[0].start():ms[0].start() + 3]):
            hdr = ln; base = len(docs)
            for m in ms:
                dash, delim = m.group(1), m.group(3); body = []; i += 1
                while i < len(lines) and (lines[i].strip() if dash else lines[i].rstrip()) != delim:
                    body.append(lines[i]); i += 1
                docs.append((hdr, '\n'.join(body) + '\n', bool(m.group(2))))
            k = [base - 1]
            def mark(_m):
                k[0] += 1; return ' __HD%d__ ' % k[0]
            out.append(HD.sub(mark, hdr)); i += 1
        else:
            out.append(ln); i += 1
    return '\n'.join(out), docs

def newline_to_semi(s):
    out = []; q = None; i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            out.append(' ' if s[i + 1] == '\n' else s[i:i + 2]); i += 2; continue
        if q:
            if c == q: q = None
        elif c in '\'"':
            q = c
        elif c == '\n':
            out.append(' ; '); i += 1; continue
        out.append(c); i += 1
    return ''.join(out)

def tokens(s):
    try:
        lx = shlex.shlex(newline_to_semi(s), posix=True, punctuation_chars=True)
        lx.whitespace_split = True
        return list(lx)
    except ValueError:
        return re.split(r'\s+', re.sub(r'(&&|\|\||;|\|)', r' \1 ', s.replace('\n', ' ; ')))

def simple_commands(toks):
    cur = []
    for t in toks:
        if t in SEP:
            if cur: yield cur
            cur = []
        else:
            cur.append(t)
    if cur: yield cur

def drop_redirs(toks):
    out = []; i = 0; target = None
    while i < len(toks):
        t = toks[i]
        if t in REDIR:
            if out and out[-1].isdigit(): out.pop()
            if t in ('>', '>>', '>|') and i + 1 < len(toks) and target is None: target = (t, toks[i + 1])
            i += 2; continue
        out.append(t); i += 1
    return out, target

def is_script(p):
    return p.endswith(SCRIPT_EXT)

def parse(cmd, cwd, env):
    """env is mutated (session-level variable map).
    -> dict(writes=[(path, body, append)], inline=n, runs=[(path, args, kind)], copies=[(src,dst,op)], removes=[path], chmods=[path])"""
    res = dict(writes=[], inline=0, runs=[], copies=[], removes=[], chmods=[], sed=[])
    stripped, docs = strip_heredocs(cmd)
    cwd = cwd or '/'
    env.setdefault('HOME', HOME); env.setdefault('TMPDIR', '/private/tmp'); env['PWD'] = cwd
    toks = tokens(stripped)
    for raw in simple_commands(toks):
        sc, target = drop_redirs(raw)
        # assignments
        i = 0
        if sc and sc[0] in ('export', 'local', 'readonly'): i = 1
        while i < len(sc) and re.match(r'^[A-Za-z_]\w*=', sc[i]):
            k, v = sc[i].split('=', 1)
            v = expand(v, env)
            if v.endswith('$') or v == '': v = '<dyn:%s>' % k
            env[k] = v; i += 1
        sc = [expand(t, env) for t in sc[i:]]
        if target: target = (target[0], expand(target[1], env))
        marks = [int(t[4:-2]) for t in sc if re.match(r'^__HD\d+__$', t)]
        sc = [t for t in sc if not re.match(r'^__HD\d+__$', t)]
        if not sc: continue
        if marks:
            body = docs[marks[0]][1]; h0 = os.path.basename(sc[0])
            if h0 == 'cat' and target and len(sc) == 1:
                res['writes'].append((norm(target[1], cwd), body, target[0] == '>>'))
            elif h0 == 'tee':
                fs = [x for x in sc[1:] if not x.startswith('-')]
                if fs: res['writes'].append((norm(fs[0], cwd), body, '-a' in sc))
            elif PY.match(h0) or h0 in SH or h0 in JS or h0 in ('uv', 'Rscript', 'perl', 'ruby', 'osascript'):
                res['inline'] += 1
        env['_'] = sc[-1]
        while sc and os.path.basename(sc[0]) in WRAP:
            w = os.path.basename(sc[0]); sc = sc[1:]
            while sc and (sc[0].startswith('-') or re.match(r'^[A-Za-z_]\w*=', sc[0]) or (w in ('timeout', 'gtimeout') and re.match(r'^\d+[smhd]?$', sc[0]))):
                if sc[0] in ('-s', '-k', '--signal', '--kill-after', '-u', '-C') and len(sc) > 1: sc = sc[1:]
                sc = sc[1:]
        if not sc: continue
        c0 = os.path.basename(sc[0]); a = sc[1:]
        if c0 == 'cd' and a:
            d = a[-1]
            if '<dyn' not in d and '$' not in d: cwd = norm(d, cwd); env['PWD'] = cwd
            continue
        if c0 in ('cp', 'mv') and len(a) >= 2:
            srcs = [x for x in a[:-1] if not x.startswith('-')]
            for s_ in srcs: res['copies'].append((norm(s_, cwd), norm(a[-1], cwd), c0))
        elif c0 == 'rm':
            for x in a:
                if not x.startswith('-'): res['removes'].append(norm(x, cwd))
        elif c0 == 'chmod':
            for x in a[1:]:
                res['chmods'].append(norm(x, cwd))
        elif c0 == 'sed' and any(x.startswith('-i') for x in a):
            for x in a:
                if is_script(x): res['sed'].append(norm(x, cwd))
        script = None; kind = None; rest = []
        if PY.match(c0) or c0 == 'uv':
            j = 0
            if c0 == 'uv':
                if a[:1] != ['run']: continue
                j = 1
                while j < len(a) and a[j].startswith('-'):
                    j += 2 if a[j] in ('--with', '--python', '-p', '--project', '--directory', '--extra', '--group', '--env-file', '--with-requirements', '--from') else 1
                if j < len(a) and PY.match(os.path.basename(a[j])): j += 1
                elif j < len(a) and a[j] == 'pytest': c0 = 'pytest'; a = a[j + 1:]; j = None
            if j is not None:
                mod = None
                while j < len(a) and a[j].startswith('-') and a[j] != '-':
                    if a[j] == '-c': j = len(a); break
                    if a[j] == '-m': mod = a[j + 1] if j + 1 < len(a) else ''; j += 2; break
                    j += 2 if a[j] in ('-X', '-W') else 1
                if mod in ('pytest', 'unittest'):
                    c0 = 'pytest'; a = a[j:]
                elif mod is None and j < len(a) and a[j] != '-':
                    script, rest, kind = a[j], a[j + 1:], 'interp'
        elif c0 in SH:
            j = 0
            while j < len(a) and a[j].startswith('-'):
                if a[j] == '-c' or 'c' in a[j][1:] and not a[j].startswith('--'): j = len(a); break
                j += 2 if a[j] in ('-o', '+o') else 1
            if j < len(a): script, rest, kind = a[j], a[j + 1:], 'interp'
        elif c0 in JS or c0 == 'npx':
            j = 0
            if c0 == 'npx':
                while j < len(a) and a[j].startswith('-'): j += 1
                if j < len(a) and a[j] in JS: c0 = a[j]; j += 1
                else: j = len(a)
            if j < len(a) and a[j] in ('run', 'test', 'x') and c0 in ('bun', 'deno'):
                if a[j] == 'test': kind = 'pytest'
                j += 1
            while j < len(a) and a[j].startswith('-'):
                if a[j] in ('-e', '--eval', '-p', '--print'): j = len(a); break
                j += 2 if a[j] in ('-r', '--require', '--import', '--loader') else 1
            if j < len(a) and (is_script(a[j]) or '/' in a[j]): script, rest, kind = a[j], a[j + 1:], kind or 'interp'
        elif c0 in OTHER:
            j = 0
            while j < len(a) and a[j].startswith('-'):
                if a[j] == '-e': j = len(a); break
                j += 1
            if j < len(a): script, rest, kind = a[j], a[j + 1:], 'interp'
        elif is_script(sc[0]) and ('/' in sc[0]):
            script, rest, kind = sc[0], a, 'direct'
        if c0 == 'pytest':
            for x in a:
                x = x.split('::')[0]
                if x.endswith('.py'): res['runs'].append((norm(x, cwd), (), 'pytest'))
        if script and '<dyn' not in script.split('/')[-1]:
            res['runs'].append((norm(script, cwd), tuple(rest), kind))
    return res
