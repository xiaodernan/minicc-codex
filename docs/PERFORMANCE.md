# minicc 性能与资源使用

> 本文件汇总本主线**有实测数据**的性能改进与资源治理决策。所有数字都来自可复跑的
> 命令或本机基准；没有复测的不写成"已完成"。配套的回归纪律见
> [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md)（评估正确性）、
> [SERVICE_PLANE_GATEWAY.md](SERVICE_PLANE_GATEWAY.md)（网关缓存治理）。

## 1. 导入时间（模块加载）

`minicc/llm/openai_provider.py` 曾在模块顶层 `from openai import`（openai 包拉出上百个
pydantic 模块）。`minicc.webserver` 此前 50–70s 完成导入；改为惰性 `_openai_sdk()` 后：

| 模块 | 改后实测 |
| --- | --- |
| `minicc.llm.openai_provider` | ~1.71s |
| `minicc.webserver` | **1.61s**（约 30×） |
| `minicc.agent` | 0.00s（命中 `sys.modules`） |

测试 `tests/test_webserver.py` 8 passed（4.69s）；`tests/test_openai_provider.py` 等
**103 passed**。门槛靠 `tests/test_plan_channel.py` 的 monkeypatch 契约保留（模块级
惰性代理类 `AsyncOpenAI`，`monkeypatch.setattr(provider_module, "AsyncOpenAI", factory)`
依然可用）。

## 2. 任务库按会话读取（SQLite）

`list_by_session` 此前 `SELECT task_id, payload FROM tasks ORDER BY created_at ASC`
**无 WHERE、全表拉回**，再逐行 `json.loads` 过滤。会话内每条消息的成本累加器
（`/cost`）都要付 O(全库行数) 的 JSON 反序列化。

改为：

```sql
SELECT task_id, payload FROM tasks
WHERE json_extract(payload, '$.session_id') = ?
ORDER BY created_at ASC
```

- JSON1（SQLite ≥3.9 内置）在 SQL 内完成比较；匹配行远少于总行数。
- 坏行会让 `json_extract` 以 `malformed JSON` 终止**整表**，故捕获
  `sqlite3.DatabaseError` 时回退到原"load-and-skip"语义，行为逐行等价。
- 本机 800 快照 / 40 会话临时库：老路径 ~58.3ms → 新路径 ~35.8ms（≈1.6×）。
- 测试：`tests/test_task_store.py` 10 passed；`test_session.py`、`test_trace.py`（取 12 条相关）、`test_workspaces.py` 合计 17 passed。

## 3. 影响分析图遍历（`minicc/impact.py`）

- 变更传播用 **BFS + 父指针**：每个受影响节点只入队一次，O(V+E)，避免了 O(V²) 的
  "对每个文件重新遍历其依赖"。
- `_JS_LEXER_RE`、`_CITABLE_EVIDENCE_MARKER`（M8-T835）：正则**编译一次**提升到模块
  常量，不再每次调用重编译；门 `tests/test_regex_hoisting_has_one_home.py` 钉住常量必须
  在 import 期编译。

## 4. 缓存层

### 4.1 网关 Redis 缓存（service plane）

`minicc-cloud-gateway` 的 `/api/cached/inspector/status` 与 `/api/cached/insights/summary`
用 Redis（`spring.cache.type: redis`，TTL 60s，`cache-names: gateway-routes`）做读缓存，
另有 `/api/cached/inspector/changes?workspace=<abs>`（String 直存，30s 上游预算）；
`CacheKeys.forService()` 是**一元化**键主人，fanout 消息把一份 invalidate 送给
**每个**绑定副本。实机 2026-11-13：TTL 复用命中（2199ms→74ms、changes 4.7s→64ms）。
`CacheKeys` 现在 split keys by shape：status/summary 定向驱逐、changes 只随 TTL 过期
（按 workspace 键，无法按服务定向驱逐，刻意取舍）。全 8 模块 `mvn -o test` reactor 全绿（离线隔离：
`test/resources/application.properties` 覆盖 broker 自动启动）。

### 4.2 Python 侧进程内缓存（M8-T853 新增 cache-topology 信号）

