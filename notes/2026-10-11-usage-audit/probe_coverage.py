"""How many recorded "no matches found" failures name a word the unmatched-glob probe reads.

The file system of the failing call is gone, so this is coverage, not precision: for each
recall event whose error says `no matches found: WORD`, is WORD one of the words the probe
would have tested (and, tested against an empty directory, reported)? Precision is held
against real zsh in tests/test_probe.py."""
import importlib.machinery, importlib.util, json, os, re, sys, tempfile
loader = importlib.machinery.SourceFileLoader("compound_cli", os.path.join(os.path.dirname(__file__), "..", "..", "bin", "compound"))
spec = importlib.util.spec_from_loader("compound_cli", loader); cli = importlib.util.module_from_spec(spec); loader.exec_module(cli)
events = [json.loads(l) for l in open(os.path.expanduser("~/.claude/compound/events.jsonl")) if l.strip()]
empty = tempfile.mkdtemp()
seen = covered = cut = 0; missed = []
for e in events:
    if e.get("type") != "recall": continue
    m = re.search(r"no matches found: (\S+)", e.get("error") or "")
    if not m: continue
    call = e.get("call") or ""
    seen += 1
    if len(call) >= 3990: cut += 1
    # The probe reads only inside the call's directory and the project: the event's project
    # stands for the project, and the empty directory for where the call ran.
    os.environ["COMPOUND_PROJECT"] = e.get("project") or empty
    words = cli.unmatched_globs(call, empty)
    if m.group(1) in words or any(m.group(1) in w or w in m.group(1) for w in words): covered += 1
    else: missed.append((m.group(1), call[:140].replace("\n", " ")))
print("recall events with a no-matches-found error:", seen, "| word read by the probe:", covered, "| call cut at the log's cap:", cut)
for word, call in missed[:25]: print("  missed", word, "|", call)
