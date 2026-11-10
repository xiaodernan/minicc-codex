"""M8-T755 — ``minicc/atomic_file.py`` 的重试逻辑。

该模块是仓库里"Windows 共享冲突 ride-out"的唯一回答：``replace_with_retry`` 和
``read_text_with_retry``。此前它零同名测试（模块清单核对发现），但它的契约是
精确的、可测的：

1. 第一次就成功 → 只调用一次底层原语；
2. 前 N 次 ``PermissionError`` 后成功 → 总调用次数 N+1；
3. 预算耗尽 → 抛出最后一次 ``PermissionError``，调用次数恰好等于 ``attempts``；
4. ``delay`` 可以是 callable（调用形式）——grow-backoff 需求由 session/webauth
   两侧使用；这里用零距离 callable 验证它被按 ``attempts`` 次调用而不出错。
"""

from __future__ import annotations

import pytest

from minicc import atomic_file


def _permission_error(path) -> PermissionError:
    return PermissionError(5, "Access is denied", path)


class _FlakyReplace:
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls: list[tuple[str, str]] = []

    def __call__(self, source, target):
        self.calls.append((str(source), str(target)))
        if len(self.calls) <= self.fail_times:
            raise _permission_error(target)


def _make_flaky_read(fail_times: int, body: str = "payload"):
    calls: list[str] = []

    def fake_read_text(self, *args, **kwargs):
        calls.append(str(self))
        if len(calls) <= fail_times:
            raise _permission_error(self)
        return body

    return fake_read_text, calls


def test_replace_with_retry_first_try(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("payload", encoding="utf-8")
    fake = _FlakyReplace(fail_times=0)
    monkeypatch.setattr("os.replace", fake)
    atomic_file.replace_with_retry(src, dst, attempts=3, delay=0)
    assert [c[0] for c in fake.calls] == [str(src)]
    # 假原语不真移动文件；真实 os.replace 语义由其他集成测试覆盖
    assert len(fake.calls) == 1


def test_replace_with_retry_rides_out_transient_refusals(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("payload", encoding="utf-8")
    fake = _FlakyReplace(fail_times=2)
    monkeypatch.setattr("os.replace", fake)
    atomic_file.replace_with_retry(src, dst, attempts=4, delay=0)
    assert len(fake.calls) == 3  # 2 次 PermissionError + 1 次成功


def test_replace_with_retry_exhausts_budget_and_raises(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("payload", encoding="utf-8")
    fake = _FlakyReplace(fail_times=99)
    monkeypatch.setattr("os.replace", fake)
    with pytest.raises(PermissionError):
        atomic_file.replace_with_retry(src, dst, attempts=3, delay=0)
    assert len(fake.calls) == 3  # 预算恰好耗尽，不多不少


def test_replace_with_retry_accepts_a_callable_delay(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("payload", encoding="utf-8")
    fake = _FlakyReplace(fail_times=2)
    monkeypatch.setattr("os.replace", fake)
    seen: list[int] = []

    def grow(attempt: int) -> float:
        seen.append(attempt)
        return 0

    atomic_file.replace_with_retry(src, dst, attempts=5, delay=grow)
    assert seen == [0, 1]  # 每次失败后才问 delay(attempt)


def test_read_text_with_retry_first_try(tmp_path, monkeypatch):
    target = tmp_path / "f.txt"
    target.write_text("payload", encoding="utf-8")
    fake, calls = _make_flaky_read(fail_times=0)
    monkeypatch.setattr("pathlib.Path.read_text", fake)
    assert atomic_file.read_text_with_retry(target, attempts=3, delay=0) == "payload"
    assert len(calls) == 1


def test_read_text_with_retry_rides_out_transient_refusals(tmp_path, monkeypatch):
    target = tmp_path / "f.txt"
    target.write_text("payload", encoding="utf-8")
    fake, calls = _make_flaky_read(fail_times=2)
    monkeypatch.setattr("pathlib.Path.read_text", fake)
    assert atomic_file.read_text_with_retry(target, attempts=4, delay=0) == "payload"
    assert len(calls) == 3


def test_read_text_with_retry_exhausts_budget_and_raises(tmp_path, monkeypatch):
    target = tmp_path / "f.txt"
    target.write_text("payload", encoding="utf-8")
    fake, calls = _make_flaky_read(fail_times=99)
    monkeypatch.setattr("pathlib.Path.read_text", fake)
    with pytest.raises(PermissionError):
        atomic_file.read_text_with_retry(target, attempts=3, delay=0)
    assert len(calls) == 3


def test_default_budget_shape_matches_the_session_checkpoint():
    # 24 attempts x 50ms — session.py 的预算（原子性的公共形状）；勿再平铺
    assert atomic_file.DEFAULT_ATTEMPTS == 24
    assert atomic_file.DEFAULT_DELAY == 0.05
