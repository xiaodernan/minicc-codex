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
