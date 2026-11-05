"""Reads and writes tags of the supported audio formats."""
import logging
import os
import re
import stat
import struct
import subprocess
import urllib.request

import eyed3
import eyed3.core
from eyed3.id3.frames import ImageFrame
from mutagen.asf import ASF, ASFByteArrayAttribute
from mutagen.mp4 import MP4, MP4Cover

from .backup import id3v2_size

eyed3.log.setLevel(logging.ERROR)

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wma")
DOWNLOAD_TIMEOUT_SECONDS = 60
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000


def is_audio_file(filename):
    # "._name.mp3" files are macOS metadata, not audio.
    return filename.lower().endswith(AUDIO_EXTENSIONS) and not filename.startswith("._")


def download_cover(url):
    """(bytes, mime type) of the cover, or None if it cannot be downloaded."""
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            return response.read(), response.headers.get_content_type()
    except Exception as e:
        print(f"Error downloading cover art: {e}")
        return None


def _year_of(value):
    match = re.search(r"\b\d{4}\b", str(value or ""))
    return match.group() if match else None


# --- MP3 ---

def _read_mp3(path):
    audio = eyed3.load(path)
    if not audio or not audio.tag:
        return {}
    tag = audio.tag
    date = tag.getBestDate()
    return {'artist': tag.artist, 'title': tag.title, 'album': tag.album,
            'year': str(date.year) if date and date.year else None,
            'genre': tag.genre.name if tag.genre else None,
            'has_cover': len(tag.images) > 0}


def remove_corrupted_tag(path):
    """Removes an ID3v2 tag that eyed3 cannot read. Back the file up first."""
    with open(path, 'rb') as f:
        data = f.read()
    size = id3v2_size(data[:10], len(data))
    if not size:
        return False
    with open(path, 'wb') as f:
        f.write(data[size:])
    print(f"Removed corrupted ID3 tag from: {os.path.basename(path)}")
    return True


def _write_mp3(path, final, cover):
    try:
        audio = eyed3.load(path)
    except Exception:
        if not remove_corrupted_tag(path):
            raise
        audio = eyed3.load(path)

    if not audio:
        raise ValueError("could not load the file as MP3")
    if not audio.tag:
        audio.initTag()

    tag = audio.tag
    tag.artist = final['artist']
    tag.album_artist = final['artist']
    tag.title = final['title']
    # Fields without a new value keep what the file already has.
    if final.get('album'):
        tag.album = final['album']
    if final.get('genre'):
        tag.genre = final['genre']
    year = _year_of(final.get('year'))
    if year:
        tag.recording_date = eyed3.core.Date(int(year))
    if cover:
        tag.images.set(ImageFrame.FRONT_COVER, cover[0], cover[1])
    # Frames read from the file keep their encoding, and Latin-1 cannot hold every new value.
    tag.save(version=(2, 3, 0), encoding="utf16")


def _clear_mp3(path):
    audio = eyed3.load(path)
    if not audio or not audio.tag:
        return
    tag = audio.tag
    tag.album = None
    tag.recording_date = None
    tag.release_date = None
    tag.original_release_date = None
    for image in list(tag.images):
        tag.images.remove(image.description)
    tag.save(version=(2, 3, 0))


# --- M4A ---

def _first(tags, key):
    values = tags.get(key)
    return str(values[0]) if values else None


def _read_m4a(path):
    tags = MP4(path).tags
    if not tags:
        return {}
    return {'artist': _first(tags, '\xa9ART'), 'title': _first(tags, '\xa9nam'), 'album': _first(tags, '\xa9alb'),
            'year': _year_of(_first(tags, '\xa9day')), 'genre': _first(tags, '\xa9gen'),
            'has_cover': bool(tags.get('covr'))}


def _write_m4a(path, final, cover):
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags['\xa9ART'] = [final['artist']]
    tags['aART'] = [final['artist']]
    tags['\xa9nam'] = [final['title']]
    if final.get('album'):
        tags['\xa9alb'] = [final['album']]
    if final.get('genre'):
        tags['\xa9gen'] = [final['genre']]
    year = _year_of(final.get('year'))
    if year:
        tags['\xa9day'] = [year]
    if cover:
        image_format = MP4Cover.FORMAT_PNG if cover[1] == "image/png" else MP4Cover.FORMAT_JPEG
        tags['covr'] = [MP4Cover(cover[0], imageformat=image_format)]
    audio.save()


def _clear_keys(audio, keys):
    if audio.tags:
        for key in keys:
            if key in audio.tags:
                del audio.tags[key]
        audio.save()


def _clear_m4a(path):
    _clear_keys(MP4(path), ('\xa9alb', '\xa9day', 'covr'))


# --- WMA ---

def _read_wma(path):
    tags = ASF(path).tags
    if not tags:
        return {}
    return {'artist': _first(tags, 'Author'), 'title': _first(tags, 'Title'), 'album': _first(tags, 'WM/AlbumTitle'),
            'year': _year_of(_first(tags, 'WM/Year')), 'genre': _first(tags, 'WM/Genre'),
            'has_cover': bool(tags.get('WM/Picture'))}


def _wma_picture(data, mime):
    front_cover = 3
    header = struct.pack("<BI", front_cover, len(data))
    return ASFByteArrayAttribute(header + mime.encode("utf-16-le") + b"\0\0" + b"\0\0" + data)


def _write_wma(path, final, cover):
    audio = ASF(path)
    tags = audio.tags
    tags['Author'] = [final['artist']]
    tags['WM/AlbumArtist'] = [final['artist']]
    tags['Title'] = [final['title']]
    if final.get('album'):
        tags['WM/AlbumTitle'] = [final['album']]
    if final.get('genre'):
        tags['WM/Genre'] = [final['genre']]
    year = _year_of(final.get('year'))
    if year:
        tags['WM/Year'] = [year]
    if cover:
        tags['WM/Picture'] = [_wma_picture(cover[0], cover[1])]
    audio.save()


def _clear_wma(path):
    _clear_keys(ASF(path), ('WM/AlbumTitle', 'WM/Year', 'WM/Picture'))


READERS = {".mp3": _read_mp3, ".m4a": _read_m4a, ".wma": _read_wma}
WRITERS = {".mp3": _write_mp3, ".m4a": _write_m4a, ".wma": _write_wma}
CLEARERS = {".mp3": _clear_mp3, ".m4a": _clear_m4a, ".wma": _clear_wma}


def _extension(path):
    return os.path.splitext(path)[1].lower()


def read_tags(path):
    """Current tags; empty when there are none or they cannot be read."""
    empty = {'artist': None, 'title': None, 'album': None, 'year': None, 'genre': None, 'has_cover': False}
    try:
        return {**empty, **READERS[_extension(path)](path)}
    except Exception:
        return empty  # A corrupted tag is handled when writing.


def clear_release_tags(path):
    """Removes album, year and cover."""
    CLEARERS[_extension(path)](path)


def write_tags(path, final):
    cover = download_cover(final['cover_art']) if final.get('cover_art') else None
    WRITERS[_extension(path)](path, final, cover)


# --- OneDrive ---

def is_cloud_only(path):
    attributes = getattr(os.stat(path), "st_file_attributes", 0)
    return bool(attributes & (stat.FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS))


def free_local_copy(path):
    """Asks OneDrive to keep the file in the cloud only, as it was before the run."""
    subprocess.run(["attrib", "-P", "+U", path], check=False, capture_output=True)
