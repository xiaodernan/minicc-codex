"""Authorization and verification policy helpers for the agent loop.

Kept separate from ``loop.py`` so the giant turn function can ask two
stable questions without inlining string lists:

- does this tool need ``should_allow`` before it runs?
- does this successful tool result count as post-write verification?
"""

from __future__ import annotations

from typing import Any
import re
from .check_commands import command_parts, checker_invocation

from ..audit import tool_requires_authorization
from ..tools.bash import split_command_argv

# M4-T1: a workspace write is not only the four explicit write tools. An agent
# that runs ``sed -i`` or ``python patch.py`` mutates the workspace just as much,
# so ``verification_required`` must trip for those too. Kept here (next to
# ``is_verification_evidence``) so loop.py asks one stable question.
WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "worktree_create", "worktree_remove"})

# Programs whose normal use rewrites the filesystem.
_MUTATING_PROGRAMS = frozenset({
    "mv", "cp", "rm", "rmdir", "mkdir", "touch", "dd", "ln", "shred",
    "truncate", "tee", "patch", "rsync", "install", "unzip", "zip",
    "tar", "gzip", "gunzip", "bzip2", "xz", "7z", "make", "cmake", "cargo",
})
_GIT_MUTATING = frozenset({
    "add", "rm", "mv", "checkout", "restore", "reset", "clean", "commit",
    "apply", "stash", "rebase", "merge", "cherry-pick", "revert",
})
_PKG_MUTATING = frozenset({
    "install", "uninstall", "update", "upgrade", "add", "remove", "ci", "build", "link",
})
_INTERPRETERS = frozenset({
    "python", "python3", "py", "node", "ruby", "perl", "php",
    "bash", "sh", "zsh", "dash", "ksh",
})
#: The flag each interpreter uses to run **inline code** rather than a file
#: or a module.  Inline code can write anything - ``open(f, "w")``,
#: ``fs.writeFileSync``, ``rm -rf`` - so a call that runs it is a call that
#: *could* rewrite the workspace.
_INLINE_CODE_FLAGS = {
    "python": {"-c"},
    "python3": {"-c"},
    "py": {"-c"},
    "node": {"-e", "--eval", "-p", "--print"},
    "ruby": {"-e"},
    "perl": {"-e"},
    "php": {"-r"},
    "bash": {"-c"},
    "sh": {"-c"},
    "zsh": {"-c"},
    "dash": {"-c"},
    "ksh": {"-c"},
}
_SCRIPT_EXT = (".py", ".js", ".mjs", ".cjs", ".sh", ".rb", ".pl", ".php", ".ts")


