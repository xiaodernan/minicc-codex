<!-- minicc 仓库的 PR 模板。CI 有十余个 leg；以下清单按本地能跑的门排序。 -->

## 做了什么

<!-- 一句话说清动机和改动面 -->

## 本地验证

- [ ] `python scripts/doc_pointers.py --check` → rc=0（若动了 docs，必跑）
- [ ] `python -m pytest tests/test_roadmap_does_not_contain_helper_script_source.py tests/test_docs_index_enumerates_every_docs_md.py -q` → 全绿
- [ ] `python -m pytest -q`（或至少覆盖改动面的模块测试）
- [ ] 若新增 `docs/*.md`：`docs/INDEX.md` 里登记了一行
- [ ] 若改动发布/合流纪律：commit message 形如 `M8-T<号>: <一句话>`，`docs/ROADMAP_TO_PRODUCT.md` 追加了对应批次

## 注意

- CI-only 门 `test_installed_console_scripts_run_from_a_real_install` 在本地 Windows 上因全局 Python 缺 `openai` 会红——CI 是准绳，本地红不算数。
- 不要放宽任何门来让 CI 绿（先修门意图，不削门）。
- nightly eval 默认跳过。
- 不要提交 `.minicc/`（已被 .gitignore 覆盖，复核一下 `git status`）。
