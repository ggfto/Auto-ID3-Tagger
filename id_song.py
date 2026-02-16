import asyncio
import os
import urllib.request
import argparse
import eyed3
import eyed3.plugins.art
import musicbrainzngs
import acoustid
from shazamio import Shazam, Serialize

# Initialize MusicBrainz user agent
musicbrainzngs.set_useragent("AutoID3Tagger", "0.2", "https://github.com/ggfto/Auto-ID3-Tagger")

def remove_corrupted_tag(path):
    """
    Manually removes ID3v2 tag if eyed3 fails to read it due to encoding errors.
    """
    try:
        with open(path, 'rb') as f:
            header = f.read(10)

        if header.startswith(b'ID3'):
            # Synchsafe integer conversion
            size = (header[6] << 21) | (header[7] << 14) | (header[8] << 7) | header[9]
            tag_size = 10 + size

            # Check flags for footer (bit 4)
            flags = header[5]
            if (flags & 0x10):
                tag_size += 10

            # Safety check: don't delete if tag size seems huge (larger than file)
            file_size = os.path.getsize(path)
            if tag_size >= file_size:
                print(f"Warning: Tag size {tag_size} seems invalid for {path} (size: {file_size}). Skipping removal.")
                return False

            with open(path, 'rb') as f:
                f.seek(tag_size)
                audio_data = f.read()

            with open(path, 'wb') as f:
                f.write(audio_data)

            print(f"Removed corrupted ID3 tag from: {os.path.basename(path)}")
            return True
    except Exception as e:
        print(f"Failed to remove bad tag for {path}: {e}")
    return False

async def identify_shazam(shazam_client, path):
    try:
        out = await shazam_client.recognize(path)
        if len(out['matches']) < 1:
            return None

        track = out['track']
        data = Serialize.track(track)

        tags = {
            'title': track['title'],
            'artist': track['subtitle'],
            'genre': track['genres']['primary'] if 'primary' in track.get('genres', {}) else None,
            'album': None,
            'year': None,
            'cover_art': track['images']['coverarthq'].replace("400x400", "1000x1000") if 'images' in track and 'coverarthq' in track['images'] else None
        }

        for section in data.sections:
            if section.type == "SONG":
                for md in section.metadata:
                    if md.title == "Album":
                        tags['album'] = md.text
                    if md.title == "Released":
                        tags['year'] = md.text

        return tags
    except Exception as e:
        print(f"Shazam error: {e}")
        return None

def identify_acoustid(api_key, path):
    try:
        results = acoustid.match(api_key, path)
        for score, recording_id, title, artist in results:
            if score > 0.8:
                return {
                    'title': title,
                    'artist': artist,
                    'album': None, # AcoustID simple lookup might not give album
                    'year': None,
                    'genre': None,
                    'cover_art': None,
                    'musicbrainz_id': recording_id
                }
    except Exception as e:
        print(f"AcoustID error: {e}")
    return None

def fetch_musicbrainz_metadata(artist, title):
    print(f"Fetching MusicBrainz metadata for: {artist} - {title}")
    try:
        # Search for recordings
        result = musicbrainzngs.search_recordings(artist=artist, recording=title, limit=1)
        if result['recording-count'] == 0:
            return None

        recording = result['recording-list'][0]

        tags = {
            'title': recording['title'],
            'artist': recording['artist-credit-phrase'],
            'album': None,
            'year': None,
            'genre': None
        }

        if 'release-list' in recording and len(recording['release-list']) > 0:
            release = recording['release-list'][0]
            tags['album'] = release['title']
            if 'date' in release:
                tags['year'] = release['date'].split('-')[0]

        if 'tag-list' in recording:
             # Get the most popular tag as genre
             tags['genre'] = max(recording['tag-list'], key=lambda t: int(t['count']))['name']

        return tags
    except Exception as e:
        print(f"MusicBrainz error: {e}")
        return None

async def main(music_folder, acoustid_key=None):
    shazam = Shazam()

    if not os.path.exists(music_folder):
        print(f"Error: Path '{music_folder}' not found.")
        return

    print(f"Scanning recursively: {music_folder}")

    for root, dirs, files in os.walk(music_folder):
        for file in files:
            path = os.path.join(root, file)

            if not os.path.isfile(path):
                continue
            if not file.lower().endswith(".mp3"):
                continue

            print(f"Processing: {file}")

            tags = None
            source = None

            # 1. Try Shazam
            tags = await identify_shazam(shazam, path)
            if tags:
                source = "Shazam"

            # 2. Try AcoustID if Shazam failed and key provided
            if not tags and acoustid_key:
                print("Shazam failed, trying AcoustID...")
                tags = identify_acoustid(acoustid_key, path)
                if tags:
                    source = "AcoustID"

            if not tags:
                print(f"Could not identify: {file}")
                continue

            # 3. Enhance with MusicBrainz (Optional but recommended)
            # If we have basic info, validade/enhance with MB
            mb_tags = fetch_musicbrainz_metadata(tags['artist'], tags['title'])
            if mb_tags:
                print("Enhanced with MusicBrainz data")
                # Merge tags, preferring MB for text data, but keeping Shazam/AcoustID cover art/genre if missing
                tags['album'] = mb_tags.get('album') or tags.get('album')
                tags['year'] = mb_tags.get('year') or tags.get('year')
                # Use MB artist/title for standardization
                tags['artist'] = mb_tags['artist']
                tags['title'] = mb_tags['title']
                if not tags.get('genre'):
                    tags['genre'] = mb_tags.get('genre')

            print(f"Identified ({source}): {tags['artist']} - {tags['title']} ({tags.get('album', 'Unknown Album')})")

            # Apply tags
            try:
                try:
                    id3 = eyed3.load(path)
                except Exception:
                    if remove_corrupted_tag(path):
                        id3 = eyed3.load(path)
                    else:
                        raise

                if not id3:
                    print(f"Could not load ID3 tags for {file}")
                    continue

                if not id3.tag:
                    id3.initTag()

                id3.tag.album = tags.get('album')
                id3.tag.artist = tags['artist']
                id3.tag.album_artist = tags['artist']
                id3.tag.genre = tags.get('genre')
                id3.tag.title = tags['title']
                id3.tag.year = tags.get('year')

                # Handle Cover Art
                if tags.get('cover_art'):
                    local_art = os.path.join(root, "tmp_file" + tags['cover_art'][-4:])
                    try:
                        urllib.request.urlretrieve(tags['cover_art'], local_art)
                        id3_front_cover_id = eyed3.utils.art.TO_ID3_ART_TYPES['FRONT_COVER'][0]
                        id3_cover = eyed3.plugins.art.ArtFile(local_art)
                        id3_cover.id3_art_type = id3_front_cover_id
                        id3.tag.images.set(id3_cover.id3_art_type, id3_cover.image_data, id3_cover.mime_type)
                    except Exception as e:
                        print(f"Error downloading cover art: {e}")
                    finally:
                        if os.path.exists(local_art):
                            os.remove(local_art)

                id3.tag.save(version=(2, 3, 0))
                print("Saved new tags")

            except Exception as e:
                print(f"Error tagging {file}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto ID3 Tagger via Shazam, AcoustID & MusicBrainz")
    parser.add_argument("folder", help="path to the music folder")
    parser.add_argument("--acoustid-key", help="Optional API key for AcoustID recognition", required=False)
    args = parser.parse_args()

    asyncio.run(main(args.folder, args.acoustid_key))
