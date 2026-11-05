import pytest

from autotag import identify, report, review, tagging


@pytest.fixture
def row(tmp_path, monkeypatch):
    monkeypatch.setattr(identify, "fetch_release_info", lambda artist, title: None)
    written = []
    monkeypatch.setattr(tagging.audiofile, "write_tags", lambda path, final: written.append(final))
    monkeypatch.setattr(tagging.audiofile, "read_tags", lambda path: {
        "artist": "Old", "title": "Old Title", "album": None, "year": None, "genre": None, "has_cover": False})
    path = tmp_path / "Shannon - Let the Music Play.mp3"
    path.write_bytes(b"x" * 300)
    data = {"path": str(path), "status": "review", "source": "Shazam", "new_artist": "euginethedj",
            "new_title": "Let the Music Play", "album": "EP", "year": "2020", "genre": "House", "cover_art": ""}
    data["written"] = written
    return data


def test_accept_writes_the_identification(row, tmp_path):
    result = review.accept(row, str(tmp_path / "state"))
    assert row["written"][0]["artist"] == "euginethedj"
    assert result["status"] == "tagged"


def test_use_file_name_writes_the_name(row, tmp_path):
    result = review.use_file_name(row, str(tmp_path / "state"))
    assert (row["written"][0]["artist"], row["written"][0]["title"]) == ("Shannon", "Let the Music Play")
    assert result["status"] == "tagged_from_name"
    assert result["source"] == "File name"


def test_use_file_name_needs_artist_and_title(tmp_path):
    with pytest.raises(ValueError):
        review.use_file_name({"path": str(tmp_path / "Just a Title.mp3")}, str(tmp_path))


def test_reject_changes_nothing(row):
    assert review.reject(row)["status"] == "rejected"
    assert row["written"] == []


def test_pending_only_lists_reviews_under_the_folder(tmp_path):
    state = str(tmp_path / "state")
    log = report.Report(state)
    log.add({"path": str(tmp_path / "in" / "a.mp3"), "status": "review"})
    log.add({"path": str(tmp_path / "in" / "b.mp3"), "status": "tagged"})
    log.add({"path": str(tmp_path / "out" / "c.mp3"), "status": "review"})
    log.close()

    assert [r["path"] for r in review.pending(str(tmp_path / "in"), state)] == [str(tmp_path / "in" / "a.mp3")]


def test_latest_decision_wins(tmp_path):
    state = str(tmp_path / "state")
    log = report.Report(state)
    log.add({"path": str(tmp_path / "a.mp3"), "status": "review"})
    log.add({"path": str(tmp_path / "a.mp3"), "status": "rejected"})
    log.close()

    assert review.pending(str(tmp_path), state) == []
