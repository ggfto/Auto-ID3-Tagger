import pytest

from autotag.metadata import (build_final, choose_album_and_year, choose_title, drop_unconfirmed_details, keep_spelling,
                              needs_release_info, nothing_to_change)


@pytest.mark.parametrize("new,filename,existing,expected", [
    # The file name knows the version.
    ("Set Me Free", "11_2nd Room - Set Me Free (Original Mix).mp3", None, "Set Me Free (Original Mix)"),
    ("Piano In the Dark", "Brenda Russell-Piano In The Dark - Edit.mp3", None, "Piano In the Dark (Edit)"),
    ("Cherish", "Kool _ The Gang-Cherish - Single Version.mp3", None, "Cherish (Single Version)"),
    # A version in the name replaces another one from the identification.
    ("Song (Radio Edit)", "A - Song (Extended Mix).mp3", None, "Song (Extended Mix)"),
    # A fuller description from the identification is kept.
    ("Can't You See (feat. Dessy Slavova) [Deepjack & Mr.Nu Remix]",
     "11_Stage Rockers - Can't You See (Deepjack _ Mr.Nu Remix).mp3", None,
     "Can't You See (feat. Dessy Slavova) (Deepjack & Mr.Nu Remix)"),
    # Brackets that are part of the title are not versions.
    ("Alone Again (Naturally)", "Gilbert O_Sullivan-Alone Again (Naturally).mp3", None, "Alone Again (Naturally)"),
    # A duplicate marker is not a version.
    ("Still", "Commodores-Still (2).mp3", None, "Still"),
    # Words confirmed by the file name are not lost.
    ("Hard to Say I'm Sorry", "Chicago-Hard To Say I_m SorryGet Away (Remastered Album Version).mp3",
     "Hard to Say I'm Sorry / Get Away", "Hard to Say I'm Sorry / Get Away (Remastered Album Version)"),
    # A wrong version in old tags does not come back.
    ("Another Day In Paradise", "Phil Collins-Another Day In Paradise.mp3",
     "Another Day in Paradise (TONIN Afrohouse remix)", "Another Day in Paradise"),
    # A repeated title in old tags is not a better spelling.
    ("Oh, Pretty Woman", "Roy Orbison-Oh, Pretty Woman.mp3", "Oh Pretty Woman (Oh Pretty Woman)", "Oh, Pretty Woman"),
    # Old tags that repeat the artist inside the title are not more complete.
    ("The Sound of Silence", "Simon _ Garfunkel-The Sound of Silence.mp3", "Simon & Garfunkel - Sound of Silence",
     "The Sound of Silence"),
    ("Human", "The Human League-Human.mp3", "The Human League", "Human"),
    # With no useful name, the version comes from the tags.
    ("Song", "Track 01.mp3", "Song (Extended Mix)", "Song (Extended Mix)"),
])
def test_choose_title(new, filename, existing, expected):
    assert choose_title(new, filename, existing) == expected


@pytest.mark.parametrize("new,existing,expected", [
    ("Sergio Mendes", "Sérgio Mendes", "Sérgio Mendes"),
    ("Sérgio Mendes", "Sergio Mendes", "Sérgio Mendes"),
    ("EXTREME", "Extreme", "Extreme"),
    ("Extreme", "EXTREME", "Extreme"),
    ("Air Supply", "air supply", "Air Supply"),
    ("Ain't No Sunshine", "Ain’t No Sunshine", "Ain’t No Sunshine"),
    ("The Commodores", "Commodores", "Commodores"),
    ("New Artist", "Old Artist", "New Artist"),
    ("New Artist", None, "New Artist"),
])
def test_keep_spelling(new, existing, expected):
    assert keep_spelling(new, existing) == expected


def catalog(album, year):
    return {"album": album, "year": year, "earliest_year": year, "any_album": album}


def test_same_album_takes_the_catalog_year():
    proposal = {"album": "Sergio Mendes", "year": "1966"}
    info = catalog("Sérgio Mendes", "1983")
    assert choose_album_and_year(proposal, "Never Gonna Let You Go", {}, info) == ("Sergio Mendes", "1983")


def test_earlier_studio_album_replaces_the_identification():
    proposal = {"album": "Bonnie", "year": "2005"}
    info = catalog("Faster Than the Speed of Night", "1983")
    assert choose_album_and_year(proposal, "Total Eclipse", {}, info) == ("Faster Than the Speed of Night", "1983")


@pytest.mark.parametrize("info", [catalog("Gumbo", "2017"), catalog("It's Too Late", "1977")])
def test_catalog_without_an_earlier_release_does_not_replace_the_identification(info):
    proposal = {"album": "Bee Gees: 1976 - 1979 - EP", "year": "1977"}
    assert choose_album_and_year(proposal, "How Deep", {}, info) == ("Bee Gees: 1976 - 1979 - EP", "1977")


