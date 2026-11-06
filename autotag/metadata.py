"""Decides the final values to write, given an identification and what the file already has."""
import re

from .matching import coverage, file_stem, is_informative, split_stem, token_list, tokens

VERSION_WORDS = re.compile(
    r"\b(mix|remix|edit|version|versao|versão|live|remaster(ed)?|extended|radio|acoustic|acustico|acústico"
    r"|instrumental|dub|re-?record(ed|ing)?|rework|bootleg|mono|stereo|mashup|ao vivo)\b", re.IGNORECASE)
# These identify a different recording, so another release's album and year would be wrong for it.
SPECIFIC_RECORDING = re.compile(
    r"\b(remix|live|re-?record(ed|ing)?|rework|bootleg|mashup|ao vivo|acoustic|acustico|acústico|instrumental)\b",
    re.IGNORECASE)
UNRELIABLE_ALBUM = re.compile(
    r"sped[ -]up|slowed|nightcore|karaoke|tribute|podcast|workout|relax|lullab|ringtone|made famous"
    r"|in the style of|originally performed|various (tracks|artists)", re.IGNORECASE)

# Catalog albums with these names are compilations, even when catalogued as studio albums.
COMPILATION_ALBUM = re.compile(
    r"\b(hits|bravo|absolute|promo only|club mix|best of|vol(ume)?\.?\s*\d+)\b", re.IGNORECASE)
# A single often comes out the year before its album, but not much earlier.
MAX_YEARS_BEFORE_ALBUM = 1

BRACKETS = re.compile(r"\s*[(\[{]([^)\]}]*)[)\]}]")
TRAILING_DASH = re.compile(r"\s+[-–—]\s+([^-–—]+)$")


def version_details(text):
    """Version descriptions in text: 'X (Extended Mix) - Radio Edit' gives both."""
    found = [m.group(1) for m in BRACKETS.finditer(text or "") if VERSION_WORDS.search(m.group(1))]
    trailing = TRAILING_DASH.search(BRACKETS.sub("", text or ""))
    if trailing and VERSION_WORDS.search(trailing.group(1)):
        found.append(trailing.group(1))
    return [clean_file_text(v) for v in found]


def strip_versions(text):
    """text without its version descriptions; other brackets such as (feat. X) stay."""
    text = BRACKETS.sub(lambda m: "" if VERSION_WORDS.search(m.group(1)) else m.group(0), text or "")
    return TRAILING_DASH.sub(lambda m: "" if VERSION_WORDS.search(m.group(1)) else m.group(0), text).strip()


def clean_file_text(text):
    """File names replace characters such as '&' with '_'."""
    return " ".join(text.replace(" _ ", " & ").replace("_", " ").split())


def keep_spelling(new, existing):
    """Keeps the current spelling when both say the same words, unless the new one is clearly better."""
    if not existing or token_list(new) != token_list(existing):
        return new
    if sum(not c.isascii() and c.isalpha() for c in new) > sum(not c.isascii() and c.isalpha() for c in existing):
        return new
    if (existing.isupper() and not new.isupper()) or (existing.islower() and not new.islower()):
        return new
    return existing


def _more_complete_title(new_base, existing_base, stem):
    """Current title when it has more words than the new one and the file name confirms them."""
    extras = tokens(existing_base) - tokens(new_base)
    if not extras or not tokens(new_base) <= tokens(existing_base):
        return new_base
    # Only the title part counts: old tags often repeat the artist inside the title.
    squeezed = "".join(token_list(split_stem(stem)[1]))
    return existing_base if all(word in squeezed for word in extras) else new_base


def drop_unconfirmed_details(title, filename):
    """
    title without bracketed details the file name does not have.

    A fingerprint is shared by similar recordings, so a detail such as (instrumental)
    may belong to another one of them.
    """
    named = tokens(file_stem(filename))
    kept = BRACKETS.sub(lambda m: m.group(0) if coverage(tokens(m.group(1)), named) == 1 else "", title).strip()
    return kept or title


