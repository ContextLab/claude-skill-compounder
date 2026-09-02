"""Install / uninstall claude-skill-compounder into a Claude Code configuration.

Everything here is pure filesystem + JSON work against a caller-supplied
``claude_dir``, so the tests exercise the real code paths against a real temporary
Claude directory rather than a mock.

What gets wired:

* ``hooks.UserPromptSubmit``     -> compound-improvement.sh prompt (section 1 reminder)
* ``hooks.PostToolUse``          -> compound-improvement.sh edit   (section 2 reminder)
* ``hooks.PostToolUse``          -> skill-use.sh ok                (one `use` row per
                                                                    skill invocation)
* ``hooks.PostToolUseFailure``   -> skill-use.sh fail              (the same, for the
                                                                    invocations that did
                                                                    not run)
* ``hooks.PreToolUse``           -> claim-gate.sh (matcher Bash)   (denies a `git commit`
                                                                    whose message asserts
                                                                    a figure the session
                                                                    never produced)
* ``hooks.Stop``                 -> insight-capture.sh             (skill-candidate queue)
* ``hooks.Stop``                 -> claim-gate.sh                  (the same check on the
                                                                    closing message)
* ``statusLine``              -> statusline.sh                    (forge animation)
* ``CLAUDE.md``               -> the doctrine stanza              (inside a marker block,
                                                                    so the habits the
                                                                    hooks name are
                                                                    written where the
                                                                    model reads them)
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
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Markers identify our entries so install is idempotent and uninstall is surgical.
HOOK_MARKER = "compound-improvement.sh"
INSIGHT_MARKER = "insight-capture.sh"
# The end-of-turn claim gate, wired to the two events it acts on. `Stop` gates the closing
# message; `PreToolUse`/`Bash` gates a `git commit` message, and that second arm is not a
# nicety -- a commit message never appears in `last_assistant_message`, so a Stop wiring
# alone cannot see it, and both founding incidents were commit messages.
# The script also carries a `PostToolUse` accumulator arm, and it is deliberately NOT
# wired. That arm records every long integer out of a tool RESULT, including an Agent/Task
# result, and a subagent's report is exactly the testimony the Stop arm cuts out of its
# evidence on purpose ("the load-bearing exclusion", hooks/claim-gate.sh). Feeding it back
# in would make the gate stop catching relayed figures, which is the defect it exists for.
# The script's own header agrees from the other side: the session-wide transcript scan
# measured 0.22 s, "which is why the PostToolUse accumulator is optional rather than
# required". If it is ever wired, it needs a matcher that excludes Agent and Task.
CLAIM_GATE_MARKER = "claim-gate.sh"
# One `use` row per Skill invocation, which is how the ledger answers "when has it been
# used since". Wired to two events, not one: `PostToolUse` fires only when the tool
# succeeded, and a failure arrives as `PostToolUseFailure` (measured, 2.1.245). A
# success-only wiring would record every failed invocation as a use.
USE_MARKER = "skill-use.sh"
# THE THREE GATES ISSUE #19 ADDED, and each is wired to the events it can act on.
#
# `repeat-gate.sh` is the only entry of ours on THREE events at once, because the thing it
# recognises is a sequence rather than a moment: a failure (PostToolUseFailure), the call
# that worked instead (PostToolUse), and the next attempt at the failure (PreToolUse). Drop
# any one wiring and it degrades silently -- without the failure arm it learns nothing,
# without the success arm every deny is "this failed before" with no workaround to offer,
# and without the PreToolUse arm it is a log nobody reads.
REPEAT_GATE_MARKER = "repeat-gate.sh"
# `doc-gate.sh` denies a `git push` carrying code changes and no documentation change. Same
# event and same matcher as the claim gate's commit arm, and for the same reason: a matcher
# selects a tool, never a command, so which Bash commands are pushes is decided in-script.
DOC_GATE_MARKER = "doc-gate.sh"
# `apply-gate.sh` blocks the end of a turn that forged a skill and never used it. Issue #19
# asks for a notification at that moment; the measurement in that issue's own thread is that
# notifications at that moment are read past, so it refuses instead.
APPLY_GATE_MARKER = "apply-gate.sh"
# `remind.sh` delivers a reminder recorded by `skillnote add --remind` at the moment its
# match rule fires. Two events, because a reminder can be keyed to a prompt (keywords) or
# to a call about to happen (a command signature, a path glob), and those arrive on
# different events. It denies nothing on either: it emits `additionalContext`, which is
# the field measured to reach the model on both events (docs/CLAUDE-CODE-BEHAVIOR.md,
# CLI 2.1.258). ONE PreToolUse entry covers all three tools it acts on, dispatching on
# `.tool_name` in-script; three entries would triple the deliveries for the same work.
REMIND_MARKER = "remind.sh"
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
# PostToolUse matches on the tool name, so the matcher for skill invocations is literally
# the tool's name. Verified by dumping the payload of a real `Skill` call on 2.1.245.
SKILL_MATCHER = "Skill"
# PreToolUse matches on the tool name as well, so the claim gate's commit arm can only ask
# for `Bash`. Which Bash commands are commits is decided inside the script, which exits 0
# on everything else; a matcher cannot express it.
COMMIT_MATCHER = "Bash"
# The repeat gate runs on every delivery of three events, so its matcher is a COST BOUND as
# much as a filter. `Bash|Skill` covers both failures issue #19 names by example -- a broken
# built-in retried as a `gh` command, and a skill that does not connect -- while leaving the
# high-frequency read tools (Read, Grep, Glob) out of the stream entirely. MCP tool names
# are deliberately NOT matched: `mcp__.*` may well work, but nothing here has measured that
# a matcher regex is applied to an MCP tool name, and a wiring that silently matches nothing
# is worse than one that admits its scope. Widening it is this one string.
REPEAT_MATCHER = "Bash|Skill"
# The reminder hook's PreToolUse matcher. Deliberately NOT `EDIT_MATCHER`, which is the
# same three tools in a different order: these are two independent decisions about two
# different scripts, and sharing the constant would make a change to one silently rewire
# the other. `Bash` for the command arm, `Write|Edit` for the path arm.
REMIND_MATCHER = "Bash|Write|Edit"
LEDGER = "ledger.jsonl"
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

def _real_file_path(path):
    """The regular file a configured path ultimately names.

    stow, chezmoi and hand-rolled dotfiles all present ``settings.json`` -- and
    ``CLAUDE.md``, which is the same kind of file to the same tools -- as a symlink into
    a dotfiles repo. ``os.replace`` onto the link would delete it and leave a regular
    file, orphaning the source with exit 0 and no warning, so every write resolves the
    link first and writes *through* it.
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


