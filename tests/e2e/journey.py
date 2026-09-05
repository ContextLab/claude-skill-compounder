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
    <out>/bin       a throwaway bin dir for the six CLIs, and `surfer`
    <out>/state     a throwaway state root (ledger, insights, reminders, forges)
    <out>/project   a scratch git project, the "problem" the journey is about
    <out>/logs      every command's argv, stdout, stderr, and every claude stream

The state root and the transcripts root are redirected with SKILL_COMPOUNDER_STATE and
SKILL_COMPOUNDER_TRANSCRIPTS, which every shipped script reads for exactly this purpose,
so nothing here can reach ~/.claude/skill-compounder.

`CLAUDE_CONFIG_DIR` is the knob with TWO settings, and `--config-dir` picks between
them.

`--config-dir ambient` (the DEFAULT) leaves `HOME` and `CLAUDE_CONFIG_DIR` alone and
swaps the configuration for one call at a time: `--settings <out>/claude/settings.json`
with `--setting-sources ''` (or `project`). A throwaway config directory holds no login,
and docs/CLAUDE-CODE-BEHAVIOR.md records why: on macOS the subscription credential lives
in the Keychain and is reached through the ambient environment. Step 0 re-measures that
rather than trusting it. Three consequences follow, all stated in the report: sessions
run on the operator's ambient credentials, Claude Code writes their transcripts into the
REAL ~/.claude/projects/<slug-of-scratch-project>/, and the throwaway *personal* skills
directory (<out>/claude/skills) is on no session's roster, so the routing gate is
measured at PROJECT scope instead.

`--config-dir fresh` is the isolation issue #42 asks for, and it needs a credential
handed in through the environment rather than borrowed from the Keychain.
`CLAUDE_CODE_OAUTH_TOKEN` (minted by `claude setup-token`) or `ANTHROPIC_API_KEY` must be
set; the harness refuses to start without one and never logs its value. Then
`CLAUDE_CONFIG_DIR` points at <out>/claude for every process, and NO `--settings` and no
`--setting-sources` flag is passed at all: the throwaway config IS the config. Both
variables were measured to be consulted under a fresh config directory on CLI 2.1.260 --
an invalid `CLAUDE_CODE_OAUTH_TOKEN` answered `Failed to authenticate. API Error: 401
Invalid bearer token` and an invalid `ANTHROPIC_API_KEY` answered `Invalid API key · Fix
external API key`, where no credential at all answers `Not logged in · Please run
/login`. Which of the three consequences the mode removes, and the fact that NO run with
a real token has been made yet, is in docs/e2e.md.

`--check-auth` spends ONE call answering whether the chosen mode can authenticate, and
exits. The journey is thirteen calls; twelve of them are wasted discovering a stale token
at step 2.

COST. Aim: under 15 `claude -p` calls, all `--model sonnet` with a small `--max-turns`.
The forge step drives the CLI half only -- no builder agents, no red-team agents -- which
is what keeps step 7 to seconds rather than the median 3.3 hours a real forge takes.

THE STEPS RUN IN THE ORDER OF `STEPS`, NOT IN NUMBER ORDER. 12-16 (the mission and the
lesson) were added after 11 (uninstall) was numbered, and uninstall has to be last, so
the run order is 0-10, 12-16, 11. See the comment on `STEPS`.

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
import tempfile
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

# The two environment variables a fresh CLAUDE_CONFIG_DIR was MEASURED to consult on CLI
# 2.1.260 (2026-09-04), in the order this harness prefers them: `claude setup-token`
# mints the first against the operator's subscription, and the second is an API key that
# bills separately. The NAME is reported; the VALUE is never printed, logged or written
# into the report.
TOKEN_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")

# The probe prompt, and the refusals judged as STRINGS rather than as exit statuses.
# Measured on 2.1.260, 2026-09-04: all three refusals below print their sentence on
# STDOUT with an empty stderr and exit **1**, so the status says only that something went
# wrong and cannot tell "no credential" from "the credential was rejected" -- which is
# the distinction fresh mode is made of. The string is what separates them.
AUTH_PROBE_PROMPT = "Reply with exactly the word: pineapple"
AUTH_REFUSALS = ("Not logged in", "Please run /login", "Invalid API key",
                 "Failed to authenticate", "Fix external API key")


