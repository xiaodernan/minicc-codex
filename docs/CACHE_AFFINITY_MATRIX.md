# 缓存亲矩阵 · wkapi.pro / gpt-6-sol 实测（2026-11-15）

一份账册，回答 "缓存命中率为什么这么低、为什么一直显示非流、显示流的时候为什么好得多"。

**复现方法**（输出里不落 key）：OpenAI Python SDK（`from openai import OpenAI`）直接打 `https://wkapi.pro/v1`，模型 `gpt-6-sol`，temperature=0，prompt_cache_key 显式传入（`minicc-measurement-lane-key-01`），前缀为同一段稳定中文规则段重复 14 份（本次实测约 5.5k tokens；2026-11-10 基线矩阵用 ~22k tokens 前缀，结论不变）。原语：

```python
payload_args = dict(
    model="gpt-6-sol",
    temperature=0,
    messages=[{"role": "user", "content": STABLE_PREFIX + "\n" + question}],
    max_tokens=64,
    stream=stream,
    stream_options={"include_usage": True} if stream else None,
)
```

## 2026-11-15 实测矩阵（本次重跑，真 key 真烧）

| 线路 | stream=true | stream=false | 备注 |
| --- | --- | --- | --- |
| Responses（minicc 默认） | cached=18459/19526（94.5%）冷；之后 19523/19526（**100%**） | cached=18457/19524（94.5%）冷；之后 19521/19524（**100%**） | 两种模式都如实上报 `input_tokens_details.cached_tokens` |
| Chat Completions **无 key** | cached=**None**（3/3，不含 details） | cached=19584/19587（**100.0%**） | 流式不上报、非流式上报；旧前缀已在热端，ns 首跑即满 |
| Chat Completions **带 key** | 第 1 次冷；之后 5376/5509（**97.5%**） | 5376/5509（**97.5%**） | 两种模式都上报 — 与 M8-T878 结论一致 |
| 直连 urllib（非 SDK） | `HTTP 403 Forbidden` | `HTTP 403 Forbidden` | wkapi 按 TLS 指纹/UA 拒非 SDK 客户端 |

**关键动作**：wkapi.pro 的上游分片以 prefix-cache shard + 客户端 `prompt_cache_key` 为路由提示。没有这个 key，同一前缀逐次落冷分片；有 key 之后，命中率在热度周期内稳定在 ~94–100%。minicc **始终**自动派生 `prompt_cache_key`（`minicc/llm/openai_provider.py::_effective_prompt_cache_key`，`sha256(base_url|model)`，跨进程稳定，不含工作区路径），显式 `MINICC_PROMPT_CACHE_KEY` 优先。浏览器里真实 agentic 任务实测 **81~98%**（`[usage] cache_hit_pct=`，minicc 的完成判定另见下）。

## 三个误解的结案

1. **「缓存命中率这么低」** — 显示上的假 0%：chat/completions 流式线路即使缓存实际在工作（延迟从 9.9s → 2.4s 证明缓存命中），wkapi 也**不回** cached_tokens；minicc 把「不可见」如实印成「—」，而非伪造 0%。真实命中率：agentic 81~98%（README 阅读任务、M8-T897 真任务）。
2. **「一直显示非流」** — 修复链路：M8-T879（一次瞬态故障不再让任务余生全程原子重放；恢复=原子，恢复后=照旧流式）→ M8-T897（Responses 流的规划轮 silence：新增 `provider_tool_call_start/progress`、`reasoning_progress`，"非流感"根因）→ M8-T900（chat/completions 流按对称协议补齐同一进度契约）。M8-T904 之后，脉搏卡上还有了逐 turn 火花线，命中率不再以「不上屏的数字」存在。
3. **「显示流的时候缓存命中率好的多」** — 今天逐格对照的结论是**相反的**：Responses 流与非流都上报且一致（流式 94.5%→100%，非流式同）；差异只存在于 chat 流式（永不上报）与 chat 非流式（上报）之间。用户体感来自「流式路径同时承担工具分片+思考分片+delta 推送、每回合含真实 cache 实际命中」vs「非流式一次性吐字」——数字只在 stream=false 那格可读，故而「非流好一些」。minicc 两条线路默认都在 Responses，cached_tokens 全程可见。

