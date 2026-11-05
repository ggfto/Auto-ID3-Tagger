import acoustid
import pytest

from autotag import identify


@pytest.fixture
def lookup(monkeypatch):
    """Sets AcoustID's answer without reading a file or using the network."""
    identify.identify_acoustid.cache_clear()
    monkeypatch.setattr(acoustid, "fingerprint_file", lambda path: (200, "fp"))

    def answer(response):
        def fake(*args, **kwargs):
            if isinstance(response, Exception):
                raise response
            return response
        monkeypatch.setattr(acoustid, "lookup", fake)
    yield answer
    identify.identify_acoustid.cache_clear()


def result(score, title, artist):
    recording = {"id": "r", "title": title, "artists": [{"name": artist}]}
    return {"score": score, "recordings": [recording]}


def test_only_confident_results_are_kept(lookup):
    lookup({"status": "ok", "results": [result(0.95, "Song", "Artist"), result(0.79, "Other", "Other")]})
    found = identify.identify_acoustid("key", "a.mp3")
    assert [(p["artist"], p["title"]) for p in found] == [("Artist", "Song")]


def test_typographic_hyphens_become_plain(lookup):
    lookup({"status": "ok", "results": [result(0.95, "Maniac (re\u2010recorded)", "Run\u2010D.M.C.")]})
    found = identify.identify_acoustid("key", "a.mp3")[0]
    assert (found["artist"], found["title"]) == ("Run-D.M.C.", "Maniac (re-recorded)")


def test_invalid_key_is_a_failure_that_retries_cannot_fix(lookup):
    lookup({"status": "error", "error": {"code": 4, "message": "invalid API key"}})
    with pytest.raises(ValueError):
        identify.identify_acoustid("key", "a.mp3")


@pytest.mark.parametrize("response", [
    acoustid.WebServiceError("down"),
    {"status": "error", "error": {"code": 14, "message": "too many requests"}},
])
def test_other_failures_leave_the_decision_to_shazam(lookup, response):
    lookup(response)
    assert identify.identify_acoustid("key", "a.mp3") == []


def test_lookup_is_not_repeated_for_a_file_retried_later(lookup, monkeypatch):
    calls = []
    monkeypatch.setattr(acoustid, "lookup", lambda *a, **k: calls.append(a) or {"status": "ok", "results": []})
    identify.identify_acoustid("key", "a.mp3")
    identify.identify_acoustid("key", "a.mp3")
    assert len(calls) == 1


def release(title, date, group_id, primary="Album", status="Official"):
    return {"title": title, "date": date, "status": status,
            "release-group": {"id": group_id, "primary-type": primary}}


def test_release_info_has_the_cover_of_each_release(monkeypatch):
    recording = {"artist-credit-phrase": "A", "title": "T", "release-list": [
        release("Hits", "1980", "g1", primary="Compilation"), release("Album", "1990", "g2")]}
    monkeypatch.setattr(identify.musicbrainzngs, "search_recordings",
                        lambda **kwargs: {"recording-list": [recording]})

    info = identify.fetch_release_info("A", "T")

    assert (info["album"], info["year"]) == ("Album", "1990")
    assert info["cover_art"] == identify.COVER_URL.format("g2")
    assert (info["any_album"], info["any_cover"]) == ("Hits", identify.COVER_URL.format("g1"))


def test_release_without_a_group_can_tie_with_one_that_has_it(monkeypatch):
    same = [release("Album", "1990", "g1"), {"title": "Album", "date": "1990", "status": "Official",
                                             "release-group": {"primary-type": "Album"}}]
    monkeypatch.setattr(identify.musicbrainzngs, "search_recordings", lambda **kwargs: {
        "recording-list": [{"artist-credit-phrase": "A", "title": "T", "release-list": same}]})
    assert identify.fetch_release_info("A", "T")["album"] == "Album"