def _program_basename(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")


def command_may_modify_workspace(command: str) -> bool:
    """Conservative: True when a bash command could rewrite the workspace.

    Over-reporting only forces an extra verification pass; under-reporting lets
    a real write skip the verifier, so the heuristic errs toward True.
    """
    text = str(command or "")
    if not text.strip():
        return False
    # Output redirection writes a file no matter the program.
    if ">" in text:
        return True
    for argv in split_command_argv(text):
        if not argv:
            continue
        program = _program_basename(argv[0])
        rest = argv[1:]
        # M8-T323: ``tsc`` **emits** JavaScript next to the sources unless it
        # is told not to, and the emitted files are real build output - not a
        # cache like ``.mypy_cache``.  The evidence predicate calls ``tsc`` a
        # check, so the two answers have to agree about the side effect too:
        # otherwise the check that was supposed to *verify* the work also
        # produced the build output, and the task still looked read-only.
        if program == "npx" and rest and _program_basename(rest[0]) == "tsc":
            program, rest = "tsc", rest[1:]
        if program == "tsc":
            if not any(tok.startswith("--noEmit") for tok in rest):
                return True
            continue
        if program == "sed":
            if any(tok == "-i" or tok.startswith("-i") or tok.startswith("--in-place") for tok in rest):
                return True
            continue
        if program in _MUTATING_PROGRAMS:
            return True
        if program == "git" and rest and rest[0] in _GIT_MUTATING:
            return True
        if program in {"npm", "yarn", "pnpm", "pip", "pip3", "uv", "poetry", "go"} and any(
            tok in _PKG_MUTATING for tok in rest
        ):
            return True
        if program in {"npm", "yarn", "pnpm"}:
            # M8-T324: a **script** that rewrites the sources is a write:
            # ``npm run format`` (prettier --write) and ``npm run lint:fix``
            # (eslint --fix) rewrite the very files they look at.  The
            # evidence predicate calls ``format`` a check, so the two
            # answers have to agree about the side effect - otherwise the
            # "check" rewrote the change it was supposed to be verifying,
            # and the task still looked read-only.
            #
            # The check-only spellings (``--check``, ``:check``) stay
            # non-writes.
            if any(tok in {"--check", "--dry-run", "--list-different"} for tok in rest):
                continue
            script = ""
            if len(rest) >= 2 and rest[0] == "run":
                script = rest[1]
            elif rest:
                script = rest[0]
            if script:
                # The check-only spellings stay non-writes.
                if script.endswith(":check") or script.endswith("-check"):
                    continue
                base = script.split(":", 1)[0]
                if base in {"format", "fmt"} or script.endswith(":fix") or script.endswith("-fix"):
                    return True
            if any(tok in {"--fix", "--write"} for tok in rest):
                return True
        if program in _INTERPRETERS:
            flags = {tok for tok in rest if tok.startswith("-")}
            # M8-T322: inline code (``python -c``, ``node -e``, ``bash -c``)
            # can write anything, and this function's own contract says the
            # heuristic errs toward True - "under-reporting lets a real
            # write skip the verifier".  The old code skipped the whole
            # interpreter branch for ``-c``/``-m`` because inline code "is
            # not a workspace script", but that is a statement about where
            # the code comes from, not about whether it writes: a task
            # whose only change was ``python -c "open(f,'w').write(...)"``
            # was reported as **read-only**, so the verification stage was
            # skipped and the task was certified without being checked.
            #
            # ``-m`` is different on purpose: a module's main is usually a
            # checker, and the artefacts a check leaves behind are not
            # inputs (M8-T280) - so ``python -m pytest`` stays a non-write.
            if flags & _INLINE_CODE_FLAGS.get(program, set()):
                return True
            if "-c" in flags or "-m" in flags:
                continue
            # M8-T322: ``node --check <file>`` only **parses** the file - it
            # never runs it and never writes anything.  The write predicate
            # used to call it a write (the file name ends in ``.js``), while
            # ``is_verification_evidence`` called it verification - two
            # answers for one call.  And the verification plan *generates*
            # exactly this command, so every frontend task's own check
            # looked like a change: the task stopped being "read-only" and
            # the post-write evidence rule was satisfied by the check that
            # was supposed to be checking it.
            if program == "node" and "--check" in flags:
                continue
            if any(tok.endswith(_SCRIPT_EXT) for tok in rest if not tok.startswith("-")):
                return True
    return False


def is_workspace_write(tool: str, arguments: dict[str, Any] | None, status: str) -> bool:
    """True when a successful tool call actually changed (or may change) files."""
    if status != "ok":
        return False
    if tool in WRITE_TOOL_NAMES:
        return True
    if tool == "bash":
        return command_may_modify_workspace(str((arguments or {}).get("command") or ""))
    return False


# Only bash evidence can clear ``verification_required``. git_status / read_file
# / grep are useful inspection but they do not prove the change works.
#
# M8-T303: the marker list that used to live here was **never used** by the
# implementation - the rule is a whitelist over the command's *executable*
# (``checker_invocation``), not a substring search.  It stayed exported, and
# it advertised a rule that is not the rule: a reader would conclude that
# "pytest" appearing anywhere in a command made it verification evidence
# (``echo pytest`` does not).  A stale second copy of a rule is worse than no
# copy, so it is gone rather than kept in step.


def is_verification_evidence(tool: str, arguments: dict[str, Any] | None, status: str) -> bool:
    """True when a successful tool call is actual verification, not inspection."""
    if status != "ok" or tool != "bash":
        return False
    args = arguments or {}
    # M8-T279: a backgrounded command is not verification.  Starting it
    # returns ``status="ok"`` without running a single test, and the
    # predicate only looked at the command text - so
    # ``bash("python -m pytest", run_in_background=true)`` cleared
    # ``verification_required`` and counted as "the change was checked
    # afterwards".  The foreground path is safe (a non-zero exit becomes
    # ``status="error"``), but the background path never fails that way.
    if args.get("run_in_background"):
        return False
    command = str(args.get("command") or "")
    if not command.strip():
        return False
    # Merely printing a command, collecting tests or asking for --help cannot
    # prove anything about a change. Only actual checker executables count.
    if any(char in command for char in "&|;<>`$()%^!\n\r"):
        return False
    try:
        parts = command_parts(command)
    except ValueError:
        return False
    if not parts or any(part.split("=", 1)[0].lower() in {"--collect-only", "--co", "--help", "-h", "--version", "--showconfig", "--show-config", "--show-settings", "--show-files", "--listfilesonly", "--explainfiles", "--init"} for part in parts):
        return False
    executable, arguments = checker_invocation(command)
    if executable in {"pytest", "unittest", "mypy", "pyright", "tsc", "compileall"}:
        return True
    if executable == "ruff":
        return bool(arguments and (arguments[0] == "check" and "--fix" not in arguments or arguments[0] == "format" and "--check" in arguments))
    if executable == "node":
        return len(arguments) == 2 and arguments[0] == "--check"
    if executable in {"npm", "pnpm", "yarn"}:
        script = arguments[1] if len(arguments) >= 2 and arguments[0] == "run" else arguments[0] if arguments else ""
        return bool(re.fullmatch(r"(?:test(?::[\w-]+)?|check(?::[\w-]+)?|typecheck|lint|build)", script))
    return False


__all__ = [
    "WRITE_TOOL_NAMES",
    "command_may_modify_workspace",
    "is_verification_evidence",
    "is_workspace_write",
    "tool_requires_authorization",
]
