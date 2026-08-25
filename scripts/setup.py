#!/usr/bin/env python3
"""Install/uninstall driver. Called by install.sh / uninstall.sh (or directly).

Wires up the hooks, status line, skill, and CLI. All the logic lives in
skill_compounder.installer, which is what the test suite exercises."""

import argparse
import os
import sys
from pathlib import Path

APP_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_HOME not in sys.path:
    sys.path.insert(0, APP_HOME)

from skill_compounder import installer  # noqa: E402


def main():
    ap = argparse.ArgumentParser(prog="claude-skill-compounder setup")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--claude-dir", default=str(Path.home() / ".claude"))
    ap.add_argument("--bin-dir", default=str(Path.home() / ".local" / "bin"))
    ap.add_argument("--state-dir", default=None)
    args = ap.parse_args()

    if args.uninstall:
        rep = installer.uninstall(APP_HOME, args.claude_dir, args.bin_dir, args.state_dir)
        print("Uninstalled claude-skill-compounder:")
        for k, v in rep.items():
            print("  %-10s %s" % (k, v))
        print("\nYour forge/reminder state is left intact. To delete it:")
        print("  rm -rf ~/.claude/skill-compounder")
        return 0

    rep = installer.install(APP_HOME, args.claude_dir, args.bin_dir, args.state_dir)
    print("Installed claude-skill-compounder:")
    for k, v in rep.items():
        print("  %-10s %s" % (k, v))
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
