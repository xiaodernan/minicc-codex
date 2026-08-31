# Public Reference Review

Research date: 2026-08-31

This note records design patterns taken from public documentation and source
inspection. The project keeps its own Python agent engine and native Web UI;
the references are not copied into the runtime.

## OpenHanako

Repository: <https://github.com/liliMozi/openhanako>

- Apache License 2.0.
- Electron 42, React 19, Zustand, Vite, Hono, and SQLite.
- A server-first split keeps the engine, server, desktop renderer, bridges, and
  plugins separate.
- The useful patterns for this project are local-first data ownership, explicit
  session/file sidecars, a plugin contract, event-driven background work, and
  durable recovery metadata.

## cc-haha

Repository: <https://github.com/NanmiCoder/cc-haha>

- The repository declares MIT for its own distribution, but its README states
  that it is based on leaked Claude Code source. This project does not copy its
  source, bundled assets, or proprietary upstream implementation.
- Tauri 2 provides a Rust desktop host, a WebView frontend, sidecar processes,
  IPC commands/events, and capability/CSP configuration.
- The safe ideas to study are bounded event buffering, resumable session
  metadata, explicit cancellation propagation, and transport adapters.

## Frakio Work

Repository: <https://github.com/MadsGao/frakio-work>

- Electron 43, React, Zustand, Vite, Hono, SQLite, and multiple runtime
  adapters.
- The Frakio Work Community License requires a commercial license for modified
  derivative works, redistribution, sales, or hosted service. Its source,
  screenshots, logo, and brand are therefore not copied here.
- The high-level UI direction is valuable: a calm light frame, a left
  workspace/conversation rail, one spacious central work surface, a single
  composer, compact activity summaries, and an optional detail panel.

## Tauri in Plain Language

Tauri is a desktop application shell, not a CSS framework. The frontend still
uses HTML/CSS/JavaScript, while a Rust host creates the native window and
communicates with the frontend through commands and events. Windows normally
uses WebView2, macOS uses WebKit, and Linux uses WebKitGTK. Compared with
Electron, a Tauri package is usually smaller because it reuses the system
WebView, but it adds Rust tooling, platform-specific packaging, and a stricter
IPC/security model.

For minicc, the conservative path is to keep the working Python service and
Web UI. A future desktop build can use Tauri to launch the Python service as a
sidecar, wait for a health endpoint, pass a per-process local token, forward
close/cancel signals, and shut the child down cleanly. Rewriting the Agent
engine in Rust is not required to gain a Tauri desktop shell.

## Applied Here

The current UI change is an original Frakio-inspired layout adaptation. It
keeps the existing task APIs, SSE replay, image attachments, timeline folding,
completion review, workspace inspector, and Plants vs. Zombies entry point.
The inspector is still available through its existing toggle, but the central
conversation is the default focus. No third-party source or visual asset was
copied.

References:

- <https://v2.tauri.app/concept/architecture/>
- <https://v2.tauri.app/concept/inter-process-communication/>
- <https://v2.tauri.app/security/>
- <https://github.com/liliMozi/openhanako>
- <https://github.com/NanmiCoder/cc-haha>
- <https://github.com/MadsGao/frakio-work>
