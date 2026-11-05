import shutil
import subprocess

import pytest

from autotag import audiofile

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
ENCODERS = {"mp3": "libmp3lame", "m4a": "aac", "wma": "wmav2"}


def make_audio(tmp_path, extension):
    path = tmp_path / f"song.{extension}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:a", ENCODERS[extension], str(path)], check=True)
    return str(path)


@needs_ffmpeg
@pytest.mark.parametrize("extension", ENCODERS)
def test_tags_written_can_be_read_back(tmp_path, monkeypatch, extension):
    monkeypatch.setattr(audiofile, "download_cover", lambda url: (PNG, "image/png"))
    path = make_audio(tmp_path, extension)

    audiofile.write_tags(path, {"artist": "Sérgio Mendes", "title": "Song (Live)", "album": "Album", "year": "1983",
                                "genre": "Pop", "cover_art": "http://cover"})

    assert audiofile.read_tags(path) == {"artist": "Sérgio Mendes", "title": "Song (Live)", "album": "Album",
                                         "year": "1983", "genre": "Pop", "has_cover": True}


@needs_ffmpeg
@pytest.mark.parametrize("extension", ENCODERS)
def test_fields_without_a_value_keep_what_the_file_has(tmp_path, extension):
    path = make_audio(tmp_path, extension)
    audiofile.write_tags(path, {"artist": "A", "title": "T", "album": "Album", "year": "1999", "genre": "Pop"})

    audiofile.write_tags(path, {"artist": "B", "title": "U", "album": None, "year": None, "genre": None})

    tags = audiofile.read_tags(path)
    assert (tags["artist"], tags["album"], tags["year"], tags["genre"]) == ("B", "Album", "1999", "Pop")


@needs_ffmpeg
@pytest.mark.parametrize("extension", ENCODERS)
def test_clear_removes_only_album_year_and_cover(tmp_path, monkeypatch, extension):
    monkeypatch.setattr(audiofile, "download_cover", lambda url: (PNG, "image/png"))
    path = make_audio(tmp_path, extension)
    audiofile.write_tags(path, {"artist": "A", "title": "T", "album": "Album", "year": "1999", "genre": "Pop",
                                "cover_art": "http://cover"})

    audiofile.clear_release_tags(path)

    assert audiofile.read_tags(path) == {"artist": "A", "title": "T", "album": None, "year": None,
                                         "genre": "Pop", "has_cover": False}


def test_unreadable_file_reads_as_empty(tmp_path):
    path = tmp_path / "broken.m4a"
    path.write_bytes(b"not audio")
    assert audiofile.read_tags(str(path))["artist"] is None


@pytest.mark.parametrize("name,expected", [
    ("song.mp3", True), ("SONG.M4A", True), ("song.wma", True),
    ("._song.mp3", False), ("song.wav", False), ("song.kar", False),
])
def test_supported_files(name, expected):
    assert audiofile.is_audio_file(name) is expected
