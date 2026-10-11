"""Follow-through of lessons: after a lesson existed, did later sessions that met its
situation get the lesson surfaced, and did they follow it or redo the work by hand?

Usage: python3 mine_followthrough.py CACHE_DIR CONFIG.json [--rebuild]
       (the configuration may be named by the environment variable FOLLOWTHROUGH_CONFIG instead)
Reads ~/.claude/projects (read-only) and ~/.claude/compound/events.jsonl (read-only).
Writes followthrough.jsonl beside this file: one row per lesson x session. That file quotes
private commands and is not kept in the repository.

Which lessons are followed, when each was recorded, and the names of the projects, files
and scripts some of them are about come from CONFIG.json. It is a local file that is not
kept in the repository: the rows name the owner's lessons and projects and stay on the
machine. Its form (every name below is made up):

    {"exclude_sessions": ["<id of the session running the study>"],
     "lessons": [
       {"group": "script", "name": "ci-poll-in-background", "since": "2026-01-01T00:00:00",
        "detector": "ci_poll", "script": "wait-for-ci.py"},
       {"group": "plain", "name": "verify-push", "since": "2026-01-01T00:00:00", "detector": "push"},
       {"group": "plain", "name": "check-report-after-edit", "since": "2026-01-01T00:00:00",
        "detector": "check_after_edit", "project": "my-report", "file": "report.tex",
        "script": "check_report.sh"}],
     "native": [
       {"name": "my-bib-skill", "since": "2026-01-01T00:00:00", "detector": "bib",
        "project": "my-bibliography", "bib_file": "refs.bib", "checker": "check_refs.py"},
       {"name": "my-slow-loop-skill", "since": "2026-01-01T00:00:00", "detector": "slow_loop"}]}

`since` is when the lesson was recorded (UTC); only calls after it count. `project` is a
regular expression searched in the session's directory and project name; a row with a
project applies only there. Detectors and what else a row gives them:

  ci_poll           a loop or watch that polls a hosted check; followed = `script` was run
  ci_checks         the checks of one commit are asked for; followed = `script` was run
  inflight          a job is started that outlives the turn; followed = `script` was run
  job_log           a hosted job's log is fetched; followed = fetched whole through the API
  push              a push; followed = `git ls-remote` after it
  kill              a script is killed by name; followed = its children are killed and looked for
  pgrep             pgrep/pkill -f; by hand = a wait loop on pgrep -f; followed = kill -0
  docs              a docs site is built or served (`extra`: more regular expressions for the
                    project's own build steps); followed = `script` was run
  no_parallel_flag  pytest in `project`; by hand = pytest with -n
  check_after_edit  `file` (and files of its extension) edited in `project`; followed =
                    `script` run within the next three calls
  pipeline_script   a script whose name matches one of `names` is written or run in `project`;
                    by hand = written anew; followed = run under nohup
  notes_before_push a push in `project`; by hand = notes committed just after it
  bib   (native)    an entry added to a .bib file (only `bib_file` when given), or `checker` run
  slow_loop (native) one tool run twice for five minutes or more, or the user says it is slow

Every situation marker is a regular expression over Bash commands with here-document
bodies removed, so every count is a heuristic: a lower bound where the regex is narrow
(a situation met without the marker is not seen) and an upper bound where a marker
appears in a command for another reason.
"""
import json, os, re, sys, pickle, collections

HOME = os.path.expanduser('~')
ROOT = HOME + '/.claude/projects'
HERE = os.path.dirname(os.path.abspath(__file__))
M = re.M | re.S

