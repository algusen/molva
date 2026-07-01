import shutil
import subprocess
import wave

import pytest

from molva import audio

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _gen_tone(path, duration_sec=2.0, rate=44100):
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={duration_sec}:sample_rate={rate}",
            "-ac", "2",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _gen_video_with_audio(path, duration_sec=2.0):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:size=64x64:duration={duration_sec}",
            "-f", "lavfi", "-i", f"sine=frequency=300:duration={duration_sec}",
            "-shortest",
            "-c:v", "libx264", "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _gen_video_no_audio(path, duration_sec=1.0):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=red:size=64x64:duration={duration_sec}",
            "-c:v", "libx264",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_probe_reports_duration_and_audio(tmp_path):
    tone_path = tmp_path / "tone.wav"
    _gen_tone(tone_path, duration_sec=2.0)

    result = audio.probe(str(tone_path))

    assert result.has_audio is True
    assert result.duration_sec == pytest.approx(2.0, abs=0.2)


def test_probe_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        audio.probe("/no/such/file.wav")


def test_probe_video_without_audio_raises_unsupported(tmp_path):
    video_path = tmp_path / "silent.mp4"
    _gen_video_no_audio(video_path)

    with pytest.raises(audio.UnsupportedMediaError):
        audio.probe(str(video_path))


def test_to_wav16k_mono_converts_audio_file(tmp_path):
    tone_path = tmp_path / "tone.wav"
    _gen_tone(tone_path, duration_sec=1.5, rate=44100)

    out_path = audio.to_wav16k_mono(str(tone_path), out_dir=str(tmp_path / "out"))

    with wave.open(out_path, "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1


def test_to_wav16k_mono_extracts_audio_track_from_video(tmp_path):
    video_path = tmp_path / "clip.mp4"
    _gen_video_with_audio(video_path, duration_sec=1.5)

    out_path = audio.to_wav16k_mono(str(video_path), out_dir=str(tmp_path / "out"))

    with wave.open(out_path, "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        assert wf.getnframes() / wf.getframerate() == pytest.approx(1.5, abs=0.2)


def test_to_wav16k_mono_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        audio.to_wav16k_mono(str(tmp_path / "missing.wav"))