`minicc/redis_cache.py`：`REDIS_URL` 不可用/未装 redis 包时自动回退进程内
`OrderedDict` LRU（线程安全、上限可配），不产生部署依赖；测试
`tests/test_redis_cache.py` 钉住设/取/删/清、TTL 过期、命名空间隔离、线程安全、
后端异常不抛。**M8-T853 新增 `stats()`**：模组级共享的计数器分布在 `RedisCache.get`/`set`/`delete`/`clear` 五个关卡，返回 `{"gets":..,"hits":..,"misses":..,"sets":..,"sets_shared":..,"sets_local":..,"deletes":..,"clears":..,"live_backend":bool,"local_units":int}`；这一负载通过 `/api/metrics` 的 `redis_cache` 字段暴露，操作员可从此分辨「共享命中」与「本地降级命中」两种状态——此前 cache 的**唯一可靠对外信号是 `set()` 的返回值**。


## 5. 前端体积与对比度

- 产物内容寻址：`npm run build:web` 输出 `web/assets/<hash>.<ext>`，对
  **contents** 哈希，`check:web` 保证产物与源同步、`asset-manifest` 不谎报。
- `web/app.js` ~310KB、`web/game.js` ~110KB（按 2026-11-12 构建实测）；arcade
  （钓鱼/游戏场）**按需懒加载**，主工作台不下载。
- 文本对比度门：`--quiet` 对 `--sidebar` 全主题 ≥ 4.5（浅各 `#475569` 对
  `#f1f5f9` ≈ 6.92，深 `#94a3b8` 对 `#0f172a` ≈ 6.96）；`frontend_optimization_smoke`
  全绿（reducer, fast startup, lazy arcade, stale responses, tabs, modal keyboard,
  tree keyboard, preview races）。
- 移动（≤640px）不再把 assistant 气泡钉 75%：M8-T834 交付全宽，移动端结果总结可读
  宽度 ≥300px 契约恢复。

## 6. 度量纪律

1. 先量后改：每项优化前有可复跑的对照（如 `old_list` vs `list_by_session` 的临时库 A/B）。
2. 门槛不能弱于原先的红：
   `tests/test_doc_readings.py::test_the_pinned_reading_is_the_count_this_tree_collects`
   钉住 BENCHMARK_EVALUATION.md 的计数；stale 31→ **35 passed**。
3. 归档的测量数字用了不外传：结果写在 `docs/BENCHMARK_EVALUATION.md` 与
   `docs/ROADMAP_TO_PRODUCT.md` 的带日期段落里（本文件只收进阶纪律与可复跑条目）。
4. `minicc web` 的 workload 不为压测而压测：性能测试都是真实路径（真实 SQLite、真实
   Pytest 收集数、真实 Playwright），不是 base-specific 的"数字花活"。

## 7. 未做的（给后人的工作单）

- ~~网关 `/api/cached/*` 曾是派生模拟（hardcoded Map.of 响应）~~ — 已改写为真实上游探活 + 真实缓存：`/api/cached/inspector/status`、`/api/cached/insights/summary`（lb:// 上游探活 + Redis 60s），`/api/cached/inspector/changes?workspace=<abs>`（inspector 的 Python 变更清单，String 直存）。M8-T861 还修掉一处无人发现的生产级缺陷：缓存的 `Mono<ResponseEntity<Map>>` 里 `ResponseEntity` 不可序列化，真 Redis 上每次 cache 写都会炸（全靠 `spring.cache.type=none` 的测试掩盖）。剩余：把 eviction bus 扩成按服务驱逐全部键（需 Redis 模式删除）或逐服务发布。
- `minicc/task_store.py` 的 `search()` 在 `task_search` 表为空时行为与索引一致（没测
  过 FTS 命中率）；`task_search_fts` 已由 upsert 维持。
- FFI 语义：SQLite JSON1 在 ≥3.9 可用；macOS/Linux 发行版的可移植性已依赖 Python
  3.11 的 bundled SQLite（本机 3.39.4）。如果有人用到无 JSON1 的 SQLite 构建，
  `json_extract` 会报 `no such function` —— 需要给该环境加回退臂（同 malformed-JSON 的
  DatabaseError 捕获点）。
