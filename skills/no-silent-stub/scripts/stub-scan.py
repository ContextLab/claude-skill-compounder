#!/usr/bin/env python3
"""First-pass mechanical scan for silent stubs in Python source.

Usage:
    python3 stub-scan.py PATH [PATH ...]

Prints one finding per line, as `path:line: rule: message`, and exits 1 when
anything is found, 0 when clean, 2 on a usage error. A file that fails to parse
is reported as a finding rather than skipped, because a scan that quietly
skips input is itself the defect this scan looks for.

The scan is deliberately conservative. It answers "can a caller tell this apart
from success?" only where that question has a syntactic answer: a value returned
without being derived, a handler that discards its exception, a fallback keyed
on a missing credential or a cache miss. A fallback with no marker and no
guard is invisible here, so a clean report is a starting point, not a proof.
"""

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

MARKER = re.compile(
    r"(?i)\b(todo|fixme|xxx|hack|for now|placeholder|stub|stubbed|dummy|"
    r"fake data|hardcode|hardcoded|hard-coded|temporary|temporarily|"
    r"wire this up|wire it up|not implemented|real impl)\b"
)
CRED = re.compile(r"(?i)(api[_-]?key|apikey|token|secret|credential|password|environ|getenv)")
EXPECTED_NAME = re.compile(r"(?i)^(expected|gold|ground_truth|truth|reference|answer_key)")
ACTUAL_NAME = re.compile(r"(?i)^(actual|predicted|prediction|claude|model|got|output|generated)")
CORRECT_NAME = re.compile(r"(?i)^(is_correct|correct|passed|is_valid|matched|score)$")
SQL_COPY = re.compile(r"(?i)\b(expected\w*)\s+as\s+(\w*(answer|actual|output|prediction)\w*)")
MOCKISH = re.compile(
    r"(from unittest\.mock import|from unittest import mock|import unittest\.mock|"
    r"\bMagicMock\b|\bAsyncMock\b|\bmock\.patch\b|\bmonkeypatch\b|^import mock$)",
    re.MULTILINE,
)
DEFAULTISH = re.compile(r"(?i)(default|fallback|placeholder|sample|stub)")
LOOKUPISH = {"get", "fetch", "lookup", "read", "load", "find", "query"}
LOGGISH = re.compile(r"(?i)(log|warn|error|print|report|emit|capture|record)")

def _strip_docstring(body):
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _is_ellipsis(stmt):
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis)


def _is_empty_value(value):
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value is None or value.value == "" or value.value == 0 or value.value is False
    if isinstance(value, (ast.List, ast.Set, ast.Tuple)):
        return not value.elts
    if isinstance(value, ast.Dict):
        return not value.keys
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
            and value.func.id in {"list", "dict", "set", "tuple"} and not value.args:
        return True
    return False


def _is_bare_value(value):
    """A value written down rather than derived: a literal or an empty container."""
    return value is None or isinstance(value, ast.Constant) or _is_empty_value(value)


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


def _decorators(fn):
    return {ast.unparse(d) for d in fn.decorator_list}


