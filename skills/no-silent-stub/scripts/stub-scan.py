#!/usr/bin/env python3
"""Mechanical scan for silent stubs. Python only, diff-scoped by default.

    python3 stub-scan.py --diff [--base REF]   scan only lines this branch added
    python3 stub-scan.py PATH [PATH ...]       triage an existing tree
    python3 stub-scan.py --help

Findings print as `path:line: rule: message`. Exit 1 if anything is found,
0 if clean, 2 on a usage error, a path that does not exist, or a git failure.
A path that does not exist is an error and not a clean report, because a scan
that quietly skips its input is the defect this scan looks for.

Two things this cannot do, both reported rather than hidden:

* It parses Python and nothing else. Other languages are counted and reported
  as `unscanned-language`; run the grep floor in SKILL.md on those.
* An unmarked fallback with no guard has no syntactic tell. Nothing here
  reaches it. A clean report is a floor, not a proof.

Rules are tuned for precision over recall, measured on third-party libraries
rather than on the fixtures in this repo. Shapes deliberately NOT flagged,
because in real code they are usually correct: a handler that returns a bool
or None (the value is the signal, as in `except OSError: return False`), a
no-op override hook, and a bare `return` with a marker comment.
"""

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

MARKER = re.compile(
    r"(?i)(\btodo\b|\bfixme\b|\bxxx\b|\bhack\b|\bfor now\b|\bplaceholder\b|\bstub\b|"
    r"\bstubbed\b|\bdummy\b|fake data|\bhard-?coded\b|\btemporar(y|ily)\b|"
    r"wire (this|it) up|not implemented|real impl)"
)
# The floor is split in two. A structural match is a finding on its own. A
# marker word is a finding only next to something that returns, because prose
# discussing stubs (this skill's own SKILL.md, for one) is full of marker words
# and none of them are defects. Measured on a real unplanted diff, that split
# removed nine false positives out of eleven.
FLOOR_STRUCTURE = re.compile(
    r"(?i)(return \[\];?\s*$|return \{\};?\s*$|return nil, nil|"
    r"except[^:]*:\s*pass\s*$|catch\s*\([^)]*\)\s*\{\s*\}|"
    r"\bMagicMock\(|pytest\.mark\.(skip|xfail)|@unittest\.skip)"
)
FLOOR_MARKER = re.compile(
    r"(?i)(\btodo\b|\bfixme\b|\bxxx\b|\bplaceholder\b|for now|not implemented)"
)
FLOOR_RETURNS = re.compile(
    r"(?i)(\breturn\b|\bpass\b\s*$|\{\s*\}\s*;?\s*$|\bnil\b|\bnull\b|\bNone\b)"
)
ENV_LOOKUP = re.compile(
    r"(?i)(os\.environ|os\.getenv|getenv\(|environ\.get|getpass|"
    r"\.get\(\s*['\"][A-Za-z0-9_]*(key|token|secret|password|credential)[A-Za-z0-9_]*['\"])"
)
EXPECTED_NAME = re.compile(r"(?i)^(expected|gold|ground_truth|truth|reference|answer_key)")
ACTUAL_NAME = re.compile(r"(?i)^(actual|predicted|prediction|claude|model|got|output|generated)")
CORRECT_NAME = re.compile(r"(?i)^(is_correct|correct|passed|is_valid|matched)$")
SQL_COPY = re.compile(r"(?i)\b(expected\w*)\s+as\s+(\w*(answer|actual|output|prediction)\w*)")
MOCKISH = re.compile(
    r"(from unittest\.mock import|from unittest import mock|import unittest\.mock|"
    r"\bMagicMock\(|\bAsyncMock\(|\bmock\.patch\()"
)
DEFAULTISH = re.compile(r"(?i)(default|fallback|placeholder|sample|stub)")
LOOKUPISH = {"get", "fetch", "lookup", "read", "load", "find", "query"}
LOGGISH = re.compile(r"(?i)(log|warn|error|print|report|emit|capture|record|traceback)")
WIDENING = re.compile(r"^\s*(@\s*)?(pytest\.mark\.(skip|xfail)|unittest\.skip|"
                      r"[A-Za-z_.]*\.skip\(|xfail\()")