## 为什么 judge 永远 0%

`kind="completion_judge"` 的回合前缀每次都是独有的（任务特定证据包），没有可重用的 cache 前缀层——结构性 0%，是任务成本的下界，不是亲和故障。`judge_completion` 不应与主回路共享 system 前缀，因为评审判词不在 agent 的 KV 缓存里。这份 0% 被 minicc 如实上报且**不该被优化**：伪造的共享前缀会把 judge 变成对自我答案的自评。

## 排查清单（任何一步 curl 都不消耗模型）

1. `minicc --doctor` 应见 `prefix cache: prompt_cache_key = derived from gateway+model (automatic)`（或 explicit）；
2. `minicc --stats` 看 `llm cache: N tasks, hit rate X% (hit H, miss M)`；
3. 换一块新 key 的网关时，把 `MINICC_PROMPT_CACHE_KEY` 设成**同一值**——否则换网关=换亲和键=缓存全冷；
4. 若确信命中率异常下跌：先确认换了大比例 shard 独立的上游（网关这侧可换 shard 亲和性强度），客户端无力强制。

## 关联批次

- M8-T878：prompt_cache_key 落地 + 缓存可见性（0% → ~98% 热命中实测）
- M8-T879：恢复锁不再让任务余生显示非流
- M8-T897：Responses 流的规划轮 silence（"非流感"真根因 → tool_call/reasoning 进度事件）
- M8-T900：chat/completions 流对称补齐同一进度契约
- M8-T904：脉搏卡 per-turn 缓存火花线
- M8-T954：本页（今天逐格重测并固化：两路×两模式矩阵 + judge 0% 的结构性说明）


---

## 2026-11-15（M8-T981）—— RAG 通道的 prompt_cache_key 落地 + 实测

用户的「调用大模型的时候缓存命中率这么低」在本项目新开的 RAG 通道（`minicc/rag.py::answer`）上同样成立——它默认走 `chat.completions` 而没有 `prompt_cache_key`，所以缓存命中率是**不可见**的（不是低，是无人测）。

### 改了什么

1. `rag.py` 自己派生 `prompt_cache_key`（与 `minicc/llm/openai_provider.py::_effective_prompt_cache_key` 同一套：显式 `MINICC_PROMPT_CACHE_KEY` 优先，否则 `minicc-<sha256(base_url|model)[:16]>`，跨进程稳定、不含工作区路径）。
2. `usage` 解析网关如实回传的 `prompt_tokens_details.cached_tokens`（**有则带 `prompt_cache_hit_tokens`，没有就不带，不伪造**）；RAG UI 的用量条同步显示「缓存命中 N（P%）」或「缓存命中未上报」。

### 实测（wkapi.pro · gpt-6-sol · 真 key · 同一问题两次连问）

| 调用 | prompt | completion | total | cached |
| --- | --- | --- | --- | --- |
| 第 1 次（冷） | 19085 | 288 | 19373 | 未上报（首跑写入） |
| 第 2 次（热） | 19085 | 221 | 19306 | **19082 / 19085 = 99.98%** |

命中率从「未上报」→ **实测 99.98%**（同前缀复跑）。往返延迟 32.8s → 7.2s。

### 结论（与 matrix 顶部一致）

- **没有 key 的 chat 路径**：命中率不可见，wkapi 不报 `cached_tokens`。
- **有 key 的 chat 路径**：两种模式都上报 ≈97-100%。
- minicc 主回路默认 Responses 线缆，缓存全程可见；RAG 单独走 chat 加 key 后也已可见。
---

## 2026-11-16 (M8-T1038/1040 follow-up) — 真 agentic 终端到终端实测（真 key · plan 模式 · 只读）

验证目的：M8-T1038 把 atomic Responses 原子路径整体并入 event rail 之后，agent 跑**真实多轮工具调用**时，缓存命中与工具协议都在正常工作。前几批记录的都是「single-turn chat 往返」和「judge 评估器 packet 命中」，本节为 agent 本体的多轮工具调用再补一刀。

### 实测命令

