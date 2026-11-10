# minicc 运维与自检手册

这份手册讲一件事：**一台机器能不能拿来跑 minicc**，以及出了问题先看什么。
所有自检都是离线的——不调网络、不加载模型、不运行测试套件、不修改已有状态（除非你明确跑 `--setup` 且目标文件不存在）。

## 1. 从空目录到可跑

全新环境（没有 `.env`、没有 `MINICC_API_KEY`）也能完成这一节的所有步骤：

```powershell
minicc --setup --workspace <目录>      # 或 python -m minicc.setup <目录>
minicc --doctor --workspace <目录>     # 人可读报告
minicc --doctor --json --workspace <目录>
minicc --doctor-strict --workspace <目录>   # CI 守门：warning 也算红
```

`--setup` 只创建缺失的骨架：`<目录>/.minicc/permissions.json`（默认 deny `.env`、`.env.local`、`secrets/`、`secrets/**`、`.ssh`、`.aws`）与 `<目录>/.minicc/web_token.json`（0o600）。**已存在的文件绝不覆盖**。

`--doctor` 逐项报告并给出 `fix_hint`，覆盖：Python ≥ 3.11、`import minicc`、`minicc/` 全量 `py_compile`、`.minicc/` 可写、审计日志最后一行是合法 JSON、`web_token.json` 权限位、`permissions.json` 能否解析、git work tree。

`--doctor` / `--doctor-strict` / `--setup` 在配置解析（`_load()`）之前分发：它们不需要 `MINICC_API_KEY` 与 `MINICC_BASE_URL`，也不访问网络。其余命令（REPL、`--print-config`、 Editor 创建、`--fork-from` 之外的一切）仍然按旧规则解析配置。

`--json` 只与 `--doctor` / `--doctor-strict` / `--stats` / `--capabilities` / `--version` 搭配；单独给 `--json` 是用法错误（exit 2）。JSON 形状：诊断系列为 `{"ok":…, "warn":…, "fatal":…, "checks":[{"name","severity","detail","fix_hint"}]}`，`--capabilities` 为 `{"count":N,"tools":[{"name","description"}]}`，`--version` 为 `{"name":"minicc","version":"<semver>"}`。`--doctor` 不输出 JSON，除非你要它的 `checks` 数组。

退出码契约：

- `0`：没有 fatal；对 `--doctor-strict` 额外要求没有 warning；
- `1`：至少一个 fatal（`--doctor`），或存在 warning/fatal（`--doctor-strict`）；
- `2`：用法错误（argparse 拒绝、`--json` 无 `--doctor*`、无 `MINICC_API_KEY` 的 REPL 启动等）。

## 2. 人可读 / 机器可读格式的使用场景

- 人跑：默认人可读报告，`✓`/`△`/`✗` 风格的 `[ok]/[warn]/[fail]` 前缀，每项后跟 `detail`，失败项再跟一行 `→ fix_hint`。
- CI / 脚本：`--doctor --json`，直接 `python -c "import json,sys; d=json.load(sys.stdin); sys.exit(1 if d['fatal'] else 0)"` 消费；`--doctor-strict --json` 直接以退出码守门。
- 任何 CI 面的「必须绿」门建议固定用 `--doctor-strict`，不要依赖 grep 输出文本。

## 3. Web 面：`/api/health` 与 `/api/doctor` 分工

- `GET /api/health`：**liveness only**，恒 `{ok: true, service: "minicc"}`，不做探测，可串进 load balancer / k8s probe，任意客户端可读。
- `GET /api/doctor`：**diagnostic**，`run_doctor()` 的完整 JSON 报告，与 `/api/*` 一样需要 bearer token（或 `token` query）。**不**挂在 health 上——probe 每秒轮询时跑全量 `py_compile` 既慢又会把 liveness 成本放大到与包大小成正比。
- 诊断端点自身故障时退回 `{ok:0, warn:0, fatal:1, checks:[{name:"doctor_runner", …}]}`，不传播 500。

## 4. CI 里的跑法

- 仓库自带的 **M1 reliability probe**（见 `scripts/reliability_probe.py`）会在 CI 中：跑 9 个 M1 目标 pytest、再跑一次 `--setup` → `--doctor` 端到端 roundtrip、最后做凭据扫描。
- `--doctor` 在 pristine tree 上失败（exit 非 0）的典型原因：CI runner 没有 `MINICC_API_KEY`/`.env`，而 doctor 分发落在了 `_load()` **之前**（本手册第 1 节的契约）——这正是这份分发顺序存在的原因（批次 696 修）。
- 凭据扫描是「本机状态不泄漏 provider key 形状」的证明；`published` 计数（key 形状出现在已跟踪文件里）是披露而非泄漏。

## 5. 磁盘纪律

`workspace/.minicc/` 是**本地状态目录**：历史会话、审计日志（`audit.jsonl`）、`allowlist.json`、`todos.json`、`web_token.json`、`permissions.json`、任务快照都会落在这里。它不受 git 跟踪；不要把它纳入提交、不要整目录删除。`--doctor` 对它只有读与「建 + 删一个 probe 文件」两种操作，其余一律只读。

`permissions.json` 的 schema 以 `minicc/permissions.py` 的 `load_permission_rules` 为准；手改后务必 `--doctor` 验证 `permissions_json` 项。

## 6. doctor 不是什么

- 不是修复器：它只报，不改。`chmod 600`、修 `permissions.json`、装缺失依赖都要人来做。
- 不是测试运行器：它不跑 `pytest`。
- 不是网络探测：不 ping 任何 provider。
- 不是日志解析器：`audit_log` 只检查最后一行可解析成 JSON，不给出「是不是攻击」的判断。

## 7. 相关文件

- `minicc/doctor.py` — 八个探测与 `DoctorCheck`/`DoctorReport` 类型、`format_report` 的两种输出；
- `minicc/setup.py` — `--setup` 骨架逻辑；
- `minicc/main.py` — CLI 分发顺序与 `--json` 用法错误守卫；
- `minicc/webserver.py` — `/api/health` 与 `/api/doctor` 两个端点分工；
- `scripts/reliability_probe.py` — CI 中的 M1 + setup→doctor roundtrip 守卫；
- `docs/ONE_FACT_ONE_HOME.md` — 同一事实只许一个家的方法论，本手册的 doctor 探测文档与这套纪律同源。