def parse(f, sid):
    # A resumed session's file starts with a copy of the earlier session's lines; each copied
    # line keeps the earlier id in `session_id`, and is left to the file it came from.
    ev = []; calls = {}; cwd = None
    for l in open(f, errors='ignore'):
        try: d = json.loads(l)
        except Exception: continue
        if d.get('session_id') and d.get('session_id') != sid: continue
        t = d.get('type'); ts = d.get('timestamp') or ''
        cwd = cwd or d.get('cwd')
        if t == 'attachment':
            a = d.get('attachment') or {}
            if a.get('type') == 'hook_additional_context':
                c = a.get('content'); c = '\n'.join(c) if isinstance(c, list) else str(c)
                ev.append({'k': 'hook', 'ts': ts, 'text': c[:6000]})
            continue
        if t not in ('user', 'assistant'): continue
        c = (d.get('message') or {}).get('content')
        if t == 'user' and isinstance(c, str):
            ev.append({'k': 'prompt', 'ts': ts, 'text': c[:8000], 'meta': bool(d.get('isMeta') or d.get('isCompactSummary'))}); continue
        if not isinstance(c, list): continue
        for b in c:
            if not isinstance(b, dict): continue
            bt = b.get('type')
            if bt == 'text' and t == 'user':
                ev.append({'k': 'prompt', 'ts': ts, 'text': b.get('text', '')[:8000], 'meta': bool(d.get('isMeta') or d.get('isCompactSummary'))})
            elif bt == 'text' and t == 'assistant':
                ev.append({'k': 'text', 'ts': ts, 'text': b.get('text', '')[:1500]})
            elif bt == 'tool_use':
                if b.get('id') in calls: continue      # a resumed or forked transcript repeats lines
                e = {'k': 'call', 'ts': ts, 'name': b.get('name'), 'inp': b.get('input') or {}, 'err': None, 'res': '', 'rts': ''}
                calls[b.get('id')] = e; ev.append(e)
            elif bt == 'tool_result':
                e = calls.get(b.get('tool_use_id'))
                if e is not None:
                    r = b.get('content')
                    if isinstance(r, list): r = '\n'.join(x.get('text', '') for x in r if isinstance(x, dict))
                    r = r if isinstance(r, str) else json.dumps(r)
                    e['err'] = bool(b.get('is_error')); e['res'] = r[:2500] + ('...' + r[-1500:] if len(r) > 4000 else r[2500:]); e['rts'] = ts
    return cwd, ev

def build(cache):
    S = []
    for dp, dn, fn in os.walk(ROOT):
        for n in fn:
            if not n.endswith('.jsonl'): continue
            f = os.path.join(dp, n); rel = os.path.relpath(f, ROOT).split(os.sep)
            cwd, ev = parse(f, rel[1].replace('.jsonl', ''))
            if not ev: continue
            S.append({'file': f, 'project': rel[0], 'session': rel[1].replace('.jsonl', ''), 'sub': len(rel) > 2, 'cwd': cwd or '', 'ev': ev})
    pickle.dump(S, open(cache, 'wb')); return S

# ---------- helpers
HD = re.compile(r"<<-?\s*(['\"]?)(\w+)\1.*?^\s*\2\s*$", M)
def cmd(e):
    return HD.sub('<<HEREDOC', e['inp'].get('command', '') or '') if e['name'] == 'Bash' else ''
P = r"(?:^|[;&|(]\s*|\$\(\s*|`\s*|\b(?:do|then|else|time|nohup)\s+)"        # command position
def RX(s): return re.compile(s, M)
def EXEC(name):   # the script is run, not read (cat/sed/ls/cp/chmod of it do not count)
    return RX(r"(?:^|[;&|(]\s*|\b(?:bash|sh|zsh|nohup|python3?|uv run(?: -q)?(?: python3?)?)\s+(?:-\w+\s+)*)[\"']?[~\w/.${}-]*" + re.escape(name))
def bash(s, since): return [(i, e) for i, e in enumerate(s['ev']) if e['k'] == 'call' and e['name'] == 'Bash' and e['ts'] >= since]
def q(e, n=260): return {'ts': e['ts'], 'cmd': cmd(e)[:n]}

# ---------- lessons.  Each returns {'hits':[...], 'followed':[...], 'hand':[...]} of quoted calls for ONE stream.
def regex_lesson(sit, follow, kinds=()):
    def f(s, since):
        H = []; F = []; N = []
        for i, e in bash(s, since):
            c = cmd(e)
            if follow.search(c): F.append(q(e))
            if sit.search(c):
                x = {**q(e), 'kind': next((k for k, r in kinds if r.search(c)), '')}
                H.append(x)
                if not follow.search(c): N.append(x)
        return {'hits': H, 'followed': F, 'hand': N}
    return f

