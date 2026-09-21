# 插件 API（工具契约 v1）

本文定义 **minicc 对第三方工具承诺的稳定接口**：字段契约、版本号、注册期校验、
冲突与覆盖语义，以及能力声明如何影响权限判定。

对应里程碑：`docs/ROADMAP_TO_PRODUCT.md` → M8-T3。
回归测试：`tests/test_plugin_api.py`（本文所有 ```python 代码块由该测试原样执行）。

公开入口只有一个，全部从 `minicc.tools` 导入：

```python
from minicc.tools import (
    CAPABILITIES,          # 可声明的能力名集合
    TOOL_API_VERSION,      # 当前宿主实现的工具接口版本
    Editor,                # 工作区边界内的文件读写原语
    Param,                 # 参数声明（配合 params 使用）
    ToolCall,              # 一次调用：tool + arguments
    ToolRegistrationError, # 注册被拒时抛出的异常（ValueError 子类）
    ToolRegistry,          # 注册表：register / execute / restrict
    ToolResult,            # 统一返回值
    ToolSpec,              # 工具声明
    build_registry,        # 内置工具集
    validate_tool_spec,    # 不注册只校验（CI 里自检用）
)
```

---

## 1. ToolSpec 字段契约

| 字段 | 类型 | 必填 | 约束 | 作用 |
| --- | --- | --- | --- | --- |
| `name` | `str` | 是 | 1–128 位，字母或数字开头，只含 `A-Za-z0-9_.-~` | 模型侧调用名，注册表的唯一键 |
| `description` | `str` | 是 | 非空 | **直接进入模型上下文**，决定它会不会用你的工具 |
| `risk` | `str` | 是 | `readonly` \| `write` \| `exec` | 权限策略的唯一输入，见下表 |
| `params` | `tuple[Param, ...]` | 是 | 名字唯一、类型合法；与 `input_schema` 二选一 | 由注册表负责校验并拒绝未知参数 |
| `handler` | `callable` | 是 | 可调用 | 真正干活；`handler(arguments) -> ToolResult` |
| `visible` | `bool` | 否（默认 `True`） | — | 是否出现在工具明细里 |
| `input_schema` | `dict \| None` | 否 | 顶层 `type == "object"`；与 `params` 二选一 | 需要嵌套/枚举结构时自己给 JSON Schema |
| `cancellable` | `bool` | 否（默认 `False`） | — | `True` 时以 `handler(arguments, cancel_event=...)` 调用 |
| `api_version` | `int` | 否（默认 `TOOL_API_VERSION`） | `<= TOOL_API_VERSION` | 声明依赖的接口版本 |
| `capabilities` | `tuple[str, ...]` | 否（默认空） | 只能取 `CAPABILITIES` 中的值，且不低于 `risk` | 能力声明，见第 4 节 |

`Param(name, type, required=False, min_value=None, max_value=None, max_len=None, description="")`，
`type` 只能是 `"str" | "int" | "bool" | "list[str]"`。

### risk 决定权限，不决定实现

| risk | 无授权时的默认结果 |
| --- | --- |
| `readonly` | 直接放行（联网类除外，见 `capabilities`） |
| `write` | 需要本任务写入授权（`--allow-changes` / Web 审批 / 会话 allowlist） |
| `exec` | 需要本任务命令授权；命令含联网行为时额外要联网授权 |

**把有副作用的工具标成 `readonly` 就是提权。** 注册表无法读你的代码，因此第 4 节的
能力声明用来把「我做了什么」写进契约，并检查它和 `risk` 是否自相矛盾。

## 2. 版本号

`TOOL_API_VERSION = 1`。宿主只会拒绝，不会猜测：

- `api_version > TOOL_API_VERSION` → 拒绝注册，提示升级 minicc 或降低声明版本；
- 声明版本低于已下线的最低版本 → 拒绝注册。

字段语义变化时才会升版本号；新增带默认值的可选字段不算破坏性变更。

## 3. 注册期校验与冲突语义

`registry.register(spec)` 会先完整校验，再检查命名冲突：

1. **非法 schema 直接抛 `ToolRegistrationError`**（它是 `ValueError` 子类），消息点名出错字段。
   这是硬门：一个坏 `input_schema` 会让整轮 provider 请求失败，把整个会话拖死。
2. **后注册者不会静默替换已存在的工具。** 与内置工具同名时错误里写明「内置工具」，
   确需替换必须显式 `override=True`，且替换会被记录在 `registry.overrides()` 里供审计。

```python
import tempfile
from pathlib import Path

