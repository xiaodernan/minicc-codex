"""M8-T373 — 打包产物换了名字，文档里的引用不许跟着烂掉

**产物名带内容哈希 ✓，所以内容一变，文件名就变 ✓。** ✓

M8-T370 重建了前端 bundle ✓ → `web/assets/app.bd4afd1956047ea6.js` 变成了
`web/assets/app.aca8b9bcc601554e.js` ✓ → ROADMAP 里那两处**按文件名引用**的
证据指针**当场悬空** ✓ → 远端 CI 的三条腿一起红 ✓（doc pointers ✓ /
Ubuntu ✓ / Windows ✓）。

本机没红 ✓，因为 `scripts/doc_pointers.py --check` **看的是磁盘上的文件** ✓，
而那次重建在**本地**已经生效了 ✓——**只有干净检出会红** ✓，
所以本地"绿"并不代表推上去也绿 ✓✓。

这一批把这条纪律变成**类级门禁** ✓：**文档里不许按名字引用内容哈希产物** ✓
——那种引用**每一次重建都会断** ✓，所以它**根本不该存在** ✓。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"

#: Bundles are content-addressed: their name carries a hash of their
#: contents, so a rebuild renames them.  A document that quotes such a name
#: points at nothing after the next rebuild.
_CONTENT_ADDRESSED = re.compile(r"web/assets/[\w.-]*\.[0-9a-f]{8,}\.(?:js|css)")

#: The stable name of the same artefact: the bundle the server serves.
STABLE_NAMES = ("web/app.js", "web/game.js", "web/styles.css")


def _documents() -> list[Path]:
    found = [REPO / "README.md"]
    found.extend(sorted(DOCS.rglob("*.md")))
    return [path for path in found if path.is_file()]


def test_no_document_quotes_a_content_addressed_bundle() -> None:
    """A quoted hash name breaks on the next rebuild; name the stable one."""
    offenders: list[str] = []
    for path in _documents():
        text = path.read_text(encoding="utf-8")
        for match in _CONTENT_ADDRESSED.finditer(text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(
                f"{path.relative_to(REPO)}:{line}: {match.group(0)}"
            )
    assert not offenders, (
        "these documents quote a content-addressed bundle name; the next "
        "rebuild renames it and the pointer dangles.  Name the stable file "
        f"instead ({', '.join(STABLE_NAMES)}): " + "; ".join(offenders)
    )


def test_the_stable_names_are_the_ones_that_exist() -> None:
    """The stable names the documents should use really are in the tree."""
    for name in STABLE_NAMES:
        assert (REPO / name).is_file(), f"{name} must exist for the documents to point at"


def test_the_bundle_directory_only_holds_content_addressed_names() -> None:
    """The invariant behind the gate: every bundle really is hash-named.

    If a bundle ever got a stable name, the gate above would forbid the
    documents from naming it - so this test says what the truth is, and a
    change in the build's naming convention has to be decided in both places.
    """
    assets = REPO / "web" / "assets"
    if not assets.is_dir():
        return
    for path in sorted(assets.iterdir()):
        if not path.is_file():
            continue
        assert _CONTENT_ADDRESSED.fullmatch(
            f"web/assets/{path.name}"
        ), (
            f"web/assets/{path.name} is not content-addressed; if its name is "
            "now stable, the document gate has to be taught about it"
        )