# Measured on 308 kLOC of third-party libraries (see SKILL.md "What this scan
# is worth"). `constant-stub` produced six findings there and none were true:
# it cannot tell a deliberate base-class default or an always-constant
# implementation from a stub, because that difference is semantic. It stays in
# the rule set because on a diff, where the code was written minutes ago, that
# confusion mostly does not arise. Triage mode drops it and says so.
DIFF_ONLY_RULES = {"constant-stub"}
SCANNABLE = {".py"}
CODE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb", ".java", ".kt",
                 ".c", ".h", ".cc", ".cpp", ".cs", ".swift", ".sh", ".bash", ".zsh",
                 ".php", ".scala", ".lua", ".pl", ".r", ".m", ".sql"}


def _strip_docstring(body):
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _is_ellipsis(stmt):
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis)


def _is_none(value):
    return value is None or (isinstance(value, ast.Constant) and value.value is None)


def _is_signal(value):
    """True for the conventional vocabulary of absence.

    `None` and booleans are how Python says "no" / "absent" / "did not apply".
    A caller reads them as answers, which is why `except OSError: return False`
    in a predicate is correct code and must never be flagged.
    """
    if _is_none(value):
        return True
    if isinstance(value, (ast.Tuple, ast.List)) and value.elts:
        return all(_is_signal(e) for e in value.elts)
    return isinstance(value, ast.Constant) and isinstance(value.value, bool)


def _is_written_down(value):
    """A value present in the source rather than derived from an input."""
    if value is None:
        return False
    if isinstance(value, ast.Constant):
        return True
    if isinstance(value, (ast.List, ast.Set, ast.Tuple)):
        return all(isinstance(e, ast.Constant) for e in value.elts)
    if isinstance(value, ast.Dict):
        return all(isinstance(v, ast.Constant) for v in value.values)
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
            and value.func.id in {"list", "dict", "set", "tuple"} and not value.args:
        return True
    return False


def _is_invented(value, params):
    """A written-down value a caller cannot read as "absent".

    Stricter than `_is_written_down`: excludes None, booleans, and the
    caller's own parameters, all of which carry information a caller can act on.
    """
    if _is_signal(value):
        return False
    if isinstance(value, ast.Name):
        return value.id not in params and bool(DEFAULTISH.search(value.id))
    if isinstance(value, ast.Constant):
        return value.value != "" and value.value != 0
    return isinstance(value, (ast.Dict, ast.List)) and bool(
        getattr(value, "keys", None) or getattr(value, "elts", None))


def _has_raise(node):
    return any(isinstance(n, ast.Raise) for n in ast.walk(node))


def _names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _param_names(fn):
    a = fn.args
    everything = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
    if a.vararg:
        everything.append(a.vararg)
    if a.kwarg:
        everything.append(a.kwarg)
    return [p.arg for p in everything if p.arg not in {"self", "cls"}]


def _base_names(value):
    out = []
    if isinstance(value, ast.Name):
        out.append(value.id)
    elif isinstance(value, ast.Attribute):
        out.append(value.attr)
        out.extend(_base_names(value.value))
    elif isinstance(value, ast.Subscript):
        sl = value.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            out.append(sl.value)
        out.extend(_base_names(value.value))
    return out


def _target_name(target):
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) \
            and isinstance(target.slice.value, str):
        return target.slice.value
    return None


