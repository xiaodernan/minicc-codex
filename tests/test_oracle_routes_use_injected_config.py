"""M8-T1339: oracle HTTP routes must use the service's injected config.

Before this, the builders reloaded .env from disk via their default `config=None`.
With the project switched to a slow local CPU model (M8-T1335), the route-
coverage probe's 30s timeout was exceeded by a real LLM call on
`/api/oracle-plan` etc. — a test-only server with a fake config was silently
making real model calls. Passing the service config keeps production behavior
identical (same config) while tests and slow lanes use what was injected.
"""

from __future__ import annotations

import re
from pathlib import Path

WEBSERVER = Path(__file__).resolve().parents[1] / "minicc" / "webserver.py"


def _text() -> str:
    return WEBSERVER.read_text(encoding="utf-8")


def test_every_llm_oracle_builder_receives_the_injected_config() -> None:
    body = _text()
    # Every LLM-backed builder call must carry config=...; find any call missing it.
    calls = re.findall(r"self\._json\((build_\w+)\((.*?)\)\)", body, re.DOTALL)
    llm_builders = {
        "build_ci_diagnosis", "build_audit_story", "build_workspace_retrospective",
        "build_workspace_recommendations", "build_trend_insight", "build_visitor_insight",
        "build_workspace_review", "build_workspace_plan", "build_workspace_diagnosis",
        "build_workspace_brief",
    }
    seen = {name for name, args in calls if name in llm_builders}
    assert seen == llm_builders, f"oracle builders not reached as route calls: {llm_builders - seen}"
    for name, args in calls:
        if name in llm_builders:
            assert "config=self.server.service.config" in args, f"{name} reloads config from disk"


def test_rule_based_drift_is_left_alone() -> None:
    # admin_drift has no config param; do not force one into it.
    body = _text()
    line = next((l for l in body.splitlines() if "self._json(build_workspace_drift(" in l), "")
    assert line, "drift route disappeared"
    assert "config=" not in line
