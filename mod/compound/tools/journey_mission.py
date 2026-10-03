#!/usr/bin/env python3
"""The journey for the mission half of the compound mod. Real `claude -p` sessions; run by hand, never in CI.

Each step names what kind of evidence it is. OUTCOME steps pass on what a session could
do that it could not do without the mod, and carry a no-mod control. DELIVERY steps pass
on the mod's own log plus the event having happened, and prove only that the text was
handed over at that moment.

  subagent    OUTCOME   a subagent told nothing can state a phrase only the user's prompt
                        held. Control: without the mod it cannot.
  compact     OUTCOME   after /compact, a resumed session with no tools quotes the phrase.
                        Control: reported, not required (a summary may keep it anyway).
  ambiguity   DELIVERY  a resumed session given "continue" gets the earlier request.
  completion  DELIVERY  a turn with many tool calls that ends on "done" is stated once.
  periodic    DELIVERY  with the interval at zero, a tool call gets the mission.

usage: journey.py [--model haiku] [--keep]

history-surfer's capture hook is wired through the throwaway project's own
.claude/settings.json and writes to a throwaway store, so nothing reaches the real one.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURFER_HOOK = os.path.expanduser("~/claude-history-surfer/hooks/log_prompt.py")
NO_TOOLS = "Bash,Read,Grep,Glob,Write,Edit,WebFetch,WebSearch,Task,Agent"


def make_project(path):
    os.makedirs(os.path.join(path, ".claude"))
    settings = {"hooks": {"UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": '"%s" "%s"' % (sys.executable, SURFER_HOOK)}]}]}}
    with open(os.path.join(path, ".claude", "settings.json"), "w") as fh:
        json.dump(settings, fh)


def session(cwd, env, model, prompt, save, with_mod=True, extra=()):
    argv = ["claude", "-p", "--model", model, "--setting-sources", "project",
            "--output-format", "stream-json", "--verbose", *extra]
    # Emptied so that a mod enabled in the user's own settings cannot load into a session
    # here, the control least of all; --setting-sources does not switch that variable off.
    env = dict(env, CLAUDE_CODE_PLUGIN_DIRS="", COMPOUND_LESSONS="0")
    if with_mod:
        argv += ["--plugin-dir", MOD]
    done = subprocess.run(argv, input=prompt, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    with open(save, "w") as fh:
        fh.write(done.stdout + "\n--- stderr ---\n" + done.stderr)
    sid, final, assistants = None, "", 0
    for line in done.stdout.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        sid = msg.get("session_id") or sid
        if msg.get("type") == "assistant":
            assistants += 1
        if msg.get("type") == "result":
            final = msg.get("result") or ""
    return {"sid": sid, "final": final, "assistants": assistants, "raw": done.stdout}


def hits(state, session_ids=None):
    path = os.path.join(state, "mod", "mission.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return [r for r in rows if session_ids is None or r.get("session") in session_ids]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(SURFER_HOOK):
        raise SystemExit("history-surfer's capture hook is not at %s" % SURFER_HOOK)

    root = tempfile.mkdtemp(prefix="mission-journey-")
    state = os.path.join(root, "state")
    os.makedirs(state)
    env = dict(os.environ, SKILL_COMPOUNDER_STATE=state,
               CLAUDE_HISTORY_SURFER_DIR=os.path.join(root, "surfer"))
    results = []

    def check(step, kind, what, ok, detail=""):
        results.append(ok)
        print("%s  %-10s %-8s %s%s" % ("PASS" if ok else "FAIL", step, kind, what,
                                       ("  [" + detail.replace("\n", " ")[:160] + "]") if detail else ""))

    def project(name):
        path = os.path.join(root, name)
        make_project(path)
        return path

    def stream(name):
        return os.path.join(root, name + ".stream")

    # ---- subagent: the phrase lives only in the user's prompt
    ask = ("The codename for my project is %s. Use the Agent tool to dispatch one general-purpose "
           "subagent, and give it EXACTLY this instruction and nothing else: 'If a project codename "
           "appears anywhere in your context, reply with it; otherwise reply NONE.' Do not tell the "
           "subagent the codename yourself. Then repeat its reply to me word for word.")
    for with_mod, phrase, label in ((False, "tessellate-quince-41", "control"), (True, "obsidian-heron-77", "mod")):
        got = session(project("sub-" + label), env, args.model, ask % phrase, stream("sub-" + label),
                      with_mod=with_mod, extra=("--allowedTools", "Agent"))
        told = phrase in got["final"]
        if with_mod:
            mine = hits(state, {got["sid"]})
            check("subagent", "OUTCOME", "a subagent told nothing states the user's phrase", told, got["final"])
            check("subagent", "DELIVERY", "logged at the subagent's start, with its agent id",
                  any(r["moment"] == "subagent" and r["agent"] for r in mine))
            check("dispatch", "DELIVERY", "logged before the Agent call, for the parent",
                  any(r["moment"] == "dispatch" for r in mine))
        else:
            check("subagent", "CONTROL", "without the mod the subagent cannot state it", not told, got["final"])

    # ---- compact: the phrase after a compaction, with no tools to look it up
    opening = ("I am working on %s for this project. Start by running `echo started` with the Bash "
               "tool, then reply with one short sentence saying you have started.")
    quote = ("Without using any tools, quote verbatim any text of the USER's own requests that you "
             "can see in your context right now. If you can see none, reply with exactly: NONE.")
    for with_mod, phrase, label in ((False, "the marrow-lantern migration", "control"),
                                    (True, "the copper-thistle migration", "mod")):
        proj = project("compact-" + label)
        first = session(proj, env, args.model, opening % phrase, stream("compact-open-" + label),
                        with_mod=with_mod, extra=("--allowedTools", "Bash"))
        session(proj, env, args.model, "/compact", stream("compact-run-" + label),
                with_mod=with_mod, extra=("--resume", first["sid"]))
        after = session(proj, env, args.model, quote, stream("compact-ask-" + label),
                        with_mod=with_mod, extra=("--resume", first["sid"], "--disallowed-tools", NO_TOOLS))
        kept = phrase.lower() in after["final"].lower()
        if with_mod:
            mine = hits(state)
            check("compact", "OUTCOME", "the phrase is quoted back after /compact", kept, after["final"])
            check("compact", "DELIVERY", "logged at the compaction or the resume",
                  any(r["moment"] in ("compact", "resume") for r in mine))
        else:
            print("INFO  compact    CONTROL  without the mod the phrase %s after /compact"
                  % ("ALSO survived" if kept else "did not survive"))

    # ---- ambiguity: a short prompt in a resumed session
    proj = project("ambiguity")
    first = session(proj, env, args.model,
                    "Please list three colours of the rainbow in one line, then stop.",
                    stream("ambiguity-open"))
    again = session(proj, env, args.model, "continue", stream("ambiguity-short"),
                    extra=("--resume", first["sid"]))
    check("ambiguity", "DELIVERY", "a short prompt gets the last substantive request",
          any(r["moment"] == "ambiguity" for r in hits(state, {first["sid"], again["sid"]})))

    # ---- completion: a long turn ending on a claim
    proj = project("completion")
    got = session(proj, env, args.model,
                  "Run these nine commands as nine SEPARATE Bash tool calls, one at a time: echo 1, echo 2, "
                  "echo 3, echo 4, echo 5, echo 6, echo 7, echo 8, echo 9. Then reply with exactly: All done.",
                  stream("completion"), extra=("--allowedTools", "Bash"))
    mine = [r for r in hits(state, {got["sid"]}) if r["moment"] == "completion"]
    check("completion", "DELIVERY", "stated exactly once at the completion claim", len(mine) == 1,
          "%d row(s)" % len(mine))
    check("completion", "DELIVERY", "the session took another turn after it",
          "stated at most once for this turn" in got["raw"],
          "%d assistant messages" % got["assistants"])

    # ---- periodic: interval zero, one tool call
    proj = project("periodic")
    got = session(proj, dict(env, COMPOUND_MISSION_INTERVAL="0"), args.model,
                  "Run `echo periodic-probe` with the Bash tool and then reply with one word: ok.",
                  stream("periodic"), extra=("--allowedTools", "Bash"))
    check("periodic", "DELIVERY", "a tool call past the interval gets the mission",
          any(r["moment"] == "periodic" for r in hits(state, {got["sid"]})))

    print("\n%d of %d checks passed; root %s" % (sum(results), len(results), root))
    if not args.keep and all(results):
        shutil.rmtree(root)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
