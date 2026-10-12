"""Shared by the ep_* scripts: the cache, project names, rendering.

Settings, all optional, all read from the environment so that nothing about the machine
the study ran on is written here:
  EP_CACHE           directory holding sessions.pkl (ep_parse.py writes it). It holds
                     private transcript text: keep it outside the repository. The
                     default is under the home directory, never a shared temporary
                     directory: a pickle is code to whoever loads it.
  EP_SKIP_SESSIONS   comma-separated session-id prefixes to leave out (the session that
                     ran the study, for one)
"""
import pickle, os, re, stat
CACHE = os.environ.get('EP_CACHE') or os.path.expanduser('~/.cache/compound-usage-audit')
HOME_KEY = re.sub(r'[^A-Za-z0-9]', '-', os.path.expanduser('~'))    # how a project directory under the home directory is named
def env_list(name):
    """A comma-separated environment variable as a list; empty when unset."""
    return [x.strip() for x in os.environ.get(name, '').split(',') if x.strip()]
SKIP_SESSIONS = tuple(env_list('EP_SKIP_SESSIONS'))
def skip_session(sid): return bool(SKIP_SESSIONS) and sid.startswith(SKIP_SESSIONS)
def private_dir(path):
    """The cache directory, made for this user alone. One that is already there is used only
    when it is a real directory of this user's, never a link or another user's."""
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        raise SystemExit('%s is a link or is not this user\'s directory: nothing is written there' % path)
    if st.st_mode & 0o077:
        os.chmod(path, 0o700)
    return path
class write_private(object):
    """Write a cache file readable by this user alone: it holds transcript text. The bytes go
    to a new file of this process's own making, which then takes the name, so a file or a
    link already at that name is replaced and never written through."""
    def __init__(self, path, mode='wb'):
        self.path = os.path.abspath(path)
        folder = private_dir(os.path.dirname(self.path))
        self.tmp = os.path.join(folder, '.%s.%d.tmp' % (os.path.basename(self.path), os.getpid()))
        if os.path.lexists(self.tmp): os.unlink(self.tmp)
        self.fh = os.fdopen(os.open(self.tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600), mode)
    def write(self, data): return self.fh.write(data)
    def __enter__(self): return self
    def __exit__(self, kind, value, tb):
        self.fh.close()
        if kind is None: os.replace(self.tmp, self.path)
        else: os.unlink(self.tmp)
        return False
def open_own(path):
    """Open a pickle for reading, once the opened file itself is shown to be this user's and
    closed to others. The check is made on the descriptor, so the file checked is the file read."""
    d = os.stat(os.path.dirname(os.path.abspath(path)))
    if d.st_uid != os.getuid() or d.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise SystemExit('%s is in a directory open to other users: not loaded' % path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        os.close(fd)
        raise SystemExit('%s is open to other users: a pickle from it is not loaded' % path)
    return os.fdopen(fd, 'rb')
def load():
    with open_own(os.path.join(CACHE, 'sessions.pkl')) as fh:
        return pickle.load(fh)
def proj(s):
    p = s['project']
    p = re.sub('^' + re.escape(HOME_KEY) + '-', '', p)
    p = re.sub(r'--claude-worktrees-agent-\w+$', '(wt)', p)
    if p.startswith('-private-var-folders') or p.startswith('-private-tmp') or p.startswith('-tmp'): return 'TMP:' + p.split('-T-')[-1][:14]
    return p
def is_tmp(s): return proj(s).startswith('TMP:')
def calls(s): return [e for e in s['ev'] if e['k'] == 'call']

def inp_s(e, n=400):
    i = e['inp']; nm = e['name']
    if nm == 'Bash': s = i.get('command', '')
    elif nm in ('Edit', 'Write', 'Read', 'NotebookEdit'):
        s = i.get('file_path', '') or i.get('notebook_path', '')
        if nm == 'Edit': s += '  OLD: ' + (i.get('old_string') or '')[:n // 3].replace('\n', '\\n') + '  NEW: ' + (i.get('new_string') or '')[:n // 2].replace('\n', '\\n')
        if nm == 'Write': s += '  CONTENT: ' + (i.get('content') or '')[:n // 2].replace('\n', '\\n')
    elif nm == 'Agent': s = (i.get('description') or '') + ' :: ' + (i.get('prompt') or '')
    else:
        import json; s = json.dumps(i)
    return s if len(s) <= n else s[:n] + ' ...[+%d]' % (len(s) - n)

def render(s, a, b, cn=400, rn=300, tn=500, mark=()):
    out = []
    for j in range(max(0, a), min(len(s['ev']), b)):
        e = s['ev'][j]; m = '>>' if j in mark else '  '
        if e['k'] == 'prompt': out.append('%s[%d] USER(%s): %s' % (m, j, e['src'], e['text'][:tn * 2]))
        elif e['k'] == 'text': out.append('%s[%d] ASSISTANT: %s' % (m, j, e['text'][:tn]))
        else:
            r = e['res'] or ''
            r = r if len(r) <= 2 * rn else r[:rn] + ' ...[cut]... ' + r[-rn:]
            out.append('%s[%d] %s%s: %s\n        -> %s' % (m, j, e['name'], ' ERR' if e['err'] else '', inp_s(e, cn), r.replace('\n', '\n           ')))
    return '\n'.join(out)

def find_session(S, prefix):
    return [s for s in S if s['session'].startswith(prefix)]
