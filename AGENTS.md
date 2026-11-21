# AGENTS.md — minicc-codex 工作区引导

给在本工作区工作的 agent（minicc 自己、Codex、Claude 等）的dense事实卡。
本文件是**数据**：系统的安全边界与运行规则优先级永远更高。

## 这个仓库是谁
- minicc：本地优先的 coding agent + 开发者工作台（Python 引擎 `minicc/` + React 前端 `web/src/`）。
- 真实身份的账本都在 `docs/`：`ROADMAP_TO_PRODUCT.md` 是唯一开发账本（55k+ 行，每批一个编号条目）、`latest.json` 是仓库事实包、`INDEX.md` 是文档索引。

## 批次纪律（不可协商）
- 每个语义变更 = 一个新批次号（M8-T 编号递增），在 `docs/ROADMAP_TO_PRODUCT.md` 尾部追加条目：**缺什么 / 做了什么 / 证据与门 / 边界** 四段。
- 条目里写真实证据（测试名+数量、门禁名、E2E 输出），不写没有跑过的声明。
- 边界段如实写下"本批没做的部分"——下一批从这里接。

## 测试与验证
- 回归基线：`.venv`（Python 3.11.9）。系统 Python 3.14 的 subprocess 句柄有间歇性 WinError 6 噪声，spawn 子进程的测试失败先复跑再定性。
- 语义变更前跑相关家族（`pytest tests/<family>.py`），提交前跑全量（`.venv/Scripts/python.exe -m pytest tests/ -q`）。
- E2E 脚本（`tests/*_e2e.py`）烧真 token，手动跑，不进 CI。
- `tests/test_cleanup_version.py` 会拒绝仓库根目录出现任何运行产物（日志、临时文件）——用完即删。

## 前端门禁
- 改 `web/src/` 后必须 `npm run build:web` 重建 bundle，然后 `npm run check:web` 必须绿（bundle 与 asset-manifest 同步、无陈旧资产）。
- 年鉴新卷 = `web/src/panels/almanac.js` 的 CHAPTERS + LEDGER 常量 + Markup 函数 + CHAPTER_RENDERERS 注册 + `tests/almanac_smoke.mjs` 的章节数组与 CHAPTER_MARKERS，五处一一对应；年鉴正文来自 `scripts/forge_facts.py` + `scripts/almanac_forge.py` 真实锻造，不手写传文。
- en 侧零 CJK 是铁律：`tests/en_cjk_smoke.mjs` + almanac smoke 双 locale 全章节遍历。
- 中文文案单一事实源：`web/src/core/i18n.js` 的双语字典；`minicc/cli_io.py` 的 `_MESSAGES` 是引擎侧双语文案的家。

## 文档指针门禁
- `scripts/doc_pointers.py`（pytest `tests/test_doc_pointers.py`）扫描全部文档：引用的文件路径必须存在、测试名必须真实、URL 原样放过。账本里提到的文件被删/改名时同步修账本。
- `minicc/config.py` 新增的每个 `MINICC_*` 环境键必须在 `minicc.config.example` 里文档化（`tests/test_config_surface.py` 强制）。

## 数字事实的单一归属（跨卷漂移的高发区）
- 会随年鉴卷次变化的计数（Atlas 坐标、卷数、卫星数）只有一个真值源：`web/src/panels/almanac.js` 的 CHAPTERS 与 `atlas.js` 的 charted 行；`prompt.py` 的抄本、`manual.js` / `onboarding.js` 的文案、各 smoke 的期望都必须从它派生，不许各自硬编码。
- 历史快照（旧卷正文里的当年计数）是事实、不是漂移，别改；只同步「当前窗口」的抄本。加门时优先让门从真值源派生期望，而不是钉死数字——否则新卷落地下一个漏抄的门就成了维护负担。
- 相关门：`tests/test_world_map_almanac_catalog.py`、`tests/atlas_smoke.mjs`、`tests/frontend_trace_code_one_home_smoke.mjs`、`tests/test_the_*_one_home*.py`。

## 缓存与 prompt 纪律
- system prompt 的分节保持字节稳定（跨轮缓存命中依赖它）；新增分节必须是全局稳定字节或显式有界。
- `prompt.py` 的 `_WORLD_MAP` 数字（提交数、批次、坐标）只在不诚实风险为零的更新时机刷新；与 `docs/latest.json` 不一致时以 latest.json 为准并在下一批修齐。

## 已知边界
- StateGraph 的 LLM route_decider 已接线到 web.py 执行引擎的 verify 失败分叉（fail-closed）；execute_dag/固定模板尚未接。
- 年鉴 UI 与锻造流水线（forge_facts → almanac_forge → CHAPTER_DRAFT → almanac.js）每卷走全流程，INDEX.md 条目与 CHAPTER_DRAFT.json 必须同批落地。
