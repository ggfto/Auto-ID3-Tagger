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
