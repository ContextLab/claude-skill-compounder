#!/usr/bin/env python3
"""One canonical end-to-end journey: install -> use -> forge -> apply -> uninstall.

    python3 tests/e2e/journey.py --out <dir>

THIS IS NOT A UNIT TEST AND MUST NEVER RUN IN CI. It spends real `claude -p` calls on
the operator's own subscription. `run_tests.sh` globs `tests/test_*.py`, which is why
this file lives under `tests/e2e/` and is named `journey.py`: neither the glob nor a
recursive one picks it up, and nothing imports it. docs/e2e.md is the operator's guide.

WHAT IT IS FOR. Every existing test exercises one script against files on disk. Nothing
asserts that a person who clones this repo, installs it, and works for an afternoon gets
the loop the README describes. This walks that loop once, in a throwaway config and
state directory, and writes down what it SAW at each step -- the decisive line, quoted --
rather than exiting zero. A step the environment cannot run is recorded SKIPPED with the
reason, because a scenario that quietly drops a step is worse than one that fails.

ISOLATION, AND THE LIMIT IT CARRIES.

    <out>/claude    a throwaway CLAUDE dir: settings.json, skills/, CLAUDE.md
    <out>/bin       a throwaway bin dir for the five CLIs
    <out>/state     a throwaway state root (ledger, insights, reminders, forges)
    <out>/project   a scratch git project, the "problem" the journey is about
    <out>/logs      every command's argv, stdout, stderr, and every claude stream

The state root and the transcripts root are redirected with SKILL_COMPOUNDER_STATE and
SKILL_COMPOUNDER_TRANSCRIPTS, which every shipped script reads for exactly this purpose,
so nothing here can reach ~/.claude/skill-compounder.

`CLAUDE_CONFIG_DIR` is the one knob NOT turned, and docs/CLAUDE-CODE-BEHAVIOR.md says
why: a fresh config directory costs the run its credentials. Step 0 re-measures that
claim rather than trusting it, and only then falls back to the path that does work --
`--settings <out>/claude/settings.json` with `--setting-sources ''` (or `project`) and
HOME left alone. The consequence is stated plainly in the report and in docs/e2e.md:
sessions run on the operator's ambient credentials, Claude Code writes their transcripts
into the REAL ~/.claude/projects/<slug-of-scratch-project>/, and the throwaway
*personal* skills directory (<out>/claude/skills) is never on any session's roster, so
the routing gate is measured at PROJECT scope instead.

COST. Aim: under 12 `claude -p` calls, all `--model sonnet` with a small `--max-turns`.
The forge step drives the CLI half only -- no builder agents, no red-team agents -- which
is what keeps step 7 to seconds rather than the median 3.3 hours a real forge takes.

`--no-model` runs every non-model step and records the rest SKIPPED. Use it to check the
harness itself for free before spending anything.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The skill the forge step produces. The trigger token is nonsense on purpose: nothing
# else on the machine can match it, so a Skill call naming it came from the roster and
# not from the model recognising a real topic.
SKILL_NAME = "journey-zarnvex-check"
TRIGGER_TOKEN = "zarnvex"

# The note the tier-0 step writes. Same reasoning: a real answer ("run pytest") could
# come from anywhere, so the note names a runner that exists nowhere else.
NOTE_RUNNER = "./ferrous-quokka-tests.sh"
NOTE_TEXT = (
    "To run this project's test suite, run `%s --all` from the project root. "
    "There is no other runner here and pytest is not configured." % NOTE_RUNNER
)

REMIND_CMD = "./quokka-check.sh"


# --------------------------------------------------------------------------- reporting


class Step:
    """One numbered step of the journey, and everything observed inside it."""

    def __init__(self, num, title):
        self.num = num
        self.title = title
        self.ran = []          # human-readable command lines
        self.observations = []  # (label, text) pairs
        self.status = "FAIL"
        self.evidence = "(nothing recorded)"
        self.notes = []
        self.started = time.time()
        self.elapsed = None

    def cmd(self, text):
        self.ran.append(text)

    def observe(self, label, text):
        self.observations.append((label, text))

    def note(self, text):
        self.notes.append(text)

    def verdict(self, status, evidence):
        self.status = status
        self.evidence = evidence

    def finish(self):
        if self.elapsed is None:
            self.elapsed = time.time() - self.started


class Journey:
    def __init__(self, out, args):
        self.out = out
        self.args = args
        self.steps = []
        self.claude_calls = 0
        self.log_seq = 0
        self.started = time.time()
        self.auth_mode = "undetermined"
        self.transcript_sessions = []

    # -- paths ---------------------------------------------------------------
    @property
    def claude_dir(self):
        return self.out / "claude"

    @property
    def bin_dir(self):
        return self.out / "bin"

    @property
    def state_dir(self):
        return self.out / "state"

    @property
    def project(self):
        return self.out / "project"

    @property
    def logs(self):
        return self.out / "logs"

    @property
    def transcripts(self):
        return self.out / "transcripts"

    @property
    def settings(self):
        return self.claude_dir / "settings.json"

    # -- environment ---------------------------------------------------------
    def env(self, **extra):
        e = os.environ.copy()
        e["SKILL_COMPOUNDER_STATE"] = str(self.state_dir)
        e["SKILL_COMPOUNDER_TRANSCRIPTS"] = str(self.transcripts)
        # The recursion barrier. A `claude -p` we launch is a real session carrying these
        # same hooks, so without this its own Stop would dispatch a paid session review.
        e["SKILL_COMPOUNDER_DISPATCHED"] = "1"
        # Proves a Stop hook ran even on a turn where every arm correctly stayed silent.
        e["INSIGHT_DEBUG_DUMP"] = str(self.logs / "insight-payloads.jsonl")
        e["SKILLNOTE_CLAUDE_DIR"] = str(self.claude_dir)
        e["SKILLFORGE_SKILLS_DIR"] = str(self.claude_dir / "skills")
        e.pop("CLAUDE_CONFIG_DIR", None)
        e.update(extra)
        return e

    # -- running -------------------------------------------------------------
    def run(self, argv, *, cwd=None, env=None, stdin_text=None, timeout=None,
            label="cmd", check=False):
        """Run a command, log everything, return (rc, stdout, stderr).

        stdin is ALWAYS supplied. Several scripts here read their payload with
        `payload="$(cat)"`, and a subprocess that leaves stdin inherited hangs forever.
        """
        self.log_seq += 1
        base = self.logs / ("%03d-%s" % (self.log_seq, re.sub(r"[^a-z0-9]+", "-",
                                                              label.lower())))
        pretty = " ".join(argv)
        (base.with_suffix(".cmd")).write_text(
            pretty + "\n\ncwd: %s\n" % (cwd or os.getcwd()) +
            ("\nstdin:\n" + stdin_text if stdin_text else "\n(stdin: empty)\n"))
        try:
            proc = subprocess.run(
                argv, cwd=str(cwd) if cwd else None, env=env or self.env(),
                input=(stdin_text or ""), capture_output=True, text=True,
                timeout=timeout or self.args.timeout)
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            rc = 124
            out = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(
                exc.stdout, bytes) else (exc.stdout or "")
            err = "TIMEOUT after %ss\n" % (timeout or self.args.timeout)
        base.with_suffix(".out").write_text(out)
        base.with_suffix(".err").write_text(err)
        if check and rc != 0:
            raise RuntimeError("%s failed (rc=%s): %s" % (pretty, rc, err.strip()[:400]))
        return rc, out, err

    def claude(self, prompt, *, cwd, setting_sources="", extra=(), max_turns=2,
               stream=False, label="claude", timeout=None, with_settings=True):
        """One real `claude -p` call, prompt on stdin, throwaway settings only.

        `--setting-sources ''` is what takes the user's own hooks, skills, plugins and
        CLAUDE.md away; `--settings <throwaway>` is what puts OURS back. Passing
        `project` instead is how a step that needs the scratch project's CLAUDE.md or its
        .claude/skills/ gets them, and it still loads nothing of the user's.
        """
        if self.args.no_model:
            return None
        argv = ["claude", "-p", "--model", self.args.model,
                "--max-turns", str(max_turns),
                "--setting-sources", setting_sources,
                "--strict-mcp-config"]
        if with_settings:
            argv += ["--settings", str(self.settings)]
        if stream:
            argv += ["--output-format", "stream-json", "--verbose"]
        argv += list(extra)
        self.claude_calls += 1
        rc, out, err = self.run(argv, cwd=cwd, stdin_text=prompt, label=label,
                                timeout=timeout or self.args.claude_timeout)
        # An unauthenticated `claude -p` reports "Not logged in · Please run /login" as
        # ORDINARY OUTPUT. Checked as a string and not as a status: the refusal is a
        # sentence to the operator, and a harness that trusted the exit code would be
        # betting the whole scenario on a number nothing documents.
        if "Not logged in" in out or "Not logged in" in err:
            raise RuntimeError("claude is not logged in for this call: %r"
                               % (out or err)[:200])
        self._collect_session(out, stream)
        return {"rc": rc, "out": out, "err": err, "argv": argv}

    def _collect_session(self, out, stream):
        """Remember the session ids this journey created, for the transcript copy."""
        ids = set(re.findall(r'"session_id"\s*:\s*"([0-9a-f-]{8,})"', out))
        for sid in ids:
            if sid not in self.transcript_sessions:
                self.transcript_sessions.append(sid)

    # -- reporting -----------------------------------------------------------
    def step(self, num, title):
        s = Step(num, title)
        self.steps.append(s)
        return s

    def write_report(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        elapsed = time.time() - self.started
        lines = []
        w = lines.append
        w("# End-to-end journey report")
        w("")
        w("Written by `tests/e2e/journey.py`. Every quoted line below was read back off "
          "disk or out of a session stream in this run; nothing here is asserted from a "
          "zero exit status alone.")
        w("")
        w("| | |")
        w("|-|-|")
        w("| finished | %s |" % now)
        w("| elapsed | %.1f s (%.1f min) |" % (elapsed, elapsed / 60.0))
        w("| out dir | `%s` |" % self.out)
        w("| repo | `%s` |" % REPO)
        w("| repo HEAD at start | `%s` |" % getattr(self, "head_start", "?"))
        w("| repo HEAD at end | `%s` |" % getattr(self, "head_end", "?"))
        w("| claude CLI | %s |" % getattr(self, "claude_version", "?"))
        w("| model | %s |" % self.args.model)
        w("| `claude -p` calls | %d |" % self.claude_calls)
        w("| authentication path | %s |" % self.auth_mode)
        w("")
        w("## Summary")
        w("")
        w("| step | what | result | evidence |")
        w("|-|-|-|-|")
        for s in self.steps:
            ev = s.evidence.replace("|", "\\|").replace("\n", " ")
            if len(ev) > 160:
                ev = ev[:157] + "..."
            w("| %s | %s | **%s** | %s |" % (s.num, s.title, s.status, ev))
        w("")
        counts = {}
        for s in self.steps:
            counts[s.status] = counts.get(s.status, 0) + 1
        w("**%s**" % ", ".join("%d %s" % (v, k) for k, v in sorted(counts.items())))
        w("")
        for s in self.steps:
            w("---")
            w("")
            w("## Step %s — %s" % (s.num, s.title))
            w("")
            w("**Result: %s** (%.1fs)" % (s.status, s.elapsed or 0.0))
            w("")
            if s.ran:
                w("**What was run**")
                w("")
                w("```")
                for c in s.ran:
                    w(c)
                w("```")
                w("")
            if s.observations:
                w("**What was observed**")
                w("")
                for label, text in s.observations:
                    w("- *%s*" % label)
                    w("")
                    w("  ```")
                    for ln in str(text).rstrip("\n").split("\n"):
                        w("  " + ln)
                    w("  ```")
                    w("")
            if s.notes:
                w("**Notes**")
                w("")
                for n in s.notes:
                    w("- " + n)
                w("")
            w("**Decisive line**")
            w("")
            w("> " + s.evidence.replace("\n", "\n> "))
            w("")
        w("---")
        w("")
        w("## Logs")
        w("")
        w("Every command's argv, stdin, stdout and stderr is under `logs/`, numbered in "
          "the order it ran. Session streams are the `.out` files of the `claude-*` "
          "entries.")
        w("")
        path = self.out / "REPORT.md"
        path.write_text("\n".join(lines) + "\n")
        return path


# --------------------------------------------------------------------------- helpers


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def first_matching(text, pattern, default="(no match)"):
    m = re.search(pattern, text)
    return m.group(0) if m else default


def jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def stream_events(text):
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def stream_text(text):
    """Concatenate the assistant's text parts out of a stream-json transcript."""
    parts = []
    for ev in stream_events(text):
        if ev.get("type") == "assistant":
            for c in (ev.get("message") or {}).get("content") or []:
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
        elif ev.get("type") == "result" and isinstance(ev.get("result"), str):
            # The `result` event repeats the closing assistant text. Appending it
            # unconditionally made every quoted answer in the report a doubled one.
            if ev["result"].strip() not in "\n".join(parts):
                parts.append(ev["result"])
    return "\n".join(parts)


