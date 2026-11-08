"""Workspace change inspection for the web workbench.

Git is the preferred baseline. A fresh interview repository often has no
commit yet, so untracked files fall back to an empty baseline and still get a
useful red/green diff in the UI.
"""

from __future__ import annotations

import difflib
import json
import subprocess
import threading
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Any

from .gitprobe import work_tree_verdict
from .internal_paths import AUDIT_NAME
from .tools.editor import (
    _MUTATING_ACTIONS,
    audit_level,
    backup_copy_name,
    backup_copy_path,
    deletion_witness,
    move_destination,
    sha256_digest,
)
from .tools.registry import redact_text


class ChangeError(RuntimeError):
    """A requested path cannot be inspected safely."""


_IGNORED_PREFIXES = (
    ".git/",
    ".minicc/",
    ".playwright-cli/",
    ".pytest_cache/",
    ".venv/",
    "__pycache__/",
    "minicc.egg-info/",
    "node_modules/",
    "output/",
)
_MAX_FILES = 120
#: The audit actions that actually change a file.  ``read``, ``backup`` and
#: ``backup_prune`` touch the workspace but do not change it.  M8-T313: the
#: set is the editor's own - two copies of "did this change the workspace"
#: are two answers waiting to diverge.
_CHANGING_AUDIT_ACTIONS = _MUTATING_ACTIONS
#: M8-T312: how many audit lines the change panel looks at.  A busy audit
#: history pushes older entries out of the window, so the window is
#: disclosed rather than silently shrinking the change list.
_AUDIT_WINDOW_LINES = 500
#: M8-T550: bytes of the audit tail that are read.  A tail this long starts
#: mid-record by construction; that first line is a known partial, not a
#: record that could not be read.
_AUDIT_TAIL_BYTES = 256_000
#: M8-T562: what the panel can say about the content a witnessed deletion
#: removed.  The four words are the answer, and they are not interchangeable:
#: a copy that was never recorded, a copy that cannot be shown, and a copy
#: whose bytes are not the ones the line digested are three different facts -
#: collapsing them into an empty patch is how "I could not read it" becomes
#: "there was nothing there" (the family this campaign is about).
PREIMAGE_READ = "copy"
PREIMAGE_NOT_RECORDED = "not-recorded"
PREIMAGE_NOT_READABLE = "not-readable"
PREIMAGE_MISMATCH = "digest-mismatch"
#: M8-T566: the fifth word, and it is not a synonym of ``not-recorded``.  The
#: trail is read as a bounded tail (``_AUDIT_TAIL_BYTES``) and only its last
#: ``_AUDIT_WINDOW_LINES`` lines are looked at, so a ``backup`` line can be
#: outside what was read while the ``delete`` line it pairs with is inside.
#: Saying ``not-recorded`` there is the panel claiming the editor never wrote
#: a copy, on the strength of a reading that never looked that far.
PREIMAGE_NOT_IN_WINDOW = "not-in-window"
#: ``source`` when the pre-image came out of the editor's own copy instead of
#: out of git, so a reader can tell which baseline a patch was built on.
PREIMAGE_SOURCE = "audit-backup-copy"
#: M8-T565: what the panel can say about a name git wrote with a substitution
#: character in it.  ``_git`` decodes git's stdout with ``errors="replace"``, so
#: a file whose name git could not put into UTF-8 arrives in the listing as that
#: rendering - and the listing has been using the rendering as an address: the
#: path does not exist, ``_text`` answers ``""``, and a three-line file is
#: reported as "added, 0 lines".  The three verdicts are not interchangeable:
#: one disk entry renders into this name (``substituted`` - the number and the
#: patch come from that file), several do (``ambiguous`` - no number is
#: attributable), none does (``unmatched`` - the name could not be tied back at
#: all).  "" is the fourth state and means the name is its own rendering, which
#: is what every ordinary path is.
NAME_SUBSTITUTED = "substituted"
NAME_AMBIGUOUS = "ambiguous"
NAME_UNMATCHED = "unmatched"
#: The character git's decoder writes for bytes it could not read.
SUBSTITUTED_CHAR = "\ufffd"
_SUMMARY_CACHE: OrderedDict[str, tuple[object, list[dict[str, Any]]]] = OrderedDict()
_CACHE_LOCK = threading.Lock()


# M8-T385: the directories that hold tool-internal state inside a workspace.
# Two readers need this fact - change inspection skips them, and the snapshot
# journal refuses them - and each used to spell the set out itself.  One home.
INTERNAL_DIRS = frozenset({".git", ".minicc"})


def _ignored_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized in INTERNAL_DIRS or normalized.startswith(_IGNORED_PREFIXES)


def _rendered_form(name: str) -> str | None:
    """What git's record says a disk name looks like, or ``None``.

    M8-T565: git writes the name's bytes, and ``_git`` decodes them with
    ``errors="utf-8"``/``errors="replace"``, so every byte that is not valid
    UTF-8 in that position becomes one ``U+FFFD``.  On Windows git substitutes
    ``U+FFFD`` for an unpaired surrogate itself, which is the same answer for
    the ``surrogateescape`` range Python puts those bytes back into.  Running
    the name through those two steps is therefore git's own step, and it is the
    only way a listed name can be traced back to the file it came from.
    ``None`` is honest about the limit: a surrogate outside that range (U+D800
    is the common one) cannot be encoded at all here, while git still renders
    it - so such a name can only ever be reported as unmatched.
    """
    try:
        raw = name.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        return None
    return raw.decode("utf-8", "replace")