from minicc.tools import (
    Editor,
    Param,
    ToolCall,
    ToolRegistrationError,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    build_registry,
)

workspace = Path(tempfile.mkdtemp())  # 实际使用时换成你的项目根目录

# 1) 一个合法插件：能跑，且被 /tools 列出来
def line_count(args: dict) -> ToolResult:
    text = (workspace / args["path"]).read_text(encoding="utf-8")
    return ToolResult(
        status="ok",
        summary=f"{args['path']} 共 {len(text.splitlines())} 行",
    )

registry = ToolRegistry()
registry.register(ToolSpec(
    name="line_count",
    description="统计工作区内某个文本文件的行数。",
    risk="readonly",
    params=(Param("path", "str", required=True, max_len=512, description="工作区相对路径"),),
    handler=line_count,
    capabilities=("fs_read",),
))
(workspace / "notes.txt").write_text("a\nb\nc\n", encoding="utf-8")
result = registry.execute(ToolCall("line_count", {"path": "notes.txt"}))
assert result.status == "ok" and "3" in result.summary

# 未知参数由注册表拒绝，handler 永远收不到它
assert registry.execute(ToolCall("line_count", {"file": "notes.txt"})).status == "error"

# 2) 非法 schema 被拒，且错误信息点名 required
try:
    registry.register(ToolSpec(
        name="broken",
        description="required 引用了没声明的属性。",
        risk="readonly",
        params=(),
        handler=lambda args: ToolResult(),
        input_schema={"type": "object", "properties": {"q": {"type": "string"}},
                      "required": ["nope"]},
    ))
    raise AssertionError("非法 schema 应当被拒绝")
except ToolRegistrationError as exc:
    assert "required" in str(exc)

# 3) 与内置同名不会静默替换
builtins = build_registry(Editor(workspace))
try:
    builtins.register(ToolSpec(
        name="read_file", description="顶掉内置读文件工具。", risk="readonly",
        params=(), handler=lambda args: ToolResult(),
    ))
    raise AssertionError("与内置工具同名应当被拒绝")
except ToolRegistrationError as exc:
    assert "内置工具" in str(exc) and "override=True" in str(exc)

# 4) 显式覆盖：替换成功，且留下可审计记录
builtins.register(ToolSpec(
    name="read_file", description="替换版读文件工具。", risk="readonly",
    params=(), handler=lambda args: ToolResult(status="ok", summary="replaced"),
), override=True)
assert builtins.overrides() == {"read_file": "builtin"}
assert builtins.execute(ToolCall("read_file", {})).summary == "replaced"
```

## 4. 能力声明（capabilities）

可选、只能收紧、不能放宽。取值：

| 能力 | 最低 `risk` | 权限后果 |
| --- | --- | --- |
| `fs_read` | `readonly` | 仅声明，不改变判定 |
| `network` | `readonly` | **走内置联网工具同一道门**：未授予本任务联网权限时直接拒绝，且 `plan` 之外也不会自动放行 |
| `fs_write` | `write` | 声明它却写 `readonly` 会被注册期拒绝 |
| `shell` | `exec` | 同上 |

```python
from minicc.audit import authorize_tool, tool_requires_authorization
from minicc.tools import ToolRegistrationError, ToolRegistry, ToolResult, ToolSpec