def credential_name():
    """The NAME of the credential variable present in the environment, or None.

    Never returns, prints or logs the value. A journey report is an artifact an
    operator pastes into an issue.
    """
    for name in TOKEN_VARS:
        if os.environ.get(name, "").strip():
            return name
    return None


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
        # "ambient" (the default: HOME and CLAUDE_CONFIG_DIR left alone, configuration
        # swapped per call with --settings) or "fresh" (CLAUDE_CONFIG_DIR points INTO
        # <out> and a credential is handed in through the environment). See the module
        # docstring and docs/e2e.md.
        self.config_mode = getattr(args, "config_dir", "ambient")
        # Set to a reason string to record every REMAINING step SKIPPED. The only thing
        # that sets it is step 0 failing its authentication probe in fresh mode: twelve
        # further calls cannot answer a question a bad token already answered.
        self.abort = None

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

    @property
    def projects_root(self):
        """Where Claude Code writes this run's session transcripts.

        It follows CLAUDE_CONFIG_DIR, which is the whole point of the fresh mode: in
        ambient mode the transcripts land in the operator's REAL ~/.claude/projects/,
        which is consequence 2 in docs/e2e.md and the one place outside <out> that mode
        leaves anything.
        """
        if self.config_mode == "fresh":
            return self.claude_dir / "projects"
        return Path.home() / ".claude" / "projects"

    @property
    def surfer_store(self):
        """history-surfer's data directory, redirected INTO <out>.

        ONE variable moves BOTH ends. `hooks/mission.sh` reads the user's own prompts out
        of history-surfer's store and keeps no copy of them, and it derives the store the
        way history-surfer does: `MISSION_SURFER_ROOT`, then `CLAUDE_HISTORY_SURFER_DIR`,
        then `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer`. So setting
        history-surfer's own override sends the writer and the reader to the same place,
        and this run cannot reach the operator's real `~/.claude/history-surfer`.

        It took two until 2026-09-03: the hook's root was the literal
        `$HOME/.claude/history-surfer`, so `MISSION_SURFER_ROOT` had to be set here as
        well or every mission step measured a gap rather than the hook. That was a
        product defect, and this journey is what found it.
        """
        return self.out / "surfer-store"

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
        # Both ends of the mission's one source of truth, pointed inside <out> by the ONE
        # variable history-surfer itself reads. Nothing this run does can reach the
        # operator's real ~/.claude/history-surfer, and mission.sh's rung 2 is what makes
        # the reader follow the writer without a second variable.
        e["CLAUDE_HISTORY_SURFER_DIR"] = str(self.surfer_store)
        if self.config_mode == "fresh":
            # The isolation of issue #42. Every process this journey starts -- the
            # installer, the CLIs, the hooks a session fires and the session itself --
            # reads the throwaway config directory and nothing of the operator's. The
            # credential arrives in the environment instead (see credential_name()), so
            # os.environ.copy() above already carries it and nothing here prints it.
            e["CLAUDE_CONFIG_DIR"] = str(self.claude_dir)
        else:
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
               stream=False, label="claude", timeout=None, with_settings=True,
               env=None):
        """One real `claude -p` call, prompt on stdin, throwaway settings only.

        AMBIENT MODE. `--setting-sources ''` is what takes the user's own hooks, skills,
        plugins and CLAUDE.md away; `--settings <throwaway>` is what puts OURS back.
        Passing `project` instead is how a step that needs the scratch project's
        CLAUDE.md or its .claude/skills/ gets them, and it still loads nothing of the
        user's.

        FRESH MODE. Neither flag is passed. CLAUDE_CONFIG_DIR (set by env()) already
        points at the throwaway config, so the default sources -- user, project, local --
        ARE the throwaway ones, and `--settings` pointed at the same file it is already
        reading would only be a second copy to keep in step. `setting_sources` and
        `with_settings` are therefore ignored here, deliberately: a step that asks for
        `project` gets project settings either way.
        """
        if self.args.no_model:
            return None
        argv = ["claude", "-p", "--model", self.args.model,
                "--max-turns", str(max_turns), "--strict-mcp-config"]
        if self.config_mode != "fresh":
            argv += ["--setting-sources", setting_sources]
            if with_settings:
                argv += ["--settings", str(self.settings)]
        if stream:
            argv += ["--output-format", "stream-json", "--verbose"]
        argv += list(extra)
        self.claude_calls += 1
        rc, out, err = self.run(argv, cwd=cwd, stdin_text=prompt, label=label,
                                env=env, timeout=timeout or self.args.claude_timeout)
        # An unauthenticated `claude -p` reports "Not logged in · Please run /login" on
        # STDOUT, as ORDINARY OUTPUT, and every refusal shape exits 1 alike (2.1.260).
        # Checked as a string and not as a status: the refusal is a sentence to the
        # operator, and the status cannot say which refusal it was. Every string in
        # AUTH_REFUSALS, not just that one, because fresh mode meets the other shapes --
        # a rejected token answers "Failed to authenticate." and a rejected key
        # "Invalid API key".
        for marker in AUTH_REFUSALS:
            if marker in out or marker in err:
                raise RuntimeError("claude refused this call on authentication (%s): %r"
                                   % (marker, (out or err)[:200]))
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
        w("| `--config-dir` mode | %s |" % self.config_mode)
        w("| credential variable | %s |" % (credential_name() or
                                            "(none in the environment)"))
        w("")
        if self.config_mode == "fresh":
            w("**Fresh-config mode.** `CLAUDE_CONFIG_DIR` pointed at `<out>/claude` for "
              "every process, and no `--settings` and no `--setting-sources` flag was "
              "passed to any session. Where a step's *What was run* line below still "
              "names those flags it is quoting the default mode's shape; every "
              "command's real argv is in `logs/*.cmd`. %s"
              % ("The credential came from the environment variable named above and "
                 "appears nowhere in this report." if credential_name() else
                 "No credential was in the environment, so nothing that needed one "
                 "could run."))
            w("")
        w("## Summary")
        w("")
        w("Steps are listed in the order they RAN, which is not number order: 12-16 were "
          "added after 11 was numbered, and 11 tears the install down, so it runs last.")
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


def auth_probe(j, config_dir=None, *, label="claude-auth-probe"):
    """One real `claude -p`, answering only "can this configuration authenticate?".

    Returns `(ok, answer, rc)`. `config_dir` is the CLAUDE_CONFIG_DIR the probe runs
    under; None means "whatever env() gives this mode", which in ambient mode is the
    operator's own.

    `ok` is judged on the STRINGS in AUTH_REFUSALS and never on the exit status, because
    the status does not separate the cases. Measured on CLI 2.1.260, 2026-09-04, under a
    fresh `CLAUDE_CONFIG_DIR`, each on stdout with an empty stderr and each exiting 1:
    no credential answered `Not logged in · Please run /login`;
    `CLAUDE_CODE_OAUTH_TOKEN=invalid-for-probe` answered `Failed to authenticate. API
    Error: 401 Invalid bearer token`; `ANTHROPIC_API_KEY=invalid-for-probe` answered
    `Invalid API key · Fix external API key`. One status, three different facts, and the
    two that matter here -- "hand a token in" versus "that token is bad" -- are
    indistinguishable by it.
    """
    if config_dir is not None:
        Path(config_dir).mkdir(parents=True, exist_ok=True)
        env = j.env(CLAUDE_CONFIG_DIR=str(config_dir))
    else:
        env = j.env()
    j.claude_calls += 1
    rc, out, err = j.run(
        ["claude", "-p", "--model", j.args.model, "--max-turns", "1",
         "--setting-sources", "", "--strict-mcp-config"],
        cwd=j.out, env=env, stdin_text=AUTH_PROBE_PROMPT, label=label,
        timeout=j.args.claude_timeout)
    answer = (out + err).strip()
    ok = not any(m in answer for m in AUTH_REFUSALS)
    return ok, answer, rc


