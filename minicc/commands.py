"""M7-T2: user-defined slash commands and skill discovery.

Custom prompts live in markdown files::

    <workspace>/.minicc/commands/<name>.md   (project scope, wins)
    ~/.minicc/commands/<name>.md             (user scope)

with an optional front matter block (``description``, ``argument-hint``) and
the prompt template as the body (``$ARGUMENTS`` plus ``$1``-``$9`` are
substituted). ``/name rest`` entered in the CLI REPL or the web chat is
expanded *server-side* into the user message. Expanded text enters the
conversation as ordinary user content — like AGENTS.md it is a working
agreement and can never rewrite system instructions or permission boundaries.

Skills live in ``<workspace>/.minicc/skills/<name>/SKILL.md`` (plus the user
counterpart). Only name + description are injected into the system prompt;
bodies stay on disk and the agent reads them on demand ("正文不常驻").
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COMMANDS_DIR_NAME = "commands"
SKILLS_DIR_NAME = "skills"
MAX_COMMAND_BODY_CHARS = 16_000
MAX_SKILL_DESCRIPTION_CHARS = 400
RESERVED_COMMAND_NAMES = frozenset({
    "help", "tools", "status", "view", "compact", "collapse", "expand",
    "clear", "exit", "quit",
})
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_POSITIONAL_RE = re.compile(r"\$\[?[1-9]\]?")


@dataclass(frozen=True)
class SlashCommand:
    name: str
    description: str
    argument_hint: str
    template: str
    path: Path
    scope: str  # "project" | "user"

    def to_public_dict(self) -> dict[str, Any]:
        # Deliberately omits the template body: listing must not dump content.
        return {
            "name": self.name,
            "description": self.description,
            "argument_hint": self.argument_hint,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    path: Path
    scope: str


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Parse a minimal ``---`` metadata block; unknown lines are ignored."""
    meta: dict[str, str] = {}
    body = text
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                meta_lines = lines[1:index]
                body = "\n".join(lines[index + 1:]).lstrip("\n")
                for item in meta_lines:
                    key, sep, value = item.partition(":")
                    if sep and key.strip():
                        meta[key.strip().lower()] = value.strip().strip("'\"")
                break
    return meta, body


def _read_markdown(path: Path) -> tuple[dict[str, str], str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    meta, body = _parse_front_matter(text)
    body = body.strip()[:MAX_COMMAND_BODY_CHARS]
    if not body:
        return None
    return meta, body


def _command_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.glob("*.md"))


def discover_commands(workspace: Path, *, home: Path | None = None) -> list[SlashCommand]:
    """Project commands override user commands by name; invalid files skip."""
    from .config import home_dir

    user_root = (home or home_dir()) / COMMANDS_DIR_NAME
    project_root = Path(workspace) / ".minicc" / COMMANDS_DIR_NAME
    found: dict[str, SlashCommand] = {}
    for root, scope in ((user_root, "user"), (project_root, "project")):
        for path in _command_files(root):
            name = path.stem
            if name in RESERVED_COMMAND_NAMES or not _NAME_RE.match(name):
                continue
            parsed = _read_markdown(path)
            if parsed is None:
                continue
            meta, body = parsed
            found[name] = SlashCommand(
                name=name,
                description=str(meta.get("description") or body.splitlines()[0][:120]),
                argument_hint=str(meta.get("argument-hint") or meta.get("argument_hint") or ""),
                template=body,
                path=path,
                scope=scope,
            )
    return sorted(found.values(), key=lambda command: command.name)


def _split_arguments(rest: str) -> list[str]:
    try:
        return [token for token in shlex.split(rest) if token]
    except ValueError:
        return rest.split()


def expand_slash_command(
    text: str, workspace: Path, *, home: Path | None = None
) -> str | None:
    """Expand ``/name args`` into its template, or None when not a command.

    Plain messages, reserved built-ins and unknown ``/names`` all return None
    so behaviour is unchanged for everything that is not a custom command.
    """
    raw = str(text or "").strip()
    if not raw.startswith("/"):
        return None
    head, _, rest = raw[1:].partition(" ")
    if not head or head in RESERVED_COMMAND_NAMES:
        return None
    for command in discover_commands(workspace, home=home):
        if command.name != head:
            continue
        expanded = command.template.replace("$ARGUMENTS", rest.strip())
        positional = _split_arguments(rest)

        def _positional(match: re.Match[str]) -> str:
            index = int(match.group().strip("$[]")) - 1
            return positional[index] if 0 <= index < len(positional) else ""

        return _POSITIONAL_RE.sub(_positional, expanded).strip()
    return None


def discover_skills(workspace: Path, *, home: Path | None = None) -> list[SkillEntry]:
    from .config import home_dir

    user_root = (home or home_dir()) / SKILLS_DIR_NAME
    project_root = Path(workspace) / ".minicc" / SKILLS_DIR_NAME
    found: dict[str, SkillEntry] = {}
    for root, scope in ((user_root, "user"), (project_root, "project")):
        if not root.is_dir():
            continue
        for skill_file in sorted(root.glob("*/SKILL.md")):
            parsed = _read_markdown(skill_file)
            if parsed is None:
                continue
            meta, _body = parsed
            name = str(meta.get("name") or skill_file.parent.name)
            if not _NAME_RE.match(name):
                continue
            found[name] = SkillEntry(
                name=name,
                description=str(meta.get("description") or "")[:MAX_SKILL_DESCRIPTION_CHARS],
                path=skill_file,
                scope=scope,
            )
    return sorted(found.values(), key=lambda skill: skill.name)


def skills_prompt_block(workspace: Path) -> str:
    """Name+description only — bodies are read on demand by the agent."""
    skills = discover_skills(workspace)
    if not skills:
        return ""
    lines = [f"- {skill.name}: {skill.description}" for skill in skills]
    return (
        "\n\n可用技能（仅列出名称与说明，正文不常驻上下文；需要时先用 read_file 读取对应 SKILL.md）：\n"
        + "\n".join(lines)
        + f"\n技能文件目录：{Path(workspace) / '.minicc' / SKILLS_DIR_NAME}"
    )


__all__ = [
    "COMMANDS_DIR_NAME",
    "RESERVED_COMMAND_NAMES",
    "SkillEntry",
    "SlashCommand",
    "discover_commands",
    "discover_skills",
    "expand_slash_command",
    "skills_prompt_block",
]