def _write_once_literals(fn):
    """Locals bound exactly once to a written-down value and never touched again.

    Constant propagation through a single local is the first thing anyone
    writes to get past a scanner, deliberately or not.
    """
    assigns, mentions = {}, {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            mentions[node.id] = mentions.get(node.id, 0) + 1
        if isinstance(node, (ast.AugAssign, ast.AnnAssign)) and \
                isinstance(getattr(node, "target", None), ast.Name):
            assigns.setdefault(node.target.id, []).append(None)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigns.setdefault(t.id, []).append(
                        node.value if _is_written_down(node.value) else None)
                elif isinstance(t, (ast.Subscript, ast.Attribute)):
                    base = t
                    while isinstance(base, (ast.Subscript, ast.Attribute)):
                        base = base.value
                    if isinstance(base, ast.Name):
                        assigns.setdefault(base.id, []).append(None)
    out = {}
    for name, values in assigns.items():
        # bound once, to a literal, and mentioned exactly twice: the binding
        # and one use. Anything else could have been mutated in between.
        if len(values) == 1 and values[0] is not None and mentions.get(name, 0) == 2:
            out[name] = values[0]
    return out


class Scanner:

    def __init__(self, path, source, tree, relpath=None):
        self.path = path
        self.relpath = relpath or path
        self.source = source
        self.tree = tree
        self.findings = []
        self.comments = {}

    def add(self, line, rule, message):
        self.findings.append((str(self.path), line, rule, message))

    def run(self):
        self._load_comments()
        self._check_mock_outside_tests()
        self._check_marker_returns()
        self._check_self_scoring()
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_constant_stub(node)
                self._check_guarded_defaults(node)
            elif isinstance(node, ast.Try):
                self._check_try(node)
            body = getattr(node, "body", None)
            if isinstance(body, list):
                self._check_retry_exhaustion(body)
            orelse = getattr(node, "orelse", None)
            if isinstance(orelse, list):
                self._check_retry_exhaustion(orelse)
        deduped, seen = [], set()
        for f in sorted(self.findings, key=lambda f: (f[1], f[2])):
            if f[:3] in seen:
                continue
            seen.add(f[:3])
            deduped.append(f)
        return deduped

    def _load_comments(self):
        try:
            for tok in tokenize.generate_tokens(io.StringIO(self.source).readline):
                if tok.type == tokenize.COMMENT:
                    self.comments[tok.start[0]] = tok.string
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass

    def _on_test_path(self):
        parts = {p.lower() for p in Path(self.relpath).parts}
        name = Path(self.relpath).name
        return (any("test" in p for p in parts) or name.startswith("test_")
                or name == "conftest.py")

    def _check_mock_outside_tests(self):
        if self._on_test_path():
            return
        for m in MOCKISH.finditer(self.source):
            line = self.source.count("\n", 0, m.start()) + 1
            self.add(line, "mock-outside-tests",
                     f"test double `{m.group(0).strip()}` on a non-test path")

    def _check_marker_returns(self):
        # Only a `return` of a written-down value counts. A marker above a
        # bare `pass` is nearly always an empty test body or a note about the
        # line below it, which is where this rule used to generate its noise.
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Return) or _is_none(node.value):
                continue
            if not _is_written_down(node.value):
                continue
            for probe in (node.lineno, node.lineno - 1):
                text = self.comments.get(probe)
                if text and MARKER.search(text):
                    self.add(node.lineno, "marker-return",
                             f"returns a written-down value under {text.strip()!r}")
                    break

    def _check_self_scoring(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._score_named(_target_name(target), node.value, node.lineno)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                self._score_named(_target_name(node.target), node.value, node.lineno)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        self._score_named(key.value, value, node.lineno)
            elif isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg:
                        self._score_named(kw.arg, kw.value, node.lineno)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                m = SQL_COPY.search(node.value)
                if m:
                    self.add(node.lineno, "self-scoring-eval",
                             f"query aliases `{m.group(1)}` as `{m.group(2)}`")

    def _score_named(self, name, value, lineno):
        if not name:
            return
        if CORRECT_NAME.match(name) and isinstance(value, ast.Constant) \
                and value.value in (True, 1, 1.0):
            self.add(lineno, "self-scoring-eval",
                     f"`{name}` assigned the passing value {value.value!r} rather than compared")
            return
        if not ACTUAL_NAME.match(name):
            return
        for base in _base_names(value):
            if EXPECTED_NAME.match(base):
                self.add(lineno, "self-scoring-eval",
                         f"`{name}` copied from `{base}`, so the check compares a value to itself")
                return

    def _check_try(self, node):
        # Only a BARE `except:` is flagged. `except SpecificError: pass` was
        # measured across 300 kLOC of third-party code and is nearly always
        # deliberate: an optional-import probe, a candidate-file loop, a lookup
        # whose miss the caller already handles. The prose taxonomy still
        # covers it; the mechanical rule does not claim to.
        if self._on_test_path():
            return
        for handler in node.handlers:
            if handler.type is not None or _has_raise(handler):
                continue
            body = _strip_docstring(handler.body)
            if any(LOGGISH.search(ast.unparse(s)) for s in body):
                continue
            self.add(handler.lineno, "swallowed-exception",
                     "bare `except:` catches everything, logs nothing, and never re-raises")

    def _check_constant_stub(self, fn):
        if {ast.unparse(d) for d in fn.decorator_list} & {
                "abstractmethod", "abc.abstractmethod", "overload", "typing.overload",
                "abstractproperty", "singledispatch", "singledispatchmethod"}:
            return
        if fn.name.startswith("__") and fn.name.endswith("__"):
            return  # a protocol method returning a constant is an implementation
        if self._on_test_path():
            return  # toy classes inside a test file are the project's own doubles
        params = _param_names(fn)
        if not params or _has_raise(fn):
            return
        body = _strip_docstring(fn.body)
        if not body or all(_is_ellipsis(s) or isinstance(s, ast.Pass) for s in body):
            return  # a no-op hook declares nothing and returns nothing
        if _names(fn) & set(params):
            return
        propagated = _write_once_literals(fn)
        returns = []
        for s in body:
            if isinstance(s, ast.Return):
                value = s.value
                if isinstance(value, ast.Name) and value.id in propagated:
                    value = propagated[value.id]
                returns.append(value)
            elif isinstance(s, ast.Assign) and len(s.targets) == 1 \
                    and isinstance(s.targets[0], ast.Name) \
                    and s.targets[0].id in propagated:
                continue
            elif isinstance(s, ast.Pass) or _is_ellipsis(s):
                continue
            else:
                return
        real = [r for r in returns if not _is_signal(r)]
        if not real or not all(_is_written_down(r) for r in real):
            return  # None and booleans are signals; only invented values count
        self.add(fn.lineno, "constant-stub",
                 f"`{fn.name}` takes {', '.join(params)} and returns a written-down value "
                 "without reading any of them")

    def _check_guarded_defaults(self, fn):
        if _has_raise(fn):
            return
        params = set(_param_names(fn))
        lookups, creds = set(), set()
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            src = ast.unparse(node.value)
            if ENV_LOOKUP.search(src):
                creds.add(target.id)
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) \
                    and node.value.func.attr in LOOKUPISH:
                lookups.add(target.id)
        propagated = _write_once_literals(fn)
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            test_src = ast.unparse(node.test)
            test_names = _names(node.test)
            for ret in [s for s in ast.walk(node) if isinstance(s, ast.Return)]:
                value = ret.value
                if isinstance(value, ast.Name) and value.id in propagated:
                    value = propagated[value.id]
                if not _is_invented(value, params):
                    continue
                if ENV_LOOKUP.search(test_src) or (test_names & creds):
                    self.add(ret.lineno, "credential-fallback",
                             "returns an invented value on the path where an environment "
                             "value or credential is missing")
                elif (test_names & lookups) and ("None" in test_src
                                                 or test_src.startswith("not ")
                                                 or " not in " in test_src):
                    self.add(ret.lineno, "cache-miss-default",
                             "serves a default on the lookup-miss path, indistinguishable "
                             "from a real hit")

    def _check_retry_exhaustion(self, body):
        for i, stmt in enumerate(body):
            if not isinstance(stmt, (ast.For, ast.While)):
                continue
            if not any(isinstance(n, ast.Try) for n in ast.walk(stmt)):
                continue
            if not any(isinstance(n, ast.Return) for n in ast.walk(stmt)):
                continue  # a loop that never returns a success was not retrying
            tail = []
            if stmt.orelse:
                tail.append(stmt.orelse[-1])
            if i + 1 < len(body):
                tail.append(body[i + 1])
            for nxt in tail:
                if isinstance(nxt, ast.Return) and _is_written_down(nxt.value) \
                        and not _is_signal(nxt.value):
                    self.add(nxt.lineno, "retry-exhaustion-empty",
                             "every attempt failed and the exhaustion path returns a "
                             "written-down value instead of raising")


