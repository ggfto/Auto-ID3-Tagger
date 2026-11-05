"""Decisions about files that need a person. `run_review` is only the terminal front end."""
import os

from . import audiofile, report, tagging
from .matching import file_stem, split_stem
from .metadata import clean_file_text


def pending(folder, state_dir):
    """Report rows waiting for a decision, under folder."""
    return [row for row in report.load(state_dir).values()
            if row["status"] == "review" and report.is_under(row["path"], folder)]


def name_proposal(path):
    """Artist and title as written in the file name, or None if the name does not have both."""
    artist, title = split_stem(file_stem(os.path.basename(path)))
    if not artist:
        return None
    return {"artist": clean_file_text(artist), "title": clean_file_text(title)}


def accept(row, state_dir):
    """Uses the identification. Returns the new report row."""
    proposal = {"artist": row["new_artist"], "title": row["new_title"], "album": row.get("album"),
                "year": row.get("year"), "genre": row.get("genre"), "cover_art": row.get("cover_art")}
    return _write(row["path"], proposal, row.get("source"), "tagged", state_dir)


def use_file_name(row, state_dir):
    """
    Uses the artist and title from the file name. Returns the new report row.

    The current album, year and cover are removed, since they came with the wrong
    artist and title; the catalog fills them when it knows this recording.
    """
    proposal = name_proposal(row["path"])
    if not proposal:
        raise ValueError("the file name does not have an artist and a title")
    return _write(row["path"], proposal, "File name", "tagged_from_name", state_dir, discard_release=True)


def reject(row):
    """Leaves the file as it is. Returns the new report row."""
    return {**row, "status": "rejected"}


def _write(path, proposal, source, status, state_dir, discard_release=False):
    was_cloud_only = audiofile.is_cloud_only(path)
    try:
        existing = audiofile.read_tags(path)
        return tagging.write_proposal(path, proposal, existing, source, status, state_dir, discard_release)
    finally:
        if was_cloud_only:
            audiofile.free_local_copy(path)


PROMPT = "[a]ccept identification / use file [n]ame / [r]eject / [s]kip / [q]uit: "


def run_review(folder, state_dir):
    rows = pending(folder, state_dir)
    print(f"{len(rows)} file(s) to review")
    log = report.Report(state_dir)
    try:
        for index, row in enumerate(rows, 1):
            print(f"\n[{index}/{len(rows)}] {os.path.basename(row['path'])}")
            print(f"  folder:         {os.path.dirname(row['path'])}")
            print(f"  current tags:   {row['old_artist']} - {row['old_title']}")
            print(f"  identification: {row['new_artist']} - {row['new_title']}  ({row['album']}, {row['year']})")
            print(f"  from file name: {name_proposal(row['path'])}")

            choice = _ask()
            if choice == "q":
                break
            if choice == "s":
                continue
            try:
                if choice == "a":
                    log.add(accept(row, state_dir))
                elif choice == "n":
                    log.add(use_file_name(row, state_dir))
                else:
                    log.add(reject(row))
            except Exception as e:
                print(f"  Could not apply: {e!r}. The file stays in the review.")
    finally:
        log.close()


def _ask():
    while True:
        try:
            choice = input(PROMPT).strip().lower()
        except EOFError:
            return "q"
        if choice in ("a", "n", "r", "s", "q"):
            return choice