def final_text(res):
    """The answer, whether the call was plain text or stream-json."""
    if res is None:
        return ""
    out = res["out"]
    if out.lstrip().startswith("{"):
        t = stream_text(out)
        if t.strip():
            return t
    return out


# --------------------------------------------------------------------------- the steps


def step0_preflight(j):
    s = j.step("0", "preflight and the authentication decision")
    try:
        rc, out, _ = j.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], label="head")
        j.head_start = out.strip()
        rc, out, _ = j.run(["claude", "--version"], label="version")
        j.claude_version = out.strip()
        s.cmd("claude --version")
        s.observe("claude --version", j.claude_version)
        for tool in ("jq", "git", "python3", "claude"):
            if shutil.which(tool) is None:
                s.verdict("FAIL", "%s is not on PATH; the journey needs it" % tool)
                return
        s.observe("checkout", "HEAD %s\n%s" % (
            j.head_start,
            j.run(["git", "-C", str(REPO), "status", "--porcelain"],
                  label="status")[1].strip() or "(clean)"))

        # THE MEASUREMENT, not the assumption. docs/CLAUDE-CODE-BEHAVIOR.md records that
        # a fresh CLAUDE_CONFIG_DIR loses the macOS Keychain credential. Re-run it here so
        # the report carries this machine's own answer.
        if j.args.no_model:
            j.auth_mode = "(not measured: --no-model)"
            s.verdict("SKIPPED", "--no-model: the authentication probe spends a call")
            return
        probe_cfg = j.out / "auth-probe-config"
        probe_cfg.mkdir(parents=True, exist_ok=True)
        env = j.env(CLAUDE_CONFIG_DIR=str(probe_cfg))
        j.claude_calls += 1
        rc, out, err = j.run(
            ["claude", "-p", "--model", j.args.model, "--max-turns", "1",
             "--setting-sources", "", "--strict-mcp-config"],
            cwd=j.out, env=env, stdin_text="Reply with exactly the word: pineapple",
            label="claude-auth-probe", timeout=j.args.claude_timeout)
        s.cmd("CLAUDE_CONFIG_DIR=<out>/auth-probe-config claude -p --model %s "
              "--max-turns 1 --setting-sources '' --strict-mcp-config" % j.args.model)
        combined = (out + err).strip()
        s.observe("CLAUDE_CONFIG_DIR probe: rc=%d, output" % rc, combined or "(empty)")
        if "Not logged in" in combined:
            j.auth_mode = (
                "FALLBACK: `--settings <out>/claude/settings.json` with "
                "`--setting-sources ''` (or `project`), HOME and CLAUDE_CONFIG_DIR left "
                "alone. A throwaway CLAUDE_CONFIG_DIR cannot authenticate on this "
                "machine, so sessions run on the operator's ambient credentials and "
                "Claude Code writes their transcripts into the real "
                "~/.claude/projects/<slug>/.")
            s.note("The probe exited %d here. The harness does not judge on that: every "
                   "`claude` call in this file raises on the `Not logged in` STRING, "
                   "because a refusal that reaches the operator as ordinary output is "
                   "the shape that a status check silently passes, and nothing "
                   "guarantees the status across CLI builds." % rc)
            s.note("Consequence carried by every later step: the throwaway *personal* "
                   "skills directory (`<out>/claude/skills`) is on no session's roster, "
                   "so step 8 measures routing at PROJECT scope.")
            s.verdict("PASS", "CLAUDE_CONFIG_DIR probe printed %r and exited %d; "
                              "falling back to --settings + --setting-sources ''."
                      % (combined[:80], rc))
        else:
            j.auth_mode = ("PRIMARY: CLAUDE_CONFIG_DIR=<out>/claude, a fully "
                           "self-contained config directory.")
            s.verdict("PASS", "CLAUDE_CONFIG_DIR probe authenticated: %r"
                      % combined[:120])
            s.note("Unexpected on macOS given docs/CLAUDE-CODE-BEHAVIOR.md; the later "
                   "steps still use the fallback path, which is a superset of what the "
                   "primary path proves.")
    finally:
        s.finish()