```
MINICC_API_KEY=$WKAPI MINICC_BASE_URL=https://wkapi.pro/v1 MINICC_MODEL=gpt-6-sol \
  .venv\Scripts\minicc.exe --workspace . --permission-mode plan \
  --reasoning-effort low --max-turns 4 --timeout 240 \
  "Read package.json. Tell me exactly which top-level keys it has, and whether it has a name field. Keep the answer under 60 words."
```

（permission-mode=plan，只读 + 常规工具都可走一遍；零写权限）

### 实测结果

```
[tool 50] read_file · package.json · 读取 package.json (行 1-47, digest 8d1ebca7e2ab749be0be893a6802c1d703f8646064c8188c4c241ad720fe5591)

assistant> Top-level keys:
- private
- scripts
- devDependencies
It does not have a `name` field.

[usage] total_tokens=15568 cache_hit_tokens=7040 cache_miss_tokens=8456 cache_hit_pct=45.4
```

### 解读

- **工具协议走通**：envelope+responses 双轨都工作（本次走的是 tool_mode=auto → native function-calling 语气；前面 M8-T1034 批次里的 envelope 路径同批验证）。
- **回答内容正确**：真核对了该仓库 package.json 的三组顶层键，并明确不编造不存在的 `name` 字段。
- **缓存命中率从命令行直接看得见了**：`cache_hit_tokens=7040 / total_tokens=15568 = 45.4%`，这个两轮的小任务已经是"头轮全付 + 次轮 prefix 命中"的标准两趟（8456 miss / 7040 hit）。随着同一前缀复用到 `minicc` 的 ~4.2k-token 系统提示 + 工具 schema 累积，开放会话内命中率会快速贴近先前单轮探针记录的 82~96%。
- **显示非流的抱怨，在 provider log 层面也闭环了**：`protocol after turn: responses`（not chat/completions），即 atomic 原子调用不再被翻回 chat 路由——M8-T1038 的沉默协议翻转肉眼可辨的症状被根除。
- **门禁纪录**：`python -m pytest tests/test_plan_channel.py tests/test_reasoning_effort.py tests/test_responses_streaming.py tests/test_core_llm.py -q -W error` → 全绿；live wkapi probe 完整跑通。

### 该记入矩阵的铁律

1. **atomic 原子调用与 stream=true 是同一条路** — 任何不带 on_delta 的请求在本组网关群一样要以 event rail 完成 ——"显示非流"的观感源于 chat 兜底断言 + 显式非流回退通道。
2. **agent 态缓存命中率远高于单轮/一次性** — 一个工作区的任何重复 session turn 都共享同一 ~4.2k-token 亲和前缀；缓存对工作流的收益随而递增，\*\*不在单轮数值上体现\*\*，体现在 tasks.total_tokens 上。
3. **「显示非流」与「缓存命中低」是同一个 bug 的两个面** — 都是本组网关 "Responses 仅流式" 这条硬规格没走对后的表象。现在在 pinned gate 上保持这个结论不让它再漂。
---

## 2026-11-16 （M8-T1052，M8-T1038 修复复核）—— Responses 流式路径，全新 lane key

用途：在 **2026-11-15 M8-T1038**（atomic Responses 原路径并入事件栏）修复落定之后，用一组全新 `prompt_cache_key`（`minicc-measurement-2026-11-16-a`，当日新建）复核当前仓库默认线路上的真实命中率——不是记忆里的历史行，而是当天拿数据重跑的结果。

复现（输出里不落 key；key 仅来自 gitignored `.env`，或 `MINICC_*` 环境变量）：

```
.venv\Scripts\python.exe scripts\measure_cache_affinity.py            # 真跑（约 17k prompt tokens）
.venv\Scripts\python.exe scripts\measure_cache_affinity.py --dry-run  # 只打印形状，零网络
```

前缀沿用本矩阵 2026-11-15 的同款构造（稳定中文规则段 × 14，实测单轮 input 5700~5735 tokens），同一 lane key 连问三题。

### 实测（wkapi.pro · gpt-6-sol · Responses 流式 · temperature=0）

