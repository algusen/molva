import re

import pytest

from molva import output
from molva.transcriber.base import Segment

SEGMENTS = [
    Segment(start=0.0, end=4.2, text="Добрый день."),
    Segment(start=4.2, end=9.8, text="Сегодня поговорим о тестах."),
]


def test_render_txt_joins_segments_with_blank_line():
    text = output.render_txt(SEGMENTS)
    assert text == "Добрый день.\n\nСегодня поговорим о тестах."


def test_render_srt_format_and_timecodes():
    srt = output.render_srt(SEGMENTS)

    blocks = srt.split("\n\n")
    assert len(blocks) == 2
    assert blocks[0].startswith("1\n00:00:00,000 --> 00:00:04,200\nДобрый день.")
    assert blocks[1].startswith("2\n00:00:04,200 --> 00:00:09,800\n")

    timecode_re = re.compile(r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}")
    assert len(timecode_re.findall(srt)) == 2


def test_render_vtt_format_and_timecodes():
    vtt = output.render_vtt(SEGMENTS)

    assert vtt.startswith("WEBVTT\n\n")
    timecode_re = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}")
    assert len(timecode_re.findall(vtt)) == 2
    assert "," not in vtt.split("WEBVTT")[1]


def test_resolve_output_path_no_conflict(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"")

    path = output.resolve_output_path(str(source), "txt")

    assert path == tmp_path / "interview.txt"


def test_resolve_output_path_adds_suffix_on_conflict(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"")
    (tmp_path / "interview.txt").write_text("existing")

    path = output.resolve_output_path(str(source), "txt")

    assert path == tmp_path / "interview (1).txt"


def test_resolve_output_path_finds_first_free_suffix(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"")
    (tmp_path / "interview.txt").write_text("existing")
    (tmp_path / "interview (1).txt").write_text("existing")

    path = output.resolve_output_path(str(source), "txt")

    assert path == tmp_path / "interview (2).txt"


def test_write_sidecars_writes_requested_formats_and_does_not_overwrite(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"")
    (tmp_path / "interview.txt").write_text("user's own notes")

    written = output.write_sidecars(str(source), SEGMENTS, ["txt", "srt"])

    assert written == [str(tmp_path / "interview (1).txt"), str(tmp_path / "interview.srt")]
    assert (tmp_path / "interview.txt").read_text() == "user's own notes"
    assert "Добрый день." in (tmp_path / "interview (1).txt").read_text()
    assert "00:00:00,000" in (tmp_path / "interview.srt").read_text()


def test_write_sidecars_rejects_unknown_format(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"")

    with pytest.raises(ValueError):
        output.write_sidecars(str(source), SEGMENTS, ["docx"])


def test_notify_and_clipboard_are_noop_outside_macos(monkeypatch):
    monkeypatch.setattr(output.sys, "platform", "linux")
    # не должно бросать исключений и не должно вызывать subprocess
    output.notify("Pisar", "done")
    output.copy_to_clipboard("text")