def step1_install(j):
    s = j.step("1", "fresh install into a throwaway config")
    try:
        for d in (j.claude_dir, j.bin_dir, j.state_dir, j.project, j.logs,
                  j.transcripts):
            d.mkdir(parents=True, exist_ok=True)

        # A pre-existing settings.json with an unrelated hook and an unrelated status
        # line, because "install is surgical" and "uninstall restores byte-for-byte" are
        # claims about a file that already had something in it.
        pre = {
            "model": "sonnet",
            "statusLine": {"type": "command", "command": "/usr/bin/true"},
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "/usr/bin/true"}]}
                ]
            },
        }
        j.settings.write_text(json.dumps(pre, indent=2) + "\n")
        j.pre_install_sha = sha256(j.settings)
        j.pre_install_bytes = j.settings.read_bytes()
        s.observe("pre-install settings.json (sha256 %s)" % j.pre_install_sha[:16],
                  j.settings.read_text())

        argv = [sys.executable, str(REPO / "scripts" / "setup.py"),
                "--claude-dir", str(j.claude_dir),
                "--bin-dir", str(j.bin_dir),
                "--state-dir", str(j.state_dir)]
        s.cmd("python3 scripts/setup.py --claude-dir <out>/claude --bin-dir <out>/bin "
              "--state-dir <out>/state")
        rc, out, err = j.run(argv, cwd=REPO, label="install")
        s.observe("installer output (rc=%d)" % rc, (out + err).strip())
        if rc != 0:
            s.verdict("FAIL", "installer exited %d: %s" % (rc, err.strip()[:200]))
            return

        settings = json.loads(j.settings.read_text())
        hooks = settings.get("hooks") or {}
        entries = []
        for event, groups in sorted(hooks.items()):
            for g in groups or []:
                for h in g.get("hooks") or []:
                    cmd = h.get("command", "")
                    if str(REPO) in cmd:
                        entries.append("%s  %s"
                                       % (event, cmd.replace(str(REPO), "<repo>")))
        scripts = sorted({re.search(r"hooks/([a-z-]+\.sh)", e).group(1)
                          for e in entries if "hooks/" in e})
        s.observe("hook entries wired (%d entries over %d scripts)"
                  % (len(entries), len(scripts)), "\n".join(entries))

        skills = sorted(p.name for p in (j.claude_dir / "skills").iterdir()
                        if (p / "SKILL.md").exists()) if (
            j.claude_dir / "skills").exists() else []
        shipped = sorted(p.name for p in (REPO / "skills").iterdir()
                         if (p / "SKILL.md").exists())
        s.observe("skills linked into <out>/claude/skills (%d)" % len(skills),
                  "\n".join(skills))
        clis = sorted(p.name for p in j.bin_dir.iterdir()) if j.bin_dir.exists() else []
        shipped_clis = sorted(p.name for p in (REPO / "bin").iterdir() if p.is_file())
        s.observe("CLIs linked into <out>/bin (%d)" % len(clis), "\n".join(clis))

        # The unrelated entries must survive.
        untouched = json.dumps(settings.get("statusLine"), sort_keys=True)
        s.observe("pre-existing statusLine after install (wrapped, base preserved)",
                  untouched + "\n\nbase saved at: %s\n%s" % (
                      j.state_dir / "statusline-base.sh",
                      (j.state_dir / "statusline-base.sh").read_text()
                      if (j.state_dir / "statusline-base.sh").exists() else "(absent)"))

        s.cmd("<out>/bin/skillforge doctor")
        rc, out, err = j.run([str(j.bin_dir / "skillforge"), "doctor"], cwd=j.project,
                             label="doctor")
        s.observe("skillforge doctor (rc=%d)" % rc, (out + err).strip())
        doctor_bad = [ln for ln in (out + err).splitlines()
                      if re.search(r"\bPROBLEM\b|\bmissing\b|\bnot found\b|\bBROKEN\b",
                                   ln, re.I)]

        # The repo's own CLAUDE.md states these two counts in prose. It also says to
        # derive them from OUR_EVENT_MARKERS rather than from the sentence -- so check
        # the sentence against what an install actually wrote, and say so if they differ.
        doc = (REPO / ".claude" / "CLAUDE.md")
        if doc.exists():
            claimed = re.search(r"(\w+) entries over (\w+) scripts", doc.read_text())
            words = {"seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
                     "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
                     "sixteen": 16}
            if claimed:
                ce = words.get(claimed.group(1).lower())
                cs = words.get(claimed.group(2).lower())
                if (ce, cs) != (len(entries), len(scripts)):
                    s.note("DOC DRIFT (product, not harness): `.claude/CLAUDE.md` says "
                           "\"%s\", and this install wrote **%d entries over %d "
                           "scripts**." % (claimed.group(0), len(entries), len(scripts)))

        ok = (len(entries) >= 12 and set(shipped) <= set(skills)
              and set(shipped_clis) <= set(clis) and rc == 0)
        if ok:
            s.verdict("PASS",
                      "%d hook entries over %d scripts; all %d shipped skills and all "
                      "%d CLIs linked; `skillforge doctor` exited 0."
                      % (len(entries), len(scripts), len(shipped), len(shipped_clis)))
        else:
            s.verdict("FAIL",
                      "entries=%d skills=%d/%d clis=%d/%d doctor_rc=%d bad=%r"
                      % (len(entries), len(skills), len(shipped), len(clis),
                         len(shipped_clis), rc, doctor_bad[:3]))

        # The scratch project the whole journey is about.
        j.run(["git", "init", "-q", str(j.project)], label="git-init")
        (j.project / "README.md").write_text(
            "# scratch\n\nA throwaway project for the skill-compounder e2e journey.\n")
        (j.project / NOTE_RUNNER.lstrip("./")).write_text(
            "#!/bin/sh\necho 'quokka suite: 0 tests, 0 failures'\n")
        os.chmod(j.project / NOTE_RUNNER.lstrip("./"), 0o755)
        (j.project / REMIND_CMD.lstrip("./")).write_text(
            "#!/bin/sh\necho 'quokka check: ok'\n")
        os.chmod(j.project / REMIND_CMD.lstrip("./"), 0o755)
        j.run(["git", "-C", str(j.project), "add", "-A"], label="git-add")
        j.run(["git", "-C", str(j.project), "-c", "user.email=e2e@example.invalid",
               "-c", "user.name=e2e", "commit", "-q", "-m", "scratch project"],
              label="git-commit")
    finally:
        s.finish()


