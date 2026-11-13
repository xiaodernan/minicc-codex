# minicc CLI 参考

本文只覆盖**命令行旗标**，按本机 `minicc --help` 的实际输出编写（英文 flag 名以源码 `minicc/main.py` 的 `add_argument` 为准）。运维语义（doctor 怎么退出、stats 的键形状、退出码契约）见 [OPERATIONS.md](OPERATIONS.md)；环境变量见 [README.md](../README.md)。

## 约定

- 不带任何旗标直接 `minicc "<prompt>"` 进入 agent 模式；
- 带本页"自检旗标"（`--doctor` / `--doctor-strict` / `--stats` / `--capabilities` / `--setup` / `--print-config` / `--version`）时只做该事，打印后退出，不进 agent；
- `--json` 只对 `--doctor` / `--doctor-strict` / `--stats` / `--capabilities` / `--version` 有意义；

## 旗标分类

### 连接与模型

| 旗标 | 作用 |
| --- | --- |
| `--base-url URL` | OpenAI 兼容接口地址（默认来自 env/config） |
| `--api-key KEY` | API 密钥；优先级：命令行 > `.env` > `os.environ` |
| `--model NAME` | 模型名（如 `gpt-4o`） |
| `--reasoning-effort {high,low,max,mid,ultra,xhigh}` | 推理强度 |
| `--provider-type {anthropic,auto,openai}` | provider 协议 |
| `--fallback-models LIST` | 逗号分隔的备用模型列表 |
| `--tool-mode {auto,envelope,native}` | 工具调用模式 |
| `--output-style STYLE` | 输出风格（如 concise / explanatory） |

### 安全姿态

| 旗标 | 作用 |
| --- | --- |
| `--sandbox {auto,docker,host}` | 命令执行沙箱 |
| `--yolo` | 自动批准文件写入与命令 |
| `--allow-network` | 允许联网工具（web_search / webfetch） |
| `--permission-mode {acceptEdits,default,plan,yolo}` | 权限模式；`plan` 只规划不写 |
| `--subagent-writable` | 允许委派任务以 acceptEdits 写（M6-T1 默认只读计划） |

### 上下文与压缩

| 旗标 | 作用 |
| --- | --- |
| `--context-window N` | 上下文窗口 token 数 |
| `--soft-max-tokens N` | 软上限 token 数（尾声阶段硬停） |
| `--compact-threshold N` | 压缩阈值（字符） |
| `--max-turns N` | 最大模型轮次 |
| `--timeout SECONDS` | 单 provider 调用超时 |
| `--max-concurrent-tasks N` | 最大并发任务（1-64） |

### 会话与 fork

| 旗标 | 作用 |
| --- | --- |
| `--session-id ID` | 会话名；`latest` 为最近 |
| `--resume` | 恢复当前/最近会话 |
| `--list-sessions` | 列出已保存会话 |
| `--fork-from MESSAGE` | 从某条消息处 fork（配合 `--session-id`） |
| `--new-session-id NAME` | fork 结果的会话名（可选） |
| `--auto-resume` | web 启动时自动恢复中断任务 |
| `--task-executor {process,thread}` | 任务执行器（进程/线程） |

### 自检与输出（只读）

| 旗标 | 作用 |
| --- | --- |
| `--setup` | 创建 `.minicc/` 骨架（permissions.json + web_token.json）；只写缺失、不覆盖 |
| `--doctor` / `--doctor-strict` | 自检；strict 使 warn 也算 fatal |
| `--stats` | 现状清单（state/audit/tasks/sessions + cache 的 live_backend/LRU 用量/inflight 盘点数据结构） |
| `--capabilities` | 注册的工具与能力清单（JSON） |
| `--print-config` | 打印生效配置（脱敏） |
| `--version` | 版本号；`--json` 输出 `{"name": "minicc", "version": ...}` |
| `--json` | 搭配上组旗标输出压缩 JSON |
| `--verbose-tools` | 默认展开全部工具结果（否则 `/collapse` 可折叠） |
| `--no-stream` | 关闭流式输出 |
| `--fork-from` | 见上 |

## `minicc --help` 原文

```
usage: minicc [-h] [--workspace WORKSPACE] [--base-url BASE_URL]
              [--api-key API_KEY] [--model MODEL]
              [--reasoning-effort {high,low,max,mid,ultra,xhigh}]
              [--tool-mode {auto,envelope,native}]
              [--output-style OUTPUT_STYLE]
              [--compact-threshold COMPACT_THRESHOLD] [--max-turns MAX_TURNS]
              [--timeout TIMEOUT] [--context-window CONTEXT_WINDOW]
              [--soft-max-tokens SOFT_MAX_TOKENS]
              [--max-concurrent-tasks MAX_CONCURRENT_TASKS]
              [--sandbox {auto,docker,host}]
              [--provider-type {anthropic,auto,openai}]
              [--fallback-models FALLBACK_MODELS]
              [--task-executor {process,thread}] [--auto-resume] [--yolo]
              [--allow-network]
              [--permission-mode {acceptEdits,default,plan,yolo}]
              [--subagent-writable] [--no-stream] [--verbose-tools] [--resume]
              [--list-sessions] [--fork-from MESSAGE] [--new-session-id NAME]
              [--session-id SESSION_ID] [--print-config] [--setup] [--doctor]
              [--doctor-strict] [--stats] [--capabilities] [--json]
              [--version]
              [prompt ...]
```

（自检类旗标的 `--json` 不在上面 usage 行里展开；语义以 `minicc --doctor --help` 等二级 help 为准。README 描述了与这些旗标同名的环境变量。）