def backup_file(path):
    """Copy a file we are about to rewrite aside. Returns the backup path or None.

    Used for ``settings.json`` and for ``CLAUDE.md``: both are files of the user's that
    this package edits in place, and both deserve the same stamped copy first.

    The copy lands beside the *configured* path rather than beside a dotfiles source,
    so a symlinked settings.json does not sprinkle backups through someone's git repo.
    An identical backup is never written twice, and only our own timestamped copies are
    ever pruned.
    """
    p = Path(path)
    real = _real_file_path(p)
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


def write_text_file(path, text):
    """Write ``text`` atomically, so an interrupted install cannot leave a truncated
    file (a malformed settings.json disables every setting in it, and a half-written
    CLAUDE.md is prose the model reads as if it were finished).

    Writes through a symlink rather than over it: the temp file is created beside the
    resolved target so ``os.replace`` stays on one filesystem and the link survives.
    """
    real = _real_file_path(path)
    real.parent.mkdir(parents=True, exist_ok=True)
    # A fixed temp name lets two concurrent runs interleave their bytes in one file and
    # then rename the result into place, so the name is unique per writer.
    fd, tmp = tempfile.mkstemp(prefix=real.name + ".tmp-", dir=str(real.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o600 if not real.exists() else stat.S_IMODE(real.stat().st_mode))
        os.replace(tmp, str(real))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_settings(path, settings):
    """settings.json, through write_text_file above."""
    write_text_file(path, json.dumps(settings, indent=2) + "\n")


# --------------------------------------------------------------------------- doctrine
#
# The hooks fire reminders that name three habits ("check for an existing skill first",
# "notice what is costly AND recurring", "never work around a misfiring skill"). Until
# this section existed, those habits were written down in exactly one place: a stanza the
# author had hand-typed into his own ~/.claude/CLAUDE.md. Every other installation got the
# reminders and not the doctrine, so a hook was telling a session to apply a rule the
# session had never been given. Wiring the behaviour without the rule it refers to is the
# defect; this writes the rule where the model actually reads it.
#
# It goes into <claude-dir>/CLAUDE.md between two HTML comment markers, and the block is
# the unit: replaced in place on the next install, removed whole on uninstall, and
# invisible when the file is rendered. Anything outside the markers is the user's and is
# never rewritten.

DOCTRINE_FILE = "CLAUDE.md"
DOCTRINE_START = "<!-- claude-skill-compounder:doctrine:start -->"
DOCTRINE_END = "<!-- claude-skill-compounder:doctrine:end -->"
# The heading the stanza opens with, and the one thing that says a user has already
# written this doctrine down by hand. See install_doctrine().
DOCTRINE_HEADING = "## Compound Improvement"

# The doctrine itself, and the only copy of it in this repository. README.md describes
# what gets written and points here rather than restating it, because a second copy is a
# second thing to keep in step and the one nobody edits is the one a reader finds first.
# `{app_home}` is substituted with this checkout's path -- the stanza names the clone
# twice, and a hardcoded ~/claude-skill-compounder is wrong for anyone who cloned
# somewhere else.
DOCTRINE_TEXT = """\
## Compound Improvement

Every session should leave the toolchain measurably better than it found it, so the same
problem is never solved from scratch twice. The full protocol lives in the
**`skill-compounder`** skill (installed from https://github.com/ContextLab/claude-skill-compounder,
clone at `{app_home}`). Invoke the skill rather than working from memory —
it is the single source of truth and it evolves.

Three standing habits, so the recognition can fire without loading the skill first:

1. **Before any major implementation**, check whether an existing skill already solves it
   before writing a plan or any code.
2. **During work**, watch for procedures that are BOTH costly — you can name the specific
   dead end in one sentence — AND recurring, meaning you can point at the second
   occurrence. Both need a concrete referent, not a judgement: if either sentence is hard
   to write, that is the answer. Both, or it gets a note instead of a skill.
3. **When a skill misfires**, never silently work around it: fix the wording, or fix the
   procedure and re-red-team it, or retire it — retirement only with independent
   concurrence from a second fresh agent asked a neutral question.

When any of these fires, invoke `skill-compounder` and follow it exactly. It carries the
builder/red-team loop, the `skillforge` progress animation, and the retirement protocol.
The loop runs in an orchestrator subagent, not in the main thread: announce it, start the
forge, hand it off, and close it when the orchestrator reports. The red-teamer must never
be a fork of either layer — not of the orchestrator that dispatches it, and not of the
session that dispatched the orchestrator. A forked reviewer already knows what the skill
was meant to say, so it cannot find the ambiguity that will bite a cold session later; each
round needs a genuinely new reviewer, because after round one the previous one is no longer
cold.

Two hooks in `settings.json` surface these reminders automatically during long sessions
(they point at `{app_home}/hooks/compound-improvement.sh`). If they become
noise, tune `CI_EDIT_EVERY` / `CI_PROMPT_COOLDOWN` / `CI_PROMPT_MIN_CHARS` there rather
than disabling them.
"""


def doctrine_path(claude_dir):
    return Path(claude_dir) / DOCTRINE_FILE


def render_doctrine(app_home):
    """The block exactly as it is written to disk, with no trailing newline."""
    body = DOCTRINE_TEXT.replace("{app_home}", str(app_home)).strip("\n")
    return "%s\n%s\n%s" % (DOCTRINE_START, body, DOCTRINE_END)


UNTERMINATED = "unterminated"


def _doctrine_span(text):
    """Where our block sits in ``text``: (start, end), None, or ``UNTERMINATED``.

    A start marker with no end is not a block we may guess the extent of. Appending a
    fresh one would nest a block inside a block and removing "the block" would take an
    unknown amount of the user's file with it, so that case is reported and left alone.
    """
    i = text.find(DOCTRINE_START)
    if i < 0:
        return None
    j = text.find(DOCTRINE_END, i)
    if j < 0:
        return UNTERMINATED
    return (i, j + len(DOCTRINE_END))


def _doctrine_enabled(explicit=None):
    """An explicit False -- what a `--no-doctrine` flag would pass -- beats the
    environment; both default to on, because the reminders ship on and the rule they
    name has to ship with them."""
    if explicit is not None:
        return bool(explicit)
    value = os.environ.get("SKILL_COMPOUNDER_DOCTRINE", "").strip().lower()
    return value not in ("0", "no", "off", "false")


def install_doctrine(claude_dir, app_home, manifest, enabled=None):
    """Put the doctrine block in <claude-dir>/CLAUDE.md. Returns one report sentence.

    Four outcomes, all recorded in the manifest under ``doctrine`` so uninstall knows
    what it is undoing:

    * ``installed``   -- the block was written, or was already byte-for-byte current.
    * ``user-owned``  -- the file already carries a `## Compound Improvement` section of
      its own, outside our markers. That is the author's own machine, and it is the
      common case for anyone who followed the README before this existed. Appending
      would give them the doctrine twice, so nothing is written.
    * ``declined``    -- --no-doctrine / SKILL_COMPOUNDER_DOCTRINE=0.
    * ``left-alone``  -- an unterminated marker; see _doctrine_span.

    Never raises for the file's contents: a CLAUDE.md we do not understand is a reason
    to leave it alone and say so, not a reason to fail an install that is otherwise fine.
    """
    path = doctrine_path(claude_dir)
    if not _doctrine_enabled(enabled):
        manifest["doctrine"] = "declined"
        # Both causes named, because either one can be the reason and the report cannot
        # tell them apart: `--no-doctrine` reaches here as `enabled=False` and the
        # variable reaches here as an unset `enabled`. Naming only the variable told a
        # user who passed the flag that something in their environment had done it.
        return ("not written (opted out: --no-doctrine or "
                "SKILL_COMPOUNDER_DOCTRINE=0)")

    real = _real_file_path(path)
    existed = real.exists()
    text = real.read_text(encoding="utf-8") if existed else ""
    span = _doctrine_span(text)
    if span == UNTERMINATED:
        manifest["doctrine"] = "left-alone"
        return ("LEFT ALONE: %s carries %s with no matching end marker, so where our "
                "block stops cannot be known. Close it or delete it and run this again."
                % (path, DOCTRINE_START))

    # The heading is looked for OUTSIDE our own block, or our own copy would be read as
    # the user's on every install after the first and the block would never be updated.
    outside = text if span is None else text[:span[0]] + text[span[1]:]
    if DOCTRINE_HEADING in outside:
        manifest["doctrine"] = "user-owned"
        return ("left to you: %s already has its own '%s' section, so nothing was added"
                % (path, DOCTRINE_HEADING))

    block = render_doctrine(app_home)
    if span is None:
        head = text.rstrip("\n")
        new = (head + "\n\n" if head else "") + block + "\n"
    else:
        new = text[:span[0]] + block + text[span[1]:]

    manifest["doctrine"] = "installed"
    if not existed:
        manifest["doctrine_created"] = True
    elif "doctrine_created" not in manifest:
        manifest["doctrine_created"] = False
    if new == text:
        # Byte-identical: no write, so no backup either. A run that changes nothing
        # should not push a real pre-install copy out of the ten we keep.
        return "%s (already current)" % path
    backup = backup_file(path)
    write_text_file(path, new)
    return "%s (%s)" % (path, "backup %s" % backup if backup else "created")


def remove_doctrine(claude_dir, manifest):
    """Take our block back out, and nothing else. Returns one report sentence."""
    path = doctrine_path(claude_dir)
    real = _real_file_path(path)
    if not real.exists():
        return "(no %s)" % path
    text = real.read_text(encoding="utf-8")
    span = _doctrine_span(text)
    if span is None:
        return "no block of ours in %s; left alone" % path
    if span == UNTERMINATED:
        return ("LEFT ALONE: %s carries %s with no matching end marker; remove it by "
                "hand." % (path, DOCTRINE_START))

    prefix = text[:span[0]].rstrip("\n")
    suffix = text[span[1]:].lstrip("\n")
    if prefix and suffix:
        new = prefix + "\n\n" + suffix
    elif prefix:
        new = prefix + "\n"
    else:
        new = suffix

    backup = backup_file(path)
    created = bool(manifest.get("doctrine_created"))
    # Delete only a file that is ours to delete: we created it, nothing of anyone else's
    # is left in it, and it is a regular file. A symlink here means the user pointed the
    # name at a dotfiles repo after we made the file, and unlinking the target would take
    # a file we never created.
    if created and not new.strip() and not path.is_symlink():
        real.unlink()
        removed = "%s removed (we created it and nothing else was in it)" % path
    else:
        write_text_file(path, new)
        removed = "block removed from %s" % path
    manifest.pop("doctrine", None)
    manifest.pop("doctrine_created", None)
    return removed + ("" if not backup else "; backup %s" % backup)

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


def preflight(claude_dir, bin_dir, state_dir, settings_path, app_home=None,
              doctrine=None):
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
                     ("the settings directory", _real_file_path(settings_path).parent)):
        reason = _probe_writable(d)
        if reason:
            problems.append("%s: %s" % (label, reason))
    real = _real_file_path(settings_path)
    if real.exists() and not os.access(str(real), os.W_OK):
        problems.append("settings.json is not writable: %s" % real)
    if _doctrine_enabled(doctrine):
        md = _real_file_path(doctrine_path(claude_dir))
        if md.exists() and not os.access(str(md), os.W_OK):
            problems.append("CLAUDE.md is not writable: %s (or install with "
                            "SKILL_COMPOUNDER_DOCTRINE=0)" % md)
    problems.extend(_executable_problems(app_home) if app_home else [])
    if problems:
        raise InstallError("nothing was installed, because:\n  - " + "\n  - ".join(problems))


