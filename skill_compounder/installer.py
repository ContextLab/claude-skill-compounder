"""Install / uninstall claude-skill-compounder into a Claude Code configuration.

Everything here is pure filesystem + JSON work against a caller-supplied
``claude_dir``, so the tests exercise the real code paths against a real temporary
Claude directory rather than a mock.

What gets wired:

* ``hooks.UserPromptSubmit``  -> compound-improvement.sh prompt   (section 1 reminder)
* ``hooks.PostToolUse``       -> compound-improvement.sh edit     (section 2 reminder)
* ``statusLine``              -> statusline.sh                    (forge animation)
* ``skills/skill-compounder`` -> symlink to the repo's SKILL.md directory
* ``~/.local/bin/skillforge`` -> symlink to the repo's CLI

Existing hooks from other tools are preserved; an existing status line is preserved
by saving its command into the state directory and calling it from our wrapper.
"""

import json
import os
import shutil
import stat
import time
from pathlib import Path

# Markers identify our entries so install is idempotent and uninstall is surgical.
HOOK_MARKER = "compound-improvement.sh"
STATUSLINE_MARKER = "statusline.sh"
EDIT_MATCHER = "Write|Edit"

DEFAULT_STATE = Path.home() / ".claude" / "skill-compounder"


# --------------------------------------------------------------------------- settings

def read_settings(path):
    """Read settings.json, tolerating a missing file. Raises on malformed JSON:
    silently discarding a user's settings would be far worse than failing loudly."""
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def backup_settings(path):
    """Copy settings.json aside before we touch it. Returns the backup path or None."""
    p = Path(path)
    if not p.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = p.with_name(p.name + ".bak-skill-compounder-" + stamp)
    shutil.copy2(str(p), str(dest))
    return str(dest)


def write_settings(path, settings):
    """Write settings.json atomically, so an interrupted install cannot leave a
    truncated file (a malformed settings.json disables every setting in it)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(p))


# ----------------------------------------------------------------------------- hooks

def _hook_cmd(app_home, mode):
    return '"%s/hooks/compound-improvement.sh" %s' % (app_home, mode)


def _strip_marker(groups, marker):
    """Drop our hook entries (and any group left empty) from one event's list."""
    out = []
    for group in groups or []:
        hooks = [h for h in group.get("hooks", []) if marker not in str(h.get("command", ""))]
        if hooks:
            g = dict(group)
            g["hooks"] = hooks
            out.append(g)
        elif not group.get("hooks"):
            out.append(group)          # someone else's empty group; leave it alone
    return out


def merge_hooks(settings, app_home):
    """Add our two hook entries, replacing any previous copy of them.

    Other tools' hooks on the same events are preserved: we only ever remove
    entries whose command contains HOOK_MARKER.
    """
    hooks = settings.setdefault("hooks", {})

    ups = _strip_marker(hooks.get("UserPromptSubmit"), HOOK_MARKER)
    ups.append({"hooks": [{"type": "command",
                           "command": _hook_cmd(app_home, "prompt"),
                           "timeout": 10}]})
    hooks["UserPromptSubmit"] = ups

    ptu = _strip_marker(hooks.get("PostToolUse"), HOOK_MARKER)
    ptu.append({"matcher": EDIT_MATCHER,
                "hooks": [{"type": "command",
                           "command": _hook_cmd(app_home, "edit"),
                           "timeout": 10}]})
    hooks["PostToolUse"] = ptu
    return settings


def remove_hooks(settings):
    """Remove our hook entries, leaving everyone else's intact."""
    hooks = settings.get("hooks")
    if not hooks:
        return settings
    for event in ("UserPromptSubmit", "PostToolUse"):
        if event in hooks:
            remaining = _strip_marker(hooks[event], HOOK_MARKER)
            if remaining:
                hooks[event] = remaining
            else:
                del hooks[event]
    if not hooks:
        del settings["hooks"]
    return settings


# ------------------------------------------------------------------------ status line