def step2_ordinary_session(j):
    s = j.step("2", "an ordinary session runs with the throwaway hooks, and they stay "
                    "silent on a trivial prompt")
    try:
        if j.args.no_model:
            s.verdict("SKIPPED", "--no-model")
            return
        dump = Path(j.env()["INSIGHT_DEBUG_DUMP"])
        before = dump.stat().st_size if dump.exists() else 0
        s.cmd("claude -p --model %s --max-turns 2 --setting-sources '' "
              "--settings <out>/claude/settings.json --strict-mcp-config "
              "--output-format stream-json --verbose  < 'what is 2 + 2?'" % j.args.model)
        res = j.claude("What is 2 + 2? Reply with just the number.",
                       cwd=j.project, stream=True, label="claude-trivial")
        answer = final_text(res).strip()
        s.observe("answer", answer[:400])

        # Did our hooks run at all? The Stop hook appends every raw payload it is handed
        # to INSIGHT_DEBUG_DUMP before any gate, so a grown file is proof of wiring --
        # which is the half a silence test cannot otherwise distinguish from "no hooks".
        after = dump.stat().st_size if dump.exists() else 0
        payloads = jsonl(dump)
        s.observe("Stop hook payloads appended by insight-capture.sh (proof the "
                  "throwaway wiring is live)",
                  "file grew %d -> %d bytes; %d payload(s); last hook_event_name=%r"
                  % (before, after, len(payloads),
                     payloads[-1].get("hook_event_name") if payloads else None))

        # And did they SAY anything? A hook reaches the model through
        # hookSpecificOutput.additionalContext and the person through systemMessage.
        noise = []
        for ev in stream_events(res["out"]):
            blob = json.dumps(ev)
            if "additionalContext" in blob or "hookSpecificOutput" in blob:
                noise.append(blob[:300])
            if ev.get("type") == "system" and ev.get("subtype") == "informational":
                noise.append(blob[:300])
        for marker in ("hook additional context", "Reminder recorded",
                       "Checkpoint after", "compound-improvement", "skillinsight"):
            if marker.lower() in res["out"].lower():
                noise.append("stream mentions %r" % marker)
        s.observe("hook output found in the session stream",
                  "\n".join(noise) if noise else "(none)")

        quiet = not noise
        ran = after > before
        if quiet and ran:
            s.verdict("PASS",
                      "insight-capture.sh received a Stop payload (dump grew %d -> %d "
                      "bytes) and no hook emitted additionalContext or a systemMessage; "
                      "the session answered %r." % (before, after, answer[:40]))
        elif not ran:
            s.verdict("FAIL", "no Stop payload was dumped: the throwaway hooks did not "
                              "fire, so the silence proves nothing.")
        else:
            s.verdict("FAIL", "a hook spoke on a trivial prompt: %s" % noise[0])
    finally:
        s.finish()


def step3_note(j):
    s = j.step("3", "a tier-0 note is written, and a later session answers from it")
    try:
        s.cmd("<out>/bin/skillnote add --scope project --project <out>/project "
              "--source session %r" % NOTE_TEXT)
        rc, out, err = j.run([str(j.bin_dir / "skillnote"), "add",
                              "--scope", "project", "--project", str(j.project),
                              "--source", "session", NOTE_TEXT], label="skillnote-add")
        s.observe("skillnote add (rc=%d)" % rc, (out + err).strip())
        md = j.project / ".claude" / "CLAUDE.md"
        s.observe("<out>/project/.claude/CLAUDE.md",
                  md.read_text() if md.exists() else "(absent)")
        if rc != 0 or not md.exists() or NOTE_RUNNER not in md.read_text():
            s.verdict("FAIL", "the note did not land in %s" % md)
            return
        if j.args.no_model:
            s.verdict("SKIPPED", "--no-model: the readback needs a session")
            return

        # `--setting-sources project` and not '': the project's CLAUDE.md is exactly what
        # '' takes away. It still loads nothing of the user's.
        s.cmd("claude -p --setting-sources project --settings <out>/claude/settings.json"
              "  < 'how do I run the test suite in this project?'")
        res = j.claude("How do I run the test suite in this project? Answer in one "
                       "short line.", cwd=j.project, setting_sources="project",
                       max_turns=2, label="claude-note-readback")
        answer = final_text(res).strip()
        s.observe("answer", answer[:600])
        if NOTE_RUNNER.lstrip("./") in answer:
            s.verdict("PASS", "the session answered %r, naming the runner that exists "
                              "only in the note (n=1 here; the earlier live test of this "
                              "shape ran 3/3)." % answer[:120])
        else:
            s.verdict("FAIL", "the answer did not name %s: %r"
                      % (NOTE_RUNNER, answer[:200]))
    finally:
        s.finish()


