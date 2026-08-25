#!/usr/bin/env python3
"""Parse, lint, and pin the routing claims in every skill's `## Trigger precision`.

A `## Trigger precision` section is a set of *claims about a router*: these prompts
fire this skill, those prompts do not. Until 2026-08-25 not one of them had ever been
run. Three were then false. That is the whole reason this file exists.

WHAT THIS FILE CAN AND CANNOT DO
--------------------------------
It cannot tell you whether a prompt fires. Nothing static can. The evidence is in
`limits()` below and it is not a hedge -- it is a measured pair of prompts that a
static rule cannot separate. Read it before adding a "smarter" heuristic here.

What it does instead is enforce the *provenance* of each claim: every section must
carry a pin recording the exact description and the exact prompt list the claims were
measured against, plus when, with which CLI, and against which model. Any edit to
either side breaks the pin, and the only way to mend it is to measure again with
`scripts/probe_routing_claims.py`, which runs the prompts for real.

Usage:
    python3 scripts/routing_claims.py lint            # exit 1 on any finding
    python3 scripts/routing_claims.py show            # dump parsed claims
    python3 scripts/routing_claims.py pin <skill>     # print a fresh pin block
"""

import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"

SECTION = "## Trigger precision"
PIN_OPEN = "<!-- routing-pin"
PIN_CLOSE = "-->"

# Headers that introduce a list of prompts. Eight skills, six spellings between them;
# normalising here beats reformatting eight shipped files.
_FIRE = re.compile(r"^\s*(?:#{3,4}\s*)?\**\s*(?:prompts\s+that\s+)?"
                   r"(must|should)\s+fire(?:\s+this\s+skill)?\b", re.I)
_NOT_FIRE = re.compile(r"^\s*(?:#{3,4}\s*)?\**\s*(?:prompts\s+that\s+)?"
                       r"(must|should)\s+not\s+fire(?:\s+this\s+skill)?\b", re.I)
_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*)$")
_QUOTED = re.compile(r'[“"]([^”"]{4,})[”"]')
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

PIN_FIELDS = ("description-sha256", "prompts-sha256", "measured", "cli", "model", "result")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompts_digest(must_fire, must_not_fire):
    """Bind the verdicts to the exact prompt list, order included.

    A prompt added, edited, deleted or reordered changes this, so a pin cannot keep
    vouching for a list it was not measured against.
    """
    joined = "\n".join(["MUST-FIRE"] + list(must_fire)
                       + ["MUST-NOT-FIRE"] + list(must_not_fire))
    return sha256(joined)


def _frontmatter_description(text):
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md does not open with YAML frontmatter")
    front = text.split("\n---\n", 1)[0][4:]
    m = re.search(r"^description:\s*(.*)$", front, re.M)
    if not m:
        raise ValueError("frontmatter has no description")
    raw = m.group(1).strip()
    if raw and raw[0] in "\"'" and raw[-1] == raw[0] and len(raw) > 1:
        body = raw[1:-1]
        # YAML single-quoted scalars escape a quote by doubling it.
        return body.replace(raw[0] * 2, raw[0]) if raw[0] == "'" else body
    return raw


def parse_pin(section):
    """Return the pin block's fields, or None when the section carries no pin."""
    start = section.find(PIN_OPEN)
    if start < 0:
        return None
    end = section.find(PIN_CLOSE, start)
    if end < 0:
        raise ValueError("routing-pin block is not closed with -->")
    fields = {}
    for line in section[start + len(PIN_OPEN):end].splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError("routing-pin line is not `key: value`: %r" % line)
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def parse_skill(skill_md):
    text = skill_md.read_text()
    name = skill_md.parent.name
    out = {
        "name": name,
        "path": skill_md,
        "description": _frontmatter_description(text),
        "section": None,
        "must_fire": [],
        "must_not_fire": [],
        "pin": None,
        "unquoted_items": [],
    }
    # Anchor on the heading, not on the substring: two skills quote the phrase
    # "## Trigger precision" inside their prose, and splitting on the first hit
    # silently yielded an empty claim list for both.
    heads = list(re.finditer(r"^%s\s*$" % re.escape(SECTION), text, re.M))
    if not heads:
        return out
    if len(heads) > 1:
        raise ValueError("%s appears as a heading %d times" % (SECTION, len(heads)))
    tail = text[heads[0].end():]
    # The section ends at the next `##` heading. `###` sub-headings stay inside it.
    stop = re.search(r"^##\s", tail, re.M)
    section = tail[:stop.start()] if stop else tail
    out["section"] = section
    out["pin"] = parse_pin(section)

    bucket = None
    for line in section.splitlines():
        if _FIRE.match(line):
            bucket = "must_fire"
            continue
        if _NOT_FIRE.match(line):
            bucket = "must_not_fire"
            continue
        item = _ITEM.match(line)
        if not item:
            # A prose paragraph closes the list. This matters: three skills carry a
            # paragraph quoting the very fragment that was measured NOT to fire, and
            # collecting it as a claim would invert the file's meaning.
            if line.strip() and bucket and not line.startswith(" "):
                bucket = None
            continue
        if bucket is None:
            continue
        quoted = _QUOTED.search(item.group(1))
        if quoted:
            out[bucket].append(quoted.group(1).strip())
        else:
            out["unquoted_items"].append((bucket, item.group(1).strip()))
    return out