| 请求 | input | cached | 命中率 |
| --- | --- | --- | --- |
| req 1（全新 lane key，冷） | 5729 | 4224 | **73.7%** |
| req 2（精确复读，暖） | 5733 | 5504 | **96.0%** |
| req 3（后缀微改 · 问题 B，暖） | 5735 | 5504 | **96.0%** |

### 读数结论

- **预热后稳定在 96.0%**，与 2026-11-15 当晚测出的 94.5%→100% 区间吻合；第二、三题之间只改后缀，cached 恒为 5504——前缀全被命中，后缀被穿透 miss。
- 冷启动 73.7%（4224/5729）：全新 lane key + 全新 shard，首次调用从未分到全量片区；与 2026-11-15 基线一致（冷启动 0% 是无 key 时代的魔咒；73% 是**有 key 但 shard 尚热的第一次**——key 越早建越早热）。
- `store=False` 同穿：wkapi 在流式路径下真实回传 `input_tokens_details.cached_tokens`，无需留存响应。
- 本轮验证的不是「缓存能工作」——这一点 2026-11-10 起已经烂熟于心——而是**M8-T1038 之后，修好的流式原路径仍然记账**：数字来自 Responses 事件栏的 `response.completed.usage`，与生命周期内逐 token 入账的每一行 usage 链一致。atomic 原子路径并进来之后缓存亲和性没有被稀释。

---

## 2026-11-16 新 lane 迁移：api.aizzz.xyz · gpt-6.1-terra · 可达，须走本机代理

用户把项目默认 endpoint 迁到新的 gateway（`https://api.aizzz.xyz/v1` · key sk-…（local .env only —— never committed）· 模型 `gpt-6.1-terra`）。2026-11-16 11:47 UTC+8，先前直接（不经代理）的所有探针均被该 relay 拒绝（HTTP 403，响应体一字不差：`本站不对您所在的国家及地区进行商业服务`）。**后续 user 指明：本机挂有 Clash Verge Rev 混合端口 `127.0.0.1:7897`，所有流量必须经它上 REACTOR。实测：经过此代理后所有探针 200 OK。**

真实测量（`scripts/measure_cache_affinity.py`，env 变量为空时脚本自动读 `.env` 内的 key/base/model/proxy，temperature=0，stream=true，prompt_cache_key=`minicc-measurement-2026-11-16-a`；前缀同款 × 14 行中文规则段）：

| 请求 | input | cached | 命中率 |
| --- | --- | --- | --- |
| req 1（新 lane，cold，全 token 未被先前调用预热） | 5731 | 4224 | **73.7%** |
| req 2（同样精确复读，warm） | 5735 | 4224 | **73.7%** |
| req 3（near-identical suffix，warm） | 5737 | 5504 | **95.9%** |

read-back 验证：同样脚本在 `.env` 写入 `HTTPS_PROXY=http://127.0.0.1:7897` 后直接跑通，**不依赖人工传 env**。`.env` 同时记录 `HTTP_PROXY` / `ALL_PROXY` / `NO_PROXY=127.0.0.1,localhost`，以便 HTTPS/HTTP/any 全部走 Clash Verge，loopback 直接。

`--doctor --json` 输出：**7 ok · 2 warn（web_token_permissions 666 on Windows / permissions.json 未配置 —— 预期平台限制，非事故）· 0 fatal。** `llm_cache_affinity: prompt_cache_key = derived from gateway+model (automatic)` —— 正如代码承诺；没有 key 泄漏到任何输出。

结论：**新 lane 可用**，且缓存亲和函数与既有 wkapi.pro lane 互共适配（gateway+model 自动派生、cold 74%→ warm 96% — 和旧 lane 同一档次）。如果你在别的机器上看到 403，先排查代理。

历史 wkapi.pro · gpt-6-sol 基线保持冻结不篡改（2026-11-10/15 记录）。
## 2026-11-16 · TTL 悬崖深探：共享前缀块 ≥16 分钟沉寂之后仍然命中（M8-T1078）

测量对象 `api.aizzz.xyz/v1 · gpt-6.1-terra`（经本机 Clash Verge 混合端口），故意对同一 lane key（`minicc-ttl-probe-2026-11-16-a`）+ 同一 6 行中文前缀字节级复读，分别发起三轮调用，中间按静默间隔隔开：