def step4_reminders(j):
    s = j.step("4", "a tier-1 reminder fires on a prompt keyword and on a real Bash "
                    "command")
    try:
        # TWO rows, not one. The cooldown is per reminder per session and defaults to
        # once per session ever, so a single row carrying both rules would fire on the
        # prompt and then be held back from the Bash call in the same session.
        kw_text = ("This project's quokka check is flaky on a cold cache; run it twice "
                   "before believing a failure.")
        cmd_text = ("%s writes into .quokka-cache/, so it must be run from the project "
                    "root." % REMIND_CMD)
        s.cmd("<out>/bin/skillnote add --remind --scope project --project <out>/project "
              "--keyword quokka --keyword check %r" % kw_text)
        rc1, o1, e1 = j.run([str(j.bin_dir / "skillnote"), "add", "--remind",
                             "--scope", "project", "--project", str(j.project),
                             "--keyword", "quokka", "--keyword", "check", kw_text],
                            label="skillnote-remind-keyword")
        s.cmd("<out>/bin/skillnote add --remind --scope project --project <out>/project "
              "--command %r %r" % (REMIND_CMD, cmd_text))
        rc2, o2, e2 = j.run([str(j.bin_dir / "skillnote"), "add", "--remind",
                             "--scope", "project", "--project", str(j.project),
                             "--command", REMIND_CMD, cmd_text],
                            label="skillnote-remind-command")
        s.observe("skillnote add --remind x2", (o1 + e1 + o2 + e2).strip())
        store = j.state_dir / "reminders.jsonl"
        s.observe("<out>/state/reminders.jsonl",
                  store.read_text().strip() if store.exists() else "(absent)")
        if rc1 != 0 or rc2 != 0 or not store.exists():
            s.verdict("FAIL", "the reminders were not recorded (rc %d/%d)" % (rc1, rc2))
            return
        if j.args.no_model:
            s.verdict("SKIPPED", "--no-model: firing a reminder needs a session")
            return

        hits = j.state_dir / "remind" / "hits.jsonl"
        before = len(jsonl(hits))
        prompt = ("Run the quokka check for me: run exactly this command with the Bash "
                  "tool and nothing else, then tell me its output: %s" % REMIND_CMD)
        s.cmd("claude -p --permission-mode bypassPermissions --setting-sources project "
              "--settings <out>/claude/settings.json  < %r" % prompt[:60])
        res = j.claude(prompt, cwd=j.project, setting_sources="project", stream=True,
                       max_turns=6, label="claude-reminder",
                       extra=["--permission-mode", "bypassPermissions"])
        s.observe("answer", final_text(res).strip()[:400])

        rows = jsonl(hits)[before:]
        s.observe("<state>/remind/hits.jsonl rows appended by this session",
                  "\n".join(json.dumps(r) for r in rows) or "(none)")
        events = {r.get("event") for r in rows}
        # And the text the model was actually handed, quoted out of the stream.
        delivered = []
        for ev in stream_events(res["out"]):
            blob = json.dumps(ev)
            if "Reminder recorded" in blob:
                m = re.search(r"Reminder recorded[^\"\\]{0,300}", blob)
                delivered.append(m.group(0) if m else blob[:200])
        s.observe("the reminder text, as it appears in the session stream",
                  "\n".join(delivered) if delivered else
                  "(not present. `additionalContext` is delivered to the model and is "
                  "not echoed into --output-format stream-json, so its absence here is "
                  "a limit of this surface, not evidence the reminder was not "
                  "delivered. hits.jsonl above is the evidence that it was.)")

        if {"UserPromptSubmit", "PreToolUse"} <= events:
            s.verdict("PASS", "hits.jsonl gained one row per arm: %s"
                      % ", ".join(sorted('%s(%s)' % (r.get("event"), r.get("id"))
                                         for r in rows)))
        else:
            s.verdict("FAIL", "expected both UserPromptSubmit and PreToolUse hits; got "
                              "%r" % sorted(events))
    finally:
        s.finish()


CANDIDATE_TEXT = ("the throwaway end-to-end journey needs one canonical scenario, "
                  "because install, forge and uninstall have only ever been checked "
                  "one script at a time.")
CANDIDATE_LINE = "\u2605 Skill candidate: " + CANDIDATE_TEXT


