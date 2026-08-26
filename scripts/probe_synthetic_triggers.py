#!/usr/bin/env python3
"""Probe a skill whose trigger is a moment DURING the assistant's own work.

WHY THIS EXISTS
    `scripts/probe_routing_claims.py` supplies a user prompt and sees which skill fires.
    That proves exactly one thing: "if a user types this, the skill fires." Several
    shipped skills do not name a thing a user says. They name a moment that arises in
    the middle of the assistant's own work, with no user prompt anywhere near it --
    `stale-artifact-check` ("an edit you made appears to have had no observable
    effect"), `no-silent-stub`, `destructive-op-preflight`. A prompt probe cannot
    reach those moments, and it scores them 3/3 anyway.

    This script reaches them a different way: it RIGS A WORLD in which the moment is
    forced to occur, hands the session a neutral task that does not describe the
    moment, and watches whether the skill fires when the session walks into it.

MEASURED RESULT THAT MOTIVATED THIS (2026-08-26, cli 2.1.245, model sonnet)
    stale-artifact-check, the `stale_install` scenario below:

      organic  (neutral prompt, moment arises during the work)   fired  1/8
      control  (same rigged world, moment stated in the prompt)  fired  7/7
      existing prompt probe, `probe_routing_claims.py`           fired  3/3

    The moment was confirmed reached in all 8 organic replicates: the session edited
    the source, re-ran the runner, and got byte-identical output. It routed to
    `superpowers:systematic-debugging` on turn 1 in 8/8 and never came back to
    `stale-artifact-check` in 7 of them. So the number this script produces is real,
    and it is not the number the prompt probe produces. The gap between 7/7 and 1/8
    in ONE world, holding everything but the prompt constant, is the whole finding:
    the description owns the words a user types, not the moment it names.

WHAT WAS TRIED AND DOES NOT WORK (do not re-litigate without re-measuring)
    Injecting a fake mid-work history via `--input-format stream-json` looks like it
    works and does not. Plain assistant TEXT survives, but the CLI merges consecutive
    injected assistant messages into one and DROPS every injected `tool_result`,
    re-synthesising the missing ones. Established by running a seeded stream under
    `-d api --debug-file`, which logged:

        ensureToolResultPairing: repaired missing tool_result blocks (5 -> 5 messages).
        Message structure: [0] user; [1] api_system;
        [2] assistant(id=undefined, tool_uses=[toolu_01aaaa,toolu_01bbbb,toolu_01cccc]);
        [3] user; [4] api_system

    Three separate injected assistant turns collapsed into message [2] and all three
    injected tool_results vanished. So a seeded session cannot END on tool output; the
    model answers the first user text instead, and the "moment" never exists.
    Hand-authoring a transcript under `~/.claude/projects/` and `--resume`-ing it was
    NOT tested. `CLAUDE_CONFIG_DIR` relocates `projects/` but breaks auth
    ("Not logged in - Please run /login"), so that path could not be tested without
    writing into the real config directory.

GATE
    Refuses to run unless SKILL_SYNTHETIC_PROBE=1. Deliberately a DIFFERENT variable
    from `SKILL_ROUTING_PROBE`, so setting one never silently spends quota on the
    other. It must never fire from `./run_tests.sh` or CI.

MODEL
    `--model sonnet`, always, and not a flag. Personal and project skill descriptions
    were measured ABSENT from the router on haiku, so a haiku probe proves nothing
    about routing. Same reason as `probe_routing_claims.py`.

COST AND RUNTIME (measured 2026-08-26)
    An organic replicate is one `claude -p --max-turns 25` session that really edits
    files and runs commands: 90-180s and far more tokens than a prompt probe call. A
    control replicate is one `--max-turns 3` session, 20-60s. The default run is
    `--n 3`, so 6 calls per scenario. Replicates run in parallel.

PERMISSIONS
    Organic replicates pass `--dangerously-skip-permissions`, because the session must
    actually edit and execute to reach the moment. Every replicate runs in a fresh
    `tempfile.mkdtemp()` that this script created and deletes, and the rig is built
    entirely from local files. Nothing outside that directory is a target.

WHAT IT CANNOT SEE
    - It measures ONE rigged world per scenario. A skill can own its moment in the
      shape this rig makes and miss it in another shape. The fire rate is a lower
      bound on nothing and an upper bound on nothing; it is a measurement of this rig.
    - "Did not fire" is not "did the wrong thing". In the measured 5/6 non-firing runs
      the session diagnosed the stale install correctly on its own. This script
      reports ROUTING, not outcome.
    - Like the prompt probe, it sees the router as installed on THIS machine at THIS
      moment, including every plugin's skills. The measured competitor here is
      `superpowers:systematic-debugging`, which won turn 1 in 6/6 organic runs.
    - `stale_install` builds a venv and runs `pip install pytest`. With no network and
      no wheel cache the rig cannot be built; the script self-checks and refuses
      rather than reporting a fire rate from a world that was not actually stale.

Usage:
    SKILL_SYNTHETIC_PROBE=1 python3 scripts/probe_synthetic_triggers.py
    SKILL_SYNTHETIC_PROBE=1 python3 scripts/probe_synthetic_triggers.py --n 6
    SKILL_SYNTHETIC_PROBE=1 python3 scripts/probe_synthetic_triggers.py --json out.json
"""

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