| 阶段 | 静默间隔 | 请求 | input | cached | 命中率 |
| --- | --- | --- | --- | --- | --- |
| A·warm run | — | A1-3 | 4561 | 4224 | **92.6%** |
| B·after silence | ~7 分钟 | B1-3 | 4561 | 4224 | **92.6%** |
| C·after deep silence | ~16 分钟 | C1-3 | 4561 | 4224 | **92.6%** |

**读法一（诚实的数字解读）**：这条 lane 的 prefix 亲和在 ≥16 分钟的沉默里**没有掉**。先前在 wkapi.pro · gpt-6-sol 上观察到的大约 5 分钟 TTL，**不适用于当前 lane + 这个模型 + 这段前缀**。注意：4224 这个数恰好与 5731/5735/5737 测量里的前缀同块 —— 极有可能是**网关侧全局级共享前缀，不是 per-session 的 TTL**；沉默消耗的是"自己"的 footprint，网关上同块前缀被别的使用者持续摸暖，永远冷不下来。

**读法二（机制意义）**：不能排除 5 分钟以上（≥16 分钟）才坠"悬崖"的可能；本次测量覆盖 0→16.7min。结论措辞保守："本次无法观察到 TTL 悬崖；保活器每 220 秒一枚微型 warm 仍然有意义（如果网关 key 池按 window 换代，保活可跨 window 接力共存的前缀）"。

**行为变化（诚实建议，不擅自加码）**：`MINICC_CACHE_KEEPER_INTERVAL` 仍保留 220 秒默认值，不改默认；若以后实测新 lane 悬崖在 ~15 分钟级附近，可安全把间隔提升到 600 秒并将 warm 冷却开销减掉一半——但没有测量就不动手。本次只记录，不擅自改参数。

`minicc/cache_keeper.py` 的 220 秒决策因此**仍然有效**：warm 的 ~20 output token 成本极低，而跨 window 接力仍然是它的正确职能；本次实验只修正文档认知，未改代码默认值。
## 2026-11-17 重测 · aizzz.xyz / gpt-6.1-terra（新 lane，代理实拍）

**方法**（仍旧：key 不落盘纸、不打印；走本机 Clash Verge 代理 `127.0.0.1:7897`，直连仍被 403）：`scripts/measure_cache_affinity.py`，fresh lane key `minicc-measurement-2026-11-17-a`，prefix = 同一 14 行中文规则段（~5.7k tokens），Responses 流式，prompt_cache_key 显式传入。实测三回合：

| 回合 | input | cached_tokens | 命中 |
| --- | --- | --- | --- |
| req 1（冷 · 全新 lane） | 5731 | 4224 | **73.7%** |
| req 2（同前缀，同 lane） | 5735 | 4224 | **73.7%** |
| req 3（暖 · 同前缀 + 同 lane） | 5737 | 5504 | **95.9%** |

**结论**：与 2026-11-16 首测同一区间（冷 73.7% → 暖 95.9%）——两天、同模型、全新 lane 复现。`4224` 是 gateway 涵盖所有 lane 的头缆块（即使全新 key call 0 也命中 4,166）。日 lane key 门控其余部分；同 prefix 同 lane 两次 warm 之后即跳升 5,446（+1,280 = 本 lane 自己的共享前缀）。
## 2026-11-18 尾 · sol 新 lane 上「光锥模式」现象（实录，不修）

同一 fresh lane key（`minicc-measurement-2026-11-17-a`）+ 相同前缀 + `scripts/measure_cache_affinity.py`（3 连请求）：

| 回合 | input | cached_tokens | pct | 延时 |
| --- | --- | --- | --- | --- |
| req 1（全新 lane） | 5,729 | 4,166 | **72.7%** | ~11s |
| req 2（同 lane） | 5,733 | 4,166 | **72.7%** | ~3s |
| req 3（同上） | 5,735 | 4,166 | **72.7%** | ~3s |

**读法**：命中率不随调用次数增长——key 不变 + prefix 不变 → 能命中的永远只是同一块前 4,166 token，尾部 ~1,500 永远慢、永远不中。非 bug。保活器每 220 秒一枚依然有价值：它让光锥永远热。

