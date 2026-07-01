import pytest

from molva.transcriber.base import Segment
from molva.transcriber.stub import StubTranscriber


def test_segment_rejects_invalid_bounds():
    with pytest.raises(ValueError):
        Segment(start=2.0, end=1.0, text="x")


def test_segment_rejects_empty_or_unstripped_text():
    with pytest.raises(ValueError):
        Segment(start=0.0, end=1.0, text="")
    with pytest.raises(ValueError):
        Segment(start=0.0, end=1.0, text=" x ")


def test_stub_transcribes_short_clip_into_single_segment(make_wav):
    wav_path = make_wav(duration_sec=3.0)
    transcriber = StubTranscriber(segment_len=5.0)

    segments = transcriber.transcribe(wav_path, language="ru")

    assert len(segments) == 1
    assert segments[0].start == 0.0
    assert segments[0].end == pytest.approx(3.0, abs=1e-2)
    assert segments[0].text


def test_stub_splits_long_clip_into_multiple_segments(make_wav):
    wav_path = make_wav(duration_sec=12.0)
    transcriber = StubTranscriber(segment_len=5.0)

    segments = transcriber.transcribe(wav_path, language="ru")

    assert len(segments) == 3
    assert segments[0].start == 0.0
    assert segments[-1].end == pytest.approx(12.0, abs=1e-2)
    # contiguous, sorted, no overlap
    for prev, cur in zip(segments, segments[1:], strict=False):
        assert prev.end == cur.start


def test_stub_empty_input_does_not_crash(make_wav):
    wav_path = make_wav(duration_sec=0.0)
    transcriber = StubTranscriber()

    segments = transcriber.transcribe(wav_path, language="ru")

    assert segments == []