GATE = "SKILL_SYNTHETIC_PROBE"
MODEL = "sonnet"
ORGANIC_MAX_TURNS = "25"
CONTROL_MAX_TURNS = "3"
TIMEOUT = int(os.environ.get("SKILL_SYNTHETIC_PROBE_TIMEOUT", "420"))
PARALLEL = int(os.environ.get("SKILL_SYNTHETIC_PROBE_PARALLEL", "6"))


# --------------------------------------------------------------------------- rigs

def build_stale_install(root, prefixed):
    """A package installed NON-editably into a venv; edits to `src/` change nothing.

    `prefixed` is what the source tree already contains when the session arrives:
    False leaves the bug in place (the session must find and "fix" it itself, which
    is what walks it into the moment); True means the fix is already applied, for the
    control arm whose prompt says the edit already happened.
    """
    root = Path(root)
    (root / "src" / "totals").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    body = "    return sum(xs)\n" if prefixed else "    return sum(xs) + 1\n"
    (root / "src" / "totals" / "__init__.py").write_text(
        'def total(xs):\n    """Sum a list of numbers."""\n' + body)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "totals"\nversion = "0.1.0"\n\n'
        '[build-system]\nrequires = ["setuptools>=61"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        '[tool.setuptools.packages.find]\nwhere = ["src"]\n')
    (root / "tests" / "test_totals.py").write_text(
        "from totals import total\n\n\ndef test_total():\n"
        "    assert total([1, 2, 3]) == 6\n")
    run = root / "run_tests.sh"
    run.write_text('#!/bin/sh\nhere="$(cd "$(dirname "$0")" && pwd)"\n'
                   'exec "$here/.venv/bin/python" -m pytest -q "$here/tests"\n')
    run.chmod(0o755)
    (root / "README.md").write_text("# totals\n\nRun the suite with `./run_tests.sh`.\n")

    venv = root / ".venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True,
                   capture_output=True, stdin=subprocess.DEVNULL, timeout=180)
    subprocess.run([str(venv / "bin" / "pip"), "install", "-q", "pytest", str(root)],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL,
                   timeout=600)


def _normalise(text):
    """Strip a runner's own timing so two identical runs compare equal."""
    return re.sub(r"\d+\.\d+s", "<t>", text)


def verify_stale_install(root):
    """Prove the rig is really stale BEFORE spending quota on it.

    Applies the fix to the source tree and confirms the runner's output does not
    change. If it does change, the world is not stale and any fire rate measured in
    it would be meaningless.
    """
    root = Path(root)
    src = root / "src" / "totals" / "__init__.py"
    runner = [str(root / "run_tests.sh")]

    def run():
        p = subprocess.run(runner, cwd=str(root), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=180)
        return p.stdout

    before = run()
    original = src.read_text()
    src.write_text(original.replace("sum(xs) + 1", "sum(xs)"))
    after = run()
    src.write_text(original)
    if "assert 7 == 6" not in before:
        return "runner did not produce the expected failure:\n%s" % before[-500:]
    # Compare the failure SIGNATURE, not raw bytes. pytest prints its own wall clock
    # ("1 failed in 0.01s" / "0.02s"), so a byte-for-byte comparison of two identical
    # runs fails at random and reported a perfectly stale rig as not stale.
    if _normalise(before) != _normalise(after):
        return "rig is NOT stale: editing src changed the runner output"
    return None