def check_auth_only(j):
    """`--check-auth`: spend ONE call on the question, print the CLI's own answer, stop.

    The full journey is thirteen calls. Twelve of them are spent before anything would
    reveal a stale token, and a run that dies at step 2 has still spent step 0's call and
    built a report full of FAILs that all say the same thing. This is that one call, on
    its own, in whichever mode was asked for.
    """
    if j.args.no_model:
        print("error: --check-auth needs one real call and --no-model spends none.",
              file=sys.stderr)
        return 2
    # Each mode is probed the way it will actually run: fresh mode under a throwaway
    # CLAUDE_CONFIG_DIR carrying only what the environment hands it, ambient mode under
    # the operator's own configuration, which is what its sessions use.
    probe_cfg = (j.out / "auth-probe-config") if j.config_mode == "fresh" else None
    ok, answer, rc = auth_probe(j, probe_cfg, label="claude-check-auth")
    print("--config-dir       : %s" % j.config_mode)
    print("CLAUDE_CONFIG_DIR  : %s" % (("%s (throwaway, created for this probe)"
                                       % probe_cfg) if probe_cfg
                                      else "(the operator's own, as ambient mode runs)"))
    print("credential variable: %s" % (credential_name() or "(none in the environment)"))
    print("exit status        : %d" % rc)
    print("the CLI answered   : %s" % (answer or "(empty)"))
    if ok:
        print("OK: this configuration authenticates. The journey can spend its calls.")
        return 0
    if j.config_mode == "fresh":
        print("STOP: a throwaway CLAUDE_CONFIG_DIR cannot authenticate with what is in "
              "this environment. Run `claude setup-token` and export the result as "
              "CLAUDE_CODE_OAUTH_TOKEN.", file=sys.stderr)
    else:
        print("STOP: --config-dir ambient runs on the operator's own configuration and "
              "it just refused, so the journey would fail at its first session. Log in "
              "with `claude` or run `claude setup-token`.", file=sys.stderr)
    return 3


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
            s.observe("--config-dir", j.config_mode)
            s.verdict("SKIPPED", "--no-model: the authentication probe spends a call")
            return
        probe_cfg = j.out / "auth-probe-config"
        ok, combined, rc = auth_probe(j, probe_cfg)
        s.cmd("CLAUDE_CONFIG_DIR=<out>/auth-probe-config claude -p --model %s "
              "--max-turns 1 --setting-sources '' --strict-mcp-config" % j.args.model)
        s.observe("CLAUDE_CONFIG_DIR probe: rc=%d, output" % rc, combined or "(empty)")
        s.observe("--config-dir mode, and the credential it was given",
                  "%s\ncredential variable: %s (the value is never read into this "
                  "report)" % (j.config_mode,
                               credential_name() or "(none in the environment)"))

        if j.config_mode == "fresh":
            # THE ISOLATION OF ISSUE #42. The probe just ran the way every later session
            # will: a config directory with no stored login, authenticating on what the
            # environment handed it. If that failed there is nothing to fall back to --
            # falling back would silently restore the ambient identity the mode exists to
            # remove -- so the run stops here rather than spending twelve more calls.
            if ok:
                j.auth_mode = (
                    "PRIMARY: CLAUDE_CONFIG_DIR=<out>/claude, a self-contained config "
                    "directory authenticating on %s from the environment. No "
                    "--settings and no --setting-sources is passed to any session."
                    % (credential_name() or "an unnamed credential"))
                s.note("Consequences 1-3 of docs/e2e.md are the ones this mode is "
                       "designed to remove: sessions carry no borrowed identity, "
                       "transcripts land in <out>/claude/projects/, and the throwaway "
                       "PERSONAL skills directory is on the roster, so step 8 measures "
                       "routing at personal scope.")
                s.verdict("PASS", "a fresh CLAUDE_CONFIG_DIR authenticated on %s: %r"
                          % (credential_name(), combined[:120]))
            else:
                j.auth_mode = ("FAILED: --config-dir fresh, and the fresh directory "
                               "could not authenticate.")
                j.abort = ("step 0: --config-dir fresh could not authenticate (%r), so "
                           "every later step would spend a call to be told the same "
                           "thing. Run `claude setup-token` and export "
                           "CLAUDE_CODE_OAUTH_TOKEN." % combined[:120])
                s.note("No fallback is taken. `--settings` with the ambient credential "
                       "is the OTHER mode, and taking it here would quietly restore the "
                       "identity this one exists to remove.")
                s.verdict("FAIL", "a fresh CLAUDE_CONFIG_DIR printed %r and exited %d "
                                  "with credential variable %s; the run stops."
                          % (combined[:120], rc,
                             credential_name() or "(none in the environment)"))
            return

        if not ok:
            j.auth_mode = (
                "FALLBACK: `--settings <out>/claude/settings.json` with "
                "`--setting-sources ''` (or `project`), HOME and CLAUDE_CONFIG_DIR left "
                "alone. A throwaway CLAUDE_CONFIG_DIR cannot authenticate on this "
                "machine, so sessions run on the operator's ambient credentials and "
                "Claude Code writes their transcripts into the real "
                "~/.claude/projects/<slug>/.")
            s.note("The probe exited %d here. The harness does not judge on that: "
                   "every `claude` call in this file raises on the AUTH_REFUSALS "
                   "STRINGS instead. On 2.1.260, measured 2026-09-04, no credential, a "
                   "rejected OAuth token and a rejected API key all print their own "
                   "sentence on stdout and all exit 1, so the status cannot say which "
                   "of the three happened -- and nothing guarantees it across CLI "
                   "builds either." % rc)
            s.note("Consequence carried by every later step: the throwaway *personal* "
                   "skills directory (`<out>/claude/skills`) is on no session's roster, "
                   "so step 8 measures routing at PROJECT scope.")
            s.verdict("PASS", "CLAUDE_CONFIG_DIR probe printed %r and exited %d; "
                              "falling back to --settings + --setting-sources ''."
                      % (combined[:80], rc))
        else:
            j.auth_mode = ("FALLBACK NOT NEEDED: a throwaway CLAUDE_CONFIG_DIR "
                           "authenticated here, but --config-dir ambient was asked for "
                           "and the later steps still take the --settings path.")
            s.verdict("PASS", "CLAUDE_CONFIG_DIR probe authenticated: %r"
                      % combined[:120])
            s.note("A fresh config directory authenticating means a credential is in "
                   "this environment (%s). `--config-dir fresh` is the mode that USES "
                   "it; this run does not, and the fallback path proves a superset of "
                   "what it would."
                   % (credential_name() or "not through one of the two variables "
                                           "this harness knows"))
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
        s.cmd("CLAUDE_HISTORY_SURFER_DIR=<out>/surfer-store "
              "python3 scripts/setup.py --claude-dir <out>/claude --bin-dir <out>/bin "
              "--state-dir <out>/state")
        rc, out, err = j.run(argv, cwd=REPO, label="install", env=j.env())
        s.observe("installer output (rc=%d)" % rc, (out + err).strip())
        if rc != 0:
            s.verdict("FAIL", "installer exited %d: %s" % (rc, err.strip()[:200]))
            return

        # history-surfer is a DEPENDENCY as of wave 1: hooks/mission.sh reads the user's
        # own prompts out of its store and keeps no copy, so without it the mission hook
        # is inert. Steps 12-14 are the ones that fail if this did not happen; record
        # here what the installer said and whether the capture hook actually landed.
        j.install_report = (out + err)
        j.surfer_line = next((ln.strip() for ln in (out + err).splitlines()
                              if ln.strip().startswith("surfer ")), "(no surfer line)")
        settings_text = j.settings.read_text()
        j.surfer_wired = "history-surfer" in settings_text
        s.observe("history-surfer, the mission hook's dependency",
                  "installer said: %s\n\ncapture hook in <out>/claude/settings.json: %s"
                  % (j.surfer_line,
                     "\n".join(ln.strip() for ln in settings_text.splitlines()
                               if "history-surfer" in ln) or "(NONE)"))
        s.note("The installer ran on the operator's own PATH, `surfer` and all. Its "
               "history-surfer step asks whether history-surfer's hooks are in the "
               "TARGET settings.json, never whether the CLI is on PATH, and it wires an "
               "existing checkout rather than cloning a second one -- so what is asserted "
               "above is that a machine that already has history-surfer still gets the "
               "capture hook in THIS config. Until 2026-09-03 the step returned on "
               "`shutil.which(\"surfer\")` and this journey had to prune the PATH of that "
               "one subprocess to measure the mission hook rather than a missing "
               "dependency.")

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
                     "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
                     "twenty": 20, "twenty-one": 21, "twenty-two": 22,
                     "twenty-three": 23, "twenty-four": 24, "twenty-five": 25}
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
    """The transcript file for the newest session this journey created.

    Under the projects root the RUN's config directory writes to: the operator's real
    ~/.claude/projects in ambient mode, <out>/claude/projects in fresh mode.
    """
    root = j.projects_root
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
        # WHICH SCOPE IS MEASURED, AND WHY IT DEPENDS ON THE MODE. <out>/claude/skills
        # is a PERSONAL skills directory, and a session only reads it when
        # CLAUDE_CONFIG_DIR points at <out>/claude. In ambient mode it does not -- step 0
        # measured that directory as unauthenticated -- so the same SKILL.md is copied
        # where the scratch project loads it and the gate runs at PROJECT scope. In fresh
        # mode the personal roster IS reachable, which is consequence 3 of docs/e2e.md
        # removed, so nothing is copied and the gate runs where the forge installed it.
        if j.config_mode == "fresh":
            dest = src
            s.observe("the skill under test",
                      "%s\n(the throwaway PERSONAL roster, reached through "
                      "CLAUDE_CONFIG_DIR=<out>/claude; nothing was copied into the "
                      "project)" % (dest / "SKILL.md"))
            s.note("This is the routing gate at **n = 1**: one prompt, one model tier, "
                   "one CLI build. docs/CLAUDE-CODE-BEHAVIOR.md scores routing on the "
                   "stream's `Skill` tool call, never on the answer's prose, and so "
                   "does this.")
            s.note("Scope: **personal**. This is the one measurement `--config-dir "
                   "fresh` changes, and it is consequence 3 of docs/e2e.md -- the "
                   "throwaway personal skills directory being on no session's roster. "
                   "A FAIL here is a real finding about personal-scope routing and not "
                   "a harness problem.")
        else:
            dest = j.project / ".claude" / "skills" / SKILL_NAME
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / "SKILL.md", dest / "SKILL.md")
            s.observe("the skill under test", "%s\n(copied from %s; see the note below)"
                      % (dest / "SKILL.md", src))
            s.note("This is the routing gate at **n = 1**: one prompt, one model tier, "
                   "one CLI build. docs/CLAUDE-CODE-BEHAVIOR.md scores routing on the "
                   "stream's `Skill` tool call, never on the answer's prose, and so "
                   "does this.")
            s.note("Scope: **project**, not personal. The throwaway personal skills "
                   "directory is unreachable without CLAUDE_CONFIG_DIR, which step 0 "
                   "measured as unauthenticated on this machine. `--config-dir fresh` "
                   "is the mode that measures personal scope.")
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
        root = j.projects_root
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


