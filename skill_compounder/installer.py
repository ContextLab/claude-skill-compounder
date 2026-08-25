"""Install / uninstall claude-skill-compounder into a Claude Code configuration.

Everything here is pure filesystem + JSON work against a caller-supplied
``claude_dir``, so the tests exercise the real code paths against a real temporary
Claude directory rather than a mock.

What gets wired:

* ``hooks.UserPromptSubmit``  -> compound-improvement.sh prompt   (section 1 reminder)
* ``hooks.PostToolUse``       -> compound-improvement.sh edit     (section 2 reminder)
* ``hooks.Stop``              -> insight-capture.sh               (skill-candidate queue)
* ``statusLine``              -> statusline.sh                    (forge animation)
* ``skills/<name>``           -> one symlink per skill in the repo's ``skills/``
* ``~/.local/bin/<name>``     -> one symlink per executable in the repo's ``bin/``

Both the skills and the CLIs are discovered from the filesystem rather than listed
here, so adding a seed skill or a new command needs no installer change.

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
INSIGHT_MARKER = "insight-capture.sh"
# Substring matching against the user's status line command was wrong twice. A bare
# "statusline.sh" matched their ~/bin/git-statusline.sh; adding the directory component
# still matched "$HOME/dotfiles/statusline/statusline.sh", a pipeline mentioning our path,
# and our path passed as an argument to something else. Any command we do not recognise as
# exactly our own is theirs, so recognition is now an exact comparison against the command
# we write, recorded at install time so uninstall can still find it if app_home moves.
STATUSLINE_RECORD = "installed-statusline.json"
EDIT_MATCHER = "Write|Edit|Bash"

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


def _insight_cmd(app_home):
    return '"%s/hooks/insight-capture.sh"' % app_home


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

    # Stop carries .last_assistant_message, which is where insight capture reads from.
    # Only wired when the script is present, so a checkout predating it still installs.
    if (Path(app_home) / "hooks" / "insight-capture.sh").exists():
        stop = _strip_marker(hooks.get("Stop"), INSIGHT_MARKER)
        stop.append({"hooks": [{"type": "command",
                                "command": _insight_cmd(app_home),
                                "timeout": 10}]})
        hooks["Stop"] = stop
    return settings


def remove_hooks(settings):
    """Remove our hook entries, leaving everyone else's intact."""
    hooks = settings.get("hooks")
    if not hooks:
        return settings
    for event, marker in (("UserPromptSubmit", HOOK_MARKER),
                          ("PostToolUse", HOOK_MARKER),
                          ("Stop", INSIGHT_MARKER)):
        if event in hooks:
            remaining = _strip_marker(hooks[event], marker)
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
    ours = _ours_statusline(app_home)

    already = bool(existing) and _is_our_statusline(existing, app_home, state_dir)
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

    entry = {"type": "command", "command": ours, "refreshInterval": 1}
    settings["statusLine"] = entry
    # Recorded so uninstall can still recognise our entry if the checkout has moved.
    (state / STATUSLINE_RECORD).write_text(json.dumps(entry, indent=2) + "\n",
                                           encoding="utf-8")
    return settings


def remove_statusline(settings, state_dir, app_home):
    """Restore the pre-install status line, or drop ours if there was none."""
    state = Path(state_dir)
    existing = settings.get("statusLine") or {}
    if not _is_our_statusline(existing, app_home, state_dir):
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

def _points_into(link, app_home):
    """True when a symlink resolves to somewhere inside our own checkout.

    This is how we tell our link from the user's. Checking merely that a symlink exists
    is not enough: someone whose own `no-silent-stub` is a link into their dotfiles had
    it replaced on install and removed on uninstall, with no warning at any point.
    """
    try:
        target = os.path.realpath(str(link))
    except OSError:
        return False
    root = os.path.realpath(str(app_home)) + os.sep
    return (target + os.sep).startswith(root)


def _symlink_force(src, dst, app_home):
    """Link src to dst, replacing only a link that already points into our checkout.

    Everything else at that path belongs to the user and is left exactly where it is:
    a real directory, a real file, or a symlink of theirs pointing somewhere else.
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        if os.path.realpath(str(dst)) == os.path.realpath(str(src)):
            return "linked"                       # already exactly ours
        if not _points_into(dst, app_home):
            return "skipped (your own link is there)"
        dst.unlink()                              # a stale link of ours into this checkout
    elif dst.exists():
        return "skipped (something else is already there)"
    dst.symlink_to(str(src))
    return "linked"


def _unlink_if_ours(dst, expected_src):
    """Only remove a link we created. Never a real file the user put there."""
    dst = Path(dst)
    if dst.is_symlink() and os.path.realpath(str(dst)) == os.path.realpath(str(expected_src)):
        dst.unlink()
        return True
    return False


def _skill_dirs(app_home):
    """Every skill shipped in the repo: any skills/<name>/ holding a SKILL.md.

    Discovered rather than listed, so the seed pool grows without touching this file.
    """
    root = Path(app_home) / "skills"
    if not root.is_dir():
        return []
    return sorted(d for d in root.iterdir() if (d / "SKILL.md").is_file())


def _cli_files(app_home):
    """Every executable in the repo's bin/. Same reasoning as _skill_dirs."""
    root = Path(app_home) / "bin"
    if not root.is_dir():
        return []
    return sorted(f for f in root.iterdir()
                  if f.is_file() and os.access(str(f), os.X_OK) and not f.name.startswith("."))


def _link_all(sources, dest_dir, app_home):
    """Link each source, reporting per name so a collision is visible rather than silent."""
    linked, skipped = [], []
    for src in sources:
        result = _symlink_force(src, Path(dest_dir) / src.name, app_home)
        (linked if result == "linked" else skipped).append(src.name)
    parts = []
    if linked:
        parts.append(", ".join(linked))
    if skipped:
        parts.append("NOT LINKED, you already have something by that name: "
                     + ", ".join(skipped))
    return "; ".join(parts) or "(none found)"


def _ours_statusline(app_home):
    return '"%s/statusline/statusline.sh"' % app_home


def _is_our_statusline(entry, app_home, state_dir):
    """Exact match, never a substring. Falls back to what install actually recorded."""
    command = str((entry or {}).get("command", "")).strip()
    if not command:
        return False
    if command == _ours_statusline(app_home):
        return True
    record = Path(state_dir) / STATUSLINE_RECORD
    if record.exists():
        try:
            return command == json.loads(record.read_text(encoding="utf-8")).get("command")
        except ValueError:
            return False
    return False


def _unlink_all(sources, dest_dir):
    """Report per name, so "left in place (not ours)" stays visible for each one."""
    removed, kept = [], []
    for src in sources:
        (removed if _unlink_if_ours(Path(dest_dir) / src.name, src) else kept).append(src.name)
    parts = []
    if removed:
        parts.append("removed: " + ", ".join(removed))
    if kept:
        parts.append("left in place (not ours): " + ", ".join(kept))
    return "; ".join(parts) or "(none found)"


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

    report["skills"] = _link_all(_skill_dirs(app_home), claude_dir / "skills", app_home)
    report["cli"] = _link_all(_cli_files(app_home), Path(bin_dir), app_home)
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
        remove_statusline(settings, state_dir, app_home)
        write_settings(settings_path, settings)
        report["settings"] = str(settings_path)

    report["skills"] = _unlink_all(_skill_dirs(app_home), claude_dir / "skills")
    report["cli"] = _unlink_all(_cli_files(app_home), Path(bin_dir))
    return report
