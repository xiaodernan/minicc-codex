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