def scan_file(path, relpath=None):
    try:
        source = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [(str(path), 1, "unreadable", f"could not read: {exc}")]
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [(str(path), exc.lineno or 1, "unparseable", f"could not parse: {exc.msg}")]
    return Scanner(path, source, tree, relpath).run()


def collect(roots):
    """Return (python files as (path, relpath), unscanned-language counts)."""
    python, other = [], {}
    for root in roots:
        p = Path(root)
        if not p.exists():
            raise FileNotFoundError(root)
        if p.is_dir():
            for q in sorted(p.rglob("*")):
                if not q.is_file() or "__pycache__" in q.parts:
                    continue
                if q.suffix in SCANNABLE:
                    python.append((q, q.relative_to(p)))
                elif q.suffix in CODE_SUFFIXES:
                    other[q.suffix] = other.get(q.suffix, 0) + 1
        elif p.suffix in SCANNABLE:
            python.append((p, Path(p.name)))
        else:
            other[p.suffix or "(no suffix)"] = other.get(p.suffix or "(no suffix)", 0) + 1
    return python, other


def unscanned_finding(root, other):
    if not other:
        return []
    listed = ", ".join(f"{n} {suffix}" for suffix, n in sorted(other.items()))
    return [(str(root), 0, "unscanned-language",
             f"{sum(other.values())} files not parsed ({listed}); this scan is Python "
             "only, so run the grep floor from SKILL.md over them")]