def all_skills():
    return [parse_skill(p) for p in sorted(SKILLS.glob("*/SKILL.md"))]


def render_pin(claims, measured="never", cli="n/a", model="n/a", result="unmeasured"):
    return "\n".join([
        PIN_OPEN,
        "description-sha256: %s" % sha256(claims["description"]),
        "prompts-sha256: %s" % prompts_digest(claims["must_fire"], claims["must_not_fire"]),
        "measured: %s" % measured,
        "cli: %s" % cli,
        "model: %s" % model,
        "result: %s" % result,
        PIN_CLOSE,
    ])


REMEASURE = (
    "Re-measure, do not re-hash. Pasting a fresh hash in re-certifies nothing:\n"
    "    SKILL_ROUTING_PROBE=1 python3 scripts/probe_routing_claims.py {name}\n"
    "It runs every prompt in the section through a real `claude -p --model sonnet`\n"
    "session and prints which skill each one actually fired. Update the pin from its\n"
    "output, and delete or rewrite any claim it reports false."
)


def lint(claims_list):
    """Return a list of findings. Empty list means the sections are internally sound.

    Every check here is a property of the *file*, never a prediction about the router.
    """
    findings = []
    for c in claims_list:
        name = c["name"]
        if c["section"] is None:
            continue  # a skill may legitimately ship no routing claims at all
        for bucket, raw in c["unquoted_items"]:
            findings.append(
                "%s: %s list item carries no quoted prompt: %r\n"
                "  A claim has to be the verbatim utterance, or the probe cannot run it."
                % (name, bucket.replace("_", "-"), raw))
        if len(c["must_fire"]) < 3:
            findings.append("%s: only %d must-fire prompts; three is the shipped floor."
                            % (name, len(c["must_fire"])))
        if len(c["must_not_fire"]) < 3:
            findings.append("%s: only %d must-not-fire prompts; three is the shipped floor."
                            % (name, len(c["must_not_fire"])))
        pin = c["pin"]
        if pin is None:
            findings.append(
                "%s: `%s` carries routing claims but no `%s` block.\n"
                "  Nothing then notices when the description is edited out from under\n"
                "  them. Add the block below directly under the heading:\n\n%s\n"
                % (name, SECTION, PIN_OPEN,
                   "\n".join("    " + l for l in render_pin(c).splitlines())))
            continue
        missing = [f for f in PIN_FIELDS if f not in pin]
        if missing:
            findings.append("%s: routing-pin is missing field(s): %s"
                            % (name, ", ".join(missing)))
            continue
        for field in ("description-sha256", "prompts-sha256"):
            if not _HEX64.match(pin[field]):
                findings.append("%s: routing-pin %s is not a sha256: %r"
                                % (name, field, pin[field]))
        actual_desc = sha256(c["description"])
        if pin["description-sha256"] != actual_desc:
            findings.append(
                "%s: the description has changed since the routing claims were measured.\n"
                "  pinned  %s\n  current %s\n"
                "  A four-word edit to a description has already flipped a measured\n"
                "  verdict in this repository, so EVERY claim in `%s` is now unverified,\n"
                "  not just the ones that look related.\n%s"
                % (name, pin["description-sha256"], actual_desc, SECTION,
                   REMEASURE.format(name=name)))
        actual_prompts = prompts_digest(c["must_fire"], c["must_not_fire"])
        if pin["prompts-sha256"] != actual_prompts:
            findings.append(
                "%s: the prompt list has changed since it was measured.\n"
                "  pinned  %s\n  current %s\n"
                "  A prompt added, edited, reordered or deleted invalidates the recorded\n"
                "  result, which counts prompts positionally.\n%s"
                % (name, pin["prompts-sha256"], actual_prompts,
                   REMEASURE.format(name=name)))
        result = pin["result"]
        verdict = result.split(":", 1)[0].split()[0] if result.strip() else ""
        if verdict not in ("verified", "partial", "unmeasured"):
            findings.append(
                "%s: routing-pin `result` must open with verified/partial/unmeasured, "
                "got %r" % (name, result))
        measured = pin["measured"]
        if (verdict == "unmeasured") != (measured == "never"):
            findings.append(
                "%s: routing-pin says result=%r with measured=%r. A date and a verdict\n"
                "  travel together; `unmeasured` is the only result a never-run claim has."
                % (name, result, measured))
        if measured != "never":
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", measured):
                findings.append("%s: routing-pin `measured` is neither an ISO date nor "
                                "`never`: %r" % (name, measured))
            if pin["model"] != "sonnet":
                findings.append(
                    "%s: routing-pin records model %r. Personal and project skill\n"
                    "  descriptions were measured ABSENT from the router on haiku, so a\n"
                    "  haiku run proves nothing about routing. Re-measure on sonnet."
                    % (name, pin["model"]))
            if pin["cli"] in ("", "n/a"):
                findings.append(
                    "%s: routing-pin records a measurement with no `cli` version.\n"
                    "  A routing claim can go false with no local edit at all, so the\n"
                    "  version it held under is part of the claim." % name)
    return findings