GH = r"gh\s+(?:run\s+(?:view|list)|pr\s+checks|api\b[^\n]*actions/(?:runs|jobs))"
FORLOOP = P + r"for\s+\w+\s+in\b[^\n;]*;\s*do\b(?=.{0,1500}?\b" + GH + r")(?=.{0,1500}?\bsleep\b)(?=.{0,3000}?\bdone\b)"
CI_POLL = RX(r"(?:" + P + r"(?:until|while)\b(?=.{0,1500}?\b" + GH + r")(?=.{0,1500}?\bsleep\b))|" + FORLOOP + "|" + P + r"gh\s+run\s+watch\b|" + P + r"gh\s+pr\s+checks\b[^\n;&|]*--watch|" + P + r"sleep\s+\d+\s*(?:;|&&)\s*" + GH)
CI_CHECKS = RX(P + r"gh\s+run\s+list\b[^\n;&|]*--commit|" + P + r"gh\s+api\b[^\n;&|]*commits/[^\s/]+/(?:check-runs|check-suites|status)|" + P + r"gh\s+pr\s+checks\b")
POLL_KINDS = (('for-loop (not matched by the guard pattern)', RX(FORLOOP)), ('until/while loop', RX(P + r"(?:until|while)\b(?=.{0,1500}?\b" + GH + r")(?=.{0,1500}?\bsleep\b)")), ('watch', RX(r"gh\s+run\s+watch\b|gh\s+pr\s+checks\b[^\n;&|]*--watch")), ('sleep-then-gh', RX(r"sleep")))
CHECK_KINDS = (('commit', RX(r"gh\s+run\s+list\b[^\n;&|]*--commit|commits/[^\s/]+/(?:check-runs|check-suites|status)")), ('pr-checks', RX(r"gh\s+pr\s+checks")))
INFLIGHT = RX(P + r"nohup\s|" + P + r"(?:[\w/.-]*\s)?git\s+(?:-C\s+\S+\s+)?push\b(?![^\n;&|]*--dry-run)|" + P + r"gh\s+workflow\s+run\b|" + P + r"gh\s+pr\s+create\b")
DOCS_GENERIC = r"\bsphinx-build\b|-m\s+sphinx\b|" + P + r"(?:\w+=\S+\s+)*sphinx\s+-|\bmake\s+(?:-C\s+docs\s+)?html\b|http\.server"

def in_project(s, project):
    """A row with no project applies everywhere; with one, only where its regular expression is found."""
    return not project or bool(re.search(project, s['cwd'] + ' ' + s['project']))

def docs_lesson(project, script, extra=()):
    sit = RX('|'.join([DOCS_GENERIC] + list(extra))); inner = regex_lesson(sit, EXEC(script))
    def f(s, since):
        if not in_project(s, project): return None
        r = inner(s, since)
        for e in s['ev']:
            if e['k'] == 'call' and e['ts'] >= since and str(e['name']).startswith('mcp__plugin_playwright') and re.search(r"localhost|127\.0\.0\.1|_build|readthedocs", json.dumps(e['inp'])):
                x = {'ts': e['ts'], 'cmd': e['name'] + ' ' + json.dumps(e['inp'])[:200]}; r['hits'].append(x); r['hand'].append(x)
        return r
    return f

PUSH = RX(P + r"git\s+(?:-C\s+\S+\s+)?push\b(?![^\n;&|]*(?:--dry-run|--delete))")
def push_lesson(s, since):
    B = bash(s, since); H = []; F = []; N = []
    for j, (i, e) in enumerate(B):
        c = cmd(e); m = PUSH.search(c)
        if not m or e['err']: continue
        after = c[m.end():] + '\n' + '\n'.join(cmd(x) for _, x in B[j + 1:j + 5])
        H.append(q(e))
        if re.search(r"git\s+(?:-C\s+\S+\s+)?ls-remote", after): F.append({**q(e), 'verified': 'ls-remote'})
        else:
            v = re.search(r"rev-parse\s+(?:--?\w+\s+)*origin/\S*|git\s+(?:log|diff|branch\s+-\w*[rv]\w*|status)[^\n;&|]*origin/\S*|git\s+status\s+-sb|git\s+fetch\b|gh\s+(?:pr\s+(?:view|checks|list)|run\s+(?:list|view|watch)|api\b)", after)
            N.append({**q(e), 'verified': v.group(0)[:60] if v else 'nothing in the next 4 Bash calls'})
    return {'hits': H, 'followed': F, 'hand': N}