def _status_record(path: str, status: str, raw: str) -> dict[str, Any]:
    """The one shape of a changed-file status record.

    Two sources mint it: git's status lines and the audit fallback for a
    file git did not report (M8-T310).  ``raw`` is load-bearing
    provenance - the git status line itself, or the literal ``"audit"``
    - because the snapshot signature and the untracked check both read
    it, and a record whose raw says "audit" is an inferred change, not
    an observed one.
    """
    return {"path": path, "status": status, "raw": raw}


def _patch_counts(patch: str) -> tuple[int, int]:
    """How many lines a unified patch adds and how many it removes.

    M8-T563: the two file-header lines are dropped by *position*, not by
    prefix.  Counting ``-`` lines that do not start with ``---`` silently
    throws away a removed line whose own content begins with ``--`` (it
    renders as ``--- ...``), and the same is true of an added ``++`` line -
    so the number stopped being the number of lines the patch shows.  The
    list and the detail page now read the same ruler: a deletion counted
    in one place cannot answer a different figure in the other.
    """
    lines = patch.splitlines()
    if len(lines) >= 2 and lines[0].startswith("---") and lines[1].startswith("+++"):
        lines = lines[2:]
    additions = sum(1 for line in lines if line.startswith("+"))
    deletions = sum(1 for line in lines if line.startswith("-"))
    return additions, deletions


