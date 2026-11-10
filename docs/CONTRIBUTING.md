# 贡献指南

本仓库有超过 350 个合流批次和一整套"接手"门，合并 discipline 不是文档化在 README 里的装饰——而是每次提交都要过的门。本文只写**本地能亲手验证**的步骤；CI 里每个门都对应本仓一个脚本或测试文件。

## 1. 准备开发环境

```powershell
git clone <this repo>
cd minicc-codex
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

（Linux/macOS：`python -m venv .venv && .venv/bin/pip install -e ".[dev]"`。）

## 2. 提交前必跑的三件事

```powershell
# 文档指针：证据链（docs/*.md 里引用的路径必须存在、被 git 跟踪）
python scripts/doc_pointers.py --check

# 窄门：ROADMAP 账本不得出现 helper 脚本的整段前导
python -m pytest tests/test_roadmap_does_not_contain_helper_script_source.py -q

# 门：docs/INDEX.md 必须点名 docs/ 下每一篇
python -m pytest tests/test_docs_index_enumerates_every_docs_md.py -q
```

三件全绿才提交。任何一件红，**先修让门按原意通过，绝不放宽门**。

## 3. 跑完整测试

```powershell
python -m pytest -q
```

Windows 上全套约需数分钟；`test_installed_console_scripts_run_from_a_real_install` 在本地 Windows 上因全局 Python 没有 `openai` 包而红，属 CI-only 门（Ubuntu 腿打绿为准），本地可忽略该条单独失败。

## 4. 批次账本

每个提交 commit message 形如 `M8-T<批次号>: <一句话>`；`docs/ROADMAP_TO_PRODUCT.md` 为每个批次追加一节，格式：

```markdown
## 批次 <号> — M8-T<号>：<标题>

### 1 欠的是哪一条
### 2 改动
### 3 验证
### 4 边界
```

账本只追加不改写（修错自己的新批次时，明确注明修的批次号）。

## 5. One Fact One Home

同一事实只能有一个"家"。术语、常量、配置段落、字段名只能有一个权威定义。发现第二家，删到只剩一家；不行就拆成两个不同名字的东西。方法论见 [ONE_FACT_ONE_HOME.md](ONE_FACT_ONE_HOME.md)。

## 6. 提交与推送

- 推送前确保 `git status` 干净、`doc_pointers --check` rc=0。
- CI 双腿（ubuntu/windows）都可能非常慢（~20-35 分钟）。"推了一个尚不稳定的 tip"会被后续更新的 tip 取消并取代——这是刻意的：宁可整条 CI 绿也不留红 tip 在 main 上。
- 只有当 candidate 侧 failures==0 且无 leg 在跑了，才推下一笔。

## 7. 新建文档时的三件事

1. 在 `docs/INDEX.md` 登记一行（否则门 `tests/test_docs_index_enumerates_every_docs_md.py` 会红）；
2. 至少被一篇别的文档引用（指针门 `scripts/doc_pointers.py --check` 会查）；
3. 内容取自本仓事实（配置、代码、测试），不凭空设计。