# ------------------------------------------------------------- the mission (steps 12-14)
#
# `hooks/mission.sh` states the user's own prompts, verbatim, at five moments. Three of
# them are measured here, and they are the three a session cannot fake: after a
# compaction has replaced the context, inside a subagent that never saw the prompt, and
# at a completion claim. The other two (`dispatch`, `periodic`) fire on a clock or on an
# expensive dispatch and are exercised incidentally by these same sessions.
#
# EVERY ONE DEPENDS ON history-surfer. The hook keeps no copy of the prompts; it reads
# them out of history-surfer's store, so a run whose install could not put that
# dependency into the throwaway config measures nothing. That case is a FAIL carrying the
# installer's own sentence, never a silent pass.

MISSION_PHRASE_12 = "the marmalade gantry audit"
MISSION_PHRASE_13 = "the pemmican ledger rewrite"
# The one word of it that nothing else on the machine says. A subagent answering with
# THIS was told by the hook and by nothing else.
MISSION_TOKEN_13 = "pemmican"
MISSION_PHRASE_14 = "the sundial calibration sweep"

# The first line hooks/mission.sh renders on its full-mission arms. A subagent quoting
# THIS quoted nothing the parent typed: it is the hook's own framing.
MISSION_PREAMBLE = "requests in this session, verbatim, oldest first"

# `MISSION_STOP_MIN_TOOLS` is 8 by default. The Stop arm is worth one session, not eight
# tool calls' worth of one, so the knob is turned down for that step's call ALONE -- the
# hook reads it from the environment for exactly this purpose.
STOP_MIN_TOOLS_FOR_STEP_14 = "2"

STOP_CLAIM_RE = re.compile(
    r"(^|[^A-Za-z])(done|complete|completed|finished|implemented|landed|"
    r"all tests pass|all tests passed|all tests passing|ready to merge)([^A-Za-z]|$)",
    re.I)


def mission_hits(j, since=0):
    """Rows hooks/mission.sh appended to <state>/mission/hits.jsonl."""
    return jsonl(j.state_dir / "mission" / "hits.jsonl")[since:]


def surfer_rows(j, sid=None):
    """Prompt rows history-surfer captured for the scratch project."""
    slug = re.sub(r"[^a-zA-Z0-9]", "-", str(j.project)) or "unknown"
    rows = jsonl(j.surfer_store / "projects" / slug / "prompts.jsonl")
    if sid:
        rows = [r for r in rows if r.get("session_id") == sid]
    return rows


def session_id_of(res):
    """The session id of a call, from the stream's `init` event or any session_id."""
    if res is None:
        return ""
    for ev in stream_events(res["out"]):
        if ev.get("session_id"):
            return ev["session_id"]
    m = re.search(r'"session_id"\s*:\s*"([0-9a-f-]{8,})"', res["out"])
    return m.group(1) if m else ""


def assistant_turns(res):
    """The assistant's text turns, in order, out of a stream-json transcript."""
    turns = []
    for ev in stream_events(res["out"] if res else ""):
        if ev.get("type") == "assistant":
            text = "".join(c.get("text", "")
                           for c in ((ev.get("message") or {}).get("content") or [])
                           if c.get("type") == "text")
            if text.strip():
                turns.append(text)
    return turns


def tool_results(res):
    """Every tool_result body in a stream, as text."""
    out = []
    for ev in stream_events(res["out"] if res else ""):
        if ev.get("type") != "user":
            continue
        for c in ((ev.get("message") or {}).get("content") or []):
            if c.get("type") != "tool_result":
                continue
            body = c.get("content")
            out.append(body if isinstance(body, str) else json.dumps(body))
    return out


def _mission_precondition(j, s):
    """False (with the verdict already written) when the mission cannot be measured."""
    if not getattr(j, "surfer_wired", False):
        s.verdict("FAIL",
                  "history-surfer is not wired into the throwaway config, so "
                  "hooks/mission.sh has no store to read and cannot deliver anything. "
                  "The installer said: %s" % getattr(j, "surfer_line", "(nothing)"))
        return False
    if j.args.no_model:
        s.verdict("SKIPPED", "--no-model: every mission moment needs a real session")
        return False
    return True