def limits():
    """The part of this rot that no static check will ever see. Kept as code, not prose,
    so it is read by whoever next tries to strengthen `lint()`.

    1. NO STATIC RULE DECIDES WHETHER A PROMPT FIRES.
       The design brief asked for a lint that flags a must-fire prompt which "names no
       concrete subject and carries no precondition". It was to fail these two, both
       measured false on 2026-08-25:

         X1  "you've hit your usage limit, we'll pick this up tomorrow"   (session-handoff)
         X2  "That took four attempts to get the ordering right, and we
              hit it last week too."                                     (skill-compounder)

       X1 has no honest separator from a prompt in the SAME skill that was measured to
       fire:

         E1  "we're almost out of context, let's wrap up"                (session-handoff)

       Both are one clause of trigger condition plus one vague clause. Neither names any
       work object; neither has an antecedent for its pronouns; E1 is the SHORTER of the
       two. Every candidate rule -- "names a concrete subject", "has an actionable
       request", "contains a domain noun", "no dangling anaphora", minimum length --
       either passes X1 or fails E1. The same holds for X2 against three measured-firing
       declaratives with only bare definite noun phrases ("that function", "the suite",
       "the handler").

       X2 alone is separable from its fixed form ("the migration ordering ... a different
       table") but only by a word list, and a word list is exactly what the tombstone in
       tests/test_seed_stale.py forbids: "It measured clause position, and a router
       matches on semantics, so it certified wording rather than behavior."

       So `lint()` checks provenance, which is decidable, and never content, which is
       not. It would have caught X1 and X2 -- as unmeasured claims, which is what they
       were -- without pretending to read them.

    2. A THIRD OF THIS ROT IS NOT IN THIS REPOSITORY AT ALL.
       `stale-artifact-check` lost two of three must-fire prompts to
       `superpowers:systematic-debugging`, a skill in a different package. Installing a
       plugin, or an upstream editing its own description, falsifies a claim here with no
       commit here. The pin records `cli:` and `measured:` so the age of a claim is
       visible, but nothing in this file, and nothing that could be added to it, detects
       that day. Only `probe_routing_claims.py` does, and only when someone runs it.
    """
    return limits.__doc__


def _main(argv):
    cmd = argv[1] if len(argv) > 1 else "lint"
    claims = all_skills()
    if cmd == "lint":
        findings = lint(claims)
        for f in findings:
            print("FINDING: %s\n" % f)
        print("%d skill(s) with routing claims, %d finding(s)."
              % (sum(1 for c in claims if c["section"]), len(findings)))
        return 1 if findings else 0
    if cmd == "show":
        for c in claims:
            if not c["section"]:
                continue
            print("== %s (pin: %s)" % (c["name"], "yes" if c["pin"] else "MISSING"))
            for p in c["must_fire"]:
                print("   FIRE     %s" % p)
            for p in c["must_not_fire"]:
                print("   NOT-FIRE %s" % p)
        return 0
    if cmd == "pin":
        if len(argv) < 3:
            print("usage: routing_claims.py pin <skill-name>", file=sys.stderr)
            return 2
        for c in claims:
            if c["name"] == argv[2]:
                print(render_pin(c))
                return 0
        print("no such skill: %s" % argv[2], file=sys.stderr)
        return 2
    if cmd == "limits":
        print(limits())
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