def git_added_lines(base):
    """Map of path -> {line number: text} for lines this diff adds."""
    cmd = ["git", "diff", "-U0", "--no-color", base] if base else \
        ["git", "diff", "-U0", "--no-color", "HEAD"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    added, path, lineno = {}, None, 0
    for line in proc.stdout.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++") and path:
            added.setdefault(path, {})[lineno] = line[1:]
            lineno += 1

    # `git diff` does not mention a file that was never added to the index, so
    # a brand-new module full of stubs would scan clean. Every line of an
    # untracked file is a line this change added.
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True)
    if untracked.returncode == 0:
        for rel in untracked.stdout.splitlines():
            if not rel:
                continue
            try:
                text = Path(rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            added.setdefault(rel, {}).update(
                {i: line for i, line in enumerate(text.splitlines(), start=1)})
    return added


def scan_diff(base):
    findings = []
    added = git_added_lines(base)
    for rel, lines in sorted(added.items()):
        path = Path(rel)
        if path.suffix in SCANNABLE and path.exists():
            for f in scan_file(path, path):
                if f[1] in lines:
                    findings.append(f)
        elif path.suffix in CODE_SUFFIXES:
            for lineno, text in sorted(lines.items()):
                hit = FLOOR_STRUCTURE.search(text)
                if not hit and FLOOR_MARKER.search(text):
                    nearby = text + " " + lines.get(lineno + 1, "")
                    hit = FLOOR_RETURNS.search(nearby)
                if hit:
                    findings.append((rel, lineno, "floor-match",
                                     f"added line matches the grep floor: {text.strip()[:70]!r}"))
        if path.suffix in SCANNABLE or path.suffix in CODE_SUFFIXES:
            for lineno, text in sorted(lines.items()):
                if WIDENING.search(text):
                    findings.append((rel, lineno, "test-widening",
                                     f"this change adds a skip or xfail: {text.strip()[:70]!r}"))
    return findings


TRIAGE_HEADER = (
    "stub-scan: triage mode. Measured on 308 kLOC of third-party libraries this "
    "mode found 2 things, 1 of them real, so read every finding and expect most "
    "to be wrong. {dropped} is suppressed here (0 of 6 true on that corpus) and "
    "runs only under --diff. Nothing here reaches an unmarked fallback."
)


def main(argv):
    parser = argparse.ArgumentParser(
        prog="stub-scan.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="files or directories to triage")
    parser.add_argument("--diff", action="store_true",
                        help="scan only the lines this branch adds (the default posture)")
    parser.add_argument("--base", default=None, help="git ref to diff against (default HEAD)")
    args = parser.parse_args(argv[1:])

    if args.diff and args.paths:
        parser.error("--diff scans the working tree's diff; do not also pass paths")
    if not args.diff and not args.paths:
        parser.error("give --diff, or one or more paths to triage")

    try:
        if args.diff:
            findings = scan_diff(args.base)
        else:
            python, other = collect(args.paths)
            findings = []
            for path, rel in python:
                findings.extend(f for f in scan_file(path, rel)
                                if f[2] not in DIFF_ONLY_RULES)
            findings.extend(unscanned_finding(args.paths[0], other))
            print(TRIAGE_HEADER.format(dropped=", ".join(sorted(DIFF_ONLY_RULES))),
                  file=sys.stderr)
    except FileNotFoundError as exc:
        print(f"stub-scan: no such path: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"stub-scan: {exc}", file=sys.stderr)
        return 2

    for path, line, rule, message in findings:
        print(f"{path}:{line}: {rule}: {message}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