JOBLOG = RX(P + r"gh\s+run\s+view\b[^\n;&|]*--log(?:-failed)?\b|" + P + r"gh\s+api\b[^\n;&|]*actions/jobs/[^\s/]+/logs")
KILLSH = RX(P + r"pkill\s+(?:-\w+\s+)*-f\s+[\"']?[^\s\"';&|]*\.(?:sh|zsh)\b")
def kill_lesson(s, since):
    B = bash(s, since); H = []; F = []; N = []
    for j, (i, e) in enumerate(B):
        c = cmd(e); ms = list(KILLSH.finditer(c))
        if not ms: continue
        H.append(q(e))
        rest = KILLSH.sub(' ', c) + '\n' + '\n'.join(cmd(x) for _, x in B[j + 1:j + 3])
        k = re.search(r"\bp?kill\b", rest); p = re.search(r"\bps\s+(?:-|a|u|e)|\bpgrep\b", rest)
        (F if (k and p) else N).append({**q(e), 'children_killed': bool(k), 'ps_or_pgrep_after': bool(p)})
    return {'hits': H, 'followed': F, 'hand': N}

PG = RX(P + r"(?:pgrep|pkill)\s+(?:-\w+\s+)*-\w*f")
PGLOOP = RX(r"\b(?:while|until)\s+(?:!\s*)?(?:\[\s*)?(?:-[nz]\s+)?[\"$( ]*pgrep\s+(?:-\w+\s+)*-\w*f")
def pgrep_lesson(s, since):
    H = []; F = []; N = []
    for i, e in bash(s, since):
        c = cmd(e)
        if PG.search(c) or PGLOOP.search(c):
            H.append(q(e))
            if PGLOOP.search(c): N.append({**q(e), 'err': e['err']})
        if re.search(r"\bkill\s+-0\b", c): F.append(q(e))
    return {'hits': H, 'followed': F, 'hand': N}

PYTEST = RX(P + r"(?:\w+=\S+\s+)*(?:uv\s+run\s+(?:-\w+\s+)*)?(?:[\w/.-]*python3?\s+-m\s+)?(?:[\w/.-]*/)?pytest\b[^\n;&|]*")
def xdist_lesson(project):
    def f(s, since):
        if not in_project(s, project): return None
        H = []; F = []; N = []
        for i, e in bash(s, since):
            for m in PYTEST.finditer(cmd(e)):
                H.append(q(e))
                if re.search(r"\s-n\s*(?:\d+|auto)\b|--numprocesses", m.group(0)): N.append({**q(e), 'unrecognized_n': 'unrecognized arguments' in (e['res'] or '')})
                else: F.append(q(e))
                break
        return {'hits': H, 'followed': F, 'hand': N}
    return f

def check_after_edit_lesson(project, file, script):
    """`file` is the document (say report.tex); an edit of any file of its extension counts, and so
    does a command, usually a patch script, that names `file` and writes it."""
    ext = os.path.splitext(file)[1]; fn = re.escape(file)
    writes = re.compile((r"(?:\b(?:p|path|f|fn)\s*=\s*['\"]@@['\"])(?=.*(?:open\([^)]*['\"]w|\.write\(|write_text))|open\(\s*['\"]@@['\"]\s*,\s*['\"]w"
                         r"|sed\s+-i[^\n]*@@|Path\(['\"]@@['\"]\)\.write").replace('@@', fn), re.S)
    def f(s, since):
        if not in_project(s, project): return None
        E = [e for e in s['ev'] if e['k'] == 'call' and e['ts'] >= since and e['name'] != 'Read']
        def doc(e):
            if e['name'] in ('Edit', 'Write', 'MultiEdit'): return str(e['inp'].get('file_path', '')).endswith(ext)
            raw = e['inp'].get('command', '') or ''
            return e['name'] == 'Bash' and bool(writes.search(raw))
        H = []; F = []; N = []; j = 0
        while j < len(E):
            if not doc(E[j]): j += 1; continue
            k = j
            while k + 1 < len(E) and doc(E[k + 1]): k += 1
            nxt = E[k + 1:k + 4]; x = {'ts': E[j]['ts'], 'cmd': '%d edit(s) of the document: %s' % (k - j + 1, (E[j]['inp'].get('command') or str(E[j]['inp'].get('file_path', '')))[:160])}
            H.append(x)
            if any(script in (n['inp'].get('command', '') or '') for n in E[j:k + 1] + nxt): F.append(x)
            else: N.append({**x, 'next': [(n['name'] + ' ' + (cmd(n) or str(n['inp'].get('file_path', '')))[:90]) for n in nxt]})
            j = k + 1
        return {'hits': H, 'followed': F, 'hand': N}
    return f

