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


def write_proposal(path, proposal, existing, source, status, state_dir):
    """Completes the proposal, writes it if it changes anything, and returns the report row."""
    filename = os.path.basename(path)
    title = metadata.choose_title(proposal['title'], filename, existing.get('title'))
    release_info = None
    if metadata.needs_release_info(proposal, title):
        release_info = identify.fetch_release_info(proposal['artist'], proposal['title'])
    final = metadata.build_final(proposal, filename, existing, release_info)

    row = identification_row(path, existing, {**proposal, **final}, source)
    if metadata.nothing_to_change(final, existing):
        return {**row, "status": "unchanged"}

    backup.backup_tag(path, state_dir)
    audiofile.write_tags(path, final)
    return {**row, "status": status}


def identify_file(path, acoustid_key):
    """(proposal, source), or (None, '') when nothing matched. A Shazam failure raises if nothing else answers."""
    shazam_error = None
    try:
        proposal = identify.identify_shazam(path)
        if proposal:
            return proposal, "Shazam"
    except Exception as e:
        shazam_error = e

    if acoustid_key:
        proposal = identify.identify_acoustid(acoustid_key, path)
        if proposal:
            return proposal, "AcoustID"
    if shazam_error:
        raise shazam_error
    return None, ""


def process_file(path, acoustid_key, state_dir):
    """Handles one file and returns its report row. Failures raise."""
    existing = audiofile.read_tags(path)
    proposal, source = identify_file(path, acoustid_key)
    if not proposal:
        return {"path": path, "status": "unidentified",
                "old_artist": existing['artist'], "old_title": existing['title']}

    reference = build_reference(os.path.basename(path), existing)
    if reference and not matches_reference(proposal['artist'], proposal['title'], reference):
        return {**identification_row(path, existing, proposal, source), "status": "review",
                "detail": "differs from the file name (or current tags, if the name says nothing)"}

    status = "tagged" if reference else "tagged_no_reference"
    return write_proposal(path, proposal, existing, source, status, state_dir)
