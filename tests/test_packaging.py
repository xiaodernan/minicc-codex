"""M8-T4 packaging contract: an installed wheel must serve the workbench.

Every artifact test here builds for real, because the defects this milestone is
about (a wheel that installs but 404s the workbench, a version that drifts
between pyproject and the CLI, a README that tells users to run a script that
does not exist) are invisible to source-tree tests.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = """
import pathlib, sys
from setuptools import build_meta
out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
print(build_meta.build_wheel(str(out)))
print(build_meta.build_sdist(str(out)))
"""
JUNK_MARKERS = (".env", "node_modules", "__pycache__", ".sqlite3", ".log")


def _build(args: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=str(cwd), capture_output=True, text=True, errors="replace", timeout=timeout
    )


def _payload(names: set[str]) -> set[str]:
    return {name for name in names if ".dist-info" not in name}


def _manifest() -> dict[str, str]:
    return json.loads((REPO / "web" / "asset-manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    built = _build(["-c", BUILD_SCRIPT, str(out)], REPO)
    assert built.returncode == 0, built.stdout[-3000:] + built.stderr[-3000:]
    assert list(out.glob("*.whl")) and list(out.glob("*.tar.gz"))
    return out


@pytest.fixture(scope="module")
def wheel(dist: Path) -> Path:
    return max(dist.glob("*.whl"), key=lambda path: path.stat().st_mtime)


@pytest.fixture(scope="module")
def wheel_names(wheel: Path) -> set[str]:
    with zipfile.ZipFile(wheel) as archive:
        return set(archive.namelist())


@pytest.fixture(scope="module")
def metadata(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        name = next(entry for entry in archive.namelist() if entry.endswith(".dist-info/METADATA"))
        # METADATA is written with CRLF on Windows; normalise so `$` anchors work.
        return archive.read(name).decode("utf-8").replace("\r\n", "\n")


def test_wheel_ships_the_workbench_payload(wheel_names: set[str]) -> None:
    required = {"minicc/web_static/index.html", "minicc/web_static/asset-manifest.json"}
    # The manifest lists what index.html actually requests, so a missing target
    # is exactly the "installed but blank workbench" failure this task fixes.
    required |= {f"minicc/web_static{versioned}" for versioned in _manifest().values()}
    assert sorted(required - wheel_names) == []


def test_wheel_ships_the_ide_companion(wheel_names: set[str]) -> None:
    assert "minicc/ide_static/vscode/extension.js" in wheel_names
    assert "minicc/ide_static/vscode/package.json" in wheel_names


def test_wheel_excludes_development_junk(wheel_names: set[str]) -> None:
    junk = [name for name in wheel_names if any(marker in name for marker in JUNK_MARKERS)]
    assert junk == []
    assert not any(name.startswith(("tests/", "web/", "ide/", "dist/", "build/")) for name in wheel_names)


def test_an_uncleaned_build_directory_cannot_ship_a_module_that_no_longer_exists(
    tmp_path: Path,
) -> None:
    """setup.py prunes build/lib, because bdist_wheel collects its payload by walking it.

    Measured before the fix (batch 112, in a clone): delete ``minicc/mentions.py`` and
    rebuild without cleaning, and the wheel still shipped ``minicc/mentions.py`` - 76
    modules in the wheel while the source tree held 75. A rename ships the old name
    beside the new one, and nothing in the build ever removes a file.

    The plant is a module that never existed in the source tree, so the shape is
    reproduced without deleting anything from the checkout. It goes into the build
    directory the real build uses, and the next build must not carry it.
    """
    planted = REPO / "build" / "lib" / "minicc" / "stale_payload_probe.py"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text("# planted by the packaging test; must never reach a wheel\n", encoding="utf-8")
    try:
        out = tmp_path / "dist"
        built = _build(["-c", BUILD_SCRIPT, str(out)], REPO)
        assert built.returncode == 0, built.stdout[-3000:] + built.stderr[-3000:]
        # The report distinguishes "pruned it" from "it was never there": without this the
        # next assertion would also pass on a machine whose build directory happened to be
        # clean, which is the vacuity this test exists to avoid.
        assert "pruned" in built.stdout, built.stdout[-800:]
        wheel = max(out.glob("*.whl"), key=lambda path: path.stat().st_mtime)
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
        assert "minicc/stale_payload_probe.py" not in names, sorted(
            name for name in names if "stale_payload" in name
        )
    finally:
        planted.unlink(missing_ok=True)


def test_console_scripts_are_declared_and_resolve(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        points = archive.read(
            next(entry for entry in archive.namelist() if entry.endswith(".dist-info/entry_points.txt"))
        ).decode("utf-8").replace("\r\n", "\n")
    scripts = dict(re.findall(r"^([A-Za-z0-9_-]+)\s*=\s*([\w.]+:[\w]+)$", points, re.MULTILINE))
    assert set(scripts) == {"minicc", "minicc-web"}
    for name, target in scripts.items():
        module, _, attribute = target.partition(":")
        check = f"import importlib; m = importlib.import_module({module!r}); "
        check += f"assert callable(getattr(m, {attribute!r}))"
        resolved = _build(["-c", check], REPO, timeout=300)
        assert resolved.returncode == 0, f"{name} -> {target}: {resolved.stderr[-500:]}"


def test_version_is_single_sourced(metadata: str, wheel: Path, dist: Path) -> None:
    from minicc import __version__

    declared = re.search(r"^Version: (.+)$", metadata, re.MULTILINE)
    assert declared and declared.group(1) == __version__
    assert wheel.name.startswith(f"minicc-{__version__}-")
    assert (dist / f"minicc-{__version__}.tar.gz").is_file()
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version\s*=\s*["\']', pyproject, re.MULTILINE) is None, "static version pin"
    assert 'version = { attr = "minicc.__version__" }' in pyproject


def test_ide_extension_version_matches_the_package() -> None:
    from minicc import __version__

    manifest = json.loads((REPO / "ide" / "vscode" / "package.json").read_text(encoding="utf-8"))
    assert manifest["version"] == __version__, (
        "ide/vscode/package.json is a fourth version site: bump it with minicc.__version__"
    )


def test_readme_npm_commands_all_exist() -> None:
    scripts = set(json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"])
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"npm run ([A-Za-z0-9:_-]+)", readme))
    assert referenced, "README no longer documents any npm command"
    assert referenced - scripts == set()


def test_build_dist_script_is_real_and_documented() -> None:
    script = (REPO / "scripts" / "build-dist.ps1").read_text(encoding="utf-8")
    assert "build_meta.build_wheel" in script and "build_meta.build_sdist" in script
    assert "web_static/index.html" in script, "the release script must verify the workbench payload"
    assert "build-dist.ps1" in (REPO / "README.md").read_text(encoding="utf-8")


def test_sdist_round_trip_builds_the_same_wheel(
    dist: Path, wheel_names: set[str], tmp_path: Path
) -> None:
    sdist = max(dist.glob("*.tar.gz"), key=lambda path: path.stat().st_mtime)
    with tarfile.open(sdist) as archive:
        try:
            archive.extractall(tmp_path, filter="data")
        except TypeError:  # filter= arrived in 3.11.4; the sdist has no links to guard
            archive.extractall(tmp_path)
    source = next(path for path in tmp_path.iterdir() if path.is_dir())
    assert (source / "web" / "index.html").is_file(), "sdist must carry the workbench tree"
    assert (source / "setup.py").is_file(), "sdist must carry the static-asset build hook"
    out = tmp_path / "redist"
    rebuilt = _build(
        ["-c", "import pathlib, sys; from setuptools import build_meta; "
         "print(build_meta.build_wheel(sys.argv[1]))", str(out)],
        source,
    )
    assert rebuilt.returncode == 0, rebuilt.stdout[-2000:] + rebuilt.stderr[-2000:]
    names = set(zipfile.ZipFile(max(out.glob("*.whl"))).namelist())
    assert _payload(names) == _payload(wheel_names)


def test_static_root_prefers_the_packaged_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from minicc import static_assets

    packaged = tmp_path / "site" / "minicc" / "web_static"
    checkout = tmp_path / "repo" / "web"
    packaged.mkdir(parents=True)
    checkout.mkdir(parents=True)
    monkeypatch.setattr(static_assets, "_PACKAGE_ROOT", packaged.parent, raising=True)
    monkeypatch.setattr(static_assets, "_CHECKOUT_ROOT", checkout.parent, raising=True)
    assert static_assets.web_root() == checkout, "an unpopulated package tree must not win"
    (packaged / "index.html").write_text("<html></html>", encoding="utf-8")
    assert static_assets.web_root() == packaged


def test_installed_wheel_serves_the_workbench(wheel: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    installed = _build(
        ["-m", "pip", "install", "--no-index", "--no-deps", "--target", str(site), str(wheel), "--quiet"],
        REPO,
        timeout=600,
    )
    assert installed.returncode == 0, installed.stdout[-2000:] + installed.stderr[-2000:]
    check = """