# ----------------------------------------------------------------------------- hooks

def _hook_cmd(app_home, mode):
    return '"%s/hooks/compound-improvement.sh" %s' % (app_home, mode)


def _insight_cmd(app_home):
    return '"%s/hooks/insight-capture.sh"' % app_home


def _claim_gate_cmd(app_home):
    return '"%s/hooks/claim-gate.sh"' % app_home


def _has_claim_gate(app_home):
    """A checkout predating the claim gate still installs, minus those two wirings."""
    return (Path(app_home) / "hooks" / "claim-gate.sh").exists()


def _use_cmd(app_home, mode):
    return '"%s/hooks/skill-use.sh" %s' % (app_home, mode)


def _has_use_hook(app_home):
    """A checkout predating the use hook still installs, minus that one wiring."""
    return (Path(app_home) / "hooks" / "skill-use.sh").exists()


def _gate_cmd(app_home, script):
    return '"%s/hooks/%s"' % (app_home, script)


def _has_gate(app_home, script):
    """A checkout predating one of the issue-#19 gates still installs, minus its wiring.

    Same judgement as _has_claim_gate and _has_use_hook, factored because there are now
    three of them: the package must remain installable from a checkout older than any
    individual component, and the alternative -- refusing to install because one script is
    absent -- turns a partial upgrade into no upgrade at all.
    """
    return (Path(app_home) / "hooks" / script).exists()


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


