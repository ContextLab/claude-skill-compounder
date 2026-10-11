#!/usr/bin/env python3
"""guard_text: what part of a Bash command is command text, and what is data.

Proposed for `compound check` (the study is notes/2026-10-11-usage-audit/guard-study.md).
Standard library only, Python 3.9.

    classify(command)  -> one letter per character of the command:
        c  command text: words, operators, the quote characters themselves
        s  inside '...' or $'...'
        d  inside "..." (a $( ) or ` ` inside it is c again: it runs)
        h  a here-document body and its closing line
        #  a comment
    A string or a body handed to a shell IS a command and is classified as one, to any
    depth: `bash -c '...'`, `zsh -lc "..."`, `eval '...'`, `bash <<EOF`, `sh -s <<'EOF'`.
    A $( ) or ` ` inside a here-document whose delimiter is not quoted is c: the shell
    runs it before the body is handed over.

    guard_view(command)        the text a pattern is tested against: the command with
                               every here-document body and comment taken out.
    guard_search(regex, command)  the rule proposed: the pattern is searched in
                               guard_view, and a match counts only when it BEGINS in
                               command text (its first character that is not white
                               space is a `c`). A match may run on into a quoted
                               argument (`sed -i 's/a/b/' f`); it may not start in one.

The scanner never raises on a command it cannot follow (an unclosed quote, a `case`
pattern's lone `)`): what it cannot place it leaves as it found it, and a here-document
that never closes runs to the end, as it does in the shell.
"""
import re

SHELLS = ("sh", "bash", "zsh", "dash", "ksh")
WRAPPERS = ("sudo", "env", "nohup", "time", "command", "exec", "nice", "caffeinate", "timeout",
            "gtimeout", "noglob", "builtin", "xargs")
_BREAK = set(" \t\n;&|<>()")
_ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
_SHELL_C = re.compile(r"^-[A-Za-z]*c$")
SHELL_AWARE = True      # the study turns this off to measure what it is worth


def _basename(word):
    return word.rsplit("/", 1)[-1]


def _feeds_shell(words):
    """`words` are the words of a simple command up to a `<<`: is its standard input a
    script? True for a shell that names no script file (`bash`, `sh -s`, `zsh -l`,
    `sudo bash -s -- arg`)."""
    if not SHELL_AWARE:
        return False
    words = [w for w in words if not _ASSIGN.match(w)]
    for index, word in enumerate(words):
        if _basename(word) in SHELLS:
            rest = words[index + 1:]
            if any(_SHELL_C.match(w) for w in rest):
                return False  # the script is the -c string; the body is its input
            for arg in rest:
                if arg in ("-s", "--"):
                    return True
                if not arg.startswith("-") and not re.match(r"^\d*[<>]", arg):
                    return False  # a script file: the body is that script's input
            return True
        if _basename(word) in WRAPPERS or word.startswith("-") or word.isdigit():
            continue
        return False
    return False


def _takes_command_string(words):
    """The quoted word that comes next is a command line: it follows `-c` (or `-lc`)
    of a shell, or it is an argument of `eval`."""
    if not SHELL_AWARE:
        return False
    words = [w for w in words if not _ASSIGN.match(w)]
    if not words:
        return False
    head = [w for w in words if not (_basename(w) in WRAPPERS or w.isdigit())]
    if head and head[0] == "eval":
        return True
    return bool(_SHELL_C.match(words[-1])) and any(_basename(w) in SHELLS for w in words[:-1])