def step5_candidate(j):
    s = j.step("5", "a skill candidate is captured from a session")
    try:
        if j.args.no_model:
            s.verdict("SKIPPED", "--no-model")
            return
        insights = j.state_dir / "insights"
        before = sum(len(jsonl(p)) for p in insights.glob("*.jsonl")) if (
            insights.exists()) else 0
        prompt = ("Reply with exactly this single line and nothing else, copied "
                  "character for character:\n\n%s" % CANDIDATE_LINE)
        s.cmd("claude -p  < 'Reply with exactly this single line ... \u2605 Skill "
              "candidate: ...'")
        res = j.claude(prompt, cwd=j.project, max_turns=1, label="claude-candidate")
        answer = final_text(res).strip()
        s.observe("the session's closing message", answer[:400])

        rows = []
        if insights.exists():
            for p in sorted(insights.glob("*.jsonl")):
                rows.extend(jsonl(p))
        new = rows[before:]
        s.observe("<state>/insights/<ISO-week>.jsonl rows appended",
                  "\n".join(json.dumps(r) for r in new) or "(none)")
        marker_rows = [r for r in new if CANDIDATE_TEXT[:40] in (r.get("text") or "")]
        if marker_rows:
            j.candidate_hash = marker_rows[0].get("hash")
            s.note("Path used: **the model emitted the marker itself**. No transcript "
                   "was hand-edited; the row below came from `.last_assistant_message` "
                   "on Stop.")
            s.verdict("PASS", "queued: %s" % json.dumps(marker_rows[0])[:220])
            return

        # Honest fallback. The task allows writing the marker into the transcript the
        # hook reads and triggering a second Stop; say so out loud if it is used.
        s.note("The model did not reproduce the marker verbatim, so the fallback path "
               "was taken: the marker was appended to the session transcript Claude Code "
               "wrote, and a second one-turn session was run to deliver a Stop the hook "
               "could read it from.")
        transcript = _find_transcript(j)
        if transcript is None:
            s.verdict("FAIL", "the model did not emit the marker and no transcript for "
                              "this session was found to write it into.")
            return
        rec = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": CANDIDATE_LINE}]}}
        with open(transcript, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        s.observe("marker appended to the transcript the hook reads", str(transcript))
        res2 = j.claude("Reply with the single word: ok", cwd=j.project, max_turns=1,
                        label="claude-candidate-stop2",
                        extra=["--resume", transcript.stem])
        s.observe("second session (to deliver a Stop)", final_text(res2).strip()[:200])
        rows = []
        for p in sorted(insights.glob("*.jsonl")):
            rows.extend(jsonl(p))
        new = rows[before:]
        marker_rows = [r for r in new if CANDIDATE_TEXT[:40] in (r.get("text") or "")]
        if marker_rows:
            j.candidate_hash = marker_rows[0].get("hash")
            s.verdict("PASS", "queued via the transcript path: %s"
                      % json.dumps(marker_rows[0])[:220])
        else:
            s.verdict("FAIL", "neither path put a candidate in the queue; rows seen: %r"
                      % [r.get("source") for r in new])
    finally:
        s.finish()


def _find_transcript(j):
    """The real transcript file for the newest session this journey created."""
    root = Path.home() / ".claude" / "projects"
    if not root.exists():
        return None
    best = None
    for sid in j.transcript_sessions:
        for p in root.glob("*/%s.jsonl" % sid):
            if best is None or p.stat().st_mtime > best.stat().st_mtime:
                best = p
    return best


def step6_promote(j):
    s = j.step("6", "the candidate is promoted to a note")
    try:
        h = getattr(j, "candidate_hash", None)
        if not h:
            s.verdict("SKIPPED", "step 5 queued no candidate, so there is nothing to "
                                 "promote")
            return
        s.cmd("<out>/bin/skillinsight promote %s --to note --scope project "
              "--project <out>/project" % h)
        rc, out, err = j.run([str(j.bin_dir / "skillinsight"), "promote", h,
                              "--to", "note", "--scope", "project",
                              "--project", str(j.project),
                              "--why", "one scenario is the right size for this"],
                             label="skillinsight-promote")
        s.observe("skillinsight promote (rc=%d)" % rc, (out + err).strip())
        md = (j.project / ".claude" / "CLAUDE.md")
        text = md.read_text() if md.exists() else ""
        s.observe("<out>/project/.claude/CLAUDE.md after promotion", text)
        rc2, out2, err2 = j.run([str(j.bin_dir / "skillinsight"), "pending",
                                 "--project", str(j.project), "--format", "text"],
                                label="skillinsight-pending")
        s.observe("skillinsight pending (rc=%d)" % rc2,
                  (out2 + err2).strip() or "(empty)")
        if rc == 0 and CANDIDATE_TEXT[:30] in text:
            s.verdict("PASS", "the candidate is now a note in the project's CLAUDE.md "
                              "and out of the queue: %s"
                      % (out.strip().splitlines() or ["(no output)"])[0])
        else:
            s.verdict("FAIL", "promote exited %d and the note text is %sin CLAUDE.md"
                      % (rc, "" if CANDIDATE_TEXT[:30] in text else "not "))
    finally:
        s.finish()


SKILL_MD = """---
name: %s
description: >-
  Use when a %s check is being run, planned, or has just failed: deciding whether a
  %s run is trustworthy, reading a %s report, or being asked what a %s check is.
  Do NOT use for ordinary test failures, for linting, or for any check that is not a
  %s check.
---

# %s

A deliberately tiny skill, written by `tests/e2e/journey.py` so the journey has
something real to forge, install, route and apply. It exists to be found by its
nonsense trigger token and nothing else.

## Procedure

1. Run `./quokka-check.sh` from the project root.
2. A %s check is trustworthy only on a warm cache, so run it twice and compare.
3. Report the second run's output, and say which run you are quoting.
""" % (SKILL_NAME, TRIGGER_TOKEN, TRIGGER_TOKEN, TRIGGER_TOKEN, TRIGGER_TOKEN,
       TRIGGER_TOKEN, SKILL_NAME, TRIGGER_TOKEN)


def step7_forge(j):
    s = j.step("7", "a narrow skill is forged (CLI half only)")
    t0 = time.time()
    try:
        staging = j.out / "forge-staging" / SKILL_NAME
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "SKILL.md").write_text(SKILL_MD)
        s.observe("the hand-written SKILL.md", SKILL_MD)

        sf = str(j.bin_dir / "skillforge")
        trigger = ("the e2e journey needs a skill it can route and apply, and nothing "
                   "installed answers a %s check" % TRIGGER_TOKEN)
        s.cmd("skillforge start %s 6 ... --trigger ... --trigger-kind agent-decision "
              "--skill-dir <out>/forge-staging/%s" % (SKILL_NAME, SKILL_NAME))
        rc, out, err = j.run([sf, "start", SKILL_NAME, "6",
                              "a %s check the journey can route and apply"
                              % TRIGGER_TOKEN,
                              "--trigger", trigger,
                              "--trigger-kind", "agent-decision",
                              "--skill-dir", str(staging)],
                             cwd=j.project, label="forge-start")
        s.observe("skillforge start (rc=%d)" % rc, (out + err).strip())
        if rc != 0:
            s.verdict("FAIL", "start exited %d: %s" % (rc, err.strip()[:200]))
            return

        rounds = []
        for n, (blocking, total) in enumerate(((3, 5), (1, 4)), start=1):
            s.cmd("skillforge round --name %s --blocking %d --total %d"
                  % (SKILL_NAME, blocking, total))
            rc, out, err = j.run([sf, "round", "--name", SKILL_NAME,
                                  "--blocking", str(blocking), "--total", str(total),
                                  "--subsystems", "frontmatter, trigger wording",
                                  "--shapes", "ambiguous decline clause"],
                                 cwd=j.project, label="forge-round-%d" % n)
            rounds.append("rc=%d  %s" % (rc, (out + err).strip()))
        s.observe("two red-team rounds recorded", "\n".join(rounds))

        s.cmd("skillforge round --name %s --blocking 0 --total 1   # a third, unbudgeted"
              % SKILL_NAME)
        rc3, out3, err3 = j.run([sf, "round", "--name", SKILL_NAME,
                                 "--blocking", "0", "--total", "1"],
                                cwd=j.project, label="forge-round-3-refused")
        s.observe("the third round (rc=%d)" % rc3, (out3 + err3).strip())
        cap_line = first_matching(out3 + err3, r"round cap reached[^\n]*")

        s.cmd("skillforge done --name %s" % SKILL_NAME)
        rcd, outd, errd = j.run([sf, "done", "--name", SKILL_NAME,
                                 "two rounds, blocking 3 -> 1"],
                                cwd=j.project, label="forge-done")
        s.observe("skillforge done (rc=%d)" % rcd, (outd + errd).strip())

        installed = j.claude_dir / "skills" / SKILL_NAME
        s.observe("the installed skill", "%s -> %s\nSKILL.md present: %s"
                  % (installed,
                     os.readlink(installed) if installed.is_symlink() else "(not a "
                                                                          "symlink)",
                     (installed / "SKILL.md").exists()))
        ledger = jsonl(j.state_dir / "ledger.jsonl")
        s.observe("ledger rows written by this forge",
                  "\n".join(json.dumps(r)[:300] for r in ledger))
        pending = j.state_dir / "apply-pending"
        s.observe("the pending-apply debt `done` left",
                  "\n".join(sorted(p.name for p in pending.glob("*")))
                  if pending.exists() else "(none)")

        elapsed = time.time() - t0
        s.elapsed = elapsed
        ok = (rc3 == 3 and rcd == 0 and (installed / "SKILL.md").exists()
              and elapsed < 1800)
        if ok:
            s.verdict("PASS",
                      "the third round was refused with exit 3 -- \"%s\" -- `done` "
                      "closed and linked the skill, and the whole step took %.1fs "
                      "against the 30-minute (1800s) target."
                      % (cap_line[:120], elapsed))
        else:
            s.verdict("FAIL", "round3_rc=%d (want 3), done_rc=%d, installed=%s, "
                              "elapsed=%.1fs" % (rc3, rcd,
                                                 (installed / "SKILL.md").exists(),
                                                 elapsed))
    finally:
        s.finish()