OUR_EVENTS = ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
              "Stop")
# Two events carry two entries of ours -- PostToolUse the edit checkpoint and the
# skill-use recorder, Stop the insight capture and the claim gate -- so the markers are a
# tuple per event. Stripping only the first would leave the second wired to a checkout the
# user had just removed.
OUR_EVENT_MARKERS = (("UserPromptSubmit", (HOOK_MARKER, REMIND_MARKER)),
                     ("PreToolUse", (CLAIM_GATE_MARKER, DOC_GATE_MARKER,
                                     REPEAT_GATE_MARKER, REMIND_MARKER)),
                     ("PostToolUse", (HOOK_MARKER, USE_MARKER, REPEAT_GATE_MARKER)),
                     ("PostToolUseFailure", (USE_MARKER, REPEAT_GATE_MARKER)),
                     ("Stop", (INSIGHT_MARKER, CLAIM_GATE_MARKER, APPLY_GATE_MARKER)))


def preexisting_events(settings, recorded=()):
    """Which of our event keys are the USER'S, so uninstall puts back what it found.

    "Was the key there before we ran" is the obvious rule and it is wrong on the second
    install: by then every key we created on the first is there too, so a reinstall
    recorded our own keys as the user's and uninstall left a row of empty lists behind in
    their settings. Measured before this rule existed, on a config that started with only
    a PreToolUse hook of the user's: install, install, uninstall left `UserPromptSubmit`,
    `PostToolUse`, `PostToolUseFailure` and `Stop` all present and all `[]`.

    A key is the user's if it holds anything that is not ours, or if it holds no entry of
    ours at all -- which is how an empty list they put there stays theirs. ``recorded`` is
    what a previous install wrote to the manifest, unioned in and never subtracted: over-
    preserving leaves an empty key, under-preserving deletes a key of theirs, and only one
    of those is destructive.
    """
    hooks = settings.get("hooks") or {}
    if not isinstance(hooks, dict):
        return sorted(set(recorded) & set(OUR_EVENTS))
    out = set(e for e in recorded if e in OUR_EVENTS)
    for event, markers in OUR_EVENT_MARKERS:
        if event not in hooks:
            continue
        groups = _event_groups(hooks, event, strict=False)
        if groups is None:
            out.add(event)            # a shape we cannot read is not one we created
            continue
        remaining = groups
        for marker in markers:
            remaining = _strip_marker(remaining, marker)
        if remaining or len(remaining) == len(groups):
            out.add(event)
    return sorted(out)


