"""The one spelling of every ``.minicc/`` internal filename.

These names are a shared vocabulary: the module that owns a file
reads and writes it by its name, and the tool deny-lists refuse the
agent access to it by the same name.  A leaf module is the only home
they can have - the owners (allowlist, permissions, mcp) sit above
the tools layer in the import order, so the tools layer cannot
import back from them.  One literal per name, here, and every other
site imports the constant: a deny list that spells a name its owner
has since renamed is a guard that guards nothing.
"""

ALLOWLIST_NAME = "allowlist.json"
AUDIT_NAME = "audit.jsonl"
HOOKS_FILENAME = "hooks.json"
PERMISSIONS_NAME = "permissions.json"
TOKEN_FILE_NAME = "web_token.json"
MCP_CONFIG_NAME = "mcp.json"
