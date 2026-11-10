# 安全政策

## 支持的版本

| 版本 | 支持状态 |
| --- | --- |
| v0.2.x（当前 main） | ✅ 积极维护 |
| 更早版本 | ❌ 不再维护（升级到最新 main 即可） |

## 报告安全问题

请不要用公开 issue 报告安全漏洞。请通过私密渠道联系仓库所有者（见仓库主页联系方式），或提交带 `[security]` 标记的 issue 并等待所有者私下联系。

报告时请附上：复现步骤、受影响的 minicc 版本（`minicc --version`）、是否可以在干净的 `--workspace` 复现。

## 本项目的安全边界（已实现的部分）

- 凭据文件（`.env`、`.env.local`、`secrets/`、`.ssh/`、`.aws/`）默认加入 `--setup` 生成的 `.minicc/permissions.json` 的 **deny** 列表；详见 `docs/OPERATIONS.md`。
- Web 界面的 bearer token 存放在 `.minicc/web_token.json`（mode 0600 的意图；Windows 上强制不了，仅尽力）；doctor 会检查其权限并给出修复提示（`minicc --doctor --json`）。
- `.minicc/` 在仓库 `.gitignore` 中；首小时文档建议把它再加进全局 gitignore。
- 审计日志（`.minicc/audit.jsonl`）记录高风险操作；doctor 会校验其每一行是合法 JSON。
- 任务产物完成度以 digest 只读校验为准（`docs/SNAPSHOT_COMPLETION_HARDENING.md`）。

## 已知限制

- minicc 会执行 agent 选定的命令；权限门（permissions.json）是 opt-in 的，未配置时走默认模式（等同于信任本机用户）。这不是 bug，是产品当前行为。
- 跨 web 重启的"运行中"任务不提供实时镜像；见 `docs/GAP_ANALYSIS_AND_ROADMAP.md` 记录的边界。
- Web 服务器绑定 `127.0.0.1`；暴露到局域网时 bearer token 是唯一防线——请勿将 token 提交到仓库。

## 更多

- 安全清单：[docs/SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md)
- 合流账本：[docs/ROADMAP_TO_PRODUCT.md](docs/ROADMAP_TO_PRODUCT.md)
- 变更记录：[docs/CHANGELOG.md](docs/CHANGELOG.md)