def _scan(text, kind, i, end, stack):
    """Classify text[i:end] into `kind`. `stack` is the open contexts ('dq', 'paren',
    'bt', 'brace', ['arith', depth]); when it was given non-empty the scan returns where
    it empties. Returns the position it stopped at."""
    base = bool(stack)
    pending = []            # here-documents whose body starts after the next newline
    start = i               # where the simple command being read began

    def words_before(pos):
        return text[start:pos].split()

    while i < end:
        ch = text[i]
        ctx = stack[-1] if stack else "top"
        if isinstance(ctx, list):  # arithmetic
            if ch == "(":
                ctx[1] += 1
            elif ch == ")":
                if ctx[1] == 0 and text.startswith("))", i):
                    stack.pop()
                    i += 2
                    if base and not stack:
                        return i
                    continue
                ctx[1] = max(0, ctx[1] - 1)
            i += 1
            continue
        if ctx == "dq":
            if ch == "\\" and i + 1 < end:
                kind[i] = kind[i + 1] = ord("d")
                i += 2
                continue
            if ch == '"':
                stack.pop()
                i += 1
                if base and not stack:
                    return i
                continue
            if text.startswith("$((", i):
                stack.append(["arith", 0])
                i += 3
                continue
            if text.startswith("$(", i):
                stack.append("paren")
                i += 2
                start = i
                continue
            if text.startswith("${", i):
                stack.append("brace")
                i += 2
                continue
            if ch == "`":
                stack.append("bt")
                i += 1
                start = i
                continue
            kind[i] = ord("d")
            i += 1
            continue
        # ---- command text: top, paren, bt, brace
        if ch == "\\" and i + 1 < end:
            i += 2
            continue
        if ch == "'" or (ch == "$" and text.startswith("$'", i)):
            ansi = ch == "$"
            j = i + (2 if ansi else 1)
            body = j
            while j < end and text[j] != "'":
                j += 2 if (ansi and text[j] == "\\") else 1
            j = min(j, end)
            if not ansi and ctx != "brace" and _takes_command_string(words_before(i)):
                _scan(text, kind, body, j, [])
            else:
                for k in range(body, j):
                    kind[k] = ord("s")
            i = j + 1
            continue
        if ch == '"' or (ch == "$" and text.startswith('$"', i)):
            opened = i
            i += 2 if ch == "$" else 1
            if ctx != "brace" and _takes_command_string(words_before(opened)):
                scratch = bytearray(kind)
                close = _scan(text, scratch, i, end, ["dq"])
                inner_end = close - 1 if text[close - 1:close] == '"' and close - 1 >= i else close
                _scan(text, kind, i, inner_end, [])
                i = close
                continue
            stack.append("dq")
            continue
        if ch == "`":
            if ctx == "bt":
                stack.pop()
                i += 1
                if base and not stack:
                    return i
            else:
                stack.append("bt")
                i += 1
                start = i
            continue
        if ch == "$":
            if text.startswith("$((", i):
                stack.append(["arith", 0])
                i += 3
                continue
            if text.startswith("$(", i):
                stack.append("paren")
                i += 2
                start = i
                continue
            if text.startswith("${", i):
                stack.append("brace")
                i += 2
                continue
            i += 1
            continue
        if ctx == "brace":
            if ch == "}":
                stack.pop()
                if base and not stack:
                    return i + 1
            i += 1
            continue
        if ch == "(":
            if text.startswith("((", i) and text[start:i].strip() in ("", "for", "while", "until", "if"):
                stack.append(["arith", 0])
                i += 2
                continue
            stack.append("paren")
            i += 1
            start = i
            continue
        if ch == ")":
            if ctx == "paren":
                stack.pop()
                i += 1
                if base and not stack:
                    return i
                continue
            i += 1
            continue
        if ch == "#" and (i == 0 or text[i - 1] in " \t\n;&|("):
            j = text.find("\n", i, end)
            j = end if j < 0 else j
            for k in range(i, j):
                kind[k] = ord("#")
            i = j
            continue
        if ch == "<" and text.startswith("<<", i):
            if text.startswith("<<<", i):
                i += 3
                continue
            j = i + 2
            dash = j < end and text[j] == "-"
            if dash:
                j += 1
            while j < end and text[j] in " \t":
                j += 1
            delim, quoted = [], False
            while j < end and text[j] not in _BREAK:
                if text[j] in "'\"":
                    close = text.find(text[j], j + 1, end)
                    if close < 0:
                        break
                    delim.append(text[j + 1:close])
                    quoted = True
                    j = close + 1
                elif text[j] == "\\" and j + 1 < end:
                    delim.append(text[j + 1])
                    quoted = True
                    j += 2
                else:
                    delim.append(text[j])
                    j += 1
            delim = "".join(delim)
            if not delim:
                i += 2
                continue
            pending.append((delim, dash, quoted, _feeds_shell(words_before(i))))
            i = j
            continue
        if ch == "\n":
            if pending:
                pos = i + 1
                for delim, dash, quoted, shell in pending:
                    body_start = pos
                    body_end = close_end = end
                    while pos < end:
                        eol = text.find("\n", pos, end)
                        eol = end if eol < 0 else eol
                        line = text[pos:eol]
                        if (line.lstrip("\t") if dash else line) == delim:
                            body_end, close_end = pos, eol
                            break
                        pos = eol + 1
                    if shell:
                        _scan(text, kind, body_start, body_end, [])
                    else:
                        for k in range(body_start, body_end):
                            kind[k] = ord("h")
                        if not quoted:
                            _expansions(text, kind, body_start, body_end)
                    for k in range(body_end, close_end):
                        kind[k] = ord("h")
                    pos = close_end + 1
                    if close_end >= end:
                        break
                pending = []
                # go on from the newline that ends the closing line, so that what
                # follows it starts a line and a simple command
                i = min(pos - 1, end)
                if i < end and text[i] == "\n":
                    start = i + 1
                    i += 1
                continue
            start = i + 1
            i += 1
            continue
        if ch in ";&|":
            start = i + 1
        i += 1
    return i


