import pytest

from autotag import identify, tagging

REFERENCE = ("Artist", "Song")


def proposal(artist, title):
    return {"artist": artist, "title": title, "album": None, "year": None, "genre": None, "cover_art": None}


@pytest.fixture
def services(monkeypatch):
    """Sets what each service answers and records the calls to Shazam."""
    state = {"acoustid": [], "shazam": None, "shazam_calls": 0}

    def shazam(path):
        state["shazam_calls"] += 1
        if isinstance(state["shazam"], Exception):
            raise state["shazam"]
        return state["shazam"]

    monkeypatch.setattr(identify, "identify_acoustid", lambda key, path: state["acoustid"])
    monkeypatch.setattr(identify, "identify_shazam", shazam)
    return state


def test_confirmed_acoustid_result_saves_the_shazam_request(services):
    services["acoustid"] = [proposal("Artist", "Song")]
    assert tagging.identify_file("f", "key", REFERENCE)[1] == "AcoustID"
    assert services["shazam_calls"] == 0


def test_detail_the_file_name_does_not_have_is_dropped(services):
    services["acoustid"] = [proposal("Artist", "Song (instrumental)")]
    assert tagging.identify_file("Artist - Song.mp3", "key", REFERENCE)[0]["title"] == "Song"


def test_any_confident_candidate_can_be_the_confirmed_one(services):
    services["acoustid"] = [proposal("Someone Else", "Other"), proposal("Artist", "Song")]
    assert tagging.identify_file("f", "key", REFERENCE) == (proposal("Artist", "Song"), "AcoustID")


def test_shazam_decides_when_acoustid_differs_from_the_name(services):
    services["acoustid"] = [proposal("Someone Else", "Other")]
    services["shazam"] = proposal("Artist", "Song")
    assert tagging.identify_file("f", "key", REFERENCE) == (proposal("Artist", "Song"), "Shazam")


def test_unconfirmed_acoustid_result_is_used_only_when_shazam_has_nothing(services):
    services["acoustid"] = [proposal("Someone Else", "Other")]
    assert tagging.identify_file("f", "key", REFERENCE) == (proposal("Someone Else", "Other"), "AcoustID")


def test_without_a_reference_shazam_is_asked_first(services):
    services["acoustid"] = [proposal("Artist", "Song")]
    services["shazam"] = proposal("Shazam Artist", "Song")
    assert tagging.identify_file("f", "key", None)[1] == "Shazam"


def test_without_a_key_only_shazam_is_used(services):
    services["acoustid"] = [proposal("Artist", "Song")]
    assert tagging.identify_file("f", None, REFERENCE) == (None, "")


def test_shazam_refusal_is_not_replaced_by_an_unconfirmed_result(services):
    services["acoustid"] = [proposal("Someone Else", "Other")]
    services["shazam"] = identify.RateLimited("Shazam")
    with pytest.raises(identify.RateLimited):
        tagging.identify_file("f", "key", REFERENCE)


TAGS = {"artist": "Queen", "title": "Bohemia", "album": None, "year": None, "genre": None, "has_cover": False}


@pytest.fixture
def pipeline(services, monkeypatch):
    """process_file without touching a file; returns the state and what would be written."""
    written = []
    monkeypatch.setattr(tagging.audiofile, "read_tags", lambda path: dict(TAGS))
    monkeypatch.setattr(tagging.backup, "backup_tag", lambda path, state_dir: None)
    monkeypatch.setattr(tagging.audiofile, "write_tags", lambda path, final: written.append(final))
    services["written"] = written
    return services


def good_album(monkeypatch):
    info = {"album": "Album", "year": "1990", "earliest_year": "1990", "any_album": "Album"}
    monkeypatch.setattr(identify, "fetch_release_info", lambda artist, title: info)


def doubtful_album(monkeypatch):
    info = {"album": "Bravo Hits 7", "year": "1995", "earliest_year": "1990", "any_album": "Bravo Hits 7"}
    monkeypatch.setattr(identify, "fetch_release_info", lambda artist, title: info)


def test_trusted_catalog_album_needs_no_shazam(pipeline, monkeypatch):
    good_album(monkeypatch)
    pipeline["acoustid"] = [proposal("Queen", "Bohemia")]

    row = tagging.process_file("Queen - Bohemia.mp3", "key", "state")

    assert pipeline["shazam_calls"] == 0
    assert row["source"] == "AcoustID"
    assert pipeline["written"][0]["album"] == "Album"


def test_doubtful_album_takes_the_release_data_from_shazam(pipeline, monkeypatch):
    doubtful_album(monkeypatch)
    pipeline["acoustid"] = [proposal("Queen", "Bohemia")]
    pipeline["shazam"] = {**proposal("Queen", "Bohemia"), "album": "Own", "year": "1991", "genre": "Pop",
                          "cover_art": "http://own"}

    row = tagging.process_file("Queen - Bohemia.mp3", "key", "state")

    assert row["source"] == "AcoustID+Shazam"
    final = pipeline["written"][0]
    assert (final["album"], final["year"], final["genre"], final["cover_art"]) == ("Own", "1991", "Pop", "http://own")


def test_shazam_naming_another_song_is_ignored(pipeline, monkeypatch):
    doubtful_album(monkeypatch)
    pipeline["acoustid"] = [proposal("Queen", "Bohemia")]
    pipeline["shazam"] = {**proposal("Other", "Different"), "album": "Wrong", "year": "1991"}

    row = tagging.process_file("Queen - Bohemia.mp3", "key", "state")

    # The tags already say this artist and title, so without Shazam's album nothing changes.
    assert (row["source"], row["status"]) == ("AcoustID", "unchanged")
    assert row["album"] != "Wrong"
    assert pipeline["written"] == []


def test_unconfirmed_fingerprint_waits_for_review_even_if_the_title_matches(pipeline):
    pipeline["acoustid"] = [proposal("The Bloomsbury Set", "Stayin Alive")]

    row = tagging.process_file("Stayin' Alive_Bee Gees.mp3", "key", "state")

    assert row["status"] == "review"
    assert pipeline["written"] == []


def test_live_album_is_not_used_for_a_title_that_is_not_live(pipeline, monkeypatch):
    info = {"album": "Studio", "year": "1995", "earliest_year": "1979", "any_album": "Studio"}
    monkeypatch.setattr(identify, "fetch_release_info", lambda artist, title: info)
    pipeline["acoustid"] = [proposal("Queen", "Bohemia")]
    pipeline["shazam"] = {**proposal("Queen", "Bohemia"), "album": "Rio After Dark (Live In Rio)", "year": "2002",
                          "genre": "Rock", "cover_art": "http://live"}

    tagging.process_file("Queen - Bohemia.mp3", "key", "state")

    final = pipeline["written"][0]
    assert (final["album"], final["year"], final["genre"], final["cover_art"]) == ("Studio", "1995", "Rock", None)
