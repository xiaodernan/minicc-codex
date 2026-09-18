# minicc 全面优化交付说明

日期：2026-09-18。范围：[项目整体评审](PROJECT_REVIEW_2026-09-18.md)和[实现计划 A1–E2](DEEP_OPTIMIZATION_PLAN.md)。本次在当前工作区完成实现及定向验收，保留原有未提交工作，没有执行 reset/stash，没有提交或发布。

## 交付结论

已落实评审中的检索、压缩、完成评估、变更驱动验证、行为评测、任务权限、进程恢复、长流、持久化、搜索、Git 摘要、首屏加载、静态资源、亮暗主题、移动端、交互和模块边界优化。不是仅提供计划；代码、验收用例和构建产物均在工作区。

本地交互性能显著改善，真实模型 API 与修复闭环已验证。真实模型仅运行两个不同修复样本及一个最终版本重复样本，不能从这些结果推导通用编码准确率，也不能把组件测试成功率当成模型能力。

## 1. 准确率和可验证完成

| 计划 | 最终实现 | 主要代码 |
|---|---|---|
| A1 | 目录遍历前剪枝；排除依赖、隐藏缓存及生成目录；跨请求有界索引；按文件元数据增量解析；查询必须有实际相关性；提取更多符号，避免 error 普通文本伪装测试失败 | `minicc/agent/retrieval.py`、`minicc/web.py` |
| A2 | 按完整并行工具轮次保留上下文；原始目标与最近修正保留；发送前校验 tool call/result；历史中断仅补记“结果未知”，先检查现场，避免重做副作用 | `minicc/agent/context.py`、`minicc/agent/loop.py` |
| A3 | complete 必须具备正确类型字段、可核对的事件编号及修改后证据；失败验证不能被 skipped 覆盖；按事件裁剪后序列化有效有界 JSON | `minicc/agent/completion.py` |
| A4 | 按变更选择关联 Python 测试、JS 语法及项目脚本；递归规则支持 web/**；执行全部选定命令；相同依赖和权限下复用成功验证；JSX/数据变化使缓存失效 | `minicc/agent/verification_plan.py`、`verifier.py` |
| A5 | 12 个独立行为任务；隔离临时 Git 仓库；评分器不放入任务目录；行为边界/异常/输入不变性验收；完成率、覆盖率、验收率、误完成率分别统计；续跑校验模型、协议、源码、推理强度和 fixture | `minicc/behavior_bench.py`、`benchmarks.py`、`benchmarks/behavior-tasks.json` |

有效验证不再由 `echo pytest`、`--collect-only`、`--help` 等触发。真实样本还暴露并修复了 `python -B -m unittest` 漏认问题，避免已通过的检查被反复要求。

评测器也补了自身验收：12 个原始缺陷均被判失败，12 个独立参考修复均通过；`SystemExit(0)` 不能在未执行断言时伪装成功，正确的本地 helper 导入可用。评分器是受控行为测试，不是对抗性隔离沙箱。

## 2. 后端可靠性和架构

B1–B5 已完成，详见[后端交付记录](BACKEND_OPTIMIZATION_DELIVERY.md)。

- `task_contract.py` 共用版本化 TaskRequest/TaskResult，线程和进程完整传递权限、附件、恢复、推理配置。plan 将冲突写权限归一为 false。事件沿用 `agent/protocol.py` 的可重放封装。
- `task_store.py` 原子租约、独立心跳、同事务 owner 校验，旧 worker 不可覆盖新执行结果；SQLite WAL 与连接显式关闭。
- `task_execution.py` 负责 worker 镜像/重连，使用单调绝对流偏移，16000 字符尾窗口之后继续输出；累计 usage 避免重复相加。
- `task_persistence.py` 合并后台保存，delta 回调只更新内存；文件 digest 与 DB 写入移出流回调锁；终态强制落盘，防止旧快照覆盖。
- 历史搜索迁移为脱敏文本投影，支持 Unicode casefold、工作区索引、可用时 FTS5 trigram；短查询/不具备 FTS5 时使用兼容回退，更新及裁剪同步。

新增真实子进程集成测试：先输出 16050 字符并在模型调用内等待，关闭宿主、启动新宿主，核对原 PID/租约未变、没有第二次调用、后续长流继续、最终完成落盘。该路径已通过。

保持单机模块化服务与 SQLite。线程执行器仍不能在宿主退出后继续；独立进程能继续并重连。失效租约后的恢复不等同于恢复模型请求内部状态。

## 3. 性能结果

以下为同一台 Windows 开发机的局部观测，不是生产 SLA，不是大规模 p95。

| 指标 | 评审基线 | 实现后观测 |
|---|---:|---:|
| 改动摘要 | 9273.7ms，77 次 git show | 冷 398.5ms，热 206.45ms；冷请求仅 status/rev-parse/diff 三次 Git，0 次 show |
| 索引核心源码 | minicc/ 为 0 | minicc/ 为 61；总计 145 文件、4066 符号，未截断 |
| run_agent 定位 | 返回 README/历史浏览器快照 | 第一条 minicc/agent/loop.py |
| 检索 | 每轮重建，约 0.89–2.43 秒 | 冷查询 263.59ms，热查询 2.77ms；无变化刷新重建 0 文件 |
| 工作台 ready | 10951ms，启动页等待摘要 | 实际 HTTP 热刷新 279ms；模拟 1000ms Git 延迟时 302–344ms 已进入 |
| 主要静态资源 | app 269KB + game 109KB + CSS 176KB，未压缩传输 | 当前 gzip 传输 app 约 57KB、CSS 约 22KB；游戏首屏 0 次请求 |
| 手机发送按钮 | 390×844 下底部 856px，被裁切 | 底部 826px，完整位于视口；390×430 键盘高度模拟通过 |

摘要使用 NUL 格式解析路径，支持中文、空格、重命名、新仓库 staged 后又修改/删除；patch 按需生成，列表不逐文件读取 HEAD。缓存绑定 HEAD、状态和文件元数据。

静态资产使用内容 hash、压缩、ETag：HTML 和资源别名重新校验，hash URL 长期缓存。已验证 304、gzip;q=0.5 和 gzip;q=0。旧 hash 资产保留，防止已打开页面的引用失效。

原始记录：`output/optimization-performance.json`、`output/playwright/frontend-optimization-metrics.json`。

## 4. 前端视觉与交互

- 删除累积的多套主题覆盖，统一语义调色板、布局、字体、间距、按钮和焦点状态。保留游戏与宣传页的独立样式。
- 桌面/手机亮暗主题四组通过；主文字对比度 14.02–17.43、次级 6.02–6.75、弱标签至少 4.84，均高于 4.5。
- VisualViewport 和安全区适配；输入及发送区域不会被顶部栏和软键盘高度挤出；没有横向溢出。
- 文件、命令、网络三项有效权限清晰显示；联网开关可见；图标按钮有名称、键盘焦点；radio/tab 可操作。
- 空会话三个真实动作；检查器改为“改动 / 文件 / 验证”；宣传与小游戏移至次级入口；游戏显式进入后加载。
- 首屏只等工作区元数据，历史/摘要/文件树独立加载；工作区版本和请求序号阻止旧响应污染新工作区。
- `core/transport.js` 独立网络层；`core/task-reducer.js` 纯状态归并；`chat/timeline-dom.js` 增量保留时间线节点、展开状态和阅读位置。
- 已移除无引用 01–09 旧分片和废弃迁移脚本，README 改为当前 ES 模块构建说明。

截图：

![桌面亮色](../output/playwright/optimized-1440-light.png)

![手机暗色](../output/playwright/optimized-390-dark.png)

截图前端状态使用受控 fixture；`output/playwright/production-desktop.png` 是真实本地 HTTP 及数据库状态。

## 5. 真实模型验收

用户授权使用新 API 后读取现有配置，没有输出或写入凭证，没有修改用户模型配置。

- 配置：`gpt-6-astra`，Responses，reasoning effort=max。
- 连通性：精确返回 MINICC_API_OK，8.71 秒，40 total tokens（服务返回值）。
- 两个不同隔离任务：clamp 与 chunks 均完成，并通过独立边界验收，每项 5 个检查；分别约 317.3 秒、224.0 秒。
- 最终修复后的版本又运行 clamp：通过，209.8 秒，17 轮、24 工具调用；服务返回 97020 total tokens，其中 52224 cached prompt tokens。
- 原始输出在 `output/api-smoke-20260918.json`、`output/behavior-live-results.json`、`output/behavior-final-results.json`，报告保留 fixture hash、模型配置和可用的源码 hash。

这只是小样本可用性验收，不能宣称总体 100% 准确，也没有足够证据把不同运行耗时直接解释为算法收益。12 个样本的验收器均已验证，但没有重复运行全部真实模型样本来凑分。费用单价没有可靠来源，报告保留 N/A；未观测到的重复工具率也保留 N/A。

## 6. 验证记录与复现

遵循“不总跑全量回归”：按改动分组，发现新问题后仅重跑相关检查，没有执行整个 tests 全量。

| 验证 | 结果 |
|---|---|
| 准确率、检索、P0/P1/P2、自动恢复定向组 | 50 项通过 |
| core 协议、压缩、完成评估、验证器、恢复组 | 13 项通过，102 项未选 |
| worker/持久化与搜索 | 11+7 项通过；调整后相关组再次通过 |
| core 任务管理/存储/检查点 | 21 项通过 |
| 实际 worker 重启与长流 | 单独通过，原分组 13 项通过 |
| 最终评测/摘要/静态资源/验证策略/权限组 | 36 项通过，15.80 秒，JUnit 见 output/optimization-final-checks.xml |
| HTTP gzip/ETag 独立检查 | 通过 |
| npm run test:optimization | 四组视口/主题及状态协议通过 |
| npm run test:web | 真实本地 HTTP 的 timeline / product path / desktop / mobile 通过 |
| npm run build:web、npm run check:web | 通过 |
| git diff --check | 通过 |

各分组存在重叠，不相加为总覆盖率。CI 加入前端定向优化检查。

推荐复现：

```powershell
python -m pytest tests/test_optimization_core.py tests/test_behavior_bench.py tests/test_benchmark_runner.py tests/test_verification_command_variants.py tests/test_permission_modes.py -q -o addopts=''
python -m pytest tests/test_task_worker.py tests/test_task_durability.py tests/test_history_search.py -q
npm run check:web
npm run test:optimization
```

真实评测为显式运行：`python -m minicc.benchmarks --suite behavior --run --max-tasks 2 --task-timeout 360 --results output/behavior-results.json`。无 `--run` 只生成报告，不调用模型。版本/配置变化会阻止复用旧评分。

## 7. 当前工作区与使用

当前分支 main；基线提交 `f1a380dbf785357842fde3e92740e7cf06987dea`。工作区开始时已有许多未提交修改，本次没有将全部 git diff 归为自己的成果。交付包含已修改和新增文件，后续提交时应整体检查，尤其不要漏掉运行时新模块、测试、web/asset-manifest.json 与 web/assets。

启动仍为 `python -m minicc.web --workspace <工作区> --port 8765`；如要服务重启后任务继续执行，设置 `MINICC_TASK_EXECUTOR=process`。默认线程模式保持轻量。

验证规则可放 `.minicc/verification.json`；未知技术栈不会假装已有验收，也不会默认扩大全量测试。新增语言或工作流时应补针对性规则和行为样本。

## 8. 继续实施：第二轮边界收敛

用户追加“所有能做的都做完”后，继续针对真实可复现的问题完成 F1–F4，而非重复第一轮检查。本轮未增加真实模型调用费用；已有真实样本仍只作为小样本链路证据。

### 验证与准确率

- 自动验证传入任务取消信号，终止正在执行的测试进程，不再运行后续检查或完成评估。已有默认执行器支持进程树停止，现已接入。
- 缓存身份包含实际执行命令、权限、工作区和新鲜输入；旧 plan 对象也会重新确认输入。命令改变、依赖变化、检查期间文件变化均不会复用旧通过结果。
- 检查缓存最多 16 项；指纹扫描有文件数/字节上限，读取不完整、大文件等情况禁用复用。隐藏配置纳入确认；存在 `.env`/私钥类输入时不读取秘密内容，而是禁用复用。
- 后续失败的检查会推翻同命令早先成功；取消验证不能当作完成。`--collect-only=true`、`tsc --showConfig`、只做写入的 `ruff format` 等不再算验证。
- 配置类型、路径、大小、规则数和命令数均有清晰错误；错误返回“验证阻塞”，不把内部异常丢成不明失败。验证输出在进入证据前脱敏。
- 系统提示明确要求定向验证、复用未变化的有效检查、合并独立只读调用；简单修复避免不必要的子代理与逐项 todo 更新。没有把提示变化宣称为已证明的模型加速。

### 评测闭环

- JSON 结果写入临时文件并原子替换；中断不会截断已有结果。配置、源码、fixture 必须在同条记录中一致才可续跑，不相容结果不会混入新报告。
- 支持 `--task-id` 和 `--no-resume`；小于 60 秒的超时按实际值生效。取消、部分完成、评分异常和清理失败有独立状态；不将取消/partial 交给 grader 粉饰为成功。
- 超时 worker 未退出时停止后续派发，等待结束后再清理服务，避免删除仍在使用的目录；Ctrl+C 先保存中断记录。
- 失败样本开销计入每次成功成本；执行/评分/总耗时分列，缺测保持 null。异常输入分支也验证输入不变，布尔返回不接受整数冒充。
- 使用方法和口径见 [定向行为评测](BENCHMARK_EVALUATION.md)。

### 前端与任务启动

- 弹窗新增集中焦点生命周期：Tab 循环、背景 inert、Escape 和触发器焦点恢复。文件树支持方向键/Home/End、单一 Tab 入口。
- 独立视图作用域 `core/scope.js` 防止旧详情/预览/回退响应污染新会话；提交令牌隔离重叠提交。后台任务完成不抢焦点，终态 SSE 不被滞后 running 快照覆盖。
- HTTP 封装支持调用方 AbortSignal 和 Headers，区分主动取消、超时、响应体超时、无效 JSON；监听器有退出清理。
- 内存会话视图最多 24 项、终态去重最多 2048 项，渲染历史键最多 48 项；活跃任务状态不参与淘汰。10,000 次插入的有界缓存检查通过。
- 终态连接关闭，并等待超过初始化快照超时确认 SSE 不再重开；没有任务绑定的轮询立即停止。`beforeunload` 不再把事件对象误当会话 ID。
- 只读/plan 任务跳过不需要的工作区文件快照，避免大批未提交文件拖延队列启动；允许写入的任务保留快照保护。快照改用 NUL Git 路径解析，中文、空格和字面箭头文件名正确保存/恢复。
- 交互细节见 [前端补充交付](FRONTEND_HARDENING_DELIVERY.md)。

### 第二轮验收证据

- 评测、验证、权限和摘要组合：42 项通过，`output/followup-hardening-checks.xml`。
- 最后发现的准确率/缓存/命令识别边界：49 项通过，34.20 秒，`output/hardening-acceptance.xml`。
- core 完成评估/验证/取消与相关路径：16 项通过、111 未选，`output/core-hardening-integration.xml`。
- 自动验证生命周期与缓存的实际取消、输入变化检查有独立用例；快照路径组 5 项通过，中文/空格执行真实文件往返，字面箭头用 NUL 输出解析检查（Windows 不允许 > 文件名），见 output/snapshot-path-checks.xml。
- `npm run test:optimization`、`test:transport`、`test:lifecycle`、实际本地 HTTP 的 `test:web`、`check:web` 均通过；CI 纳入 transport/lifecycle。
- 各组有重叠，不能求和为总覆盖率。未跑全量回归，未改变用户 API 凭证和模型配置，未提交或发布。

## 9. 第三轮剩余行为收尾

用户继续要求检查剩余项后，完成 G1–G4。本轮未调用真实模型；沿用第 5 节已执行样本，不将新增单元/浏览器结果视作模型准确率。

- **验证命令与检查关联**：抽出 `check_commands.py`，正确保留 Windows 解释器与路径反斜杠、空格和等号形式参数。同一 pytest/unittest 的冗余显示选项不再让修复后成功无法解除旧失败；测试路径/筛选不同仍独立。`test_selection.py` 使用语法树发现 src 布局、from-import、多行和别名引用，不会把注释/字符串当依赖；有界缓存和遍历避免反复全文件解析。
- **文件回退**：内置编辑器第一次实际修改前保留原镜像，补齐原先干净文件、已有用户改动、任务新建/删除/移动。新清单带镜像摘要，原子替换；重复捕获不覆盖最早镜像，冲突不覆盖用户后续编辑。任务仍活跃时拒绝恢复。文件数/大小/总量限制明确报告，镜像不可靠时拒绝编辑。范围和验证见 [文件回退交付](SNAPSHOT_COMPLETION_HARDENING.md)。
- **长时间线与浏览器容量**：240 条显示窗口按稳定工具 ID 保持展开节点；不变事件数组在 1000 次流刷新中重复序列化次数为 0。10000 条输入事件局部渲染约 46.6ms，实际只保留 239 个工具节点；1000 条消息的缓存保留最新完整消息。视图最多 24 项/120万字符，单项18万字符；超大单条内容不进入浏览器缓存，仍从服务端任务详情读取。配额回收只影响会话视图，认证与设置保留。
- **测试可重复运行**：产品 smoke 显式创建新任务后检查空态，已有真实历史不再造成假失败；没有删除用户历史来满足用例。

验收：命令解析/准确率45项、回退/验证/契约组合36项、快照及真实 worker18项、core相关10项通过。`test:scale`、`test:optimization`、`test:lifecycle`、实际 HTTP `test:web`、构建一致性与 diff 检查通过。分组有重叠，不累加。工作区保留未提交修改，未发布。