def step12_mission_compact(j):
    s = j.step("12", "the mission survives a compaction (SessionStart source=compact)")
    try:
        if not _mission_precondition(j, s):
            return
        before = len(mission_hits(j))
        prompt = ("I am working on %s for this project. Start by running `echo "
                  "gantry-1` with the Bash tool, then reply with one short sentence "
                  "saying you have started." % MISSION_PHRASE_12)
        s.cmd("claude -p --output-format stream-json --permission-mode "
              "bypassPermissions  < '... %s ...'" % MISSION_PHRASE_12)
        res = j.claude(prompt, cwd=j.project, stream=True, max_turns=6,
                       label="claude-mission-open",
                       extra=["--permission-mode", "bypassPermissions"])
        sid = session_id_of(res)
        s.observe("session id, and the prompt history-surfer captured for it",
                  "session_id=%s\n%s"
                  % (sid or "(none)",
                     "\n".join(json.dumps({k: v for k, v in r.items()
                                           if k in ("seq", "prompt", "is_command",
                                                    "text_final")})[:300]
                               for r in surfer_rows(j, sid)) or
                     "(NO ROWS: history-surfer captured nothing for this session)"))
        if not sid:
            s.verdict("FAIL", "no session id in the stream, so nothing can be resumed")
            return

        s.cmd("claude -p --resume %s  < '/compact'" % sid[:8])
        res2 = j.claude("/compact", cwd=j.project, max_turns=2,
                        label="claude-compact", extra=["--resume", sid])
        s.observe("the /compact call", (final_text(res2) or res2["err"]).strip()[:400])
        sid2 = session_id_of(res2) or sid

        ask = ("Without using any tools, quote verbatim any text of the USER's own "
               "requests that you can see in your context right now. If you can see "
               "none, reply with exactly: NONE.")
        s.cmd("claude -p --resume %s --output-format stream-json  < 'quote verbatim any "
              "text of the USER's own requests you can see'" % sid2[:8])
        res3 = j.claude(ask, cwd=j.project, stream=True, max_turns=2,
                        label="claude-mission-after-compact",
                        extra=["--resume", sid2, "--disallowed-tools",
                               "Bash,Read,Grep,Glob,Write,Edit,WebFetch,WebSearch,Task"])
        answer = final_text(res3).strip()
        s.observe("what the resumed session could still see", answer[:800])

        rows = [r for r in mission_hits(j, before)
                if r.get("session") in (sid, sid2)]
        s.observe("<state>/mission/hits.jsonl rows for this session",
                  "\n".join(json.dumps(r) for r in rows) or "(none)")
        s.observe("every hits.jsonl row this step appended (any session)",
                  "\n".join(json.dumps(r) for r in mission_hits(j, before)) or "(none)")
        resumed = [r for r in rows if r.get("moment") == "resume"]
        said_it = MISSION_PHRASE_12.lower() in answer.lower()
        s.note("`moment` is **resume**, not `compact`: hooks/mission.sh:344 folds "
               "`SessionStart` sources `compact` and `resume` into one arm, because both "
               "are a session that has lost what was said.")
        s.note("The phrase coming back is evidence the REQUEST TEXT survived; the "
               "hits.jsonl row is the evidence that mission.sh is what carried it. Both "
               "are required here, and neither alone is read as the other.")
        if resumed and said_it:
            s.verdict("PASS", "the resumed session quoted %r back, and mission.sh "
                              "recorded %s"
                      % (MISSION_PHRASE_12, json.dumps(resumed[0])))
        elif resumed:
            s.verdict("FAIL", "mission.sh delivered (%s) but the phrase %r did not come "
                              "back: %r"
                      % (json.dumps(resumed[0]), MISSION_PHRASE_12, answer[:200]))
        else:
            s.verdict("FAIL", "no hits.jsonl row with moment=resume for %s/%s; rows "
                              "seen: %r"
                      % (sid[:8], sid2[:8],
                         [r.get("moment") for r in mission_hits(j, before)]))
    finally:
        s.finish()


def step13_mission_subagent(j):
    s = j.step("13", "the mission reaches a subagent that never saw the prompt")
    try:
        if not _mission_precondition(j, s):
            return
        before = len(mission_hits(j))
        # WHAT THE SUBAGENT IS ASKED, AND THE THREE WORDINGS THAT FAILED FIRST. Asked for
        # "every user-request text you can see", a subagent quoted back its own task and
        # nothing else: it read the injected mission as scenery rather than as a request.
        # Asked for "text BEFORE this sentence" it answered NONE -- not an absence, but
        # the hook's own layout, since the closing sentence mission.sh appends on this arm
        # says the parent's instructions appear ABOVE the requests. Asked for "everything
        # in your context that is not this sentence", the PARENT refused outright and
        # named it a system-prompt extraction pattern, which is the correct call and a
        # useful thing to have learnt: a probe shaped like an exfiltration is not a probe
        # this package can run. So the question is now the one the hook exists to answer
        # -- can an agent that was told nothing say what the user is working on -- and it
        # asks for one line, not for a context dump.
        prompt = (
            "I am working on %s for this project, and I want to check whether a subagent "
            "can tell what I am working on without being told. Use the Agent tool with "
            "subagent_type general-purpose, and put ONLY this in that agent's prompt, "
            "copied exactly: \"Without using any tools, answer in one short line: what "
            "is the user of this session working on? If you cannot tell, reply with "
            "exactly: UNKNOWN.\" Do not mention my project to the agent and do not "
            "answer for it. Then paste the agent's answer back to me in full."
            % MISSION_PHRASE_13)
        s.cmd("claude -p --output-format stream-json --permission-mode "
              "bypassPermissions  < '<dispatch a general-purpose subagent>'")
        res = j.claude(prompt, cwd=j.project, stream=True, max_turns=10,
                       label="claude-mission-subagent",
                       extra=["--permission-mode", "bypassPermissions"])
        agent_inputs = []
        for ev in stream_events(res["out"]):
            if ev.get("type") != "assistant":
                continue
            for c in ((ev.get("message") or {}).get("content") or []):
                if c.get("type") == "tool_use" and c.get("name") in ("Agent", "Task"):
                    agent_inputs.append(json.dumps(c.get("input"))[:600])
        s.observe("what the parent actually told the subagent (so a reader can see "
                  "what it was told, which is the other half of what its answer means)",
                  "\n".join(agent_inputs) or "(no Agent/Task call in the stream)")
        reports = tool_results(res)
        s.observe("the subagent's report, as it came back to the parent",
                  "\n---\n".join(r[:1200] for r in reports) or "(none)")
        s.observe("the parent's closing message", final_text(res).strip()[:600])

        rows = mission_hits(j, before)
        s.observe("<state>/mission/hits.jsonl rows appended by this session",
                  "\n".join(json.dumps(r) for r in rows) or "(none)")
        sub_rows = [r for r in rows
                    if r.get("moment") == "subagent" and r.get("agent_id")]

        # WHERE THE EVIDENCE IS, AND WHY IT IS NOT THE SUBAGENT'S ANSWER. A row in
        # hits.jsonl says the hook emitted; only the SUBAGENT'S OWN transcript says the
        # emission arrived, and Claude Code writes one per agent at
        # <project>/<sid>/subagents/agent-<agent_id>.jsonl with the injection recorded as
        # an `attachment` of type `hook_additional_context` carrying `hookName`
        # "SubagentStart". The subagent's ANSWER is a second question -- whether it acted
        # on what it was handed -- and reading the two as one is how a run where the
        # parent merely mentioned the token in its own prose reads as a delivery. That
        # false pass happened here before this was split.
        sid = session_id_of(res)
        agent_id = sub_rows[0].get("agent_id") if sub_rows else None
        sub_tx, injected = None, []
        if sid and agent_id:
            for p in j.projects_root.glob(
                    "*/%s/subagents/agent-%s.jsonl" % (sid, agent_id)):
                sub_tx = p
                for r in jsonl(p):
                    att = r.get("attachment") or {}
                    if att.get("type") == "hook_additional_context" and \
                            "SubagentStart" in str(att.get("hookName") or
                                                   att.get("hookEvent") or ""):
                        injected.append(json.dumps(att.get("content"))[:900])
        s.observe("the subagent's OWN transcript (%s)" % (sub_tx or "not found"),
                  "\n".join(injected) or
                  "(no SubagentStart hook_additional_context attachment in it)")

        delivered = any(MISSION_TOKEN_13 in i.lower() or
                        MISSION_PREAMBLE.lower() in i.lower() for i in injected)
        acted = MISSION_TOKEN_13 in ("\n".join(reports)).lower()
        s.note("`agent_id` is non-null only on the SubagentStart arm: it is the "
               "subagent's own id, and it is what tells a delivery to the child apart "
               "from the `dispatch` delivery the parent gets on the same tool call.")
        s.note("Delivery and use are reported separately. On this run the subagent %s"
               % ("answered with the token, so it used what it was handed." if acted else
                  "was handed the mission and still answered that it could not tell what "
                  "the user was working on. That is a limit of the ARM, not of the "
                  "wiring: the hook's own header records that imperative wording was "
                  "refused as prompt injection in 2 of 4 measured runs, and a statement "
                  "of fact can be read and set aside just as easily. This step measures "
                  "arrival, which is the part the package controls."))
        if sub_rows and delivered:
            s.verdict("PASS", "mission.sh recorded %s and the subagent's own transcript "
                              "carries the injection: %s"
                      % (json.dumps(sub_rows[0]), (injected[0] if injected else "")[:220]))
        elif sub_rows:
            s.verdict("FAIL", "mission.sh recorded a subagent delivery (%s) but the "
                              "subagent's own transcript carries no SubagentStart "
                              "injection (%s)"
                      % (json.dumps(sub_rows[0]), sub_tx or "no transcript found"))
        else:
            s.verdict("FAIL", "no hits.jsonl row with moment=subagent and a non-null "
                              "agent_id; rows seen: %r"
                      % [(r.get("moment"), r.get("agent_id")) for r in rows])
    finally:
        s.finish()