def validate_settings(settings):
    """Every shape check install depends on, run before anything is written."""
    hooks = _hooks_map(settings, strict=True)
    for event in OUR_EVENTS:
        _event_groups(hooks, event, strict=True)
    return settings


def merge_hooks(settings, app_home):
    """Add our hook entries, replacing any previous copy of them.

    Other tools' hooks on the same events are preserved: we only ever remove
    entries whose command contains one of our markers.
    """
    hooks = _hooks_map(settings, strict=True)
    settings["hooks"] = hooks

    ups = _strip_marker(_event_groups(hooks, "UserPromptSubmit", True), HOOK_MARKER)
    # Stripped BEFORE anything is appended, like every other marker here, so an entry an
    # older checkout left behind is never found sitting beside a fresh one.
    ups = _strip_marker(ups, REMIND_MARKER)
    ups.append({"hooks": [{"type": "command",
                           "command": _hook_cmd(app_home, "prompt"),
                           "timeout": 10}]})
    if _has_gate(app_home, "remind.sh"):
        ups.append({"hooks": [{"type": "command",
                               "command": _gate_cmd(app_home, "remind.sh"),
                               "timeout": 10}]})
    hooks["UserPromptSubmit"] = ups

    # The claim gate's commit arm. PreToolUse is a *decision* event: this is the only
    # entry of ours that can deny a tool call, and the only one wired to an event the user
    # may already be using for permission rules of their own, so the marker strip matters
    # here as much as the append does.
    #
    # Three of our entries now live on PreToolUse and all three can deny. Every marker is
    # stripped before any is appended, so an entry left by an older checkout is never found
    # sitting beside a fresh one -- and the strip is per marker, so a gate whose script is
    # missing from this checkout has its stale entry removed rather than left orphaned
    # pointing at a file that is gone.
    pre = _event_groups(hooks, "PreToolUse", True)
    for _m in (CLAIM_GATE_MARKER, DOC_GATE_MARKER, REPEAT_GATE_MARKER, REMIND_MARKER):
        pre = _strip_marker(pre, _m)
    _pre_wired = False
    if _has_claim_gate(app_home):
        pre.append({"matcher": COMMIT_MATCHER,
                    "hooks": [{"type": "command",
                               "command": _claim_gate_cmd(app_home),
                               "timeout": 10}]})
        _pre_wired = True
    if _has_gate(app_home, "doc-gate.sh"):
        pre.append({"matcher": COMMIT_MATCHER,
                    "hooks": [{"type": "command",
                               "command": _gate_cmd(app_home, "doc-gate.sh"),
                               "timeout": 10}]})
        _pre_wired = True
    if _has_gate(app_home, "repeat-gate.sh"):
        pre.append({"matcher": REPEAT_MATCHER,
                    "hooks": [{"type": "command",
                               "command": _gate_cmd(app_home, "repeat-gate.sh"),
                               "timeout": 10}]})
        _pre_wired = True
    # LAST of the four, and the order is pinned by tests/test_plugin.py, which compares the
    # two wirings' matcher lists POSITIONALLY. It is also the only PreToolUse entry of ours
    # that cannot deny: the three gates above decide, this one states a fact.
    if _has_gate(app_home, "remind.sh"):
        pre.append({"matcher": REMIND_MATCHER,
                    "hooks": [{"type": "command",
                               "command": _gate_cmd(app_home, "remind.sh"),
                               "timeout": 10}]})
        _pre_wired = True
    # `or "PreToolUse" in hooks` IS THE WHOLE OF A FIX, and the bug it closes was silent.
    # `_strip_marker` returns a NEW list, so the strip above only takes effect when this
    # assignment runs. Guarded on `_pre_wired or pre` alone, a checkout missing every
    # PreToolUse gate stripped its stale entries into a list nobody wrote back, and the
    # ORIGINAL list -- stale entry still in it, pointing at a script that is gone --
    # stayed in settings.json. The partial case always worked, because one surviving gate
    # makes `_pre_wired` true, which is why it went unnoticed. `remove_hooks` below had
    # this right all along; these three sites now match it.
    if _pre_wired or pre or "PreToolUse" in hooks:
        hooks["PreToolUse"] = pre

    ptu = _strip_marker(_event_groups(hooks, "PostToolUse", True), HOOK_MARKER)
    ptu = _strip_marker(ptu, USE_MARKER)
    ptu = _strip_marker(ptu, REPEAT_GATE_MARKER)
    ptu.append({"matcher": EDIT_MATCHER,
                "hooks": [{"type": "command",
                           "command": _hook_cmd(app_home, "edit"),
                           "timeout": 10}]})
    if _has_use_hook(app_home):
        ptu.append({"matcher": SKILL_MATCHER,
                    "hooks": [{"type": "command",
                               "command": _use_cmd(app_home, "ok"),
                               "timeout": 10}]})
    # The repeat gate's recovery arm: the success that followed a failure is the only place
    # the workaround can be observed, and observing it is what makes the deny useful rather
    # than merely obstructive.
    if _has_gate(app_home, "repeat-gate.sh"):
        ptu.append({"matcher": REPEAT_MATCHER,
                    "hooks": [{"type": "command",
                               "command": _gate_cmd(app_home, "repeat-gate.sh"),
                               "timeout": 10}]})
    hooks["PostToolUse"] = ptu

    # The failure twin. Wiring only the success event does not merely miss failures, it
    # records each one as a success, which is a wrong number rather than a missing one.
    ptf = _strip_marker(_event_groups(hooks, "PostToolUseFailure", True), USE_MARKER)
    ptf = _strip_marker(ptf, REPEAT_GATE_MARKER)
    _ptf_wired = False
    if _has_use_hook(app_home):
        ptf.append({"matcher": SKILL_MATCHER,
                    "hooks": [{"type": "command",
                               "command": _use_cmd(app_home, "fail"),
                               "timeout": 10}]})
        _ptf_wired = True
    # This is the arm the repeat gate learns from. It is also the ONLY event that carries
    # both the failing command and the error text: measured 2026-08-26 on 2.1.246, the
    # payload holds tool_input and an `error` field reading "Exit code 1\n<stderr>", and a
    # failed Bash call fires no PostToolUse at all.
    if _has_gate(app_home, "repeat-gate.sh"):
        ptf.append({"matcher": REPEAT_MATCHER,
                    "hooks": [{"type": "command",
                               "command": _gate_cmd(app_home, "repeat-gate.sh"),
                               "timeout": 10}]})
        _ptf_wired = True
    if _ptf_wired or ptf or "PostToolUseFailure" in hooks:
        hooks["PostToolUseFailure"] = ptf

    # Stop carries .last_assistant_message, which is where both of our Stop hooks read
    # from: insight capture, and the claim gate. Each is wired only when its own script is
    # present, so a checkout predating either still installs. Both markers are stripped
    # before either is appended, so an entry of ours from an older checkout is never left
    # sitting beside a fresh one.
    stop = _strip_marker(_event_groups(hooks, "Stop", True), INSIGHT_MARKER)
    stop = _strip_marker(stop, CLAIM_GATE_MARKER)
    stop = _strip_marker(stop, APPLY_GATE_MARKER)
    wired_stop = False
    if (Path(app_home) / "hooks" / "insight-capture.sh").exists():
        stop.append({"hooks": [{"type": "command",
                                "command": _insight_cmd(app_home),
                                "timeout": 10}]})
        wired_stop = True
    if _has_claim_gate(app_home):
        stop.append({"hooks": [{"type": "command",
                                "command": _claim_gate_cmd(app_home),
                                "timeout": 10}]})
        wired_stop = True
    if _has_gate(app_home, "apply-gate.sh"):
        stop.append({"hooks": [{"type": "command",
                                "command": _gate_cmd(app_home, "apply-gate.sh"),
                                "timeout": 10}]})
        wired_stop = True
    # The same fix, and this site was the worst of the three: it had no `or stop` fallback
    # at all, so a checkout wiring nothing onto Stop discarded the stripped list whether or
    # not it had emptied it.
    if wired_stop or stop or "Stop" in hooks:
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
    for event, markers in OUR_EVENT_MARKERS:
        if event not in hooks:
            continue
        groups = _event_groups(hooks, event, strict=False)
        if groups is None:
            unreadable.append(event)
            continue
        remaining = groups
        for marker in markers:
            remaining = _strip_marker(remaining, marker)
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


