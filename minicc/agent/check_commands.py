"""Portable command tokenization and conservative verification identities."""
from __future__ import annotations

def command_parts(command: str) -> list[str]:
    """Parse literal argv without evaluating a shell or eating path slashes."""
    tokens: list[str] = []
    current: list[str] = []
    quote = ""
    started = False
    index = 0
    while index < len(command):
        char = command[index]
        if char == "\\" and index + 1 < len(command) and command[index + 1] == quote and quote:
            current.append(quote)
            index += 2
            continue
        if char in {'"', "'"}:
            if not quote:
                quote = char
                started = True
            elif quote == char:
                quote = ""
            else:
                current.append(char)
        elif char.isspace() and not quote:
            if started:
                tokens.append("".join(current))
                current = []
                started = False
        else:
            current.append(char)
            started = True
        index += 1
    if quote:
        raise ValueError("unclosed command quote")
    if started:
        tokens.append("".join(current))
    return tokens


def checker_invocation(command: str) -> tuple[str, list[str]]:
    parts = command_parts(command)
    if not parts:
        return "", []
    executable = parts[0].replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")
    arguments = parts[1:]
    if executable in {"python", "python3", "py"}:
        while arguments and arguments[0] in {"-B", "-I", "-E", "-s", "-S", "-u", "-q"}:
            arguments = arguments[1:]
        if len(arguments) < 2 or arguments[0] != "-m":
            return "", []
        return arguments[1], arguments[2:]
    return executable, arguments


def verification_identity(command: str) -> tuple[str, ...]:
    """Unify display variants, never different test selections."""
    executable, arguments = checker_invocation(command)
    if executable in {"pytest", "unittest"}:
        arguments = [arg for arg in arguments if arg not in {"-q", "-v", "-vv", "-vvv", "--quiet", "--verbose"}]
        arguments = [arg.replace("\\", "/").removeprefix("./") for arg in arguments]
        return (executable, *arguments)
    return tuple(command_parts(command))
