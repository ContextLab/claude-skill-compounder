#!/usr/bin/env python3
"""Run every routing claim for real and report which ones are true.

This is the only thing in the repository that verifies a `## Trigger precision`
section. `scripts/routing_claims.py` checks that the claims are pinned to the
description and prompt list they were measured against; it cannot check whether they
are true, and no static rule can (see `routing_claims.limits()`).

GATE
    Refuses to run unless SKILL_ROUTING_PROBE=1 is set. It spends real quota and needs
    a working `claude` login, so it must never fire from `./run_tests.sh` or CI by
    accident.

COST (measured 2026-08-25)
    One `claude -p --model sonnet --max-turns 3` per prompt, 30-90s each, six in
    parallel. Eight skills x six prompts is ~48 calls and ~15 minutes.

MODEL
    `--model sonnet`, always. Personal and project skill descriptions were measured
    ABSENT from the router on haiku, so a haiku probe proves nothing about routing.
    The model is not a flag on this script for that reason.

WHAT IT CANNOT SEE
    It measures the router as installed on THIS machine, at THIS moment: the skills in
    ~/.claude/skills, every plugin's skills, and the CLI's own bundled ones. A claim
    here already went false because a skill in a DIFFERENT package won a prompt away
    from ours. Nothing in this repository can predict that day. Re-running this is the
    only detection, which is why the pin records a date and a CLI version.

Usage:
    SKILL_ROUTING_PROBE=1 python3 scripts/probe_routing_claims.py            # all skills
    SKILL_ROUTING_PROBE=1 python3 scripts/probe_routing_claims.py session-handoff
    SKILL_ROUTING_PROBE=1 python3 scripts/probe_routing_claims.py --json out.json
"""

import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import routing_claims as rc  # noqa: E402

GATE = "SKILL_ROUTING_PROBE"
MODEL = "sonnet"
MAX_TURNS = "3"
PER_PROMPT_TIMEOUT = int(os.environ.get("SKILL_ROUTING_PROBE_TIMEOUT", "240"))
PARALLEL = int(os.environ.get("SKILL_ROUTING_PROBE_PARALLEL", "6"))


def cli_version():
    out = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL, timeout=60)
    return out.stdout.strip() or "unknown"


def skills_fired(stream):
    """Every skill named by a `Skill` tool call, in order.

    The Skill tool's argument has been spelled `skill`, `command`, and `name` across
    versions, so take whichever string field is present rather than pinning one.
    """
    fired = []
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
            if block.get("type") != "tool_use" or block.get("name") != "Skill":
                continue
            args = block.get("input") or {}
            for key in ("skill", "command", "name", "skill_name"):
                value = args.get(key)
                if isinstance(value, str) and value:
                    fired.append(value)
                    break
            else:
                fired.append("Skill(<unparsed args: %s>)" % ",".join(sorted(args)))
    return fired


def run_prompt(prompt):
    """One real session in an empty directory. Returns (fired, error)."""
    # Manual cleanup, ignoring errors: a probed session writes real files into its cwd
    # and can still be flushing them as the context manager unlinks, which raised
    # `Directory not empty` and lost an otherwise-valid measurement.
    cwd = tempfile.mkdtemp(prefix="routing-probe-")
    try:
        cmd = ["claude", "-p", "--model", MODEL, "--max-turns", MAX_TURNS,
               "--output-format", "stream-json", "--verbose", prompt]
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                  stdin=subprocess.DEVNULL,
                                  timeout=PER_PROMPT_TIMEOUT)
        except subprocess.TimeoutExpired:
            return [], "timed out after %ds" % PER_PROMPT_TIMEOUT
        fired = skills_fired(proc.stdout)
        # A non-zero exit is NOT an error here. `--max-turns` exhaustion and a denied
        # permission both exit 1, and both happen AFTER the routing decision, which is
        # taken in the first assistant turn. Discarding those runs threw away a correct
        # must-not-fire measurement on the first real call made against this script.
        if not any('"type":"assistant"' in line or '"type": "assistant"' in line
                   for line in proc.stdout.splitlines()):
            return [], ("claude produced no assistant turn (exit %d): %s"
                        % (proc.returncode, (proc.stderr or "").strip()[:200]))
        return fired, None
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def probe(claims_list):
    jobs = []
    for claims in claims_list:
        if not claims["section"]:
            continue
        for prompt in claims["must_fire"]:
            jobs.append((claims["name"], "must-fire", prompt))
        for prompt in claims["must_not_fire"]:
            jobs.append((claims["name"], "must-not-fire", prompt))

    results = []
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futures = {pool.submit(run_prompt, job[2]): job for job in jobs}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            name, kind, prompt = futures[future]
            fired, error = future.result()
            hit = any(f == name or f.endswith("/" + name) or f.endswith(":" + name)
                      for f in fired)
            ok = (hit if kind == "must-fire" else not hit) and error is None
            results.append({"skill": name, "kind": kind, "prompt": prompt,
                            "fired": fired, "error": error, "pass": ok})
            done += 1
            print("  [%2d/%2d] %-5s %-26s %s"
                  % (done, len(jobs), "PASS" if ok else "FAIL", name, prompt[:60]),
                  file=sys.stderr)
    print("  %d prompts in %.0fs" % (len(jobs), time.time() - started), file=sys.stderr)
    return results


