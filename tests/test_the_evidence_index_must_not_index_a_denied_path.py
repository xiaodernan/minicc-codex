"""M8-T351 — deny 规则也管得住本地检索索引

`permissions.json` 的 deny 规则是绝对否决：`secrets/*` 被拒，agent 读它被拒。
而**本地检索索引**是同一批文件的另一个读者——它不問规则，于是：

1. 索引把 `secrets/notes.json` 收进去了（实测：`records` 里就有它）；
2. 一次以 "TOPSECRET" 为关键词的检索命中了它（`reason: content+fresh`）；
3. 于是模型的证据包里出现了**被拒路径**的名字与符号——模型被指向一个它读
   不了的文件，只能白跑一轮。

被拒路径的前置理由与快照那条一样：**规则管的是路径，而索引是路径的另一个
搬运工**（M8-T350 修的是快照那条搬运路）。

本门钉住：被规则覆盖的路径不进索引、也不会成为命中；索引的普查里**披露**
被拒的条数（它是"按政策变小"，不是"被预算截断"）；控制组——没被规则碰到的
文件照旧被索引、照旧能命中。
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.agent.retrieval import get_evidence_index


def _workspace(tmp_path: Path, *, deny_paths: list[str] | None) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "secrets").mkdir(parents=True)
    (workspace / "secrets" / "notes.json").write_text(
        json.dumps({"projectkey": "TOPSECRET-VALUE"}), encoding="utf-8"
    )
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text(
        "def f():\n    return 1\n", encoding="utf-8"
    )
    if deny_paths is not None:
        (workspace / ".minicc").mkdir()
        (workspace / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": {"paths": deny_paths}}), encoding="utf-8"
        )
    return workspace


def test_a_denied_path_is_not_indexed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    index = get_evidence_index(workspace)
    hits = index.search("TOPSECRET", limit=8)
    assert not hits, [hit.path for hit in hits]
    # Only the ordinary file made it into the index.
    assert index.stats().get("files_indexed") == 1, index.stats()


def test_no_hit_names_a_denied_path(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    index = get_evidence_index(workspace)
    for query in ("TOPSECRET", "secrets", "notes", "projectkey"):
        for hit in index.search(query, limit=8):
            assert not hit.path.startswith("secrets/"), (query, hit.path)


def test_the_census_discloses_the_denied_count(tmp_path: Path) -> None:
    """A skip the operator cannot see is a silent hole."""
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    index = get_evidence_index(workspace)
    stats = index.stats()
    assert stats.get("files_denied") == 1, stats
    # A denied path is missing **by policy**, not by a budget: the walk is
    # still complete.
    from minicc.agent.retrieval import census_is_complete

    assert census_is_complete(stats) is True, stats


def test_an_ordinary_file_is_still_indexed_and_hits(tmp_path: Path) -> None:
    """The control: the index still does its job."""
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    index = get_evidence_index(workspace)
    hits = index.search("def f", limit=8)
    assert any(hit.path == "src/app.py" for hit in hits), [hit.path for hit in hits]
    assert index.stats().get("files_indexed") == 1, index.stats()