def choose_title(new_title, filename, existing_title):
    """
    Identified title, keeping what the file knows and the identification may not.

    The file name is the best source for a version, because an identification
    often reports another version of the same recording.
    """
    stem = file_stem(filename)
    informative = is_informative(stem)
    existing_base = strip_versions(existing_title)

    base = strip_versions(new_title)
    if informative:
        base = _more_complete_title(base, existing_base, stem)
    base = keep_spelling(base, existing_base)

    new_versions = version_details(new_title)
    file_versions = version_details(stem if informative else existing_title)
    versions = new_versions
    if file_versions and not tokens(" ".join(file_versions)) <= tokens(" ".join(new_versions)):
        versions = file_versions
    return " ".join([base] + [f"({v})" for v in versions])


def choose_album_and_year(proposal, title, existing, release_info):
    album = proposal.get("album")
    if album and UNRELIABLE_ALBUM.search(album):
        album = None
    match = re.search(r"\b\d{4}\b", str(proposal.get("year") or ""))
    year = match.group() if match else None

    if release_info and not SPECIFIC_RECORDING.search(title):
        catalog_album, catalog_year = release_info.get("album"), release_info.get("year")
        if catalog_album and (UNRELIABLE_ALBUM.search(catalog_album) or COMPILATION_ALBUM.search(catalog_album)):
            pass
        elif catalog_album and not (album and year):
            album, year = catalog_album, catalog_year
        elif catalog_album and tokens(catalog_album) == tokens(album):
            year = catalog_year
        elif catalog_album and catalog_year < year:
            album, year = catalog_album, catalog_year
        elif not catalog_album:
            earliest = release_info.get("earliest_year")
            if earliest and (not year or earliest < year):
                year = earliest
            album = album or release_info.get("any_album")
        # Otherwise the catalog has no earlier release, which usually means it holds a
        # reissue or a mislabeled release, so the identification stays.

    return album or existing.get("album"), year or existing.get("year")


def album_is_doubtful(title, release_info):
    """True when the catalog alone cannot be trusted for the album of this title."""
    if SPECIFIC_RECORDING.search(title) or not release_info or not release_info.get("album"):
        return True
    if COMPILATION_ALBUM.search(release_info["album"]):
        return True
    return int(release_info["year"]) - int(release_info["earliest_year"]) > MAX_YEARS_BEFORE_ALBUM


def is_album_of_another_recording(album, title):
    """A live album, for instance, when nothing says the file is a live recording."""
    return bool(album and SPECIFIC_RECORDING.search(album) and not SPECIFIC_RECORDING.search(title))


def needs_release_info(proposal, title):
    """A specific recording only asks the catalog when something is missing."""
    return not SPECIFIC_RECORDING.search(title) or not (proposal.get("album") and proposal.get("year"))


def choose_cover(proposal, album, existing, release_info):
    """The identified cover, or the catalog's when the file has none and the album is that release."""
    if proposal.get("cover_art"):
        return proposal["cover_art"]
    if existing.get("has_cover") or not release_info:
        return None
    if album == release_info.get("album"):
        return release_info.get("cover_art")
    if album == release_info.get("any_album"):
        return release_info.get("any_cover")
    return None


def build_final(proposal, filename, existing, release_info):
    title = choose_title(proposal["title"], filename, existing.get("title"))
    album, year = choose_album_and_year(proposal, title, existing, release_info)
    return {
        "artist": keep_spelling(proposal["artist"], existing.get("artist")),
        "title": title,
        "album": album,
        "year": year,
        "genre": proposal.get("genre") or existing.get("genre"),
        "cover_art": choose_cover(proposal, album, existing, release_info),
    }


def nothing_to_change(final, existing):
    same_text = all(final.get(field) == existing.get(field) for field in ("artist", "title", "album", "year", "genre"))
    return same_text and (existing.get("has_cover") or not final.get("cover_art"))