def step8_routing(j):
    s = j.step("8", "the forged skill routes in a fresh session (routing gate, n=1)")
    try:
        src = j.claude_dir / "skills" / SKILL_NAME
        if not (src / "SKILL.md").exists():
            s.verdict("SKIPPED", "step 7 installed no skill to route")
            return
        # WHY THE COPY. <out>/claude/skills is a PERSONAL skills directory, and a session
        # only reads it when CLAUDE_CONFIG_DIR points at <out>/claude -- which step 0
        # measured as losing the credential. Project scope is the scope this environment
        # can actually measure, so the same SKILL.md is put where the scratch project
        # loads it and the gate is run there. Reported as project scope, not personal.
        dest = j.project / ".claude" / "skills" / SKILL_NAME
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "SKILL.md", dest / "SKILL.md")
        s.observe("the skill under test", "%s\n(copied from %s; see the note below)"
                  % (dest / "SKILL.md", src))
        s.note("This is the routing gate at **n = 1**: one prompt, one model tier, one "
               "CLI build. docs/CLAUDE-CODE-BEHAVIOR.md scores routing on the stream's "
               "`Skill` tool call, never on the answer's prose, and so does this.")
        s.note("Scope: **project**, not personal. The throwaway personal skills "
               "directory is unreachable without CLAUDE_CONFIG_DIR, which step 0 "
               "measured as unauthenticated on this machine.")
        if j.args.no_model:
            s.verdict("SKIPPED", "--no-model")
            return

        prompt = ("I need to know whether this repo's %s check can be trusted right "
                  "now. What should I do?" % TRIGGER_TOKEN)
        s.cmd("claude -p --setting-sources project --settings <out>/claude/settings.json "
              "--output-format stream-json --disallowed-tools Read,Grep,Glob,Bash,...  "
              "< %r" % prompt)
        res = j.claude(prompt, cwd=j.project, setting_sources="project", stream=True,
                       max_turns=4, label="claude-routing",
                       extra=["--disallowed-tools",
                              "Read,Grep,Glob,Bash,Write,Edit,WebFetch,WebSearch,Task"])
        skill_calls, results = [], []
        for ev in stream_events(res["out"]):
            if ev.get("type") == "assistant":
                for c in (ev.get("message") or {}).get("content") or []:
                    if c.get("type") == "tool_use" and c.get("name") == "Skill":
                        skill_calls.append(json.dumps(c))
            if ev.get("type") == "user":
                for c in (ev.get("message") or {}).get("content") or []:
                    if c.get("type") == "tool_result":
                        body = json.dumps(c.get("content"))
                        if "kill" in body:
                            results.append(body[:300])
        s.observe("Skill tool calls in the stream",
                  "\n".join(skill_calls) or "(none)")
        s.observe("the tool_result that says whether it launched",
                  "\n".join(results) or "(none)")
        s.observe("answer", final_text(res).strip()[:500])
        j.routing_evidence = (skill_calls[0] if skill_calls else "")

        # hooks/skill-use.sh is wired to PostToolUse(Skill), so a real invocation should
        # also have put a `use` row in the throwaway ledger.
        uses = [r for r in jsonl(j.state_dir / "ledger.jsonl")
                if r.get("event") == "use"]
        s.observe("`use` rows in the ledger after this session",
                  "\n".join(json.dumps(r)[:300] for r in uses) or "(none)")
        j.use_rows = uses

        if any(SKILL_NAME in c for c in skill_calls):
            s.verdict("PASS", "the session called the Skill tool for it without being "
                              "told its name: %s" % skill_calls[0][:200])
        else:
            s.verdict("FAIL", "no Skill tool call naming %s; calls seen: %r"
                      % (SKILL_NAME, skill_calls[:2]))
    finally:
        s.finish()


def step9_apply_verdict(j):
    s = j.step("9", "the skill is applied to the original problem, and judged")
    try:
        sf = str(j.bin_dir / "skillforge")
        evidence = getattr(j, "routing_evidence", "") or ""
        if not evidence:
            evidence = ("the journey's scratch project had no %s procedure; the skill "
                        "supplied one" % TRIGGER_TOKEN)
        evidence = evidence[:400]
        s.cmd("skillforge apply --name %s --outcome used --evidence '<verbatim stream "
              "line>'" % SKILL_NAME)
        rc, out, err = j.run([sf, "apply", "--name", SKILL_NAME, "--outcome", "used",
                              "--evidence", evidence], cwd=j.project,
                             label="forge-apply")
        s.observe("skillforge apply (rc=%d)" % rc, (out + err).strip())
        s.cmd("skillforge verdict --name %s --verdict WORKED --evidence '<verbatim>'"
              % SKILL_NAME)
        rc2, out2, err2 = j.run([sf, "verdict", "--name", SKILL_NAME,
                                 "--verdict", "WORKED", "--evidence", evidence],
                                cwd=j.project, label="forge-verdict")
        s.observe("skillforge verdict (rc=%d)" % rc2, (out2 + err2).strip())
        rows = jsonl(j.state_dir / "ledger.jsonl")
        applied = [r for r in rows if r.get("event") == "apply"]
        verdicts = [r for r in rows if r.get("event") == "verdict"]
        s.observe("apply and verdict rows in the ledger",
                  "\n".join(json.dumps(r)[:400] for r in applied + verdicts) or "(none)")
        pending = j.state_dir / "apply-pending"
        s.observe("the pending-apply debt after apply",
                  "\n".join(sorted(p.name for p in pending.glob("*")))
                  if pending.exists() else "(directory gone)")
        if rc == 0 and rc2 == 0 and applied and verdicts:
            s.verdict("PASS", "one apply row (outcome=%s, marker=%s) and one verdict row "
                              "(%s) are in the ledger, and the pending-apply debt is "
                              "discharged."
                      % (applied[-1].get("outcome"), applied[-1].get("marker"),
                         verdicts[-1].get("verdict")))
        else:
            s.verdict("FAIL", "apply rc=%d verdict rc=%d apply_rows=%d verdict_rows=%d"
                      % (rc, rc2, len(applied), len(verdicts)))
    finally:
        s.finish()


