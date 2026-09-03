#!/usr/bin/env python3
"""Install/uninstall driver. Called by install.sh / uninstall.sh (or directly).

Wires up the hooks, status line, skill, and CLI. All the logic lives in
skill_compounder.installer, which is what the test suite exercises.

Every failure the installer can reach is reported as a sentence naming the file,
key or directory at fault. A traceback tells the user nothing they can act on, and
the two cases that produced one -- a read-only bin directory and a settings.json we
cannot parse -- are exactly the cases where they most need to know what happened."""

import argparse
import os
import sys
from pathlib import Path

APP_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_HOME not in sys.path:
    sys.path.insert(0, APP_HOME)

from skill_compounder import installer  # noqa: E402


def _print_report(title, rep):
    print(title)
    for k, v in rep.items():
        print("  %-10s %s" % (k, v))


def main():
    ap = argparse.ArgumentParser(prog="claude-skill-compounder setup")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--claude-dir", default=str(Path.home() / ".claude"))
    ap.add_argument("--bin-dir", default=str(Path.home() / ".local" / "bin"))
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--no-doctrine", action="store_true",
                    help="do not append the Compound Improvement block to CLAUDE.md "
                         "(same as SKILL_COMPOUNDER_DOCTRINE=0)")
    ap.add_argument("--enable-review", action="store_true",
                    help="turn on paid session review after installing (writes "
                         "SKILL_COMPOUNDER_REVIEW=1 into settings.json's env block; "
                         "same as SKILL_COMPOUNDER_ENABLE_REVIEW=1). Off by default: "
                         "install alone never touches the env block.")
    ap.add_argument("--disable-review", action="store_true",
                    help="turn paid session review back off (removes the key this "
                         "package set; a value you set yourself is left alone)")
    args = ap.parse_args()

    enable_review = args.enable_review or (
        os.environ.get("SKILL_COMPOUNDER_ENABLE_REVIEW", "").strip() == "1")
    if enable_review and args.disable_review:
        print("error: --enable-review and SKILL_COMPOUNDER_ENABLE_REVIEW=1 ask for the "
              "opposite of --disable-review. Pick one.", file=sys.stderr)
        return 1

    if args.uninstall:
        try:
            rep = installer.uninstall(APP_HOME, args.claude_dir, args.bin_dir,
                                      args.state_dir)
        except (installer.InstallError, ValueError, OSError) as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1
        _print_report("Uninstalled claude-skill-compounder:", rep)
        print("\nYour forge/reminder state is left intact. To delete it:")
        print("  rm -rf ~/.claude/skill-compounder")
        if rep.get("errors"):
            print("\nerror: %s" % rep["errors"], file=sys.stderr)
            print("Everything listed above as removed really is removed; fix the problem "
                  "and run this again to finish.", file=sys.stderr)
            return 1
        return 0

    try:
        # `False if the flag is set else None`, never `not args.no_doctrine`. The kwarg is
        # tri-state: None means "ask SKILL_COMPOUNDER_DOCTRINE", and an explicit True beats
        # the environment, so passing `not args.no_doctrine` would make every ordinary run
        # override `SKILL_COMPOUNDER_DOCTRINE=0` and write the block the user declined.
        rep = installer.install(APP_HOME, args.claude_dir, args.bin_dir, args.state_dir,
                                doctrine=False if args.no_doctrine else None)
    except (installer.InstallError, ValueError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    _print_report("Installed claude-skill-compounder:", rep)
    if rep.get("errors"):
        print("\nerror: %s" % rep["errors"], file=sys.stderr)
        print("Everything listed above as linked really is installed; fix the problem "
              "and run this again to finish.", file=sys.stderr)
        return 1

    # Opt-in only: install() above never touches the env block, so the spend requires a
    # yes, never a no (issue #39). --disable-review is meaningful even on a plain install
    # (it is also how uninstall's own manifest-gated removal gets exercised by hand).
    if enable_review:
        print("\n" + installer.REVIEW_DATA_BOUNDARY)
        rev = installer.enable_review(args.claude_dir, args.state_dir)
        if rev.get("note"):
            print(rev["note"])
        else:
            print("Session review is now ON (env.%s=%s in %s)."
                  % (installer.REVIEW_ENV_KEY, installer.REVIEW_ENV_VALUE, rev["settings"]))
    elif args.disable_review:
        rev = installer.disable_review(args.claude_dir, args.state_dir)
        if rev.get("note"):
            print("\n" + rev["note"])
        elif rev.get("changed"):
            print("\nSession review is now OFF (env.%s removed from %s)."
                  % (installer.REVIEW_ENV_KEY, rev["settings"]))
        else:
            print("\nSession review was already off.")

    print("\nNext steps:")
    # The CLI names are RE-DERIVED from what was just linked, never listed here. The
    # hardcoded list said "skillforge, skillreport, skillinsight, and skillcontrib" and
    # stayed saying it after `skillrepeat` shipped -- a fifth CLI, linked by the same
    # install whose closing advice denied it existed. The installer already discovers what
    # to link by walking `bin/`, so a sentence that enumerates them by hand is a second
    # source of truth that only ever falls behind.
    clis = rep.get("cli") or ""
    names = [n for n in (c.strip() for c in clis.split(",")) if n]
    if len(names) > 1:
        which = "for %s and %s" % (", ".join(names[:-1]), names[-1])
    elif names:
        which = "for %s" % names[0]
    else:
        which = "for this package's CLIs"
    print("  1. Ensure %s is on your PATH\n     (%s)." % (args.bin_dir, which))
    print("  2. jq is required: `brew install jq` / `apt install jq`.")
    print("  3. Hooks and skills load without a restart, but /hooks forces a reload.")
    print("  4. Try:  skillforge start demo 4 \"checking the animation\"  then  skillforge clear")
    print("  5. `skillreport` shows what has been forged and whether it got reused.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