def pipeline_script_lesson(project, names):
    """`names` are regular expressions for the start of the script's basename (say `release_\w*`)."""
    alt = '(?:' + '|'.join(names) + ')'
    PIPE = RX(r"[\w/.$~-]*" + alt + r"\w*\.(?:sh|zsh)")
    WROTE = re.compile(r"cat\s*>\s*\S*" + alt); RAN = re.compile(r"(?:^|[;&|(]\s*|\b(?:bash|sh|zsh|nohup)\s+(?:-\w+\s+)*)[\"']?[\w/.$~{}-]*" + alt, M)
    def f(s, since):
        if not in_project(s, project): return None
        H = []; F = []; N = []
        for e in s['ev']:
            if e['k'] != 'call' or e['ts'] < since: continue
            if e['name'] == 'Write' and PIPE.search(str(e['inp'].get('file_path', ''))):
                x = {'ts': e['ts'], 'cmd': 'Write ' + e['inp']['file_path'] + ' (%d chars)' % len(e['inp'].get('content', ''))}; H.append(x); N.append(x)
            elif e['name'] == 'Bash':
                raw = e['inp'].get('command', '') or ''; c = cmd(e)
                if WROTE.search(raw):
                    x = {'ts': e['ts'], 'cmd': raw[:200] + ' [here-document writes the script]'}; H.append(x); N.append(x)
                elif PIPE.search(c) and RAN.search(c):
                    H.append(q(e))
                    if 'nohup' in c: F.append(q(e))
        return {'hits': H, 'followed': F, 'hand': N}
    return f

def notes_push_lesson(project):
    def f(s, since):
        if not in_project(s, project): return None
        B = bash(s, since); H = []; F = []; N = []
        for j, (i, e) in enumerate(B):
            c = cmd(e); m = PUSH.search(c)
            if not m or e['err']: continue
            H.append(q(e)); bad = None
            for _, x in B[j + 1:j + 7]:
                cx = cmd(x)
                if PUSH.search(cx) and not re.search(r"git\s+add\s+(?:-\w+\s+)*notes/", cx): break
                if re.search(r"git\s+add\s+(?:-\w+\s+)*(?:notes/|\S*MEMORY|\S*memory/)[^\n;&|]*(?:&&|;)\s*git\s+commit", cx): bad = q(x); break
            (N if bad else F).append({**q(e), 'note_commit_after': bad})
        return {'hits': H, 'followed': F, 'hand': N}
    return f

JOBLOG_WHOLE = RX(r"gh\s+api\b[^\n;&|]*--allow-escape-sequences[^\n;&|]*actions/jobs/|gh\s+api\b[^\n;&|]*actions/jobs/[^\n;&|]*--allow-escape-sequences")
DETECTORS = {
    'ci_poll': lambda r: regex_lesson(CI_POLL, EXEC(r['script']), POLL_KINDS),
    'ci_checks': lambda r: regex_lesson(CI_CHECKS, EXEC(r['script']), CHECK_KINDS),
    'inflight': lambda r: regex_lesson(INFLIGHT, EXEC(r['script'])),
    'job_log': lambda r: regex_lesson(JOBLOG, JOBLOG_WHOLE),
    'push': lambda r: push_lesson,
    'kill': lambda r: kill_lesson,
    'pgrep': lambda r: pgrep_lesson,
    'docs': lambda r: docs_lesson(r.get('project'), r['script'], r.get('extra') or ()),
    'no_parallel_flag': lambda r: xdist_lesson(r.get('project')),
    'check_after_edit': lambda r: check_after_edit_lesson(r.get('project'), r['file'], r['script']),
    'pipeline_script': lambda r: pipeline_script_lesson(r.get('project'), r['names']),
    'notes_before_push': lambda r: notes_push_lesson(r.get('project')),
}
LESSONS = []      # (group, name, since (UTC), function), from the configuration
EXCLUDE = set()   # session ids left out (the session the study ran in)
NATIVE = []       # rows of the configuration's "native" list