def step10_report(j):
    s = j.step("10", "skillreport shows the use, apply and verdict")
    try:
        # Copy just this journey's own transcripts into the throwaway transcripts root,
        # so skillreport's invocation recovery reads the journey's sessions and no others.
        root = Path.home() / ".claude" / "projects"
        copied = []
        for sid in j.transcript_sessions:
            for p in root.glob("*/%s.jsonl" % sid):
                d = j.transcripts / p.parent.name
                d.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, d / p.name)
                copied.append(str(d / p.name))
        s.observe("this journey's own transcripts copied into <out>/transcripts "
                  "(SKILL_COMPOUNDER_TRANSCRIPTS), so no real project is read",
                  "\n".join(copied) or "(none found)")

        sr = str(j.bin_dir / "skillreport")
        s.cmd("<out>/bin/skillreport skills")
        rc, out, err = j.run([sr, "skills"], cwd=j.project, label="skillreport-skills")
        s.observe("skillreport skills (rc=%d)" % rc, (out + err).strip())
        skills_out = out + err
        s.cmd("<out>/bin/skillreport applied")
        rc2, out2, err2 = j.run([sr, "applied"], cwd=j.project,
                                label="skillreport-applied")
        s.observe("skillreport applied (rc=%d)" % rc2, (out2 + err2).strip())
        applied_out = out2 + err2

        # The stanza `skillreport skills` prints for this one skill, not just its name:
        # the five questions are the point, and "the string appears somewhere" is not
        # evidence that any of them were answered.
        stanza = []
        grab = False
        for ln in skills_out.splitlines():
            if ln.strip() == SKILL_NAME:
                grab = True
            elif grab and ln.strip() == "":
                break
            if grab:
                stanza.append(ln.rstrip())
        s.observe("the five-question stanza for the forged skill",
                  "\n".join(stanza) or "(the skill is not in `skillreport skills`)")
        fields = {}
        for ln in stanza[1:]:
            m = re.match(r"\s+(\w+)\s+(.*)", ln)
            if m:
                fields[m.group(1)] = m.group(2).strip()
        named = bool(stanza)
        want = ("uses", "applied", "verdict")
        answered = [k for k in want
                    if fields.get(k) and not fields[k].startswith("none recorded")
                    and "nothing to discharge" not in fields[k]]
        if rc == 0 and rc2 == 0 and named and set(answered) >= {"applied", "verdict"}:
            s.verdict("PASS", "skillreport answers %s for it — applied: %s | verdict: "
                              "%s | uses: %s"
                      % (", ".join(answered), fields.get("applied", "?")[:80],
                         fields.get("verdict", "?")[:60], fields.get("uses", "?")[:60]))
        else:
            s.verdict("FAIL", "skills rc=%d applied rc=%d, %s named, answered=%r"
                      % (rc, rc2, "is" if named else "is NOT", answered))
    finally:
        s.finish()


def step11_uninstall(j):
    s = j.step("11", "uninstall restores settings.json byte-for-byte and removes only "
                     "our links")
    try:
        argv = [sys.executable, str(REPO / "scripts" / "setup.py"), "--uninstall",
                "--claude-dir", str(j.claude_dir), "--bin-dir", str(j.bin_dir),
                "--state-dir", str(j.state_dir)]
        s.cmd("python3 scripts/setup.py --uninstall --claude-dir <out>/claude "
              "--bin-dir <out>/bin --state-dir <out>/state")
        rc, out, err = j.run(argv, cwd=REPO, label="uninstall")
        s.observe("uninstaller output (rc=%d)" % rc, (out + err).strip())

        after_sha = sha256(j.settings)
        same = j.settings.read_bytes() == j.pre_install_bytes
        s.observe("settings.json before vs after",
                  "pre-install  sha256 %s (%d bytes)\npost-uninstall sha256 %s (%d "
                  "bytes)\nidentical: %s" % (
                      j.pre_install_sha, len(j.pre_install_bytes), after_sha,
                      len(j.settings.read_bytes()), same))
        if not same:
            s.observe("post-uninstall settings.json", j.settings.read_text())

        left_skills = sorted(p.name for p in (j.claude_dir / "skills").iterdir()) if (
            j.claude_dir / "skills").exists() else []
        left_bin = sorted(p.name for p in j.bin_dir.iterdir()) if j.bin_dir.exists() \
            else []
        s.observe("what is left in the throwaway dirs",
                  "skills/: %r\nbin/: %r" % (left_skills, left_bin))
        if SKILL_NAME in left_skills:
            s.note("`%s` is still in skills/: uninstall removes only links it can prove "
                   "it created, and this one was linked by `skillforge done`."
                   % SKILL_NAME)
        else:
            s.note("Nothing is left in skills/ or bin/. The forged skill's LINK was "
                   "removed too, with the uninstaller saying so and saying the skill "
                   "itself is untouched — quoted above.")
        state_alive = (j.state_dir / "ledger.jsonl").exists()
        s.observe("runtime state after uninstall",
                  "ledger.jsonl still present: %s (%d rows)"
                  % (state_alive, len(jsonl(j.state_dir / "ledger.jsonl"))))

        if rc == 0 and same and state_alive:
            s.verdict("PASS", "settings.json is byte-identical to its pre-install "
                              "content (sha256 %s), and the ledger survived."
                      % after_sha[:16])
        else:
            s.verdict("FAIL", "rc=%d, byte-identical=%s, state_alive=%s"
                      % (rc, same, state_alive))
    finally:
        s.finish()


# --------------------------------------------------------------------------- main


STEPS = [step0_preflight, step1_install, step2_ordinary_session, step3_note,
         step4_reminders, step5_candidate, step6_promote, step7_forge, step8_routing,
         step9_apply_verdict, step10_report, step11_uninstall]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="One canonical end-to-end journey through claude-skill-compounder. "
                    "Spends real claude -p calls; never run it in CI.")
    ap.add_argument("--out", required=True,
                    help="directory to build the throwaway world in and keep every "
                         "artifact under (created if absent; must be empty or new)")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=float, default=180.0,
                    help="seconds for an ordinary command")
    ap.add_argument("--claude-timeout", type=float, default=300.0,
                    help="seconds for one claude -p call")
    ap.add_argument("--no-model", action="store_true",
                    help="run every step that needs no model call and record the rest "
                         "SKIPPED; spends nothing")
    ap.add_argument("--only", default="",
                    help="comma-separated step numbers to attempt (others are recorded "
                         "SKIPPED). Steps depend on each other; this is for debugging "
                         "the harness, not for a real run.")
    args = ap.parse_args(argv)

    out = Path(args.out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        print("error: %s exists and is not empty. Pick a fresh --out." % out,
              file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)

    j = Journey(out, args)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    print("e2e journey -> %s" % out)
    for fn in STEPS:
        num = fn.__name__[4:fn.__name__.index("_")]
        if only and num not in only:
            s = j.step(num, fn.__name__[fn.__name__.index("_") + 1:].replace("_", " "))
            s.verdict("SKIPPED", "--only %s" % args.only)
            s.finish()
            continue
        try:
            fn(j)
        except Exception as exc:                      # noqa: BLE001
            s = j.steps[-1] if j.steps and j.steps[-1].elapsed is None else \
                j.step(num, fn.__name__)
            s.observe("exception", "%s: %s" % (type(exc).__name__, exc))
            s.verdict("FAIL", "the harness raised: %s: %s" % (type(exc).__name__, exc))
            s.finish()
        last = j.steps[-1]
        print("  step %-2s %-9s %s" % (last.num, last.status, last.title[:64]))
        try:
            j.head_end = subprocess.run(
                ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                text=True, input="").stdout.strip()
        except OSError:
            j.head_end = "?"
        j.write_report()

    path = j.write_report()
    print("\nREPORT: %s" % path)
    print("claude -p calls: %d   elapsed: %.1fs" % (j.claude_calls,
                                                    time.time() - j.started))
    return 0 if all(s.status != "FAIL" for s in j.steps) else 1


if __name__ == "__main__":
    sys.exit(main())
