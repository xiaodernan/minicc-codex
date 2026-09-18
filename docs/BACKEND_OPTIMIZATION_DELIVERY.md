# 后端任务运行时优化交付记录

日期：2026-09-18。覆盖实现计划 B1–B5；基于中断任务的现有工作区继续实现，未覆盖或回退已有改动。

## 已交付行为

- `task_contract.py` 为线程和进程执行器提供同一版本化请求及结果契约，完整保留权限模式、联网/写入开关、图片附件、推理强度、会话恢复标记和验证结果。任务事件继续使用 `agent/protocol.py` 的可重放事件封装。
- `task_store.py` 使用原子执行租约，只有一个 owner 可以取得任务。worker 独立续租，写入快照时在同一 SQLite 事务中校验租约，失效旧 worker 无法覆盖新执行者结果。配置或请求解析失败也会释放租约。
- 主进程恢复前先检查原始租约，存活的独立 worker 保持 running 并重连；关闭 web 服务时保留其执行。独立 worker 保留任务原始创建时间和附加元数据。
- `task_execution.py` 使用绝对流偏移镜像增量，超过 16,000 字符仍更新；错过整个保留窗口会重置显示快照；重放事件去重。上下文、压缩事件与累计 token 计数在进程模式同步，避免最后一次累计 usage 重复相加。
- `task_persistence.py` 合并同一任务的待保存状态。模型 delta 回调仅更新内存和排队，不做 SQLite 写入。终态同步落盘，序号防止旧 running 快照覆盖新终态。检查点 digest 只在文件/命令证据变化时重算；所有 SQLite 连接显式关闭。
- 历史搜索新增只包含脱敏可见文本的 `task_search` 投影，旧库启动时迁移，支持 Unicode casefold。可用时启用 FTS5 trigram 索引，短查询和不支持 FTS5 的 SQLite 使用投影回退；不扫描大型事件 JSON。工作区过滤、更新、裁剪同步生效。

## 定向验收

未运行全量回归。

```powershell
.venv/Scripts/python.exe -m pytest tests/test_task_worker.py tests/test_task_durability.py tests/test_history_search.py -q
.venv/Scripts/python.exe -m pytest tests/test_core.py -k 'task_manager or task_store or interrupted_readonly or task_snapshot' -q
```

- worker/持久化分组 11 项与搜索分组 7 项通过，含真实子进程执行与取消、进程提交到最终 SQLite 落盘。
- 核心任务管理分组 21 项通过，含会话队列、并行会话、取消、检查点恢复、附件恢复和持久历史。
- 新增定向契约覆盖原子租约竞争及旧 owner 写入隔离、超过窗口后的流恢复、重复镜像、累计 usage、请求/结果一致性、活 worker 重连、慢 SQLite 不阻塞流回调、终态覆盖顺序、旧库 Unicode 搜索迁移与索引清理。
- 中断后补验：worker、持久化、自动恢复分组共 13 项通过；另新增真实子进程重启集成用例，先输出 16,050 字符，在模型调用中关闭宿主再启动新宿主，确认原 worker PID / 租约不变、没有新建重复任务、后续文本持续更新且最终落盘完成。该新增用例单独通过。
- fake provider 改为引用实际完成评估证据编号，避免因新验收契约而产生虚假测试失败。测试结果证明运行时协议，不作为真实模型准确率。

## 运行边界

SQLite 仍是本地单机持久化；不是分布式队列。线程执行器在 web 进程退出后无法继续运行；独立进程模式可以继续，租约失效后的恢复仍依赖原有安全检查点规则，不承诺恢复到模型调用内部的精确位置。

文件职责：`task_manager.py` 调度与会话队列；`task_contract.py` 传输契约；`task_execution.py` worker 镜像与重连；`task_persistence.py` 合并保存；`task_store.py` 数据库、租约、搜索；`task_worker.py` 独立执行入口。
