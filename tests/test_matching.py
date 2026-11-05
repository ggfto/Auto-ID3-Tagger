import pytest

from autotag.matching import build_reference, is_informative, matches_reference, same_recording


def accepts(filename, artist, title, existing=None):
    reference = build_reference(filename, existing or {})
    return reference is None or matches_reference(artist, title, reference)


@pytest.mark.parametrize("filename,artist,title", [
    ("11_2nd Room - Set Me Free (Original Mix).mp3", "2nd Room", "Set Me Free"),
    ("Commodores-Still (2).mp3", "The Commodores", "Still"),
    ("Kool _ The Gang-Cherish - Single Version.mp3", "Kool & The Gang", "Cherish"),
    ("Marvin Gaye-Lets Get It On.mp3", "Marvin Gaye", "Let's Get It On"),
    ("Sergio Mendes-Never Gonna Let You Go.mp3", "Sérgio Mendes", "Never Gonna Let You Go"),
    ("Set Me Free.mp3", "2nd Room", "Set Me Free"),
    ("Set Me Free - 2nd Room.mp3", "2nd Room", "Set Me Free"),
    ("Dance - The Underdog Project - Summer Jam.m4a", "The Underdog Project", "Summer Jam 2003 (Summermix)"),
    ("Artist - 1979.mp3", "Artist", "1979"),
])
def test_accepts_identification_that_agrees_with_the_name(filename, artist, title):
    assert accepts(filename, artist, title)


@pytest.mark.parametrize("filename,artist,title", [
    ("10_Shannon - Let the Music Play (John Reyton Version).mp3", "euginethedj", "Let the Music Play"),
    ("Quincy Jones-Just Once.mp3", "James Ingram", "Just Once (New Version)"),
    ("Kid Cudi-The Resurrection Of Scott Mescudi.mp3", "Elton John", "Can You Feel The Love Tonight"),
    ("The Greatest Love Band-I Will Be Right Here Waiting for You.mp3", "True Songs Makers", "Right Here Waiting"),
])
def test_rejects_identification_that_differs_from_the_name(filename, artist, title):
    assert not accepts(filename, artist, title)


def test_file_name_wins_over_tags_that_agree_with_the_identification():
    existing = {"artist": "Elton John", "title": "Can You Feel the Love Tonight"}
    assert not accepts("Kid Cudi-Resurrection.mp3", "Elton John", "Can You Feel the Love Tonight", existing)


def test_tags_are_the_reference_when_the_name_says_nothing():
    existing = {"artist": "Bee Gees", "title": "Too Much Heaven"}
    assert accepts("Track 01.mp3", "Bee Gees", "Too Much Heaven", existing)
    assert not accepts("Track 01.mp3", "Someone Else", "Another Song", existing)


def test_no_reference_when_name_and_tags_say_nothing():
    assert build_reference("Track 01.mp3", {"artist": "Unknown Artist", "title": ""}) is None


def test_placeholders_are_not_informative():
    assert not is_informative("Faixa 12")
    assert is_informative("2nd Room")


def test_catalog_results_must_be_the_same_recording():
    assert same_recording("Sérgio Mendes", "Never Gonna Let You Go", "Sergio Mendes", "Never Gonna Let You Go (Live)")
    assert not same_recording("2nd Today", "Set Free", "2nd Room", "Set Me Free")
