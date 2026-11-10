# minicc 首小时手册

> 全局索引：[INDEX.md](INDEX.md)。

目标：装完到能在一次真实任务里交付，路径上每一步都可以复制粘贴运行；每步的输出都把**实际**结果写下来（不是营销话术）。

本文只面向第一次用的人。自检的参数语义请看 [`OPERATIONS.md`](OPERATIONS.md)；`minicc --print-config` 的原理见 [`README.md`](../README.md)；服务面（registry/gateway/inspector/tasks）见 [`docs/SERVICE_PLANE_PLAN.md`](SERVICE_PLANE_PLAN.md)。

## 1. 装

```powershell
python -m pip install -e ".[dev]"
```
（在干净 venv 走 `pip wheel . && pip install dist/*.whl` 也可以。）

## 2. 准备工作区骨架

```powershell
minicc --setup --workspace C:\path\to\target
```

实测输出（节选，当前 tip）：

```
minicc --setup: workspace ready
created C:\path\to\target\.minicc
wrote permissions.json: deny [.env, .env.local, secrets, secrets/**, .ssh, .aws]
wrote web_token.json: bearer token (0o600 intended)
web bearer token lives at .minicc/web_token.json — do not commit it
```

**只写缺失的文件，绝不覆盖已有**——重跑是安全的。

## 3. 自检（不需要 key）

```powershell
minicc --doctor --workspace C:\path\to\target
minicc --doctor --json --workspace C:\path\to\target
minicc --doctor-strict --workspace C:\path\to\target    # CI 守门：warn 也算红
```

实测（全空，非 git 树）：

```
minicc doctor — ok=5 warn=3 fatal=0
[ok] python_version: python 3.11.1
[ok] minicc_import: import ok — 0.2.0
[ok] module_compiles: 91 modules compiled
[ok] minicc_dir_writable: .minicc/ writable
[ok] audit_log: no audit.jsonl yet — nothing to audit
[warn] web_token_permissions: mode 666 (not enforced on Windows)
[warn] permissions_json: no permissions.json; all calls follow the default mode
   → copy a minimal allowlist (deny secrets/) if you rely on it
[warn] git_worktree: not a git work tree — benchmarks and change-list cannot run; agent can still edit
```

注意几个点：

- **`web_token_permissions` 在 Windows 下是 warn**（NTFS 模式位无意义），不是 fatal；
- **`git_worktree` warn** 只是告诉你这个目录不是 git 仓库——agent 仍能干活，只是 benchmarks/changes 命令会灰；
- 加入 git 后 `git_worktree` 会变成 ok，并继续通过 `--doctor-strict`（如果你还没放行 permissions.json，strict 依旧红——CI 需要那个红）。

`--json` 输出是一个压缩 JSON：

```json
{"ok": 5, "warn": 3, "fatal": 0, "checks": [{"name": "python_version", "severity": "ok", "detail": "python 3.11.1", "fix_hint": null}, ...]}
```

## 4. 现状清单（也不需要 key）

```powershell
minicc --stats --workspace C:\path\to\target
minicc --stats --json --workspace C:\path\to\target
```

实测：

```
minicc stats — workspace C:/path/to/target
state: present (.minicc/, 332 bytes)
audit: absent
tasks: absent (no tasks.sqlite3)
sessions: 0 stored, 0 messages
```

想知道 `tasks.sqlite3` 里有多少 by status？`--stats --json` 的 `tasks` 子树：`{"present": false, "total": 0, "by_status": {"queued": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0, "interrupted": 0}, "other": 0}`。

## 5. 版本

```powershell
minicc --version
minicc --version --json
```

```
minicc 0.2.0
```

```json
{"name": "minicc", "version": "0.2.0"}
```

## 6. 第一次进模型（需要 key）

```powershell
$env:MINICC_API_KEY = "sk-..."
minicc "list the files in the current directory and count them"
```

注意：这里**没有** `--print-config`——先把 `minicc.config.example` 复制成 `.env` 比读 README 快得多。`--api-key` 与 `.env` 的优先级：命令行 > `.env` > `os.environ`。

## 7. 交付

`minicc` 退出后 `.minicc/web_token.json` 可能已生成（仅用于 Web 界面；首次用 `minicc-web` 时自动）。minicc 自己的 `.gitignore` 已经包含了 `.minicc/`；你在别的 git 仓里跑 `minicc` 时，顺手再加一行到 `~/.gitignore_global` 或本仓 `.git/info/exclude` 即可：

```
.minicc/
```

## 8. 卡住了先看哪里

- 测试没跑通：`pytest`，然后 `scripts/reliability_probe.py`；
- Web 不出页面：`python -m minicc.web --workspace C:\path\to\target` 然后 `curl http://127.0.0.1:8765/api/health`；
- 权限门红了：**先** `--doctor --json` 看哪一项红，再派 `fix_hint`；
- `--doctor-strict` 报警：先把所有 `warn` 清干净（补 permissions.json / 移入 git 树 / 重启审计日志）。

---

下一步：读 [docs/CLI_REFERENCE.md](CLI_REFERENCE.md)（全部旗标，实录）→ 读 `docs/OPERATIONS.md`（参数详解与排障表）→ 读 `README.md`（所有能力的总清单）→ 读 `docs/CHANGELOG.md`（本次合流的批次清单与已知边界）。完整索引：[docs/INDEX.md](INDEX.md)。服务面部署：[docs/SERVICE_PLANE_OPERATOR.md](SERVICE_PLANE_OPERATOR.md)。
