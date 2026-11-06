"""From an identification to the file: shared by the automatic run and the review."""
import os

from . import audiofile, backup, identify, metadata
from .matching import build_reference, confirms_fingerprint, matches_reference


RELEASE_FIELDS = ('album', 'year', 'genre', 'cover_art')


def identification_row(path, existing, proposal, source):
    return {"path": path, "source": source,
            "old_artist": existing['artist'], "old_title": existing['title'],
            "new_artist": proposal['artist'], "new_title": proposal['title'],
            "album": proposal.get('album'), "year": proposal.get('year'),
            "genre": proposal.get('genre'), "cover_art": proposal.get('cover_art')}


def write_proposal(path, proposal, existing, source, status, state_dir, discard_release=False):
    """
    Completes the proposal, writes it if it changes anything, and returns the report row.

    discard_release is for when the current tags describe another recording: their
    album, year and cover are removed instead of kept.
    """
    filename = os.path.basename(path)
    if discard_release:
        existing = {**existing, 'album': None, 'year': None, 'has_cover': False}
    title = metadata.choose_title(proposal['title'], filename, existing.get('title'))
    release_info = None
    if metadata.needs_release_info(proposal, title):
        release_info = identify.fetch_release_info(proposal['artist'], proposal['title'])
    final = metadata.build_final(proposal, filename, existing, release_info)

    row = identification_row(path, existing, {**proposal, **final}, source)
    if not discard_release and metadata.nothing_to_change(final, existing):
        return {**row, "status": "unchanged"}

    backup.backup_tag(path, state_dir)
    if discard_release:
        audiofile.clear_release_tags(path)
    audiofile.write_tags(path, final)
    return {**row, "status": status}


def identify_file(path, acoustid_key, reference, existing_artist=None):
    """
    (proposal, source), or (None, '') when nothing matched.

    AcoustID has no tight rate limit, so a result the file name confirms saves a Shazam
    request. Anything else goes to Shazam, which finds more songs and has richer data.
    """
    candidates = identify.identify_acoustid(acoustid_key, path) if acoustid_key else []
    filename = os.path.basename(path)
    candidates = [{**c, 'title': metadata.drop_unconfirmed_details(c['title'], filename)} for c in candidates]
    if reference:
        for candidate in candidates:
            if confirms_fingerprint(candidate['artist'], candidate['title'], reference, existing_artist):
                return candidate, "AcoustID"

    proposal = identify.identify_shazam(path)
    if proposal:
        return proposal, "Shazam"
    if candidates:
        return candidates[0], "AcoustID"
    return None, ""


def _agrees(proposal, source, reference, existing):
    if source == "AcoustID":
        return confirms_fingerprint(proposal['artist'], proposal['title'], reference, existing['artist'])
    return matches_reference(proposal['artist'], proposal['title'], reference)


def with_shazam_release(path, proposal, reference, title):
    """The proposal with Shazam's release data, if Shazam names the same song and recording."""
    other = identify.identify_shazam(path)
    if not other or not matches_reference(other['artist'], other['title'], reference):
        return proposal, "AcoustID"
    if metadata.is_album_of_another_recording(other.get('album'), title):
        return {**proposal, 'genre': other.get('genre')}, "AcoustID"
    return {**proposal, **{field: other.get(field) for field in RELEASE_FIELDS}}, "AcoustID+Shazam"


def process_file(path, acoustid_key, state_dir):
    """Handles one file and returns its report row. Failures raise."""
    existing = audiofile.read_tags(path)
    reference = build_reference(os.path.basename(path), existing)
    proposal, source = identify_file(path, acoustid_key, reference, existing['artist'])
    if not proposal:
        return {"path": path, "status": "unidentified",
                "old_artist": existing['artist'], "old_title": existing['title']}

    if reference and not _agrees(proposal, source, reference, existing):
        return {**identification_row(path, existing, proposal, source), "status": "review",
                "detail": "differs from the file name (or current tags, if the name says nothing)"}

    if source == "AcoustID" and reference:
        title = metadata.choose_title(proposal['title'], os.path.basename(path), existing['title'])
        if metadata.album_is_doubtful(title, identify.fetch_release_info(proposal['artist'], proposal['title'])):
            proposal, source = with_shazam_release(path, proposal, reference, title)

    status = "tagged" if reference else "tagged_no_reference"
    return write_proposal(path, proposal, existing, source, status, state_dir)