def step14_mission_completion(j):
    s = j.step("14", "the mission is stated once at a completion claim (Stop)")
    try:
        if not _mission_precondition(j, s):
            return
        before = len(mission_hits(j))
        prompt = ("Do exactly this and nothing more, as part of %s: run `echo "
                  "sundial-a` with the Bash tool, then run `echo sundial-b` with the "
                  "Bash tool, then reply with exactly the word: done"
                  % MISSION_PHRASE_14)
        s.cmd("MISSION_STOP_MIN_TOOLS=%s claude -p --output-format stream-json "
              "--permission-mode bypassPermissions  < 'two echoes, then \"done\"'"
              % STOP_MIN_TOOLS_FOR_STEP_14)
        res = j.claude(prompt, cwd=j.project, stream=True, max_turns=10,
                       label="claude-mission-stop",
                       extra=["--permission-mode", "bypassPermissions"],
                       env=j.env(MISSION_STOP_MIN_TOOLS=STOP_MIN_TOOLS_FOR_STEP_14))
        turns = assistant_turns(res)
        s.observe("the assistant's text turns, in order",
                  "\n---\n".join("[%d] %s" % (i, t.strip()[:400])
                                 for i, t in enumerate(turns)) or "(none)")
        claim_at = next((i for i, t in enumerate(turns) if STOP_CLAIM_RE.search(t)), None)
        after_claim = turns[claim_at + 1:] if claim_at is not None else []
        rows = mission_hits(j, before)
        s.observe("<state>/mission/hits.jsonl rows appended by this session",
                  "\n".join(json.dumps(r) for r in rows) or "(none)")
        completions = [r for r in rows if r.get("moment") == "completion"]
        s.note("The Stop arm blocks at most ONCE per prompt_id, so \"exactly one\" is "
               "the claim being checked, not \"at least one\": a second block would "
               "spend the operator's turn twice for one completion claim.")
        s.note("`MISSION_STOP_MIN_TOOLS` was %s for this call only. The shipped default "
               "is 8; the arm being measured is the same one either way, and the knob is "
               "read from the environment for exactly this." % STOP_MIN_TOOLS_FOR_STEP_14)
        if len(completions) == 1 and after_claim:
            s.verdict("PASS", "the turn claimed completion at turn %d and the Stop hook "
                              "put another turn after it (%r); one completion row: %s"
                      % (claim_at, after_claim[0].strip()[:120],
                         json.dumps(completions[0])))
        elif len(completions) == 1:
            s.verdict("FAIL", "one completion row (%s) but no assistant turn after the "
                              "claim; turns seen: %d"
                      % (json.dumps(completions[0]), len(turns)))
        else:
            s.verdict("FAIL", "expected exactly one completion row; got %d: %r"
                      % (len(completions), [json.dumps(r) for r in completions][:3]))
    finally:
        s.finish()


# ------------------------------------------------------------- the lesson (steps 15-16)
#
# `hooks/repeat-gate.sh`'s recovery arm says it the FIRST time: a call failed, a different
# call succeeded, and the store bound the two. `bin/skillnote add --lesson` is the one
# command that records it in three places at once, and `hooks/remind.sh` is what states
# it back to the next session about to make the same call.

LESSON_BAD_CMD = "ls --nonexistent-flag ."
LESSON_GOOD_CMD = "ls -la ."
LESSON_SCRIPT = "ls-portably.sh"


def repeat_rows(j, kind=None, session=None):
    rows = jsonl(j.state_dir / "repeats" / "index.jsonl")
    if kind:
        rows = [r for r in rows if r.get("t") == kind]
    if session:
        rows = [r for r in rows if r.get("session") == session]
    return rows


def _transcript_for(j, sid):
    root = j.projects_root
    if not sid or not root.exists():
        return None
    for p in root.glob("*/%s.jsonl" % sid):
        return p
    return None