def _base_names(value):
    """Identifier-ish strings a value is built from, for name-matching rules."""
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
                self._check_function(node)
            if isinstance(node, ast.ExceptHandler):
                self._check_handler(node)
        for node in ast.walk(self.tree):
            body = getattr(node, "body", None)
            if isinstance(body, list):
                self._check_retry_exhaustion(body)
            orelse = getattr(node, "orelse", None)
            if isinstance(orelse, list):
                self._check_retry_exhaustion(orelse)
        self.findings.sort(key=lambda f: (f[1], f[2]))
        deduped, seen = [], set()
        for f in self.findings:
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
        except (tokenize.TokenError, IndentationError):
            pass

    def _check_mock_outside_tests(self):
        parts = {p.lower() for p in Path(self.relpath).parts}
        name = Path(self.relpath).name
        if any("test" in p for p in parts) or name.startswith("test_") or name == "conftest.py":
            return
        for m in MOCKISH.finditer(self.source):
            line = self.source.count("\n", 0, m.start()) + 1
            self.add(line, "mock-outside-tests",
                     f"test double `{m.group(0).strip()}` on a non-test path")

    def _check_marker_returns(self):
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.Return, ast.Pass)):
                continue
            if isinstance(node, ast.Return) and not _is_bare_value(node.value):
                continue
            for probe in (node.lineno, node.lineno - 1, node.lineno - 2):
                text = self.comments.get(probe)
                if text and MARKER.search(text):
                    kind = "return" if isinstance(node, ast.Return) else "pass"
                    self.add(node.lineno, "marker-return",
                             f"{kind} on a live path under comment {text.strip()!r}")
                    break

    def _check_self_scoring(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._score_pair(target, node.value, node.lineno)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                self._score_pair(node.target, node.value, node.lineno)
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

    def _score_pair(self, target, value, lineno):
        if isinstance(target, ast.Name):
            self._score_named(target.id, value, lineno)

    def _score_named(self, name, value, lineno):
        if CORRECT_NAME.match(name) and isinstance(value, ast.Constant) \
                and value.value in (True, 1, 1.0, 100):
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

    def _check_handler(self, handler):
        if _has_raise(handler):
            return
        body = _strip_docstring(handler.body)
        inert = all(
            isinstance(s, ast.Pass)
            or _is_ellipsis(s)
            or (isinstance(s, ast.Return) and _is_bare_value(s.value))
            for s in body
        ) if body else True
        logs = any(
            LOGGISH.search(ast.unparse(s)) for s in body
        )
        if inert and not logs:
            what = "bare `except:`" if handler.type is None else \
                f"`except {ast.unparse(handler.type)}`"
            self.add(handler.lineno, "swallowed-exception",
                     f"{what} discards the error and continues as if nothing failed")
        elif handler.type is None and not logs:
            self.add(handler.lineno, "swallowed-exception",
                     "bare `except:` catches everything and never re-raises")

    def _check_function(self, fn):
        self._check_constant_stub(fn)
        self._check_guarded_defaults(fn)

    def _check_constant_stub(self, fn):
        if _decorators(fn) & {"abstractmethod", "abc.abstractmethod", "overload",
                              "typing.overload", "abstractproperty"}:
            return
        params = _param_names(fn)
        if not params:
            return
        body = _strip_docstring(fn.body)
        if not body or all(_is_ellipsis(s) for s in body):
            return
        if _has_raise(fn):
            return
        if _names(fn) & set(params):
            return
        shaped = all(
            isinstance(s, ast.Pass)
            or _is_ellipsis(s)
            or (isinstance(s, ast.Return) and _is_bare_value(s.value))
            for s in body
        )
        if shaped:
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
            if CRED.search(src):
                creds.add(target.id)
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) \
                    and node.value.func.attr in LOOKUPISH:
                lookups.add(target.id)
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            test_src = ast.unparse(node.test)
            test_names = _names(node.test)
            returned = [s for s in ast.walk(node) if isinstance(s, ast.Return)]
            for ret in returned:
                if ret.value is None or (isinstance(ret.value, ast.Constant)
                                         and ret.value.value is None):
                    continue
                invented = (
                    isinstance(ret.value, ast.Constant)
                    or (isinstance(ret.value, ast.Name) and ret.value.id not in params
                        and DEFAULTISH.search(ret.value.id))
                    or (isinstance(ret.value, (ast.Dict, ast.List)) )
                )
                if not invented:
                    continue
                if CRED.search(test_src) or (test_names & creds):
                    self.add(ret.lineno, "credential-fallback",
                             "returns an invented value on the path where a credential or "
                             "environment value is missing")
                elif (test_names & lookups) and ("None" in test_src or test_src.startswith("not ")
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
            tail = []
            if stmt.orelse:
                tail.append(stmt.orelse[-1])
            if i + 1 < len(body):
                tail.append(body[i + 1])
            for nxt in tail:
                if isinstance(nxt, ast.Return) and _is_empty_value(nxt.value):
                    self.add(nxt.lineno, "retry-exhaustion-empty",
                             "every attempt failed and the exhaustion path returns an empty "
                             "value instead of raising")


def scan_file(path, relpath=None):
    source = Path(path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [(str(path), exc.lineno or 1, "unparseable", f"could not parse: {exc.msg}")]
    return Scanner(path, source, tree, relpath).run()


def iter_paths(roots):
    """Yield (path, path-relative-to-the-root-given) so that the test-path

    exclusion is judged on the project's own layout and not on wherever the
    project happens to be checked out.
    """
    for root in roots:
        p = Path(root)
        if p.is_dir():
            for q in sorted(p.rglob("*.py")):
                if "__pycache__" not in q.parts:
                    yield q, q.relative_to(p)
        elif p.suffix == ".py":
            yield p, Path(p.name)


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    findings = []
    for path, relpath in iter_paths(argv[1:]):
        findings.extend(scan_file(path, relpath))
    for path, line, rule, message in findings:
        print(f"{path}:{line}: {rule}: {message}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