def install_statusline(settings, app_home, state_dir):
    """Point statusLine at our wrapper, preserving any existing status line.

    The previous command is written to ``<state>/statusline-base.sh`` and the original
    statusLine object is recorded in ``<state>/original-statusline.json`` so uninstall
    can put things back exactly as they were.
    """
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    existing = settings.get("statusLine")
    ours = '"%s/statusline/statusline.sh"' % app_home

    already = bool(existing) and STATUSLINE_MARKER in str(existing.get("command", ""))
    if existing and not already:
        # Preserve verbatim, as an executable script our wrapper can call.
        base = state / "statusline-base.sh"
        base.write_text(
            "#!/usr/bin/env bash\n"
            "# The status line configured before claude-skill-compounder was installed.\n"
            "# Preserved verbatim; statusline.sh calls this first.\n"
            + str(existing.get("command", "")) + "\n",
            encoding="utf-8")
        base.chmod(base.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        (state / "original-statusline.json").write_text(
            json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    settings["statusLine"] = {"type": "command", "command": ours, "refreshInterval": 1}
    return settings


def remove_statusline(settings, state_dir):
    """Restore the pre-install status line, or drop ours if there was none."""
    state = Path(state_dir)
    existing = settings.get("statusLine") or {}
    if STATUSLINE_MARKER not in str(existing.get("command", "")):
        return settings                      # not ours; do not touch it
    original = state / "original-statusline.json"
    if original.exists():
        try:
            settings["statusLine"] = json.loads(original.read_text(encoding="utf-8"))
            return settings
        except ValueError:
            pass
    settings.pop("statusLine", None)
    return settings


# -------------------------------------------------------------------------- symlinks

def _symlink_force(src, dst):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            shutil.rmtree(str(dst))
    dst.symlink_to(str(src))
    return str(dst)


def _unlink_if_ours(dst, expected_src):
    """Only remove a link we created — never a real file the user put there."""
    dst = Path(dst)
    if dst.is_symlink() and os.path.realpath(str(dst)) == os.path.realpath(str(expected_src)):
        dst.unlink()
        return True
    return False


# ------------------------------------------------------------------- install/uninstall

def install(app_home, claude_dir, bin_dir, state_dir=None):
    app_home = str(Path(app_home).resolve())
    claude_dir = Path(claude_dir)
    state_dir = str(state_dir or DEFAULT_STATE)
    settings_path = claude_dir / "settings.json"

    report = {}
    report["backup"] = backup_settings(settings_path) or "(no existing settings.json)"

    settings = read_settings(settings_path)
    merge_hooks(settings, app_home)
    install_statusline(settings, app_home, state_dir)
    write_settings(settings_path, settings)
    report["settings"] = str(settings_path)

    report["skill"] = _symlink_force(Path(app_home) / "skills" / "skill-compounder",
                                     claude_dir / "skills" / "skill-compounder")
    report["cli"] = _symlink_force(Path(app_home) / "bin" / "skillforge",
                                   Path(bin_dir) / "skillforge")
    report["state"] = state_dir
    return report


def uninstall(app_home, claude_dir, bin_dir, state_dir=None):
    app_home = str(Path(app_home).resolve())
    claude_dir = Path(claude_dir)
    state_dir = str(state_dir or DEFAULT_STATE)
    settings_path = claude_dir / "settings.json"

    report = {}
    report["backup"] = backup_settings(settings_path) or "(no existing settings.json)"

    if Path(settings_path).exists():
        settings = read_settings(settings_path)
        remove_hooks(settings)
        remove_statusline(settings, state_dir)
        write_settings(settings_path, settings)
        report["settings"] = str(settings_path)

    report["skill"] = ("removed" if _unlink_if_ours(
        claude_dir / "skills" / "skill-compounder",
        Path(app_home) / "skills" / "skill-compounder") else "left in place (not ours)")
    report["cli"] = ("removed" if _unlink_if_ours(
        Path(bin_dir) / "skillforge",
        Path(app_home) / "bin" / "skillforge") else "left in place (not ours)")
    return report