# ------------------------------------------------------------------------ adoption
#
# THE LEDGER HAS TO COVER THE SKILLS THAT EXIST, NOT THE ONES A FORGE HAPPENED TO BUILD.
# Three of nine shipped skills had a forge record; the other six entered the pool as seeds
# and were invisible to every question the ledger is asked. A skill with no `origin` row
# cannot be reported on at all, so its uses read as zero -- which is the same shape of
# false negative this whole package exists to remove.
#
# So install writes the missing rows. Two populations, and they are NOT the same claim:
#
#   skills/ in this checkout      `origin:"adopted"`. We ship it; how it was authored is
#                                 not asserted, only that it was already here when the
#                                 ledger started looking.
#   a real directory sitting in   `origin:"unknown"`. It is in the user's pool and this
#   the installed skills dir      package cannot prove what created it. It may well be one
#                                 we forged there -- a skill forged for personal use lands
#                                 exactly there and is the normal case in the field, not
#                                 an edge case -- or it may be the user's own work.
#                                 "unknown" is the only honest answer, and it is a better
#                                 record than no record.
#   a symlink we cannot prove     SKIPPED entirely. A link pointing into somebody else's
#   we made                       checkout belongs to that project, and writing a row for
#                                 it would be this package claiming a skill it never
#                                 touched. `_link_is_ours` is the same four-proof judgement
#                                 the rest of this file uses; a link that proves nothing is
#                                 reported, never adopted.
#
# The rows are written by `bin/skillforge origin`, not here. One implementation of the row
# shape, the horizon marker and the "one origin per skill, ever" rule, in the one place
# that already owns the ledger -- a second, Python-flavoured copy of that logic would be
# the one that drifts.