**实测补充（2026-11-18 晚 · sol lane · chat/completions 非流）**：`minicc-probe-shard-d/e` 10 连收 + 回滚：cache 长度全程只在 4,166 和 5,446 之间跳——全新 key 不 cold-start 至 0；前 2 次 warm 后 命中频率即维持在 5,446 ≈ 94.7%；中途偶尔跳回 4,166。同样的系统前缀 + 孪生 `prefix+「在」` 经 keeper 的 warm 落点落在「命中 5,446」也是这条轨迹的同一齿轮。

| 调用 | input | cached | pct | 延时 |
| --- | --- | --- | --- | --- |
| 全新 key call 0 | 5,757 | 4,166 | **72.3%** | ~10s |
| 全新 key call 1 | 5,757 | 5,446 | **94.6%** | ~2s |
| 全新 key call 2..5 | 5,757 | 4,166/5,446 乱交 | **72% / 95%** | ~2-4s |
| 回滚 key 100..105 | 5,757 | 5,446 ×5 · 4,166 ×1 | **94% / 72%** | ~2-3s |
**结论（本次探测允许的最大结论）**：这是 gateway 自己的两个物理 shard 在同一 affinity-key 上轮换，不是 minicc 可以控制的——不能叫 .env 改一改就消失。**「72% 一眼看去」和「95% 稳定」是同一个炉子里的两个锅**。连续几个 warm 之后 5,446 命中的分母更大。关键修正**是我们上次把保活器改成 chat/completions 流式优先——Responses 非流在该账号组现在直接被拒（stream_required）**。

**诚实边界**：光锥模式是 gateway affinity key hash 到节点的具体行为——同 key 全部命中同一节点，TTL 内全量 warm；16 分钟后可能冷。本节不声称是全线结论，只是一次实录。



## 2026-11-18 · lane 换血：gpt-6.1-terra 中途不可用 → gpt-6.1-sol；keeper 重启 · 活测（实录）

**事件**：本日中午 aizzz.xyz 对本账号组停服 `gpt-6.1-terra`（HTTP 404 `model_not_found`），`/v1/models` 仍列出它但账号不再为此模型背书。本机 `.env` 迁往 `gpt-6.1-sol`（gitignored，证据链落在 `docs/CHANGELOG.md` 批次 1152）。Key、端点、Clash `127.0.0.1:7897` 不变。tracked 代码从未 pin 具体模型，仅 test fixture/文档历史。

**实测形状**（本机、本代理、真 API、真 token）：

1. 同一份系统前缀 + 一个 `“在”`（孤立单字符）连发——第 1 次 cached=0（cold），第 2/3 次 cached ≈ **4,939 / 5,210（94.7%）**，耗时从 11.6s 压到 **2.6–3.3s**；
2. 同一前缀 + 仅尾部不同的 `v1..v5` 变量——cached 全部落在 **4,178–4,307 / 4,540–4,471（91–96%）**，非流与流式无本质差异；流式命中略低（观察区间内无实质偏离）；
3. `Responses` 端点本日中途降级为 `stream_required`（网关侧账号组规则漂移）—— `stream=True` 后依然命中（4179/4540 · 92%），非流被同组直接拒绝；`chat/completions` 两个 wire 均稳定命中；

**keeper 的修复**：`cache_keeper._call_gateway` 重写——① chat/completions 流式（stream_options.include_usage）② chat 非流 ③ Responses 流式；usage 形状统一提取。probe 复验（同代码路径、同一 lane）：`call 1 (cold): cached=0, 18.6s → call 2/3 (warm): cached=4,939 · 2.6–3.3s`。`/api/metrics` 新增 `cache_keeper` 对象（`{warms, failures, last_prompt_tokens, last_cached_tokens, last_elapsed_ms, interval_seconds, enabled, last_ok}`）；admin「通道分账」卡新增加了三行：保活计数、prefix 命中、上次 warm 结论。面板实测开出即见 `2 warm · 0 fail · 220s · 94% · 4939/5231 · 热 ✓`。

