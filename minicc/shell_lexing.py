"""Shell lexing constants shared across the codebase.

The quote character set is used by:
- minicc.agent.check_commands.command_parts
- minicc.tools.bash._has_unquoted_background_operator
- minicc.tools.bash._tokenize_segment
- minicc.tools.bash.split_command_argv
- minicc.config._parse_dotenv
- minicc.config workspace_roots parsing

One home for the fact "these are the quote characters".
"""

from __future__ import annotations

#: The set of quote characters recognized by the shell tokenizer.
QUOTE_CHARS = frozenset({'"', "'"})