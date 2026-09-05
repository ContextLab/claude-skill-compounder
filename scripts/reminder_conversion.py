#!/usr/bin/env python3
"""Re-derive the nudge-to-output conversion rate from your own Claude Code transcripts.

Issue #30 recorded "10.5% of nudged sessions invoke skill-compounder" as a one-off sweep
whose method lived only in a notes file. This is that sweep as a program, so the figure is
re-derivable rather than quoted. It reads transcripts and two local state files, prints
every figure as numerator/denominator, and writes nothing.

    python3 scripts/reminder_conversion.py                    # overall + per project
    python3 scripts/reminder_conversion.py --since 2026-09-02 # post-tier window
    python3 scripts/reminder_conversion.py --until 2026-09-02 # pre-tier window
    python3 scripts/reminder_conversion.py --json
    python3 scripts/reminder_conversion.py --selftest         # fixture, asserts counts

stdlib only, python3. Nothing here makes a network call and nothing here writes to your
transcripts, your state directory or the repository.

--------------------------------------------------------------------- THE MATCH RULES

Each rule below was settled by reading real records out of this machine's store, not from
the hook's source, because the store holds records written by every version of the hook
that has ever run. The census that settled them classified every delivered
`[skill-compounder]` string on this machine into the four kinds below with zero unknowns
(1499 of 1499, 2026-09-04); run with `--json` for the current census.

1. A NUDGE DELIVERY is a transcript record whose `.attachment.type` is
   `"hook_additional_context"` and whose `.attachment.content[]` holds a string containing
   `[skill-compounder]`.

   Why that record and not `hook_success`: Claude Code writes TWO records for one
   `PostToolUse` delivery -- a `hook_success` carrying the hook's argv and raw stdout, and a
   `hook_additional_context` carrying the text that actually reached the model -- but for
   `UserPromptSubmit` it writes only the second. Measured on this store on 2026-09-04:
   1271 prompt-arm deliveries appear as `hook_additional_context` and 0 as `hook_success`,
   and the second figure is the load-bearing one rather than the first. Keying on
   `hook_success` would silently drop the arm that fires most. `hook_additional_context` is
   also the stronger claim: it says the context was injected, not merely that a hook printed
   something.

   Why the text and not the hook's path: `hook_success.command` names
   `compound-improvement.sh`, and `hook_additional_context` carries no command at all, so a
   path rule cannot classify the arm that dominates. `[skill-compounder]` is unique to this
   hook -- `grep -ho '\[skill-[a-z-]*\]' hooks/*.sh` reports 5 hits, all in
   `hooks/compound-improvement.sh`.

   Why an `attachment` record and not any record containing the string: 8 assistant records
   and 7 user records on this store contain `[skill-compounder]` because somebody quoted a
   nudge back. Counting those would count a discussion of a nudge as a nudge.

2. THE KIND OF A NUDGE is read off the delivered text, because that is the only field the
   record carries that distinguishes the arms:

     checkpoint   contains "Checkpoint after "          (the edit checkpoint, ci-checkpoint)
     skill-check  contains "check whether an existing skill already solves this"
                                                        (the prompt nudge, ci-skill-check)
     prose        contains "is durable prose other people will read"          (ci-prose)
     queue        contains "skill-candidate queue has"                        (the queue announcement)

   The checkpoint text embeds a varying edit count and the prose text a varying basename, so
   both rules match on the invariant substring around them.

   THE DENOMINATOR IS checkpoint + skill-check AND NOT ALL FOUR. Those two are the arms that
   name `skill-compounder`; the prose arm points at `ai-tell-audit` and the queue arm at
   `skillinsight`, so folding them in would put sessions in the denominator that were never
   asked for the thing the numerator counts. All four are reported.

3. AN INVOCATION OF skill-compounder is an assistant `tool_use` block with `.name == "Skill"`
   whose `.input.skill` is `skill-compounder` (or `<plugin>:skill-compounder`), MINUS any
   whose `.id` appears as the `.tool_use_id` of a `tool_result` carrying `"is_error": true`.
   This is `bin/skillreport`'s rule, followed here so the two instruments cannot disagree:
   an attempt that came back `Unknown skill` is a failure, not a use.

4. AN INVOCATION OF A CHEAP TIER is a `tool_use` block with `.name == "Bash"` whose
   `.input.command` names `skillnote` or `skillinsight` IN COMMAND POSITION -- at the start
   of the string or after a shell separator, allowing leading VAR=value assignments and a
   leading path. A bare substring rule would count `grep -n skillnote bin/*` and this
   repository's own documentation as tier usage. The looser "named anywhere" count is
   reported beside it so the gap between the two rules is visible rather than assumed away.

5. A SESSION is `.sessionId`, and its PROJECT is the transcript's parent directory name --
   Claude Code's own slug for the working directory. Overall figures count distinct session
   ids; per-project figures count distinct (project, session) pairs, and the report prints
   both totals so a session that appears under two slugs is visible rather than silent.

6. HARNESS SESSIONS are reported separately, never dropped. A session any of whose records
   carries `.entrypoint == "sdk-cli"` was driven by a script -- `claude -p`, which is how
   this repository's own probes and end-to-end tests run. `bin/skillreport` excludes those
   from its reuse headline for the same reason. The headline here counts every session, so
   it stays comparable with the 10.5% baseline, and the human-driven figures are printed
   underneath it.

7. THE WINDOW is applied to EVENTS, not to sessions. `--since` / `--until` filter on the
   record's `.timestamp` (ISO-8601, `--since` inclusive, `--until` exclusive), so a session
   that was nudged before the window and invoked inside it is not counted as a conversion in
   that window. Records whose timestamp will not parse are counted and reported on their own
   line rather than being assigned to a window.

8. THE nudges.jsonl JOIN is by lineage id where an id exists on both sides, and the report
   says how many rows exist. `hooks/compound-improvement.sh` began logging a delivery id
   only on 2026-09-04, and a ledger row carries the id it descends from in `.from`, so the
   join is reported with both denominators rather than as a rate. Where no ledger row
   carries `.from`, that is stated as the reason the id join is empty, and the weaker
   session-level join (nudge `cc_session` against a ledger row's `.session`) is reported
   beside it, labelled as a sequence and not a cause.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

# ------------------------------------------------------------------ match rule constants

NUDGE_TAG = "[skill-compounder]"

# Ordered: the first rule that matches wins. Every substring here was verified present in a
# real delivered record on this machine's store.
NUDGE_KINDS = (
    ("checkpoint", "Checkpoint after "),
    ("skill-check", "check whether an existing skill already solves this"),
    ("prose", "is durable prose other people will read"),
    ("queue", "skill-candidate queue has"),
)

# The two arms that name skill-compounder. Rule 2.
COMPOUNDER_KINDS = ("checkpoint", "skill-check")

SKILL_NAME = "skill-compounder"

# Rule 4: command position is the start of the string or a shell separator, then any number
# of VAR=value assignments, then an optional path, then the CLI name as a whole word.
TIER_CMD_RE = re.compile(
    r"(?:^|[;|&\n(`]|\$\()\s*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=[^\s;|&]*\s+)*"
    r"(?:[^\s;|&()]*/)?"
    r"(skillnote|skillinsight)(?![\w./-])"
)
TIER_MENTION_RE = re.compile(r"(?<![\w./-])(skillnote|skillinsight)(?![\w-])")

# Cheap substring pre-filters. A line that holds none of these cannot carry anything this
# script counts, and skipping json.loads on it is what makes a 2.8 GB store scannable.
# `"Skill"` rather than `"name":"Skill"`, and `is_error` rather than `"is_error":true`:
# real transcripts are compact JSON and the fixture below is not, and a hint that assumes
# one spelling passes the live store while silently counting nothing on a fixture.
LINE_HINTS = (NUDGE_TAG, '"Skill"', "is_error", "skillnote", "skillinsight")

TIER_LANDED = "2026-09-02"  # bin/skillnote and hooks/remind.sh shipped; v0.3.0 tagged 09-03
NUDGE_ID_LOGGING_BEGAN = "2026-09-04"  # log_nudge landed; nothing before this carries an id


# ----------------------------------------------------------------------------- utilities


def parse_day(s: str) -> float:
    """YYYY-MM-DD -> epoch seconds at UTC midnight."""
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def parse_iso(ts: str):
    """Claude Code writes '2026-08-28T03:56:20.803Z'. Returns epoch seconds or None."""
    if not isinstance(ts, str) or not ts:
        return None
    t = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
    try:
        return datetime.fromisoformat(t).timestamp()
    except ValueError:
        return None


def frac(n: int, d: int) -> str:
    if d <= 0:
        return "%d/%d (not computable, denominator is 0)" % (n, d)
    return "%d/%d (%.1f%%)" % (n, d, 100.0 * n / d)


def frac_json(n: int, d: int) -> dict:
    return {"n": n, "d": d, "pct": (100.0 * n / d) if d > 0 else None}


def texts_of(attachment: dict):
    c = attachment.get("content")
    if isinstance(c, list):
        return [x for x in c if isinstance(x, str)]
    if isinstance(c, str):
        return [c]
    return []


def kind_of(text: str):
    for name, needle in NUDGE_KINDS:
        if needle in text:
            return name
    return None


def blocks_of(rec: dict):
    msg = rec.get("message")
    if not isinstance(msg, dict):
        return []
    content = msg.get("content")
    return content if isinstance(content, list) else []


# ------------------------------------------------------------------------------- the sweep


class Sweep:
    """One pass over the transcript store, accumulating per-session facts."""

    def __init__(self, since=None, until=None):
        self.since = since
        self.until = until
        self.files = 0
        self.unparsed_lines = 0
        self.undated_records = 0
        # session -> set(project slug); session -> set(entrypoint)
        self.projects = collections.defaultdict(set)
        self.entrypoints = collections.defaultdict(set)
        # (session, kind) delivery counts and session sets
        self.deliveries = collections.Counter()
        self.proj_deliveries = collections.Counter()  # (project, kind) -> deliveries
        self.nudged = collections.defaultdict(set)  # kind -> {session}
        self.invoked = set()  # sessions that invoked skill-compounder (ok)
        self.invoked_failed = set()  # sessions whose only attempts errored
        self.tier_cmd = collections.defaultdict(set)  # cli -> {session}
        self.tier_mention = collections.defaultdict(set)
        self.err_ids = set()
        self._pending_skill = []  # (tool_use_id, session, ts) awaiting the error-id set
        self.session_files = collections.Counter()

    def in_window(self, ts):
        if ts is None:
            self.undated_records += 1
            return False
        if self.since is not None and ts < self.since:
            return False
        if self.until is not None and ts >= self.until:
            return False
        return True

    def scan(self, projects_dir: str):
        for slug in sorted(os.listdir(projects_dir)):
            d = os.path.join(projects_dir, slug)
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                if not name.endswith(".jsonl"):
                    continue
                self.files += 1
                self._scan_file(os.path.join(d, name), slug)
        # Rule 3: an attempt is not a use. The error ids are pooled across the whole store
        # because ids are unique tokens and a resumed session copies records verbatim.
        for tid, sid, _ts in self._pending_skill:
            if tid and tid in self.err_ids:
                self.invoked_failed.add(sid)
            else:
                self.invoked.add(sid)
        return self

    def _scan_file(self, path, slug):
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            return
        with fh:
            for line in fh:
                if not any(h in line for h in LINE_HINTS):
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    self.unparsed_lines += 1
                    continue
                if not isinstance(rec, dict):
                    continue
                sid = rec.get("sessionId") or ""
                ts = parse_iso(rec.get("timestamp") or "")
                self._record(rec, sid, ts, slug)

    def _record(self, rec, sid, ts, slug):
        att = rec.get("attachment")
        if isinstance(att, dict) and att.get("type") == "hook_additional_context":
            for text in texts_of(att):
                i = text.find(NUDGE_TAG)
                if i < 0:
                    continue
                kind = kind_of(text[i:])
                if kind is None:
                    kind = "unclassified"
                if not self.in_window(ts):
                    continue
                self._note_session(sid, slug, rec)
                self.deliveries[kind] += 1
                self.proj_deliveries[(slug, kind)] += 1
                self.nudged[kind].add(sid)
            return

        # Error ids are collected regardless of window: an attempt's result may land on the
        # far side of a window boundary from the attempt, and the set is only ever used to
        # subtract.
        for b in blocks_of(rec):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_result" and b.get("is_error") is True:
                tid = b.get("tool_use_id")
                if isinstance(tid, str) and tid:
                    self.err_ids.add(tid)
                continue
            if b.get("type") != "tool_use":
                continue
            name = b.get("name")
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            if name == "Skill":
                skill = inp.get("skill")
                if not isinstance(skill, str):
                    continue
                if skill != SKILL_NAME and not skill.endswith(":" + SKILL_NAME):
                    continue
                if not self.in_window(ts):
                    continue
                self._note_session(sid, slug, rec)
                self._pending_skill.append((b.get("id"), sid, ts))
            elif name == "Bash":
                cmd = inp.get("command")
                if not isinstance(cmd, str) or not cmd:
                    continue
                hits_m = set(m.group(1) for m in TIER_MENTION_RE.finditer(cmd))
                if not hits_m:
                    continue
                if not self.in_window(ts):
                    continue
                self._note_session(sid, slug, rec)
                for cli in hits_m:
                    self.tier_mention[cli].add(sid)
                for m in TIER_CMD_RE.finditer(cmd):
                    self.tier_cmd[m.group(1)].add(sid)

    def _note_session(self, sid, slug, rec):
        if not sid:
            return
        self.projects[sid].add(slug)
        ep = rec.get("entrypoint")
        if isinstance(ep, str) and ep:
            self.entrypoints[sid].add(ep)


# ------------------------------------------------------------------------------- reporting


def is_harness(sweep: Sweep, sid: str) -> bool:
    return "sdk-cli" in sweep.entrypoints.get(sid, set())


def cohort(sweep: Sweep, sessions, human_only: bool):
    if not human_only:
        return set(sessions)
    return set(s for s in sessions if not is_harness(sweep, s))


def build_report(sweep: Sweep, args) -> dict:
    nudged_all = set()
    for kind in COMPOUNDER_KINDS:
        nudged_all |= sweep.nudged.get(kind, set())
    any_nudged = set()
    for kind in sweep.nudged:
        any_nudged |= sweep.nudged[kind]

    tier_sessions = set()
    for cli in sweep.tier_cmd:
        tier_sessions |= sweep.tier_cmd[cli]
    tier_mention_sessions = set()
    for cli in sweep.tier_mention:
        tier_mention_sessions |= sweep.tier_mention[cli]

    out = {
        "corpus": {
            "projects_dir": args.projects_dir,
            "transcript_files": sweep.files,
            "unparsed_lines": sweep.unparsed_lines,
            "records_with_unusable_timestamp": sweep.undated_records,
            "since": args.since,
            "until": args.until,
        },
        "deliveries": dict(sweep.deliveries),
        "sessions_by_nudge_kind": {k: len(v) for k, v in sorted(sweep.nudged.items())},
        "cohorts": {},
        "per_project": [],
    }

    for label, human_only in (("all-sessions", False), ("human-driven", True)):
        nud = cohort(sweep, nudged_all, human_only)
        anyn = cohort(sweep, any_nudged, human_only)
        inv = cohort(sweep, sweep.invoked, human_only)
        invf = cohort(sweep, sweep.invoked_failed, human_only)
        tier = cohort(sweep, tier_sessions, human_only)
        tierm = cohort(sweep, tier_mention_sessions, human_only)
        note = cohort(sweep, sweep.tier_cmd.get("skillnote", set()), human_only)
        insight = cohort(sweep, sweep.tier_cmd.get("skillinsight", set()), human_only)
        any_out = inv | tier
        out["cohorts"][label] = {
            "nudged_sessions": len(nud),
            "nudged_sessions_any_arm": len(anyn),
            "sessions_invoking_skill_compounder": len(inv),
            "sessions_whose_skill_attempts_all_errored": len(invf),
            "sessions_running_skillnote": len(note),
            "sessions_running_skillinsight": len(insight),
            "sessions_running_either_tier_cli": len(tier),
            "sessions_naming_a_tier_cli_anywhere": len(tierm),
            "nudge_to_skill": frac_json(len(nud & inv), len(nud)),
            "nudge_to_tier_cli": frac_json(len(nud & tier), len(nud)),
            "nudge_to_any_output": frac_json(len(nud & any_out), len(nud)),
            "invoked_without_a_nudge": len(inv - nud),
        }

    # Per project. Rule 5: pairs, not sessions, and both totals are printed.
    proj_rows = []
    pair_total = 0
    for slug in sorted(set(s for sid in sweep.projects for s in sweep.projects[sid])):
        p_deliv = sum(v for (sl, k), v in sweep.proj_deliveries.items()
                      if sl == slug and k in COMPOUNDER_KINDS)
        p_nud = set(s for s in nudged_all if slug in sweep.projects.get(s, set()))
        p_inv = set(s for s in sweep.invoked if slug in sweep.projects.get(s, set()))
        p_tier = set(s for s in tier_sessions if slug in sweep.projects.get(s, set()))
        pair_total += len(p_nud)
        if not p_nud and not p_inv and not p_tier:
            continue
        proj_rows.append(
            {
                "project": slug,
                "deliveries": p_deliv,
                "nudged": len(p_nud),
                "invoked": len(p_inv),
                "both": len(p_nud & p_inv),
                "tier": len(p_tier),
                "nudge_to_skill": frac_json(len(p_nud & p_inv), len(p_nud)),
            }
        )
    proj_rows.sort(key=lambda r: (-r["nudged"], -r["invoked"], r["project"]))
    out["per_project"] = proj_rows
    out["corpus"]["nudged_project_session_pairs"] = pair_total
    out["corpus"]["nudged_distinct_sessions"] = len(nudged_all)
    return out


# ------------------------------------------------------------------ the nudges.jsonl join


def nudge_log_join(state_dir: str, since=None, until=None) -> dict:
    nudges_path = os.path.join(state_dir, "reminders", "nudges.jsonl")
    ledger_path = os.path.join(state_dir, "ledger.jsonl")
    res = {
        "nudges_path": nudges_path,
        "ledger_path": ledger_path,
        "nudges_exists": os.path.exists(nudges_path),
        "rows": 0,
        "rows_in_window": 0,
        "rows_by_kind": {},
        "rows_with_lineage_id": 0,
        "rows_unattributed": 0,
        "distinct_ids": 0,
        "first_ts": None,
        "last_ts": None,
        "ledger_rows": 0,
        "ledger_rows_with_from": 0,
        "id_join_matched_rows": 0,
        "session_join_nudged_sessions": 0,
        "session_join_sessions_with_a_ledger_row": 0,
    }
    rows = []
    if res["nudges_exists"]:
        with open(nudges_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    rows.append(r)
    res["rows"] = len(rows)
    kinds = collections.Counter()
    ids = set()
    ts_all = []
    sessions = set()
    for r in rows:
        ts = r.get("ts")
        if isinstance(ts, (int, float)):
            ts_all.append(ts)
            if since is not None and ts < since:
                continue
            if until is not None and ts >= until:
                continue
        res["rows_in_window"] += 1
        kinds[str(r.get("kind"))] += 1
        rid = r.get("id")
        if rid == "unattributed" or not rid:
            res["rows_unattributed"] += 1
        else:
            res["rows_with_lineage_id"] += 1
            ids.add(rid)
        for key in ("cc_session", "session"):
            v = r.get(key)
            if isinstance(v, str) and v:
                sessions.add(v)
    res["rows_by_kind"] = dict(sorted(kinds.items()))
    res["distinct_ids"] = len(ids)
    if ts_all:
        res["first_ts"] = min(ts_all)
        res["last_ts"] = max(ts_all)

    ledger_from = collections.Counter()
    ledger_sessions = set()
    if os.path.exists(ledger_path):
        with open(ledger_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                res["ledger_rows"] += 1
                frm = r.get("from")
                if isinstance(frm, str) and frm:
                    res["ledger_rows_with_from"] += 1
                    ledger_from[frm] += 1
                if r.get("event") in ("note", "start", "use", "apply", "verdict"):
                    s = r.get("session")
                    if isinstance(s, str) and s:
                        ledger_sessions.add(s)
    res["id_join_matched_rows"] = sum(v for k, v in ledger_from.items() if k in ids)
    res["session_join_nudged_sessions"] = len(sessions)
    res["session_join_sessions_with_a_ledger_row"] = len(sessions & ledger_sessions)
    return res


# ---------------------------------------------------------------------------- text output


def print_report(rep: dict, join: dict, args):
    w = sys.stdout.write
    bar = "-" * 78
    w("REMINDER CONVERSION SWEEP\n")
    w(bar + "\n")
    c = rep["corpus"]
    w("  transcripts:      %d file(s) under %s\n" % (c["transcript_files"], c["projects_dir"]))
    w("  window:           since=%s until=%s\n" % (c["since"] or "(none)", c["until"] or "(none)"))
    w("  unparsable lines: %d\n" % c["unparsed_lines"])
    w("  records whose timestamp would not parse (excluded from every window): %d\n"
      % c["records_with_unusable_timestamp"])

    w("\nNUDGE DELIVERIES BY ARM (a delivery is one injected context, rule 1)\n")
    if not rep["deliveries"]:
        w("  none in this window\n")
    for kind, n in sorted(rep["deliveries"].items(), key=lambda kv: -kv[1]):
        w("  %-14s %6d deliver(ies) in %d session(s)%s\n"
          % (kind, n, rep["sessions_by_nudge_kind"].get(kind, 0),
             "   <- in the denominator" if kind in COMPOUNDER_KINDS else ""))

    for label in ("all-sessions", "human-driven"):
        d = rep["cohorts"][label]
        w("\nCOHORT: %s\n" % label)
        if label == "human-driven":
            w("  (sessions with no record carrying entrypoint=sdk-cli; rule 6)\n")
        w("  nudged sessions (checkpoint or skill-check):   %d\n" % d["nudged_sessions"])
        w("  nudged sessions (any arm, incl. prose/queue):  %d\n" % d["nudged_sessions_any_arm"])
        w("  sessions invoking skill-compounder:            %d\n"
          % d["sessions_invoking_skill_compounder"])
        w("  sessions whose Skill attempts all errored:     %d\n"
          % d["sessions_whose_skill_attempts_all_errored"])
        w("  sessions running skillnote:                    %d\n" % d["sessions_running_skillnote"])
        w("  sessions running skillinsight:                 %d\n"
          % d["sessions_running_skillinsight"])
        w("  sessions naming either CLI anywhere (looser):  %d\n"
          % d["sessions_naming_a_tier_cli_anywhere"])
        w("  invoked skill-compounder with no nudge:        %d\n" % d["invoked_without_a_nudge"])
        for name, key in (
            ("nudge -> skill-compounder", "nudge_to_skill"),
            ("nudge -> skillnote|skillinsight", "nudge_to_tier_cli"),
            ("nudge -> any of the three", "nudge_to_any_output"),
        ):
            f = d[key]
            w("  %-34s %s\n" % (name + ":", frac(f["n"], f["d"])))

    w("\nPER PROJECT (rule 5: distinct (project, session) pairs)\n")
    w("  DELIVERIES counts injected contexts on the two counted arms; every other column\n"
      "  counts SESSIONS. The two units are both here because issue #30's per-project\n"
      "  figure was a delivery count and its overall figure was a session count.\n")
    rows = rep["per_project"]
    shown = rows[: args.per_project] if args.per_project > 0 else rows
    w("  %-46s %10s %7s %8s %5s %5s\n"
      % ("PROJECT", "DELIVERIES", "NUDGED", "INVOKED", "BOTH", "TIER"))
    for r in shown:
        w("  %-46s %10d %7d %8d %5d %5d\n"
          % (r["project"][:46], r["deliveries"], r["nudged"], r["invoked"], r["both"],
             r["tier"]))
    if len(rows) > len(shown):
        rest = rows[len(shown):]
        w("  %-46s %10d %7d %8d %5d %5d\n"
          % ("(+%d more project(s), counts included)" % len(rest),
             sum(r["deliveries"] for r in rest),
             sum(r["nudged"] for r in rest), sum(r["invoked"] for r in rest),
             sum(r["both"] for r in rest), sum(r["tier"] for r in rest)))
    w("  nudged (project, session) pairs: %d; nudged distinct sessions: %d\n"
      % (c["nudged_project_session_pairs"], c["nudged_distinct_sessions"]))

    w("\nNUDGE LOG JOIN (%s)\n" % join["nudges_path"])
    if not join["nudges_exists"]:
        w("  the log does not exist: 0 rows\n")
    else:
        w("  rows on disk:                    %d\n" % join["rows"])
        w("  rows in this window:             %d\n" % join["rows_in_window"])
        w("  by kind:                         %s\n"
          % (", ".join("%s=%d" % kv for kv in join["rows_by_kind"].items()) or "(none)"))
        w("  rows carrying a lineage id:      %s\n"
          % frac(join["rows_with_lineage_id"], join["rows_in_window"]))
        w("  distinct lineage ids:            %d\n" % join["distinct_ids"])
        if join["first_ts"]:
            w("  first / last row:                %s / %s\n"
              % (datetime.fromtimestamp(join["first_ts"], timezone.utc).isoformat(),
                 datetime.fromtimestamp(join["last_ts"], timezone.utc).isoformat()))
        w("  ledger rows:                     %d, of which carry .from: %d\n"
          % (join["ledger_rows"], join["ledger_rows_with_from"]))
        w("  id join (ledger .from in nudge ids): %s\n"
          % frac(join["id_join_matched_rows"], join["ledger_rows_with_from"]))
        if join["ledger_rows_with_from"] == 0:
            w("  the id join is empty because no ledger row carries .from yet, not because\n"
              "  no nudge id matched. Rule 8.\n")
        w("  session join (a sequence, never a cause): %s\n"
          % frac(join["session_join_sessions_with_a_ledger_row"],
                 join["session_join_nudged_sessions"]))
    w("\n")


# ------------------------------------------------------------------------------- selftest

FIXTURE_RECORDS = [
    # s1: nudged (checkpoint) and invoked -> a conversion.
    {"sessionId": "s1", "timestamp": "2026-09-03T10:00:00.000Z", "type": "attachment",
     "entrypoint": "cli", "attachment": {"type": "hook_additional_context", "content": [
         "[skill-compounder] Checkpoint after 12 file edits. (a) Have you fixed"]}},
    {"sessionId": "s1", "timestamp": "2026-09-03T10:00:01.000Z", "type": "attachment",
     "entrypoint": "cli", "attachment": {"type": "hook_success", "command": "x edit",
                                         "stdout": "[skill-compounder] Checkpoint after 12 file edits."}},
    {"sessionId": "s1", "timestamp": "2026-09-03T10:01:00.000Z", "type": "assistant",
     "entrypoint": "cli", "message": {"content": [
         {"type": "tool_use", "id": "t1", "name": "Skill",
          "input": {"skill": "skill-compounder"}}]}},
    # s2: nudged (skill-check), attempted the skill and it errored -> not a conversion.
    {"sessionId": "s2", "timestamp": "2026-09-03T11:00:00.000Z", "type": "attachment",
     "entrypoint": "cli", "attachment": {"type": "hook_additional_context", "content": [
         "[skill-compounder] Before starting implementation, check whether an existing "
         "skill already solves this"]}},
    {"sessionId": "s2", "timestamp": "2026-09-03T11:01:00.000Z", "type": "assistant",
     "entrypoint": "cli", "message": {"content": [
         {"type": "tool_use", "id": "t2", "name": "Skill",
          "input": {"skill": "skill-compounder"}}]}},
    {"sessionId": "s2", "timestamp": "2026-09-03T11:01:01.000Z", "type": "user",
     "entrypoint": "cli", "message": {"content": [
         {"type": "tool_result", "tool_use_id": "t2", "is_error": True,
          "content": "<tool_use_error>Unknown skill</tool_use_error>"}]}},
    # s3: nudged (skill-check), ran skillnote in command position -> a tier conversion.
    {"sessionId": "s3", "timestamp": "2026-09-03T12:00:00.000Z", "type": "attachment",
     "entrypoint": "cli", "attachment": {"type": "hook_additional_context", "content": [
         "[skill-compounder] Before starting implementation, check whether an existing "
         "skill already solves this"]}},
    {"sessionId": "s3", "timestamp": "2026-09-03T12:01:00.000Z", "type": "assistant",
     "entrypoint": "cli", "message": {"content": [
         {"type": "tool_use", "id": "t3", "name": "Bash",
          "input": {"command": "cd /x && skillnote add --scope project \"a line\""}}]}},
    # s4: nudged (prose only) -> not in the skill-compounder denominator at all.
    {"sessionId": "s4", "timestamp": "2026-09-03T13:00:00.000Z", "type": "attachment",
     "entrypoint": "cli", "attachment": {"type": "hook_additional_context", "content": [
         "[skill-compounder] README.md is durable prose other people will read."]}},
    # s5: harness session, nudged and invoked -> counted in all-sessions, not human-driven.
    {"sessionId": "s5", "timestamp": "2026-09-03T14:00:00.000Z", "type": "attachment",
     "entrypoint": "sdk-cli", "attachment": {"type": "hook_additional_context", "content": [
         "[skill-compounder] Checkpoint after 24 file edits."]}},
    {"sessionId": "s5", "timestamp": "2026-09-03T14:01:00.000Z", "type": "assistant",
     "entrypoint": "sdk-cli", "message": {"content": [
         {"type": "tool_use", "id": "t5", "name": "Skill",
          "input": {"skill": "skill-compounder"}}]}},
    # s6: nudged, and only MENTIONS skillnote inside a grep -> mention, never a tier run.
    {"sessionId": "s6", "timestamp": "2026-09-03T15:00:00.000Z", "type": "attachment",
     "entrypoint": "cli", "attachment": {"type": "hook_additional_context", "content": [
         "[skill-compounder] Checkpoint after 36 file edits."]}},
    {"sessionId": "s6", "timestamp": "2026-09-03T15:01:00.000Z", "type": "assistant",
     "entrypoint": "cli", "message": {"content": [
         {"type": "tool_use", "id": "t6", "name": "Bash",
          "input": {"command": "grep -rn skillnote bin/ | head"}}]}},
    # s7: an assistant QUOTING a nudge is not a delivery (rule 1, third paragraph).
    {"sessionId": "s7", "timestamp": "2026-09-03T16:00:00.000Z", "type": "assistant",
     "entrypoint": "cli", "message": {"content": [
         {"type": "text", "text": "the hook said [skill-compounder] Checkpoint after 12 "
                                  "file edits, which I disregarded"}]}},
    # s8: OUT OF THE POST-TIER WINDOW. Nudged and invoked before 2026-09-02.
    {"sessionId": "s8", "timestamp": "2026-08-20T09:00:00.000Z", "type": "attachment",
     "entrypoint": "cli", "attachment": {"type": "hook_additional_context", "content": [
         "[skill-compounder] Checkpoint after 12 file edits."]}},
    {"sessionId": "s8", "timestamp": "2026-08-20T09:05:00.000Z", "type": "assistant",
     "entrypoint": "cli", "message": {"content": [
         {"type": "tool_use", "id": "t8", "name": "Skill",
          "input": {"skill": "skill-compounder"}}]}},
]

# project slug -> the sessions whose records live under it
FIXTURE_LAYOUT = {"-proj-alpha": ["s1", "s2", "s3", "s4", "s7"],
                  "-proj-beta": ["s5", "s6", "s8"]}


def write_fixture(root: str) -> str:
    for slug, sessions in FIXTURE_LAYOUT.items():
        d = os.path.join(root, slug)
        os.makedirs(d, exist_ok=True)
        for s in sessions:
            recs = [r for r in FIXTURE_RECORDS if r["sessionId"] == s]
            with open(os.path.join(d, s + ".jsonl"), "w", encoding="utf-8") as fh:
                for r in recs:
                    # Compact, the way Claude Code writes them.
                    fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return root


def selftest() -> int:
    """Build a real fixture on disk, run the real sweep over it, assert the counts."""
    failures = []

    def check(label, got, want):
        if got != want:
            failures.append("%s: got %r, want %r" % (label, got, want))

    with tempfile.TemporaryDirectory(prefix="reminder-conversion-selftest-") as tmp:
        proj = write_fixture(os.path.join(tmp, "projects"))
        args = argparse.Namespace(projects_dir=proj, since=None, until=None, per_project=0)

        s = Sweep().scan(proj)
        rep = build_report(s, args)
        check("transcript files", rep["corpus"]["transcript_files"], 8)
        check("checkpoint deliveries", rep["deliveries"].get("checkpoint"), 4)
        check("skill-check deliveries", rep["deliveries"].get("skill-check"), 2)
        check("prose deliveries", rep["deliveries"].get("prose"), 1)
        check("unclassified deliveries", rep["deliveries"].get("unclassified"), None)

        a = rep["cohorts"]["all-sessions"]
        # s1 s2 s3 s5 s6 s8 were nudged on a compounder arm; s4 prose-only, s7 quote-only.
        check("nudged (all)", a["nudged_sessions"], 6)
        check("nudged any arm (all)", a["nudged_sessions_any_arm"], 7)
        # s1, s5, s8 invoked and succeeded; s2's only attempt errored.
        check("invoked (all)", a["sessions_invoking_skill_compounder"], 3)
        check("errored-only (all)", a["sessions_whose_skill_attempts_all_errored"], 1)
        check("nudge->skill n (all)", a["nudge_to_skill"]["n"], 3)
        check("nudge->skill d (all)", a["nudge_to_skill"]["d"], 6)
        # only s3 RAN skillnote; s6 merely named it.
        check("skillnote runs (all)", a["sessions_running_skillnote"], 1)
        check("named anywhere (all)", a["sessions_naming_a_tier_cli_anywhere"], 2)
        check("nudge->tier n (all)", a["nudge_to_tier_cli"]["n"], 1)
        check("nudge->any n (all)", a["nudge_to_any_output"]["n"], 4)

        h = rep["cohorts"]["human-driven"]
        check("nudged (human)", h["nudged_sessions"], 5)
        check("invoked (human)", h["sessions_invoking_skill_compounder"], 2)
        check("nudge->skill n (human)", h["nudge_to_skill"]["n"], 2)
        check("nudge->skill d (human)", h["nudge_to_skill"]["d"], 5)

        rows = {r["project"]: r for r in rep["per_project"]}
        check("alpha deliveries", rows["-proj-alpha"]["deliveries"], 3)
        check("beta deliveries", rows["-proj-beta"]["deliveries"], 3)
        check("alpha nudged", rows["-proj-alpha"]["nudged"], 3)
        check("alpha invoked", rows["-proj-alpha"]["invoked"], 1)
        check("beta nudged", rows["-proj-beta"]["nudged"], 3)
        check("beta invoked", rows["-proj-beta"]["invoked"], 2)

        # The window is applied to events (rule 7): s8's pair is entirely pre-tier.
        args2 = argparse.Namespace(projects_dir=proj, since=TIER_LANDED, until=None,
                                   per_project=0)
        s2 = Sweep(since=parse_day(TIER_LANDED)).scan(proj)
        rep2 = build_report(s2, args2)
        check("post-tier nudged", rep2["cohorts"]["all-sessions"]["nudged_sessions"], 5)
        check("post-tier invoked",
              rep2["cohorts"]["all-sessions"]["sessions_invoking_skill_compounder"], 2)
        args3 = argparse.Namespace(projects_dir=proj, since=None, until=TIER_LANDED,
                                   per_project=0)
        s3_ = Sweep(until=parse_day(TIER_LANDED)).scan(proj)
        rep3 = build_report(s3_, args3)
        check("pre-tier nudged", rep3["cohorts"]["all-sessions"]["nudged_sessions"], 1)
        check("pre-tier nudge->skill n",
              rep3["cohorts"]["all-sessions"]["nudge_to_skill"]["n"], 1)

        # An empty state directory must join to zeros rather than raising.
        j = nudge_log_join(os.path.join(tmp, "state"))
        check("empty state rows", j["rows"], 0)
        check("empty state exists", j["nudges_exists"], False)

        # A real state directory, written here, must be read back exactly.
        st = os.path.join(tmp, "state2")
        os.makedirs(os.path.join(st, "reminders"))
        with open(os.path.join(st, "reminders", "nudges.jsonl"), "w") as fh:
            fh.write(json.dumps({"id": "ci-checkpoint", "ts": 1788491207, "session": "s1",
                                 "kind": "checkpoint", "event": "PostToolUse",
                                 "cc_session": "s1"}) + "\n")
            fh.write(json.dumps({"id": "unattributed", "ts": 1788491208, "session": "s9",
                                 "kind": "prose", "event": "PostToolUse"}) + "\n")
        with open(os.path.join(st, "ledger.jsonl"), "w") as fh:
            fh.write(json.dumps({"event": "note", "session": "s1", "ts": 1788491300}) + "\n")
            fh.write(json.dumps({"event": "start", "session": "sz", "from": "ci-checkpoint",
                                 "ts": 1788491400}) + "\n")
        j2 = nudge_log_join(st)
        check("state2 rows", j2["rows"], 2)
        check("state2 with id", j2["rows_with_lineage_id"], 1)
        check("state2 unattributed", j2["rows_unattributed"], 1)
        check("state2 ledger from", j2["ledger_rows_with_from"], 1)
        check("state2 id join", j2["id_join_matched_rows"], 1)
        check("state2 session join", j2["session_join_sessions_with_a_ledger_row"], 1)

    if failures:
        for f in failures:
            sys.stderr.write("SELFTEST FAIL  %s\n" % f)
        sys.stderr.write("selftest: %d failure(s)\n" % len(failures))
        return 1
    sys.stdout.write("selftest: OK\n")
    return 0


# ----------------------------------------------------------------------------------- main


def main(argv=None) -> int:
    default_projects = os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
    default_state = os.environ.get("SKILL_COMPOUNDER_STATE") or os.path.expanduser(
        "~/.claude/skill-compounder")

    p = argparse.ArgumentParser(
        prog="reminder_conversion.py",
        description="Re-derive the nudge-to-output conversion rate (issue #30).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Every figure is printed as numerator/denominator. Nothing is written.")
    p.add_argument("--projects-dir", default=default_projects,
                   help="transcript root (default: %s)" % default_projects)
    p.add_argument("--state-dir", default=default_state,
                   help="skill-compounder state root (default: %s)" % default_state)
    p.add_argument("--since", metavar="YYYY-MM-DD", default=None,
                   help="count only events at or after this UTC day")
    p.add_argument("--until", metavar="YYYY-MM-DD", default=None,
                   help="count only events strictly before this UTC day")
    p.add_argument("--per-project", type=int, default=20, metavar="N",
                   help="show N project rows and fold the rest (0 = show all)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--selftest", action="store_true",
                   help="write a fixture to a temp dir, sweep it, assert the counts")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()

    if not os.path.isdir(args.projects_dir):
        sys.stderr.write("no such transcript directory: %s\n" % args.projects_dir)
        return 2

    since = parse_day(args.since) if args.since else None
    until = parse_day(args.until) if args.until else None
    sweep = Sweep(since=since, until=until).scan(args.projects_dir)
    rep = build_report(sweep, args)
    join = nudge_log_join(args.state_dir, since=since, until=until)

    if args.json:
        json.dump({"report": rep, "nudge_log": join}, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_report(rep, join, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