def _skillforge_bin(app_home):
    p = Path(app_home) / "bin" / "skillforge"
    return str(p) if os.access(str(p), os.X_OK) else None


def _origin_rows(state_dir):
    """How many origin rows the ledger holds, by name. Tolerates a corrupt line."""
    names = set()
    try:
        with open(str(Path(state_dir) / LEDGER), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or '"origin"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("event") == "origin":
                    names.add(row.get("name"))
    except OSError:
        pass
    return names


def _record_origin(forge_bin, state_dir, name, origin, skill_dir):
    """One `skillforge origin` call. Never raises: a missing row is not a failed install."""
    env = dict(os.environ)
    env["SKILL_COMPOUNDER_STATE"] = str(state_dir)
    try:
        subprocess.run([forge_bin, "origin", "--name", name, "--origin", origin,
                        "--skill-dir", str(skill_dir)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, env=env, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def adopt_origins(app_home, claude_dir, state_dir, manifest=None):
    """Give every skill in the pool an origin row, if it has none. Idempotent.

    Returns a one-line report. Running it twice writes nothing the second time, because
    `skillforge origin` refuses to add a second origin row for a name that has one.
    """
    forge_bin = _skillforge_bin(app_home)
    if forge_bin is None:
        return ("skipped: bin/skillforge is not executable, so no origin rows were "
                "written (the ledger will show these skills as unknown)")
    before = _origin_rows(state_dir)
    shipped = _skill_dirs(app_home)
    for d in shipped:
        if d.name not in before:
            _record_origin(forge_bin, state_dir, d.name, "adopted", d)

    shipped_names = {d.name for d in shipped}
    manifest = read_manifest(state_dir) if manifest is None else manifest
    skipped = 0
    dest = Path(claude_dir) / "skills"
    try:
        entries = sorted(dest.iterdir())
    except OSError:
        entries = []
    for p in entries:
        if p.name in shipped_names or not (p / "SKILL.md").is_file():
            continue
        if p.is_symlink():
            if not _link_is_ours(p, app_home, manifest):
                skipped += 1          # somebody else's skill; not ours to describe
                continue
            # Ours, but pointing outside the checkout -- a skill forged elsewhere.
            target = _link_target(p) or str(p)
            if p.name not in before:
                _record_origin(forge_bin, state_dir, p.name, "unknown", target)
            continue
        if p.name not in before:
            _record_origin(forge_bin, state_dir, p.name, "unknown", p)
    after = _origin_rows(state_dir)
    added = len(after - before)
    note = "%d origin row(s) written, %d skill(s) already recorded" % (added, len(before))
    if skipped:
        note += ("; %d installed skill(s) belong to another project (links this package "
                 "cannot prove it made) and were left out of the ledger" % skipped)
    return note


# ------------------------------------------------------------------- install/uninstall

def install(app_home, claude_dir, bin_dir, state_dir=None, doctrine=None):
    app_home = str(Path(app_home).resolve())
    claude_dir = Path(claude_dir)
    state_dir = str(state_dir or DEFAULT_STATE)
    settings_path = claude_dir / "settings.json"

    # Everything that can be checked is checked before anything is applied.
    settings = validate_settings(read_settings(settings_path))
    preflight(claude_dir, bin_dir, state_dir, settings_path, app_home, doctrine)
    # Which event keys are the user's, so uninstall can put back exactly what it found.
    # Read together with the manifest: a reinstall must not adopt the keys the first
    # install created.
    preexisting = preexisting_events(
        settings, read_manifest(state_dir).get("preexisting_hook_events") or ())

    report = {}
    report["backup"] = backup_file(settings_path) or "(no existing settings.json)"

    merge_hooks(settings, app_home)
    install_statusline(settings, app_home, state_dir)
    write_settings(settings_path, settings)
    report["settings"] = str(settings_path)

    manifest = read_manifest(state_dir)
    manifest["app_home"] = app_home
    manifest["claude_dir"] = str(claude_dir)
    manifest["preexisting_hook_events"] = preexisting
    manifest["bin_dir"] = str(bin_dir)
    # Before write_manifest below, which is what records the outcome this returns.
    report["doctrine"] = install_doctrine(claude_dir, app_home, manifest, doctrine)

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
    # After the manifest is written, because the ownership judgement below reads it: a
    # link this very install just made is only provably ours once it is recorded.
    report["ledger"] = adopt_origins(app_home, claude_dir, state_dir, manifest)

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
    report["backup"] = backup_file(settings_path) or "(no existing settings.json)"
    problems = []

    if _real_file_path(settings_path).exists():
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
    report["doctrine"] = remove_doctrine(claude_dir, manifest)
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
    # A skill that becomes live has to be answerable for in the ledger, or its uses read
    # as zero forever. `skillforge done` writes `origin:"forged"` BEFORE it calls this, so
    # a forged skill keeps that answer; this only catches a skill linked outside a forge,
    # where all we honestly know is that it was already authored when we adopted it.
    forge_bin = _skillforge_bin(app_home)
    if forge_bin is not None:
        _record_origin(forge_bin, state_dir, name, "adopted", target)
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
