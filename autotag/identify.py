"""Identification services. Failures raise, so the caller can try the file again later."""
import asyncio
import re
from functools import lru_cache

import acoustid
import musicbrainzngs
from aiohttp_retry import ExponentialRetry
from shazamio import HTTPClient, Serialize, Shazam
from shazamio.exceptions import FailedDecodeJson

from .matching import same_recording
from .pacing import Pacer

musicbrainzngs.set_useragent("AutoID3Tagger", "0.4", "https://github.com/ggfto/Auto-ID3-Tagger")

SHAZAM_PACER = Pacer(start_interval=5, min_interval=4, max_interval=30, cooldown=60)
ACOUSTID_MIN_SCORE = 0.8
ACOUSTID_INVALID_KEY = 4
ACOUSTID_TIMEOUT_SECONDS = 30
COVER_URL = "https://coverartarchive.org/release-group/{}/front-1200"
# MusicBrainz spells names with typographic hyphens, which hide words from comparisons.
PLAIN_HYPHENS = str.maketrans({"\u2010": "-", "\u2011": "-"})


class RateLimited(Exception):
    """The service refused the request because of its rate limit."""


async def _recognize(path):
    # One attempt: retries belong to the run's queue, where they do not hold a thread.
    client = HTTPClient(retry_options=ExponentialRetry(attempts=1))
    return await Shazam(http_client=client).recognize(path)


def identify_shazam(path):
    """Returns a proposal, or None when Shazam has no match."""
    SHAZAM_PACER.wait()
    try:
        out = asyncio.run(_recognize(path))
    except FailedDecodeJson as e:
        # Shazam answers HTTP 429 with an HTML page, which is what fails to decode.
        SHAZAM_PACER.limited()
        raise RateLimited("Shazam") from e
    SHAZAM_PACER.succeeded()

    if len(out['matches']) < 1:
        return None

    track = out['track']
    data = Serialize.track(track)
    images = track.get('images', {})
    proposal = {
        'title': track['title'],
        'artist': track['subtitle'],
        'genre': track.get('genres', {}).get('primary'),
        'album': None,
        'year': None,
        'cover_art': images['coverarthq'].replace("400x400", "1000x1000") if 'coverarthq' in images else None,
    }

    for section in data.sections:
        if section.type == "SONG":
            for md in section.metadata:
                if md.title == "Album":
                    proposal['album'] = md.text
                if md.title == "Released":
                    proposal['year'] = md.text
    return proposal


@lru_cache(maxsize=512)
def identify_acoustid(api_key, path):
    """
    Proposals for the recordings AcoustID is confident about, best first.

    Cached because a file waiting for Shazam is tried again from the start. A failure
    only means Shazam decides, except a bad key, which no retry can fix.
    """
    try:
        duration, fingerprint = acoustid.fingerprint_file(path)
        response = acoustid.lookup(api_key, fingerprint, duration, timeout=ACOUSTID_TIMEOUT_SECONDS)
        if response.get("error", {}).get("code") == ACOUSTID_INVALID_KEY:
            raise ValueError("invalid AcoustID API key")
        results = list(acoustid.parse_lookup_result(response))
    except acoustid.AcoustidError as e:
        print(f"AcoustID failed, using Shazam: {path}: {e}")
        return []
    return [{'title': title.translate(PLAIN_HYPHENS), 'artist': artist.translate(PLAIN_HYPHENS),
             'album': None, 'year': None, 'genre': None, 'cover_art': None}
            for score, _recording_id, title, artist in results
            if score > ACOUSTID_MIN_SCORE and title and artist]


def _year(release):
    match = re.match(r"\d{4}", release.get("date") or "")
    return match.group() if match else None


def _is_studio_album(release):
    group = release.get("release-group", {})
    return group.get("primary-type") == "Album" and not group.get("secondary-type-list")


def _cover_url(release):
    group_id = release.get("release-group", {}).get("id")
    return COVER_URL.format(group_id) if group_id else None


def _date_and_name(release):
    return release[:2]


def fetch_release_info(artist, title):
    """
    Earliest official release of exactly this artist and title, or None.

    A search returns mostly compilations and bootlegs, so a large page is read and
    only official releases count.
    """
    result = musicbrainzngs.search_recordings(artist=artist, recording=title, limit=100)

    albums, others = [], []
    for recording in result.get("recording-list", []):
        if not same_recording(recording.get("artist-credit-phrase"), recording.get("title"), artist, title):
            continue
        for release in recording.get("release-list", []):
            year = _year(release)
            if release.get("status") == "Official" and year:
                (albums if _is_studio_album(release) else others).append((year, (release.get("title") or "").translate(PLAIN_HYPHENS), _cover_url(release)))

    if not albums and not others:
        return None
    earliest = min(albums + others, key=_date_and_name)
    info = {"earliest_year": earliest[0], "any_album": earliest[1], "any_cover": earliest[2]}
    if albums:
        info["year"], info["album"], info["cover_art"] = min(albums, key=_date_and_name)
    return info
