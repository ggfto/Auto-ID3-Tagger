import pytest

from autotag.backup import backup_tag, id3v2_size, restore_tag

AUDIO = b"\xff\xfb" + b"a" * 2000
V2 = b"ID3\x03\x00\x00\x00\x00\x00\x0a" + b"x" * 10
V1 = b"TAG" + b"y" * 125


def write(path, data):
    path.write_bytes(data)
    return str(path)


def test_size_of_a_tag_larger_than_the_file_is_invalid():
    with pytest.raises(ValueError):
        id3v2_size(b"ID3\x03\x00\x00\x00\x00\x7f\x7f", 100)


def test_file_without_tag_has_size_zero():
    assert id3v2_size(AUDIO[:10], len(AUDIO)) == 0


@pytest.mark.parametrize("original", [V2 + AUDIO + V1, V2 + AUDIO, AUDIO + V1, AUDIO])
def test_restore_returns_the_exact_original_file(tmp_path, original):
    path = write(tmp_path / "song.mp3", original)
    backup_tag(path, str(tmp_path / "state"))
    write(tmp_path / "song.mp3", b"ID3\x03\x00\x00\x00\x00\x00\x05zzzzz" + AUDIO + b"TAG" + b"n" * 125)

    restore_tag(path, str(tmp_path / "state"))

    assert (tmp_path / "song.mp3").read_bytes() == original


def test_first_backup_is_never_replaced(tmp_path):
    original = V2 + AUDIO
    path = write(tmp_path / "song.mp3", original)
    state = str(tmp_path / "state")
    backup_tag(path, state)
    write(tmp_path / "song.mp3", b"ID3\x03\x00\x00\x00\x00\x00\x05zzzzz" + AUDIO)
    backup_tag(path, state)

    restore_tag(path, state)

    assert (tmp_path / "song.mp3").read_bytes() == original


def test_other_formats_are_restored_from_a_full_copy(tmp_path):
    path = write(tmp_path / "song.m4a", b"original")
    state = str(tmp_path / "state")
    backup_tag(path, state)
    write(tmp_path / "song.m4a", b"changed")

    restore_tag(path, state)

    assert (tmp_path / "song.m4a").read_bytes() == b"original"