def step15_lesson_first_time(j):
    s = j.step("15", "a failure and its recovery are bound, and the session is told so")
    try:
        if j.args.no_model:
            s.verdict("SKIPPED", "--no-model: the recovery arm needs two real tool calls")
            return
        before = len(repeat_rows(j))
        # ONE CALL AT A TIME, SAID OUT LOUD. Asked for both commands without this, the
        # model issued them as PARALLEL tool calls in a single assistant message, and the
        # SUCCESS came back before the FAILURE. The recovery arm binds forward in time
        # only -- it arms on a failure and looks at later successes -- so nothing bound,
        # and the store held a `fail` row with no `recover`. That is a real property of
        # the arm rather than a defect of it, and it is recorded in the notes below.
        prompt = ("Run this exact command with the Bash tool and WAIT for its result "
                  "before doing anything else: %s\nIt will fail; that is expected and it "
                  "is what I want to see. Only after you have seen that failure, run "
                  "this one: %s\nDo not put both commands in the same message. Then tell "
                  "me in one line what the difference was."
                  % (LESSON_BAD_CMD, LESSON_GOOD_CMD))
        s.cmd("claude -p --output-format stream-json --permission-mode "
              "bypassPermissions  < 'run `%s`, then `%s`'"
              % (LESSON_BAD_CMD, LESSON_GOOD_CMD))
        res = j.claude(prompt, cwd=j.project, stream=True, max_turns=8,
                       label="claude-lesson-first",
                       extra=["--permission-mode", "bypassPermissions"])
        sid = session_id_of(res)
        s.observe("answer", final_text(res).strip()[:400])

        new = repeat_rows(j)[before:]
        s.observe("<state>/repeats/index.jsonl rows appended by this session",
                  "\n".join(json.dumps(r)[:400] for r in new) or "(none)")
        recovers = [r for r in new if r.get("t") == "recover"]
        fails = [r for r in new if r.get("t") == "fail"]

        # The statement the PostToolUse arm emits reaches the MODEL as
        # additionalContext, which --output-format stream-json does not echo. Claude
        # Code writes it into the session transcript, so that is where it is read from,
        # with the stream checked too in case a later build echoes it.
        transcript = _transcript_for(j, sid)
        hay = res["out"]
        if transcript is not None and transcript.exists():
            hay += "\n" + transcript.read_text(errors="replace")
        quoted = [ln for ln in hay.splitlines() if "skillnote add --lesson" in ln]
        s.observe("the lesson statement, found in %s"
                  % (transcript if transcript else "the stream only"),
                  "\n".join(q.strip()[:600] for q in quoted[:2]) or "(not found)")

        s.note("The two calls have to be SEQUENTIAL. Issued as parallel tool calls in "
               "one assistant message, the success came back before the failure on this "
               "machine and nothing bound: `hooks/repeat-gate.sh` arms on a failure and "
               "binds a later success, so a recovery that arrives first is not one. The "
               "prompt says so explicitly for that reason.")
        if recovers:
            j.lesson_sig = recovers[0].get("sig")
            j.lesson_session = sid
        if recovers and quoted:
            s.verdict("PASS", "the store bound the recovery (%s) and the session was "
                              "handed the statement naming `skillnote add --lesson %s`"
                      % (json.dumps(recovers[0])[:220], j.lesson_sig))
        elif recovers:
            s.verdict("FAIL", "the store bound the recovery (%s) but no surface here "
                              "carries the statement the PostToolUse arm emitted"
                      % json.dumps(recovers[0])[:220])
        else:
            s.verdict("FAIL", "no recover row; %d fail row(s) seen: %r"
                      % (len(fails), [r.get("norm") for r in fails][:3]))
    finally:
        s.finish()


def step16_lesson_recorded(j):
    s = j.step("16", "the lesson is recorded in three places and reaches the next "
                     "session")
    try:
        sig = getattr(j, "lesson_sig", None)
        if not sig:
            s.verdict("SKIPPED", "step 15 bound no recovery, so there is no signature "
                                 "to record a lesson against")
            return
        script = j.project / LESSON_SCRIPT
        script.write_text("#!/bin/sh\n# what to run instead of `%s`\nexec ls -la \"$@\"\n"
                          % LESSON_BAD_CMD)
        os.chmod(script, 0o755)
        text = ("BSD `ls` has no --nonexistent-flag and fails before listing anything; "
                "use `%s` instead." % LESSON_GOOD_CMD)
        s.cmd("<out>/bin/skillnote add --lesson %s --scope project --project "
              "<out>/project --attach %s %r" % (sig, LESSON_SCRIPT, text))
        rc, out, err = j.run([str(j.bin_dir / "skillnote"), "add", "--lesson", sig,
                              "--scope", "project", "--project", str(j.project),
                              "--attach", str(script), text],
                             cwd=j.project, label="skillnote-lesson")
        s.observe("skillnote add --lesson (rc=%d)" % rc, (out + err).strip())

        md = j.project / ".claude" / "CLAUDE.md"
        md_line = next((ln for ln in (md.read_text().splitlines() if md.exists() else [])
                        if "lesson:%s" % sig in ln), "")
        s.observe("1/3 the note line in <out>/project/.claude/CLAUDE.md",
                  md_line or "(no line carrying lesson:%s)" % sig)
        rem = [r for r in jsonl(j.state_dir / "reminders.jsonl")
               if r.get("lesson_sig") == sig]
        s.observe("2/3 the reminder row in <state>/reminders.jsonl",
                  "\n".join(json.dumps(r) for r in rem) or "(none)")
        led = [r for r in jsonl(j.state_dir / "ledger.jsonl")
               if r.get("lesson_sig") == sig]
        s.observe("3/3 the ledger note row",
                  "\n".join(json.dumps(r)[:500] for r in led) or "(none)")
        attached = sorted(str(p.relative_to(j.project))
                          for p in (j.project / ".claude" / "lessons").rglob("*")
                          if p.is_file()) if (
            j.project / ".claude" / "lessons").exists() else []
        s.observe("the attachment, copied into the project's own lessons directory",
                  "\n".join(attached) or "(none)")
        three = bool(md_line) and bool(rem) and bool(led)
        if rc != 0 or not three:
            s.verdict("FAIL", "rc=%d; CLAUDE.md line=%s, reminder rows=%d, ledger "
                              "rows=%d" % (rc, bool(md_line), len(rem), len(led)))
            return
        if j.args.no_model:
            s.verdict("SKIPPED", "--no-model: the readback needs a following session")
            return

        hits = j.state_dir / "remind" / "hits.jsonl"
        before = len(jsonl(hits))
        prompt = ("Run this exact command with the Bash tool, exactly as written, and "
                  "then tell me what it printed: %s" % LESSON_BAD_CMD)
        s.cmd("claude -p --setting-sources project --permission-mode bypassPermissions "
              "  < 'run `%s`'" % LESSON_BAD_CMD)
        res = j.claude(prompt, cwd=j.project, setting_sources="project", stream=True,
                       max_turns=6, label="claude-lesson-readback",
                       extra=["--permission-mode", "bypassPermissions"])
        s.observe("answer", final_text(res).strip()[:400])
        rows = jsonl(hits)[before:]
        s.observe("<state>/remind/hits.jsonl rows appended by that session",
                  "\n".join(json.dumps(r) for r in rows) or "(none)")
        fired = [r for r in rows if r.get("id") == (rem[0].get("id") if rem else None)]
        s.note("The reminder is keyed on the failing call's normalised signature, taken "
               "verbatim from that signature's own `fail` row -- not on a keyword and "
               "not on the command as the model happened to write it.")
        if fired:
            s.verdict("PASS", "one command reminder (%s) and one lesson line, one "
                              "reminder row and one ledger row for %s: %s"
                      % (rem[0].get("id"), sig, json.dumps(fired[0])))
        else:
            s.verdict("FAIL", "the lesson was recorded in all three places but the "
                              "following session's `%s` fired no reminder; rows seen: %r"
                      % (LESSON_BAD_CMD, [json.dumps(r) for r in rows][:3]))
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

        # THE DEPENDENCY IS NOT OURS TO REMOVE, and that is the whole reason this is two
        # commands. Install now also installs history-surfer, whose own installer writes
        # a UserPromptSubmit and a Stop entry of its own; our uninstall removes only what
        # we wrote, so after it settings.json still carries those two. The uninstaller
        # says so and prints the exact command that takes them out. Running THAT is what
        # keeps "byte for byte" a claim about the pair rather than a claim quietly
        # narrowed to one of them.
        surviving = [ln.strip() for ln in j.settings.read_text().splitlines()
                     if "history-surfer" in ln]
        s.observe("what our uninstall leaves behind, and what it says about it",
                  ("\n".join(surviving) or "(nothing)") + "\n\n"
                  + next((ln.strip() for ln in (out + err).splitlines()
                          if ln.strip().startswith("surfer ")), "(no surfer line)"))
        if surviving:
            manifest = {}
            mpath = j.state_dir / "install-manifest.json"
            if mpath.exists():
                try:
                    manifest = json.loads(mpath.read_text())
                except ValueError:
                    manifest = {}
            home = ((manifest.get("surfer") or {}).get("home")
                    or str(Path(REPO).parent / "claude-history-surfer"))
            s.cmd("python3 %s/scripts/setup.py --uninstall --claude-dir <out>/claude "
                  "--bin-dir <out>/bin   # the command the line above prints" % home)
            rc_s, out_s, err_s = j.run(
                [sys.executable, str(Path(home) / "scripts" / "setup.py"), "--uninstall",
                 "--claude-dir", str(j.claude_dir), "--bin-dir", str(j.bin_dir)],
                cwd=REPO, label="uninstall-surfer")
            s.observe("history-surfer's own uninstall (rc=%d)" % rc_s,
                      (out_s + err_s).strip())
            s.note("Two uninstalls, in the order the first one prints. `%s` is left on "
                   "disk by both, with the prompt history in it: neither package created "
                   "that data and neither deletes it." % j.surfer_store)

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


