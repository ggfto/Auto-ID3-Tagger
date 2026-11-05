"""Identification services. Failures raise, so the caller can try the file again later."""
import asyncio
import re

import acoustid
import musicbrainzngs
from aiohttp_retry import ExponentialRetry
from shazamio import HTTPClient, Serialize, Shazam

from .matching import same_recording

musicbrainzngs.set_useragent("AutoID3Tagger", "0.4", "https://github.com/ggfto/Auto-ID3-Tagger")


async def _recognize(path):
    # One attempt: retries belong to the run's queue, where they do not hold a thread.
    client = HTTPClient(retry_options=ExponentialRetry(attempts=1))
    return await Shazam(http_client=client).recognize(path)


def identify_shazam(path):
    """Returns a proposal, or None when Shazam has no match."""
    out = asyncio.run(_recognize(path))
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


def identify_acoustid(api_key, path):
    for score, _recording_id, title, artist in acoustid.match(api_key, path):
        if score > 0.8 and title and artist:
            return {'title': title, 'artist': artist, 'album': None, 'year': None, 'genre': None, 'cover_art': None}
    return None


def _year(release):
    match = re.match(r"\d{4}", release.get("date") or "")
    return match.group() if match else None


def _is_studio_album(release):
    group = release.get("release-group", {})
    return group.get("primary-type") == "Album" and not group.get("secondary-type-list")


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
                (albums if _is_studio_album(release) else others).append((year, release.get("title")))

    if not albums and not others:
        return None
    info = {"earliest_year": min(albums + others)[0], "any_album": min(albums + others)[1]}
    if albums:
        info["year"], info["album"] = min(albums)
    return info
