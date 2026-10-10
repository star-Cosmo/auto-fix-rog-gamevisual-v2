"""Unit tests for the two-tier run log, flush, and UAC append mode."""

from pathlib import Path

from gamevisual_fixer.logger import RunLog


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_success_log_excludes_trace(tmp_path: Path) -> None:
    """On success, debug-tier (trace) lines are dropped; detail stays."""
    log = RunLog(log_dir=tmp_path)
    log.log("start")
    log.detail("always-detail")
    log.trace("debug-only")
    log.set_summary("ok")
    text = _read(log.finish())
    assert "start" in text
    assert "always-detail" in text
    assert "debug-only" not in text


def test_failed_log_includes_trace(tmp_path: Path) -> None:
    """On failure, debug-tier lines are included so support gets full detail."""
    log = RunLog(log_dir=tmp_path)
    log.log("start")
    log.trace("debug-only")
    log.log_error("boom")
    log.set_summary("failed")
    text = _read(log.finish())
    assert "debug-only" in text
    assert "失败" in text


def test_debug_mode_includes_trace_on_success(tmp_path: Path) -> None:
    """--debug forces debug-tier lines even on a successful run."""
    log = RunLog(log_dir=tmp_path, debug=True)
    log.log("start")
    log.trace("debug-only")
    text = _read(log.finish())
    assert "debug-only" in text


def test_flush_writes_without_result_section(tmp_path: Path) -> None:
    """flush() persists steps but leaves the result section to finish()."""
    log = RunLog(log_dir=tmp_path)
    log.log("step1")
    path = log.flush()
    text = _read(path)
    assert "step1" in text
    assert "执行结果" not in text


def test_append_mode_merges_child_into_parent_log(tmp_path: Path) -> None:
    """The elevated child appends to the parent's file without a second BOM."""
    parent = RunLog(log_dir=tmp_path)
    parent.log("parent-step")
    parent_path = parent.flush()

    child = RunLog(append_to=parent_path, log_dir=tmp_path)
    child.log("child-step")
    child.set_summary("child done")
    returned = child.finish()

    assert returned == parent_path
    text = _read(parent_path)
    assert "parent-step" in text
    assert "child-step" in text
    assert text.startswith("\ufeff")
    assert text.count("\ufeff") == 1  # no second BOM from the child


def test_module_bus_is_noop_without_activation() -> None:
    """detail/trace are harmless no-ops until a run log is activated."""
    from gamevisual_fixer import logger

    logger.deactivate()
    logger.detail("should not raise")
    logger.trace("should not raise")


def test_log_error_marks_failure(tmp_path: Path) -> None:
    """log_error flips the run to 失败 and records the message."""
    log = RunLog(log_dir=tmp_path)
    log.log("start")
    log.log_error("something broke")
    text = _read(log.finish())
    assert "失败" in text
    assert "something broke" in text


def test_log_exception_includes_traceback(tmp_path: Path) -> None:
    """log_exception records the exception type, message, and marks failure."""
    log = RunLog(log_dir=tmp_path)
    try:
        raise ValueError("boom")
    except ValueError as exc:
        log.log_exception(exc)
    text = _read(log.finish())
    assert "ValueError" in text
    assert "boom" in text
    assert "失败" in text
