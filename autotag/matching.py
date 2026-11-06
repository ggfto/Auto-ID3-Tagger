"""Compares an identification with what a file claims to be."""
import difflib
import os
import re
import unicodedata

STOPWORDS = {"feat", "ft", "featuring", "the", "a", "e", "and", "de", "da", "do", "with", "vs"}
PLACEHOLDER_TOKENS = {"track", "faixa", "audio", "musica", "music", "song", "unknown", "desconhecido",
                      "untitled", "artist", "artista", "title", "titulo", "various", "mp3"}


def token_list(text):
    """Lowercase, accent-free words of text in order, without stopwords."""
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(c for c in normalized if not unicodedata.combining(c)).lower()
    return [t for t in re.split(r"[^a-z0-9]+", normalized) if t and t not in STOPWORDS]


def tokens(text):
    return set(token_list(text))


def core_title(title):
    """Title without bracketed details such as (Original Mix) or [Remix]."""
    return re.sub(r"[(\[{].*?[)\]}]", " ", title or "")


def coverage(wanted, available):
    """Fraction of wanted tokens found in available, tolerating small typos."""
    if not wanted:
        return 0.0
    found = sum(1 for w in wanted
                if w in available
                or any(difflib.SequenceMatcher(None, w, a).ratio() >= 0.85 for a in available))
    return found / len(wanted)


def is_informative(text):
    """False for empty values and placeholders such as 'Track 01' or 'Unknown Artist'."""
    return any(not t.isdigit() and t not in PLACEHOLDER_TOKENS for t in tokens(text))


def file_stem(filename):
    """File name without extension and leading track number."""
    return re.sub(r"^\d+[\s._-]+", "", os.path.splitext(filename)[0])


def split_stem(stem):
    """(artist, title) from 'Artist - Title' or 'Artist-Title'; artist is empty if there is no separator."""
    parts = re.split(r"\s+[-–—]\s+", stem, maxsplit=1)
    if len(parts) < 2:
        parts = stem.split("-", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", stem)


def build_reference(filename, existing):
    """
    The (artist, title) a file claims to be, or None if it says nothing useful.

    A useful file name wins over the tags: tags may have been written by an earlier
    automatic run, so they would only confirm that run's mistakes.
    """
    stem = file_stem(filename)
    if is_informative(stem):
        return split_stem(stem)
    if is_informative(existing.get("title")):
        artist = existing.get("artist")
        return (artist if is_informative(artist) else "", existing["title"])
    return None


def matches_reference(artist, title, reference):
    ref_artist, ref_title = reference
    everything = tokens(f"{ref_artist} {ref_title}")
    title_tokens = tokens(core_title(title))
    # Numbers such as a year in "Summer Jam 2003" are often missing from the file name.
    words = {t for t in title_tokens if not t.isdigit()} or title_tokens
    if coverage(words, everything) < 0.7:
        return False
    if not ref_artist:
        return True

    # Sides are tested separately because some files are named "Title - Artist".
    identified = tokens(artist)
    return (coverage(identified, everything) >= 0.6
            or coverage(tokens(ref_artist), identified) >= 0.6
            or coverage(tokens(ref_title), identified) >= 0.6)


def confirms_fingerprint(artist, title, reference, existing_artist):
    """
    Stricter than matches_reference, because a confirmed fingerprint skips Shazam.

    Similar recordings share a fingerprint, so a cover or a later version must not
    pass on its title alone.
    """
    if not matches_reference(artist, title, reference):
        return False
    ref_artist, ref_title = reference
    known = tokens(f"{ref_artist} {ref_title} {existing_artist or ''}")
    if not {t for t in tokens(core_title(title)) if t.isdigit()} <= known:
        return False
    return bool(ref_artist) or coverage(tokens(artist), known) >= 0.6


def same_recording(artist_a, title_a, artist_b, title_b):
    """Strict check used to accept data from a catalog search."""
    return (tokens(artist_a) == tokens(artist_b)
            and tokens(core_title(title_a)) == tokens(core_title(title_b)))