# RUN ORDER, NOT NUMBER ORDER. Step 11 tears the install down, so everything that needs
# the wiring has to run before it. Steps 12-16 were added after 11 was numbered and
# docs/e2e.md cites the numbers, so the numbers stay where they are and this list says
# what actually happens: ... 10, 12, 13, 14, 15, 16, 11. The report lists steps in the
# order they ran, which is this order.
STEPS = [step0_preflight, step1_install, step2_ordinary_session, step3_note,
         step4_reminders, step5_candidate, step6_promote, step7_forge, step8_routing,
         step9_apply_verdict, step10_report,
         step12_mission_compact, step13_mission_subagent, step14_mission_completion,
         step15_lesson_first_time, step16_lesson_recorded,
         step11_uninstall]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="One canonical end-to-end journey through claude-skill-compounder. "
                    "Spends real claude -p calls; never run it in CI.")
    ap.add_argument("--out",
                    help="directory to build the throwaway world in and keep every "
                         "artifact under (created if absent; must be empty or new). "
                         "Required, except with --check-auth, which makes its own.")
    ap.add_argument("--config-dir", choices=("ambient", "fresh"), default="ambient",
                    help="ambient (default): HOME and CLAUDE_CONFIG_DIR are left alone "
                         "and each session gets the throwaway configuration through "
                         "--settings with --setting-sources. fresh: CLAUDE_CONFIG_DIR "
                         "points at <out>/claude, neither flag is passed, and a "
                         "credential must be in the environment "
                         "(CLAUDE_CODE_OAUTH_TOKEN, from `claude setup-token`, or "
                         "ANTHROPIC_API_KEY). See docs/e2e.md.")
    ap.add_argument("--check-auth", action="store_true",
                    help="spend ONE claude -p call answering whether the chosen "
                         "--config-dir can authenticate, print the CLI's own answer, "
                         "and exit (0 authenticated, 3 not). Run it before a real "
                         "journey: the journey is thirteen calls and none of the other "
                         "twelve would tell you anything new about a stale token.")
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

    # THE REFUSAL, BEFORE ANYTHING IS BUILT OR SPENT. `--config-dir fresh` has no stored
    # login to fall back on, so without a credential in the environment every one of the
    # thirteen calls would be answered `Not logged in · Please run /login`. --check-auth
    # is exempt on purpose: "have I got a token?" is exactly what an operator without one
    # runs, and it answers in one call with the CLI's own words. --no-model spends none.
    if args.config_dir == "fresh" and not args.no_model and not args.check_auth \
            and not credential_name():
        print("error: --config-dir fresh needs a credential in the environment and "
              "found neither %s: run `claude setup-token` and export the result as "
              "CLAUDE_CODE_OAUTH_TOKEN (or set ANTHROPIC_API_KEY), because a throwaway "
              "CLAUDE_CONFIG_DIR has no stored login and answers `Not logged in · "
              "Please run /login`." % " nor ".join(TOKEN_VARS), file=sys.stderr)
        return 2

    if args.out:
        out = Path(args.out).expanduser().resolve()
        if out.exists() and any(out.iterdir()):
            print("error: %s exists and is not empty. Pick a fresh --out." % out,
                  file=sys.stderr)
            return 2
    elif args.check_auth:
        out = Path(tempfile.mkdtemp(prefix="journey-check-auth-"))
    else:
        print("error: --out is required (it is optional only with --check-auth).",
              file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)

    j = Journey(out, args)
    if args.check_auth:
        return check_auth_only(j)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    print("e2e journey -> %s  (--config-dir %s)" % (out, args.config_dir))
    for fn in STEPS:
        num = fn.__name__[4:fn.__name__.index("_")]
        if j.abort or (only and num not in only):
            s = j.step(num, fn.__name__[fn.__name__.index("_") + 1:].replace("_", " "))
            s.verdict("SKIPPED", j.abort or ("--only %s" % args.only))
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
