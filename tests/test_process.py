import pytest
import process


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
