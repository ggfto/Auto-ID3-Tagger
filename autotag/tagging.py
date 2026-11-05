"""From an identification to the file: shared by the automatic run and the review."""
import os

from . import audiofile, backup, identify, metadata
from .matching import build_reference, matches_reference


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


def identify_file(path, acoustid_key, reference):
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
            if matches_reference(candidate['artist'], candidate['title'], reference):
                return candidate, "AcoustID"

    proposal = identify.identify_shazam(path)
    if proposal:
        return proposal, "Shazam"
    if candidates:
        return candidates[0], "AcoustID"
    return None, ""


def process_file(path, acoustid_key, state_dir):
    """Handles one file and returns its report row. Failures raise."""
    existing = audiofile.read_tags(path)
    reference = build_reference(os.path.basename(path), existing)
    proposal, source = identify_file(path, acoustid_key, reference)
    if not proposal:
        return {"path": path, "status": "unidentified",
                "old_artist": existing['artist'], "old_title": existing['title']}

    if reference and not matches_reference(proposal['artist'], proposal['title'], reference):
        return {**identification_row(path, existing, proposal, source), "status": "review",
                "detail": "differs from the file name (or current tags, if the name says nothing)"}

    status = "tagged" if reference else "tagged_no_reference"
    return write_proposal(path, proposal, existing, source, status, state_dir)
