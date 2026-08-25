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
    args = ap.parse_args()

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
        rep = installer.install(APP_HOME, args.claude_dir, args.bin_dir, args.state_dir)
    except (installer.InstallError, ValueError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    _print_report("Installed claude-skill-compounder:", rep)
    if rep.get("errors"):
        print("\nerror: %s" % rep["errors"], file=sys.stderr)
        print("Everything listed above as linked really is installed; fix the problem "
              "and run this again to finish.", file=sys.stderr)
        return 1
    print("\nNext steps:")
    print("  1. Ensure %s is on your PATH (for skillforge, skillreport,\n"
          "     skillinsight, and skillcontrib)." % args.bin_dir)
    print("  2. jq is required: `brew install jq` / `apt install jq`.")
    print("  3. Hooks and skills load without a restart, but /hooks forces a reload.")
    print("  4. Try:  skillforge start demo 4 \"checking the animation\"  then  skillforge clear")
    print("  5. `skillreport` shows what has been forged and whether it got reused.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
