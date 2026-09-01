#!/usr/bin/env python3
"""Run every routing claim for real, N times each, and report k/N per prompt.

This is the only thing in the repository that verifies a `## Trigger precision`
section. `scripts/routing_claims.py` checks that the claims are pinned to the
description and prompt list they were measured against; it cannot check whether they
are true, and no static rule can (see `routing_claims.limits()`).

ONE RUN IS ONE DRAW
    Routing here is stochastic. One unchanged description, probed three times, gave
    3/3, then 1/3, then 2/3, with no edit anywhere between the runs. A single sample
    therefore reports a draw as though it were a property, and its date cannot separate
    a real regression -- a plugin installed nearby changed the field -- from the same
    variance landing differently.

    N=3 does not cure that; it makes it visible. `skill-compounder`'s own six prompts,
    probed three separate times on 2026-08-26 with nothing edited between, scored 9/9,
    then 8/9, then 9/9. So three runs is a floor for DETECTING spread, not a score that
    earns `verified`, and a prompt seen at 2/3 has not passed -- it has been shown
    unreliable, and a later clean pass does not un-show it.

    So every prompt is submitted `--runs N` times (default 3, `SKILL_ROUTING_PROBE_RUNS`)
    and folded into a k/N count by `aggregate()`:

        k == N   PASS   every draw won
        0 < k < N SPLIT  the claim is flaky. This is a finding, not a failure: it is
                         reported, named, and pinned as `partial`. Re-running until a
                         green appears certifies the draw, not the claim.
        k == 0   FAIL    the claim is false.

    A section is `verified` only when every prompt won every draw; anything else is
    `partial`. A non-zero exit means "not verified", which includes "flaky".

GATE
    Refuses to run unless SKILL_ROUTING_PROBE=1 is set. It spends real quota and needs
    a working `claude` login, so it must never fire from `./run_tests.sh` or CI by
    accident.

COST (re-measured 2026-08-26, CLI 2.1.245)
    One `claude -p --model sonnet --max-turns 3` per draw, six at a time
    (`SKILL_ROUTING_PROBE_PARALLEL`). A CALL IS ONE PROMPT IN ONE DRAW, so every call
    count here is arithmetic: `len(prompts_for(claims)) * runs`, nothing else.
    `tests/test_routing_gate.py` now derives the figure that way instead of reading it
    out of this paragraph -- this paragraph agreeing with the protocol is precisely how
    a one-run cost survived the move to `--runs 3` in both files at once.

    Quote the cost at the N the gate demands, not at one run. One skill is 6 prompts:
    18 calls at `--runs 3`. The twelve pinned skills are 72 prompts: 72 calls per run
    and 216 calls at three.

    Per draw, off the `seconds` field this script writes for every draw into `--json`:
    over a WHOLE 216-draw `--runs 3` pass of all twelve sections, 2026-09-01 at CLI
    2.1.252, 7-76s per draw, median 23s, and 924s (~15.4 minutes) wall clock, six at once.
    That is the gate measured end to end rather than scaled from one section, which is
    what the previous figure here was. Treat wall clock as an order of magnitude and
    never as a figure to check: two 18-draw passes of the same six prompts on one day
    took 86s and 74s. Draws in which some skill fired ran slower than draws in which none
    did -- median 24s against 18s over those 180 -- so a section is dearer than its call
    count alone suggests. The "~15 minutes" this docstring and `SKILL.md` both carried
    until 2026-08-26 was one run's figure, never re-derived after the gate went to three
    runs; the 8-47s/median-22s spread that replaced it was one section's 18 draws.

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
    SKILL_ROUTING_PROBE=1 python3 scripts/probe_routing_claims.py --runs 5 session-handoff
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
# The floor the forging protocol states, and the reason it is not 1: two draws can
# disagree but cannot say which way, and the observed spread (3/3, 1/3, 2/3) is wide
# enough that one draw is close to uninformative.
MIN_RUNS = 3
RUNS = int(os.environ.get("SKILL_ROUTING_PROBE_RUNS", str(MIN_RUNS)))


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
    """One real session in an empty directory. Returns (fired, error, seconds)."""
    # Manual cleanup, ignoring errors: a probed session writes real files into its cwd
    # and can still be flushing them as the context manager unlinks, which raised
    # `Directory not empty` and lost an otherwise-valid measurement.
    cwd = tempfile.mkdtemp(prefix="routing-probe-")
    started = time.time()
    try:
        cmd = ["claude", "-p", "--model", MODEL, "--max-turns", MAX_TURNS,
               "--output-format", "stream-json", "--verbose", prompt]
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                  stdin=subprocess.DEVNULL,
                                  timeout=PER_PROMPT_TIMEOUT)
        except subprocess.TimeoutExpired:
            return [], "timed out after %ds" % PER_PROMPT_TIMEOUT, time.time() - started
        fired = skills_fired(proc.stdout)
        # A non-zero exit is NOT an error here. `--max-turns` exhaustion and a denied
        # permission both exit 1, and both happen AFTER the routing decision, which is
        # taken in the first assistant turn. Discarding those runs threw away a correct
        # must-not-fire measurement on the first real call made against this script.
        if not any('"type":"assistant"' in line or '"type": "assistant"' in line
                   for line in proc.stdout.splitlines()):
            return [], ("claude produced no assistant turn (exit %d): %s"
                        % (proc.returncode, (proc.stderr or "").strip()[:200])), \
                time.time() - started
        return fired, None, time.time() - started
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def won(skill, kind, fired, error):
    """Did this one draw go the way the claim says it should?

    A skill is `fired` under its bare name or under any package qualification of it,
    because the same skill is reachable as `x`, `pkg:x` and `pkg/x`.
    """
    if error is not None:
        return False
    hit = any(f == skill or f.endswith("/" + skill) or f.endswith(":" + skill)
              for f in fired)
    return hit if kind == "must-fire" else not hit


def aggregate(draws):
    """Fold per-draw rows into one k/N row per (skill, kind, prompt).

    Kept pure and separate from `probe()` because this is the only place a verdict is
    decided. Two defects shipped in this repository as guards that never executed --
    a `wc -c` value read as non-numeric, a basic-regex `grep` alternation whose bar was
    literal -- and both looked correct. This function can be exercised on recorded
    draws, with a draw deliberately flipped, without spending a call. Do that rather
    than trusting the output because it looks plausible.
    """
    order, by_key = [], {}
    for d in draws:
        key = (d["skill"], d["kind"], d["prompt"])
        if key not in by_key:
            by_key[key] = []
            order.append(key)
        by_key[key].append(d)
    out = []
    for key in order:
        rows = sorted(by_key[key], key=lambda r: r["draw"])
        n = len(rows)
        wins = sum(1 for r in rows if r["win"])
        out.append({
            "skill": key[0], "kind": key[1], "prompt": key[2],
            "runs": n, "wins": wins,
            "pass": n > 0 and wins == n,
            "split": 0 < wins < n,
            "errors": [r["error"] for r in rows if r["error"]],
            "fired": [r["fired"] for r in rows],
            "draws": rows,
        })
    return out


def verdict(row):
    if row["pass"]:
        return "PASS"
    if row["split"]:
        return "SPLIT"
    return "FAIL"


def prompts_for(claims_list):
    """Every (skill, kind, prompt) triple a section claims. The aggregation key."""
    prompts = []
    for claims in claims_list:
        if not claims["section"]:
            continue
        for prompt in claims["must_fire"]:
            prompts.append((claims["name"], "must-fire", prompt))
        for prompt in claims["must_not_fire"]:
            prompts.append((claims["name"], "must-not-fire", prompt))
    return prompts


def jobs_for(claims_list, runs):
    """One job per (skill, kind, prompt) PER DRAW -- the whole point of `--runs`.

    Draw-major, not prompt-major: a whole run completes before the next begins, so an
    interrupted probe leaves entire runs rather than a ragged N that aggregate() would
    score against different denominators per prompt.

    Pure, so `tests/test_routing_claims.py` can prove the fan-out is N-fold by counting
    it rather than by trusting that 3 was passed somewhere.
    """
    if runs < 1:
        raise ValueError("runs must be >= 1, got %r" % runs)
    prompts = prompts_for(claims_list)
    return [(name, kind, prompt, draw)
            for draw in range(runs)
            for (name, kind, prompt) in prompts]


def probe(claims_list, runs=None):
    """Submit every prompt `runs` times and return the aggregated k/N rows.

    The per-draw rows survive on each row's `draws` key, so a surprise is diagnosable
    from `--json` without re-spending quota.
    """
    runs = RUNS if runs is None else runs
    jobs = jobs_for(claims_list, runs)
    prompts = prompts_for(claims_list)

    if runs < MIN_RUNS:
        print("  NOTE: --runs %d is below the stated floor of %d. The result is a draw, "
              "not a verdict." % (runs, MIN_RUNS), file=sys.stderr)
    draws = []
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futures = {pool.submit(run_prompt, job[2]): job for job in jobs}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            name, kind, prompt, draw = futures[future]
            fired, error, seconds = future.result()
            ok = won(name, kind, fired, error)
            draws.append({"skill": name, "kind": kind, "prompt": prompt,
                          "draw": draw, "win": ok, "fired": fired, "error": error,
                          "seconds": round(seconds, 1)})
            done += 1
            print("  [%3d/%3d] draw %d/%d %-4s %-26s %s"
                  % (done, len(jobs), draw + 1, runs, "WON" if ok else "LOST",
                     name, prompt[:52]),
                  file=sys.stderr)
    elapsed = time.time() - started
    per_draw = sorted(d["seconds"] for d in draws)
    print("  %d prompts x %d runs = %d draws in %.0fs (per draw: min %.0fs, median "
          "%.0fs, max %.0fs)"
          % (len(prompts), runs, len(draws), elapsed,
             per_draw[0] if per_draw else 0,
             per_draw[len(per_draw) // 2] if per_draw else 0,
             per_draw[-1] if per_draw else 0),
          file=sys.stderr)
    return aggregate(draws)


def pin_result(rows, runs):
    """The one-line `result:` value for a section. `verified` demands every draw."""
    fire = [r for r in rows if r["kind"] == "must-fire"]
    notfire = [r for r in rows if r["kind"] == "must-not-fire"]
    wf, nf = sum(r["wins"] for r in fire), sum(r["runs"] for r in fire)
    wn, nn = sum(r["wins"] for r in notfire), sum(r["runs"] for r in notfire)
    counts = ("%d/%d must-fire draws, %d/%d must-not-fire draws" % (wf, nf, wn, nn))
    if all(r["pass"] for r in rows):
        return "verified %s (%d/%d each prompt over %d runs)" % (counts, runs, runs, runs)
    # THE WHOLE PROMPT, never a prefix. `[:60]` truncated it, and
    # `tests/test_routing_gate.py` requires the quoted text to match a prompt that is
    # actually in the section -- so for any prompt longer than 60 characters this
    # function emitted a pin the repository's own gate rejects, and every `partial` pin
    # that ever shipped had to be written by hand instead. Quoted plainly rather than
    # with %r, because repr escapes an apostrophe and the gate matches literally.
    flaky = ["'%s' %d/%d" % (r["prompt"], r["wins"], r["runs"])
             for r in rows if not r["pass"]]
    return "partial %s over %d runs; not clean: %s" % (counts, runs, "; ".join(flaky))


def report(results, version, runs=None):
    """Print the k/N table and the pin block to write. True only when every draw won."""
    if runs is None:
        runs = max([r["runs"] for r in results], default=0)
    by_skill = {}
    for r in results:
        by_skill.setdefault(r["skill"], []).append(r)
    print("\nrouting probe  model=%s  cli=%s  runs=%d\n" % (MODEL, version, runs))
    for name in sorted(by_skill):
        rows = by_skill[name]
        fire = [r for r in rows if r["kind"] == "must-fire"]
        notfire = [r for r in rows if r["kind"] == "must-not-fire"]
        print("%s  %d/%d must-fire draws, %d/%d must-not-fire draws"
              % (name,
                 sum(r["wins"] for r in fire), sum(r["runs"] for r in fire),
                 sum(r["wins"] for r in notfire), sum(r["runs"] for r in notfire)))
        for r in rows:
            if r["pass"]:
                continue
            print("    %-5s %-13s %d/%d  %s"
                  % (verdict(r), r["kind"], r["wins"], r["runs"], r["prompt"]))
            for d in r["draws"]:
                if d["win"]:
                    continue
                what = d["error"] or ("fired %s" % (d["fired"] or "nothing at all"))
                print("             draw %d: %s" % (d["draw"] + 1, what))
        print("    pin: measured: <today>  cli: %s  model: %s  runs: %d\n"
              "         result: %s"
              % (version, MODEL, runs, pin_result(rows, runs)))
    print("  Refresh the two hashes with: python3 scripts/routing_claims.py pin <skill>")
    print("\nA SPLIT is information, not a failure: the claim is flaky and `partial` is\n"
          "the honest pin for it. What is forbidden is re-running until a green appears\n"
          "and pinning that -- it certifies the draw, not the claim. A SPLIT or a FAIL is\n"
          "repaired by editing the DESCRIPTION and measuring the whole section again,\n"
          "never by editing the pin or deleting the prompt.")
    return all(r["pass"] for r in results)


def parse_args(argv):
    """Returns (skills, out_json, runs). Unknown flags are an error, not a skill name.

    Hand-rolled because the value of `--runs` does not start with `--` and the previous
    `[a for a in argv if not a.startswith("--")]` filter would have taken it for one.
    """
    skills, out_json, runs = [], None, RUNS
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            i += 1
            if i >= len(argv):
                raise ValueError("--json needs a path")
            out_json = argv[i]
        elif arg == "--runs":
            i += 1
            if i >= len(argv):
                raise ValueError("--runs needs a count")
            try:
                runs = int(argv[i])
            except ValueError:
                raise ValueError("--runs takes an integer, got %r" % argv[i])
            if runs < 1:
                raise ValueError("--runs must be at least 1, got %d" % runs)
        elif arg.startswith("-"):
            raise ValueError("unknown flag %r" % arg)
        else:
            skills.append(arg)
        i += 1
    return skills, out_json, runs


def main(argv):
    if os.environ.get(GATE) != "1":
        print(__doc__, file=sys.stderr)
        # DERIVED, never restated. A hardcoded 48 here outlived two prompt additions
        # and disagreed with the docstring above it; a call is one prompt in one draw,
        # so the only honest source is the prompt list that exists right now.
        per_run = len(prompts_for(rc.all_skills()))
        print("REFUSING TO RUN: set %s=1 to spend real quota on %d `claude -p` calls "
              "per run, x%d runs by default (%d calls)."
              % (GATE, per_run, RUNS, per_run * RUNS), file=sys.stderr)
        return 2
    try:
        args, out_json, runs = parse_args(argv[1:])
    except ValueError as exc:
        print("%s\n\n%s" % (exc, __doc__), file=sys.stderr)
        return 2
    claims_list = rc.all_skills()
    if args:
        wanted = set(args)
        claims_list = [c for c in claims_list if c["name"] in wanted]
        missing = wanted - {c["name"] for c in claims_list}
        if missing:
            print("no such skill(s): %s" % ", ".join(sorted(missing)), file=sys.stderr)
            return 2
    version = cli_version()
    results = probe(claims_list, runs=runs)
    if out_json:
        Path(out_json).write_text(json.dumps(
            {"model": MODEL, "cli": version, "runs": runs,
             "results": results,
             # Flat per-draw rows as well as the nested ones, so a surprise can be
             # grepped and re-aggregated without walking the tree.
             "draws": [d for r in results for d in r["draws"]]}, indent=2))
    return 0 if report(results, version, runs) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