def test_unreliable_catalog_album_is_ignored():
    proposal = {"album": "Divide", "year": "2017"}
    assert choose_album_and_year(proposal, "Shape of You", {}, catalog("Various Tracks", "2015")) == ("Divide", "2017")


def test_catalog_fills_what_the_identification_does_not_have():
    assert choose_album_and_year({"album": None, "year": None}, "Song", {}, catalog("Album", "1990")) == ("Album", "1990")


def test_specific_recording_keeps_its_own_release():
    proposal = {"album": "In Concert (Live)", "year": "2005"}
    info = {"album": "Lost in Love", "year": "1980", "earliest_year": "1980", "any_album": "Lost in Love"}
    assert choose_album_and_year(proposal, "All Out Of Love (Live)", {}, info) == ("In Concert (Live)", "2005")
    assert not needs_release_info(proposal, "All Out Of Love (Live)")


def test_unreliable_album_is_not_written():
    proposal = {"album": "Every Time You Go Away (Re-recorded - Sped Up) - Single", "year": "2006"}
    existing = {"album": "The Secret of Association", "year": None}
    assert choose_album_and_year(proposal, "Every Time", existing, None) == ("The Secret of Association", "2006")


def test_earlier_year_is_used_without_a_studio_album():
    proposal = {"album": "Hits", "year": "2011"}
    info = {"earliest_year": "1995", "any_album": "Other"}
    assert choose_album_and_year(proposal, "Song", {}, info) == ("Hits", "1995")


def test_fields_without_new_value_keep_the_current_one():
    existing = {"artist": "A", "title": "T", "album": "Album", "year": "1999", "genre": "Pop"}
    final = build_final({"artist": "A", "title": "T"}, "A - T.mp3", existing, None)
    assert (final["album"], final["year"], final["genre"]) == ("Album", "1999", "Pop")


def test_nothing_to_change_needs_a_cover_when_one_is_available():
    existing = {"artist": "A", "title": "T", "album": "B", "year": "1999", "genre": "Pop", "has_cover": False}
    final = {"artist": "A", "title": "T", "album": "B", "year": "1999", "genre": "Pop", "cover_art": "http://x"}
    assert not nothing_to_change(final, existing)
    assert nothing_to_change(final, {**existing, "has_cover": True})
    assert nothing_to_change({**final, "cover_art": None}, existing)


FROM_CATALOG = {"album": "Album", "year": "1990", "cover_art": "http://album", "earliest_year": "1980",
                "any_album": "Hits", "any_cover": "http://hits"}


def test_catalog_cover_goes_with_the_catalog_album():
    final = build_final({"artist": "A", "title": "T"}, "A - T.mp3", {}, FROM_CATALOG)
    assert (final["album"], final["cover_art"]) == ("Album", "http://album")


def test_catalog_cover_does_not_replace_the_one_in_the_file():
    final = build_final({"artist": "A", "title": "T"}, "A - T.mp3", {"has_cover": True}, FROM_CATALOG)
    assert final["cover_art"] is None


def test_catalog_cover_is_not_used_for_another_album():
    proposal = {"artist": "A", "title": "T", "album": "Own", "year": "1985"}
    final = build_final(proposal, "A - T.mp3", {}, {**FROM_CATALOG, "year": "2000"})
    assert (final["album"], final["cover_art"]) == ("Own", None)


def test_identified_cover_wins_over_the_catalog():
    final = build_final({"artist": "A", "title": "T", "cover_art": "http://own"}, "A - T.mp3", {}, FROM_CATALOG)
    assert final["cover_art"] == "http://own"


@pytest.mark.parametrize("title,filename,expected", [
    ("Heat Waves (instrumental)", "63 - Glass Animals - Heat Waves.mp3", "Heat Waves"),
    ("abcdefu (demo)", "61 - GAYLE - abcdefu.mp3", "abcdefu"),
    ("Temperature (Album Version)", "11 - Temperature - Sean Paul - The Trinity.mp3", "Temperature"),
    # The file name confirms these.
    ("Cold Heart (PNAU Remix)", "01 - Cold Heart - PNAU Remix - Elton John.mp3", "Cold Heart (PNAU Remix)"),
    ("MONTERO (Call Me by Your Name)", "22 - Lil Nas X - MONTERO (Call Me By Your Name).mp3",
     "MONTERO (Call Me by Your Name)"),
    # A small typo in the file name is still a confirmation.
    ("Belly Dancer (Bonanza)", "58 - Akon - Bananza (Belly Dancer).mp3", "Belly Dancer (Bonanza)"),
    # A title made only of brackets is left alone.
    ("(Untitled)", "Artist - Song.mp3", "(Untitled)"),
])
def test_drop_unconfirmed_details(title, filename, expected):
    assert drop_unconfirmed_details(title, filename) == expected
