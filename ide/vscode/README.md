# minicc VS Code extension

Lightweight helper for the local minicc workbench. It does not embed an agent
runtime; it talks to the same process you already started with `minicc-web`.

## Commands

- **minicc: Open Workbench** — opens `minicc.workbenchUrl` (default `http://127.0.0.1:8765`).
- **minicc: Send Selection** — copies the current selection (or the whole file) to the clipboard so you can paste it into the workbench composer.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `minicc.workbenchUrl` | `http://127.0.0.1:8765` | Local workbench URL |

Install from this folder with `code --install-extension .` after opening `ide/vscode`, or use **Extensions: Install from VSIX** once packaged.
