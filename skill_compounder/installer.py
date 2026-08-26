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

Three rules govern everything below, in this order:

1. Never touch what we cannot prove we created.
2. Never apply half of an install. Check first, and if something still fails, say
   exactly what landed and what did not.
3. Never hand the user a traceback. Every reachable failure names the key, the
   path, or the directory that is wrong.
"""

import json
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

# Markers identify our entries so install is idempotent and uninstall is surgical.
HOOK_MARKER = "compound-improvement.sh"
INSIGHT_MARKER = "insight-capture.sh"
# Substring matching against the user's status line command was wrong twice. A bare
# "statusline.sh" matched their ~/bin/git-statusline.sh; adding the directory component
# still matched "$HOME/dotfiles/statusline/statusline.sh", a pipeline mentioning our path,
# and our path passed as an argument to something else. So the status line carries a marker
# we author ourselves, exactly as the two hooks do: a trailing shell comment, which the
# command's own shell ignores and which no path of the user's can collide with. It is also
# location-independent, so moving the checkout does not orphan the entry.
STATUSLINE_MARKER = "# claude-skill-compounder"
STATUSLINE_RECORD = "installed-statusline.json"
# What this package linked, recorded at install time. This is what lets a *different*
# checkout recognise the links a previous one made; see _link_is_ours.
MANIFEST = "install-manifest.json"
EDIT_MATCHER = "Write|Edit|Bash"
BACKUP_PREFIX = ".bak-skill-compounder-"
MAX_BACKUPS = 10

DEFAULT_STATE = Path.home() / ".claude" / "skill-compounder"


class InstallError(Exception):
    """A problem the user can act on, reported without a traceback."""


class SettingsShapeError(InstallError, ValueError):
    """settings.json parses as JSON but has a key we cannot work with."""


def _jsontype(value):
    return {dict: "an object", list: "a list", str: "a string", bool: "a boolean",
            int: "a number", float: "a number", type(None): "null"}.get(type(value), "a value")


# --------------------------------------------------------------------------- settings

def _real_settings_path(path):
    """The regular file a settings path ultimately names.

    stow, chezmoi and hand-rolled dotfiles all present ``settings.json`` as a symlink
    into a dotfiles repo. ``os.replace`` onto the link would delete it and leave a
    regular file, orphaning the source with exit 0 and no warning, so every write
    resolves the link first and writes *through* it.
    """
    p = Path(path)
    if not p.is_symlink():
        return p
    try:
        return Path(os.path.realpath(str(p)))
    except OSError as exc:
        raise InstallError("cannot follow the symlink at %s (%s)" % (p, exc))


def read_settings(path):
    """Read settings.json, tolerating a missing file. Raises on malformed JSON:
    silently discarding a user's settings would be far worse than failing loudly."""
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SettingsShapeError("%s is not valid JSON (%s). Nothing was changed; fix "
                                 "the file and run this again." % (p, exc))
    if not isinstance(data, dict):
        raise SettingsShapeError("%s must hold a JSON object at the top level, but it "
                                 "holds %s. Nothing was changed." % (p, _jsontype(data)))
    return data


def _stamp():
    """Backup timestamp. Pinned by SKILL_COMPOUNDER_NOW (epoch seconds) in tests."""
    pinned = os.environ.get("SKILL_COMPOUNDER_NOW", "").strip()
    if pinned:
        try:
            return time.strftime("%Y%m%d-%H%M%S", time.localtime(int(pinned)))
        except ValueError:
            pass
    return time.strftime("%Y%m%d-%H%M%S")


def _our_backups(p):
    return sorted(p.parent.glob(p.name + BACKUP_PREFIX + "*"))


def backup_settings(path):
    """Copy settings.json aside before we touch it. Returns the backup path or None.

    The copy lands beside the *configured* path rather than beside a dotfiles source,
    so a symlinked settings.json does not sprinkle backups through someone's git repo.
    An identical backup is never written twice, and only our own timestamped copies are
    ever pruned.
    """
    p = Path(path)
    real = _real_settings_path(p)
    if not real.exists():
        return None
    content = real.read_bytes()

    existing = _our_backups(p)
    for old in reversed(existing):
        try:
            if old.read_bytes() == content:
                return str(old)          # nothing has changed since that one
        except OSError:
            continue

    # The stamp has second resolution, so two runs a second apart would otherwise write
    # the same name and the second would overwrite the pre-install copy -- the one worth
    # keeping. A suffix is added rather than clobbering.
    base = p.with_name(p.name + BACKUP_PREFIX + _stamp())
    dest, n = base, 1
    while dest.exists():
        n += 1
        dest = base.with_name(base.name + "-%d" % n)
    shutil.copy2(str(real), str(dest))
    for old in _our_backups(p)[:-MAX_BACKUPS]:
        try:
            old.unlink()
        except OSError:
            pass
    return str(dest)


