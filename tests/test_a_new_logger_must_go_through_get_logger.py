"""M8-T330 — 新加的日志器必须走仓库自己的 `get_logger()`

仓库的约定是 `logging_setup.get_logger(name)`：它会调 `configure_logging()`，
把 `SecretRedactionFilter` 挂到 "minicc" 日志器的 handler 上，并把 `propagate`
设成 False。

而裸的 `logging.getLogger("minicc.rpc")` 两件事都不做：它是 "minicc" 的**子
日志器**，但**没有配置**它。于是记录会**穿过**根 logger 的 handler——**绕过脱敏
过滤器**——而这条记录带的是**完整 traceback**。

本门禁在**全新解释器**里逐个模块单独验：否则只要另一个模块调过
`get_logger`，整个命名空间就配置好了，这条门禁就永远绿——而那个模块自己仍然
是漏的。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

MODULES = ["minicc.output_style", "minicc.agent.rpc"]

_PROBE = (
    "import importlib, logging, sys;"
    "importlib.import_module(sys.argv[1]);"
    "root = logging.getLogger('minicc');"
    "print(len(root.handlers), root.propagate)"
)


def _probe(module: str) -> tuple[int, bool]:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, module],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        # The child's own stdout has to be decoded the same way the parent's
        # is: without the environment pin, the child picks the platform's
        # default encoding and the two halves of a pipe disagree.
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"{module}: {result.stderr[-800:]}"
    handlers, propagate = result.stdout.split()
    return int(handlers), propagate == "True"


@pytest.mark.parametrize("module", MODULES)
def test_importing_the_module_alone_configures_the_logging(module: str) -> None:
    """The module has to configure the namespace it writes into."""
    handlers, propagate = _probe(module)
    assert handlers, (
        f"importing {module} left the 'minicc' logger without a handler - the "
        "secret-redaction filter is not attached, so every record walks past it"
    )
    assert propagate is False, (
        f"importing {module} left the 'minicc' logger propagating to the root "
        "handlers, so its records are emitted a second time without the "
        "redaction"
    )