SCENARIOS = {
    "stale_install": {
        "skill": "stale-artifact-check",
        "build": build_stale_install,
        "verify": verify_stale_install,
        # Names the task, never the moment. No "identical", no "no effect", no
        # "stale", nothing from the skill's description.
        "organic_prompt": "./run_tests.sh is failing. Please make it pass.",
        # The matched control: same world, moment spelled out in the prompt.
        "control_prompt": (
            "I already edited src/totals/__init__.py to fix the off-by-one, but "
            "./run_tests.sh still prints the character-for-character identical "
            "failure. Sort it out."),
        "moment": ("session edits src/totals, re-runs ./run_tests.sh, "
                   "and gets byte-identical output"),
    },
}


# ------------------------------------------------------------------------ running

def cli_version():
    out = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL, timeout=60)
    return out.stdout.strip() or "unknown"


def tool_calls(stream):
    """Every tool call in the stream, in order, as (name, input-json)."""
    calls = []
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_use":
                calls.append((block.get("name"), json.dumps(block.get("input") or {})))
    return calls


def skills_fired(calls):
    """Skill names from Skill tool calls.

    The argument key has been spelled `skill`, `command`, and `name` across CLI
    versions, so take whichever string field is present rather than pinning one.
    """
    fired = []
    for name, raw in calls:
        if name != "Skill":
            continue
        args = json.loads(raw)
        for key in ("skill", "command", "name", "skill_name"):
            value = args.get(key)
            if isinstance(value, str) and value:
                fired.append(value)
                break
        else:
            fired.append("Skill(<unparsed args: %s>)" % ",".join(sorted(args)))
    return fired


def _wrote_source(name, raw):
    """A write into the rigged source tree, by any means the session might use."""
    if name in ("Edit", "Write", "NotebookEdit"):
        return "src/totals" in raw
    # A session may edit through the shell instead of the edit tools.
    return name == "Bash" and "src/totals" in raw and any(
        tok in raw for tok in ("sed ", "cat >", "tee ", "python3 -c", "printf ", ">>"))


def _ran_runner(name, raw):
    """An execution of the thing whose output the session is about to trust.

    Excludes install commands: `pip install -e .` is the REPAIR, and counting it as
    the re-run would score the moment as reached on the wrong call.
    """
    if name != "Bash":
        return False
    if "pip install" in raw or "pip show" in raw:
        return False
    return "run_tests.sh" in raw or "pytest" in raw


def moment_reached(calls):
    """Did the session actually walk into the stale moment?

    Requires a write to the source tree followed by a LATER execution of the runner.
    If this is False the replicate measured nothing and must not be scored: the world
    was rigged but the session never entered it. Deliberately broad on both halves --
    a narrow matcher (Edit-tool only, exact `run_tests.sh` string) silently scored
    two real runs as `moment=False` and threw the measurement away.
    """
    edited = False
    for name, raw in calls:
        if _wrote_source(name, raw):
            edited = True
        elif edited and _ran_runner(name, raw):
            return True
    return False