def load_config(path):
    """Fills LESSONS, EXCLUDE and NATIVE from the local configuration file (see the docstring)."""
    cfg = json.load(open(path))
    EXCLUDE.update(cfg.get('exclude_sessions') or [])
    for r in cfg.get('lessons') or []:
        LESSONS.append((r['group'], r['name'], r['since'], DETECTORS[r['detector']](r)))
    for r in cfg.get('native') or []:
        if r['detector'] not in ('bib', 'slow_loop'): raise SystemExit('unknown native detector: %s' % r['detector'])
        NATIVE.append(r)


def surfaced(ev, S_by, name, sid, since):
    base = name.split('@')[0]; out = collections.Counter()
    for e in ev:
        if e.get('session') != sid: continue
        if e['type'] in ('reuse', 'guard', 'recall', 'use') and (e.get('lesson') == base or base in (e.get('lessons') or [])): out[e['type']] += 1
    for s in S_by[sid]:
        for e in s['ev']:
            if e['k'] == 'hook' and '[compound]' in e['text'] and base in e['text']: out['hook-message-in-transcript'] += 1
            elif e['k'] == 'call' and ('RECORDED-NOTE lesson=' + base) in (e['res'] or ''): out['guard/recall-note-in-transcript'] += 1
            elif e['k'] == 'call' and e['name'] == 'Bash' and re.search(r"compound[\"']?\s+show\s+" + re.escape(base) + r"\b|lessons/" + re.escape(base) + r"/SKILL\.md", e['inp'].get('command', '') or ''): out['session-read-the-lesson'] += 1
            elif e['k'] == 'call' and e['name'] == 'Read' and ('lessons/' + base + '/') in str(e['inp'].get('file_path', '')): out['session-read-the-lesson'] += 1
    return dict(out)

# ---------- native skills
ENTRY = re.compile(r"@(?:article|book|misc|inproceedings|incollection|techreport|phdthesis|mastersthesis|unpublished|inbook|proceedings|online|software)\s*\{\s*[\w:.-]+\s*,", re.I)
LONG = RX(P + r"(?:\w+=\S+\s+)*(?:uv\s+run\s+(?:-\w+\s+)*)?(?:[\w/.-]*python3?\s+-m\s+)?(?:[\w/.-]*/)?(pytest|run_tests\.sh|sphinx-build|sphinx|make|latexmk|npm (?:test|run build)|bun test|gh workflow run|nohup\s+\S+)")
SLOW = re.compile(r"\b(slow|slowly|taking so long|so long|waiting|wasted? time|dead time|taking forever)\b", re.I)
def dur(e):
    try:
        from datetime import datetime as D
        f = lambda t: D.fromisoformat(t.replace('Z', '+00:00'))
        return (f(e['rts']) - f(e['ts'])).total_seconds()
    except Exception: return 0