def report(results, version):
    by_skill = {}
    for r in results:
        by_skill.setdefault(r["skill"], []).append(r)
    print("\nrouting probe  model=%s  cli=%s\n" % (MODEL, version))
    clean = []
    for name in sorted(by_skill):
        rows = by_skill[name]
        fire = [r for r in rows if r["kind"] == "must-fire"]
        notfire = [r for r in rows if r["kind"] == "must-not-fire"]
        okf = sum(r["pass"] for r in fire)
        okn = sum(r["pass"] for r in notfire)
        print("%s  %d/%d must-fire, %d/%d must-not-fire"
              % (name, okf, len(fire), okn, len(notfire)))
        for r in rows:
            if r["pass"]:
                continue
            if r["error"]:
                print("    ERROR  %-13s %s\n           -> %s"
                      % (r["kind"], r["prompt"], r["error"]))
            elif r["kind"] == "must-fire":
                print("    FALSE  must-fire     %s\n           -> fired %s"
                      % (r["prompt"], r["fired"] or "nothing at all"))
            else:
                print("    FALSE  must-not-fire %s\n           -> fired %s"
                      % (r["prompt"], r["fired"]))
        if okf == len(fire) and okn == len(notfire) and fire and notfire:
            clean.append((name, len(fire), len(notfire)))
    if clean:
        print("\nPins to write for the clean sections (date them today):")
        for name, nf, nn in clean:
            print("  %s -> measured: <today>  cli: %s  model: %s\n"
                  "     result: verified %d/%d must-fire, %d/%d must-not-fire"
                  % (name, version, MODEL, nf, nf, nn, nn))
        print("  Refresh the two hashes with: python3 scripts/routing_claims.py pin <skill>")
    print("\nA section with any FALSE row above is not repairable by editing the pin.\n"
          "Delete or rewrite the false claim, then probe it again.")
    return all(r["pass"] for r in results)


def main(argv):
    if os.environ.get(GATE) != "1":
        print(__doc__, file=sys.stderr)
        print("REFUSING TO RUN: set %s=1 to spend real quota on ~48 `claude -p` calls."
              % GATE, file=sys.stderr)
        return 2
    args = [a for a in argv[1:] if not a.startswith("--")]
    out_json = None
    if "--json" in argv[1:]:
        idx = argv.index("--json")
        out_json = argv[idx + 1]
        args = [a for a in args if a != out_json]
    claims_list = rc.all_skills()
    if args:
        wanted = set(args)
        claims_list = [c for c in claims_list if c["name"] in wanted]
        missing = wanted - {c["name"] for c in claims_list}
        if missing:
            print("no such skill(s): %s" % ", ".join(sorted(missing)), file=sys.stderr)
            return 2
    version = cli_version()
    results = probe(claims_list)
    if out_json:
        Path(out_json).write_text(json.dumps(
            {"model": MODEL, "cli": version, "results": results}, indent=2))
    return 0 if report(results, version) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