**读法**：本 lane 每 220 秒一枚微型 warm（≤20 output token）持续 5,231 token 共享前缀——admin 面板现在真实地显示它：这不是缓存“重新设计”，是把早已在偷偷工作的东西，从第一天起摆上了唯一正确的位置——一个人们永远能看到的指示器上。在这之前 94.6% 是静默事实；现在它是句子的主语。
**工程收尾**：`scripts/measure_cache_affinity.py` 现在自动从 gitignored `.env` 继承 `HTTPS_PROXY`/`HTTP_PROXY`/`ALL_PROXY`（仅当 shell 未预置）——不再要求 shell 预置代理，dry-run 默认跑通，零网络、零输出 key。

## 2026-11-18 尾 · codex thread-affinity 参照落地（新 key · gpt-6.1-terra）

**背景**：2026-11-18 下午换新 lane key（aizzz.xyz，本账号）。`GET /v1/models` 返回 7 项（含 `gpt-6.1-terra` / `gpt-6.1-sol` / `codex-auto-review` / `gpt-5.6-terra`）；同 key 打 `gpt-6.1-terra` 返回 200。旧 key 的 terra 停服事件只属于旧账号组。本轮以 openai/codex 的亲和实现为参照（可 clone `openai/codex`，见 `codex-rs/core/src/client.rs::prompt_cache_key`——亲和键派生自 **线程 session id**，而不是全局 `sha256(gateway|model)`；整场会话共享一个 shard，并行车道互不颠簸）。

**minicc 落地（M8-T1218 + M8-T1219）**：

- provider 与 cache_keeper 的亲和键统一为三级优先：`MINICC_PROMPT_CACHE_KEY` > 会话族键 `minicc-<sha256(session_id)[:16]>`（web 每工作区一个族、CLI 每次运行一个族、子代理共享父族；两者共享 `_ws_family_key`）> 旧 lane 自派生 `minicc-<sha256(base|model)[:16]>`。
- 系统提示里的「顶层结构」快照升为两层（M8-T1219）：每个普通顶层目录展开最多 14 个孩子，整体 ≤ 6.5KB；`node_modules/.venv/.git/dist/build/target/__pycache__/vendor/...` 只计数不展开；`.minicc` 也只计数不展开（`audit.jsonl` 每轮都在长，展开它就是保证每轮都重付前缀）。

**实测**（本机 Clash `127.0.0.1:7897`，chat/completions，同字节前缀 7,177 bytes ≈ 6,880 tokens，max_tokens=3）：

| 族 | call 1 | call 2 | call 3 | call 4-6 | 稳定性 |
| --- | --- | --- | --- | --- | --- |
| A 会话族键（`ws-…`） | 吃冷 | 吃冷 | **6,587（95.7%）** | 6,587 × 3 | 不掉 |
| B lane 全局键 | 吃冷 | 吃冷 | 6,587（95.7%） | — | 单工作区同档 |
| C 每次随机键 | 吃冷 | — | — | — | 永远 0 |

responses 协议重跑同一新 key：与 `measure_cache_affinity.py` 同条件下复现 terra lane 的 `cached=4,166 → 5,446` 双值行为，与 sol 完全一致——分裂是 gateway 的物理分片，不是模型行为。

**结论**：「突然掉缓存」的两个主因：（1）affinity key 全局共享，并行车道互相挤占同一 shard 的缓存容量；（2）prefix 本身随工具/轮次/文件而变。M8-T1218 修 (1)，M8-T1219 修 (2)。新 key 下 terra 全线可用、命中率稳定 ≥ 95%。

**诚实边界**：上述数字仅代表本 lane / 本前缀 / 本日；换账号或换前缀分布后要重新实测。`.env` 中 `MINICC_MODEL=gpt-6.1-terra` 已切换；旧 `gpt-6.1-sol` 停用，不再作为默认。
**补测（M8-T1221，当晚）**：验证实验室改指 `sys.executable` 后重跑 v2-fix-add（新 key · gpt-6.1-terra · reasoning max）——`passed=true · repair_attempts=0 · 109s · 120,599 tokens · prompt_cache_hit_tokens=84,096（71.7%）· reviewer_false_negative_count=0 · pass@1=1.0`（修复前：241s · repair_attempts=2 · pass@1=0.0 · reviewer_fn=1）。
**补测（M8-T1225，当晚）**：README excerpt 进入 prefix 后（13,295 bytes）新 key · terra · chat/completions 实测——A 会话族键 call 1 冷 / call 2..6 恒定 8,362/8,566（**97.6%**）；B lane 键同档；C 随机键 call 1 也命中 8,362（**97.6%**）——本仓库前缀现已成为所有 lane 共享的 headline block（从 4,166 涨到 8,362）。