import json, sys
sys.path.insert(0, sys.argv[1])
from minicc import static_assets
root = static_assets.web_root()
assert root.name == "web_static", root
body, headers = static_assets.asset_response(root, "index.html")
assert b"<" in body and headers["Content-Type"].startswith("text/html"), headers
manifest = json.loads((root / "asset-manifest.json").read_text(encoding="utf-8"))
bundle_name = next(iter(manifest.values())).lstrip("/")
bundle, bundle_headers = static_assets.asset_response(root, bundle_name)
assert bundle and bundle_headers["Content-Type"], bundle_headers
print("served", len(body), "html +", len(bundle), "bytes of", bundle_name)
"""
    served = _build(["-c", check, str(site)], tmp_path, timeout=300)
    assert served.returncode == 0, served.stdout + served.stderr[-2000:]
    assert "served" in served.stdout


def _scripts_dir(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_installed_console_scripts_run_from_a_real_install(tmp_path: Path, wheel: Path) -> None:
    """M8-T4's acceptance, executable: both entry points run from an install.

    The recorded E2E (the M8-T4 row) ran ``pip wheel .`` into a clean venv,
    ``minicc --version``, then ``minicc-web --port ...`` answering ``/``, the
    hash bundles and ``/api/health`` with 200. Nothing in the suite repeats
    that: the console-script test resolves the entry points from the *repo*
    tree, and the installed-wheel test serves assets through
    ``static_assets`` directly, never through a server an installed
    ``minicc-web`` would start. This gate runs the real scripts from a real
    install of the real wheel.

    The venv is created with ``--system-site-packages`` and the wheel with
    ``--no-deps --no-index``: dependency completeness is pyproject's
    contract (``pip check``), and this gate must stay hermetic and offline.
    What it proves is the artifact half - the console wrappers, the packaged
    workbench payload, and a server that serves them. An anti-vacuity check
    pins that the imported ``minicc`` is the installed one, not the checkout.
    """
    from minicc import __version__

    venv = tmp_path / "venv"
    venv_python = venv.joinpath("Scripts", "python.exe") if os.name == "nt" else venv.joinpath("bin", "python")
    created = _build(["-m", "venv", "--system-site-packages", str(venv)], REPO, timeout=300)
    assert created.returncode == 0, created.stdout[-2000:] + created.stderr[-2000:]
    installed = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel), "--quiet"],
        cwd=str(tmp_path), capture_output=True, text=True, errors="replace", timeout=600,
    )
    assert installed.returncode == 0, installed.stdout[-2000:] + installed.stderr[-2000:]

    # Anti-vacuity: the venv must be serving the wheel's package, not the
    # checkout the test process itself imported.
    origin = subprocess.run(
        [str(venv_python), "-c", "import minicc; print(minicc.__file__)"],
        cwd=str(tmp_path), capture_output=True, text=True, errors="replace", timeout=120,
    )
    assert origin.returncode == 0, origin.stderr[-2000:]
    module_path = Path(origin.stdout.strip()).resolve()
    assert str(module_path).casefold().startswith(str(venv.resolve()).casefold()), (
        f"the venv resolved minicc outside itself: {module_path}"
    )

    scripts = _scripts_dir(venv)
    cli = scripts / ("minicc.exe" if os.name == "nt" else "minicc")
    version = subprocess.run(
        [str(cli), "--version"], cwd=str(tmp_path), capture_output=True, text=True, errors="replace", timeout=120
    )
    assert version.returncode == 0, version.stdout + version.stderr[-2000:]
    assert f"minicc {__version__}" in version.stdout, version.stdout

    workspace = tmp_path / "ws"
    workspace.mkdir()
    port = _free_port()
    web = scripts / ("minicc-web.exe" if os.name == "nt" else "minicc-web")
    server = subprocess.Popen(
        [str(web), "--workspace", str(workspace), "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
    )
    try:
        deadline = time.monotonic() + 60
        ready = False
        while time.monotonic() < deadline:
            if server.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as probe:
                    if probe.status == 200:
                        ready = True
                        break
            except OSError:
                time.sleep(0.25)
        if not ready:
            # Batch 221: CI has been red here since 2026-10-08 with only "never
            # answered /api/health within 60s", which is the wrong sentence when the
            # server died instantly - the loop breaks on poll() and the message reads
            # like a timeout. The output was already being captured, but only in the
            # finally block, so it was lost whenever this path raised. Reap here and
            # put the exit code and the tail into the failure.
            exited_before_deadline = server.poll() is not None
            server.terminate()
            try:
                out, _ = server.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()
                out, _ = server.communicate()
            raise AssertionError(
                "the installed minicc-web never answered /api/health within 60s; "
                f"exited_before_deadline={exited_before_deadline} rc={server.returncode}; "
                f"output tail: {(out or '')[-2000:]}"
            )
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=20) as home:
            assert home.status == 200, home.status
            html = home.read()
        assert b"<" in html, html[:200]
        bundle = next(iter(_manifest().values())).lstrip("/")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/{bundle}", timeout=30) as asset:
            assert asset.status == 200, asset.status
            payload = asset.read()
        assert len(payload) > 1000, len(payload)
    finally:
        server.terminate()
        try:
            out, _ = server.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
            out, _ = server.communicate()
    assert f"http://127.0.0.1:{port}/" in (out or ""), (out or "")[-2000:]