class ChangeInspector:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self._renames: dict[str, str] = {}
        # M8-T562: resolved path -> (what the delete line digested, the copies
        # the window recorded for it).  Filled by ``files_without_diff``, read
        # lazily by ``_diff_for_target``.  M8-T563: the list reads it too, for
        # the deletions git never counted - the number a row carries and the
        # patch the detail page shows are one fact, so they are read once,
        # from this filing, and nowhere else.
        self._audit_preimage_sources: dict[str, tuple[str, list[tuple[str, str]]]] = {}
        # M8-T565: git's rendered name -> (verdict, the disk name it was made
        # from).  Filled by ``files_without_diff``, read by the counting loop,
        # by ``diff`` and by ``summary`` - one ruler, so a row's number and the
        # detail page cannot disagree about which file a name stands for.
        self._name_verdicts: dict[str, tuple[str, str]] = {}

    def _resolve(self, raw_path: str) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ChangeError("path 不能为空")
        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise ChangeError("不允许绝对路径")
        resolved = (self.workspace / candidate).resolve()
        if not resolved.is_relative_to(self.workspace):
            raise ChangeError("路径超出工作区")
        return resolved

    def _git(self, args: list[str]) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 127, "", "git unavailable"
        return result.returncode, result.stdout, result.stderr

    def _status_lines(self) -> tuple[list[str], str | None]:
        """Git's status records — and why, if the tree could not be read.

        M8-T548: the failure branches used to answer ``[]``, the same list a
        clean tree produces, so the change panel reported 「没有变更」 about a
        workspace whose git had refused.  ``None`` now means *the tree was
        read*; a workspace that is not a repository (or has no work tree)
        is still a readable, supported empty baseline.
        """
        code, stdout, stderr = self._git(["status", "--porcelain=v1", "-z", "-uall"])
        if code != 0:
            return [], self._status_failure(code, stderr)
        # NUL records preserve spaces, Unicode and embedded newlines. A
        # rename/copy carries destination first and source as the next record.
        records = iter(stdout.split("\0"))
        output = []
        self._renames.clear()
        for raw in records:
            if not raw:
                continue
            if "R" in raw[:2] or "C" in raw[:2]:
                origin = next(records, "")
                self._renames[raw[3:]] = origin
            output.append(raw)
        return output, None

    def _status_failure(self, code: int, stderr: str) -> str | None:
        """The reason a failed ``git status`` is a failed read, or ``None``.

        ``_git`` answers 127 / "git unavailable" for both an OSError and a
        20-second timeout — git did not run at all.  Its own non-zero exits
        are split by ``work_tree_verdict``: no repository is a fact about
        the workspace (the module exists for workspaces with no commit, and
        a workspace with no repository at all is the same kind of fact);
        everything else is a tree we were not allowed to read.
        """
        if code == 127 and "git unavailable" in stderr:
            return "git status 无法运行（20 秒超时或 PATH 里没有 git），变更清单没有读出来"
        kind, detail = work_tree_verdict(self.workspace)
        if kind == "no":
            return None
        reason = f"git status 退出码 {code}"
        first = (stderr or "").strip().splitlines()
        if first:
            reason += f": {first[0][:200]}"
        if kind == "unknown":
            reason += f"（且无法确认这是不是仓库：{detail}）"
        return reason

    @staticmethod
    def _parse_status(raw: str) -> tuple[str, str]:
        code = raw[:2]
        path = raw[3:] if len(raw) > 3 else ""
        if code == "??" or "A" in code:
            status = "added"
        elif "D" in code:
            status = "deleted"
        elif "R" in code:
            status = "renamed"
        else:
            status = "modified"
        return status, path

    def _audit_paths(self) -> tuple[set[str], set[str], str | None]:
        """Paths the editor **changed**, from the audit trail — and why not.

        The first set is every path a changing action named.  The second is
        the half of it that names a file the trail says is **gone** - see
        the M8-T561 note below.

        M8-T300: the action was ignored, so a ``read`` landed in the same
        set as a ``write`` - and the fallback then reported every file the
        agent had merely *read* as "modified", with an empty patch.  The
        audit trail records ``read``/``backup``/``backup_prune`` alongside
        the actions that change a file; only the latter are changes.

        M8-T312: the window is the last 500 lines of the tail, and it is
        applied **after** the read - so a busy audit history (a few hundred
        reads) pushes the writes out of the window, and the change panel
        reports a clean workspace while ``/api/audit`` still shows the
        write.  The window is now disclosed.

        M8-T549: the whole read used to sit in ``except ...: return set()``
        — the empty set an audit trail with no writes produces.  Every read
        of the trail now answers: ``None`` means *the trail was read*, and
        an OS failure carries a reason.  The existence check moved inside
        the try for the same reason: on 3.11 ``Path.is_file`` raises, and
        one unreadable stat used to turn the summary into a 500.

        M8-T550: a line that could not be read as a record is not a line
        that never existed.  It is counted in ``_audit_unreadable_lines``
        (instead of crashing the panel when it parsed to a non-object, or
        disappearing without a word when it did not parse at all).  The
        first line of a tail cut at ``_AUDIT_TAIL_BYTES`` is dropped before
        the count — that partial is made by the cut, not by corruption.

        M8-T556: this reader also vetoed every path that begins with a
        dot - a clause that predates ``_ignored_path`` and outlived it.
        The tool's own state (``.git``, ``.minicc``) is already refused
        by the predicate the git-status reader uses, so the extra clause
        only hid user dotfiles: a gitignored ``.env`` was recorded by the
        audit, unseen by git, and answered as no such file.  Both
        readers now decide with ``_ignored_path`` alone.

        M8-T557: and the record's own path was coerced, not read.
        The line pre-filter required the word ``"path"``;
        ``str(value or "")`` then turned ``123`` into a path -
        matching a real file of that name when one existed - and
        turned the other shapes into names no file has.  The
        window is parsed line by line now; only a non-blank string
        is a path, and a record that names none is counted in
        ``_audit_records_without_path``.  It names no file, so
        unlike an unreadable line it does not hold the clean
        shortcut in ``diff()``.

        M8-T558: and a line whose own action was refused was
        read as a change.  Every refusal site in the editor
        records the attempt *before* anything is written, and
        ``audit_level`` - the same function ``/api/audit``
        filters by - calls such a line a warning.  A refusal
        wrote nothing, so it names no file; it is counted in
        ``_audit_refused_records``.  The panel asks the rule
        rather than trusting the ``level`` the line carries.

        M8-T559: the action was coerced the way the path used
        to be.  ``str(value or "")`` turned ``["write"]`` into
        a word no action set knows, and an empty action slipped
        past the ``if action and ...`` filter - so a record
        that said nothing about its action was read as a change.
        Only a non-blank string is an action now; the rest are
        counted in ``_audit_records_without_action``.  Unlike a
        refusal, such a record still names a file, so it holds
        the clean shortcut in ``diff()``.

        M8-T560: a ``move`` line names its source, and the
        source is what the operation removes.  The file that
        exists afterwards is spelled only in ``detail`` (the
        editor's own arrow form), and only that line's
        reader - ``move_destination`` - may turn it into a path.
        A move the audit recorded is a change git cannot always
        see, so the destination joins the set next to the source.

        M8-T561: a ``delete`` line names the file it removed, and that
        file is absent by construction - which is exactly the shape the
        ``is_file`` fallback in ``files_without_diff`` cannot answer, so
        the panel said nothing had changed about a file the trail watched
        disappear.  The deletions travel beside the paths instead of
        inside them, and only for what the window actually says: the line
        has to carry the content it removed (``deletion_witness``), the
        path's last action has to be the deletion, and its first action
        must not be a creation - a file born and buried inside the window
        leaves the workspace as it was.

        M8-T562: the same pass files the two halves a deletion's content is
        made of - what the ``delete`` line digested and what the ``backup``
        lines said they kept - beside the path each names.  A copy line is
        still not a change, so it joins none of the sets above; reading it
        here costs no second pass over the trail, and the copies are opened
        only when a detail page asks (``_read_deletion_preimage``).
        """
        self._audit_window_truncated = False
        self._audit_unreadable_lines = 0
        self._audit_records_without_path = 0
        self._audit_refused_records = 0
        self._audit_records_without_action = 0
        # M8-T562: the two halves of a witnessed deletion, kept apart from the
        # change sets because a copy line is not a change (M8-T300 said so
        # about ``read`` and ``backup``) and the digest alone names no file.
        self._audit_deletion_witnesses = {}
        self._audit_backup_copies = {}
        self._audit_preimage_sources = {}
        audit = self.workspace / ".minicc" / AUDIT_NAME
        paths: set[str] = set()
        first_action: dict[str, str] = {}
        last_action: dict[str, str] = {}
        witnessed: set[str] = set()
        try:
            if not audit.is_file():
                if audit.exists():
                    return set(), set(), (
                        f"审计记录（.minicc/{AUDIT_NAME}）不是一个文件"
                        "（可能是目录），读不出来，git 看不到的改动没有兜底"
                    )
                if audit.parent.exists() and not audit.parent.is_dir():
                    return set(), set(), (
                        f"审计记录（.minicc/{AUDIT_NAME}）的父路径（.minicc）"
                        "不是一个目录，读不出来，git 看不到的改动没有兜底"
                    )
                return set(), set(), None
            # Read a bounded tail; audit histories can be many megabytes.
            with audit.open("rb") as stream:
                size = audit.stat().st_size
                stream.seek(max(0, size - _AUDIT_TAIL_BYTES))
                tail = stream.read().decode("utf-8", errors="replace")
            lines = tail.splitlines()
            if size > _AUDIT_TAIL_BYTES and lines:
                lines = lines[1:]
            # M8-T566: the question this flag answers is "did the panel read
            # the whole trail", and there are two ways not to: the byte tail
            # never looked at the head, and the line cap drops lines that were
            # read.  Counting only the cap (the old ``len(lines) > `` test) left
            # a 320 KB trail reporting nothing was missed.
            self._audit_window_truncated = (
                size > _AUDIT_TAIL_BYTES or len(lines) > _AUDIT_WINDOW_LINES
            )
            for line in lines[-_AUDIT_WINDOW_LINES:]:
                try:
                    item = json.loads(line)
                except ValueError:
                    self._audit_unreadable_lines += 1
                    continue
                if not isinstance(item, dict):
                    self._audit_unreadable_lines += 1
                    continue
                raw_action = item.get("action")
                if not isinstance(raw_action, str) or not raw_action.strip():
                    # M8-T559: a record that does not say which action it
                    # was cannot say it changed this file - and the old
                    # ``str()`` both invented a word (``123``) and let an
                    # empty one slip past the filter below.
                    self._audit_records_without_action += 1
                    continue
                action = raw_action.strip().lower()
                if action == "backup":
                    # M8-T562: a copy line changes no file, so it must not join
                    # the change sets - M8-T300 was right about that.  It is
                    # still the only line that says *where* the content a later
                    # delete removed was kept, so its name and its digest are
                    # filed beside the path it names.  A refusal never wrote a
                    # copy (M8-T558's rule), a line that names no path is no
                    # file's copy, and a digest that is not a string witnesses
                    # nothing (M8-T559's gate, M8-T561's witness).
                    self._note_backup_copy(item)
                    continue
                if action not in _CHANGING_AUDIT_ACTIONS:
                    continue
                raw_path = item.get("path")
                if not isinstance(raw_path, str) or not raw_path.strip():
                    # M8-T557: a record that names no usable path named no
                    # file.  ``str(value or "")`` used to turn ``123`` into
                    # a real path and the other shapes into names no file
                    # has; both were then matched against the workspace.
                    self._audit_records_without_path += 1
                    continue
                path = raw_path.replace("\\", "/")
                if audit_level(action, item.get("detail")) == "warning":
                    # M8-T558: the rule that marks a refusal is the
                    # editor's own - each refusal site audits before
                    # it writes.  A refused action changed no file.
                    self._audit_refused_records += 1
                    continue
                if not _ignored_path(path):
                    paths.add(path)
                    first_action.setdefault(path, action)
                    last_action[path] = action
                    if action == "delete" and (witness := deletion_witness(item)):
                        # M8-T561: the line that digested the bytes it
                        # removed is the only one that can say a file was
                        # there to begin with.
                        witnessed.add(path)
                        # M8-T562: and it is the same line that says *what*
                        # was there.  The last one wins, the same way the last
                        # action decides whether the path is gone at all.
                        self._audit_deletion_witnesses[path] = witness
                if action == "move":
                    # M8-T560: the source named above is gone by the time
                    # this line is read, so on its own it lists a file that
                    # no longer exists.  The destination is the change the
                    # model made; the editor's own reader turns the detail
                    # into it, and nothing is listed when the line does not
                    # spell one.
                    destination = move_destination(item.get("detail"))
                    if destination:
                        destination = destination.replace("\\", "/")
                        if not _ignored_path(destination):
                            paths.add(destination)
        except (OSError, ValueError, TypeError) as exc:
            return set(), set(), (
                f"审计记录（.minicc/{AUDIT_NAME}）读不出来"
                f"（{type(exc).__name__}: {exc}），git 看不到的改动没有兜底"
            )
        deletions = {
            path
            for path in witnessed
            if last_action.get(path) == "delete" and first_action.get(path) != "create"
        }
        return paths, deletions, None

    def _note_backup_copy(self, item: dict) -> None:
        """File the copy a ``backup`` line says it kept, beside its path.

        Only `_backup` writes such a line, and it writes it after the copy
        succeeded, so a name is read out of the arrow form the same reader
        uses everywhere (`backup_copy_name`) - a refusal detail never spells
        one, which is why M8-T558's verdict is not asked again here.
        """
        name = backup_copy_name(item)
        digest = deletion_witness(item)
        raw_path = item.get("path")
        if not name or not digest or not isinstance(raw_path, str) or not raw_path.strip():
            return
        path = raw_path.replace("\\", "/")
        if _ignored_path(path):
            return
        self._audit_backup_copies.setdefault(path, []).append((digest, name))

    def _read_deletion_preimage(self, path: str) -> tuple[str, str]:
        """What a witnessed deletion removed, and what stopped us saying so.

        The editor digested the file before unlinking it and copied it into
        its own backup directory, so the window normally holds both halves:
        the ``delete`` line's witness and the ``backup`` line's name.  The
        pair is made by the digest, not by the name and not by the order the
        lines were written (M8-T562), and the bytes are believed only after
        they digest to the witness - a copy somebody overwrote since is not
        the content this deletion removed.  Every other answer is said out
        loud: ``not-recorded`` when no line names a copy for that content,
        ``not-readable`` when one does but its bytes cannot be shown here,
        ``digest-mismatch`` when they are not the digested bytes.  All three
        used to be the same empty patch.

        M8-T566: ``not-recorded`` is only owed by a reading that saw the whole
        trail.  When the window cut records - by bytes or by lines - and none
        of them named a copy for this path, the honest answer is
        ``not-in-window``: nothing was seen, and the reader knows it did not
        look everywhere.  The other three words stand on facts the window
        cannot undo, so they are still said first.
        """
        source = self._audit_preimage_sources.get(path)
        if not source:
            return "", ""
        witness, copies = source
        unreadable = False
        mismatch = False
        for digest, name in reversed(copies):
            if digest != witness:
                continue
            copy = backup_copy_path(self.workspace, name)
            if copy is None:
                unreadable = True
                continue
            try:
                body = copy.read_bytes()
            except OSError:
                unreadable = True
                continue
            if sha256_digest(body) != witness:
                mismatch = True
                continue
            try:
                return PREIMAGE_READ, body.decode("utf-8")
            except UnicodeDecodeError:
                unreadable = True
                continue
        if mismatch:
            return PREIMAGE_MISMATCH, ""
        if unreadable:
            return PREIMAGE_NOT_READABLE, ""
        if self._audit_window_truncated:
            return PREIMAGE_NOT_IN_WINDOW, ""
        return PREIMAGE_NOT_RECORDED, ""

    def _preimage_signature(self, complete: list[dict[str, Any]]) -> tuple:
        """The bytes a listed deletion may be counted at, as the disk has them.

        M8-T563: the fingerprint covered the working files and HEAD alone.  A
        row counted out of a backup copy has one more input - that copy's
        bytes - and it does not touch the file that is gone: prune the copy
        and the memo keeps serving the number the disk can no longer show.
        The trail needs no entry of its own; every reading of it that changes
        a row's number changes this filing, and the filing is what these
        entries are built from.  Only the candidates the read would actually
        open are stat'ed (the ones whose digest is the witness), and no bytes
        are read here.
        """
        entries: list[tuple] = []
        for item in complete:
            if item.get("status") != "deleted":
                continue
            source = self._audit_preimage_sources.get(str(item["path"]))
            if not source:
                continue
            witness, copies = source
            for digest, name in copies:
                if digest != witness:
                    continue
                copy = backup_copy_path(self.workspace, name)
                if copy is None:
                    entries.append((str(item["path"]), str(name), None))
                    continue
                try:
                    stat = copy.stat()
                except OSError:
                    entries.append((str(item["path"]), str(name), None))
                    continue
                entries.append((str(item["path"]), str(name), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
        return tuple(entries)

    def _computed_files(self) -> list[dict[str, Any]]:
        """Every changed file, with its counts.  Not truncated."""
        complete = sorted(self.files_without_diff(), key=lambda item: item["path"].casefold())
        # M8-T306: the cache fingerprint was built from the **truncated**
        # list, so a change to a file past the cap did not invalidate it -
        # the summary kept serving the old additions/deletions.  The
        # signature now covers every file the inspector knows about.
        signature = []
        for item in complete:
            # M8-T565: a row whose name is a rendering is counted out of the
            # file that rendering came from, so it is that file's stat the memo
            # has to watch.  Keying the fingerprint by the name that opens
            # nothing left every entry ``(raw, None, None)`` - a stale number
            # no edit could invalidate.
            verdict, listed_source = self._name_verdicts.get(str(item["path"]), ("", ""))
            try:
                stat = self._resolve(listed_source or str(item["path"])).stat()
                signature.append((item["raw"], stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, self._renames.get(item["path"])))
            except (OSError, ChangeError):
                signature.append((item["raw"], None, None))
        # HEAD/index mutations invalidate even when the working file did not
        # change. rev-parse handles linked worktrees without assuming .git/.
        code, head, _ = self._git(["rev-parse", "HEAD"])
        key = str(self.workspace)
        # M8-T563: a row may now be counted out of a backup copy, and neither
        # the copy nor the trail touches the deleted file's own stat.  Without
        # this third half, pruning the copy left the list serving a number the
        # disk can no longer show - the stale memo, one level up.
        fingerprint = (head if code == 0 else "", tuple(signature), self._preimage_signature(complete))
        with _CACHE_LOCK:
            cached = _SUMMARY_CACHE.get(key)
            if cached and cached[0] == fingerprint:
                _SUMMARY_CACHE.move_to_end(key)
                return deepcopy(cached[1])
        stats = self._numstat()
        output: list[dict[str, Any]] = []
        # M8-T307: the counts cover **every** file the inspector knows
        # about, not only the ones that fit in the cap.  The list is
        # truncated (and the truncation is disclosed); the totals are not.
        for item in complete:
            counts = stats.get(item["path"], (0, 0))
            name_verdict, listed_source = self._name_verdicts.get(str(item["path"]), ("", ""))
            try:
                if item["raw"].startswith("??") or code != 0:
                    # Before the first commit HEAD is an empty baseline.
                    # Cached numstat sees only staged content; the worktree
                    # may contain additional edits or a staged-then-deleted file.
                    # M8-T565: this is the branch that reads the **disk**, and a
                    # name git wrote with a substitution in it is not a disk
                    # path.  One file makes that name, so the lines counted are
                    # that file's.  None or several make it, and no number is
                    # this row's - which is said as ``None``, not as 0, because
                    # "0 lines" is the answer this campaign keeps meeting.
                    if name_verdict in (NAME_AMBIGUOUS, NAME_UNMATCHED):
                        counts = (None, None)
                    else:
                        counts = (
                            len(self._text(self._resolve(listed_source or str(item["path"]))).splitlines()),
                            0,
                        )
            except ChangeError:
                pass
            row = {**item, "additions": counts[0], "deletions": counts[1], "name_resolution": name_verdict}
            if item["status"] == "deleted":
                # M8-T563: the detail page has read this file's content out of
                # the editor's own copy since M8-T562, while the list answered
                # 0 lines for it until this batch - one fact, two answers in
                # the same payload.  The verdict travels in the same key the
                # detail page uses, so a row that could not be counted says why
                # instead of borrowing the word for "there was nothing in it".
                # A deletion git already counted is not asked (no source is
                # filed for it), so git's number stays git's number.
                verdict, text = self._read_deletion_preimage(str(item["path"]))
                if verdict:
                    row["deletion_preimage"] = verdict
                    if verdict == PREIMAGE_READ:
                        row["deletions"] = len(text.splitlines())
            output.append(row)
        with _CACHE_LOCK:
            _SUMMARY_CACHE[key] = (fingerprint, deepcopy(output))
            _SUMMARY_CACHE.move_to_end(key)
            while len(_SUMMARY_CACHE) > 16:
                _SUMMARY_CACHE.popitem(last=False)
        return output

    def files(self) -> list[dict[str, Any]]:
        """The changed files, capped at ``_MAX_FILES``.

        M8-T307: the cap applies to the **list**, not to the numbers.  The
        summary's totals are computed over every file, so a workspace with
        300 changes reports 300 (and the additions that go with them) while
        the list itself shows the first 120 - and the summary says so.
        """
        return self._computed_files()[:_MAX_FILES]

    def _numstat(self) -> dict[str, tuple[int, int]]:
        code, stdout, _ = self._git(["diff", "--numstat", "-z", "--find-renames", "HEAD", "--"])
        if code != 0:
            # An unborn repository has no HEAD; staged additions still have
            # meaningful counts and untracked files are counted separately.
            code, stdout, _ = self._git(["diff", "--cached", "--numstat", "-z", "--find-renames", "--"])
        result = {}
        if code == 0:
            records = iter(stdout.split("\0"))
            for record in records:
                parts = record.split("\t", 2)
                if len(parts) == 3:
                    added, deleted, path = parts
                    if not path:
                        next(records, "")
                        path = next(records, "")
                    result[path] = (int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0)
        return result

    def _baseline(self, path: str) -> str:
        code, stdout, _stderr = self._git(["show", f"HEAD:{path}"])
        return stdout if code == 0 else ""

    @staticmethod
    def _text(path: Path) -> str:
        if not path.is_file():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
            return "" if "\0" in text else text
        except UnicodeDecodeError:
            return ""
        except OSError as exc:
            raise ChangeError(f"读取文件失败: {exc}") from exc

    def diff(self, raw_path: str) -> dict[str, Any]:
        target = self._resolve(raw_path)
        path = target.relative_to(self.workspace).as_posix()
        # M8-T304: the status table is keyed by the **resolved** path.  It
        # used to be keyed by the raw spelling, so an audit entry recorded
        # as ``sub/../notes.md`` (or a path through a symlinked directory)
        # put the file under one key while ``diff("notes.md")`` looked it up
        # under another - and the lookup missed, falling back to "clean".
        # The panel said "modified" and the diff said "clean" for the same
        # file.
        status_map: dict[str, str] = {}
        for item in self.files_without_diff():
            key = self._resolved_relative(str(item["path"]))
            if not key:
                # M8-T291: a path that does not resolve inside the workspace
                # (git reports symlinks that point out of the tree) has no
                # key here - and letting ``_resolve`` raise would turn the
                # diff route into a 500.
                key = str(item["path"])
            status = str(item.get("status") or "clean")
            status_map[key] = status
            # M8-T565: a listed name that is a rendering has been the table's
            # only key, so the disk's own spelling missed it and this route
            # invented a baseline for a file the list had just named - one file,
            # two answers ("clean" here, "added" there), which is the same
            # defect M8-T304 closed for the raw/relative spelling.  Both
            # spellings now reach the record; the rendered one is the only one
            # that can travel in a URL, so it is the one that must keep working.
            _verdict, listed_source = self._name_verdicts.get(key, ("", ""))
            if listed_source:
                status_map.setdefault(listed_source, status)
        status = status_map.get(path, "clean")
        # The caller may have spelled the path as the disk holds it or as git
        # rendered it; the verdict is filed under the rendering either way.
        listed = path if SUBSTITUTED_CHAR in path else (_rendered_form(path) or "")
        name_verdict, listed_source = self._name_verdicts.get(listed, ("", ""))
        if name_verdict == NAME_SUBSTITUTED:
            try:
                # The rendering is the only spelling that can travel in a URL,
                # so the route follows it back to the file on disk.
                target = self._resolve(listed_source)
            except ChangeError:
                pass
        # M8-T548: every entry in ``status_map`` came from the status read, so
        # ``files_without_diff`` above has just refreshed the reason.
        return self._diff_for_target(
            target,
            path,
            status,
            self._status_read_error,
            self._audit_read_error,
            self._audit_unreadable_lines,
            self._audit_records_without_path,
            self._audit_refused_records,
            self._audit_records_without_action,
            name_verdict,
            bool(self._audit_window_truncated),
        )

    def _diff_for_target(
        self,
        target: Path,
        path: str,
        status: str,
        status_read_error: str | None = None,
        audit_read_error: str | None = None,
        audit_unreadable_lines: int = 0,
        audit_records_without_path: int = 0,
        audit_refused_records: int = 0,
        audit_records_without_action: int = 0,
        name_resolution: str = "",
        audit_window_truncated: bool = False,
    ) -> dict[str, Any]:
        # M8-T565: two of the three verdicts mean no disk file can be named for
        # this record, so there is nothing to read and no number to show.  The
        # answer is "no number, and here is why" - not the empty patch of a file
        # that has three lines in it, which is what ``after = ""`` used to become.
        unattributable = name_resolution in (NAME_AMBIGUOUS, NAME_UNMATCHED)
        # Untracked files have no HEAD baseline; avoid a subprocess for each
        # one when the workspace is a fresh interview repository.
        before = (
            ""
            if status == "added" or unattributable
            else self._baseline(self._renames.get(path, path))
        )
        after = "" if unattributable else self._text(target)
        source = "git-or-empty-baseline"
        preimage = ""
        if status == "deleted":
            # M8-T562: the trail said this file was deleted and digested what
            # was in it, and git has nothing to say (no repository, untracked
            # file, ignored path).  The content is not lost - the editor kept a
            # copy - so an empty patch here was the panel answering "there was
            # nothing in it" about bytes it never went and looked at.
            # A deletion git already showed keeps git's own pre-image: ``before``
            # is not empty there, and the verdict stays "" because the list
            # never filed an audit source beside it.
            verdict, text = self._read_deletion_preimage(path)
            preimage = verdict
            if verdict == PREIMAGE_READ and not before:
                before = text
                source = PREIMAGE_SOURCE
        if (
            not before
            and target.is_file()
            and status == "clean"
            and not status_read_error
            and not audit_read_error
            and not audit_unreadable_lines
            and not audit_records_without_action
        ):
            # M8-T548: ``clean`` when the status table could not be read is a
            # guess, and copying the file onto its own baseline would print
            # an empty patch for a file that did change - the same collapse
            # one level down.
            # M8-T549: the audit trail is the other source that could have
            # named this file; with it unreadable the same guess is made, so
            # the shortcut waits for both reads.
            # M8-T550: a line the audit could not read could have named this
            # file too; the shortcut waits for every line as well.
            # M8-T557: a record with no path is deliberately absent from
            # this condition - it named no file, so it cannot have named
            # this one.
            # M8-T558: a refusal is absent for the same reason - the
            # editor wrote nothing, so the line is no evidence that this
            # file changed either.
            # M8-T559: a record that cannot say its action is the other
            # case - it still names a file, and that file may be this one,
            # so the shortcut waits for it like it waits for a bad line.
            before = after

        if not before and not after:
            patch = ""
        else:
            lines = difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
            patch = "\n".join(lines)
        patch, _ = redact_text(patch)
        additions, deletions = (None, None) if unattributable else _patch_counts(patch)
        return {
            "path": path,
            "status": status,
            "patch": patch,
            "additions": additions,
            "deletions": deletions,
            "source": source,
            # M8-T565: the verdict on the name this record was written with -
            # "" when the name is the disk's own spelling.
            "name_resolution": name_resolution,
            # M8-T562: what the panel can say about the content a deletion
            # removed - "" when the question does not arise here.
            "deletion_preimage": preimage,
            # M8-T548: ``status`` may be the ``clean`` fallback; the reason
            # says whether it could be trusted.
            "status_read_error": status_read_error or None,
            # M8-T549: the fallback trail's own read failure travels beside it.
            "audit_read_error": audit_read_error or None,
            # M8-T550: and how many of its lines the window could not read.
            "audit_unreadable_lines": int(audit_unreadable_lines),
            # M8-T557: records that parsed but named no usable path.
            "audit_records_without_path": int(audit_records_without_path),
            # M8-T558: records whose own action was refused.
            "audit_refused_records": int(audit_refused_records),
            # M8-T559: records that never said which action they were.
            "audit_records_without_action": int(audit_records_without_action),
            # M8-T566: the reason ``deletion_preimage`` may answer
            # ``not-in-window`` - this reading did not see the whole trail, and
            # the page that shows the word is the page that has to say that.
            "audit_window_truncated": bool(audit_window_truncated),
        }

    def files_without_diff(self) -> list[dict[str, Any]]:
        """Return status records without recursively calculating every diff."""
        items: dict[str, dict[str, Any]] = {}
        raw_lines, self._status_read_error = self._status_lines()
        for raw in raw_lines:
            status, path = self._parse_status(raw)
            if path and not _ignored_path(path):
                items[path] = _status_record(path, status, raw)
        audit_paths, audit_deletions, self._audit_read_error = self._audit_paths()
        for path in audit_paths:
            # M8-T310: the audit records the **raw** argument the model
            # passed (``sub/../notes.md``), while git records the clean
            # relative path (``notes.md``).  Keying the audit fallback by
            # the raw spelling put the same file into the list twice - once
            # from git and once from the audit - with two different
            # statuses, and the counts were added twice.  Both sources are
            # keyed by the resolved relative path.
            key = self._resolved_relative(path)
            if key and key not in items and (self.workspace / key).is_file():
                items[key] = _status_record(key, "modified", "audit")
        for path in sorted(audit_deletions):
            # M8-T561: the loop above can only speak for files that are still
            # here, and the file a ``delete`` line names is not - so the one
            # change the trail says most plainly was the one the panel had no
            # word for.  Git already naming it wins (``key not in items``),
            # and so does the tree: a file that is back, or a directory in
            # its place, is not something that disappeared.
            key = self._resolved_relative(path)
            if key and key not in items and not (self.workspace / key).exists():
                items[key] = _status_record(key, "deleted", "audit")
                witness = self._audit_deletion_witnesses.get(path)
                if witness:
                    # M8-T562: filed under the resolved key, the same one the
                    # detail page asks with.  M8-T563: the list asks with it
                    # too - a listed deletion is counted from this same
                    # filing, so the two answers cannot come from two rulers.
                    self._audit_preimage_sources[key] = (
                        witness,
                        self._audit_backup_copies.get(path, []),
                    )
        self._resolve_listed_names(items)
        return list(items.values())

    def _resolved_relative(self, raw_path: str) -> str:
        """The workspace-relative path a raw path names, or "" when outside."""
        try:
            target = self._resolve(str(raw_path))
            return target.relative_to(self.workspace).as_posix()
        except (OSError, ValueError, ChangeError):
            return ""

    def _listed_sources(self, rel_path: str) -> list[str]:
        """The workspace-relative names that render into a listed name.

        M8-T565: walked segment by segment, because git's substitution is not
        confined to the last segment - a directory whose name git could not
        write arrives as ``bad/inner.md`` with the ``bad`` half replaced.  A
        segment is a match when ``_rendered_form`` of the disk name equals the
        segment as listed, so a faithful segment matches exactly one entry (an
        ambiguous one several).  Only files are returned for the last segment:
        ``-uall`` lists directory contents, never a directory, so a directory
        that renders into a record's name is not the file the record is about.
        An unlistable directory contributes nothing, which is the same answer
        as "no entry makes this name" and is disclosed as such.
        """
        parts = rel_path.split("/")
        level: list[tuple[str, Path]] = [("", self.workspace)]
        for index, part in enumerate(parts):
            if not part or part in (".", ".."):
                return []
            last = index == len(parts) - 1
            nxt: list[tuple[str, Path]] = []
            for rel, directory in level:
                try:
                    entries = list(directory.iterdir())
                except (OSError, ValueError):
                    continue
                for entry in entries:
                    if _rendered_form(entry.name) != part:
                        continue
                    if last and not entry.is_file():
                        continue
                    nxt.append((f"{rel}/{entry.name}".lstrip("/"), entry))
            if not nxt:
                return []
            level = nxt
        return [rel for rel, _ in level]

    def _resolve_listed_names(self, items: dict[str, dict[str, Any]]) -> None:
        """Say what each listed name that git wrote with a substitution in it stands for.

        Only names carrying ``SUBSTITUTED_CHAR`` are asked: a name without it
        is the disk's own spelling, because Python's decode of git's bytes
        invents that character and nothing else.  Audit rows are skipped -
        their path is a string the editor was handed, not a decoding of bytes,
        so treating it as an address is correct.  A single source that *is* the
        listed name leaves no verdict: the file is literally named that.
        """
        verdicts: dict[str, tuple[str, str]] = {}
        for path, item in items.items():
            if SUBSTITUTED_CHAR not in path or item["raw"] == "audit":
                continue
            sources = self._listed_sources(path)
            if len(sources) == 1 and sources[0] == path:
                verdicts[path] = ("", "")
            elif len(sources) == 1:
                verdicts[path] = (NAME_SUBSTITUTED, sources[0])
            elif not sources:
                verdicts[path] = (NAME_UNMATCHED, "")
            else:
                verdicts[path] = (NAME_AMBIGUOUS, "")
        self._name_verdicts = verdicts

    def summary(self) -> dict[str, Any]:
        # M8-T305 / T307: the totals cover every changed file; the list is
        # capped and the truncation is disclosed.  ``files()`` used to
        # truncate and the summary used to report the truncated length as
        # the total - so a workspace with 300 changes claimed 120, and the
        # additions/deletions covered only the first 120.
        complete = self._computed_files()
        files = complete[:_MAX_FILES]
        return {
            "files": files,
            "total_files": len(complete),
            "additions": sum(int(item.get("additions") or 0) for item in complete),
            "deletions": sum(int(item.get("deletions") or 0) for item in complete),
            "truncated": len(complete) > len(files),
            "shown_files": len(files),
            # M8-T312: the audit window is disclosed too - a change that
            # fell out of the window is missing, and the panel should say so
            # rather than report a clean workspace.
            "audit_window_truncated": bool(
                getattr(self, "_audit_window_truncated", False)
            ),
            # M8-T548: ``total_files: 0`` from a failed read is not "nothing
            # changed"; the reason travels with the answer.
            "status_read_error": getattr(self, "_status_read_error", None),
            # M8-T549: the same answer for the fallback trail.
            "audit_read_error": getattr(self, "_audit_read_error", None),
            # M8-T550: a line that could not be read is counted, not dropped.
            "audit_unreadable_lines": int(
                getattr(self, "_audit_unreadable_lines", 0)
            ),
            # M8-T557: a record that named no usable path is counted too.
            "audit_records_without_path": int(
                getattr(self, "_audit_records_without_path", 0)
            ),
            # M8-T558: a refused action changed no file, so it lists none.
            "audit_refused_records": int(
                getattr(self, "_audit_refused_records", 0)
            ),
            # M8-T559: a record that named no action named no change.
            "audit_records_without_action": int(
                getattr(self, "_audit_records_without_action", 0)
            ),
            # M8-T565: how many of these names are git's rendering rather than
            # the disk's spelling.  One row's verdict says which file it stands
            # for; this says how much of the list was written that way, so a
            # panel can tell a workspace full of such names from one row.
            "substituted_names": sum(
                1 for item in complete if item.get("name_resolution")
            ),
            "workspace": self.workspace.as_posix(),
        }


__all__ = ["ChangeError", "ChangeInspector"]
