import pytest
from unittest.mock import MagicMock
import process


@pytest.fixture(autouse=True)
def reset_module_state():
    process._reset_cancel()
    process._current_proc = None
    yield
    process._reset_cancel()
    process._current_proc = None


def test_progress_event_fields():
    e = process.ProgressEvent(step="transcription", pct=0.5, message="test")
    assert e.step == "transcription"
    assert e.pct == 0.5
    assert e.message == "test"


def test_progress_event_indeterminate_sentinel():
    e = process.ProgressEvent(step="gemini", pct=-1.0, message="")
    assert e.pct == -1.0


def test_process_cancelled_is_exception():
    with pytest.raises(process.ProcessCancelled):
        raise process.ProcessCancelled("annulé")


def test_cancel_sets_flag():
    process._reset_cancel()
    assert not process._cancel_requested
    process.cancel()
    assert process._cancel_requested
    process._reset_cancel()


def test_reset_cancel_clears_flag():
    process._cancel_requested = True
    process._reset_cancel()
    assert not process._cancel_requested


def test_emit_calls_callback():
    events = []
    process._emit(events.append, "transcription", 0.5, "test msg")
    assert len(events) == 1
    assert events[0].step == "transcription"
    assert events[0].pct == 0.5


def test_emit_noop_without_callback():
    process._emit(None, "transcription", 0.0, "msg")  # doit ne pas lever d'exception


def test_cancel_terminates_proc():
    mock_proc = MagicMock()
    process._current_proc = mock_proc
    process.cancel()
    mock_proc.terminate.assert_called_once()
    assert process._current_proc is None