def _expansions(text, kind, lo, hi):
    """In a here-document body whose delimiter is not quoted, a $( ) or ` ` is run by
    the shell: classify what is inside as command text."""
    k = lo
    while k < hi:
        if text[k] == "\\":
            k += 2
        elif text.startswith("$(", k) and not text.startswith("$((", k):
            inner = bytearray(b"c" * len(kind))
            stop = _scan(text, inner, k + 2, hi, ["paren"])
            for m in range(k, min(stop, hi)):
                kind[m] = inner[m]
            k = max(stop, k + 2)
        elif text[k] == "`":
            stop = text.find("`", k + 1, hi)
            if stop < 0:
                return
            inner = bytearray(b"c" * len(kind))
            _scan(text, inner, k + 1, stop, [])
            for m in range(k, stop + 1):
                kind[m] = inner[m]
            k = stop + 1
        else:
            k += 1


def classify(command):
    kind = bytearray(b"c" * len(command))
    try:
        _scan(command, kind, 0, len(command), [])
    except RecursionError:
        pass
    return kind.decode("ascii")


def view(command, kinds, drop):
    """The command without the characters whose kind is in `drop`."""
    return "".join(ch for ch, k in zip(command, kinds) if k not in drop)


def guard_view(command, kinds=None):
    """(text, kinds of that text): here-document bodies and comments taken out."""
    kinds = classify(command) if kinds is None else kinds
    keep = [(ch, k) for ch, k in zip(command, kinds) if k not in "h#"]
    return "".join(ch for ch, _ in keep), "".join(k for _, k in keep)


def starts_in_command(match, kinds):
    """The match's first character that is not white space is command text."""
    text = match.string
    pos = match.start()
    while pos < match.end() and text[pos].isspace():
        pos += 1
    if pos >= len(kinds):
        return True
    return kinds[pos] == "c"


def guard_search(regex, command, kinds=None):
    """The proposed rule. `regex` is a compiled pattern (re.MULTILINE). Returns the
    first match that begins in command text, or None."""
    text, text_kinds = guard_view(command, kinds)
    for match in regex.finditer(text):
        if starts_in_command(match, text_kinds):
            return match
    return None


def simple_commands(command, kinds=None):
    """The simple commands of a command, quoted arguments kept, here-document bodies and
    comments dropped: split where command text has ; & | ( ) or a newline."""
    text, text_kinds = guard_view(command, kinds)
    out, cur = [], []
    for ch, k in zip(text, text_kinds):
        if k == "c" and ch in ";&|()\n":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [part.strip() for part in out if part.strip()]


if __name__ == "__main__":
    import sys
    source = sys.stdin.read()
    marks = classify(source)
    offset = 0
    for line in source.split("\n"):
        print(line)
        print(marks[offset:offset + len(line)])
        offset += len(line) + 1
    print("--- guard_view")
    print(guard_view(source, marks)[0])