def replicate(scenario, arm, index):
    spec = SCENARIOS[scenario]
    cwd = tempfile.mkdtemp(prefix="synthetic-probe-%s-%s%d-" % (scenario, arm, index))
    try:
        try:
            spec["build"](cwd, prefixed=(arm == "control"))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return {"arm": arm, "index": index, "error": "rig build failed: %s" % exc}
        if arm == "organic":
            problem = spec["verify"](cwd)
            if problem:
                return {"arm": arm, "index": index, "error": problem}

        prompt = spec["organic_prompt"] if arm == "organic" else spec["control_prompt"]
        cmd = ["claude", "-p", "--model", MODEL,
               "--max-turns", ORGANIC_MAX_TURNS if arm == "organic" else CONTROL_MAX_TURNS,
               "--output-format", "stream-json", "--verbose",
               "--no-session-persistence"]
        if arm == "organic":
            # Required: the session must really edit and execute to reach the moment.
            # The cwd is a throwaway directory this script made and deletes.
            cmd.append("--dangerously-skip-permissions")
        cmd.append(prompt)

        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                  stdin=subprocess.DEVNULL, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return {"arm": arm, "index": index, "error": "timed out after %ds" % TIMEOUT}

        calls = tool_calls(proc.stdout)
        if not calls and not any('"type":"assistant"' in ln or '"type": "assistant"' in ln
                                 for ln in proc.stdout.splitlines()):
            return {"arm": arm, "index": index,
                    "error": "claude produced no assistant turn (exit %d): %s"
                             % (proc.returncode, (proc.stderr or "").strip()[:200])}
        # A non-zero exit is NOT an error. `--max-turns` exhaustion exits 1 and happens
        # long after the routing decision this measures.
        fired = skills_fired(calls)
        return {"arm": arm, "index": index, "error": None, "fired": fired,
                "steps": len(calls),
                # Kept so a replicate that scored surprisingly can be diagnosed from
                # the --json file instead of being re-run at full cost.
                "calls": [[n, raw[:300]] for n, raw in calls],
                "moment": moment_reached(calls) if arm == "organic" else True}
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def probe(scenario, n):
    jobs = [("organic", i) for i in range(n)] + [("control", i) for i in range(n)]
    results = []
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futures = {pool.submit(replicate, scenario, arm, i): (arm, i) for arm, i in jobs}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            results.append(row)
            done += 1
            print("  [%d/%d] %-7s #%d  %s" % (
                done, len(jobs), row["arm"], row["index"],
                row.get("error") or ("moment=%s fired=%s"
                                     % (row["moment"], row["fired"] or "nothing"))),
                  file=sys.stderr)
    print("  %d replicates in %.0fs" % (len(jobs), time.time() - started), file=sys.stderr)
    return results


def report(scenario, results, version):
    spec = SCENARIOS[scenario]
    skill = spec["skill"]
    print("\nsynthetic trigger probe  scenario=%s  skill=%s  model=%s  cli=%s"
          % (scenario, skill, MODEL, version))
    print("moment: %s\n" % spec["moment"])

    def hit(row):
        return any(f == skill or f.endswith("/" + skill) or f.endswith(":" + skill)
                   for f in row.get("fired", []))

    ok = True
    for arm in ("organic", "control"):
        rows = [r for r in results if r["arm"] == arm]
        errors = [r for r in rows if r.get("error")]
        good = [r for r in rows if not r.get("error")]
        scored = [r for r in good if r["moment"]] if arm == "organic" else good
        fired = [r for r in scored if hit(r)]
        label = ("organic  (neutral prompt; moment must arise during the work)"
                 if arm == "organic"
                 else "control  (same world; moment described in the prompt)")
        print("%s" % label)
        if arm == "organic":
            print("  moment reached in %d/%d completed replicates" % (len(scored), len(good)))
        print("  %s fired in %d/%d scored replicates" % (skill, len(fired), len(scored)))
        others = sorted({f for r in scored for f in r.get("fired", []) if not hit(r)})
        if others:
            print("  competitors seen: %s" % ", ".join(others))
        for r in errors:
            print("  ERROR #%d: %s" % (r["index"], r["error"]))
            ok = False
        if arm == "organic" and len(scored) < len(good):
            print("  NOTE: replicates that never reached the moment are excluded, not"
                  " counted as misses.")
        if not scored:
            print("  NOTHING WAS MEASURED for this arm.")
            ok = False
        print()

    print("Read the two numbers together. A control that fires and an organic arm that\n"
          "does not is the finding this script exists to produce: the skill owns the\n"
          "words, not the moment. Neither number is a pass/fail gate -- do not pin one\n"
          "into a `## Trigger precision` section, which is defined over user prompts.\n"
          "'Did not fire' is not 'did the wrong thing'; this measures routing only.")
    return ok


def main(argv):
    if os.environ.get(GATE) != "1":
        print(__doc__, file=sys.stderr)
        print("REFUSING TO RUN: set %s=1 to spend real quota on long agentic sessions."
              % GATE, file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("scenario", nargs="?", default="stale_install",
                        choices=sorted(SCENARIOS))
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--json")
    args = parser.parse_args(argv[1:])

    version = cli_version()
    results = probe(args.scenario, args.n)
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"scenario": args.scenario, "skill": SCENARIOS[args.scenario]["skill"],
             "model": MODEL, "cli": version, "results": results}, indent=2))
    return 0 if report(args.scenario, results, version) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