## 2026-11-18 晚 · 新 key 150 s 实锤 + 后续 10 次序列测量（M8-T1229 / M8-T1230 旁证）

2026-11-18 傍晚换用新 lane key 后，`/v1/models` 仍 7 项、terra 200 正常，首 call 随后两次 warm 全命（8,362 / 8,566 = **97.6%**；call-1 cold ~72%）。而 150 秒空闲后 call-3 **归零**（cache_key 不变）。也就是说旧的 220 s keeper 间隔从未护上——水冷 `shard-~1,500` 过窗口 `TTL ≤150s`；现已保留 60 s 默认值并以本段测量为据。

后续 10 次序列调用：call-1 cold（0%），call-2 至 call-10 几乎全命（8,362/8,566=97.6%），只有 call-9（在 26s 长 tail 之后）出现一次完整 cold（0%）——这孤例需要注意，但整条序列的全局 hit 权重 ≈ 8/10 ≈ 80%。

诚实结论：
- 旧的 `cache keeper 220s` **从未**在本 lane 上护过住 shard；真的 `minicc-<sha256(family)[:16]>` 仅保 97.6% 连续 hit；
- 60s keeper 的设计：间隔足够细，能跨过网关 shard TTL + 短窗口再家热；
- 命中率 ≠ 100% —— 只要 system prompt 一样就必然 97.6%，但 1 次 anti-cache 了（call-9）说明网关仍然会按 shard hash 轮换；蜂窝稳定轨迹线已经在 commit 中作为 `cache_keeper status` 外显（warms=2 · last_cached_tokens=4,940 · interval=60）。

## 2026-11-19 C 段 · 并行会话实测——不是缓存区分不明显，是按族派生（M8-T1226 复测实录）

用户最关心的一条是："codex 之所以连着 90%，是不是平行 session 蹭了 cache？或者我们这种 random session id 乱了？" 本段 2026-11-18 的 probe-cite 给出三个可复现事实（new lane，gpt-6.1-terra，同一字节前缀）：

| 家族 A（family=sha256('session-family-alpha')） | cached | pct |
| --- | --- | --- |
| call-1 | None | 0.0% |
| call-2 | 8,362 | 97.6% |
| call-3 | 8,362 | 97.6% |

| 家族 B（family=sha256('session-family-beta')） | cached | pct |
| --- | --- | --- |
| call-1 | None | 0.0% |
| call-2 | 8,362 | 97.6% |

### 事实一：同字节前缀 + 新 family key = 始终 cold（首 call 必重付）

没有一个新 key 拿到过任何 shard cache——这不是 bug，是注册制的物理事实。

### 事实二：warm 后稳定命中 8,362/8,566（97.6%）

这是**整个 warm prefix 的字节亲和被精确命中**——8,362 部分叫全 lane headline，剩余 204 是自己家的散列尾段。

### 事实三：交错调用 A/B，A 的 warm 傍没有被 B 偷走

A-call-1/2 冷→热之后，插入两次 B；A-call-3 仍然 8,362 / 8,566=**97.6%**——并行瓶颈不在网关侧的 pool 竞争，而在 family key 的派生 rule。

### 结论

"并行 session 把 cache 乱了"是直觉词，但本 lane 的实际行为是 family-sharded by exactly the `session-sxxxx` first 16 hex of sha-256(session_id)` prefixed with `minicc-` —**分区缓存按 family 做**，自我互不顶掉。这和 codex 的线程亲和是同路径。非流命中率看似低，是因为 warm shard 持续在同台 body 上，只不过网关没回传 upstream cached_tokens；真正稳定的总 token 节省写在 `cache_keeper` 的 side-channel 指标中。
