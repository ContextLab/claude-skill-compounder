#!/usr/bin/env python3
"""The package installed through Claude Code's plugin marketplace, in a fresh
configuration. Real `claude` commands and `claude -p` sessions; run by hand.

Every step runs under the world's own CLAUDE_CONFIG_DIR (`--config fresh`, which this
journey requires), so the install writes nothing to the real `~/.claude`, and the sessions
load the mod only because the install enabled it: no `--plugin-dir` is passed.

  install   a copy of the package with a scratch `.claude-plugin/marketplace.json` is added
            as a marketplace and `compound` is installed from it; both commands succeed,
            the fresh configuration's settings enable it, and the real `~/.claude` files the
            commands would write are byte for byte as they were.
  load      a session's `init` message lists the installed plugin, and no `--plugin-dir`.
  prompt    the prompt hook fired: an `index` event for the session.
  tool      the tool-call hook fired: an earlier session's failed build is written down as
            `met`, and the later session that fixes it owes a `capture`.
  stop      the stop hook fired: that session's stop was refused once (`refuse`, why "debt").
  cli       the mod found the CLI shipped beside it: what it told the session names
            `<plugin root>/bin/compound`, the session settled the debt by running it, and
            nothing in the mod failed.

usage: journey_marketplace.py [--model haiku] [--keep]
"""
import hashlib
import json
import os

import common

MARKETPLACE = "compound-journey"
REAL = [os.path.expanduser(os.path.join("~/.claude", *p)) for p in
        (("settings.json",), ("plugins", "installed_plugins.json"), ("plugins", "known_marketplaces.json"))]
FINISH_NOW = (common.BUILD_TASK + " The moment the build succeeds, end your turn with that line, before doing anything "
              "else. If your attempt to finish is refused, do what the refusal asks, and then finish.")


def digests():
    out = {}
    for path in REAL:
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                out[path] = hashlib.sha256(fh.read()).hexdigest()
        else:
            out[path] = None
    return out


def init_message(stream):
    with open(stream) as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "system" and msg.get("subtype") == "init":
                return msg
    return {}


def main():
    args = common.arguments(__doc__)
    if common.CONFIG != "fresh":
        raise SystemExit("this journey installs a plugin, which only --config fresh keeps out of the real ~/.claude")
    w = common.World("marketplace")
    package = w.copy_of_package()
    with open(os.path.join(package, ".claude-plugin", "marketplace.json"), "w") as fh:
        json.dump({"name": MARKETPLACE, "owner": {"name": "journey"},
                   "plugins": [{"name": "compound", "source": "./"}]}, fh, indent=2)
    project = w.project("alpha", build=True)
    before = digests()

    added = w.run_claude(project, "plugin", "marketplace", "add", package)
    w.check("install", "the copy was added as a marketplace", added.returncode == 0, (added.stdout + added.stderr).strip())
    put = w.run_claude(project, "plugin", "install", "compound@" + MARKETPLACE)
    w.check("install", "compound was installed from it", put.returncode == 0, (put.stdout + put.stderr).strip())
    settings = os.path.join(w.config, "settings.json")
    enabled = {}
    if os.path.isfile(settings):
        with open(settings) as fh:
            enabled = json.load(fh).get("enabledPlugins", {})
    w.check("install", "the fresh configuration enables it", enabled.get("compound@" + MARKETPLACE) is True, enabled)

    quiet = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}
    first = w.session(project, common.MEET_BUILD, args.model, installed=True, **quiet)
    init = init_message(first.stream)
    plugins = [p for p in init.get("plugins", []) if isinstance(p, dict) and p.get("name") == "compound"]
    w.check("load", "the session lists the installed plugin", len(plugins) == 1, init.get("plugins"))
    root = plugins[0].get("path", "") if plugins else ""
    print("      plugin root %s" % root)
    w.check("prompt", "the prompt hook fired: an index event", len(w.events(project, session=first.sid, kind="index")) == 1,
            ", ".join(e["type"] for e in w.events(project, session=first.sid)))
    met = w.events(project, session=first.sid, kind="met")
    w.show("met", met)
    w.check("tool", "the tool-call hook wrote the failed build down", len(met) >= 1 and "a profile is required" in met[0].get("sig", ""),
            met)

    s = w.session(project, FINISH_NOW, args.model, tools=("Bash", "Skill"), installed=True, **quiet)
    events = w.events(project, session=s.sid)
    w.show("event", events)
    kinds = [e["type"] for e in events]
    w.check("tool", "the fix owes a lesson: a capture event", "capture" in kinds, ", ".join(kinds))
    refused = [e for e in events if e["type"] == "refuse"]
    w.check("stop", "the stop hook refused the stop once, for the debt",
            len(refused) == 1 and refused[0].get("why") == "debt", refused)
    cli = os.path.join(root, "bin", "compound") if root else "(no plugin root)"
    with open(s.stream) as fh:
        stream = fh.read()
    w.check("cli", "what the mod told the session names the CLI beside it", root != "" and cli in stream, cli)
    settled = [c for c in s.bash() if cli in c[0] and (" add" in c[0] or " skip" in c[0])]
    after = kinds[kinds.index("capture") + 1:] if "capture" in kinds else []
    w.check("cli", "the session settled the debt by running that CLI",
            bool(settled) and any(k in ("learn", "skip") for k in after),
            " | ".join(c[0][:120] for c in s.bash() if "compound" in c[0]) or "no compound call")
    w.check("cli", "nothing in the mod failed",
            [e for e in events + w.events(project, session=first.sid) if e["type"] == "error"] == [],
            [e for e in events if e["type"] == "error"])
    w.check("cli", "the session still answered", s.returncode == 0 and "build ok" in s.result, s.result[-300:])
    after_digests = digests()
    w.check("install", "the real ~/.claude files were not touched", before == after_digests,
            [p for p in REAL if before[p] != after_digests[p]])
    w.finish(args.keep)


if __name__ == "__main__":
    main()