registry = ToolRegistry()
registry.register(ToolSpec(
    name="http_head",
    description="对单个 URL 发一次 HEAD 请求。",
    risk="readonly",
    params=(),
    handler=lambda args: ToolResult(status="ok", summary="200"),
    capabilities=("network",),
))

name = "http_head"
caps = registry.capabilities_of(name)
risk = registry.risk_of(name)

# 声明了 network 就必须过授权门，即使它只是 readonly
assert tool_requires_authorization(name, risk, caps) is True
# 未授权联网 → 拒绝，并给出可读原因
denied = authorize_tool(name, risk, {}, allow_changes=False, allow_network=False,
                        capabilities=caps)
assert denied.allowed is False and denied.authorization == "missing_task_network"
# 本任务明确授权联网 → 放行
granted = authorize_tool(name, risk, {}, allow_changes=False, allow_network=True,
                         capabilities=caps)
assert granted.allowed is True

# 自相矛盾的声明（写文件却标 readonly）在注册期就被拒
try:
    registry.register(ToolSpec(
        name="sneaky", description="谎报风险等级。", risk="readonly",
        params=(), handler=lambda args: ToolResult(), capabilities=("fs_write",),
    ))
    raise AssertionError("fs_write 至少要 write 风险")
except Exception as exc:
    assert "fs_write" in str(exc)
```

不声明能力 = 什么都不会多得到（内置工具即按此运行）；`network` 是**唯一**能改变判定的声明，
因为「只读但会出网」正是命名白名单挡不住的那一类。

## 5. handler 契约

- 入参 `arguments: dict` 已由注册表校验过（`params` 模式）或原样透传（`input_schema` 模式）。
  **它是模型写的，属于不可信输入**：路径一律走 `Editor`/工作区相对路径，不要拼 shell。
- 返回值必须是 `ToolResult`：`status ∈ ok|error|denied|cancelled|timed_out`，
  `summary` 一行结论，`output` 正文，`data` 放结构化附加信息。
- 抛 `ToolError` → 模型收到 `[TOOL_ERROR] …`；抛 `ToolParamError` → `[INVALID_ARGUMENTS] …`；
  抛任何其他异常也会被兜底成 `[TOOL_ERROR]`，不会打断 agent 循环。
- 输出**自动脱敏**（API key、Bearer、私钥块、带凭据的 URL 等），命中即追加
  `security_tags=["redacted"]`；不要自己把密钥回显到 `summary`。
- 长输出请自己用 `from minicc.tools.registry import split_output` 做头尾保留截断，
  并把 `truncated` 据实置为 `True`；注册表不会替你裁。
- 需要响应取消时设 `cancellable=True`，并周期性检查 `cancel_event.is_set()`。

## 6. 怎么把插件接进一次真实运行

当前版本**没有磁盘扫描式加载器**，这是刻意决定：minicc 会在不可信仓库上工作，
自动 import 工作区里的 `.py` 等于让被分析的项目在你机器上执行任意代码。
集成方式是显式的、由你写下的 Python：

```python
from pathlib import Path  # doc-test: skip

from minicc.tools import Editor, build_registry

workspace = Path(".")  # 项目根目录
registry = build_registry(Editor(workspace))

# 显式安装：只有你 import 过的模块才会获得注册能力
import my_minicc_plugin  # 你自己写的模块

my_minicc_plugin.install(registry)
```

`install(registry)` 内部就是一串 `registry.register(ToolSpec(...))`。需要覆盖内置工具时
必须写 `override=True`，运行后可从 `registry.overrides()` 回查替换了谁。

## 7. 兼容性承诺

- 只要 `TOOL_API_VERSION` 不变，字段含义、`risk` 语义、`[CODE]` 错误前缀、脱敏规则都不变。
- 新增可选字段（带默认值）不算破坏；删除字段、改变字段含义、改变权限判定才会升版本。
- `registry.register()` 的失败类型始终是 `ValueError` 子类，老的 `except ValueError` 调用方不受影响。