def native(S, S_by, ev):
    rows = []; inv = []
    for sid, streams in S_by.items():
        for row in NATIVE:
            name, since = row['name'], row['since']
            only = row.get('bib_file') or ''; home = row.get('project') or ''      # the one bibliography file, and the project that holds it
            checker = EXEC(row['checker']) if row.get('checker') else None
            hits = []; kinds = collections.Counter()
            for s in streams:
                if row['detector'] == 'bib':
                    own = bool(home) and bool(re.search(home, s['cwd'] + ' ' + s['project']))
                    for e in s['ev']:
                        if e['k'] != 'call' or e['ts'] < since: continue
                        fp = str(e['inp'].get('file_path', ''))
                        if e['name'] in ('Edit', 'Write', 'MultiEdit') and fp.endswith('.bib'):
                            if only and not (os.path.basename(fp) == only or (home and re.search(home, fp))): continue
                            new = str(e['inp'].get('new_string') or e['inp'].get('content') or '')
                            kinds['adds an entry to a .bib' if ENTRY.search(new) else 'edits a .bib'] += 1; hits.append({'ts': e['ts'], 'cmd': e['name'] + ' ' + fp + ' ' + new[:120]})
                        elif e['name'] == 'Bash':
                            c = cmd(e); raw = e['inp'].get('command', '') or ''
                            # an entry written by the shell or a patch script: the text of an entry and a .bib path in one command
                            if ENTRY.search(raw) and re.search(r"\.bib\b", raw) and not re.match(r"\s*(?:grep|rg|sed -n|awk|cat)\b", raw) and (not only or only in raw):
                                kinds['adds an entry to a .bib'] += 1; hits.append({'ts': e['ts'], 'cmd': raw[:260]})
                            elif checker and checker.search(c): kinds['the bibliography checker'] += 1; hits.append(q(e))
                    if only and own: kinds['in the bibliography project itself'] = 1
                else:
                    runs = collections.defaultdict(list)
                    for i, e in bash(s, since):
                        m = LONG.search(cmd(e))
                        if m: runs[m.group(1).split()[0] if not m.group(1).startswith('nohup') else 'nohup'].append(e)
                    for k, es in runs.items():
                        slow = [e for e in es if dur(e) >= 300]
                        if len(slow) >= 2: kinds['same tool, >=2 foreground runs of >=300 s'] += 1; hits.append({**q(slow[1]), 'secs': dur(slow[1])})
                        elif len([e for e in es if e['inp'].get('run_in_background') or dur(e) >= 300 or k == 'nohup']) >= 2:
                            kinds['same tool, >=2 runs in the background or >=300 s'] += 1; hits.append(q(es[1]))
                    if not s['sub']:
                        for e in s['ev']:
                            if e['k'] == 'prompt' and e['ts'] >= since and not e['meta'] and len(e['text']) < 3000 and not e['text'].lstrip().startswith(('<', '[', 'Caveat', 'This session is being continued')) and SLOW.search(e['text']):
                                kinds['user text: slow/waiting'] += 1; hits.append({'ts': e['ts'], 'cmd': 'USER: ' + e['text'][max(0, SLOW.search(e['text']).start() - 100):SLOW.search(e['text']).end() + 100]})
            # invocations
            uses = []
            for s in streams:
                last_prompt = None; hooks = []
                for e in s['ev']:
                    if e['k'] == 'prompt' and not e['meta'] and e['text'].strip():
                        typed = ('<command-name>/' + name) in e['text'] or re.match(r"\s*/" + re.escape(name) + r"\b", e['text'])
                        if typed and e['ts'] >= since: uses.append({'ts': e['ts'], 'how': 'typed /' + name, 'file': s['file']})
                        if not e['text'].lstrip().startswith('<system-reminder') : last_prompt = e; hooks = []
                    elif e['k'] == 'hook': hooks.append(e)
                    elif e['k'] == 'call' and e['name'] == 'Skill' and e['inp'].get('skill') == name:
                        lp = last_prompt['text'] if last_prompt else ''
                        h = [x for x in hooks if 'Reuse before building' in x['text'] and name in x['text']]
                        if ('<command-name>/' + name) in lp: how = 'typed /' + name
                        elif h: how = 'after a [compound] Reuse before building message that named it'
                        elif name in lp: how = ('subagent prompt' if s['sub'] else 'user prompt') + ' named the skill'
                        else: how = 'model, unprompted (' + ('subagent' if s['sub'] else 'main loop') + ')'
                        uses.append({'ts': e['ts'], 'how': how, 'file': s['file'], 'prompt': lp[:200]})
            if not hits and not uses: continue
            main = [s['file'] for s in streams if not s['sub']]
            hits.sort(key=lambda x: (not x['cmd'].startswith(('Edit', 'Write')) and not ENTRY.search(x['cmd']), x['ts']))
            row = {'group': 'native', 'lesson': name, 'session': sid, 'transcript': main[0] if main else streams[0]['file'], 'situation_hits': len(hits), 'situation_kinds': dict(kinds),
                   'surfaced_by': surfaced(ev, S_by, name, sid, since), 'followed': bool(uses), 'invocations': uses, 'example': hits[:3]}
            rows.append(row)
    return rows

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    config = args[1] if len(args) > 1 else os.environ.get('FOLLOWTHROUGH_CONFIG', '')
    if not args or not config: raise SystemExit('usage: mine_followthrough.py CACHE_DIR CONFIG.json [--rebuild]   (see the docstring for CONFIG.json)')
    load_config(config)
    cache = os.path.join(args[0], 'ft.pkl')
    S = pickle.load(open(cache, 'rb')) if os.path.exists(cache) and '--rebuild' not in sys.argv else build(cache)
    ev = []
    for l in open(HOME + '/.claude/compound/events.jsonl'):
        try: ev.append(json.loads(l))
        except Exception: pass
    S_by = collections.defaultdict(list)
    for s in S:      # sessions in a temporary directory are test and journey runs, not work
        if s['session'] not in EXCLUDE and not re.match(r"-(?:private-)?(?:var-folders|tmp)", s['project']): S_by[s['session']].append(s)
    authors = collections.defaultdict(set)      # sessions that wrote or rewrote the lesson
    for e in ev:
        if e['type'] in ('learn', 'skill') and e.get('lesson'): authors[e['lesson']].add(e.get('session'))
    rows = []
    for group, name, since, fn in LESSONS:
        for sid, streams in S_by.items():
            H = []; F = []; N = []
            for s in streams:
                r = fn(s, since)
                if not r: continue
                for k, dst in (('hits', H), ('followed', F), ('hand', N)):
                    for x in r[k]: dst.append({**x, 'file': s['file']})
            if not H and not F: continue
            main_f = [s['file'] for s in streams if not s['sub']]
            rows.append({'group': group, 'lesson': name, 'session': sid, 'transcript': main_f[0] if main_f else streams[0]['file'], 'situation_hits': len(H),
                         'kinds': dict(collections.Counter(x.get('kind', '') for x in H if x.get('kind'))), 'authoring_session': sid in authors[name.split('@')[0]],
                         'surfaced_by': surfaced(ev, S_by, name, sid, since), 'followed': len(F), 'by_hand': len(N), 'example': (F[:2] + N[:3]) or H[:3]})
    nat = native(S, S_by, ev)
    for r in nat: r['authoring_session'] = r['session'] in authors[r['lesson']]
    rows += nat
    with open(os.path.join(HERE, 'followthrough.jsonl'), 'w') as o:
        for r in rows: o.write(json.dumps(r) + '\n')
    # summary
    print('%-44s %9s %9s %9s %9s %9s' % ('lesson', 'sessions', 'surfaced', 'followed', 'by-hand', 'both'), ' (authoring = sessions that wrote the lesson, counted in the columns)')
    for group, name, since, fn in LESSONS:
        R = [r for r in rows if r['lesson'] == name and r['situation_hits']]
        print('%-44s %9d %9d %9d %9d %9d   calls: hit %d followed %d hand %d; followed w/o situation: %d' % (name, len(R), sum(bool(r['surfaced_by']) for r in R), sum(r['followed'] > 0 for r in R),
              sum(r['by_hand'] > 0 and r['followed'] == 0 for r in R), sum(r['by_hand'] > 0 and r['followed'] > 0 for r in R), sum(r['situation_hits'] for r in R), sum(r['followed'] for r in R), sum(r['by_hand'] for r in R),
              len([r for r in rows if r['lesson'] == name and not r['situation_hits']])), '| authoring sessions among them:', sum(r['authoring_session'] for r in R),
              '| kinds', dict(sum((collections.Counter(r['kinds']) for r in R), collections.Counter())), '| sessions by kind', dict(collections.Counter(k for r in R for k in r['kinds'])))
    for name in [r['name'] for r in NATIVE]:
        R = [r for r in rows if r['lesson'] == name]; A = [r for r in R if r['situation_hits']]
        print('%-44s %9d %9d %9d %9d' % (name, len(A), sum(bool(r['surfaced_by']) for r in A), sum(r['followed'] for r in A), sum(not r['followed'] for r in A)), ' invoked in %d sessions (%d without a situation hit)' % (sum(r['followed'] for r in R), sum(r['followed'] and not r['situation_hits'] for r in R)))
        for k in sorted({k for r in A for k in r['situation_kinds']}):
            K = [r for r in A if k in r['situation_kinds']]
            print('      %-52s sessions %d  invoked %d  not invoked %d  surfaced %d' % (k, len(K), sum(r['followed'] for r in K), sum(not r['followed'] for r in K), sum(bool(r['surfaced_by']) for r in K)))
        for r in R:
            for u in r['invocations']: print('     ', u['ts'], r['session'][:8], os.path.basename(os.path.dirname(u['file']))[-30:], '|', u['how'])

if __name__ == '__main__':
    main()