def write_settings(path, settings):
    """Write settings.json atomically, so an interrupted install cannot leave a
    truncated file (a malformed settings.json disables every setting in it).

    Writes through a symlink rather than over it: the temp file is created beside the
    resolved target so ``os.replace`` stays on one filesystem and the link survives.
    """
    real = _real_settings_path(path)
    real.parent.mkdir(parents=True, exist_ok=True)
    # A fixed temp name lets two concurrent runs interleave their bytes in one file and
    # then rename the result into place, so the name is unique per writer.
    fd, tmp = tempfile.mkstemp(prefix=real.name + ".tmp-", dir=str(real.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(settings, indent=2) + "\n")
        os.chmod(tmp, 0o600 if not real.exists() else stat.S_IMODE(real.stat().st_mode))
        os.replace(tmp, str(real))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ------------------------------------------------------------------------- preflight

def _probe_writable(directory):
    """Prove we can write where we are about to write, rather than trust mode bits.

    Permission bits lie on NFS, on ACL-carrying filesystems and on read-only mounts, so
    this creates and deletes a real temp file in the nearest existing ancestor.
    Returns None when writable, or a human-readable reason.
    """
    target = Path(directory)
    # lexists, not exists: a dangling symlink *is* something, and walking up past one
    # left install to discover it nine times over, one FileExistsError per skill, after
    # the hooks and the status line were already wired.
    while not os.path.lexists(str(target)) and target.parent != target:
        target = target.parent
    if target.is_symlink() and not target.exists():
        return "%s is a symlink pointing at %s, which does not exist" % (
            target, _link_target(target))
    if not target.is_dir():
        return "%s is not a directory" % target
    try:
        fd, name = tempfile.mkstemp(prefix=".skill-compounder-probe-", dir=str(target))
    except OSError as exc:
        return "%s is not writable (%s)" % (target, exc.strerror or exc)
    os.close(fd)
    try:
        os.unlink(name)
    except OSError:
        pass
    return None


def _executable_problems(app_home):
    """A checkout whose executable bits are gone installs into something that cannot run.

    Downloading the repo as a zip, or unpacking it from an archive that drops modes, gave
    exit 0, "Installed", `cli (none found)` -- and a statusLine wired to a file the shell
    refuses to execute. Nothing said so. Both halves are checked here, with the fix.
    """
    home = Path(app_home)
    problems = []
    scripts = [home / "statusline" / "statusline.sh"]
    scripts += sorted((home / "hooks").glob("*.sh"))
    dead = [str(s) for s in scripts if s.is_file() and not os.access(str(s), os.X_OK)]
    if dead:
        problems.append("these are wired into settings.json but are not executable "
                        "(chmod +x them): " + ", ".join(dead))
    binroot = home / "bin"
    if binroot.is_dir():
        files = [f for f in sorted(binroot.iterdir())
                 if f.is_file() and not f.name.startswith(".")]
        if files and not any(os.access(str(f), os.X_OK) for f in files):
            problems.append("nothing in %s is executable, so no command would be "
                            "installed (chmod +x %s/*)" % (binroot, binroot))
    return problems


def preflight(claude_dir, bin_dir, state_dir, settings_path, app_home=None):
    """Check everything install needs *before* it changes anything.

    A read-only bin directory used to raise after the hooks, the status line and every
    skill were already live: the user read "it failed" while most of it was installed
    and `skillforge` was missing from PATH. Everything that must be writable is proven
    writable first, and all the problems are reported at once rather than one per run.
    """
    problems = []
    for label, d in (("the Claude config directory", Path(claude_dir)),
                     ("the skills directory", Path(claude_dir) / "skills"),
                     ("the CLI directory", Path(bin_dir)),
                     ("the state directory", Path(state_dir)),
                     ("the settings directory", _real_settings_path(settings_path).parent)):
        reason = _probe_writable(d)
        if reason:
            problems.append("%s: %s" % (label, reason))
    real = _real_settings_path(settings_path)
    if real.exists() and not os.access(str(real), os.W_OK):
        problems.append("settings.json is not writable: %s" % real)
    problems.extend(_executable_problems(app_home) if app_home else [])
    if problems:
        raise InstallError("nothing was installed, because:\n  - " + "\n  - ".join(problems))


# ----------------------------------------------------------------------------- hooks

def _hook_cmd(app_home, mode):
    return '"%s/hooks/compound-improvement.sh" %s' % (app_home, mode)


def _insight_cmd(app_home):
    return '"%s/hooks/insight-capture.sh"' % app_home


def _hooks_map(settings, strict):
    """The ``hooks`` object, or a clear error naming the key that is wrong.

    ``null`` means "no hooks" and is accepted. A list, a string or a number is not
    something we can merge into, and guessing what was meant is worse than refusing.
    Uninstall passes ``strict=False``: a shape we cannot read holds no entry of ours
    anyway, and it must never be the reason the package cannot be removed.
    """
    hooks = settings.get("hooks")
    if hooks is None:
        return {}
    if not isinstance(hooks, dict):
        if not strict:
            return None
        raise SettingsShapeError(
            'settings.json: "hooks" must be an object mapping event names to lists of '
            'hook groups, but it is %s. Nothing was changed; fix or remove that key.'
            % _jsontype(hooks))
    return hooks


def _event_groups(hooks, event, strict):
    """One event's list of hook groups, validated. ``hooks.<event>`` names any fault."""
    groups = hooks.get(event)
    if groups is None:
        return []
    where = "hooks.%s" % event
    if not isinstance(groups, list):
        if not strict:
            return None
        raise SettingsShapeError(
            'settings.json: "%s" must be a list of hook groups, but it is %s. '
            'Nothing was changed; fix or remove that key.' % (where, _jsontype(groups)))
    for i, group in enumerate(groups):
        if not isinstance(group, dict):
            if not strict:
                return None
            raise SettingsShapeError(
                'settings.json: "%s[%d]" must be an object, but it is %s. Nothing was '
                'changed; fix or remove that entry.' % (where, i, _jsontype(group)))
        entries = group.get("hooks")
        if entries is None:
            continue
        if not isinstance(entries, list):
            if not strict:
                return None
            raise SettingsShapeError(
                'settings.json: "%s[%d].hooks" must be a list, but it is %s. Nothing was '
                'changed; fix or remove that entry.' % (where, i, _jsontype(entries)))
        for j, entry in enumerate(entries):
            if not isinstance(entry, dict):
                if not strict:
                    return None
                raise SettingsShapeError(
                    'settings.json: "%s[%d].hooks[%d]" must be an object, but it is %s. '
                    'Nothing was changed; fix or remove that entry.'
                    % (where, i, j, _jsontype(entry)))
    return groups


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


def validate_settings(settings):
    """Every shape check install depends on, run before anything is written."""
    hooks = _hooks_map(settings, strict=True)
    for event in ("UserPromptSubmit", "PostToolUse", "Stop"):
        _event_groups(hooks, event, strict=True)
    return settings


def merge_hooks(settings, app_home):
    """Add our two hook entries, replacing any previous copy of them.

    Other tools' hooks on the same events are preserved: we only ever remove
    entries whose command contains HOOK_MARKER.
    """
    hooks = _hooks_map(settings, strict=True)
    settings["hooks"] = hooks

    ups = _strip_marker(_event_groups(hooks, "UserPromptSubmit", True), HOOK_MARKER)
    ups.append({"hooks": [{"type": "command",
                           "command": _hook_cmd(app_home, "prompt"),
                           "timeout": 10}]})
    hooks["UserPromptSubmit"] = ups

    ptu = _strip_marker(_event_groups(hooks, "PostToolUse", True), HOOK_MARKER)
    ptu.append({"matcher": EDIT_MATCHER,
                "hooks": [{"type": "command",
                           "command": _hook_cmd(app_home, "edit"),
                           "timeout": 10}]})
    hooks["PostToolUse"] = ptu

    # Stop carries .last_assistant_message, which is where insight capture reads from.
    # Only wired when the script is present, so a checkout predating it still installs.
    if (Path(app_home) / "hooks" / "insight-capture.sh").exists():
        stop = _strip_marker(_event_groups(hooks, "Stop", True), INSIGHT_MARKER)
        stop.append({"hooks": [{"type": "command",
                                "command": _insight_cmd(app_home),
                                "timeout": 10}]})
        hooks["Stop"] = stop
    return settings


def remove_hooks(settings, preexisting=()):
    """Remove our hook entries, leaving everyone else's intact.

    ``preexisting`` names the events that already had a key before we installed, read
    back from the manifest. An event key of the user's that happened to hold an empty
    list is theirs and stays; one we created is removed with everything else of ours.

    Returns a note for the report. Never raises on a shape it cannot read: refusing to
    uninstall because some *other* key is malformed traps the user with the package
    installed and no way to remove it.
    """
    hooks = _hooks_map(settings, strict=False)
    if hooks is None:
        return ('left alone: "hooks" is not an object, so it holds no entry of ours '
                "(fix that key by hand if you did not mean it)")
    if not settings.get("hooks"):
        return "nothing to remove"
    unreadable = []
    for event, marker in (("UserPromptSubmit", HOOK_MARKER),
                          ("PostToolUse", HOOK_MARKER),
                          ("Stop", INSIGHT_MARKER)):
        if event not in hooks:
            continue
        groups = _event_groups(hooks, event, strict=False)
        if groups is None:
            unreadable.append(event)
            continue
        remaining = _strip_marker(groups, marker)
        if remaining or event in preexisting:
            hooks[event] = remaining     # an empty list the user put there stays theirs
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    if unreadable:
        return "removed ours; left alone (shape not readable): " + ", ".join(unreadable)
    return "removed ours"


# ------------------------------------------------------------------------ status line

def _statusline_command(entry):
    """The command out of a statusLine entry, whatever legal-ish shape it arrived in.

    A plain string used to raise AttributeError in both directions, which meant a user
    who had one could not remove this package at all. Removability wins: we read what
    is there and preserve it verbatim.
    """
    if isinstance(entry, dict):
        return str(entry.get("command", "")).strip()
    if isinstance(entry, str):
        return entry.strip()
    return ""


def _ours_statusline(app_home):
    return '"%s/statusline/statusline.sh"  %s' % (app_home, STATUSLINE_MARKER)


def _legacy_statusline(app_home):
    return '"%s/statusline/statusline.sh"' % app_home


def _statusline_home(command):
    """The directory of a bare `"<dir>/statusline/statusline.sh"` command, or None."""
    c = command.strip()
    if len(c) > 1 and c[0] == '"' and c[-1] == '"':
        c = c[1:-1]
    tail = "/statusline/statusline.sh"
    return c[:-len(tail)] if c.endswith(tail) else None


def install_statusline(settings, app_home, state_dir):
    """Point statusLine at our wrapper, preserving any existing status line.

    The previous command is written to ``<state>/statusline-base.sh`` and the original
    statusLine object is recorded in ``<state>/original-statusline.json`` so uninstall
    can put things back exactly as they were. Sibling keys the user set on statusLine
    (``padding`` and anything Claude Code grows later) are carried across unchanged.
    """
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    existing = settings.get("statusLine")
    ours = _ours_statusline(app_home)

    already = bool(existing) and _is_our_statusline(existing, app_home, state_dir)
    if not existing:
        # There is nothing to restore, so any record of a previous one is stale and must
        # go. Left behind, uninstall resurrected a status line the user had deleted by
        # hand, and the wrapper ran the dead command once a second in the meantime.
        for stale in (state / "original-statusline.json", state / "statusline-base.sh"):
            if stale.exists():
                stale.unlink()
    if existing and not already:
        # Preserve verbatim, as an executable script our wrapper can call.
        base = state / "statusline-base.sh"
        base.write_text(
            "#!/usr/bin/env bash\n"
            "# The status line configured before claude-skill-compounder was installed.\n"
            "# Preserved verbatim; statusline.sh calls this first.\n"
            + _statusline_command(existing) + "\n",
            encoding="utf-8")
        base.chmod(base.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        (state / "original-statusline.json").write_text(
            json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    entry = {}
    if isinstance(existing, dict):
        entry = {k: v for k, v in existing.items()
                 if k not in ("type", "command", "refreshInterval")}
    entry.update({"type": "command", "command": ours, "refreshInterval": 1})
    settings["statusLine"] = entry
    # Recorded so uninstall can still recognise our entry if the checkout has moved.
    (state / STATUSLINE_RECORD).write_text(json.dumps(entry, indent=2) + "\n",
                                           encoding="utf-8")
    return settings


def remove_statusline(settings, state_dir, app_home):
    """Restore the pre-install status line, or drop ours if there was none.

    Returns a note for the report, because "success" while leaving statusLine pointing
    at a script that no longer exists is the failure this reports against.
    """
    state = Path(state_dir)
    existing = settings.get("statusLine")
    if not existing:
        return "nothing to remove"
    if not _is_our_statusline(existing, app_home, state_dir):
        command = _statusline_command(existing)
        home = _statusline_home(command)
        if home and not Path(command.strip('"')).exists():
            return ("LEFT IN PLACE, but it points at %s, which does not exist. It is not "
                    "one of ours, so it was not touched -- check it by hand." % command)
        return "left yours in place"

    original = state / "original-statusline.json"
    if original.exists():
        try:
            settings["statusLine"] = json.loads(original.read_text(encoding="utf-8"))
            return "restored the status line you had before"
        except ValueError:
            pass
    settings.pop("statusLine", None)
    if (state / STATUSLINE_RECORD).exists() or state.exists():
        return "removed ours (you had no status line before)"
    return ("removed ours; your previous status line could not be restored because %s is "
            "gone -- it is in the settings backup above if you had one" % state)


def _is_our_statusline(entry, app_home, state_dir):
    """Never a substring of a path. Our own marker, then three location-bound fallbacks
    for entries written by versions that predate the marker."""
    command = _statusline_command(entry)
    if not command:
        return False
    if STATUSLINE_MARKER in command:
        return True
    if command == _legacy_statusline(app_home):
        return True
    record = Path(state_dir) / STATUSLINE_RECORD
    if record.exists():
        try:
            if command == json.loads(record.read_text(encoding="utf-8")).get("command"):
                return True
        except (ValueError, AttributeError):
            pass
    home = _statusline_home(command)
    return bool(home) and _is_our_checkout(home)


# -------------------------------------------------------------------------- manifest

def manifest_path(state_dir):
    return Path(state_dir) / MANIFEST


def read_manifest(state_dir):
    p = manifest_path(state_dir)
    if not p.exists():
        return {"app_home": "", "links": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"app_home": "", "links": {}}
    if not isinstance(data, dict):
        return {"app_home": "", "links": {}}
    if not isinstance(data.get("links"), dict):
        data["links"] = {}
    return data


def write_manifest(state_dir, manifest):
    p = manifest_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Unique per writer, for the reason write_settings gives: a fixed temp name lets two
    # concurrent runs delete each other's file and fail after everything else applied.
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".tmp-", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, str(p))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# -------------------------------------------------------------------------- symlinks

def _is_our_checkout(directory):
    """True only for a directory that literally contains this package's own source.

    This is what lets a link be recognised as ours no matter which clone made it: the
    file it points at is one of ours by construction, so adopting it cannot take
    anything from the user. A directory we cannot identify this way is not ours.
    """
    d = Path(directory)
    return ((d / "skill_compounder" / "installer.py").is_file()
            and (d / "skills" / "skill-compounder" / "SKILL.md").is_file())


def _link_target(link):
    """The absolute path a symlink names, without resolving it. Works when it dangles."""
    try:
        raw = os.readlink(str(link))
    except OSError:
        return None
    if not os.path.isabs(raw):
        raw = os.path.join(os.path.dirname(str(link)), raw)
    return os.path.normpath(raw)


def _points_into(link, app_home):
    """True when a symlink resolves to somewhere inside our own checkout.

    Kept as one of four ownership rules rather than the only one: on its own it is
    bound to the *current* app_home, so moving or re-cloning the checkout made every
    link this package created unrecognisable, in both directions at once.
    """
    try:
        target = os.path.realpath(str(link))
    except OSError:
        return False
    root = os.path.realpath(str(app_home)) + os.sep
    return (target + os.sep).startswith(root)


def _link_is_ours(dst, app_home, manifest):
    """Did *this package* create the symlink at dst? Four independent proofs.

    Identity is never "a link exists here" and never the shape of a path on its own.
    Someone whose own `no-silent-stub` is a link into their dotfiles had it replaced on
    install and removed on uninstall, with no warning at any point, and a rule that
    matched `<anything>/skills/<name>` would do that again. Each rule below is a proof
    of authorship:

    1. The manifest we wrote at install time names this destination and this target.
    2. ...or names this target under some other destination (the config dir moved).
    3. The target is inside the checkout running right now.
    4. The target lives in a directory that contains this package's own source, at the
       exact relative path we would have linked it from. The file it points at is ours.

    A dangling link with no manifest entry satisfies none of them, so it is left alone
    and reported rather than adopted.
    """
    dst = Path(dst)
    if not dst.is_symlink():
        return False
    target = _link_target(dst)
    if target is None:
        return False
    links = (manifest or {}).get("links") or {}
    key = os.path.normpath(os.path.abspath(str(dst)))
    if links.get(key) == target:
        return True
    if target in set(links.values()):
        return True
    if _points_into(dst, app_home):
        return True
    parent = os.path.dirname(target)
    home = os.path.dirname(parent)
    if (os.path.basename(target) == dst.name
            and os.path.basename(parent) in ("skills", "bin")
            and _is_our_checkout(home)):
        return True
    return False


def _symlink_force(src, dst, app_home, manifest):
    """Link src to dst, replacing only a link we can prove this package created.

    Everything else at that path belongs to the user and is left exactly where it is:
    a real directory, a real file, or a symlink of theirs pointing somewhere else.
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        if _link_target(dst) == os.path.normpath(os.path.abspath(str(src))):
            return "linked"                       # already exactly ours
        if not _link_is_ours(dst, app_home, manifest):
            return "skipped (your own link is there)"
        dst.unlink()                              # a link of ours into an older checkout
    elif dst.exists():
        return "skipped (something else is already there)"
    try:
        dst.symlink_to(str(src))
    except FileExistsError:
        # Another run of ours got there between the check and the call. If the result is
        # the link we wanted, that is success; reporting "could not be linked (File
        # exists)" for a link that is present and correct is a lie about the outcome.
        if dst.is_symlink() and _link_target(dst) == os.path.normpath(os.path.abspath(str(src))):
            return "linked"
        raise
    return "linked"


def _unlink_if_ours(dst, app_home, manifest):
    """Only remove a link we created. Never a real file the user put there."""
    dst = Path(dst)
    if not dst.exists() and not dst.is_symlink():
        return "absent"
    if _link_is_ours(dst, app_home, manifest):
        dst.unlink()
        return "removed"
    return "kept"


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


def _link_all(sources, dest_dir, app_home, manifest):
    """Link each source, reporting per name so a collision is visible rather than silent.

    An OSError mid-loop is reported against the name it happened to, not raised: half of
    an install plus a traceback tells the user nothing about which half.
    """
    linked, skipped, failed = [], [], []
    for src in sources:
        dst = Path(dest_dir) / src.name
        try:
            result = _symlink_force(src, dst, app_home, manifest)
        except OSError as exc:
            failed.append("%s (%s)" % (src.name, exc.strerror or exc))
            continue
        if result == "linked":
            linked.append(src.name)
            manifest.setdefault("links", {})[os.path.normpath(os.path.abspath(str(dst)))] = \
                os.path.normpath(os.path.abspath(str(src)))
        else:
            skipped.append(src.name)
    parts = []
    if linked:
        parts.append(", ".join(linked))
    if skipped:
        parts.append("NOT LINKED, you already have something by that name: "
                     + ", ".join(skipped))
    if failed:
        parts.append("NOT INSTALLED, could not be linked: " + ", ".join(failed))
    return "; ".join(parts) or "(none found)", failed


def _manifest_names(manifest, dest_dir):
    """Names this package linked into dest_dir on some earlier run.

    The shipped skills and CLIs are enumerated from the *current* checkout, so a name
    that was renamed or dropped upstream became invisible: `git pull`, reinstall,
    uninstall, and the old link stayed behind, dangling, with the report saying
    "removed" and exit 0. A dangling `skillreport` on PATH is a broken command.
    """
    root = os.path.normpath(os.path.abspath(str(dest_dir)))
    out = []
    for dest in (manifest or {}).get("links", {}):
        if os.path.dirname(os.path.normpath(dest)) == root:
            out.append(os.path.basename(dest))
    return sorted(set(out))


def _unlink_all(sources, dest_dir, app_home, manifest):
    """Report per name. A name that was never there is absent, not "not ours".

    A name in the manifest that this version does not ship is reported SEPARATELY. It is
    almost always a skill someone forged locally with `skillforge done`, and listing it
    among the shipped ones told its author their own work had been swept up as part of
    the package -- with no hint that the source is still on disk and re-linkable.
    """
    names = [src.name for src in sources]
    extra = [n for n in _manifest_names(manifest, dest_dir) if n not in names]
    buckets = {"removed": [], "kept": [], "absent": [], "failed": []}
    forged = []
    for name in names + extra:
        dst = Path(dest_dir) / name
        try:
            outcome = _unlink_if_ours(dst, app_home, manifest)
        except OSError as exc:
            buckets["failed"].append("%s (%s)" % (name, exc.strerror or exc))
            continue
        if outcome == "removed" and name in extra:
            forged.append(name)
        else:
            buckets[outcome].append(name)
        manifest.get("links", {}).pop(os.path.normpath(os.path.abspath(str(dst))), None)
    parts = []
    if buckets["removed"]:
        parts.append("removed: " + ", ".join(buckets["removed"]))
    if forged:
        parts.append("also unlinked, not shipped by this package — forged locally, or "
                     "renamed upstream: " + ", ".join(forged)
                     + " (the skill itself is untouched; re-link one with: skillforge "
                       "install <name> --skill-dir <where it is>)")
    if buckets["kept"]:
        parts.append("left in place (not ours): " + ", ".join(buckets["kept"]))
    if buckets["failed"]:
        parts.append("OURS BUT NOT REMOVED: " + ", ".join(buckets["failed"]))
    if buckets["absent"] and not buckets["removed"] and not buckets["kept"] and not forged:
        parts.append("nothing to remove")
    return "; ".join(parts) or "(none found)", buckets["failed"]


def _prune_retired(dest_dir, keep_names, app_home, manifest):
    """Remove links we made for names this version no longer ships, once they are dead.

    An upstream rename (`git pull`, then reinstall) left the old link behind pointing at
    a path that no longer exists -- a dangling command on PATH. Only a link that is
    provably ours *and* already broken is removed, so a name still served by another
    checkout is never pulled out from under it.
    """
    removed = []
    for name in _manifest_names(manifest, dest_dir):
        if name in keep_names:
            continue
        dst = Path(dest_dir) / name
        if not dst.is_symlink() or dst.exists():
            continue
        if not _link_is_ours(dst, app_home, manifest):
            continue
        try:
            dst.unlink()
        except OSError:
            continue
        manifest.get("links", {}).pop(os.path.normpath(os.path.abspath(str(dst))), None)
        removed.append(name)
    return removed


def _dangling_report(dest_dir, names):
    """Links at our names that point at nothing and that we could not prove are ours."""
    out = []
    for name in names:
        p = Path(dest_dir) / name
        if p.is_symlink() and not p.exists():
            out.append("%s -> %s" % (p, _link_target(p)))
    return out


# ------------------------------------------------------------------- install/uninstall

def install(app_home, claude_dir, bin_dir, state_dir=None):
    app_home = str(Path(app_home).resolve())
    claude_dir = Path(claude_dir)
    state_dir = str(state_dir or DEFAULT_STATE)
    settings_path = claude_dir / "settings.json"

    # Everything that can be checked is checked before anything is applied.
    settings = validate_settings(read_settings(settings_path))
    preflight(claude_dir, bin_dir, state_dir, settings_path, app_home)
    # Which event keys were already there, so uninstall can put back exactly what it found.
    preexisting = sorted(e for e in ("UserPromptSubmit", "PostToolUse", "Stop")
                         if e in (settings.get("hooks") or {}))

    report = {}
    report["backup"] = backup_settings(settings_path) or "(no existing settings.json)"

    merge_hooks(settings, app_home)
    install_statusline(settings, app_home, state_dir)
    write_settings(settings_path, settings)
    report["settings"] = str(settings_path)

    manifest = read_manifest(state_dir)
    manifest["app_home"] = app_home
    manifest["claude_dir"] = str(claude_dir)
    manifest["preexisting_hook_events"] = preexisting
    manifest["bin_dir"] = str(bin_dir)

    skills = _skill_dirs(app_home)
    clis = _cli_files(app_home)
    report["skills"], skill_failures = _link_all(skills, claude_dir / "skills",
                                                 app_home, manifest)
    report["cli"], cli_failures = _link_all(clis, Path(bin_dir), app_home, manifest)

    retired = (_prune_retired(claude_dir / "skills", [d.name for d in skills],
                              app_home, manifest)
               + _prune_retired(bin_dir, [f.name for f in clis], app_home, manifest))
    if retired:
        # NOT "from an earlier version": a link forged with `skillforge done` whose
        # source moved lands here too, and telling its owner it was a leftover from an
        # upgrade sends them looking in the wrong place for something they still want.
        report["retired"] = ("links of ours that had stopped pointing at anything, "
                             "removed: " + ", ".join(retired)
                             + " (a skill you forged is restored with: skillforge "
                               "install <name> --skill-dir <where it is now>)")
    write_manifest(state_dir, manifest)
    report["state"] = state_dir

    stray = (_dangling_report(claude_dir / "skills", [d.name for d in skills])
             + _dangling_report(bin_dir, [f.name for f in clis]))
    if stray:
        report["attention"] = ("these links point at nothing and are not ours, so they "
                               "were left alone: " + "; ".join(stray))
    if skill_failures or cli_failures:
        report["errors"] = ("this install is incomplete: "
                            + ", ".join(skill_failures + cli_failures))
    return report


def uninstall(app_home, claude_dir, bin_dir, state_dir=None):
    app_home = str(Path(app_home).resolve())
    claude_dir = Path(claude_dir)
    state_dir = str(state_dir or DEFAULT_STATE)
    settings_path = claude_dir / "settings.json"

    report = {}
    report["backup"] = backup_settings(settings_path) or "(no existing settings.json)"
    problems = []

    if _real_settings_path(settings_path).exists():
        try:
            settings = read_settings(settings_path)
        except SettingsShapeError as exc:
            # Never a reason to refuse: a settings.json we cannot parse is exactly when
            # a user most needs to be able to take this package off, and the links and
            # the state below come off regardless.
            settings = None
            report["settings"] = "LEFT ALONE: %s" % exc
            problems.append("our hook and statusLine entries are still in %s, because "
                            "it could not be parsed" % settings_path)
        if settings is not None:
            pre = read_manifest(state_dir).get("preexisting_hook_events") or ()
            report["hooks"] = remove_hooks(settings, pre)
            report["statusline"] = remove_statusline(settings, state_dir, app_home)
            write_settings(settings_path, settings)
            report["settings"] = str(settings_path)

    manifest = read_manifest(state_dir)
    skills = _skill_dirs(app_home)
    clis = _cli_files(app_home)
    report["skills"], skill_failures = _unlink_all(skills, claude_dir / "skills",
                                                   app_home, manifest)
    report["cli"], cli_failures = _unlink_all(clis, Path(bin_dir), app_home, manifest)
    if manifest_path(state_dir).exists():
        write_manifest(state_dir, manifest)

    names = ([d.name for d in skills] + _manifest_names(manifest, claude_dir / "skills"))
    binnames = [f.name for f in clis] + _manifest_names(manifest, bin_dir)
    stray = (_dangling_report(claude_dir / "skills", names)
             + _dangling_report(bin_dir, binnames))
    if stray:
        report["attention"] = ("these links point at nothing and could not be proved "
                               "ours, so they were left alone: " + "; ".join(stray))
    problems.extend(skill_failures + cli_failures)
    if problems:
        report["errors"] = "this uninstall is incomplete: " + ", ".join(problems)
    return report


# ------------------------------------------------------- installing one forged skill
#
# The installer above runs when someone installs the package. A skill forged DURING a
# session appears long after that, and until it is linked it does not exist as far as
# the session is concerned: `Skill(claim-provenance)` answered `Unknown skill` for a
# skill that had just passed a ten-round red-team loop, and the usage report showed it
# with 0 uses -- which reads as "nobody used it" when the truth is that nobody could.
#
# `skillforge done` calls link_skill() so that closing a forge is what makes the skill
# live. It is a separate entry point rather than a re-run of install() because a forge
# closes over a SINGLE skill that may live anywhere -- a personal directory, someone
# else's repository -- while install() is about this package's own checkout.
#
# What it must not do is decide that a name is free because something is merely sitting
# at it. Ownership is _link_is_ours and nothing else: the same four proofs of authorship
# install() uses, so there is one judgement in this codebase and not two.

def _default_app_home():
    """The checkout this module is running from."""
    return str(Path(__file__).resolve().parent.parent)


def _declared_skill_name(skill_dir):
    """The `name:` in a SKILL.md's frontmatter, or None.

    A directory called `aliased` whose frontmatter says `name: actual` installs under one
    name and announces itself under another, and which of the two a session can invoke is
    not something this function decides -- it only reports that the two disagree, which is
    always an authoring mistake worth surfacing at install time.
    """
    try:
        with open(str(Path(skill_dir) / "SKILL.md"), encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
            if first.strip() != "---":
                return None
            for _ in range(40):
                line = fh.readline()
                if not line or line.strip() == "---":
                    return None
                if line.startswith("name:"):
                    return line.split(":", 1)[1].strip().strip("'\"") or None
    except OSError:
        return None
    return None


def link_skill(skill_dir, skills_dir, app_home=None, state_dir=None):
    """Make one already-authored skill live: ``<skills_dir>/<name>`` -> ``skill_dir``.

    Returns a dict with ``status`` in:

    ``linked``          the link was created just now.
    ``already-linked``  the exact link was already there. Closing a forge twice, or
                        forging a name that is already installed, lands here.
    ``already-there``   the skill already lives inside skills_dir under its own name.
    ``refused``         something we cannot prove we created holds that name. Nothing
                        was touched, and the caller has to say so out loud.
    ``failed``          the link could not be written (a read-only directory, say).

    Never raises for a collision -- a collision is an outcome to report, not a crash.
    Raises InstallError only when the caller pointed at something that is not a skill.
    """
    src = Path(skill_dir)
    if not (src / "SKILL.md").is_file():
        raise InstallError("%s holds no SKILL.md, so there is no skill to install there"
                           % src)
    name = src.name
    dest_dir = Path(skills_dir)
    dst = dest_dir / name
    state_dir = str(state_dir or DEFAULT_STATE)
    app_home = str(Path(app_home).resolve()) if app_home else _default_app_home()

    target = os.path.normpath(os.path.abspath(str(src)))
    result = {"name": name, "dest": str(dst), "target": target, "skills_dir": str(dest_dir)}
    declared = _declared_skill_name(src)
    if declared and declared != name:
        result["declared_name"] = declared

    if os.path.normpath(os.path.abspath(str(dst))) == target:
        result["status"] = "already-there"
        result["message"] = "%s already lives in %s" % (name, dest_dir)
        return result

    manifest = read_manifest(state_dir)
    # Distinguished BEFORE the call: _symlink_force reports "linked" for a link it just
    # made and for one that was already exactly right, and a caller that says "installed"
    # on every second `done` is telling the user something happened when nothing did.
    was_there = dst.is_symlink() and _link_target(dst) == target
    # A link of OURS pointing somewhere else is legitimately replaced -- a second
    # checkout, a moved repository -- but replacing it is a thing that HAPPENED, and a
    # report that mentions only the new target hides which skill just stopped being the
    # one that answers to this name.
    displaced = None
    if dst.is_symlink() and not was_there and _link_is_ours(dst, app_home, manifest):
        displaced = _link_target(dst)

    try:
        outcome = _symlink_force(src, dst, app_home, manifest)
    except OSError as exc:
        result["status"] = "failed"
        result["message"] = "%s could not be created (%s)" % (dst, exc.strerror or exc)
        return result

    if outcome != "linked":
        result["status"] = "refused"
        result["message"] = (
            "%s is already taken by something this package did not create (%s). "
            "Nothing was changed." % (dst, outcome.replace("skipped ", "").strip("()")))
        return result

    result["status"] = "already-linked" if was_there else "linked"
    result["message"] = "%s -> %s" % (dst, target)
    if displaced:
        result["displaced"] = displaced
    # Recorded for the same reason install() records its links: it is proof #1 of
    # authorship, so a later uninstall removes this link instead of leaving it dangling,
    # and a re-forge from a moved checkout still recognises it as ours.
    manifest.setdefault("links", {})[os.path.normpath(os.path.abspath(str(dst)))] = target
    # read_manifest seeds an empty string, which setdefault would happily keep; a real
    # app_home already there came from an install and is the authoritative one.
    if not manifest.get("app_home"):
        manifest["app_home"] = app_home
    try:
        write_manifest(state_dir, manifest)
    except OSError as exc:
        # The link is live either way; say what was not recorded rather than pretending.
        result["warning"] = "the link was made but not recorded in %s (%s)" % (
            manifest_path(state_dir), exc.strerror or exc)
    return result


_LINK_EXIT = {"linked": 0, "already-linked": 0, "already-there": 0,
              "refused": 3, "failed": 4, "error": 5}


def _main(argv):
    """`python3 installer.py link-skill --skill-dir P --skills-dir D [...]`.

    Exists so that `skillforge` -- shell and jq everywhere else -- can reuse the
    ownership judgement above instead of reimplementing four proofs in bash, where the
    second implementation would inevitably be the weaker one. Always prints one JSON
    object, so the shell side never has to parse prose.
    """
    if not argv or argv[0] != "link-skill":
        sys.stderr.write("usage: installer.py link-skill --skill-dir <dir> "
                         "--skills-dir <dir> [--app-home <dir>] [--state-dir <dir>]\n")
        return 2
    opts = {}
    rest = argv[1:]
    while rest:
        key = rest.pop(0)
        if not key.startswith("--"):
            sys.stderr.write("installer.py: unexpected argument %r\n" % key)
            return 2
        if "=" in key:
            key, value = key.split("=", 1)
        elif rest:
            value = rest.pop(0)
        else:
            sys.stderr.write("installer.py: %s needs a value\n" % key)
            return 2
        opts[key[2:].replace("-", "_")] = value
    missing = [k for k in ("skill_dir", "skills_dir") if not opts.get(k)]
    if missing:
        sys.stderr.write("installer.py: missing --%s\n" % ", --".join(missing))
        return 2
    try:
        out = link_skill(opts["skill_dir"], opts["skills_dir"],
                         app_home=opts.get("app_home") or None,
                         state_dir=opts.get("state_dir") or None)
    except InstallError as exc:
        out = {"status": "error", "message": str(exc), "name": Path(opts["skill_dir"]).name,
               "dest": str(Path(opts["skills_dir"]) / Path(opts["skill_dir"]).name)}
    except OSError as exc:
        out = {"status": "error", "message": str(exc), "name": Path(opts["skill_dir"]).name,
               "dest": str(Path(opts["skills_dir"]) / Path(opts["skill_dir"]).name)}
    sys.stdout.write(json.dumps(out) + "\n")
    return _LINK_EXIT.get(out["status"], 5)


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
